from typing import TypeVar, Optional, List, Union, Pattern
from abc import ABC
import re

from baidupcs_py.baidupcs import PcsFile


class Sifter(ABC):
    def pattern(self) -> Union[Pattern, str, None]:
        """
        The regex pattern used to the sifter

        If it returns '', then the sifter will match all inputs
        """
        return None

    def include(self) -> bool:
        """Include the sifted result or exclude"""
        return True

    def sift(self, obj: Union[PcsFile, str]) -> bool:
        """
        True: to include
        False: to exclude
        """

        include = self.include()
        pat = self.pattern()

        if not pat:
            return include

        if isinstance(obj, PcsFile):
            buf = obj.path
        else:
            buf = obj

        if isinstance(pat, Pattern):
            if pat.search(buf):
                return include
            else:
                return not include
        else:  # str
            if pat in buf:
                return include
            else:
                return not include

    def __call__(self, obj: Union[PcsFile, str]) -> bool:
        return self.sift(obj)


class IncludeSifter(Sifter):
    def __init__(self, needle: Optional[str], regex: bool = False):
        _pattern: Union[Pattern, str, None] = None
        self._pattern = _pattern
        if needle:
            if regex:
                self._pattern = re.compile(needle)
            else:
                self._pattern = needle

    def pattern(self):
        return self._pattern


class ExcludeSifter(IncludeSifter):
    def __init__(self, needle: Optional[str], regex: bool = False):
        super().__init__(needle, regex=regex)

    def include(self):
        return False


class IsFileSifter(Sifter):
    def sift(self, obj: Union[PcsFile, str]) -> bool:
        assert isinstance(obj, PcsFile)
        return obj.is_file or not obj.is_dir


class IsDirSifter(Sifter):
    def sift(self, obj: Union[PcsFile, str]) -> bool:
        assert isinstance(obj, PcsFile)
        return obj.is_dir or not obj.is_file


T = TypeVar("T", PcsFile, str)


def sift(objs: List[T], sifters: List[Sifter]) -> List[T]:
    if sifters:
        objs = [obj for obj in objs if all([sifter(obj) for sifter in sifters])]
    return objs
