from typing import Optional, List, Tuple, Dict, Callable
from io import IOBase, BytesIO
from os import PathLike
from threading import Semaphore
from concurrent.futures import ThreadPoolExecutor, as_completed

from baidupcs_py.common import constant

import requests
from requests import Response

READ_SIZE = 1 * constant.OneK
DEFAULT_MAX_CHUNK_SIZE = 10 * constant.OneM


class RangeRequestIO(IOBase):
    def __init__(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE,
        callback: Callable[..., None] = None,
        **kwargs,
    ):
        kwargs["stream"] = True

        self._method = method
        self._url = url
        self._headers = headers
        self._max_chunk_size = max_chunk_size
        self._callback = callback
        self._session = requests.session()
        self._offset = 0
        self._kwargs = kwargs
        self._len: Optional[int] = None
        super().__init__()

    def __len__(self) -> int:
        if isinstance(self._len, int):
            return self._len

        with self._request((0, 1)) as resp:
            resp_headers = resp.headers
            if not resp_headers.get("Content-Range"):
                raise IOError("Server does not support `Range` head")

        try:
            _, length = resp_headers["Content-Range"].split("/")
            _len = int(length)
            self._len = _len
            return _len
        except Exception as err:
            raise IOError("Can't parse response head `Content-Range`") from err

    def _request(self, _range: Tuple[int, int]) -> Response:
        headers = dict(self._headers or {})
        headers["Range"] = "bytes={}-{}".format(*_range)
        try:
            resp = self._session.request(
                self._method, self._url, headers=headers, **self._kwargs
            )
            return resp
        except Exception as err:
            raise IOError("Request Error") from err

    def read(self, size: int = -1) -> Optional[bytes]:
        if size == 0:
            return b""

        if size == -1:
            size = len(self) - self._offset

        buf = BytesIO()
        ranges = self._split_chunk(size)
        for _range in ranges:
            with self._request(_range) as resp:
                stream = resp.raw
                while True:
                    b = stream.read(READ_SIZE)
                    if not b:
                        break
                    buf.write(b)
                    self._offset += len(b)

                    # Call callback
                    if self._callback:
                        self._callback(self._offset)

        buf.seek(0, 0)
        return buf.read()

    def seek(self, offset: int, whence: int = 0):
        if whence == 0:
            self._offset = offset
        elif whence == 1:
            self._offset += offset
        elif whence == 2:
            self._offset = len(self) - offset

    def tell(self) -> int:
        return self._offset

    def seekable(self) -> bool:
        try:
            len(self)
            return True
        except Exception:
            return False

    def writable(self) -> bool:
        return False

    def _split_chunk(self, size: int) -> List[Tuple[int, int]]:
        start, end = self._offset, min(self._offset + size, len(self))
        left = list(range(start, end, self._max_chunk_size))
        left.append(end)
        right = [i - 1 for i in left]
        return [(s, e) for s, e in zip(left[:-1], right[1:])]
