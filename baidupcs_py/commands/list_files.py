from typing import Optional, List

from baidupcs_py.baidupcs import BaiduPCSApi
from baidupcs_py.baidupcs.inner import PcsRapidUploadInfo
from baidupcs_py.common.localstorage import save_rapid_upload_info
from baidupcs_py.commands.sifter import Sifter, sift
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
):
    is_dir = api.is_dir(remotepath)
    if is_dir:
        pcs_files = api.list(remotepath, desc=desc, name=name, time=time, size=size)
    else:
        pcs_files = api.meta(remotepath)

    pcs_files = sift(pcs_files, sifters)
    if not pcs_files:
        return

    for i in range(len(pcs_files)):
        pcs_file = pcs_files[i]
        dl_link = None
        if show_dl_link:
            dl_link = api.download_link(pcs_file.path)

        rpinfo = None
        if show_hash_link:
            rpinfo = api.rapid_upload_info(pcs_file.path, check=check_md5)
            if rapiduploadinfo_file and rpinfo:
                save_rapid_upload_info(
                    rapiduploadinfo_file,
                    rpinfo.slice_md5,
                    rpinfo.content_md5,
                    rpinfo.content_crc32,
                    rpinfo.content_length,
                    remotepath=pcs_file.path,
                    user_id=user_id,
                    user_name=user_name,
                )

        pcs_files[i] = pcs_file._replace(rapid_upload_info=rpinfo, dl_link=dl_link)

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
        )
