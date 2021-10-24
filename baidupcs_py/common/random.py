import random
import os
import struct
from functools import partial

MAX_U64 = 1 << 64

shuffle = partial(
    random.shuffle, random=lambda: struct.unpack("Q", os.urandom(8))[0] / MAX_U64
)
