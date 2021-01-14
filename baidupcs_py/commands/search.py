from typing import Optional, List

from baidupcs_py.baidupcs import BaiduPCSApi
from baidupcs_py.commands.display import display_files
from baidupcs_py.commands.sifter import Sifter, IncludeSifter


def search(
    api: BaiduPCSApi,
    keyword: str,
    remotedir: str = "/",
    recursive: bool = False,
    sifters: Optional[List[Sifter]] = None,
    highlight: bool = False,
    show_size: bool = False,
    show_date: bool = False,
    show_md5: bool = False,
):
    pcs_files = api.search(keyword, remotedir, recursive=recursive)

    sifters = [*(sifters or []), IncludeSifter(keyword)]
    display_files(
        pcs_files,
        remotedir,
        sifters=sifters,
        highlight=highlight,
        show_size=show_size,
        show_date=show_date,
        show_md5=show_md5,
        show_absolute_path=True,
    )
