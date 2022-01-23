from typing import List

from baidupcs_py.baidupcs import BaiduPCSApi
from baidupcs_py.commands.log import get_logger
from baidupcs_py.commands.sifter import Sifter, sift
from baidupcs_py.utils import human_size

from rich.console import Console

logger = get_logger(__name__)

DEFAULT_MAX_WORKERS = 10


def du(
    api: BaiduPCSApi,
    remotepath: str,
    recursive: bool = False,
    sifters: List[Sifter] = [],
    highlight: bool = False,
) -> int:
    is_dir = api.is_dir(remotepath)
    if is_dir:
        pcs_files = api.list(remotepath)
    else:
        pcs_files = api.meta(remotepath)

    pcs_files = sift(pcs_files, sifters, recursive=recursive)
    if not pcs_files:
        return 0

    usage = 0
    for pcs_file in pcs_files:
        if pcs_file.is_dir:
            if recursive:
                usage += du(
                    api,
                    pcs_file.path,
                    recursive=recursive,
                    sifters=sifters,
                    highlight=highlight,
                )
        else:
            usage += pcs_file.size or 0

    return usage


def disk_usage(
    api: BaiduPCSApi,
    *remotepaths: str,
    recursive: bool = False,
    sifters: List[Sifter] = [],
):
    console = Console()
    with console.status("") as status:
        for rp in remotepaths:
            status.update(status=f"[b green]Request remote[/b green]: {rp}")
            usage = du(api, rp, recursive=recursive, sifters=sifters)
            console.print(f"{human_size(usage)}\t{usage}\t{rp}")
