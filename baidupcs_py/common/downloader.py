from typing import Optional, Any, Callable
from os import PathLike
from threading import Semaphore
from concurrent.futures import ThreadPoolExecutor, as_completed, Future

from baidupcs_py.common.constant import CPU_NUM
from baidupcs_py.common.io import RangeRequestIO, READ_SIZE
from baidupcs_py.common.concurrent import sure_release

from rich.progress import TaskID

DEFAULT_MAX_WORKERS = 5


class MeDownloader(RangeRequestIO):
    @classmethod
    def _set_executor(
        cls,
        max_workers: int = CPU_NUM,
    ):
        cls._executor = ThreadPoolExecutor(max_workers=max_workers)
        cls._semaphore = Semaphore(max_workers)
        cls._futures = []

    @classmethod
    def _exit_executor(cls):
        as_completed(cls._futures)
        cls._futures = []
        cls._executor.__exit__(None, None, None)

    def __init__(self, *args, max_workers: int = CPU_NUM, **kwargs):
        super().__init__(*args, **kwargs)
        if not getattr(self.__class__, "_executor", None):
            self.__class__._set_executor(max_workers)

    def download(
        self,
        localpath: PathLike,
        task_id: Optional[TaskID],
        done_callback: Optional[Callable[[Future], Any]] = None,
    ):
        self._task_id = task_id
        self._fd = open(localpath, "wb")

        cls = self.__class__
        cls._semaphore.acquire()

        fut = cls._executor.submit(
            sure_release,
            cls._semaphore,
            self.work,
        )
        if done_callback:
            fut.add_done_callback(done_callback)
        cls._futures.append(fut)

    def work(self):
        size = len(self)
        ranges = self._split_chunk(size)
        for _range in ranges:
            with self._request(_range) as resp:
                stream = resp.raw
                while True:
                    b = stream.read(READ_SIZE)
                    if not b:
                        break

                    self._fd.write(b)
                    self._offset += len(b)

                    # Call callback
                    if self._callback:
                        self._callback(self._task_id, self._offset)
