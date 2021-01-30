import struct


def u64_to_u8x8(u64: int) -> bytes:
    return struct.pack("!Q", u64)


def u8x8_to_u64(u8x8: bytes) -> int:
    return struct.unpack("!Q", u8x8)[0]
