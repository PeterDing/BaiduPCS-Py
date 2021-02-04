from typing import Optional, Dict, List, Tuple, Callable, IO

from io import BytesIO
from baidupcs_py.common.io import RangeRequestIO, DEFAULT_MAX_CHUNK_SIZE
from baidupcs_py.baidupcs.pcs import BaiduPCS, BaiduPCSError, M3u8Type
from baidupcs_py.baidupcs.inner import (
    PcsFile,
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
    def cookies(self) -> Dict[str, Optional[str]]:
        return self._baidupcs.cookies

    def bdstoken(self) -> Optional[str]:
        return self._baidupcs.bdstoken()

    def quota(self) -> PcsQuota:
        info = self._baidupcs.quota()
        return PcsQuota(quota=info["quota"], used=info["used"])

    def meta(self, *remotepaths: str) -> List[PcsFile]:
        info = self._baidupcs.meta(*remotepaths)
        return [PcsFile.from_(v) for v in info.get("list", [])]

    def exists(self, remotepath: str) -> bool:
        return self._baidupcs.exists(remotepath)

    def is_file(self, remotepath: str) -> bool:
        return self._baidupcs.is_file(remotepath)

    def is_dir(self, remotepath: str) -> bool:
        return self._baidupcs.is_dir(remotepath)

    def list(
        self,
        remotepath: str,
        desc: bool = False,
        name: bool = False,
        time: bool = False,
        size: bool = False,
    ) -> List[PcsFile]:
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
        info = self._baidupcs.upload_file(
            io, remotepath, ondup=ondup, callback=callback
        )
        return PcsFile.from_(info)

    def rapid_upload_file(
        self,
        slice_md5: str,
        content_md5: str,
        content_crc32: int,
        io_len: int,
        remotepath: str,
        ondup="overwrite",
    ) -> PcsFile:
        info = self._baidupcs.rapid_upload_file(
            slice_md5, content_md5, content_crc32, io_len, remotepath, ondup=ondup
        )
        return PcsFile.from_(info)

    def upload_slice(
        self, io: IO, callback: Callable[[MultipartEncoderMonitor], None] = None
    ) -> str:
        info = self._baidupcs.upload_slice(io, callback=callback)
        return info["md5"]

    def combine_slices(
        self, slice_md5s: List[str], remotepath: str, ondup="overwrite"
    ) -> PcsFile:
        info = self._baidupcs.combine_slices(slice_md5s, remotepath, ondup=ondup)
        return PcsFile.from_(info)

    def search(
        self, keyword: str, remotepath: str, recursive: bool = False
    ) -> List[PcsFile]:
        info = self._baidupcs.search(keyword, remotepath, recursive=recursive)
        pcs_files = []
        for file_info in info["list"]:
            pcs_files.append(PcsFile.from_(file_info))
        return pcs_files

    def makedir(self, directory: str) -> PcsFile:
        info = self._baidupcs.makedir(directory)
        return PcsFile.from_(info)

    def move(self, *remotepaths: str) -> List[FromTo]:
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
        info = self._baidupcs.copy(*remotepaths)
        r = info["extra"].get("list")
        if not r:
            raise BaiduPCSError("File operator [copy] fails")
        return [FromTo(from_=v["from"], to_=v["to"]) for v in r]

    def remove(self, *remotepaths: str):
        self._baidupcs.remove(*remotepaths)

    def magnet_info(self, magnet: str) -> List[PcsMagnetFile]:
        info = self._baidupcs.magnet_info(magnet)
        return [PcsMagnetFile.from_(v) for v in info["magnet_info"]]

    def torrent_info(self, remote_torrent: str):
        self._baidupcs.torrent_info(remote_torrent)

    def add_task(self, task_url: str, remotedir: str) -> str:
        info = self._baidupcs.add_task(task_url, remotedir)
        return str(info["task_id"])

    def tasks(self, *task_ids: str) -> List[CloudTask]:
        info = self._baidupcs.tasks(*task_ids)
        tasks = []
        for task_id, v in info["task_info"].items():
            v["task_id"] = task_id
            tasks.append(CloudTask.from_(v))
        return tasks

    def list_tasks(self) -> List[CloudTask]:
        info = self._baidupcs.list_tasks()
        return [CloudTask.from_(v) for v in info["task_info"]]

    def clear_tasks(self) -> int:
        info = self._baidupcs.clear_tasks()
        return info["total"]

    def cancel_task(self, task_id: str):
        self._baidupcs.cancel_task(task_id)

    def share(self, *remotepaths: str, password: Optional[str] = None) -> PcsSharedLink:
        info = self._baidupcs.share(*remotepaths, password=password)
        link = PcsSharedLink.from_(info)._replace(
            paths=list(remotepaths), password=password
        )
        return link

    def list_shared(self, page: int = 1) -> List[PcsSharedLink]:
        info = self._baidupcs.list_shared(page)
        return [PcsSharedLink.from_(v) for v in info["list"]]

    def shared_password(self, share_id: int) -> Optional[str]:
        info = self._baidupcs.shared_password(share_id)
        p = info["pwd"]
        if p == "0":
            return None
        return p

    def cancel_shared(self, *share_ids: int):
        self._baidupcs.cancel_shared(*share_ids)

    def access_shared(
        self,
        shared_url: str,
        password: str,
        vcode_str: str = "",
        vcode: str = "",
        show_vcode: bool = True,
    ):
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
        """Return `vcode_str`, `vcode_img_url`"""

        info = self._baidupcs.getcaptcha(shared_url)
        return info["vcode_str"], info["vcode_img"]

    def get_vcode_img(self, vcode_img_url: str, shared_url: str) -> bytes:
        return self._baidupcs.get_vcode_img(vcode_img_url, shared_url)

    def shared_paths(self, shared_url: str) -> List[PcsSharedPath]:
        info = self._baidupcs.shared_paths(shared_url)
        uk = info["uk"]
        share_id = info["shareid"]
        bdstoken = info["bdstoken"]

        if not info.get("file_list"):
            return []

        return [
            PcsSharedPath.from_(v)._replace(uk=uk, share_id=share_id, bdstoken=bdstoken)
            for v in info["file_list"]["list"]
        ]

    def list_shared_paths(
        self, sharedpath: str, uk: int, share_id: int, bdstoken: str
    ) -> List[PcsSharedPath]:
        info = self._baidupcs.list_shared_paths(sharedpath, uk, share_id)
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
        self._baidupcs.transfer_shared_paths(
            remotedir, fs_ids, uk, share_id, bdstoken, shared_url
        )

    def user_info(self) -> PcsUser:
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
        info = self._baidupcs.user_products()
        pds = []
        for p in info["product_infos"]:
            pds.append(
                PcsUserProduct(
                    name=p["product_name"],
                    start_time=p["start_time"],
                    end_time=p["end_time"],
                )
            )

        level = info["level_info"]["current_level"]
        return pds, level

    def download_link(self, remotepath: str, pcs: bool = False) -> str:
        info = self._baidupcs.download_link(remotepath, pcs=pcs)
        assert bool(
            info.get("urls")
        ), "Remote entry should be blocked. Server returns no download link."
        return info["urls"][0]["url"]

    def file_stream(
        self,
        remotepath: str,
        max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE,
        callback: Callable[..., None] = None,
        encrypt_key=Optional[str],
    ) -> RangeRequestIO:
        return self._baidupcs.file_stream(
            remotepath,
            max_chunk_size=max_chunk_size,
            callback=callback,
            encrypt_key=encrypt_key,
        )

    def m3u8_stream(self, remotepath: str, type: M3u8Type = "M3U8_AUTO_720") -> str:
        info = self._baidupcs.m3u8_stream(remotepath, type)
        if info.get("m3u8_content"):
            return info["m3u8_content"]
        else:
            # Here should be a error
            return ""
