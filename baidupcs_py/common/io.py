from typing import Optional, List, Tuple, Dict, Union, Any, Callable, Generator, IO
from io import BytesIO, UnsupportedOperation
from enum import Enum
from pathlib import Path
from zlib import crc32
from random import Random
import os
import hashlib
import logging
import time

from baidupcs_py.common import constant
from baidupcs_py.common.number import u64_to_u8x8, u8x8_to_u64
from baidupcs_py.common.crypto import (
    random_bytes,
    random_sys_bytes,
    Cryptography,
    SimpleCryptography,
    ChaCha20Cryptography,
    AES256CBCCryptography,
    aes256cbc_encrypt,
    aes256cbc_decrypt,
    padding_key,
    padding_size,
    pkcs7_padding,
    pkcs7_unpadding,
    generate_salt,
    generate_key_iv,
    calu_md5,
    calu_crc32_and_md5,
)
from baidupcs_py.common.log import LogLevels, get_logger

import requests
from requests import Response

_LOG_LEVEL = os.getenv("LOG_LEVEL", "CRITICAL").upper()
if _LOG_LEVEL not in LogLevels:
    _LOG_LEVEL = "CRITICAL"
logger = get_logger(__name__, level=_LOG_LEVEL)

READ_SIZE = 1 * constant.OneK
DEFAULT_MAX_CHUNK_SIZE = 10 * constant.OneM

BAIDUPCS_PY_CRYPTO_MAGIC_CODE = b"\x00@@#__BAIDUPCS_PY__CRYPTO__#@@\x00\xff"
ENCRYPT_HEAD_LEN = len(BAIDUPCS_PY_CRYPTO_MAGIC_CODE) + 1 + 16 + 8
PADDED_ENCRYPT_HEAD_LEN = padding_size(ENCRYPT_HEAD_LEN, 16)
PADDED_ENCRYPT_HEAD_WITH_SALT_LEN = PADDED_ENCRYPT_HEAD_LEN + 8


def total_len(o: Any) -> int:
    """Read obj len"""

    if hasattr(o, "__len__"):
        return len(o)

    if hasattr(o, "seekable"):
        if o.seekable():
            _offset = o.tell()
            _len = o.seek(0, 2)
            o.seek(_offset, 0)
            return _len

    if hasattr(o, "len"):
        return o.len

    if hasattr(o, "fileno"):
        try:
            fileno = o.fileno()
        except UnsupportedOperation:
            pass
        else:
            return os.fstat(fileno).st_size

    if hasattr(o, "getvalue"):
        # e.g. BytesIO, cStringIO.StringIO
        return len(o.getvalue())

    raise TypeError("Unsupported Operation: no method to get len")


class ChunkIO(IO):
    """Wrap a IO, only read `size` bytes"""

    def __init__(self, io: IO, size: int):
        self._io = io
        self._size = size
        self._offset = 0
        self._io_offset = io.tell()

    def __len__(self) -> int:
        return self._size

    def read(self, size: int = -1) -> Optional[bytes]:
        remain = self._size - self._offset
        if size == -1:
            size = remain
        else:
            size = min(size, remain)

        data = self._io.read(size) or b""
        if data:
            self._offset += len(data)
        return data

    def seek(self, offset: int, whence: int = 0) -> int:
        if not self.seekable():
            raise ValueError(f"{self._io.__class__.__name__} is not support seeking")

        if whence == 0:
            if offset < 0:
                raise ValueError(f"Negative seek position {offset}")
            pass
        elif whence == 1:
            offset += self._offset
        elif whence == 2:
            offset = self._size - offset

        offset = max(0, offset)
        offset = min(self._size, offset)
        self._io.seek(self._io_offset + offset)
        self._offset = offset
        return self._offset

    def tell(self) -> int:
        return self._offset

    def seekable(self) -> bool:
        return self._io.seekable()

    def writable(self):
        return False

    def close(self):
        pass


def sample_data(io: IO, rg: Random, size: int) -> bytes:
    """Sample data with size"""

    _len = io.seek(0, 2)
    data = b""
    for _ in range(size):
        i = rg.randint(0, max(0, _len - 1))
        io.seek(i, 0)
        data += io.read(1)
    io.seek(0, 0)
    return data


def rapid_upload_params(io: IO) -> Tuple[str, str, int, int]:
    io_len = 0
    chunk_size = constant.OneM
    crc32_v = 0
    md5_v = hashlib.md5()

    buf = io.read(256 * constant.OneK)
    io_len += len(buf)
    slice_md5 = calu_md5(buf)
    md5_v.update(buf)
    t = io.read(chunk_size - 256 * constant.OneK)
    io_len += len(t)
    md5_v.update(t)
    buf += t
    crc32_v = crc32(buf, crc32_v).conjugate()

    # content_crc32, content_md5 = calu_crc32_and_md5(io, constant.OneM)

    while True:
        buf = io.read(chunk_size)
        if buf:
            md5_v.update(buf)
            crc32_v = crc32(buf, crc32_v).conjugate()
            io_len += len(buf)
        else:
            break

    content_crc32, content_md5 = crc32_v.conjugate() & 0xFFFFFFFF, md5_v.hexdigest()

    # if isinstance(io, EncryptIO):
    #     io_len = len(io)
    # else:
    #     io_len = io.seek(0, 2)
    #     io.seek(0, 0)

    return slice_md5, content_md5, content_crc32, io_len


def rapid_upload_params2(localPath: Path) -> Tuple[str, str, int, int]:
    buf = localPath.open("rb").read(constant.OneM)
    slice_md5 = calu_md5(buf[: 256 * constant.OneK])
    content_crc32, content_md5 = calu_crc32_and_md5(localPath.open("rb"), constant.OneM)
    return slice_md5, content_md5, content_crc32, localPath.stat().st_size


def generate_nonce_or_iv(salt: bytes, io: IO) -> bytes:
    io_len = total_len(io)
    rg = Random(salt)
    sample = sample_data(io, rg, 16)
    return random_bytes(16, salt + sample + str(io_len).encode("utf-8"))


class EncryptIO(IO):
    """Encrypt IO

    All methods are implied for stream cipher.
    Block cipher needs to imply by itself.
    """

    def __init__(self, io: IO, encrypt_password: bytes, total_origin_len: int):
        self._io = io

        # The length of unencrypted content of `self._io`
        self._io_len = total_len(self._io)

        # The offset of encrypted content of `self._io`
        self._offset = 0

        # The total length of all original (decrypted) content
        #
        # Only define it at __init__
        self._total_origin_len = total_origin_len

        self._encrypt_password = encrypt_password

        self._salt_for_head = generate_salt()
        self._encrypt_key_for_head, self._iv_for_head = generate_key_iv(
            encrypt_password, self._salt_for_head, 32, 16
        )

        # `self._encrypt_key`,`self._nonce_or_iv` is for cryptography
        self._salt = generate_salt()
        self._encrypt_key, self._nonce_or_iv = generate_key_iv(
            encrypt_password, self._salt, 32, 16
        )

        # Cryptography
        #
        # Instantiated at each subclass, here is for mypy
        self._crypto: Optional[Cryptography] = None

        self._total_head = None
        self._total_head_len = len(self.total_head)

    def reset(self):
        """Reset io and crypto"""
        self._io.seek(0, 0)
        self._offset = 0
        self._crypto.reset()

    @property
    def total_head(self) -> bytes:
        """
        Version 1:
        aes256cbc_encrypt(`BAIDUPCS_PY_CRYPTO_MAGIC_CODE 32bytes`, encrypt_password, random_bytes(16, encrypt_password)) +
        `encrypt algorithm code 1bytes` +
        `nonce or iv 16bytes` +
        `total_origin_len 8bytes`

        Version 2:
        aes256cbc_encrypt(
            `BAIDUPCS_PY_CRYPTO_MAGIC_CODE 32bytes` +
            `encrypt algorithm code 1bytes` +
            `nonce_or_iv 16bytes`
            `total_origin_len 8bytes`
        ) +
        `salt 8bytes`

        Version 3:
        aes256cbc_encrypt(
            `BAIDUPCS_PY_CRYPTO_MAGIC_CODE 32bytes` +
            `encrypt algorithm code 1bytes` +
            `salt 8bytes` + `random padding 8bytes`
            `total_origin_len 8bytes`
        ) +
        `salt 8bytes`
        """

        if self._total_head:
            return self._total_head

        assert len(self._salt) == 8

        ori_head = padding_key(
            BAIDUPCS_PY_CRYPTO_MAGIC_CODE
            + self.MAGIC_CODE
            + self._salt
            + random_sys_bytes(8)
            + u64_to_u8x8(self._total_origin_len),
            PADDED_ENCRYPT_HEAD_LEN,
            value=b"",
        )

        # AES256CBC Encrypt head
        self._total_head = (
            aes256cbc_encrypt(ori_head, self._encrypt_key_for_head, self._iv_for_head)
            + self._salt_for_head
        )
        return self._total_head

    def __len__(self) -> int:
        return self._total_head_len + self._io_len

    def read(self, size: int = -1) -> Optional[bytes]:
        """The read only imply to stream cipher"""

        if self._offset < self._total_head_len:
            if size < 0:
                data = self.total_head[self._offset :]
                io_buf = self._io.read()
                data += self._crypto.encrypt(io_buf)
            else:
                data = self.total_head[self._offset : self._offset + size]
                size -= len(data)
                if size > 0:
                    io_buf = self._io.read(size)
                    data += self._crypto.encrypt(io_buf)
        else:
            io_buf = self._io.read(size)
            data = self._crypto.encrypt(io_buf)
        self._offset += len(data)
        return data

    def seek(self, offset: int, whence: int = 0) -> int:
        if (
            not self.seekable()
            and offset == 0
            and whence == 0
            and self._total_head_len > 0
        ):
            self._crypto.reset()
            self._io.seek(0, 0)
            self._offset = 0
            return self._offset

        if not self.seekable():
            raise ValueError(
                f"{self._crypto.__class__.__name__} is not support seeking"
            )

        if whence == 0:
            if offset < 0:
                raise ValueError(f"Negative seek position {offset}")
            pass
        elif whence == 1:
            offset += self._offset
        elif whence == 2:
            offset = len(self) - offset

        io_offset = offset - self._total_head_len
        if io_offset > 0:
            io_len = self._io.seek(0, 2)
            io_offset = self._io.seek(min(io_offset, io_len), 0)
            self._offset = self._total_head_len + io_offset
        else:
            self._io.seek(0, 0)
            self._offset = max(0, offset)
        return self._offset

    def tell(self) -> int:
        return self._offset

    def seekable(self) -> bool:
        """For stream cipher"""

        return True

    def writable(self) -> bool:
        return False

    def close(self):
        self._io.close()


class SimpleEncryptIO(EncryptIO):
    MAGIC_CODE = b"\x00"

    BLOCK_SIZE = 16  # 16 bytes

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._crypto = SimpleCryptography(self._encrypt_key + self._nonce_or_iv)


class ChaCha20EncryptIO(EncryptIO):
    MAGIC_CODE = b"\x01"

    BLOCK_SIZE = 16  # 16 bytes

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._crypto = ChaCha20Cryptography(self._encrypt_key, self._nonce_or_iv)

    def reset(self):
        super().reset()

    def seekable(self) -> bool:
        return False


class AES256CBCEncryptIO(EncryptIO):
    MAGIC_CODE = b"\x02"

    BLOCK_SIZE = 16  # 16 bytes

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._crypto = AES256CBCCryptography(self._encrypt_key, self._nonce_or_iv)

        # The offset of encrypted origin content
        self._origin_io_offset = 0
        # Origin content cache
        self._origin_cache = bytearray()

        # Total length of final encrypted content
        self._encrypted_io_len = padding_size(self._io_len, self.BLOCK_SIZE)
        # Encrypted content cache
        self._encrypted_cache = bytearray()

        self._need_data_padded = self._total_origin_len != self._encrypted_io_len

    def reset(self):
        super().reset()
        self._origin_io_offset = 0
        self._origin_cache = bytearray()
        self._encrypted_cache = bytearray()

    def __len__(self):
        """Encrypted content length"""

        return self._total_head_len + self._encrypted_io_len

    def _read_block(self, size: int = -1):
        """Read encrypted block to cache"""

        # `self._encrypted_cache` has remains.
        if size > 0 and len(self._encrypted_cache) > size:
            return

        # `size` must be large or equal to the `size` as `size` be the times of `self.BLOCK_SIZE`
        if size > 0:
            size = padding_size(size, self.BLOCK_SIZE)

        data = self._io.read(size) or b""
        if not data:
            return

        self._origin_io_offset += len(data)
        self._origin_cache.extend(data)

        avail_ori_len = padding_size(
            len(self._origin_cache), self.BLOCK_SIZE, ceil=False
        )
        if avail_ori_len > 0:
            ori_cn = self._origin_cache[:avail_ori_len]
            self._origin_cache = self._origin_cache[avail_ori_len:]
        else:
            ori_cn = b""

        # The end encryption
        if self._origin_io_offset == self._total_origin_len:

            # Take all remainder
            if self._origin_cache:
                ori_cn += bytes(self._origin_cache)
                self._origin_cache.clear()

            # Padding
            if self._need_data_padded:
                ori_cn = pkcs7_padding(ori_cn, self.BLOCK_SIZE)

            enc_cn = self._crypto.encrypt(ori_cn)
            self._crypto.finalize()
        else:
            enc_cn = self._crypto.encrypt(ori_cn)

        self._encrypted_cache.extend(enc_cn)

    def _takeout(self, size: int = -1) -> bytes:
        """Take out from encrypted cache"""

        self._read_block(size)

        if size < 0:
            data = bytes(self._encrypted_cache)
            self._encrypted_cache.clear()
        else:
            data = bytes(self._encrypted_cache[:size])
            self._encrypted_cache = self._encrypted_cache[size:]
        return data

    def read(self, size: int = -1) -> Optional[bytes]:
        if self._offset < self._total_head_len:
            if size < 0:
                data = self.total_head[self._offset :]
                data += self._takeout()
            else:
                data = self.total_head[self._offset : self._offset + size]
                size -= len(data)
                if size > 0:
                    data += self._takeout(size)
        else:
            data = self._takeout(size)
        self._offset += len(data)
        return data

    def seekable(self) -> bool:
        return False


class DecryptIO(IO):
    def __init__(
        self, io: IO, encrypt_key: bytes, nonce_or_iv: bytes, total_origin_len: int
    ):
        self._io = io

        # The offset after ENCRYPT_HEAD_LEN
        # Must be equal ENCRYPT_HEAD_LEN
        #
        # When `self.set_io` be called, the `_io_init_offset` must be set to `io.tell()`
        self._io_init_offset = io.tell()

        # The length of decrypted content of `self._io`
        #
        # When `self.set_io` be called, the `_io_len` must be set to new io's len
        self._io_len = total_len(self._io)

        # The offset of decrypted content of `self._io`
        #
        # When `self.set_io` be called, the `_offset` must be set to `io.tell()`
        self._offset = 0

        self._encrypt_key = encrypt_key
        self._nonce_or_iv = nonce_or_iv

        # The total length of all original (decrypted) content
        #
        # Only define it at __init__
        self._total_origin_len = total_origin_len

        self._total_head_len = ENCRYPT_HEAD_LEN

    def __len__(self) -> int:
        return self._io_len - self._io_init_offset

    def set_io(self, io: IO):
        self._io = io
        self._io_init_offset = io.tell()
        self._offset = 0
        self._io_len = total_len(self._io)

    def read(self, size: int = -1) -> Optional[bytes]:
        data = self._io.read(size)
        if not data:
            return b""
        self._offset += len(data)
        return data

    def seek(self, offset: int, whence: int = 0) -> int:
        # ChaCha20 and AES are depended on previous decrypted
        if not self.seekable():
            raise ValueError(f"{self.__class__.__name__} is not support seeking")

        if whence == 0:
            if offset < 0:
                raise ValueError(f"Negative seek position {offset}")
            pass
        elif whence == 1:
            offset += self._offset
        elif whence == 2:
            offset = len(self) - offset

        offset = max(0, offset)
        offset = min(len(self), offset)
        self._io.seek(offset + self._io_init_offset, 0)
        self._offset = offset
        return offset

    def tell(self) -> int:
        return self._offset

    def seekable(self) -> bool:
        return True

    def writable(self) -> bool:
        return False

    def close(self):
        self._io.close()


class SimpleDecryptIO(DecryptIO):
    def __init__(self, io: IO, encrypt_key: bytes, nonce: bytes, total_origin_len: int):
        super().__init__(io, encrypt_key, nonce, total_origin_len)

        self._crypto = SimpleCryptography(self._encrypt_key + self._nonce_or_iv)

    def read(self, size: int = -1) -> Optional[bytes]:
        data = self._io.read(size)
        if not data:
            return b""
        self._offset += len(data)
        return self._crypto.decrypt(data)

    def seekable(self) -> bool:
        return True


class ChaCha20DecryptIO(DecryptIO):
    BLOCK_SIZE = 16  # 16 bytes

    def __init__(self, io: IO, encrypt_key: bytes, nonce: bytes, total_origin_len: int):
        encrypt_key = padding_key(encrypt_key, self.BLOCK_SIZE * 2)
        nonce = padding_key(nonce, self.BLOCK_SIZE)
        super().__init__(io, encrypt_key, nonce, total_origin_len)

        self._crypto = ChaCha20Cryptography(self._encrypt_key, self._nonce_or_iv)

    def read(self, size: int = -1) -> Optional[bytes]:
        data = self._io.read(size)
        if not data:
            return b""
        self._offset += len(data)
        return self._crypto.decrypt(data)

    def seekable(self) -> bool:
        return False


class AES256CBCDecryptIO(DecryptIO):
    BLOCK_SIZE = 16  # 16 bytes

    def __init__(self, io: IO, encrypt_key: bytes, iv: bytes, total_origin_len: int):
        encrypt_key = padding_key(encrypt_key, self.BLOCK_SIZE * 2)
        iv = padding_key(iv, self.BLOCK_SIZE)
        super().__init__(io, encrypt_key, iv, total_origin_len)

        self._crypto = AES256CBCCryptography(self._encrypt_key, self._nonce_or_iv)

        self._encrypted_io_offset = 0
        self._encrypted_io_len = padding_size(total_origin_len, self.BLOCK_SIZE)
        self._encrypted_data_padded = total_origin_len != self._encrypted_io_len

        self._encrypted_cache = bytearray()
        self._decrypted_cache = bytearray()

    def __len__(self) -> int:
        """The decrypted content length of `self._io`"""

        avail_enc_len = padding_size(
            self._io_len - self._io_init_offset, self.BLOCK_SIZE, ceil=False
        )
        return avail_enc_len

    def _read_block(self, size: int = -1):
        """Read encrypted block to cache"""

        # `self._decrypted_cache` has remains.
        if size > 0 and len(self._decrypted_cache) > size:
            return

        # `size` must be large or equal to the `size` as `size` be the times of `self.BLOCK_SIZE`
        if size > 0:
            size = padding_size(size, self.BLOCK_SIZE)

        data = self._io.read(size)
        if not data:
            return

        self._encrypted_io_offset += len(data)
        self._encrypted_cache.extend(data)

        avail_enc_len = padding_size(
            len(self._encrypted_cache), self.BLOCK_SIZE, ceil=False
        )
        if avail_enc_len > 0:
            enc_cn = self._encrypted_cache[:avail_enc_len]
            self._encrypted_cache = self._encrypted_cache[avail_enc_len:]
        else:
            enc_cn = b""

        # The end decryption
        if self._encrypted_io_offset == self._encrypted_io_len:
            if self._encrypted_cache:
                enc_cn += bytes(self._encrypted_cache)
                self._encrypted_cache.clear()

            dec_cn = self._crypto.decrypt(enc_cn)

            if self._encrypted_data_padded:
                dec_cn = pkcs7_unpadding(dec_cn, self.BLOCK_SIZE)

            self._crypto.finalize()
        else:
            dec_cn = self._crypto.decrypt(enc_cn)

        self._decrypted_cache.extend(dec_cn)

    def read(self, size: int = -1) -> Optional[bytes]:
        self._read_block(size)

        if size < 0:
            data = bytes(self._decrypted_cache)
            self._decrypted_cache.clear()
        else:
            data = bytes(self._decrypted_cache[:size])
            self._decrypted_cache = self._decrypted_cache[size:]
        self._offset += len(data)
        return data

    def seekable(self) -> bool:
        return False


def parse_head(head: bytes) -> Tuple[bytes, bytes, bytes, bytes]:
    i = len(BAIDUPCS_PY_CRYPTO_MAGIC_CODE)
    return (
        head[:i],
        head[i : i + 1],  # magic_code
        head[i + 1 : i + 1 + 16],  # salt + random padding
        head[i + 1 + 16 : i + 1 + 16 + 8],  # total_origin_len
    )


def _decryptio_version1(
    total_head: bytes, io: IO, encrypt_password: bytes
) -> Optional[DecryptIO]:
    encrypt_password = padding_key(encrypt_password, 32)

    if len(total_head) < ENCRYPT_HEAD_LEN:
        return

    # Version 1
    b_mc, magic_code, nonce_or_iv, total_origin_len = parse_head(total_head)
    b_mc = aes256cbc_decrypt(b_mc, encrypt_password, random_bytes(16, encrypt_password))
    total_origin_len = u8x8_to_u64(total_origin_len)

    if b_mc != BAIDUPCS_PY_CRYPTO_MAGIC_CODE:
        return

    if magic_code == SimpleEncryptIO.MAGIC_CODE:
        return SimpleDecryptIO(io, encrypt_password, b"", total_origin_len)
    elif magic_code == ChaCha20EncryptIO.MAGIC_CODE:
        return ChaCha20DecryptIO(io, encrypt_password, nonce_or_iv, total_origin_len)
    elif magic_code == AES256CBCEncryptIO.MAGIC_CODE:
        return AES256CBCDecryptIO(io, encrypt_password, nonce_or_iv, total_origin_len)
    else:
        logging.warning(f"Unknown magic_code: {magic_code}")
        return


def _decryptio_version3(
    total_head: bytes, io: IO, encrypt_password: bytes
) -> Optional[DecryptIO]:
    if len(total_head) < PADDED_ENCRYPT_HEAD_WITH_SALT_LEN:
        return

    enc_head, salt_for_head = (
        total_head[:PADDED_ENCRYPT_HEAD_LEN],
        total_head[PADDED_ENCRYPT_HEAD_LEN:],
    )

    encrypt_key_for_head, iv_for_head = generate_key_iv(
        encrypt_password, salt_for_head, 32, 16
    )

    head = aes256cbc_decrypt(enc_head, encrypt_key_for_head, iv_for_head)

    b_mc, magic_code, padding_salt, total_origin_len = parse_head(head)
    total_origin_len = u8x8_to_u64(total_origin_len)

    salt = padding_salt[:8]
    encrypt_key, nonce_or_iv = generate_key_iv(encrypt_password, salt, 32, 16)

    if b_mc != BAIDUPCS_PY_CRYPTO_MAGIC_CODE:
        return

    eio = None
    if magic_code == SimpleEncryptIO.MAGIC_CODE:
        eio = SimpleDecryptIO(io, encrypt_key, nonce_or_iv, total_origin_len)
    elif magic_code == ChaCha20EncryptIO.MAGIC_CODE:
        eio = ChaCha20DecryptIO(io, encrypt_key, nonce_or_iv, total_origin_len)
    elif magic_code == AES256CBCEncryptIO.MAGIC_CODE:
        eio = AES256CBCDecryptIO(io, encrypt_key, nonce_or_iv, total_origin_len)
    else:
        logging.warning(f"Unknown magic_code: {magic_code}")
        return

    eio._total_head_len = PADDED_ENCRYPT_HEAD_WITH_SALT_LEN
    return eio


def to_decryptio(io: IO, encrypt_password: bytes):
    if not encrypt_password:
        return io

    total_head = io.read(ENCRYPT_HEAD_LEN)
    eio = _decryptio_version1(total_head, io, encrypt_password)
    if eio is not None:
        return eio

    # No support Version 2

    total_head += io.read(PADDED_ENCRYPT_HEAD_WITH_SALT_LEN - ENCRYPT_HEAD_LEN)
    eio = _decryptio_version3(total_head, io, encrypt_password)
    if eio is not None:
        return eio

    io.seek(0, 0)
    return io


class AutoDecryptRequest:
    def __init__(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE,
        encrypt_password: bytes = b"",
        **kwargs,
    ):
        kwargs["stream"] = True

        self._method = method
        self._url = url
        self._headers = headers
        self._session = requests.session()
        self._kwargs = kwargs
        self._max_chunk_size = max_chunk_size
        self._encrypt_password = encrypt_password
        self._dio = None
        self._has_encrypted = False
        self._total_head_len = 0
        self._decrypted_count = 0
        self._parsed = False

        # Rapid Upload Infos
        #
        # Total raw content length
        self._content_length: Optional[int] = None
        # Total raw content md5
        self._content_md5: Optional[str] = None
        # Total raw content crc32
        self._content_crc32: Optional[int] = None

    def _init(self):
        """Initiate request info"""

        if not self._parsed:
            self._parse_crypto()

        if self._content_length is None:
            # To invoke `self._parse_rapid_upload_info`
            with self._request((0, 1)):
                pass

    @property
    def content_length(self) -> int:
        """Remote content length"""

        self._init()
        assert self._content_length
        return self._content_length

    @property
    def content_md5(self) -> Optional[str]:
        """Remote content length"""

        self._init()
        assert self._content_length
        return self._content_md5

    @property
    def content_crc32(self) -> Optional[int]:
        """Remote content length"""

        self._init()
        assert self._content_length
        return self._content_crc32

    def _parse_rapid_upload_info(self, resp: Response):
        if not resp.ok or self._content_length:
            return

        headers = resp.headers
        if headers.get("x-bs-file-size"):
            self._content_length = int(headers["x-bs-file-size"])
        if not self._content_length and headers.get("Content-Range"):
            self._content_length = int(headers["Content-Range"].split("/")[-1])

        if headers.get("Content-MD5"):
            self._content_md5 = headers["Content-MD5"]

        if headers.get("x-bs-meta-crc32"):
            self._content_crc32 = int(headers["x-bs-meta-crc32"])

    def _parse_crypto(self):
        if self._encrypt_password:
            with self._request((0, PADDED_ENCRYPT_HEAD_WITH_SALT_LEN - 1)) as resp:
                raw_data = resp.raw.read()
                if len(raw_data) == PADDED_ENCRYPT_HEAD_WITH_SALT_LEN:
                    self._dio = to_decryptio(BytesIO(raw_data), self._encrypt_password)
                    self._has_encrypted = isinstance(self._dio, DecryptIO)
                    self._total_head_len = (
                        self._dio._total_head_len if self._has_encrypted else 0
                    )
        self._parsed = True

    def _request(self, _range: Tuple[int, int]) -> Response:
        headers = dict(self._headers or {})
        headers["Range"] = "bytes={}-{}".format(*_range)

        while True:
            try:
                resp = self._session.request(
                    self._method, self._url, headers=headers, **self._kwargs
                )
                if not resp.ok:
                    logger.warning(
                        "`%s._request` request error: status_code: %s, body: %s",
                        self.__class__.__name__,
                        resp.status_code,
                        resp.content[:1000],
                    )

                    # Error: 31626: user is not authorized, hitcode:122
                    # Error: 31326: user is not authorized, hitcode:117
                    # Request is temporally blocked.
                    # This error occurs when url is from `BaiduPCS.download_link(..., pcs=True)`
                    if b"user is not authorized" in resp.content:
                        time.sleep(2)
                        continue
                self._parse_rapid_upload_info(resp)
                break
            except Exception as err:
                logger.warning(
                    "`%s._request` request error: %s",
                    self.__class__.__name__,
                    err,
                )
                raise IOError(f"{self.__class__.__name__} - Request Error") from err

        if not resp.ok:
            raise IOError(
                f"{self.__class__.__name__} - Response is not ok: "
                f"status_code: {resp.status_code}, body: {resp.content[:1000]}"
            )

        return resp

    def rangeable(self) -> bool:
        """Is support uncontinue range request?"""

        self._init()

        if self._dio is None:
            return True
        return self._dio.seekable()

    def __len__(self) -> int:
        """The decrypted data length"""

        self._init()

        return self._content_length - self._total_head_len

    def read(self, _range: Tuple[int, int]) -> Generator[bytes, None, None]:
        self._init()

        start, end = _range
        if end < 0:
            end = len(self)
        end = min(end, len(self))

        if end - start == 0:
            return None

        if start != self._decrypted_count and not self.rangeable():
            raise IndexError(
                "ChaCha20 must decoded data with continue data."
                f"start: {start}, decrypted count: {self._decrypted_count}"
            )

        ranges = self._split_chunk(
            start + self._total_head_len, end + self._total_head_len
        )
        for _rg in ranges:
            with self._request(_rg) as resp:
                stream = resp.raw
                while True:
                    buf = stream.read(READ_SIZE)
                    if not buf:
                        break
                    self._decrypted_count += len(buf)
                    bio = BytesIO(buf)
                    if self._dio is not None and isinstance(self._dio, DecryptIO):
                        self._dio.set_io(bio)
                        yield self._dio.read() or b""
                    else:
                        yield buf

    def _split_chunk(self, start: int, end: int) -> List[Tuple[int, int]]:
        """Split the chunks for range header

        Echo chunk has the length at most `self._max_chunk_size`.
        """

        left = list(range(start, end, self._max_chunk_size))
        left.append(end)
        right = [i - 1 for i in left]
        return [(s, e) for s, e in zip(left[:-1], right[1:])]


class RangeRequestIO(IO):
    def __init__(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE,
        callback: Callable[..., None] = None,
        encrypt_password: bytes = b"",
        **kwargs,
    ):
        kwargs["stream"] = True

        self._method = method
        self._url = url
        self._headers = headers
        self._kwargs = kwargs
        self._max_chunk_size = max_chunk_size
        self._callback = callback
        self._encrypt_password = encrypt_password

        self.reset()

    def reset(self):
        self._offset = 0
        self._auto_decrypt_request = AutoDecryptRequest(
            self._method,
            self._url,
            headers=self._headers,
            max_chunk_size=self._max_chunk_size,
            encrypt_password=self._encrypt_password,
            **self._kwargs,
        )

    def __len__(self) -> int:
        return len(self._auto_decrypt_request)

    def read(self, size: int = -1) -> Optional[bytes]:
        if size == 0:
            return b""

        if size == -1:
            size = len(self) - self._offset

        start, end = self._offset, self._offset + size

        buf = b""
        for b in self._auto_decrypt_request.read((start, end)):
            buf += b
            self._offset += len(b)
            # Call callback
            if self._callback:
                self._callback(self._offset)
        return buf

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._offset = offset
        elif whence == 1:
            self._offset += offset
        elif whence == 2:
            self._offset = len(self) - offset

        self._offset = max(0, self._offset)
        self._offset = min(len(self), self._offset)
        return self._offset

    def tell(self) -> int:
        return self._offset

    def seekable(self) -> bool:
        return self._auto_decrypt_request.rangeable()

    def writable(self) -> bool:
        return False

    def close(self):
        pass


class EncryptType(Enum):
    No = "No"
    Simple = "Simple"
    ChaCha20 = "ChaCha20"
    AES256CBC = "AES256CBC"

    def encrypt_io(self, io: IO, encrypt_password: bytes):
        io_len = total_len(io)
        if self == EncryptType.No:
            return io
        elif self == EncryptType.Simple:
            return SimpleEncryptIO(io, encrypt_password, io_len)
        elif self == EncryptType.ChaCha20:
            return ChaCha20EncryptIO(io, encrypt_password, io_len)
        elif self == EncryptType.AES256CBC:
            return AES256CBCEncryptIO(io, encrypt_password, io_len)
        else:
            raise ValueError(f"Unknown EncryptType: {self}")


def reset_encrypt_io(io: Union[IO, EncryptIO]):
    if isinstance(io, EncryptIO):
        io.reset()
    else:
        io.seek(0, 0)
