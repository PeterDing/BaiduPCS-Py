from baidupcs_py.baidupcs import BaiduPCSApi
from baidupcs_py.commands.display import display_files, display_from_to


def makedir(api: BaiduPCSApi, *remotedirs: str, show: bool = False):
    pcs_files = []
    for d in remotedirs:
        pcs_file = api.makedir(d)
        pcs_files.append(pcs_file)

    if show:
        display_files(pcs_files, "/", show_absolute_path=True)


def move(api: BaiduPCSApi, *remotepaths: str, show: bool = False):
    from_to_list = api.move(*remotepaths)

    if show:
        display_from_to(*from_to_list)


def rename(api: BaiduPCSApi, source: str, dest: str, show: bool = False):
    from_to_list = api.rename(source, dest)

    if show:
        display_from_to(from_to_list)


def copy(api: BaiduPCSApi, *remotepaths: str, show: bool = False):
    from_to_list = api.copy(*remotepaths)

    if show:
        display_from_to(*from_to_list)


def remove(api: BaiduPCSApi, *remotepaths: str):
    api.remove(*remotepaths)
