from typing import Union, Tuple, IO
import json
import time
from zlib import crc32

from hashlib import md5, sha1


def calu_md5(buf: Union[str, bytes], encoding="utf-8") -> str:
    assert isinstance(buf, (str, bytes))

    if isinstance(buf, str):
        buf = buf.encode(encoding)
    return md5(buf).hexdigest()


def calu_crc32_and_md5(stream: IO[bytes], chunk_size: int) -> Tuple[int, str]:
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


def dump_json(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def format_date(timestramp: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestramp))


def human_size(size: int) -> str:
    s = float(size)
    v = ""
    t = ""
    for t in ["B", "KB", "MB", "GB", "TB"]:
        if s < 1024.0:
            v = f"{s:3.1f}"
            break
        s /= 1024.0
    if v.endswith(".0"):
        v = v[:-2]
    return f"{v} {t}"
