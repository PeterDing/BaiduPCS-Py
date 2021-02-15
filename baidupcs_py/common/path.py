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
    """Join posix paths

    Only resolve relative path.
    """

    has_root = Path(source).as_posix().startswith("/")

    if not isinstance(source, Path):
        source = Path(source)
    if not isinstance(dest, Path):
        dest = Path(dest)

    path = (source / dest).resolve().as_posix()

    if not has_root:
        parents = Path("").resolve().as_posix()
        path = path[len(parents) + 1 :]

    if IS_WIN and has_root:
        return path.split(":", 1)[-1]
    else:
        return path
