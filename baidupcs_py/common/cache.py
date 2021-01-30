from typing import Dict, Any
from collections import UserDict
from functools import wraps, _make_key
import time


class TimeoutCache(UserDict):
    def __init__(self, timeout: int):
        super().__init__()
        self._timeout = timeout
        self._last_used: Dict[Any, float] = {}

    def __getitem__(self, key):
        val = super().__getitem__(key)

        now = time.time()
        if now - self._last_used[key] > self._timeout:
            self.clear_timeout()
            raise KeyError(key)

        return val

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        now = time.time()
        self._last_used[key] = now

    def clear_timeout(self):
        now = time.time()
        for key in list(self.keys()):
            if now - self._last_used[key] > self._timeout:
                self.__delitem__(key)
                del self._last_used[key]


def timeout_cache(timeout: int):
    def cached(func):
        _cache = TimeoutCache(timeout)

        @wraps(func)
        def wrap(*args, **kwargs):
            key = _make_key(args, kwargs, False)
            val = _cache.get(key)
            if val:
                return val
            val = func(*args, **kwargs)
            _cache[key] = val
            return val

        return wrap

    return cached
