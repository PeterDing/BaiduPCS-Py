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
