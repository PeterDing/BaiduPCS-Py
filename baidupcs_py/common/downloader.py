from typing import Optional, Any, Callable
from os import PathLike
from pathlib import Path
from threading import Semaphore
from concurrent.futures import ThreadPoolExecutor, as_completed, Future

from baidupcs_py.common.constant import CPU_NUM
from baidupcs_py.common.io import RangeRequestIO
from baidupcs_py.common.concurrent import sure_release, retry

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
        if getattr(cls, "_executor", None):
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
        continue_: bool = False,
        done_callback: Optional[Callable[[Future], Any]] = None,
        except_callback: Optional[Callable[..., Any]] = None,
    ):
        """
        Download the url content to `localpath`

        The downloading work executing in the class ThreadPoolExecutor

        Args:
            continue_ (bool): If set to True, only downloading the remain content depended on
            the size of `localpath`
        """

        self._localpath = localpath
        self._task_id = task_id
        self._except_callback = except_callback
        self.continue_ = continue_

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

    def _init_fd(self):
        if self.continue_:
            _path = Path(self._localpath)
            if self.seekable():
                _offset = _path.stat().st_size if _path.exists() else 0
                _fd = _path.open("ab")
                _fd.seek(_offset, 0)
            else:
                _offset = 0
                _fd = _path.open("wb")
        else:
            _offset = 0
            _fd = open(self._localpath, "wb")

        self._offset = _offset
        self._fd = _fd

    @retry(30)
    def work(self):
        self._init_fd()

        try:
            start, end = self._offset, len(self)

            for b in self._auto_decrypt_request.read((start, end)):
                self._fd.write(b)
                self._offset += len(b)
                # Call callback
                if self._callback:
                    self._callback(self._task_id, self._offset)
        except Exception as err:
            if self._except_callback is not None:
                self._except_callback(self._task_id)
            self.reset()
            raise err
        finally:
            self._fd.close()
