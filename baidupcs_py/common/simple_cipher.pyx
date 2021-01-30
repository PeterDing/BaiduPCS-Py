import random
import copy

cdef crypt(unsigned char *data, unsigned char *byte_map, int len_):
    cdef unsigned int c

    for i in range(len_):
        c = data[i]
        data[i] = byte_map[c]


class SimpleCryptography:
    """Simple Cryptography

    This crypto algorithm uses a random uint8 map to transfer an uint8 to another uint8.
    So, the decryption process does not depend on previous decrypted data.

    The algorithm is vulnerable, so NO using to encrypt important data.
    """

    def __init__(self, key):
        rg = random.Random()
        rg.seed(key, version=2)

        _byte_map = list(range(1 << 8))
        rg.shuffle(_byte_map)

        # encrypt_byte_map[ori_char] -> encrypted_char
        self._encrypt_byte_map = bytes(bytearray(_byte_map))

        # decrypt_byte_map[encrypted_char] -> ori_char
        self._decrypt_byte_map = bytes(
            bytearray([c for _, c in sorted(zip(_byte_map, range(1 << 8)))])
        )

        self._key = key

    def encrypt(self, data):
        data = bytes(bytearray(data))  # copy
        crypt(data, self._encrypt_byte_map, len(data))
        return data

    def decrypt(self, data):
        data = bytes(bytearray(data))  # copy
        crypt(data, self._decrypt_byte_map, len(data))
        return data

    def reset(self):
        pass

