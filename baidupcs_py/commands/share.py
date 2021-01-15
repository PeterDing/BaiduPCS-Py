from typing import Optional, Dict, Set
import os
from pathlib import Path
from collections import deque

from baidupcs_py.baidupcs import BaiduPCSApi, PcsSharedPath, BaiduPCSError
from baidupcs_py.commands.display import display_shared_links

from rich import print


def share_files(api: BaiduPCSApi, *remotepaths: str, password: Optional[str] = None):
    shared_link = api.share(*remotepaths, password=password)
    display_shared_links(shared_link)


def list_shared(api: BaiduPCSApi, page: int = 1, show_all=True):
    _shared_links = api.list_shared(page=page)
    if not _shared_links:
        return

    shared_links = []
    for sl in _shared_links:
        if sl.has_password():
            assert sl.share_id
            pwd = api.shared_password(sl.share_id)
            sl = sl._replace(password=pwd)

        if show_all:
            shared_links.append(sl)
            continue

        if sl.available():
            shared_links.append(sl)
    display_shared_links(*shared_links)


def cancel_shared(api: BaiduPCSApi, *share_ids: int):
    api.cancel_shared(*share_ids)


def save_shared(
    api: BaiduPCSApi,
    shared_url: str,
    remotedir: str,
    password=Optional[str],
    show_vcode: bool = True,
):
    assert remotedir.startswith("/"), "`remotedir` must be an absolute path"

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
        uk, share_id, bdstoken = (
            shared_path.uk,
            shared_path.share_id,
            shared_path.bdstoken,
        )
        assert uk
        assert share_id
        assert bdstoken

        rd = _remotedirs[shared_path]
        if rd not in _dir_exists and not api.exists(rd):
            api.makedir(rd)
            _dir_exists.add(rd)

        # rd = (Path(_remotedirs[shared_path]) / os.path.basename(shared_path.path)).as_posix()
        try:
            api.transfer_shared_paths(
                rd, [shared_path.fs_id], uk, share_id, bdstoken, shared_url
            )
            print(f"save: {shared_path.path} to {rd}")
            continue
        except BaiduPCSError as err:
            if err.error_code not in (12, -33):
                raise err

            if err.error_code == 12:  # -33: '一次支持操作999个，减点试试吧'
                print(f"[yellow]WARNING[/]: {shared_path.path} has be in {rd}")
            if err.error_code == -33:  # -33: '一次支持操作999个，减点试试吧'
                print(
                    f"[yellow]WARNING[/]: {shared_path.path} "
                    "has more items and need to transfer one by one"
                )

        sub_paths = api.list_shared_paths(shared_path.path, uk, share_id, bdstoken)
        rd = (Path(rd) / os.path.basename(shared_path.path)).as_posix()
        for sp in sub_paths:
            _remotedirs[sp] = rd
        shared_paths.extendleft(sub_paths[::-1])
