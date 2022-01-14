from typing import Optional, List, Tuple, IO

import os
import time
import functools
from io import BytesIO
from enum import Enum
from pathlib import Path
from threading import Semaphore
from concurrent.futures import ThreadPoolExecutor, as_completed

from baidupcs_py.baidupcs.errors import BaiduPCSError
from baidupcs_py.baidupcs import BaiduPCSApi, FromTo
from baidupcs_py.common import constant
from baidupcs_py.common.path import is_file, exists, walk
from baidupcs_py.common.event import KeyHandler, KeyboardMonitor
from baidupcs_py.common.constant import CPU_NUM
from baidupcs_py.common.concurrent import sure_release, retry
from baidupcs_py.common.progress_bar import _progress, progress_task_exists
from baidupcs_py.common.localstorage import save_rapid_upload_info
from baidupcs_py.common.io import (
    total_len,
    rapid_upload_params,
    EncryptType,
    reset_encrypt_io,
)
from baidupcs_py.commands.log import get_logger

from requests_toolbelt import MultipartEncoderMonitor

from rich.progress import TaskID
from rich.table import Table
from rich.box import SIMPLE
from rich.text import Text
from rich import print

logger = get_logger(__name__)

# If slice size >= 100M, the rate of uploading will be much lower.
DEFAULT_SLICE_SIZE = 30 * constant.OneM


UPLOAD_STOP = False

_rapiduploadinfo_file: Optional[str] = None


def _wait_start():
    while True:
        if UPLOAD_STOP:
            time.sleep(1)
        else:
            break


def _toggle_stop(*args, **kwargs):
    global UPLOAD_STOP
    UPLOAD_STOP = not UPLOAD_STOP
    if UPLOAD_STOP:
        print("[i yellow]Uploading stop[/i yellow]")
    else:
        print("[i yellow]Uploading continue[/i yellow]")


# Pass "p" to toggle uploading start/stop
KeyboardMonitor.register(KeyHandler("p", callback=_toggle_stop))


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
            parents_num = max(len(Path(localpath).parts) - 1, 0)
            for sub_path in walk(localpath):
                relative_path = Path(*Path(sub_path).parts[parents_num:]).as_posix()
                remotepath = to_remotepath(relative_path, remotedir)
                ft.append(FromTo(sub_path, remotepath))
    return ft


class UploadType(Enum):
    """Upload Type

    One: Upload the slices of one file concurrently
    Many: Upload files concurrently
    """

    One = 1
    Many = 2


def _handle_deadly_error(err, fail_count):

    # If following errors occur, we need to re-upload
    if isinstance(err, BaiduPCSError) and (
        err.error_code == 31352  # commit superfile2 failed
        or err.error_code == 31363  # block miss in superfile2
        or err.error_code == 31062  # 文件名非法
    ):
        logger.warning(
            "Deadly error: %s, fail_count: %s",
            err,
            fail_count,
            exc_info=err,
        )
        raise err


# remotedir must be a directory
def upload(
    api: BaiduPCSApi,
    from_to_list: List[FromTo],
    upload_type: UploadType = UploadType.One,
    ondup: str = "overwrite",
    encrypt_password: bytes = b"",
    encrypt_type: EncryptType = EncryptType.No,
    max_workers: int = CPU_NUM,
    slice_size: int = DEFAULT_SLICE_SIZE,
    ignore_existing: bool = True,
    show_progress: bool = True,
    rapiduploadinfo_file: Optional[str] = None,
    user_id: Optional[int] = None,
    user_name: Optional[str] = None,
    check_md5: bool = False,
):
    """Upload from_tos

    Args:
        upload_type (UploadType): the way of uploading.
        max_workers (int): The number of concurrent workers.
        slice_size (int): The size of slice for uploading slices.
        ignore_existing (bool): Ignoring these localpath which of remotepath exist.
        show_progress (bool): Show uploading progress.

        check_md5 (bool): To fix the content md5 after `combine_slices`
            `combine_slices` always does not return correct content md5. To fix it,
            we need to use `rapid_upload_file` re-upload the content.
            Warning, if content length is large, it could take some minutes,
            e.g. it takes 5 minutes about 2GB.
    """

    logger.debug(
        "======== Uploading start ========\n-> UploadType: %s\n-> Size of from_to_list: %s",
        upload_type,
        len(from_to_list),
    )

    global _rapiduploadinfo_file
    if _rapiduploadinfo_file is None:
        _rapiduploadinfo_file = rapiduploadinfo_file

    if upload_type == UploadType.One:
        upload_one_by_one(
            api,
            from_to_list,
            ondup,
            max_workers=max_workers,
            encrypt_password=encrypt_password,
            encrypt_type=encrypt_type,
            slice_size=slice_size,
            ignore_existing=ignore_existing,
            show_progress=show_progress,
            user_id=user_id,
            user_name=user_name,
            check_md5=check_md5,
        )
    elif upload_type == UploadType.Many:
        upload_many(
            api,
            from_to_list,
            ondup,
            max_workers=max_workers,
            encrypt_password=encrypt_password,
            encrypt_type=encrypt_type,
            slice_size=slice_size,
            ignore_existing=ignore_existing,
            show_progress=show_progress,
            user_id=user_id,
            user_name=user_name,
            check_md5=check_md5,
        )


def _init_encrypt_io(
    api: BaiduPCSApi,
    localpath: str,
    remotepath: str,
    encrypt_password: bytes = b"",
    encrypt_type: EncryptType = EncryptType.No,
    ignore_existing: bool = True,
    task_id: Optional[TaskID] = None,
) -> Optional[Tuple[IO, int, int, int]]:
    assert exists(Path(localpath)), f"`{localpath}` does not exist"

    if ignore_existing:
        try:
            if api.exists(remotepath):
                print(f"`{remotepath}` already exists.")
                logger.debug("`_init_encrypt_io`: remote file already exists")
                if task_id is not None and progress_task_exists(task_id):
                    _progress.remove_task(task_id)
                return None
        except Exception as err:
            if task_id is not None and progress_task_exists(task_id):
                _progress.remove_task(task_id)
            raise err

    stat = Path(localpath).stat()
    local_ctime, local_mtime = int(stat.st_ctime), int(stat.st_mtime)

    encrypt_io = encrypt_type.encrypt_io(open(localpath, "rb"), encrypt_password)
    # IO Length
    encrypt_io_len = total_len(encrypt_io)

    logger.debug(
        "`_init_encrypt_io`: encrypt_type: %s, localpath: %s, remotepath: %s, encrypt_io_len: %s",
        encrypt_type,
        localpath,
        remotepath,
        encrypt_io_len,
    )

    return (encrypt_io, encrypt_io_len, local_ctime, local_mtime)


def _rapid_upload(
    api: BaiduPCSApi,
    localpath: str,
    remotepath: str,
    slice256k_md5: str,
    content_md5: str,
    content_crc32: int,
    io_len: int,
    local_ctime: int,
    local_mtime: int,
    ondup: str,
    encrypt_password: bytes = b"",
    encrypt_type: EncryptType = EncryptType.No,
    task_id: Optional[TaskID] = None,
    user_id: Optional[int] = None,
    user_name: Optional[str] = None,
) -> bool:
    logger.debug("`_rapid_upload`: rapid_upload starts")
    try:
        api.rapid_upload_file(
            slice256k_md5,
            content_md5,
            0,  # not needed
            io_len,
            remotepath,
            local_ctime=local_ctime,
            local_mtime=local_mtime,
            ondup=ondup,
        )

        if _rapiduploadinfo_file:
            save_rapid_upload_info(
                _rapiduploadinfo_file,
                slice256k_md5,
                content_md5,
                content_crc32,
                io_len,
                localpath=localpath,
                remotepath=remotepath,
                encrypt_password=encrypt_password,
                encrypt_type=encrypt_type.value,
                user_id=user_id,
                user_name=user_name,
            )

        if task_id is not None and progress_task_exists(task_id):
            _progress.update(task_id, completed=io_len)
            _progress.remove_task(task_id)

        logger.debug("`_rapid_upload`: rapid_upload success, task_id: %s", task_id)
        return True
    except BaiduPCSError as err:
        logger.warning("`_rapid_upload`: rapid_upload fails")

        if err.error_code != 31079:  # 31079: '未找到文件MD5，请使用上传API上传整个文件。'
            if task_id is not None and progress_task_exists(task_id):
                _progress.remove_task(task_id)

            logger.warning("`_rapid_upload`: unknown error: %s", err)
            raise err
        else:
            logger.debug("`_rapid_upload`: %s, no exist in remote", localpath)

            if task_id is not None and progress_task_exists(task_id):
                _progress.reset(task_id)

        return False


@retry(20, except_callback=_handle_deadly_error)
def _combine_slices(
    api: BaiduPCSApi,
    remotepath: str,
    slice_md5s: List[str],
    local_ctime: int,
    local_mtime: int,
    ondup: str,
):
    api.combine_slices(
        slice_md5s,
        remotepath,
        local_ctime=local_ctime,
        local_mtime=local_mtime,
        ondup=ondup,
    )


def upload_one_by_one(
    api: BaiduPCSApi,
    from_to_list: List[FromTo],
    ondup: str,
    max_workers: int = CPU_NUM,
    encrypt_password: bytes = b"",
    encrypt_type: EncryptType = EncryptType.No,
    slice_size: int = DEFAULT_SLICE_SIZE,
    ignore_existing: bool = True,
    show_progress: bool = True,
    user_id: Optional[int] = None,
    user_name: Optional[str] = None,
    check_md5: bool = False,
):
    """Upload files one by one with uploading the slices concurrently"""

    with _progress:
        for from_to in from_to_list:
            task_id = None
            if show_progress:
                task_id = _progress.add_task("upload", start=False, title=from_to.from_)
            upload_file_concurrently(
                api,
                from_to,
                ondup,
                max_workers=max_workers,
                encrypt_password=encrypt_password,
                encrypt_type=encrypt_type,
                slice_size=slice_size,
                ignore_existing=ignore_existing,
                task_id=task_id,
                user_id=user_id,
                user_name=user_name,
                check_md5=check_md5,
            )

    logger.debug("======== Uploading end ========")


@retry(
    -1,
    except_callback=lambda err, fail_count: (
        _handle_deadly_error(err, fail_count),
        logger.warning(
            "`upload_file_concurrently`: fails: error: %s, fail_count: %s",
            err,
            fail_count,
            exc_info=err,
        ),
    ),
)
def upload_file_concurrently(
    api: BaiduPCSApi,
    from_to: FromTo,
    ondup: str,
    max_workers: int = CPU_NUM,
    encrypt_password: bytes = b"",
    encrypt_type: EncryptType = EncryptType.No,
    slice_size: int = DEFAULT_SLICE_SIZE,
    ignore_existing: bool = True,
    task_id: Optional[TaskID] = None,
    user_id: Optional[int] = None,
    user_name: Optional[str] = None,
    check_md5: bool = False,
):
    """Uploading one file by uploading it's slices concurrently"""

    localpath, remotepath = from_to

    info = _init_encrypt_io(
        api,
        localpath,
        remotepath,
        encrypt_password=encrypt_password,
        encrypt_type=encrypt_type,
        ignore_existing=ignore_existing,
        task_id=task_id,
    )
    if not info:
        return
    encrypt_io, encrypt_io_len, local_ctime, local_mtime = info

    # Progress bar
    if task_id is not None and progress_task_exists(task_id):
        _progress.update(task_id, total=encrypt_io_len)
        _progress.start_task(task_id)

    slice_completed = 0
    slice_completeds = {}  # current i-th index slice completed size

    def callback_for_slice(idx: int, monitor: MultipartEncoderMonitor):
        if task_id is not None and progress_task_exists(task_id):
            slice_completeds[idx] = monitor.bytes_read
            current_compledted: int = sum(list(slice_completeds.values()))
            _progress.update(task_id, completed=slice_completed + current_compledted)

    slice256k_md5 = ""
    content_md5 = ""
    content_crc32 = 0
    io_len = 0

    if encrypt_type == EncryptType.No and encrypt_io_len > 256 * constant.OneK:
        # Rapid Upload
        slice256k_md5, content_md5, content_crc32, io_len = rapid_upload_params(
            encrypt_io
        )
        ok = _rapid_upload(
            api,
            localpath,
            remotepath,
            slice256k_md5,
            content_md5,
            content_crc32,
            io_len,
            local_ctime,
            local_mtime,
            ondup,
            encrypt_password=encrypt_password,
            encrypt_type=encrypt_type,
            task_id=task_id,
            user_id=user_id,
            user_name=user_name,
        )
        if ok:
            return

    try:
        # Upload file slice
        logger.debug("`upload_file_concurrently`: upload_slice starts")

        reset_encrypt_io(encrypt_io)

        completed_slice_md5s = []

        def upload_slice(item: Tuple[int, IO]):
            idx, io = item

            # Retry upload until success
            slice_md5 = retry(
                -1,
                except_callback=lambda err, fail_count: (
                    _handle_deadly_error(err, fail_count),
                    io.seek(0, 0),
                    logger.warning(
                        "`upload_file_concurrently`: error: %s, fail_count: %s",
                        err,
                        fail_count,
                        exc_info=err,
                    ),
                    _wait_start(),
                ),
            )(api.upload_slice)(io, callback=functools.partial(callback_for_slice, idx))

            slice_completeds.pop(idx)
            completed_slice_md5s.append((idx, slice_md5))

            nonlocal slice_completed
            slice_completed += total_len(io)

        semaphore = Semaphore(max_workers)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futs = []
            offset = 0
            idx = 0
            while True:
                semaphore.acquire()

                size = min(slice_size, encrypt_io_len - offset)
                if idx != 0 and size == 0:
                    break

                data = encrypt_io.read(size)
                io = BytesIO(data or b"")

                fut = executor.submit(sure_release, semaphore, upload_slice, (idx, io))
                futs.append(fut)

                idx += 1
                offset += size

            as_completed(futs)

        completed_slice_md5s.sort()
        slice_md5s = [md5 for _, md5 in completed_slice_md5s]

        # Combine slices
        _combine_slices(
            api,
            remotepath,
            slice_md5s,
            local_ctime,
            local_mtime,
            ondup,
        )

        logger.debug(
            "`upload_file_concurrently`: upload_slice and combine_slices success, task_id: %s",
            task_id,
        )

        # `combine_slices` can not get right content md5.
        # We need to check whether server updates by hand.
        if check_md5:
            _check_md5(
                api,
                localpath,
                remotepath,
                slice256k_md5,
                content_md5,
                content_crc32,
                io_len,
                encrypt_password=encrypt_password,
                encrypt_type=encrypt_type.value,
                user_id=user_id,
                user_name=user_name,
            )

        if task_id is not None and progress_task_exists(task_id):
            _progress.remove_task(task_id)
    except Exception as err:
        logger.warning("`upload_file_concurrently`: error: %s", err)
        raise err
    finally:
        encrypt_io.close()
        if task_id is not None and progress_task_exists(task_id):
            _progress.reset(task_id)


def upload_many(
    api: BaiduPCSApi,
    from_to_list: List[FromTo],
    ondup: str = "overwrite",
    encrypt_password: bytes = b"",
    encrypt_type: EncryptType = EncryptType.No,
    max_workers: int = CPU_NUM,
    slice_size: int = DEFAULT_SLICE_SIZE,
    ignore_existing: bool = True,
    show_progress: bool = True,
    rapiduploadinfo_file: Optional[str] = None,
    user_id: Optional[int] = None,
    user_name: Optional[str] = None,
    check_md5: bool = False,
):
    """Upload files concurrently that one file is with one connection"""

    excepts = {}
    semaphore = Semaphore(max_workers)
    with _progress:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futs = {}
            for idx, from_to in enumerate(from_to_list):
                semaphore.acquire()
                task_id = None
                if show_progress:
                    task_id = _progress.add_task(
                        "upload", start=False, title=from_to.from_
                    )

                logger.debug(
                    "`upload_many`: Upload: index: %s, task_id: %s", idx, task_id
                )

                fut = executor.submit(
                    sure_release,
                    semaphore,
                    upload_file,
                    api,
                    from_to,
                    ondup,
                    encrypt_password=encrypt_password,
                    encrypt_type=encrypt_type,
                    slice_size=slice_size,
                    ignore_existing=ignore_existing,
                    task_id=task_id,
                    user_id=user_id,
                    user_name=user_name,
                    check_md5=check_md5,
                )
                futs[fut] = from_to

            for fut in as_completed(futs):
                e = fut.exception()
                if e is not None:
                    from_to = futs[fut]
                    excepts[from_to] = e

    logger.debug("======== Uploading end ========")

    # Summary
    if excepts:
        table = Table(title="Upload Error", box=SIMPLE, show_edge=False)
        table.add_column("From", justify="left", overflow="fold")
        table.add_column("To", justify="left", overflow="fold")
        table.add_column("Error", justify="left")

        for from_to, e in sorted(excepts.items()):
            table.add_row(from_to.from_, Text(str(e), style="red"))

        _progress.console.print(table)


@retry(
    -1,
    except_callback=lambda err, fail_count: (
        _handle_deadly_error(err, fail_count),
        logger.warning(
            "`upload_file`: fails: error: %s, fail_count: %s",
            err,
            fail_count,
            exc_info=err,
        ),
    ),
)
def upload_file(
    api: BaiduPCSApi,
    from_to: FromTo,
    ondup: str,
    encrypt_password: bytes = b"",
    encrypt_type: EncryptType = EncryptType.No,
    slice_size: int = DEFAULT_SLICE_SIZE,
    ignore_existing: bool = True,
    task_id: Optional[TaskID] = None,
    user_id: Optional[int] = None,
    user_name: Optional[str] = None,
    check_md5: bool = False,
):
    """Upload one file with one connection"""

    _wait_start()

    localpath, remotepath = from_to

    info = _init_encrypt_io(
        api,
        localpath,
        remotepath,
        encrypt_password=encrypt_password,
        encrypt_type=encrypt_type,
        ignore_existing=ignore_existing,
        task_id=task_id,
    )
    if not info:
        return
    encrypt_io, encrypt_io_len, local_ctime, local_mtime = info

    # Progress bar
    if task_id is not None and progress_task_exists(task_id):
        _progress.update(task_id, total=encrypt_io_len)
        _progress.start_task(task_id)

    slice_completed = 0

    def callback_for_slice(monitor: MultipartEncoderMonitor):
        if task_id is not None and progress_task_exists(task_id):
            _progress.update(task_id, completed=slice_completed + monitor.bytes_read)

    slice256k_md5 = ""
    content_md5 = ""
    content_crc32 = 0
    io_len = 0

    if encrypt_type == EncryptType.No and encrypt_io_len > 256 * constant.OneK:
        # Rapid Upload
        slice256k_md5, content_md5, content_crc32, io_len = rapid_upload_params(
            encrypt_io
        )
        ok = _rapid_upload(
            api,
            localpath,
            remotepath,
            slice256k_md5,
            content_md5,
            content_crc32,
            io_len,
            local_ctime,
            local_mtime,
            ondup,
            encrypt_password=encrypt_password,
            encrypt_type=encrypt_type,
            task_id=task_id,
            user_id=user_id,
            user_name=user_name,
        )
        if ok:
            return

    try:
        # Upload file slice
        logger.debug("`upload_file`: upload_slice starts")

        slice_md5s = []
        reset_encrypt_io(encrypt_io)

        idx = 0
        while True:
            _wait_start()

            logger.debug(
                "`upload_file`: upload_slice: slice_completed: %s", slice_completed
            )

            size = min(slice_size, encrypt_io_len - slice_completed)
            if idx != 0 and size == 0:
                break

            data = encrypt_io.read(size) or b""
            io = BytesIO(data)

            logger.debug(
                "`upload_file`: upload_slice: size should be %s == %s", size, len(data)
            )

            # Retry upload until success
            slice_md5 = retry(
                -1,
                except_callback=lambda err, fail_count: (
                    _handle_deadly_error(err, fail_count),
                    io.seek(0, 0),
                    logger.warning(
                        "`upload_file`: `upload_slice`: error: %s, fail_count: %s",
                        err,
                        fail_count,
                        exc_info=err,
                    ),
                    _wait_start(),
                ),
            )(api.upload_slice)(io, callback=callback_for_slice)

            slice_md5s.append(slice_md5)
            slice_completed += size
            idx += 1

        # Combine slices
        _combine_slices(
            api,
            remotepath,
            slice_md5s,
            local_ctime,
            local_mtime,
            ondup,
        )

        logger.debug(
            "`upload_file`: upload_slice and combine_slices success, task_id: %s",
            task_id,
        )

        # `combine_slices` can not get right content md5.
        # We need to check whether server updates by hand.
        if check_md5:
            _check_md5(
                api,
                localpath,
                remotepath,
                slice256k_md5,
                content_md5,
                content_crc32,
                io_len,
                encrypt_password=encrypt_password,
                encrypt_type=encrypt_type.value,
                user_id=user_id,
                user_name=user_name,
            )

        if task_id is not None and progress_task_exists(task_id):
            _progress.remove_task(task_id)
    except Exception as err:
        logger.warning("`upload_file`: error: %s", err)
        raise err
    finally:
        encrypt_io.close()
        if task_id is not None and progress_task_exists(task_id):
            _progress.reset(task_id)


def _check_md5(
    api: BaiduPCSApi,
    localpath: str,
    remotepath: str,
    slice_md5: str,
    content_md5: str,
    content_crc32: int,  # not needed
    content_length: int,
    encrypt_password: bytes = b"",
    encrypt_type: str = "",
    user_id: Optional[int] = None,
    user_name: Optional[str] = None,
):
    """Fix remote content md5 with rapid upload

    There is a delay for server to handle uploaded data after `combine_slices`,
    so we retry fix it.
    """

    i = 0
    while True:
        logger.debug(
            f"`_check_md5`: retry: {i}: "
            "slice_md5: %s, content_md5: %s, content_crc32: %s, io_len: %s, remotepath: %s",
            slice_md5,
            content_md5,
            content_crc32,
            content_length,
            remotepath,
        )
        i += 1

        try:
            api.rapid_upload_file(
                slice_md5,
                content_md5,
                content_crc32,  # not needed
                content_length,
                remotepath,
                ondup="overwrite",
            )
            logger.warning("`_check_md5`: successes")

            if _rapiduploadinfo_file:
                save_rapid_upload_info(
                    _rapiduploadinfo_file,
                    slice_md5,
                    content_md5,
                    content_crc32,
                    content_length,
                    localpath=localpath,
                    remotepath=remotepath,
                    encrypt_password=encrypt_password,
                    encrypt_type=encrypt_type,
                    user_id=user_id,
                    user_name=user_name,
                )
            return
        except Exception as err:
            logger.warning("`_check_md5`: fails: %s", err)
            time.sleep(2)
            continue
