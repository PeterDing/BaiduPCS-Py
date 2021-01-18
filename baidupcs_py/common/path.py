from typing import Iterator
from pathlib import Path
import os
from os import PathLike


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
    if not isinstance(source, Path):
        source = Path(source)
    if not isinstance(dest, Path):
        dest = Path(dest)
    return (source / dest).resolve().as_posix()
