from typing import List

from baidupcs_py.baidupcs import BaiduPCSApi
from baidupcs_py.commands.sifter import Sifter
from baidupcs_py.commands.display import display_files


def list_file(
    api: BaiduPCSApi,
    remotepath: str,
    desc: bool = False,
    name: bool = False,
    time: bool = False,
    size: bool = False,
    recursive: bool = False,
    sifters: List[Sifter] = [],
    highlight: bool = False,
    show_size: bool = False,
    show_date: bool = False,
    show_md5: bool = False,
    show_absolute_path: bool = False,
):
    is_dir = api.is_dir(remotepath)
    if is_dir:
        pcs_files = api.list(remotepath, desc=desc, name=name, time=time, size=size)
    else:
        pcs_files = api.meta(remotepath)

    display_files(
        pcs_files,
        remotepath,
        sifters=sifters,
        highlight=highlight,
        show_size=show_size,
        show_date=show_date,
        show_md5=show_md5,
        show_absolute_path=show_absolute_path,
    )

    if is_dir and recursive:
        for pcs_file in pcs_files:
            if pcs_file.is_dir:
                list_file(
                    api,
                    pcs_file.path,
                    desc=desc,
                    name=name,
                    time=time,
                    size=size,
                    recursive=recursive,
                    sifters=sifters,
                    highlight=highlight,
                    show_size=show_size,
                    show_date=show_date,
                    show_md5=show_md5,
                    show_absolute_path=show_absolute_path,
                )


def list_files(
    api: BaiduPCSApi,
    *remotepaths: str,
    desc: bool = False,
    name: bool = False,
    time: bool = False,
    size: bool = False,
    recursive: bool = False,
    sifters: List[Sifter] = [],
    highlight: bool = False,
    show_size: bool = False,
    show_date: bool = False,
    show_md5: bool = False,
    show_absolute_path: bool = False,
):
    for rp in remotepaths:
        list_file(
            api,
            rp,
            desc=desc,
            name=name,
            time=time,
            size=size,
            recursive=recursive,
            sifters=sifters,
            highlight=highlight,
            show_size=show_size,
            show_date=show_date,
            show_md5=show_md5,
            show_absolute_path=show_absolute_path,
        )
