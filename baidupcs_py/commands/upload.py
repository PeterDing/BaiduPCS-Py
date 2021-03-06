from typing import Optional, List

import os
import time
from io import BytesIO
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
DEFAULT_SLICE_SIZE = 50 * constant.OneM


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
            n = len(str(Path(localpath).parent))
            for sub_path in walk(localpath):
                remotepath = to_remotepath(sub_path[n + 1 :], remotedir)
                ft.append(FromTo(sub_path, remotepath))
    return ft


# remotedir must be a directory
def upload(
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
    """Upload from_tos

    Args:
        max_workers (int): The number of concurrent workers
        slice_size (int): The size of slice for uploading slices.
        ignore_existing (bool): Ignoring these localpath which of remotepath exist.
        show_progress (bool): Show uploading progress.

        check_md5 (bool): To fix the content md5 after `combine_slices`
            `combine_slices` always not return correct content md5. To fix it,
            we need to use `rapid_upload_file` re-upload the content.
            Warning, if content length is large, it could take some minutes,
            e.g. it takes 5 minutes about 2GB.
    """

    logger.debug(
        "======== Uploading start ========\n-> Size of from_to_list: %s",
        len(from_to_list),
    )

    global _rapiduploadinfo_file
    if _rapiduploadinfo_file is None:
        _rapiduploadinfo_file = rapiduploadinfo_file

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

                logger.debug("-> Upload: index: %s, task_id: %s", idx, task_id)

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
            f"`upload`: `check_md5`: retry: {i}: "
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
            logger.warning("`upload`: `check_md5` successes")

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
            logger.warning("`upload`: `check_md5` fails: %s", err)
            time.sleep(2)
            continue


@retry(
    -1,
    except_callback=lambda err, fail_count: logger.warning(
        "`upload_file`: fails: error: %s, fail_count: %s",
        err,
        fail_count,
        exc_info=err,
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
    _wait_start()

    localpath, remotepath = from_to

    assert exists(localpath), f"`{localpath}` does not exist"

    if ignore_existing:
        try:
            if api.exists(remotepath):
                print(f"`{remotepath}` already exists.")
                logger.debug("`upload`: remote file already exists")
                if task_id is not None and progress_task_exists(task_id):
                    _progress.remove_task(task_id)
                return
        except Exception as err:
            if task_id is not None and progress_task_exists(task_id):
                _progress.remove_task(task_id)
            raise err

    logger.debug(
        "`upload`: encrypt_type: %s, localpath: %s, remotepath, %s",
        encrypt_type,
        localpath,
        remotepath,
    )

    stat = Path(localpath).stat()
    local_ctime, local_mtime = int(stat.st_ctime), int(stat.st_mtime)

    encrypt_io = encrypt_type.encrypt_io(open(localpath, "rb"), encrypt_password)
    # IO Length
    encrypt_io_len = total_len(encrypt_io)

    logger.debug("`upload`: encrypt_io_len: %s", encrypt_io_len)

    # Progress bar
    if task_id is not None and progress_task_exists(task_id):
        _progress.update(task_id, total=encrypt_io_len)
        _progress.start_task(task_id)

    def callback(monitor: MultipartEncoderMonitor):
        if task_id is not None and progress_task_exists(task_id):
            _progress.update(task_id, completed=monitor.bytes_read)

    slice_completed = 0

    def callback_for_slice(monitor: MultipartEncoderMonitor):
        if task_id is not None and progress_task_exists(task_id):
            _progress.update(task_id, completed=slice_completed + monitor.bytes_read)

    slice256k_md5 = ""
    content_md5 = ""
    content_crc32 = 0
    io_len = 0

    if encrypt_io_len > 256 * constant.OneK:
        # Rapid Upload
        logger.debug("`upload`: rapid_upload starts")
        try:
            slice256k_md5, content_md5, content_crc32, io_len = rapid_upload_params(
                encrypt_io
            )
            api.rapid_upload_file(
                slice256k_md5,
                content_md5,
                0,  # not needed
                encrypt_io_len,
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
                _progress.update(task_id, completed=encrypt_io_len)
                _progress.remove_task(task_id)

            logger.debug("`upload`: rapid_upload success, task_id: %s", task_id)
            return
        except BaiduPCSError as err:
            logger.warning("`upload`: rapid_upload fails")

            if err.error_code != 31079:  # 31079: '未找到文件MD5，请使用上传API上传整个文件。'
                if task_id is not None and progress_task_exists(task_id):
                    _progress.remove_task(task_id)

                logger.warning("`rapid_upload`: unknown error: %s", err)
                raise err
            else:
                logger.debug("`rapid_upload`: %s, no exist in remote", localpath)

                if task_id is not None and progress_task_exists(task_id):
                    _progress.reset(task_id)

    try:
        # Upload file slice
        logger.debug("`upload`: upload_slice starts")

        slice_md5s = []
        reset_encrypt_io(encrypt_io)

        while True:
            _wait_start()

            logger.debug("`upload`: upload_slice: slice_completed: %s", slice_completed)

            size = min(slice_size, encrypt_io_len - slice_completed)
            if size == 0:
                break

            data = encrypt_io.read(size) or b""
            io = BytesIO(data)

            logger.debug(
                "`upload`: upload_slice: size should be %s == %s", size, len(data)
            )

            # Retry upload until success
            slice_md5 = retry(
                -1,
                except_callback=lambda err, fail_count: (
                    io.seek(0, 0),
                    logger.warning(
                        "`upload`: `upload_slice`: error: %s, fail_count: %s",
                        err,
                        fail_count,
                        exc_info=err,
                    ),
                    _wait_start(),
                ),
            )(api.upload_slice)(io, callback=callback_for_slice)

            slice_md5s.append(slice_md5)
            slice_completed += size

        # Combine slices
        def _handle_combin_slices_error(err, fail_count):
            logger.warning(
                "`upload`: `combine_slices`: error: %s, fail_count: %s",
                err,
                fail_count,
                exc_info=err,
            )

            # If following errors occur, we need to re-upload
            if (
                isinstance(err, BaiduPCSError)
                and err.error_code == 31352  # commit superfile2 failed
                or err.error_code == 31363  # block miss in superfile2
            ):
                raise err

        retry(20, except_callback=_handle_combin_slices_error)(api.combine_slices)(
            slice_md5s,
            remotepath,
            local_ctime=local_ctime,
            local_mtime=local_mtime,
            ondup=ondup,
        )

        logger.debug(
            "`upload`: upload_slice and combine_slices success, task_id: %s", task_id
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
        logger.warning("`upload`: error: %s", err)
        raise err
    finally:
        encrypt_io.close()
        if task_id is not None and progress_task_exists(task_id):
            _progress.reset(task_id)
