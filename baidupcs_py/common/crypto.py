from typing import Union, List, Tuple, IO, Any
import re
import sys
import subprocess
import random
from abc import ABC, abstractmethod
from zlib import crc32
from hashlib import md5, sha1

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.padding import PKCS7
from cryptography.hazmat.backends import default_backend

from baidupcs_py.common.simple_cipher import SimpleCryptography as _SimpleCryptography


def _md5_cmd(localpath: str) -> List[str]:
    if sys.platform == "darwin":
        cmd = ["md5", localpath]
    elif sys.platform == "linux":
        cmd = ["md5sum", localpath]
    else:  # windows
        cmd = ["CertUtil", "-hashfile", localpath, "MD5"]
    return cmd


def calu_file_md5(localpath: str) -> str:
    cp = subprocess.run(
        _md5_cmd(localpath), universal_newlines=True, stdout=subprocess.PIPE
    )

    output = cp.stdout.strip()
    if sys.platform == "darwin":
        return re.split(r"\s+", output)[-1]
    elif sys.platform == "linux":
        return re.split(r"\s+", output)[0]
    else:  # windows
        return re.split(r"\s+", output)[-6]


def calu_md5(buf: Union[str, bytes], encoding="utf-8") -> str:
    assert isinstance(buf, (str, bytes))

    if isinstance(buf, str):
        buf = buf.encode(encoding)
    return md5(buf).hexdigest()


def calu_crc32_and_md5(stream: IO, chunk_size: int) -> Tuple[int, str]:
    md5_v = md5()
    crc32_v = 0
    while True:
        buf = stream.read(chunk_size)
        if buf:
            md5_v.update(buf)
            crc32_v = crc32(buf, crc32_v).conjugate()
        else:
            break
    return crc32_v.conjugate() & 0xFFFFFFFF, md5_v.hexdigest()


def calu_sha1(buf: Union[str, bytes], encoding="utf-8") -> str:
    assert isinstance(buf, (str, bytes))

    if isinstance(buf, str):
        buf = buf.encode(encoding)
    return sha1(buf).hexdigest()


U8_LIST = list(range(1 << 8))


def random_bytes(size: int, seed: Any = None) -> bytes:
    """Generate random bytes"""

    rg = random.Random(seed)
    return bytes(rg.sample(U8_LIST, size))


def padding_key(key: Union[str, bytes], len_: int = 0) -> bytes:
    if isinstance(key, str):
        key = key.encode("utf-8")

    assert len(key) <= len_
    return key + b"\xff" * (len_ - len(key))


def padding_size(length: int, block_size: int, ceil: bool = True) -> int:
    """Return minimum the multiple which is large or equal than the `length`

    Args:
        block_size (int): the length of bytes, no the length of bit
    """

    remainder = length % block_size
    if ceil:
        return (block_size - remainder) * int(remainder != 0) + length
    else:
        return length - remainder


def pkcs7_padding(data: bytes, block_size):
    """
    Args:
        block_size (int): the length of bytes, no the length of bit
    """

    padder = PKCS7(block_size * 8).padder()
    return padder.update(data) + padder.finalize()


def pkcs7_unpadding(data: bytes, block_size):
    """
    Args:
        block_size (int): the length of bytes, no the length of bit
    """

    unpadder = PKCS7(block_size * 8).unpadder()
    return unpadder.update(data) + unpadder.finalize()


class Cryptography(ABC):
    @abstractmethod
    def encrypt(self, data: bytes) -> bytes:
        pass

    @abstractmethod
    def decrypt(self, data: bytes) -> bytes:
        pass

    @abstractmethod
    def reset(self):
        pass

    @abstractmethod
    def finalize(self):
        """Finalize encryptor and decryptor, no return data"""


class SimpleCryptography(Cryptography):
    """Simple Cryptography

    This crypto algorithm uses a random uint8 map to transfer an uint8 to another uint8.
    So, the decryption process does not depend on previous decrypted data.

    The algorithm is vulnerable, so NO using to encrypt important data.
    """

    def __init__(self, key):
        self._c = _SimpleCryptography(key)
        self._key = key

    def encrypt(self, data: bytes) -> bytes:
        return self._c.encrypt(data)

    def decrypt(self, data: bytes) -> bytes:
        return self._c.decrypt(data)

    def reset(self):
        pass

    def finalize(self):
        pass


class ChaCha20Cryptography(Cryptography):
    """ChaCha20 Cryptography

    ChaCha20 stream algorithm.

    The decryption process does depend on previous decrypted data.
    """

    def __init__(self, key: bytes, nonce: bytes):
        assert len(key) == 32
        assert len(nonce) == 16

        self._key = key
        self._nonce = nonce
        self.reset()

    def encrypt(self, data: bytes) -> bytes:
        return self._encryptor.update(data)

    def decrypt(self, data: bytes) -> bytes:
        return self._decryptor.update(data)

    def reset(self):
        cipher = Cipher(
            algorithms.ChaCha20(self._key, self._nonce),
            mode=None,
            backend=default_backend(),
        )
        self._encryptor = cipher.encryptor()
        self._decryptor = cipher.decryptor()

    def finalize(self):
        self._encryptor.finalize()
        self._decryptor.finalize()


class AES256CBCCryptography(Cryptography):
    def __init__(self, key: bytes, iv: bytes):
        assert len(key) == 32
        assert len(iv) == 16

        self._key = key
        self._iv = iv
        self._mode = modes.CBC(iv)
        self.reset()

    def encrypt(self, data: bytes) -> bytes:
        assert len(data) % 16 == 0
        return self._encryptor.update(data)

    def decrypt(self, data: bytes) -> bytes:
        return self._decryptor.update(data)

    def reset(self):
        cipher = Cipher(algorithms.AES(self._key), mode=self._mode)
        self._encryptor = cipher.encryptor()
        self._decryptor = cipher.decryptor()

    def finalize(self):
        self._encryptor.finalize()
        self._decryptor.finalize()


def aes265cbc_encrypt(data: bytes, key: bytes, iv: bytes):
    crypto = AES256CBCCryptography(key, iv)
    return crypto.encrypt(data) + crypto._encryptor.finalize()


def aes265cbc_decrypt(data: bytes, key: bytes, iv: bytes):
    crypto = AES256CBCCryptography(key, iv)
    return crypto.decrypt(data) + crypto._decryptor.finalize()
