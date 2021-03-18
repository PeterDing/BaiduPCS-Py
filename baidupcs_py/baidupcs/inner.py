from typing import Optional, List, Dict, NamedTuple
from collections import namedtuple
from urllib.parse import unquote

from base64 import standard_b64encode

import os


class PcsRapidUploadInfo(NamedTuple):
    """Rapid Upload Info"""

    slice_md5: str
    content_md5: str
    content_crc32: int
    content_length: int
    remotepath: Optional[str] = None

    def _filename(self) -> str:
        filename = os.path.basename(self.remotepath or "")
        if not filename:
            return ""
        else:
            return filename.replace(" ", "%20")

    def cs3l(self) -> str:
        """cs3l://<content_md5>#<slice_md5>#<content_crc32>#<content_length>#<filename>"""

        filename = self._filename()
        content_crc32 = self.content_crc32 or "0"
        return f"cs3l://{self.content_md5}#{self.slice_md5}#{content_crc32}#{self.content_length}#{filename}"

    def short(self) -> str:
        """<content_md5>#<slice_md5>#<content_length>#<filename>"""

        filename = self._filename()
        return f"{self.content_md5}#{self.slice_md5}#{self.content_length}#{filename}"

    def bdpan(self) -> str:
        """bdpan://{base64(<filename>|<content_length>|<content_md5>|<slice_md5>)}"""

        filename = self._filename()
        return "bdpan://" + standard_b64encode(
            f"{filename}|{self.content_length}|{self.content_md5}|{self.slice_md5}".encode(
                "utf-8"
            )
        ).decode("utf-8")

    def all_links(self) -> List[str]:
        return [self.cs3l(), self.short(), self.bdpan()]

    @staticmethod
    def hash_link_protocols() -> List[str]:
        return ["cs3l", "short", "bdpan"]

    @staticmethod
    def default_hash_link_protocol() -> str:
        return "cs3l"


class PcsFile(NamedTuple):
    """
    A Baidu PCS file

    path: str  # remote absolute path
    is_dir: Optional[bool] = None
    is_file: Optional[bool] = None
    fs_id: Optional[int] = None  # file id
    size: Optional[int] = None
    md5: Optional[str] = None
    block_list: Optional[List[str]] = None  # block md5 list
    category: Optional[int] = None
    user_id: Optional[int] = None
    ctime: Optional[int] = None  # server created time
    mtime: Optional[int] = None  # server modifed time
    local_ctime: Optional[int] = None  # local created time
    local_mtime: Optional[int] = None  # local modifed time
    server_ctime: Optional[int] = None  # server created time
    server_mtime: Optional[int] = None  # server modifed time
    shared: Optional[bool] = None  # this file is shared if True
    """

    path: str  # remote absolute path
    is_dir: Optional[bool] = None
    is_file: Optional[bool] = None
    fs_id: Optional[int] = None  # file id
    size: Optional[int] = None
    md5: Optional[str] = None
    block_list: Optional[List[str]] = None  # block md5 list
    category: Optional[int] = None
    user_id: Optional[int] = None
    ctime: Optional[int] = None  # server created time
    mtime: Optional[int] = None  # server modifed time
    local_ctime: Optional[int] = None  # local created time
    local_mtime: Optional[int] = None  # local modifed time
    server_ctime: Optional[int] = None  # server created time
    server_mtime: Optional[int] = None  # server modifed time
    shared: Optional[bool] = None  # this file is shared if True

    rapid_upload_info: Optional[PcsRapidUploadInfo] = None
    dl_link: Optional[str] = None

    @staticmethod
    def from_(info) -> "PcsFile":
        return PcsFile(
            path=info.get("path"),
            is_dir=info.get("isdir") == 1,
            is_file=info.get("isdir") == 0,
            fs_id=info.get("fs_id"),
            size=info.get("size"),
            md5=info.get("md5"),
            block_list=info.get("block_list"),
            category=info.get("category"),
            user_id=info.get("user_id"),
            ctime=info.get("ctime"),
            mtime=info.get("mtime"),
            local_ctime=info.get("local_ctime"),
            local_mtime=info.get("local_mtime"),
            server_ctime=info.get("server_ctime"),
            server_mtime=info.get("server_mtime"),
            shared=info.get("shared"),
        )


class PcsMagnetFile(NamedTuple):
    """
    A file in a magnet link

    path: str  # the file path in the magnet link
    size: Optional[int] = None
    """

    path: str  # the file path in the magnet link
    size: Optional[int] = None

    @staticmethod
    def from_(info) -> "PcsMagnetFile":
        return PcsMagnetFile(path=info.get("file_name"), size=info.get("size"))


class PcsSharedLink(NamedTuple):
    url: str
    paths: Optional[List[str]] = None
    fs_ids: Optional[List[int]] = None
    password: Optional[str] = None

    # channel == 4, has password
    channel: Optional[bool] = None

    share_id: Optional[int] = None
    ctime: Optional[int] = None

    @staticmethod
    def from_(info) -> "PcsSharedLink":
        return PcsSharedLink(
            url=info.get("link") or info.get("shortlink"),
            paths=info.get("paths") or [info.get("typicalPath")],
            fs_ids=info.get("fsIds"),
            password=info.get("password"),
            channel=info.get("channel"),
            share_id=info.get("share_id") or info.get("shareId") or info.get("shareid"),
            ctime=info.get("ctime"),
        )

    def has_password(self) -> bool:
        if self.password:
            return True
        if self.channel == 4:
            return True
        return False

    def available(self) -> bool:
        if not self.paths:
            return False
        if self.paths[0].startswith("/"):
            return True
        else:
            return False


class PcsSharedPath(NamedTuple):
    """
    User shared path

    `sharedpath`: original shared path
    `remotepath`: the directory where the `sharedpath` will save
    """

    fs_id: int
    path: str
    size: int
    is_dir: bool
    is_file: bool
    md5: Optional[str] = None
    local_ctime: Optional[int] = None  # local created time
    local_mtime: Optional[int] = None  # local modifed time
    server_ctime: Optional[int] = None  # server created time
    server_mtime: Optional[int] = None  # server modifed time

    uk: Optional[int] = None
    share_id: Optional[int] = None
    bdstoken: Optional[str] = None

    @staticmethod
    def from_(info) -> "PcsSharedPath":
        if "parent_path" in info:
            path = unquote(info["parent_path"] or "") + "/" + info["server_filename"]
        else:
            path = info["path"]
        return PcsSharedPath(
            fs_id=info.get("fs_id"),
            path=path,
            size=info.get("size"),
            is_dir=info.get("isdir") == 1,
            is_file=info.get("isdir") == 0,
            md5=info.get("md5"),
            local_ctime=info.get("local_ctime"),
            local_mtime=info.get("local_mtime"),
            server_ctime=info.get("server_ctime"),
            server_mtime=info.get("server_mtime"),
            uk=info.get("uk"),
            share_id=info.get("share_id") or info.get("shareid"),
            bdstoken=info.get("bdstoken"),
        )


FromTo = namedtuple("FromTo", ["from_", "to_"])


class PcsQuota(NamedTuple):
    quota: int
    used: int


class PcsAuth(NamedTuple):
    bduss: str
    cookies: Dict[str, Optional[str]]
    stoken: Optional[str] = None
    ptoken: Optional[str] = None


class PcsUserProduct(NamedTuple):
    name: str
    start_time: int  # second
    end_time: int  # second


class PcsUser(NamedTuple):
    user_id: int
    user_name: Optional[str] = None
    auth: Optional[PcsAuth] = None
    age: Optional[float] = None
    sex: Optional[str] = None
    quota: Optional[PcsQuota] = None
    products: Optional[List[PcsUserProduct]] = None
    level: Optional[int] = None


TASK_STATUS_MSG = {
    0: "下载成功",
    1: "下载进行中",
    2: "系统错误",
    3: "资源不存在",
    4: "下载超时",
    5: "资源存在但下载失败",
    6: "存储空间不足",
    7: "任务取消",
    8: "目标地址数据已存在",
    9: "任务删除",
    10: "部分下载成功",
}


class CloudTask(NamedTuple):
    """
    Baidu PCS Cloud Task
    """

    task_id: str
    source_url: str
    task_name: str
    path: str  # Saved remote directory
    status: int
    size: int
    finished_size: int
    ctime: int  # created time
    stime: int  # begined time
    ftime: int  # finished time

    @staticmethod
    def from_(info) -> "CloudTask":
        size = info.get("size") or info.get("file_size")
        if size:
            size = int(size)
        finished_size = info.get("finished_size")
        if finished_size:
            finished_size = int(finished_size)

        return CloudTask(
            task_id=str(info["task_id"]),
            source_url=info.get("source_url"),
            task_name=info.get("task_name"),
            path=info.get("save_path") or info.get("path"),
            status=int(info.get("status", 3)),
            size=size,
            finished_size=finished_size,
            ctime=info.get("ctime"),
            stime=info.get("stime"),
            ftime=info.get("ftime"),
        )

    def status_mean(self) -> Optional[str]:
        return TASK_STATUS_MSG.get(self.status)

    def finished(self) -> bool:
        return self.status == 0
