from typing import Optional, List, Dict
from enum import Enum
from pathlib import Path
import os
import shutil
import subprocess

from baidupcs_py.baidupcs import BaiduPCSApi
from baidupcs_py.commands.sifter import Sifter, sift
from baidupcs_py.commands.download import USER_AGENT
from baidupcs_py.commands.errors import CommandError

from rich import print


MEDIA_EXTS = set(
    [
        ".wma",
        ".wav",
        ".mp3",
        ".aac",
        ".ra",
        ".ram",
        ".mp2",
        ".ogg",
        ".aif",
        ".mpega",
        ".amr",
        ".mid",
        ".midi",
        ".m4a",
        ".m4v",
        ".wmv",
        ".rmvb",
        ".mpeg4",
        ".mpeg2",
        ".flv",
        ".avi",
        ".3gp",
        ".mpga",
        ".qt",
        ".rm",
        ".wmz",
        ".wmd",
        ".wvx",
        ".wmx",
        ".wm",
        ".swf",
        ".mpg",
        ".mp4",
        ".mkv",
        ".mpeg",
        ".mov",
        ".mdf",
        ".iso",
        ".asf",
        ".vob",
    ]
)


def _with_media_ext(path: str) -> bool:
    ext = os.path.splitext(path)[-1]
    if ext in MEDIA_EXTS:
        return True
    else:
        return False


class Player(Enum):
    mpv = "mpv"  # https://mpv.io

    def which(self) -> Optional[str]:
        return shutil.which(self.value)

    def play(
        self,
        url: str,
        cookies: Dict[str, Optional[str]],
        m3u8: bool = False,
        quiet: bool = False,
    ):
        global DEFAULT_PLAYER
        if not self.which():
            print(
                f"[yellow]No player {self.name}[/yellow], using default player: {DEFAULT_PLAYER.name}"
            )
            self = DEFAULT_PLAYER
        if not self.which():
            raise CommandError(f"No player: {self.name}")

        if self == Player.mpv:
            cmd = self._mpv_cmd(url, cookies, m3u8=m3u8, quiet=quiet)
        else:
            cmd = self._mpv_cmd(url, cookies, m3u8=m3u8, quiet=quiet)

        returncode = self.spawn(cmd)
        if returncode != 0:
            print(
                f"[italic]{self.value}[/italic] fails. return code: [red]{returncode}[/red]"
            )

    def spawn(self, cmd: List[str], quiet: bool = False):
        child = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL if quiet else None,
        )
        return child.returncode

    def _mpv_cmd(
        self,
        url: str,
        cookies: Dict[str, Optional[str]],
        m3u8: bool = False,
        quiet: bool = False,
    ):
        _ck = "Cookie: " + "; ".join(
            [f"{k}={v if v is not None else ''}" for k, v in cookies.items()]
        )
        cmd = [
            self.which(),
            url,
            "--no-ytdl",
            "--http-header-fields="
            f'"User-Agent: {USER_AGENT}","{_ck}","Connection: Keep-Alive"',
        ]
        if m3u8:
            cmd.append(
                "--stream-lavf-o-append="
                "protocol_whitelist=file,http,https,tcp,tls,crypto,hls,applehttp"
            )
        if quiet:
            cmd.append("--really-quiet")
        return cmd


DEFAULT_PLAYER = Player.mpv
DEFAULT_TEMP_M3U8 = str(Path("~").expanduser() / ".baidupcs-py" / "recent.m3u8")


def play_file(
    api: BaiduPCSApi,
    remotepath: str,
    player: Player = DEFAULT_PLAYER,
    m3u8: bool = False,
    quiet: bool = False,
):
    if not _with_media_ext(remotepath):
        return

    print(f"[italic blue]Play[/italic blue]: {remotepath}" + " (m3u8)" if m3u8 else "")

    if m3u8:
        m3u8_cn = api.m3u8_stream(remotepath)
        with open(DEFAULT_TEMP_M3U8, "w") as fd:
            fd.write(m3u8_cn)
        url = DEFAULT_TEMP_M3U8
    else:
        url = api.download_link(remotepath)

    player.play(url, api.cookies, m3u8=m3u8, quiet=quiet)


def play_dir(
    api: BaiduPCSApi,
    remotedir: str,
    sifters: List[Sifter] = [],
    recursive: bool = False,
    from_index: int = 0,
    player: Player = DEFAULT_PLAYER,
    m3u8: bool = False,
    quiet: bool = False,
):
    remotepaths = api.list(remotedir)
    remotepaths = sift(remotepaths, sifters)
    for rp in remotepaths[from_index:]:
        if rp.is_file:
            play_file(api, rp.path, player, quiet=quiet)
        else:  # is_dir
            play_dir(
                api,
                rp.path,
                sifters=sifters,
                recursive=recursive,
                from_index=from_index,
                player=player,
                quiet=quiet,
            )


def play(
    api: BaiduPCSApi,
    remotepaths: List[str],
    sifters: List[Sifter] = [],
    recursive: bool = False,
    from_index: int = 0,
    player: Player = DEFAULT_PLAYER,
    m3u8: bool = False,
    quiet: bool = False,
):
    """Play media file in `remotepaths`

    Args:
        `from_index` (int): The start index of playing entries from EACH remote directory
    """

    for rp in remotepaths:

        if not api.exists(rp):
            print(f"[yellow]WARNING[/yellow]: `{rp}` does not exist.")
            continue

        if api.is_file(rp):
            play_file(api, rp, player=player, m3u8=m3u8, quiet=quiet)
        else:
            play_dir(
                api,
                rp,
                sifters=sifters,
                recursive=recursive,
                from_index=from_index,
                player=player,
                m3u8=m3u8,
                quiet=quiet,
            )
