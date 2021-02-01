from typing import Optional, List, Any, IO

import os
import time
from io import BytesIO
from enum import Enum
from pathlib import Path
from threading import Semaphore
from concurrent.futures import ThreadPoolExecutor, as_completed
from random import Random

from baidupcs_py.baidupcs.errors import BaiduPCSError
from baidupcs_py.baidupcs import BaiduPCSApi, FromTo
from baidupcs_py.common import constant
from baidupcs_py.common.path import is_file, exists, walk
from baidupcs_py.common.event import KeyHandler, KeyboardMonitor
from baidupcs_py.common.constant import CPU_NUM
from baidupcs_py.common.concurrent import sure_release, retry
from baidupcs_py.common.progress_bar import _progress, progress_task_exists
from baidupcs_py.common.io import (
    total_len,
    sample_data,
    SimpleEncryptIO,
    ChaCha20EncryptIO,
    AES256CBCEncryptIO,
    rapid_upload_params,
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


def _toggle_stop(*args, **kwargs):
    global UPLOAD_STOP
    UPLOAD_STOP = not UPLOAD_STOP
    if UPLOAD_STOP:
        print("[i yellow]Uploading stop[/i yellow]")
    else:
        print("[i yellow]Uploading continue[/i yellow]")


# Pass "p" to toggle uploading start/stop
KeyboardMonitor.register(KeyHandler("p", callback=_toggle_stop))


def _wait_start():
    while True:
        if UPLOAD_STOP:
            time.sleep(1)
        else:
            break


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
            return SimpleEncryptIO(
                io, encrypt_key, nonce_or_iv or os.urandom(16), io_len
            )
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


@retry(-1)
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

    logger.debug("`upload`: encrypt_type: %s", encrypt_type)

    # Generate nonce_or_iv
    rg = Random(salt)
    raw_io = open(localpath, "rb")
    nonce_or_iv = sample_data(raw_io, rg, 16)
    raw_io.close()

    # IO Length
    encrypt_io = encrypt_type.encrypt_io(
        open(localpath, "rb"), encrypt_key, nonce_or_iv=nonce_or_iv
    )
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

    if encrypt_io_len > 256 * constant.OneK:
        # Rapid Upload
        logger.debug("`upload`: rapid_upload starts")
        try:
            encrypt_io = encrypt_type.encrypt_io(
                open(localpath, "rb"), encrypt_key, nonce_or_iv=nonce_or_iv
            )
            slice_md5, content_md5, content_crc32, encrypt_io_len = rapid_upload_params(
                encrypt_io
            )
            api.rapid_upload_file(
                slice_md5,
                content_md5,
                content_crc32,
                encrypt_io_len,
                remotepath,
                ondup=ondup,
            )
            encrypt_io.close()
            if task_id is not None and progress_task_exists(task_id):
                _progress.update(task_id, completed=encrypt_io_len)
                _progress.remove_task(task_id)

                logger.debug("`upload`: rapid_upload success")
                return
        except BaiduPCSError as err:
            logger.debug("`upload`: rapid_upload fails")

            if err.error_code != 31079:  # 31079: '未找到文件MD5，请使用上传API上传整个文件。'
                if task_id is not None and progress_task_exists(task_id):
                    _progress.remove_task(task_id)

                logger.warning("`rapid_upload`: unknown error: %s", err)
                raise err
            else:
                logger.info("`rapid_upload`: %s, no exist in remote", localpath)

                if task_id is not None and progress_task_exists(task_id):
                    _progress.reset(task_id)

    try:
        if encrypt_io_len < slice_size:
            # Upload file
            logger.debug("`upload`: upload_file starts")

            encrypt_io = encrypt_type.encrypt_io(
                open(localpath, "rb"), encrypt_key, nonce_or_iv=nonce_or_iv
            )

            retry(
                30,
                except_callback=lambda err, fail_count: (
                    logger.warning(
                        "`upload`: `upload_file`: error: %s, fail_count: %s",
                        err,
                        fail_count,
                    ),
                    _wait_start(),
                ),
            )(api.upload_file)(encrypt_io, remotepath, ondup=ondup, callback=callback)

            encrypt_io.close()

            logger.debug("`upload`: upload_file success")
        else:
            # Upload file slice
            logger.debug("`upload`: upload_slice starts")

            slice_md5s = []
            encrypt_io = encrypt_type.encrypt_io(
                open(localpath, "rb"), encrypt_key, nonce_or_iv=nonce_or_iv
            )

            while True:
                _wait_start()

                logger.debug(
                    "`upload`: upload_slice: slice_completed: %s", slice_completed
                )

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
                        ),
                        _wait_start(),
                    ),
                )(api.upload_slice)(io, callback=callback_for_slice)

                slice_md5s.append(slice_md5)
                slice_completed += size

            encrypt_io.close()

            # Combine slices
            retry(
                30,
                except_callback=lambda err, fail_count: logger.warning(
                    "`upload`: `combine_slices`: error: %s, fail_count: %s",
                    err,
                    fail_count,
                ),
            )(api.combine_slices)(slice_md5s, remotepath, ondup=ondup)

            logger.debug("`upload`: upload_slice and combine_slices success")

        if task_id is not None and progress_task_exists(task_id):
            _progress.remove_task(task_id)
    except Exception as err:
        logger.warning("`upload`: error: %s", err)
        raise err
    finally:
        if task_id is not None and progress_task_exists(task_id):
            _progress.reset(task_id)
