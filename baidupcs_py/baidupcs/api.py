from typing import Optional, Dict, List, Tuple, Callable, IO

from io import BytesIO

from baidupcs_py.common import constant
from baidupcs_py.common.crypto import calu_md5
from baidupcs_py.common.io import RangeRequestIO, DEFAULT_MAX_CHUNK_SIZE
from baidupcs_py.baidupcs.pcs import BaiduPCS, BaiduPCSError, M3u8Type
from baidupcs_py.baidupcs.inner import (
    PcsFile,
    PcsRapidUploadInfo,
    PcsMagnetFile,
    PcsSharedLink,
    PcsSharedPath,
    FromTo,
    PcsAuth,
    PcsUserProduct,
    PcsUser,
    PcsQuota,
    CloudTask,
)

from requests_toolbelt import MultipartEncoderMonitor
from PIL import Image

from rich import print
from rich.prompt import Prompt


class BaiduPCSApi:
    """Baidu PCS Api

    This is the wrapper of `BaiduPCS`. It parses the content of response of raw
    BaiduPCS requests to some inner data structions.
    """

    def __init__(
        self,
        bduss: Optional[str] = None,
        stoken: Optional[str] = None,
        ptoken: Optional[str] = None,
        cookies: Dict[str, Optional[str]] = {},
        user_id: Optional[int] = None,
    ):
        self._baidupcs = BaiduPCS(
            bduss, stoken=stoken, ptoken=ptoken, cookies=cookies, user_id=user_id
        )

    @property
    def bduss(self) -> str:
        return self._baidupcs._bduss

    @property
    def bdstoken(self) -> str:
        return self._baidupcs.bdstoken

    @property
    def stoken(self) -> Optional[str]:
        return self._baidupcs._stoken

    @property
    def ptoken(self) -> Optional[str]:
        return self._baidupcs._ptoken

    @property
    def baiduid(self) -> Optional[str]:
        return self._baidupcs._baiduid

    @property
    def logid(self) -> Optional[str]:
        return self._baidupcs._logid

    @property
    def user_id(self) -> Optional[int]:
        return self._baidupcs._user_id

    @property
    def cookies(self) -> Dict[str, Optional[str]]:
        return self._baidupcs.cookies

    def quota(self) -> PcsQuota:
        """Quota Information"""

        info = self._baidupcs.quota()
        return PcsQuota(quota=info["quota"], used=info["used"])

    def meta(self, *remotepaths: str) -> List[PcsFile]:
        """Meta data of `remotepaths`"""

        info = self._baidupcs.meta(*remotepaths)
        return [PcsFile.from_(v) for v in info.get("list", [])]

    def exists(self, remotepath: str) -> bool:
        """Check whether `remotepath` exists"""

        return self._baidupcs.exists(remotepath)

    def is_file(self, remotepath: str) -> bool:
        """Check whether `remotepath` is a file"""

        return self._baidupcs.is_file(remotepath)

    def is_dir(self, remotepath: str) -> bool:
        """Check whether `remotepath` is a directory"""

        return self._baidupcs.is_dir(remotepath)

    def list(
        self,
        remotepath: str,
        desc: bool = False,
        name: bool = False,
        time: bool = False,
        size: bool = False,
    ) -> List[PcsFile]:
        """List directory contents"""

        info = self._baidupcs.list(
            remotepath, desc=desc, name=name, time=time, size=size
        )
        return [PcsFile.from_(v) for v in info.get("list", [])]

    def upload_file(
        self,
        io: IO,
        remotepath: str,
        ondup="overwrite",
        callback: Callable[[MultipartEncoderMonitor], None] = None,
    ) -> PcsFile:
        """Upload an io to `remotepath`

        ondup (str): "overwrite" or "newcopy"
        callable: the callback for monitoring uploading progress

        Warning, the api CAN NOT set local_ctime and local_mtime
        """

        info = self._baidupcs.upload_file(
            io, remotepath, ondup=ondup, callback=callback
        )
        return PcsFile.from_(info)

    def rapid_upload_file(
        self,
        slice_md5: str,
        content_md5: str,
        content_crc32: int,  # not needed
        io_len: int,
        remotepath: str,
        local_ctime: Optional[int] = None,
        local_mtime: Optional[int] = None,
        ondup="overwrite",
    ) -> PcsFile:
        """Rapid Upload File

        slice_md5 (32 bytes): the md5 of pre 256KB of content.
        content_md5 (32 bytes): the md5 of total content.
        content_crc32 (int): the crc32 of total content (Not Needed),
            if content_crc32 is 0, the params of the api will be ignored.
        io_len (int): the length of total content.
        remotepath (str): the absolute remote path to save the content.
        local_ctime (optional, int): the timestramp of the local ctime
        local_mtime (optional, int): the timestramp of the local mtime
        ondup (str): "overwrite" or "newcopy"
        """

        info = self._baidupcs.rapid_upload_file(
            slice_md5,
            content_md5,
            content_crc32,
            io_len,
            remotepath,
            local_ctime=local_ctime,
            local_mtime=local_mtime,
            ondup=ondup,
        )
        return PcsFile.from_(info)

    def upload_slice(
        self, io: IO, callback: Callable[[MultipartEncoderMonitor], None] = None
    ) -> str:
        """Upload an io as a slice

        callable: the callback for monitoring uploading progress
        """

        info = self._baidupcs.upload_slice(io, callback=callback)
        return info["md5"]

    def combine_slices(
        self,
        slice_md5s: List[str],
        remotepath: str,
        local_ctime: Optional[int] = None,
        local_mtime: Optional[int] = None,
        ondup="overwrite",
    ) -> PcsFile:
        """Combine uploaded slices to `remotepath`

        local_ctime (optional, int): the timestramp of the local ctime
        local_mtime (optional, int): the timestramp of the local mtime
        ondup (str): "overwrite" or "newcopy"
        """

        info = self._baidupcs.combine_slices(
            slice_md5s,
            remotepath,
            local_ctime=local_ctime,
            local_mtime=local_mtime,
            ondup=ondup,
        )
        return PcsFile.from_(info)

    def search(
        self, keyword: str, remotepath: str, recursive: bool = False
    ) -> List[PcsFile]:
        """Search in `remotepath` with `keyword`"""

        info = self._baidupcs.search(keyword, remotepath, recursive=recursive)
        pcs_files = []
        for file_info in info["list"]:
            pcs_files.append(PcsFile.from_(file_info))
        return pcs_files

    def makedir(self, directory: str) -> PcsFile:
        info = self._baidupcs.makedir(directory)
        return PcsFile.from_(info)

    def move(self, *remotepaths: str) -> List[FromTo]:
        """Move `remotepaths[:-1]` to `remotepaths[-1]`"""

        info = self._baidupcs.move(*remotepaths)
        r = info["extra"].get("list")
        if not r:
            raise BaiduPCSError("File operator [move] fails")
        return [FromTo(from_=v["from"], to_=v["to"]) for v in r]

    def rename(self, source: str, dest: str) -> FromTo:
        info = self._baidupcs.rename(source, dest)
        r = info["extra"].get("list")
        if not r:
            raise BaiduPCSError("File operator [rename] fails")
        v = r[0]
        return FromTo(from_=v["from"], to_=v["to"])

    def copy(self, *remotepaths: str):
        """Copy `remotepaths[:-1]` to `remotepaths[-1]`"""

        info = self._baidupcs.copy(*remotepaths)
        r = info["extra"].get("list")
        if not r:
            raise BaiduPCSError("File operator [copy] fails")
        return [FromTo(from_=v["from"], to_=v["to"]) for v in r]

    def remove(self, *remotepaths: str):
        """Remove all `remotepaths`"""

        self._baidupcs.remove(*remotepaths)

    def magnet_info(self, magnet: str) -> List[PcsMagnetFile]:
        """Get the magnet information"""

        info = self._baidupcs.magnet_info(magnet)
        return [PcsMagnetFile.from_(v) for v in info["magnet_info"]]

    def torrent_info(self, remote_torrent: str):
        """Get the `remote_torrent` information"""

        self._baidupcs.torrent_info(remote_torrent)

    def add_task(self, task_url: str, remotedir: str) -> str:
        """Add a cloud task to save at `remotedir`

        task_url (str): http url
        """

        info = self._baidupcs.add_task(task_url, remotedir)
        return str(info["task_id"])

    def add_magnet_task(
        self, task_url: str, remotedir: str, selected_idx: List[int]
    ) -> str:
        """Add a magnet task to save at `remotedir`.

        task_url (str): magnet link
        selected_idx: the indexes needed to download
        """

        info = self._baidupcs.add_magnet_task(task_url, remotedir, selected_idx)
        return str(info["task_id"])

    def tasks(self, *task_ids: str) -> List[CloudTask]:
        """List cloud tasks with their `task_ids`"""

        info = self._baidupcs.tasks(*task_ids)
        tasks = []
        for task_id, v in info["task_info"].items():
            v["task_id"] = task_id
            tasks.append(CloudTask.from_(v))
        return tasks

    def list_tasks(self) -> List[CloudTask]:
        """List all cloud tasks"""

        info = self._baidupcs.list_tasks()
        return [CloudTask.from_(v) for v in info["task_info"]]

    def clear_tasks(self) -> int:
        """Clear all finished and failed cloud tasks"""

        info = self._baidupcs.clear_tasks()
        return info["total"]

    def cancel_task(self, task_id: str):
        """Cancel a cloud task with its `task_id`"""

        self._baidupcs.cancel_task(task_id)

    def share(self, *remotepaths: str, password: Optional[str] = None) -> PcsSharedLink:
        """Share `remotepaths` to public with a optional password

        To use api, `STOKEN` must be in `cookies`
        """

        info = self._baidupcs.share(*remotepaths, password=password)
        link = PcsSharedLink.from_(info)._replace(
            paths=list(remotepaths), password=password
        )
        return link

    def list_shared(self, page: int = 1) -> List[PcsSharedLink]:
        """List shared link on a page

        To use api, `STOKEN` must be in `cookies`
        """

        info = self._baidupcs.list_shared(page)
        return [PcsSharedLink.from_(v) for v in info["list"]]

    def shared_password(self, share_id: int) -> Optional[str]:
        """Show shared link password

        To use api, `STOKEN` must be in `cookies`
        """

        info = self._baidupcs.shared_password(share_id)
        p = info.get("pwd", "0")  # If "pwd" is not in info, error is 分享已过期
        if p == "0":
            return None
        return p

    def cancel_shared(self, *share_ids: int):
        """Cancel shared links with their `share_ids`

        To use api, `STOKEN` must be in `cookies`
        """

        self._baidupcs.cancel_shared(*share_ids)

    def access_shared(
        self,
        shared_url: str,
        password: str,
        vcode_str: str = "",
        vcode: str = "",
        show_vcode: bool = True,
    ):
        """Verify the `shared_url` which needs the `password`

        This method MUST be called before calling `self.shared_paths`.

        show_vcode (bool): If set True, it will be open the vcode image (if needed)
            with a gui window. Else, you need to handle the vcode.
        """

        while True:
            try:
                self._baidupcs.access_shared(shared_url, password, vcode_str, vcode)
                return
            except BaiduPCSError as err:
                if err.error_code not in (-9, -62):
                    raise err
                if show_vcode:
                    if err.error_code == -62:  # -62: '可能需要输入验证码'
                        print("[yellow]Need vcode![/yellow]")
                    if err.error_code == -9:
                        print("[red]vcode is incorrect![/red]")
                    vcode_str, vcode_img_url = self.getcaptcha(shared_url)
                    img_cn = self.get_vcode_img(vcode_img_url, shared_url)
                    img_buf = BytesIO(img_cn)
                    img_buf.seek(0, 0)
                    img = Image.open(img_buf)
                    img.show()
                    vcode = Prompt.ask("input vcode")
                else:
                    raise err

    def getcaptcha(self, shared_url: str) -> Tuple[str, str]:
        """Get one vcode information

        Return `vcode_str`, `vcode_img_url`"""

        info = self._baidupcs.getcaptcha(shared_url)
        return info["vcode_str"], info["vcode_img"]

    def get_vcode_img(self, vcode_img_url: str, shared_url: str) -> bytes:
        """Get vcode image content"""

        return self._baidupcs.get_vcode_img(vcode_img_url, shared_url)

    def shared_paths(self, shared_url: str) -> List[PcsSharedPath]:
        """Shared paths of the `shared_url`"""

        info = self._baidupcs.shared_paths(shared_url)
        uk = info.get("share_uk") or info.get("uk")
        uk = int(uk)

        assert uk, "`BaiduPCSApi.shared_paths`: Don't get `uk`"

        share_id = info["shareid"]
        bdstoken = info["bdstoken"]

        if not info.get("file_list"):
            return []

        if isinstance(info["file_list"], list):
            file_list = info["file_list"]
        elif isinstance(info["file_list"].get("list"), list):
            file_list = info["file_list"]["list"]
        else:
            raise ValueError("`shared_paths`: Parsing shared info fails")

        return [
            PcsSharedPath.from_(v)._replace(uk=uk, share_id=share_id, bdstoken=bdstoken)
            for v in file_list
        ]

    def list_shared_paths(
        self,
        sharedpath: str,
        uk: int,
        share_id: int,
        bdstoken: str,
        page: int = 1,
        size: int = 100,
    ) -> List[PcsSharedPath]:
        """Sub shared paths of the shared directory `sharedpath`"""

        info = self._baidupcs.list_shared_paths(
            sharedpath, uk, share_id, page=page, size=size
        )
        return [
            PcsSharedPath.from_(v)._replace(uk=uk, share_id=share_id, bdstoken=bdstoken)
            for v in info["list"]
        ]

    def transfer_shared_paths(
        self,
        remotedir: str,
        fs_ids: List[int],
        uk: int,
        share_id: int,
        bdstoken: str,
        shared_url: str,
    ):
        """Save these `fs_ids` of shared paths to `remotedir`"""

        self._baidupcs.transfer_shared_paths(
            remotedir, fs_ids, uk, share_id, bdstoken, shared_url
        )

    def user_info(self) -> PcsUser:
        """User's information"""

        info = self._baidupcs.user_info()
        user_id = int(info["user"]["id"])
        user_name = info["user"]["name"]

        info = self._baidupcs.tieba_user_info(user_id)
        age = float(info["user"]["tb_age"])
        sex = info["user"]["sex"]
        if sex == 1:
            sex = "♂"
        elif sex == 2:
            sex = "♀"
        else:
            sex = "unknown"

        auth = PcsAuth(
            bduss=self._baidupcs._bduss,
            cookies=self.cookies,
            stoken=self._baidupcs._stoken,
            ptoken=self._baidupcs._ptoken,
        )

        quota = self.quota()

        products, level = self.user_products()

        return PcsUser(
            user_id=user_id,
            user_name=user_name,
            auth=auth,
            age=age,
            sex=sex,
            quota=quota,
            products=products,
            level=level,
        )

    def user_products(self) -> Tuple[List[PcsUserProduct], int]:
        """User's product information"""

        info = self._baidupcs.user_products()
        pds = []
        for p in info["product_infos"]:
            # `product_name` of some entries are None (issue #30)
            if not p.get("product_name"):
                continue

            pds.append(
                PcsUserProduct(
                    name=p["product_name"],
                    start_time=p["start_time"],
                    end_time=p["end_time"],
                )
            )

        level = info["level_info"]["current_level"]
        return pds, level

    def download_link(self, remotepath: str, pcs: bool = False) -> Optional[str]:
        """Download link of the `remotepath`

        pcs (bool, default: False): If pcs is True, return the downloading pcs link
            which has a limited threshold of downstream even if the user is a svip.
            If pcs is False, return the downloading link requested by the android api
            and which has not limited threshold for a svip user.
        """

        return self._baidupcs.download_link(remotepath, pcs=pcs)

    def file_stream(
        self,
        remotepath: str,
        max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE,
        callback: Callable[..., None] = None,
        encrypt_password: bytes = b"",
        pcs: bool = False,
    ) -> Optional[RangeRequestIO]:
        """File stream as a normal io"""

        return self._baidupcs.file_stream(
            remotepath,
            max_chunk_size=max_chunk_size,
            callback=callback,
            encrypt_password=encrypt_password,
            pcs=pcs,
        )

    def m3u8_stream(self, remotepath: str, type: M3u8Type = "M3U8_AUTO_720") -> str:
        """Media file's m3u8 content"""

        info = self._baidupcs.m3u8_stream(remotepath, type)
        if info.get("m3u8_content"):
            return info["m3u8_content"]
        else:
            # Here should be a error
            return ""

    def rapid_upload_info(
        self, remotepath: str, check: bool = True
    ) -> Optional[PcsRapidUploadInfo]:
        """Rapid upload information

        check (bool): If check is True, we need to use the `self.rapid_upload_file` to
            check whether the rapid upload information is valid. Therefore some meta information
            of the `remotepath` will be changed. These are server_ctime and server_mtime.
        """

        pcs_file = self.meta(remotepath)[0]
        content_length = pcs_file.size

        if content_length < 256 * constant.OneK:
            return None

        fs = self.file_stream(remotepath, pcs=False)
        if not fs:
            return None

        data = fs.read(256 * constant.OneK)
        assert data and len(data) == 256 * constant.OneK

        slice_md5 = calu_md5(data)

        assert (
            content_length and content_length == fs._auto_decrypt_request.content_length
        )

        content_md5 = fs._auto_decrypt_request.content_md5
        content_crc32 = fs._auto_decrypt_request.content_crc32 or 0

        if not content_md5:
            return None

        block_list = pcs_file.block_list
        if block_list and len(block_list) == 1 and block_list[0] == pcs_file.md5:
            return PcsRapidUploadInfo(
                slice_md5=slice_md5,
                content_md5=content_md5,
                content_crc32=content_crc32,
                content_length=content_length,
                remotepath=pcs_file.path,
            )

        if check:
            try:
                # Try rapid_upload_file
                self.rapid_upload_file(
                    slice_md5,
                    content_md5,
                    content_crc32,
                    content_length,
                    pcs_file.path,
                    local_ctime=pcs_file.local_ctime,
                    local_mtime=pcs_file.local_mtime,
                    ondup="overwrite",
                )
            except BaiduPCSError as err:
                # 31079: "未找到文件MD5"
                if err.error_code != 31079:
                    raise err
                return None

        return PcsRapidUploadInfo(
            slice_md5=slice_md5,
            content_md5=content_md5,
            content_crc32=content_crc32,
            content_length=content_length,
            remotepath=pcs_file.path,
        )
