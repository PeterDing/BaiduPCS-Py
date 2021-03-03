from typing import List
from enum import Enum
import os

from baidupcs_py.baidupcs import BaiduPCSApi
from baidupcs_py.commands.display import display_tasks
from baidupcs_py.commands.log import get_logger
from baidupcs_py.common.file_type import MEDIA_EXTS, IMAGE_EXTS, DOC_EXTS, ARCHIVE_EXTS
from baidupcs_py.common.url import is_magnet

from rich import print

logger = get_logger(__name__)


class FileType(Enum):
    All = "All"
    Media = "Media"
    Image = "Image"
    Doc = "Doc"
    Archive = "Archive"

    def sift(self, ext: str) -> bool:
        ext = ext.lower()
        if self == FileType.Media:
            if ext in MEDIA_EXTS:
                return True
        elif self == FileType.Image:
            if ext in IMAGE_EXTS:
                return True
        elif self == FileType.Doc:
            if ext in DOC_EXTS:
                return True
        elif self == FileType.Archive:
            if ext in ARCHIVE_EXTS:
                return True
        elif self == FileType.All:
            return True
        else:
            raise RuntimeError("Here is unreachable")

        return False

    @staticmethod
    def from_(addr: str) -> "FileType":
        if addr == "a":
            return FileType.All
        if addr == "m":
            return FileType.Media
        if addr == "i":
            return FileType.Image
        if addr == "d":
            return FileType.Doc
        if addr == "c":
            return FileType.Archive

        logger.warning("Unknown FileType addr: %s", addr)

        raise ValueError(f"Unknown FileType addr: {addr}")


def add_task(
    api: BaiduPCSApi,
    task_url: str,
    remotedir: str,
    file_types: List[FileType] = [FileType.Media],
):
    if is_magnet(task_url):
        logger.warning("Add cloud task: magnet: %s", task_url)

        pmfs = api.magnet_info(task_url)
        selected_idx = []
        for idx, pmf in enumerate(pmfs, 1):
            ext = os.path.splitext(pmf.path)[-1]
            for file_type in file_types:
                if file_type.sift(ext):
                    selected_idx.append(idx)
                    break

        if not selected_idx:
            logger.warning("`add_task`: No selected idx for %s", task_url)
            return

        task_id = api.add_magnet_task(task_url, remotedir, selected_idx)
        tasks(api, task_id)
    else:
        logger.warning("Add cloud task: %s", task_url)
        task_id = api.add_task(task_url, remotedir)


def tasks(api: BaiduPCSApi, *task_ids: str):
    if not task_ids:
        return

    cloud_tasks = api.tasks(*task_ids)
    display_tasks(*cloud_tasks)


def list_tasks(api: BaiduPCSApi):
    cloud_tasks = api.list_tasks()
    tasks(api, *[t.task_id for t in cloud_tasks])


def clear_tasks(api: BaiduPCSApi):
    n = api.clear_tasks()
    print("clear tasks:", n)


def cancel_task(api: BaiduPCSApi, task_id: str):
    api.cancel_task(task_id)


def purge_all_tasks(api: BaiduPCSApi):
    clear_tasks(api)

    cloud_tasks = api.list_tasks()
    for task in cloud_tasks:
        cancel_task(api, task.task_id)
