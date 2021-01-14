from typing import Optional, List, Dict
from types import SimpleNamespace
from enum import Enum
from pathlib import Path
import os
import shutil
import subprocess

from baidupcs_py.baidupcs import BaiduPCSApi
from baidupcs_py.baidupcs import common
from baidupcs_py.commands.sifter import Sifter, sift

from rich import print

USER_AGENT = "netdisk;2.2.51.6;netdisk;10.0.63;PC;android-android"

DEFAULT_CONCURRENCY = 5
DEFAULT_CHUNK_SIZE = str(1 * common.OneM)


class DownloadParams(SimpleNamespace):
    concurrency: int = DEFAULT_CONCURRENCY
    chunk_size: str = DEFAULT_CHUNK_SIZE
    quiet: bool = False


DEFAULT_DOWNLOADPARAMS = DownloadParams()


class Downloader(Enum):
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
    ):
        global DEFAULT_DOWNLOADER
        if not self.which():
            self = DEFAULT_DOWNLOADER

        localpath_tmp = localpath + ".tmp"

        if self == Downloader.aget_py:
            cmd = self._aget_py_cmd(url, localpath_tmp, cookies, downloadparams)
        elif self == Downloader.aget_rs:
            cmd = self._aget_rs_cmd(url, localpath_tmp, cookies, downloadparams)
        elif self == Downloader.aria2:
            cmd = self._aria2_cmd(url, localpath_tmp, cookies, downloadparams)
        else:
            cmd = self._aget_py_cmd(url, localpath_tmp, cookies, downloadparams)

        returncode = self.spawn(cmd, downloadparams.quiet)
        if returncode != 0:
            print(
                f"[italic]{self.value}[/italic] fails. return code: [red]{returncode}[/red]"
            )
        else:
            shutil.move(localpath_tmp, localpath)

    def spawn(self, cmd: List[str], quiet: bool = False):
        child = subprocess.run(cmd, stdout=subprocess.DEVNULL if quiet else None)
        return child.returncode

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


DEFAULT_DOWNLOADER = Downloader.aget_py


def download_file(
    api: BaiduPCSApi,
    remotepath: str,
    localdir: str,
    downloader: Downloader = DEFAULT_DOWNLOADER,
    downloadparams: DownloadParams = DEFAULT_DOWNLOADPARAMS,
):
    localpath = Path(localdir) / os.path.basename(remotepath)

    # Make sure parent directory existed
    if not localpath.parent.exists():
        localpath.parent.mkdir(parents=True)

    if localpath.exists():
        print(f"[yellow]{localpath}[/yellow] is ready existed.")
        return

    dlink = api.download_link(remotepath)

    print(f"[italic blue]Download[/italic blue]: {remotepath} to {localpath}")
    downloader.download(
        dlink, str(localpath), api.cookies, downloadparams=downloadparams
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
):
    remotepaths = api.list(remotedir)
    remotepaths = sift(remotepaths, sifters)
    for rp in remotepaths[from_index:]:
        if rp.is_file:
            download_file(
                api, rp.path, localdir, downloader, downloadparams=downloadparams
            )
        else:  # is_dir
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
):
    """Download `remotepaths` to the `localdir`

    Args:
        `from_index` (int): The start index of downloading entries from EACH remote directory
    """

    remotepaths = sift(remotepaths, sifters)
    for rp in remotepaths:
        if not api.exists(rp):
            print(f"[yellow]WARNING[/yellow]: `{rp}` does not exist.")
            continue

        if api.is_file(rp):
            download_file(
                api, rp, localdir, downloader=downloader, downloadparams=downloadparams
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
            )
