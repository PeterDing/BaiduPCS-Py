from typing import Optional, List, Dict
from enum import Enum
from pathlib import Path
import os
import shutil
import subprocess
import random
import time

from baidupcs_py.baidupcs import BaiduPCSApi
from baidupcs_py.commands.sifter import Sifter, sift
from baidupcs_py.commands.download import USER_AGENT
from baidupcs_py.commands.errors import CommandError

_print = print

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
    ext = os.path.splitext(path)[-1].lower()
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
        player_params: List[str] = [],
        out_cmd: bool = False,
        use_local_server: bool = False,
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
            cmd = self._mpv_cmd(
                url,
                cookies,
                m3u8=m3u8,
                quiet=quiet,
                player_params=player_params,
                use_local_server=use_local_server,
            )
        else:
            cmd = self._mpv_cmd(
                url,
                cookies,
                m3u8=m3u8,
                quiet=quiet,
                player_params=player_params,
                use_local_server=use_local_server,
            )

        # Print out command
        if out_cmd:
            _print(" ".join((repr(c) for c in cmd)))
            return

        returncode = self.spawn(cmd)
        if returncode != 0:
            print(
                f"[italic]{self.value}[/italic] fails. return code: [red]{returncode}[/red]"
            )

    def spawn(
        self,
        cmd: List[str],
        quiet: bool = False,
        player_params: List[str] = [],
    ):
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
        player_params: List[str] = [],
        use_local_server: bool = False,
    ):
        if use_local_server:
            cmd = [self.which(), url, *player_params]
        else:
            _ck = "Cookie: " + "; ".join(
                [f"{k}={v if v is not None else ''}" for k, v in cookies.items()]
            )
            cmd = [
                self.which(),
                url,
                "--no-ytdl",
                "--http-header-fields="
                f'"User-Agent: {USER_AGENT}","{_ck}","Connection: Keep-Alive"',
                *player_params,
            ]
        if not use_local_server and m3u8:
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
    player_params: List[str] = [],
    m3u8: bool = False,
    quiet: bool = False,
    ignore_ext: bool = False,
    out_cmd: bool = False,
    local_server: str = "",
):
    if not ignore_ext and not _with_media_ext(remotepath):
        return

    print(f"[italic blue]Play[/italic blue]: {remotepath} {'(m3u8)' if m3u8 else ''}")

    if m3u8:
        m3u8_cn = api.m3u8_stream(remotepath)
        with open(DEFAULT_TEMP_M3U8, "w") as fd:
            fd.write(m3u8_cn)
        url = DEFAULT_TEMP_M3U8

    use_local_server = bool(local_server)
    if use_local_server:
        url = f"{local_server}{remotepath}"
        print("url:", url)
    else:
        url = api.download_link(remotepath)

    player.play(
        url,
        api.cookies,
        m3u8=m3u8,
        quiet=quiet,
        player_params=player_params,
        out_cmd=out_cmd,
        use_local_server=use_local_server,
    )


def play_dir(
    api: BaiduPCSApi,
    remotedir: str,
    sifters: List[Sifter] = [],
    recursive: bool = False,
    from_index: int = 0,
    player: Player = DEFAULT_PLAYER,
    player_params: List[str] = [],
    m3u8: bool = False,
    quiet: bool = False,
    shuffle: bool = False,
    ignore_ext: bool = False,
    out_cmd: bool = False,
    local_server: str = "",
):
    remotepaths = api.list(remotedir)
    remotepaths = sift(remotepaths, sifters)

    if shuffle:
        rg = random.Random(time.time())
        rg.shuffle(remotepaths)

    for rp in remotepaths[from_index:]:
        if rp.is_file:
            play_file(
                api,
                rp.path,
                player,
                player_params=player_params,
                m3u8=m3u8,
                quiet=quiet,
                ignore_ext=ignore_ext,
                out_cmd=out_cmd,
                local_server=local_server,
            )
        else:  # is_dir
            play_dir(
                api,
                rp.path,
                sifters=sifters,
                recursive=recursive,
                from_index=from_index,
                player=player,
                player_params=player_params,
                m3u8=m3u8,
                quiet=quiet,
                shuffle=shuffle,
                ignore_ext=ignore_ext,
                out_cmd=out_cmd,
                local_server=local_server,
            )


def play(
    api: BaiduPCSApi,
    remotepaths: List[str],
    sifters: List[Sifter] = [],
    recursive: bool = False,
    from_index: int = 0,
    player: Player = DEFAULT_PLAYER,
    player_params: List[str] = [],
    m3u8: bool = False,
    quiet: bool = False,
    shuffle: bool = False,
    ignore_ext: bool = False,
    out_cmd: bool = False,
    local_server: str = "",
):
    """Play media file in `remotepaths`

    Args:
        `from_index` (int): The start index of playing entries from EACH remote directory
    """

    if shuffle:
        rg = random.Random(time.time())
        rg.shuffle(remotepaths)

    for rp in remotepaths:

        if not api.exists(rp):
            print(f"[yellow]WARNING[/yellow]: `{rp}` does not exist.")
            continue

        if api.is_file(rp):
            play_file(
                api,
                rp,
                player=player,
                player_params=player_params,
                m3u8=m3u8,
                quiet=quiet,
                ignore_ext=ignore_ext,
                out_cmd=out_cmd,
                local_server=local_server,
            )
        else:
            play_dir(
                api,
                rp,
                sifters=sifters,
                recursive=recursive,
                from_index=from_index,
                player=player,
                player_params=player_params,
                m3u8=m3u8,
                quiet=quiet,
                shuffle=shuffle,
                ignore_ext=ignore_ext,
                out_cmd=out_cmd,
                local_server=local_server,
            )
