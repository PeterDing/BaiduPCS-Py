from typing import Optional, List, Any, IO

import os
from enum import Enum
from pathlib import Path
from threading import Semaphore
from concurrent.futures import ThreadPoolExecutor, as_completed
from random import Random

from baidupcs_py.baidupcs.errors import BaiduPCSError
from baidupcs_py.baidupcs import BaiduPCSApi, FromTo
from baidupcs_py.common.path import is_file, exists, walk
from baidupcs_py.common import constant
from baidupcs_py.common.constant import CPU_NUM
from baidupcs_py.common.concurrent import sure_release, retry
from baidupcs_py.common.progress_bar import _progress
from baidupcs_py.common.io import (
    total_len,
    sample_data,
    ChunkIO,
    EncryptIO,
    SimpleEncryptIO,
    ChaCha20EncryptIO,
    AES256CBCEncryptIO,
    rapid_upload_params,
)

from requests_toolbelt import MultipartEncoderMonitor

from rich.progress import TaskID
from rich.table import Table
from rich.box import SIMPLE
from rich.text import Text
from rich import print

# If slice size >= 100M, the rate of uploading will be much lower.
DEFAULT_SLICE_SIZE = 50 * constant.OneM


class EncryptType(Enum):
    No = "No"
    Simple = "Simple"
    ChaCha20 = "ChaCha20"
    AES265CBC = "AES265CBC"

    def encrypt_io(self, io: IO, encrypt_key: Any, nonce_or_iv: Any = None):
        io_len = total_len(io)
        if self == EncryptType.No:
            return io
        elif self == EncryptType.Simple:
            return SimpleEncryptIO(io, encrypt_key, io_len)
        elif self == EncryptType.ChaCha20:
            return ChaCha20EncryptIO(
                io, encrypt_key, nonce_or_iv or os.urandom(16), io_len
            )
        elif self == EncryptType.AES265CBC:
            return AES256CBCEncryptIO(
                io, encrypt_key, nonce_or_iv or os.urandom(16), io_len
            )
        else:
            raise ValueError(f"Unknown EncryptType: {self}")


def to_remotepath(sub_path: str, remotedir: str) -> str:
    return (Path(remotedir) / sub_path).as_posix()


def from_tos(localpaths: List[str], remotedir: str) -> List[FromTo]:
    """Find all localpaths and their corresponded remotepath"""

    ft: List[FromTo] = []
    for localpath in localpaths:
        if not exists(localpath):
            continue

        if is_file(localpath):
            remotepath = to_remotepath(os.path.basename(localpath), remotedir)
            ft.append(FromTo(localpath, remotepath))
        else:
            n = len(str(Path(localpath)))
            for sub_path in walk(localpath):
                remotepath = to_remotepath(sub_path[n + 1 :], remotedir)
                ft.append(FromTo(sub_path, remotepath))
    return ft


# remotedir must be a directory
def upload(
    api: BaiduPCSApi,
    from_to_list: List[FromTo],
    ondup: str = "overwrite",
    encrypt_key: Any = None,
    salt: Any = None,
    encrypt_type: EncryptType = EncryptType.No,
    max_workers: int = CPU_NUM,
    slice_size: int = DEFAULT_SLICE_SIZE,
    ignore_existing: bool = True,
    show_progress: bool = True,
):
    """Upload from_tos

    Args:
        max_workers (int): The number of concurrent workers
        slice_size (int): The size of slice for uploading slices.
        ignore_existing (bool): Ignoring these localpath which of remotepath exist.
        show_progress (bool): Show uploading progress.
    """

    excepts = {}
    semaphore = Semaphore(max_workers)
    with _progress:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futs = {}
            for from_to in from_to_list:
                semaphore.acquire()
                task_id = None
                if show_progress:
                    task_id = _progress.add_task(
                        "upload", start=False, title=from_to.from_
                    )

                fut = executor.submit(
                    sure_release,
                    semaphore,
                    upload_file,
                    api,
                    from_to,
                    ondup,
                    encrypt_key=encrypt_key,
                    salt=salt,
                    encrypt_type=encrypt_type,
                    slice_size=slice_size,
                    ignore_existing=ignore_existing,
                    task_id=task_id,
                )
                futs[fut] = from_to

            for fut in as_completed(futs):
                e = fut.exception()
                if e is not None:
                    from_to = futs[fut]
                    excepts[from_to] = e

    # Summary
    if excepts:
        table = Table(title="Upload Error", box=SIMPLE, show_edge=False)
        table.add_column("From", justify="left", overflow="fold")
        table.add_column("To", justify="left", overflow="fold")
        table.add_column("Error", justify="left")

        for from_to, e in sorted(excepts.items()):
            table.add_row(from_to.from_, Text(str(e), style="red"))

        _progress.console.print(table)


@retry(3)
def upload_file(
    api: BaiduPCSApi,
    from_to: FromTo,
    ondup: str,
    encrypt_key: Any = None,
    salt: Any = None,
    encrypt_type: EncryptType = EncryptType.No,
    slice_size: int = DEFAULT_SLICE_SIZE,
    ignore_existing: bool = True,
    task_id: Optional[TaskID] = None,
):
    localpath, remotepath = from_to

    assert exists(localpath), f"`{localpath}` does not exist"

    if ignore_existing:
        try:
            if api.exists(remotepath):
                print(f"`{remotepath}` already exists.")
                if task_id is not None:
                    _progress.remove_task(task_id)
                return
        except Exception as err:
            if task_id is not None:
                _progress.remove_task(task_id)
            raise err

    # Generate nonce
    rg = Random(salt)
    raw_io = open(localpath, "rb")
    nonce = sample_data(raw_io, rg, 16)
    raw_io.close()

    # IO Length
    encrypt_io = encrypt_type.encrypt_io(
        open(localpath, "rb"), encrypt_key, nonce_or_iv=nonce
    )
    if isinstance(encrypt_io, EncryptIO):
        io_len = len(encrypt_io)
    else:
        io_len = encrypt_io.seek(0, 2)
        encrypt_io.seek(0, 0)
    encrypt_io.close()

    # Progress bar
    if task_id is not None:
        _progress.update(task_id, total=io_len)
        _progress.start_task(task_id)

    def callback(monitor: MultipartEncoderMonitor):
        if task_id is not None:
            _progress.update(task_id, completed=monitor.bytes_read)

    slice_completed = 0

    def callback_for_slice(monitor: MultipartEncoderMonitor):
        if task_id is not None:
            _progress.update(task_id, completed=slice_completed + monitor.bytes_read)

    if io_len > 256 * constant.OneK:
        # Rapid Upload
        try:
            encrypt_io = encrypt_type.encrypt_io(
                open(localpath, "rb"), encrypt_key, nonce_or_iv=nonce
            )
            slice_md5, content_md5, content_crc32, io_len = rapid_upload_params(
                encrypt_io
            )
            api.rapid_upload_file(
                slice_md5, content_md5, content_crc32, io_len, remotepath, ondup=ondup
            )
            encrypt_io.close()
            if task_id is not None:
                _progress.update(task_id, completed=io_len)
                _progress.remove_task(task_id)
                return
        except BaiduPCSError as err:
            if err.error_code != 31079:  # 31079: '未找到文件MD5，请使用上传API上传整个文件。'
                if task_id is not None:
                    _progress.remove_task(task_id)
                raise err
            else:
                if task_id is not None:
                    _progress.reset(task_id)

    try:
        if io_len < slice_size:
            # Upload file
            encrypt_io = encrypt_type.encrypt_io(
                open(localpath, "rb"), encrypt_key, nonce_or_iv=nonce
            )
            api.upload_file(encrypt_io, remotepath, ondup=ondup, callback=callback)
            encrypt_io.close()
        else:
            # Upload file slice
            slice_md5s = []
            encrypt_io = encrypt_type.encrypt_io(
                open(localpath, "rb"), encrypt_key, nonce_or_iv=nonce
            )

            while True:
                size = min(slice_size, io_len - slice_completed)
                if size == 0:
                    break
                io = ChunkIO(encrypt_io, size)
                slice_md5 = api.upload_slice(io, callback=callback_for_slice)
                slice_md5s.append(slice_md5)
                slice_completed += size

            encrypt_io.close()
            api.combine_slices(slice_md5s, remotepath, ondup=ondup)
    finally:
        if task_id is not None:
            _progress.remove_task(task_id)
