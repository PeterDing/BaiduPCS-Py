from typing import Optional, List, Dict, Any

from threading import Semaphore
from concurrent.futures import ThreadPoolExecutor, as_completed

from base64 import b64decode

from baidupcs_py.baidupcs import BaiduPCSApi
from baidupcs_py.baidupcs.inner import PcsRapidUploadInfo
from baidupcs_py.common.constant import CPU_NUM
from baidupcs_py.common.concurrent import sure_release
from baidupcs_py.common.localstorage import RapidUploadInfo
from baidupcs_py.common.path import join_path
from baidupcs_py.common.localstorage import save_rapid_upload_info
from baidupcs_py.commands.display import (
    display_rapid_upload_links,
    display_rapid_upload_infos,
)

from rich import print


def _display(
    rows: List[Dict[str, Any]],
    hash_link_protocol: str = PcsRapidUploadInfo.default_hash_link_protocol(),
    show_all: bool = False,
    only_hash_link: bool = False,
):
    if show_all and not only_hash_link:
        display_rapid_upload_infos(rows)
    else:
        display_rapid_upload_links(
            rows, hash_link_protocol=hash_link_protocol, only_hash_link=only_hash_link
        )


def rapid_upload_list(
    rapiduploadinfo_file: str,
    ids: List[int] = [],
    filename: bool = False,
    time: bool = False,
    size: bool = False,
    localpath: bool = False,
    remotepath: bool = False,
    user_id: bool = False,
    user_name: bool = False,
    desc: bool = False,
    limit: int = 0,
    offset: int = -1,
    hash_link_protocol: str = PcsRapidUploadInfo.default_hash_link_protocol(),
    show_all: bool = False,
    only_hash_link: bool = False,
):
    rapiduploadinfo = RapidUploadInfo(rapiduploadinfo_file)
    rows = rapiduploadinfo.list(
        ids=ids,
        by_filename=filename,
        by_time=time,
        by_size=size,
        by_localpath=localpath,
        by_remotepath=remotepath,
        by_user_id=user_id,
        by_user_name=user_name,
        desc=desc,
        limit=limit,
        offset=offset,
    )
    _display(
        rows,
        hash_link_protocol=hash_link_protocol,
        show_all=show_all,
        only_hash_link=only_hash_link,
    )


def rapid_upload_search(
    rapiduploadinfo_file: str,
    keyword: str,
    in_filename: bool = False,
    in_localpath: bool = False,
    in_remotepath: bool = False,
    in_user_name: bool = False,
    in_md5: bool = False,
    hash_link_protocol: str = PcsRapidUploadInfo.default_hash_link_protocol(),
    show_all: bool = False,
    only_hash_link: bool = False,
):
    rapiduploadinfo = RapidUploadInfo(rapiduploadinfo_file)
    rows = rapiduploadinfo.search(
        keyword,
        in_filename=in_filename,
        in_localpath=in_localpath,
        in_remotepath=in_remotepath,
        in_user_name=in_user_name,
        in_md5=in_md5,
    )
    _display(
        rows,
        hash_link_protocol=hash_link_protocol,
        show_all=show_all,
        only_hash_link=only_hash_link,
    )


def rapid_upload_delete(rapiduploadinfo_file: str, ids: List[int]):
    rapiduploadinfo = RapidUploadInfo(rapiduploadinfo_file)
    for id in ids:
        rapiduploadinfo.delete(id)


def _parse_link(link: str) -> Any:
    """Parse rapid upload link

    Format 1: cs3l://<content_md5>#<slice_md5>#<content_crc3>#<content_length>#<filename>
    Format 2: <content_md5>#<slice_md5>#<content_length>#<filename>
    Format 3: bdpan://{base64(<filename>|<content_length>|<content_md5>|<slice_md5>)}

    Format 2 is from https://blog.jixun.moe/du-code-gen , using at
        https://greasyfork.org/zh-CN/scripts/397324-%E7%A7%92%E4%BC%A0%E9%93%BE%E6%8E%A5%E6%8F%90%E5%8F%96
    """

    if link.startswith("cs3l://"):
        chunks = link[7:].split("#", 4)
        assert len(chunks) == 5
    elif link.startswith("bdpan://"):
        link = b64decode(link[8:]).decode("utf-8")
        link = link[::-1]
        chunks = link.split("|", 3)

        assert len(chunks) == 4

        chunks = [c[::-1] for c in chunks]
        chunks = [chunks[1], chunks[0], chunks[2], chunks[3]]
    else:
        chunks = link.split("#", 3)
        assert len(chunks) == 4

    if len(chunks) == 4:
        content_crc32 = "0"
        content_md5, slice_md5, content_length, filename = chunks
    elif len(chunks) == 5:
        content_md5, slice_md5, content_crc32, content_length, filename = chunks
        content_crc32 = content_crc32 or "0"  # content_crc32 can be ''
    else:
        raise RuntimeError("Here is Unreachable")

    assert len(content_md5) == len(slice_md5) == 32

    filename = filename.replace("%20", " ")
    return (slice_md5, content_md5, int(content_crc32), int(content_length), filename)


def rapid_upload(
    api: BaiduPCSApi,
    remotedir: str,
    link: str = "",
    slice_md5: str = "",
    content_md5: str = "",
    content_crc32: int = 0,
    content_length: int = 0,
    filename: str = "",
    no_ignore_existing: bool = False,
    rapiduploadinfo_file: Optional[str] = None,
    user_id: Optional[int] = None,
    user_name: Optional[str] = None,
):
    """Rapid upload with params

    If given `link` and `filename`, then filename of link will be replace by `filename`
    """

    if link:
        slice_md5, content_md5, content_crc32, content_length, _filename = _parse_link(
            link
        )
        content_crc32 = content_crc32 or 0
        filename = filename or _filename

    remotepath = join_path(remotedir, filename)

    assert all(
        [slice_md5, content_md5, content_length]
    ), f"`rapid_upload`: parsing rapid upload link fails: {link}"

    if not no_ignore_existing:
        if api.exists(remotepath):
            return

    try:
        pcs_file = api.rapid_upload_file(
            slice_md5,
            content_md5,
            content_crc32,
            content_length,
            remotepath,
            ondup="overwrite",
        )
        if rapiduploadinfo_file:
            save_rapid_upload_info(
                rapiduploadinfo_file,
                slice_md5,
                content_md5,
                content_crc32,
                content_length,
                remotepath=remotepath,
                user_id=user_id,
                user_name=user_name,
            )
        print(f"[i blue]Save to[/i blue] {pcs_file.path}")
    except Exception as err:
        link = PcsRapidUploadInfo(
            slice_md5=slice_md5,
            content_md5=content_md5,
            content_crc32=content_crc32,
            content_length=content_length,
            remotepath=remotepath,
        ).cs3l()
        print(
            f"[i yellow]Rapid Upload fails[/i yellow]: error: {err} link: {link}",
        )


def rapid_upload_links(
    api: BaiduPCSApi,
    remotedir: str,
    links: List[str] = [],
    no_ignore_existing: bool = False,
    rapiduploadinfo_file: Optional[str] = None,
    user_id: Optional[int] = None,
    user_name: Optional[str] = None,
    max_workers: int = CPU_NUM,
):
    """Rapid Upload multi links"""

    semaphore = Semaphore(max_workers)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futs = []
        for link in links:
            link = link.strip()
            if not link:
                continue

            semaphore.acquire()
            fut = executor.submit(
                sure_release,
                semaphore,
                rapid_upload,
                api,
                remotedir,
                link=link,
                no_ignore_existing=no_ignore_existing,
                rapiduploadinfo_file=rapiduploadinfo_file,
                user_id=user_id,
                user_name=user_name,
            )
            futs.append(fut)

        for fut in as_completed(futs):
            pass
