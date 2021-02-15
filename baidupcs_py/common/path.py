from typing import Iterator
from pathlib import Path
import os
from os import PathLike

from baidupcs_py.common.platform import IS_WIN


def exists(localpath: PathLike) -> bool:
    localpath = Path(localpath)
    return localpath.exists()


def is_file(localpath: PathLike) -> bool:
    localpath = Path(localpath)
    return localpath.is_file()


def is_dir(localpath: PathLike) -> bool:
    localpath = Path(localpath)
    return localpath.is_dir()


def walk(localpath: PathLike) -> Iterator[str]:
    for root, _, files in os.walk(localpath):
        r = Path(root)
        for fl in files:
            yield (r / fl).as_posix()


def join_path(source: PathLike, dest: PathLike) -> str:
    """Join posix paths"""

    _path = (Path(source) / dest).as_posix()
    has_root = _path.startswith("/")
    if not has_root:
        _path = "/" + _path

    path = Path(_path).resolve().as_posix()

    if IS_WIN:
        p = path.split(":", 1)[-1]
        if not has_root:
            return p[1:]
        else:
            return p
    else:
        if not has_root:
            return path[1:]
        else:
            return path
