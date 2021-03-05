from typing import Optional, List, Tuple

from threading import Semaphore
from concurrent.futures import ThreadPoolExecutor, as_completed

from baidupcs_py.baidupcs import BaiduPCSApi
from baidupcs_py.baidupcs.inner import PcsFile, PcsRapidUploadInfo
from baidupcs_py.common.concurrent import sure_release
from baidupcs_py.common.localstorage import save_rapid_upload_info
from baidupcs_py.commands.log import get_logger
from baidupcs_py.commands.sifter import Sifter, sift
from baidupcs_py.commands.display import display_files

from rich import print

logger = get_logger(__name__)

DEFAULT_MAX_WORKERS = 10


def _get_download_link_and_rapid_upload_info(
    api: BaiduPCSApi,
    pcs_file: PcsFile,
    show_dl_link: bool = False,
    show_hash_link: bool = False,
    check_md5: bool = True,
) -> Tuple[Optional[str], Optional[PcsRapidUploadInfo]]:
    dl_link = None
    if show_dl_link:
        dl_link = api.download_link(pcs_file.path)

    rpinfo = None
    if show_hash_link:
        rpinfo = api.rapid_upload_info(pcs_file.path, check=check_md5)

    return dl_link, rpinfo


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
    rapiduploadinfo_file: Optional[str] = None,
    user_id: Optional[int] = None,
    user_name: Optional[str] = None,
    show_size: bool = False,
    show_date: bool = False,
    show_md5: bool = False,
    show_absolute_path: bool = False,
    show_dl_link: bool = False,
    show_hash_link: bool = False,
    hash_link_protocol: str = PcsRapidUploadInfo.default_hash_link_protocol(),
    check_md5: bool = True,
    csv: bool = False,
    only_dl_link: bool = False,
    only_hash_link: bool = False,
):
    is_dir = api.is_dir(remotepath)
    if is_dir:
        pcs_files = api.list(remotepath, desc=desc, name=name, time=time, size=size)
    else:
        pcs_files = api.meta(remotepath)

    pcs_files = sift(pcs_files, sifters, recursive=recursive)
    if not pcs_files:
        return

    if show_dl_link or show_hash_link:
        # Concurrently request rapiduploadinfo
        max_workers = DEFAULT_MAX_WORKERS
        semaphore = Semaphore(max_workers)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futs = {}
            for i in range(len(pcs_files)):
                if pcs_files[i].is_dir:
                    continue

                semaphore.acquire()
                fut = executor.submit(
                    sure_release,
                    semaphore,
                    _get_download_link_and_rapid_upload_info,
                    api,
                    pcs_files[i],
                    show_dl_link=show_dl_link,
                    show_hash_link=show_hash_link,
                    check_md5=check_md5,
                )
                futs[fut] = i

            for fut in as_completed(futs):
                i = futs[fut]
                e = fut.exception()
                if e is None:
                    dl_link, rpinfo = fut.result()
                    if rapiduploadinfo_file and rpinfo:
                        save_rapid_upload_info(
                            rapiduploadinfo_file,
                            rpinfo.slice_md5,
                            rpinfo.content_md5,
                            rpinfo.content_crc32,
                            rpinfo.content_length,
                            remotepath=pcs_files[i].path,
                            user_id=user_id,
                            user_name=user_name,
                        )
                    pcs_files[i] = pcs_files[i]._replace(
                        dl_link=dl_link, rapid_upload_info=rpinfo
                    )
                    if only_dl_link and dl_link:
                        print(dl_link)
                    if only_hash_link and rpinfo:
                        hash_link = getattr(rpinfo, hash_link_protocol)()
                        print(hash_link)
                else:
                    logger.error(
                        "`list_file`: `_get_download_link_and_rapid_upload_info` error: %s",
                        e,
                    )

    if not only_dl_link and not only_hash_link:
        display_files(
            pcs_files,
            remotepath,
            sifters=sifters,
            highlight=highlight,
            show_size=show_size,
            show_date=show_date,
            show_md5=show_md5,
            show_absolute_path=show_absolute_path,
            show_dl_link=show_dl_link,
            show_hash_link=show_hash_link,
            hash_link_protocol=hash_link_protocol,
            csv=csv,
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
                    rapiduploadinfo_file=rapiduploadinfo_file,
                    user_id=user_id,
                    user_name=user_name,
                    show_size=show_size,
                    show_date=show_date,
                    show_md5=show_md5,
                    show_absolute_path=show_absolute_path,
                    show_dl_link=show_dl_link,
                    show_hash_link=show_hash_link,
                    hash_link_protocol=hash_link_protocol,
                    check_md5=check_md5,
                    csv=csv,
                    only_dl_link=only_dl_link,
                    only_hash_link=only_hash_link,
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
    rapiduploadinfo_file: Optional[str] = None,
    user_id: Optional[int] = None,
    user_name: Optional[str] = None,
    show_size: bool = False,
    show_date: bool = False,
    show_md5: bool = False,
    show_absolute_path: bool = False,
    show_dl_link: bool = False,
    show_hash_link: bool = False,
    hash_link_protocol: str = PcsRapidUploadInfo.default_hash_link_protocol(),
    check_md5: bool = True,
    csv: bool = False,
    only_dl_link: bool = False,
    only_hash_link: bool = False,
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
            rapiduploadinfo_file=rapiduploadinfo_file,
            user_id=user_id,
            user_name=user_name,
            show_size=show_size,
            show_date=show_date,
            show_md5=show_md5,
            show_absolute_path=show_absolute_path,
            show_dl_link=show_dl_link,
            show_hash_link=show_hash_link,
            hash_link_protocol=hash_link_protocol,
            check_md5=check_md5,
            csv=csv,
            only_dl_link=only_dl_link,
            only_hash_link=only_hash_link,
        )
