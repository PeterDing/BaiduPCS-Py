from typing import Optional, List

import os
from pathlib import Path
from threading import Semaphore
from concurrent.futures import ThreadPoolExecutor, as_completed

from baidupcs_py.baidupcs import BaiduPCSApi, FromTo
from baidupcs_py.common.path import is_file, exists, walk
from baidupcs_py.common import constant
from baidupcs_py.common.constant import CPU_NUM
from baidupcs_py.common.concurrent import sure_release
from baidupcs_py.common.progress_bar import _progress
from baidupcs_py.baidupcs.errors import BaiduPCSError

from requests_toolbelt import MultipartEncoderMonitor

from rich.progress import TaskID
from rich.table import Table
from rich.box import SIMPLE
from rich.text import Text
from rich import print

DEFAULT_SLICE_SIZE = 100 * constant.OneM


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
                        "upload", start=False, localpath=from_to.from_
                    )

                fut = executor.submit(
                    sure_release,
                    semaphore,
                    upload_file,
                    api,
                    from_to,
                    ondup,
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
        table = Table(box=SIMPLE, padding=0, show_edge=False)
        table.add_column("localpath", justify="right", overflow="fold")
        table.add_column("error", justify="left")

        for from_to, e in sorted(excepts.items()):
            table.add_row(from_to.from_, Text(str(e), style="red"))

        _progress.console.print(table)


def upload_file(
    api: BaiduPCSApi,
    from_to: FromTo,
    ondup: str,
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

    local_size = Path(localpath).stat().st_size

    if task_id is not None:
        _progress.update(task_id, total=local_size)
        _progress.start_task(task_id)

    def callback(monitor: MultipartEncoderMonitor):
        if task_id is not None:
            _progress.update(task_id, completed=monitor.bytes_read)

    slice_completed = 0

    def callback_for_slice(monitor: MultipartEncoderMonitor):
        if task_id is not None:
            _progress.update(task_id, completed=slice_completed + monitor.bytes_read)

    if local_size > 256 * constant.OneK:
        try:
            api.rapid_upload_file(localpath, remotepath, ondup=ondup)
            if task_id is not None:
                _progress.update(task_id, completed=local_size)
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
        if local_size < slice_size:
            api.upload_file(localpath, remotepath, ondup=ondup, callback=callback)
        else:
            slice_md5s = []
            fd = open(localpath, "rb")
            while True:
                buf = fd.read(slice_size)
                if not buf:
                    break

                slice_md5 = api.upload_slice(buf, callback=callback_for_slice)
                slice_md5s.append(slice_md5)
                slice_completed += len(buf)

            api.combine_slices(slice_md5s, remotepath, ondup=ondup)
    finally:
        if task_id is not None:
            _progress.remove_task(task_id)
