from typing import Optional, List, Dict, Any, Callable, TypeVar
from types import SimpleNamespace
from enum import Enum
from pathlib import Path
import os
import shutil
import subprocess
from concurrent.futures import Future

from baidupcs_py.baidupcs import BaiduPCSApi
from baidupcs_py.utils import human_size, human_size_to_int
from baidupcs_py.common import constant
from baidupcs_py.common.io import to_decryptio, DecryptIO, READ_SIZE
from baidupcs_py.common.downloader import MeDownloader
from baidupcs_py.common.progress_bar import _progress, progress_task_exists
from baidupcs_py.commands.sifter import Sifter, sift
from baidupcs_py.commands.log import get_logger
from baidupcs_py.commands.display import display_blocked_remotepath

_print = print

from rich import print
from rich.progress import TaskID

logger = get_logger(__name__)

USER_AGENT = "netdisk;2.2.51.6;netdisk;10.0.63;PC;android-android"

DEFAULT_CONCURRENCY = 5
DEFAULT_CHUNK_SIZE = str(1 * constant.OneM)

# This is the threshold of range request setted by Baidu server
MAX_CHUNK_SIZE = 50 * constant.OneM


class DownloadParams(SimpleNamespace):
    concurrency: int = DEFAULT_CONCURRENCY
    chunk_size: str = DEFAULT_CHUNK_SIZE
    quiet: bool = False


DEFAULT_DOWNLOADPARAMS = DownloadParams()


class Downloader(Enum):
    me = "me"
    aget_py = "aget"  # https://github.com/PeterDing/aget
    aget_rs = "ag"  # https://github.com/PeterDing/aget-rs
    aria2 = "aria2c"  # https://github.com/aria2/aria2

    # No use axel. It Can't handle URLs of length over 1024
    # axel = 'axel'  # https://github.com/axel-download-accelerator/axel

    # No use wget. the file url of baidupan only supports `Range` request

    def which(self) -> Optional[str]:
        return shutil.which(self.value)

    def download(
        self,
        url: str,
        localpath: str,
        cookies: Dict[str, Optional[str]],
        downloadparams: DownloadParams = DEFAULT_DOWNLOADPARAMS,
        out_cmd: bool = False,
        encrypt_password: bytes = b"",
    ):
        global DEFAULT_DOWNLOADER
        if not self.which():
            self = DEFAULT_DOWNLOADER

        localpath_tmp = localpath + ".tmp"

        def done_callback(fut: Future):
            err = fut.exception()
            if not err:
                shutil.move(localpath_tmp, localpath)
            else:
                logger.info("`download`: MeDownloader fails: error: %s", err)

        if self == Downloader.me:
            self._me_download(
                url,
                localpath_tmp,
                cookies=cookies,
                downloadparams=downloadparams,
                done_callback=done_callback,
                encrypt_password=encrypt_password,
            )
            return
        elif self == Downloader.aget_py:
            cmd = self._aget_py_cmd(url, localpath_tmp, cookies, downloadparams)
        elif self == Downloader.aget_rs:
            cmd = self._aget_rs_cmd(url, localpath_tmp, cookies, downloadparams)
        elif self == Downloader.aria2:
            cmd = self._aria2_cmd(url, localpath_tmp, cookies, downloadparams)
        else:
            cmd = self._aget_py_cmd(url, localpath_tmp, cookies, downloadparams)

        # Print out command
        if out_cmd:
            _print(" ".join((repr(c) for c in cmd)))
            return

        returncode = self.spawn(cmd, downloadparams.quiet)

        logger.debug("`download`: cmd returncode: %s", returncode)

        if returncode != 0:
            print(
                f"[italic]{self.value}[/italic] fails. return code: [red]{returncode}[/red]"
            )
        else:
            if encrypt_password:
                dio = to_decryptio(open(localpath_tmp, "rb"), encrypt_password)
                if isinstance(dio, DecryptIO):
                    with open(localpath, "wb") as fd:
                        while True:
                            buf = dio.read(READ_SIZE)
                            if not buf:
                                break
                            fd.write(buf)

                    os.remove(localpath_tmp)
                    return
            shutil.move(localpath_tmp, localpath)

    def spawn(self, cmd: List[str], quiet: bool = False):
        child = subprocess.run(cmd, stdout=subprocess.DEVNULL if quiet else None)
        return child.returncode

    def _me_download(
        self,
        url: str,
        localpath: str,
        cookies: Dict[str, Optional[str]],
        downloadparams: DownloadParams = DEFAULT_DOWNLOADPARAMS,
        done_callback: Optional[Callable[[Future], Any]] = None,
        encrypt_password: bytes = b"",
    ):
        headers = {
            "Cookie ": "; ".join(
                [f"{k}={v if v is not None else ''}" for k, v in cookies.items()]
            ),
            "User-Agent": USER_AGENT,
            "Connection": "Keep-Alive",
        }

        task_id: Optional[TaskID] = None
        if not downloadparams.quiet:
            if not _progress.live._started:
                _progress.start()
            task_id = _progress.add_task("MeDownloader", start=False, title=localpath)

        def _wrap_done_callback(fut: Future):
            if task_id is not None:
                _progress.remove_task(task_id)
            if done_callback:
                done_callback(fut)

        def monit_callback(task_id: Optional[TaskID], offset: int):
            if task_id is not None:
                _progress.update(task_id, completed=offset + 1)

        def except_callback(task_id: Optional[TaskID]):
            if task_id is not None and progress_task_exists(task_id):
                _progress.reset(task_id)

        chunk_size_int = human_size_to_int(downloadparams.chunk_size)
        meDownloader = MeDownloader(
            "GET",
            url,
            headers=headers,
            max_workers=downloadparams.concurrency,
            max_chunk_size=chunk_size_int,
            callback=monit_callback,
            encrypt_password=encrypt_password,
        )

        if task_id is not None:
            length = len(meDownloader)
            _progress.update(task_id, total=length)
            _progress.start_task(task_id)

        meDownloader.download(
            Path(localpath),
            task_id=task_id,
            continue_=True,
            done_callback=_wrap_done_callback,
            except_callback=except_callback,
        )

    def _aget_py_cmd(
        self,
        url: str,
        localpath: str,
        cookies: Dict[str, Optional[str]],
        downloadparams: DownloadParams = DEFAULT_DOWNLOADPARAMS,
    ):
        _ck = "Cookie: " + "; ".join(
            [f"{k}={v if v is not None else ''}" for k, v in cookies.items()]
        )
        cmd = [
            self.which(),
            url,
            "-o",
            localpath,
            "-H",
            f"User-Agent: {USER_AGENT}",
            "-H",
            "Connection: Keep-Alive",
            "-H",
            _ck,
            "-s",
            str(downloadparams.concurrency),
            "-k",
            downloadparams.chunk_size,
        ]
        return cmd

    def _aget_rs_cmd(
        self,
        url: str,
        localpath: str,
        cookies: Dict[str, Optional[str]],
        downloadparams: DownloadParams = DEFAULT_DOWNLOADPARAMS,
    ):
        _ck = "Cookie: " + "; ".join(
            [f"{k}={v if v is not None else ''}" for k, v in cookies.items()]
        )
        cmd = [
            self.which(),
            url,
            "-o",
            localpath,
            "-H",
            f"User-Agent: {USER_AGENT}",
            "-H",
            "Connection: Keep-Alive",
            "-H",
            _ck,
            "-s",
            str(downloadparams.concurrency),
            "-k",
            downloadparams.chunk_size,
        ]
        return cmd

    def _aria2_cmd(
        self,
        url: str,
        localpath: str,
        cookies: Dict[str, Optional[str]],
        downloadparams: DownloadParams = DEFAULT_DOWNLOADPARAMS,
    ):
        _ck = "Cookie: " + "; ".join(
            [f"{k}={v if v is not None else ''}" for k, v in cookies.items()]
        )
        directory, filename = os.path.split(localpath)
        cmd = [
            self.which(),
            "-c",
            "--dir",
            directory,
            "-o",
            filename,
            "--header",
            f"User-Agent: {USER_AGENT}",
            "--header",
            "Connection: Keep-Alive",
            "--header",
            _ck,
            "-s",
            str(downloadparams.concurrency),
            "-k",
            downloadparams.chunk_size,
            url,
        ]
        return cmd


DEFAULT_DOWNLOADER = Downloader.me


def download_file(
    api: BaiduPCSApi,
    remotepath: str,
    localdir: str,
    downloader: Downloader = DEFAULT_DOWNLOADER,
    downloadparams: DownloadParams = DEFAULT_DOWNLOADPARAMS,
    out_cmd: bool = False,
    encrypt_password: bytes = b"",
):
    localpath = Path(localdir) / os.path.basename(remotepath)

    # Make sure parent directory existed
    if not localpath.parent.exists():
        localpath.parent.mkdir(parents=True)

    if not out_cmd and localpath.exists():
        print(f"[yellow]{localpath}[/yellow] is ready existed.")
        return

    dlink = api.download_link(remotepath)
    if not dlink:
        display_blocked_remotepath(remotepath)
        return

    if downloader != Downloader.me:
        print(f"[italic blue]Download[/italic blue]: {remotepath} to {localpath}")
    downloader.download(
        dlink,
        str(localpath),
        api.cookies,
        downloadparams=downloadparams,
        out_cmd=out_cmd,
        encrypt_password=encrypt_password,
    )


def download_dir(
    api: BaiduPCSApi,
    remotedir: str,
    localdir: str,
    sifters: List[Sifter] = [],
    recursive: bool = False,
    from_index: int = 0,
    downloader: Downloader = DEFAULT_DOWNLOADER,
    downloadparams=DEFAULT_DOWNLOADPARAMS,
    out_cmd: bool = False,
    encrypt_password: bytes = b"",
):
    remotepaths = api.list(remotedir)
    remotepaths = sift(remotepaths, sifters, recursive=recursive)
    for rp in remotepaths[from_index:]:
        if rp.is_file:
            download_file(
                api,
                rp.path,
                localdir,
                downloader,
                downloadparams=downloadparams,
                out_cmd=out_cmd,
                encrypt_password=encrypt_password,
            )
        else:  # is_dir
            if recursive:
                _localdir = Path(localdir) / os.path.basename(rp.path)
                download_dir(
                    api,
                    rp.path,
                    str(_localdir),
                    sifters=sifters,
                    recursive=recursive,
                    from_index=from_index,
                    downloader=downloader,
                    downloadparams=downloadparams,
                    out_cmd=out_cmd,
                    encrypt_password=encrypt_password,
                )


def download(
    api: BaiduPCSApi,
    remotepaths: List[str],
    localdir: str,
    sifters: List[Sifter] = [],
    recursive: bool = False,
    from_index: int = 0,
    downloader: Downloader = DEFAULT_DOWNLOADER,
    downloadparams: DownloadParams = DEFAULT_DOWNLOADPARAMS,
    out_cmd: bool = False,
    encrypt_password: bytes = b"",
):
    """Download `remotepaths` to the `localdir`

    Args:
        `from_index` (int): The start index of downloading entries from EACH remote directory
    """

    logger.debug(
        "`download`: sifters: %s, recursive: %s, from_index: %s, "
        "downloader: %s, downloadparams: %s, out_cmd: %s, has encrypt_password: %s",
        sifters,
        recursive,
        from_index,
        downloader,
        downloadparams,
        out_cmd,
        bool(encrypt_password),
    )
    logger.debug(
        "`download`: remotepaths should be uniq %s == %s",
        len(remotepaths),
        len(set(remotepaths)),
    )

    assert (
        human_size_to_int(downloadparams.chunk_size) < MAX_CHUNK_SIZE
    ), f"`chunk_size` must be less then {human_size(MAX_CHUNK_SIZE)}"

    for rp in remotepaths:
        if not api.exists(rp):
            print(f"[yellow]WARNING[/yellow]: `{rp}` does not exist.")
            continue

        if api.is_file(rp):
            download_file(
                api,
                rp,
                localdir,
                downloader=downloader,
                downloadparams=downloadparams,
                out_cmd=out_cmd,
                encrypt_password=encrypt_password,
            )
        else:
            _localdir = str(Path(localdir) / os.path.basename(rp))
            download_dir(
                api,
                rp,
                _localdir,
                sifters=sifters,
                recursive=recursive,
                from_index=from_index,
                downloader=downloader,
                downloadparams=downloadparams,
                out_cmd=out_cmd,
                encrypt_password=encrypt_password,
            )

    if downloader == Downloader.me:
        MeDownloader._exit_executor()

    _progress.stop()
