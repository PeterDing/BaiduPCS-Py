from typing import Optional, List, Tuple, Dict, Any, Callable, Generator, IO
from abc import ABC, abstractmethod
from io import BytesIO, UnsupportedOperation
from pathlib import Path
from zlib import crc32
from random import Random
import os
import hashlib
import logging

from baidupcs_py.common import constant
from baidupcs_py.common.number import u64_to_u8x8, u8x8_to_u64
from baidupcs_py.common.crypto import (
    random_bytes,
    Cryptography,
    SimpleCryptography,
    ChaCha20Cryptography,
    AES256CBCCryptography,
    aes265cbc_encrypt,
    aes265cbc_decrypt,
    padding_key,
    padding_size,
    pkcs7_padding,
    pkcs7_unpadding,
    calu_md5,
    calu_crc32_and_md5,
)

import requests
from requests import Response

READ_SIZE = 1 * constant.OneK
DEFAULT_MAX_CHUNK_SIZE = 10 * constant.OneM

BAIDUPCS_PY_CRYPTO_MAGIC_CODE = b"\x00@@#__BAIDUPCS_PY__CRYPTO__#@@\x00\xff"
ENCRYPT_HEAD_LEN = len(BAIDUPCS_PY_CRYPTO_MAGIC_CODE) + 1 + 16 + 8


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


class EncryptIO(IO):
    """Encrypt IO

    All methods are implied for stream cipher.
    Block cipher needs to imply by itself.
    """

    def __init__(
        self, io: IO, encrypt_key: Any, nonce_or_iv: Any, total_origin_len: int
    ):
        self._io = io

        # The length of unencrypted content of `self._io`
        self._io_len = total_len(self._io)

        # The offset of encrypted content of `self._io`
        self._offset = 0

        # The total length of all original (decrypted) content
        #
        # Only define it at __init__
        self._total_origin_len = total_origin_len

        self._encrypt_key = encrypt_key
        self._nonce_or_iv = nonce_or_iv

        # Cryptography
        #
        # Instantiated at each subclass, here is for mypy
        self._crypto: Optional[Cryptography] = None

        # AES256CBC Encrypt `BAIDUPCS_PY_CRYPTO_MAGIC_CODE`
        self._encrypted_baidupcs_py_crypto_magic_code = aes265cbc_encrypt(
            BAIDUPCS_PY_CRYPTO_MAGIC_CODE,
            self._encrypt_key,
            random_bytes(16, self._encrypt_key),
        )

        self._total_head_len = len(self.total_head())

    def total_head(self) -> bytes:
        """
        `BAIDUPCS_PY_CRYPTO_MAGIC_CODE 32bytes` +
        `encrypt algorithm code 1bytes` +
        `nonce or iv 16bytes` +
        `total_origin_len 64bit`
        """

        return (
            self._encrypted_baidupcs_py_crypto_magic_code
            + self.MAGIC_CODE
            + self._nonce_or_iv
            + u64_to_u8x8(self._total_origin_len)
        )

    def __len__(self) -> int:
        return self._total_head_len + self._io_len

    def read(self, size: int = -1) -> Optional[bytes]:
        """The read only imply to stream cipher"""

        if self._offset < self._total_head_len:
            if size < 0:
                data = self.total_head()[self._offset :]
                io_buf = self._io.read()
                data += self._crypto.encrypt(io_buf)
            else:
                data = self.total_head()[self._offset : self._offset + size]
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

    def __init__(
        self, io: IO, encrypt_key: Any, nonce_or_iv: Any, total_origin_len: int
    ):
        encrypt_key = padding_key(encrypt_key, self.BLOCK_SIZE * 2)
        nonce_or_iv = padding_key(nonce_or_iv, self.BLOCK_SIZE)
        super().__init__(io, encrypt_key, nonce_or_iv, total_origin_len)

        self._crypto = SimpleCryptography(self._encrypt_key)


class ChaCha20EncryptIO(EncryptIO):
    MAGIC_CODE = b"\x01"

    BLOCK_SIZE = 16  # 16 bytes

    def __init__(self, io: IO, encrypt_key: Any, nonce: Any, total_origin_len: int):
        encrypt_key = padding_key(encrypt_key, self.BLOCK_SIZE * 2)
        nonce = padding_key(nonce, self.BLOCK_SIZE)
        super().__init__(io, encrypt_key, nonce, total_origin_len)

        self._crypto = ChaCha20Cryptography(self._encrypt_key, self._nonce_or_iv)

    def seekable(self) -> bool:
        return False


class AES256CBCEncryptIO(EncryptIO):
    MAGIC_CODE = b"\x02"

    BLOCK_SIZE = 16  # 16 bytes

    def __init__(self, io: IO, encrypt_key: Any, iv: Any, total_origin_len: int):
        encrypt_key = padding_key(encrypt_key, self.BLOCK_SIZE * 2)
        iv = padding_key(iv, self.BLOCK_SIZE)
        super().__init__(io, encrypt_key, iv, total_origin_len)

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

    def __len__(self):
        """Encrypted content length"""

        return self._total_head_len + self._encrypted_io_len

    def _read_block(self, size: int = -1):
        """Read encrypted block to cache"""

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
                data = self.total_head()[self._offset :]
                data += self._takeout()
            else:
                data = self.total_head()[self._offset : self._offset + size]
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
        self, io: IO, encrypt_key: Any, nonce_or_iv: Any, total_origin_len: int
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
        # ChaCha20 and aes are depended on previous decrypted
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


def parse_head(head: bytes) -> Tuple[bytes, bytes, bytes, bytes]:
    i = len(BAIDUPCS_PY_CRYPTO_MAGIC_CODE)
    return (
        head[:i],
        head[i : i + 1],  # magic_code
        head[i + 1 : i + 1 + 16],  # nonce or iv or random
        head[i + 1 + 16 : i + 1 + 16 + 8],  # total_origin_len
    )


class SimpleDecryptIO(DecryptIO):
    def __init__(self, io: IO, encrypt_key: Any, total_origin_len: int):
        encrypt_key = padding_key(encrypt_key, 32)
        super().__init__(io, encrypt_key, None, total_origin_len)

        self._crypto = SimpleCryptography(self._encrypt_key)

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

    def __init__(self, io: IO, encrypt_key: Any, nonce: Any, total_origin_len: int):
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

    def __init__(self, io: IO, encrypt_key: Any, iv: Any, total_origin_len: int):
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


def to_decryptio(io: IO, encrypt_key: Any):
    if not encrypt_key:
        return io

    encrypt_key = padding_key(encrypt_key, 32)

    head = io.read(ENCRYPT_HEAD_LEN)
    if len(head) != ENCRYPT_HEAD_LEN:
        io.seek(0, 0)
        return io

    b_mc, magic_code, nonce_or_iv, total_origin_len = parse_head(head)
    b_mc = aes265cbc_decrypt(b_mc, encrypt_key, random_bytes(16, encrypt_key))
    total_origin_len = u8x8_to_u64(total_origin_len)

    if b_mc != BAIDUPCS_PY_CRYPTO_MAGIC_CODE:
        io.seek(0, 0)
        return io

    if magic_code == SimpleEncryptIO.MAGIC_CODE:
        return SimpleDecryptIO(io, encrypt_key, total_origin_len)
    elif magic_code == ChaCha20EncryptIO.MAGIC_CODE:
        return ChaCha20DecryptIO(io, encrypt_key, nonce_or_iv, total_origin_len)
    elif magic_code == AES256CBCEncryptIO.MAGIC_CODE:
        return AES256CBCDecryptIO(io, encrypt_key, nonce_or_iv, total_origin_len)
    else:
        logging.warning(f"Unknown magic_code: {magic_code}")
        io.seek(0, 0)
        return io


class AutoDecryptRequest:
    def __init__(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE,
        encrypt_key: Any = None,
        **kwargs,
    ):
        kwargs["stream"] = True

        self._method = method
        self._url = url
        self._headers = headers
        self._session = requests.session()
        self._kwargs = kwargs
        self._max_chunk_size = max_chunk_size
        self._encrypt_key = encrypt_key
        self._remote_len = None
        self._dio = None
        self._has_encrypted = False
        self._total_head_len = 0
        self._decrypted_count = 0

        if self._encrypt_key:
            self.parse_crypto()

    def parse_crypto(self):
        if self.remote_len >= ENCRYPT_HEAD_LEN:
            with self._request((0, ENCRYPT_HEAD_LEN - 1)) as resp:
                self._dio = to_decryptio(BytesIO(resp.raw.read()), self._encrypt_key)
                self._has_encrypted = isinstance(self._dio, DecryptIO)
                self._total_head_len = (
                    self._dio._total_head_len if self._has_encrypted else 0
                )

    def _request(self, _range: Tuple[int, int]) -> Response:
        headers = dict(self._headers or {})
        headers["Range"] = "bytes={}-{}".format(*_range)
        try:
            resp = self._session.request(
                self._method, self._url, headers=headers, **self._kwargs
            )
            return resp
        except Exception as err:
            raise IOError(f"{self.__class__.__name__} - Request Error") from err

    def rangeable(self) -> bool:
        """Is support uncontinue range request?"""

        if self._dio is None:
            return True
        return self._dio.seekable()

    @property
    def remote_len(self) -> int:
        """Remote content length"""

        if self._remote_len is not None:
            return self._remote_len

        with self._request((0, 1)) as resp:
            resp_headers = resp.headers
            if not resp_headers.get("Content-Range"):
                raise IOError(
                    f"{self.__class__.__name__} - "
                    "Server does not support `Range` head."
                    f" Response content: {resp.raw.read(1000)}"
                )

        try:
            _, length = resp_headers["Content-Range"].split("/")
            _remote_len = int(length)
            self._remote_len = _remote_len
            return _remote_len
        except Exception as err:
            raise IOError(
                f"{self.__class__.__name__} - "
                "Can't parse response head `Content-Range`"
            ) from err

    def __len__(self) -> int:
        """The decrypted data length"""

        return self.remote_len - self._total_head_len

    def read(self, _range: Tuple[int, int]) -> Generator[bytes, None, None]:
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
        encrypt_key: Any = None,
        **kwargs,
    ):
        kwargs["stream"] = True

        self._method = method
        self._url = url
        self._headers = headers
        self._kwargs = kwargs
        self._max_chunk_size = max_chunk_size
        self._callback = callback
        self._encrypt_key = encrypt_key

        self.reset()

    def reset(self):
        self._offset = 0
        self._auto_decrypt_request = AutoDecryptRequest(
            self._method,
            self._url,
            headers=self._headers,
            max_chunk_size=self._max_chunk_size,
            encrypt_key=self._encrypt_key,
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
