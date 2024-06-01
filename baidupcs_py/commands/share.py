from typing import Optional, List, Dict, Set
import re
import os
from pathlib import Path, PurePosixPath
from collections import deque

from baidupcs_py.baidupcs import BaiduPCSApi, PcsSharedPath, BaiduPCSError
from baidupcs_py.commands.display import display_shared_links, display_shared_paths

from rich import print


SHARED_URL_PREFIX = "https://pan.baidu.com/s/"


def _unify_shared_url(url: str) -> str:
    """Unify input shared url"""

    # For Standard url
    temp = r"pan\.baidu\.com/s/(.+?)(\?|$)"
    m = re.search(temp, url)
    if m:
        return SHARED_URL_PREFIX + m.group(1)

    # For surl url
    temp = r"baidu\.com.+?\?surl=(.+?)(\?|$)"
    m = re.search(temp, url)
    if m:
        return SHARED_URL_PREFIX + "1" + m.group(1)

    raise ValueError(f"The shared url is not a valid url. {url}")


def share_files(api: BaiduPCSApi, *remotepaths: str, password: str, period: int = 0):
    shared_link = api.share(*remotepaths, password=password, period=period)
    display_shared_links(shared_link)


def list_shared(api: BaiduPCSApi, show_all=True):
    page = 1
    while True:
        shared_links = api.list_shared(page=page)
        if not shared_links:
            break

        page += 1

        for sl in shared_links:
            if sl.has_password():
                assert sl.share_id
                pwd = api.shared_password(sl.share_id)
                sl = sl._replace(password=pwd)

            if show_all or sl.available():
                display_shared_links(sl)


def cancel_shared(api: BaiduPCSApi, *share_ids: int):
    api.cancel_shared(*share_ids)


def save_shared(
    api: BaiduPCSApi,
    shared_url: str,
    remotedir: str,
    password: Optional[str] = None,
    path_prefix: str|None = None,
    show_vcode: bool = True,
):
    assert remotedir.startswith("/"), "`remotedir` must be an absolute path"

    shared_url = _unify_shared_url(shared_url)

    # Vertify with password
    if password:
        api.access_shared(shared_url, password, show_vcode=show_vcode)

    shared_paths = deque(api.shared_paths(shared_url))

    # Record the remotedir of each shared_path
    _remotedirs: Dict[PcsSharedPath, str] = {}
    for sp in shared_paths:
        _remotedirs[sp] = remotedir

    _dir_exists: Set[str] = set()

    while shared_paths:
        shared_path = shared_paths.popleft()
        rd = _remotedirs[shared_path]
        if path_prefix:
            real_path = shared_path.path
            if shared_path.path.startswith("/sharelink"):
                # delete "/sharelinkxxxxxx
                real_path = shared_path.path[shared_path.path.find("/", 1):]
            if shared_path.is_dir:
                if real_path.startswith(path_prefix):
                    pass
                elif path_prefix.startswith(real_path):
                    sub_paths = list_all_sub_paths(api, shared_path.path, shared_path.uk, shared_path.share_id, shared_path.bdstoken)
                    rd = (Path(rd) / os.path.basename(shared_path.path)).as_posix()
                    for sp in sub_paths:
                        _remotedirs[sp] = rd
                    shared_paths.extendleft(sub_paths[::-1])
                    continue
                else:
                    continue
            else:
                if not real_path.startswith(path_prefix):
                    continue

        # Make sure remote dir exists
        if rd not in _dir_exists:
            if not api.exists(rd):
                api.makedir(rd)
            _dir_exists.add(rd)

        # Ignore existed file
        if shared_path.is_file and remotepath_exists(api, PurePosixPath(shared_path.path).name, rd):
            print(f"[yellow]WARNING[/]: {shared_path.path} has be in {rd}")
            continue

        uk, share_id, bdstoken = (
            shared_path.uk,
            shared_path.share_id,
            shared_path.bdstoken,
        )
        assert uk
        assert share_id
        assert bdstoken

        try:
            api.transfer_shared_paths(rd, [shared_path.fs_id], uk, share_id, bdstoken, shared_url)
            print(f"save: {shared_path.path} to {rd}")
            continue
        except BaiduPCSError as err:
            if err.error_code == 12:  # 12: "文件已经存在"
                print(f"[yellow]WARNING[/]: error_code: {err.error_code}, {shared_path.path} has be in {rd}")
            elif err.error_code == -32:  # -32: "剩余空间不足，无法转存",
                raise err
            elif err.error_code in (
                -33,  # -33: "一次支持操作999个，减点试试吧"
                4,  # 4: "share transfer pcs error"
                130,  # "转存文件数超限"
                120,  # "转存文件数超限"
            ):
                print(
                    f"[yellow]WARNING[/]: error_code: {err.error_code}, {shared_path.path} "
                    "has more items and need to transfer one by one"
                )
            else:
                raise err

        if shared_path.is_dir:
            # Take all sub paths
            sub_paths = list_all_sub_paths(api, shared_path.path, uk, share_id, bdstoken)

            rd = (Path(rd) / os.path.basename(shared_path.path)).as_posix()
            for sp in sub_paths:
                _remotedirs[sp] = rd
            shared_paths.extendleft(sub_paths[::-1])


def list_all_sub_paths(
    api: BaiduPCSApi,
    sharedpath: str,
    uk: int,
    share_id: int,
    bdstoken: str,
) -> List[PcsSharedPath]:
    sub_paths = []
    page = 1
    size = 100
    while True:
        sps = api.list_shared_paths(sharedpath, uk, share_id, bdstoken, page=page, size=size)
        sub_paths += sps
        if len(sps) < 100:
            break
        page += 1
    return sub_paths


def list_shared_paths(
    api: BaiduPCSApi,
    shared_url: str,
    password: Optional[str] = None,
    show_vcode: bool = True,
):
    shared_url = _unify_shared_url(shared_url)

    # Vertify with password
    if password:
        api.access_shared(shared_url, password, show_vcode=show_vcode)

    all_shared_paths: List[PcsSharedPath] = []

    shared_paths = deque(api.shared_paths(shared_url))
    all_shared_paths += shared_paths

    while shared_paths:
        shared_path = shared_paths.popleft()

        uk, share_id, bdstoken = (
            shared_path.uk,
            shared_path.share_id,
            shared_path.bdstoken,
        )
        assert uk
        assert share_id
        assert bdstoken

        if shared_path.is_dir:
            # Take all sub paths
            sub_paths = list_all_sub_paths(api, shared_path.path, uk, share_id, bdstoken)
            all_shared_paths += sub_paths
            shared_paths.extendleft(sub_paths[::-1])

    display_shared_paths(*all_shared_paths)


def remotepath_exists(api: BaiduPCSApi, name: str, rd: str, _cache: Dict[str, Set[str]] = {}) -> bool:
    names = _cache.get(rd)
    if not names:
        names = set([PurePosixPath(sp.path).name for sp in api.list(rd)])
        _cache[rd] = names
    return name in names
