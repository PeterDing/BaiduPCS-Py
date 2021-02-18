from typing import List, Tuple, Union, Any
from pathlib import Path
from threading import Semaphore
from concurrent.futures import ThreadPoolExecutor, as_completed

from baidupcs_py.baidupcs import BaiduPCSApi, PcsFile, FromTo
from baidupcs_py.common.path import walk, join_path
from baidupcs_py.common.crypto import calu_file_md5
from baidupcs_py.common.concurrent import sure_release
from baidupcs_py.common.constant import CPU_NUM
from baidupcs_py.common.io import EncryptType
from baidupcs_py.commands.upload import upload as _upload, DEFAULT_SLICE_SIZE

from rich import print


def recursive_list(api: BaiduPCSApi, remotedir: Union[str, PcsFile]) -> List[PcsFile]:
    if isinstance(remotedir, PcsFile):
        remotedir = remotedir.path

    pcs_files = []
    for pcs_file in api.list(remotedir):
        if pcs_file.is_file:
            pcs_files.append(pcs_file)
        else:
            pcs_files.extend(recursive_list(api, pcs_file.path))
    return pcs_files


def check_file_md5(localpath: str, pcs_file: PcsFile) -> bool:
    local_file_md5 = calu_file_md5(localpath)
    if local_file_md5 == pcs_file.md5:
        return True
    else:
        return False


def sync(
    api: BaiduPCSApi,
    localdir: str,
    remotedir: str,
    encrypt_password: bytes = b"",
    encrypt_type: EncryptType = EncryptType.No,
    max_workers: int = CPU_NUM,
    slice_size: int = DEFAULT_SLICE_SIZE,
    show_progress: bool = True,
):
    localdir = Path(localdir).as_posix()
    remotedir = Path(remotedir).as_posix()

    is_file = api.is_file(remotedir)
    assert not is_file, "remotedir must be a directory"

    if not api.exists(remotedir):
        all_pcs_files = {}
    else:
        all_pcs_files = {
            pcs_file.path[len(remotedir) + 1 :]: pcs_file
            for pcs_file in recursive_list(api, remotedir)
        }

    fts: List[FromTo] = []
    check_list: List[Tuple[str, PcsFile]] = []
    all_localpaths = set()
    for localpath in walk(localdir):
        path = localpath[len(localdir) + 1 :]
        all_localpaths.add(path)

        if path not in all_pcs_files:
            fts.append(FromTo(localpath, join_path(remotedir, path)))
        else:
            check_list.append((localpath, all_pcs_files[path]))

    # Compare localpath content md5 with remotepath content md5
    semaphore = Semaphore(max_workers)
    with ThreadPoolExecutor(max_workers=CPU_NUM) as executor:
        tasks = {}
        for lp, pf in check_list:
            semaphore.acquire()
            fut = executor.submit(sure_release, semaphore, check_file_md5, lp, pf)
            tasks[fut] = (lp, pf)

        for fut in as_completed(tasks):
            is_equal = fut.result()
            lp, pf = tasks[fut]
            if not is_equal:
                fts.append(FromTo(lp, pf.path))

    _upload(
        api,
        fts,
        encrypt_password=encrypt_password,
        encrypt_type=encrypt_type,
        max_workers=max_workers,
        slice_size=slice_size,
        ignore_existing=False,
        show_progress=show_progress,
    )

    to_deletes = []
    for rp in all_pcs_files.keys():
        if rp not in all_localpaths:
            to_deletes.append(all_pcs_files[rp].path)

    if to_deletes:
        api.remove(*to_deletes)
        print(f"Delete: [i]{len(to_deletes)}[/i] remote paths")
