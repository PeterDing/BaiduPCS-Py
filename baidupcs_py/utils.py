import json
import time
import string
import math


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


_nums_set = set(string.digits + ".")


def human_size_to_int(size_str: str) -> int:
    size_str = size_str.strip()
    if not size_str:
        return 0

    i = 0
    while i < len(size_str):
        if size_str[i] in _nums_set:
            i += 1
            continue
        else:
            break

    if i == 0:
        return 0

    s = float(size_str[:i])
    _s = s

    unit = size_str[i:].upper().replace(" ", "")
    if not unit:
        return math.floor(_s)

    for t in ["KB", "MB", "GB", "TB"]:
        _s *= 1024
        if unit == t or unit[0] == t[0]:
            return math.floor(_s)

    return math.floor(s)
