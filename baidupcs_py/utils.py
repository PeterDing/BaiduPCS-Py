import json
import time


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
