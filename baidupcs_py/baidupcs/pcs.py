from typing import Optional, Dict, List, Union, Any, Callable, IO
from typing_extensions import Literal
from enum import Enum

from pathlib import Path
import time
import re
import json
from urllib.parse import urlparse, quote_plus

import requests
from requests_toolbelt import MultipartEncoder, MultipartEncoderMonitor

from baidupcs_py.common import constant
from baidupcs_py.common.io import RangeRequestIO, DEFAULT_MAX_CHUNK_SIZE
from baidupcs_py.common.cache import timeout_cache
from baidupcs_py.common.crypto import calu_md5, calu_sha1
from baidupcs_py.baidupcs.errors import BaiduPCSError, parse_errno
from baidupcs_py.baidupcs.phone import get_phone_model, sum_IMEI
from baidupcs_py.baidupcs.errors import assert_ok
from baidupcs_py.utils import dump_json


PCS_BAIDU_COM = "https://pcs.baidu.com"
# PCS_BAIDU_COM = 'http://127.0.0.1:8888'
PAN_BAIDU_COM = "https://pan.baidu.com"
# PAN_BAIDU_COM = 'http://127.0.0.1:8888'

PCS_UA = "netdisk;2.2.51.6;netdisk;10.0.63;PC;android-android"
PAN_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_14_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/77.0.3865.75 Safari/537.36"

PCS_HEADERS = {"User-Agent": PCS_UA}
PAN_HEADERS = {"User-Agent": PAN_UA}

PCS_APP_ID = "778750"
PAN_APP_ID = "250528"

M3u8Type = Literal["M3U8_AUTO_720", "M3U8_AUTO_480"]


def _from_to(f: str, t: str) -> Dict[str, str]:
    return {"from": f, "to": t}


class Method(Enum):
    Head = "HEAD"
    Get = "GET"
    Post = "POST"


class PcsNode(Enum):
    Quota = "rest/2.0/pcs/quota"
    File = "rest/2.0/pcs/file"
    PcsCloud = "rest/2.0/pcs/services/cloud_dl"
    PanCloud = "rest/2.0/services/cloud_dl"
    TransferShared = "share/transfer"
    Share = "share/set"
    SharedPathList = "share/list"
    SharedRecord = "share/record"
    SharedCancel = "share/cancel"
    SharedPassword = "share/surlinfoinrecord"
    Getcaptcha = "api/getcaptcha"
    UserProducts = "rest/2.0/membership/user"


class BaiduPCS:
    """`BaiduPCS` provides pcs's apis which return raw json"""

    def __init__(
        self,
        bduss: Optional[str] = None,
        stoken: Optional[str] = None,
        ptoken: Optional[str] = None,
        cookies: Dict[str, Optional[str]] = {},
        user_id: Optional[int] = None,
    ):
        if not bduss and cookies and cookies.get("BDUSS", ""):
            bduss = cookies["BDUSS"]
        if not stoken and cookies and cookies.get("STOKEN", ""):
            stoken = cookies["STOKEN"]
        if not ptoken and cookies and cookies.get("PTOKEN", ""):
            ptoken = cookies["PTOKEN"]

        assert bduss, "`bduss` must be set. Or `BDUSS` is in `cookies`."

        if not cookies:
            cookies = {"BDUSS": bduss, "STOKEN": stoken, "PTOKEN": ptoken}

        self._bduss = bduss
        self._stoken = stoken
        self._ptoken = ptoken
        self._bdstoken = ""
        self._cookies = cookies
        self._session = requests.Session()
        self._session.cookies.update(cookies)

        user_info = None
        if not user_id:
            user_info = self.user_info()
            user_id = user_info.get("user", {}).get("id")
            if not user_id:
                user_info = None
        self._user_id = user_id
        self._user_info = user_info

    @property
    def cookies(self) -> Dict[str, Optional[str]]:
        return self._session.cookies.get_dict()

    @staticmethod
    def _form_url(node: PcsNode, domain: str = PCS_BAIDU_COM):
        return f"{domain}/{node.value}"

    @staticmethod
    def _app_id(url: str):
        """Select app_id based on `url`"""

        if PCS_BAIDU_COM in url:
            return PCS_APP_ID
        else:
            return PAN_APP_ID

    @staticmethod
    def _headers(url: str):
        """Select headers based on `url`"""

        if PCS_BAIDU_COM in url:
            return dict(PCS_HEADERS)
        else:
            return dict(PAN_HEADERS)

    def _cookies_update(self, cookies: Dict[str, str]):
        self._session.cookies.update(cookies)

    def _request(
        self,
        method: Method,
        url: str,
        params: Optional[Dict[str, str]] = {},
        headers: Optional[Dict[str, str]] = None,
        data: Union[str, bytes, Dict[str, str], Any] = None,
        files: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> requests.Response:
        if params is not None:
            app_id = self._app_id(url)
            params["app_id"] = app_id

        if not headers:
            headers = self._headers(url)

        if isinstance(data, (MultipartEncoder, MultipartEncoderMonitor)):
            assert headers
            headers["Content-Type"] = data.content_type

        try:
            resp = self._session.request(
                method.value,
                url,
                params=params,
                headers=headers,
                data=data,
                files=files,
                **kwargs,
            )
            return resp
        except Exception as err:
            raise BaiduPCSError("BaiduPCS._request", cause=err)

    def _request_get(
        self,
        url: str,
        params: Optional[Dict[str, str]] = {},
        headers: Optional[Dict[str, str]] = None,
        **kwargs,
    ) -> requests.Response:
        return self._request(Method.Get, url, params=params, headers=headers)

    def bdstoken(self) -> Optional[str]:
        assert self._stoken or self._cookies.get("STOKEN")

        url = "http://pan.baidu.com/disk/home"
        resp = self._request(Method.Get, url, params=None)
        cn = resp.text
        mod = re.search(r'bdstoken[\'":\s]+([0-9a-f]{32})', cn)
        if mod:
            s = mod.group(1)
            self._bdstoken = str(s)
            return s
        else:
            return None

    @assert_ok
    def quota(self):
        """Quota space information"""

        url = self._form_url(PcsNode.Quota)
        params = {"method": "info"}
        resp = self._request(Method.Get, url, params=params)
        return resp.json()

    def meta(self, *remotepaths: str):
        assert all(
            [p.startswith("/") for p in remotepaths]
        ), "`remotepaths` must be absolute paths"

        param = [{"path": p} for p in remotepaths]
        return self.file_operate("meta", param)

    def exists(self, remotepath: str) -> bool:
        r = self.meta(remotepath)
        if r.get("error_code"):
            return False
        else:
            return True

    def is_file(self, remotepath: str) -> bool:
        r = self.meta(remotepath)
        if r.get("error_code"):
            return False
        if r["list"][0]["isdir"] == 0:
            return True
        else:
            return False

    def is_dir(self, remotepath: str) -> bool:
        r = self.meta(remotepath)
        if r.get("error_code"):
            return False
        if r["list"][0]["isdir"] == 1:
            return True
        else:
            return False

    @assert_ok
    def list(
        self,
        remotepath: str,
        desc: bool = False,
        name: bool = False,
        time: bool = False,
        size: bool = False,
    ):
        url = self._form_url(PcsNode.File)
        orderby = None
        if name:
            orderby = "name"
        elif time:
            orderby = "time"
        elif size:
            orderby = "size"
        else:
            orderby = "name"

        params = {
            "method": "list",
            "by": orderby,
            "limit": "0-2147483647",
            "order": ["asc", "desc"][desc],
            "path": str(remotepath),
        }
        resp = self._request(Method.Get, url, params=params)
        return resp.json()

    @assert_ok
    def upload_file(
        self,
        io: IO,
        remotepath: str,
        ondup="overwrite",
        callback: Callable[[MultipartEncoderMonitor], None] = None,
    ):
        assert remotepath.startswith("/"), "`remotepath` must be an absolute path"
        remotePath = Path(remotepath)

        url = self._form_url(PcsNode.File)
        params = {
            "method": "upload",
            "ondup": ondup,
            "dir": remotePath.parent.as_posix(),
            "filename": remotePath.name,
            "BDUSS": self._bduss,
        }

        m = MultipartEncoder(fields={"file": ("file", io, "")})
        monitor = MultipartEncoderMonitor(m, callback=callback)

        resp = self._request(Method.Post, url, params=params, data=monitor)
        return resp.json()

    @assert_ok
    def rapid_upload_file(
        self,
        slice_md5: str,
        content_md5: str,
        content_crc32: int,
        io_len: int,
        remotepath: str,
        ondup="overwrite",
    ):
        """size > 256KB"""

        assert remotepath.startswith("/"), "`remotepath` must be an absolute path"

        url = self._form_url(PcsNode.File)
        params = {
            "method": "rapidupload",
            "BDUSS": self._bduss,
        }
        data = {
            "path": remotepath,
            "content-length": io_len,
            "content-md5": content_md5,
            "slice-md5": slice_md5,
            "content-crc32": content_crc32,
            "ondup": ondup,
        }
        resp = self._request(Method.Post, url, params=params, data=data)
        return resp.json()

    @assert_ok
    def upload_slice(
        self, io: IO, callback: Callable[[MultipartEncoderMonitor], None] = None
    ):
        url = self._form_url(PcsNode.File)
        params = {
            "method": "upload",
            "type": "tmpfile",
            "BDUSS": self._bduss,
        }

        m = MultipartEncoder(fields={"file": ("file", io, "")})
        monitor = MultipartEncoderMonitor(m, callback=callback)

        resp = self._request(Method.Post, url, params=params, data=monitor)
        return resp.json()

    @assert_ok
    def combine_slices(self, slice_md5s: List[str], remotepath: str, ondup="overwrite"):
        url = self._form_url(PcsNode.File)
        params = {
            "method": "createsuperfile",
            "path": remotepath,
            "ondup": ondup,
            "BDUSS": self._bduss,
        }
        data = {"param": dump_json({"block_list": slice_md5s})}
        resp = self._request(Method.Post, url, params=params, data=data)
        return resp.json()

    @assert_ok
    def search(self, keyword: str, remotepath: str, recursive: bool = False):
        url = self._form_url(PcsNode.File)
        params = {
            "method": "search",
            "path": remotepath,
            "wd": keyword,
            "re": "1" if recursive else "0",
        }
        resp = self._request(Method.Get, url, params=params)
        return resp.json()

    @assert_ok
    def makedir(self, directory: str):
        url = self._form_url(PcsNode.File)
        params = {
            "method": "mkdir",
            "path": directory,
        }
        resp = self._request(Method.Get, url, params=params)
        return resp.json()

    def file_operate(self, operate: str, param: List[Dict[str, str]]):
        url = self._form_url(PcsNode.File)
        params = {"method": operate}
        data = {"param": dump_json({"list": param})}
        resp = self._request(Method.Post, url, params=params, data=data)
        return resp.json()

    @assert_ok
    def move(self, *remotepaths: str):
        """
        Move sources to destination

        sources, dest = remotepaths[:-1], remotepaths[-1]

        `dest` must be a directory
        """

        assert len(remotepaths) > 1 and all(
            [p.startswith("/") for p in remotepaths]
        ), "`sources`, `dest` must be absolute paths"

        sources, dest = remotepaths[:-1], remotepaths[-1]

        if self.is_file(dest):
            raise BaiduPCSError("The remote `dest` is a file. It must be a directory.")

        if not self.is_dir(dest):
            self.makedir(dest)

        _sources = (Path(s) for s in sources)
        _dest = Path(dest)

        param = [_from_to(str(s), str(_dest / s.name)) for s in _sources]
        return self.file_operate("move", param)

    @assert_ok
    def rename(self, source: str, dest: str):
        """Rename `source` to `dest`"""

        assert all(
            [p.startswith("/") for p in [source, dest]]
        ), "`source`, `dest` must be absolute paths"

        param = [_from_to(source, dest)]
        return self.file_operate("move", param)

    @assert_ok
    def copy(self, *remotepaths: str):
        """
        Copy sources to destination

        sources, dest = remotepaths[:-1], remotepaths[-1]

        `dest` must be a directory
        """

        assert len(remotepaths) > 1 and all(
            [p.startswith("/") for p in remotepaths]
        ), "`sources`, `dest` must be absolute paths"

        sources, dest = remotepaths[:-1], remotepaths[-1]

        if self.is_file(dest):
            raise BaiduPCSError("The remote `dest` is a file. It must be a directory.")

        if not self.is_dir(dest):
            self.makedir(dest)

        _sources = (Path(s) for s in sources)
        _dest = Path(dest)

        param = [_from_to(str(s), str(_dest / s.name)) for s in _sources]
        return self.file_operate("copy", param)

    @assert_ok
    def remove(self, *remotepaths: str):
        assert all(
            [p.startswith("/") for p in remotepaths]
        ), "`sources`, `dest` must be absolute paths"

        param = [{"path": p} for p in remotepaths]
        return self.file_operate("delete", param)

    @assert_ok
    def cloud_operate(self, params: Dict[str, str]):
        url = self._form_url(PcsNode.PanCloud, domain=PAN_BAIDU_COM)
        resp = self._request(Method.Get, url, params=params)
        return resp.json()

    def magnet_info(self, magnet: str):
        params = {
            "method": "query_magnetinfo",
            "source_url": magnet,
            # 'save_path': '/',
            "type": "4",
        }
        return self.cloud_operate(params)

    def torrent_info(self, remote_torrent: str):
        params = {
            "method": "query_sinfo",
            "source_path": remote_torrent,
            # 'save_path': '/',
            "type": "2",
            # 't': int(time.time() * 1000),
        }
        return self.cloud_operate(params)

    def add_task(self, task_url: str, remotedir: str):
        params = {
            "method": "add_task",
            "save_path": remotedir,
            "source_url": task_url,
            "timeout": "2147483647",
        }
        return self.cloud_operate(params)

    def tasks(self, *task_ids: str):
        params = {
            "method": "query_task",
            "task_ids": ",".join(task_ids),
        }
        return self.cloud_operate(params)

    def list_tasks(self):
        params = {
            "method": "list_task",
            "need_task_info": "1",
            "status": "255",
            "start": "0",
            "limit": "1000",
        }
        return self.cloud_operate(params)

    def clear_tasks(self):
        params = {
            "method": "clear_task",
        }
        return self.cloud_operate(params)

    def cancel_task(self, task_id: str):
        params = {
            "method": "cancel_task",
            "task_id": task_id,
        }
        return self.cloud_operate(params)

    @assert_ok
    def share(self, *remotepaths: str, password: Optional[str] = None):
        """Share some paths to public"""

        assert self._stoken, "`STOKEN` is not in `cookies`"

        meta = self.meta(*remotepaths)
        fs_ids = [i["fs_id"] for i in meta["list"]]

        url = self._form_url(PcsNode.Share, domain=PAN_BAIDU_COM)
        params = {
            "channel": "chunlei",
            "clienttype": "0",
            "web": "1",
            "bdstoken": self.bdstoken() or "",
        }
        data = {
            "fid_list": dump_json(fs_ids),
            "schannel": "0",
            "channel_list": "[]",
        }
        if password:
            data["pwd"] = password
            data["schannel"] = "4"

        resp = self._request(Method.Post, url, params=params, data=data)
        info = resp.json()

        # errno: 115, '该文件禁止分享'. 但也能分享出去。。。
        if info.get("errno") == 115:
            info["errno"] = 0  # assign 0 to avoid capture error
        return info

    @assert_ok
    def list_shared(self, page: int = 1):
        """
        list.0.channel:
            - 0, no password
            - 4, with password
        """

        url = self._form_url(PcsNode.SharedRecord, domain=PAN_BAIDU_COM)
        params = {
            "page": str(page),
            "desc": "1",
            "order": "time",
        }
        resp = self._request(Method.Get, url, params=params)
        return resp.json()

    @assert_ok
    def shared_password(self, share_id: int):
        """
        Only return password
        """

        url = self._form_url(PcsNode.SharedPassword, domain=PAN_BAIDU_COM)
        params = {
            "shareid": str(share_id),
            "sign": calu_md5(f"{share_id}_sharesurlinfo!@#"),
        }
        resp = self._request(Method.Get, url, params=params)
        return resp.json()

    @assert_ok
    def cancel_shared(self, *share_ids: int):
        url = self._form_url(PcsNode.SharedCancel, domain=PAN_BAIDU_COM)
        data = {
            "shareid_list": dump_json(share_ids),
        }
        hdrs = dict(PCS_HEADERS)
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
        resp = self._request(Method.Post, url, headers=hdrs, params=None, data=data)
        return resp.json()

    def shared_init_url(self, shared_url: str) -> str:
        u = urlparse(shared_url)
        surl = u.path.split("/s/1")[-1]
        return f"https://pan.baidu.com/share/init?surl={surl}"

    def access_shared(self, shared_url: str, password: str, vcode_str: str, vcode: str):
        """Pass password to the session"""

        url = "https://pan.baidu.com/share/verify"
        init_url = self.shared_init_url(shared_url)
        params = {
            "surl": init_url.split("surl=")[-1],
            "t": str(int(time.time() * 1000)),
            "channel": "chunlei",
            "web": "1",
            "bdstoken": "null",
            "clienttype": "0",
        }
        data = {
            "pwd": password,
            "vcode": vcode,
            "vcode_str": vcode_str,
        }
        hdrs = dict(PAN_HEADERS)
        hdrs["Referer"] = init_url
        resp = self._request(Method.Post, url, headers=hdrs, params=params, data=data)
        info = resp.json()
        err = parse_errno(info.get("errno", 0), str(info))
        if err:
            raise err

    @assert_ok
    def getcaptcha(self, shared_url: str) -> str:
        url = self._form_url(PcsNode.Getcaptcha, domain=PAN_BAIDU_COM)
        params = {
            "prod": "shareverify",
            "channel": "chunlei",
            "web": "1",
            "bdstoken": "null",
            "clienttype": "0",
        }

        hdrs = dict(PAN_HEADERS)
        hdrs["Referer"] = self.shared_init_url(shared_url)
        hdrs["X-Requested-With"] = "XMLHttpRequest"
        hdrs["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        resp = self._request(Method.Get, url, headers=hdrs, params=params)
        return resp.json()

    def get_vcode_img(self, vcode_img_url: str, shared_url: str) -> bytes:
        hdrs = dict(PAN_HEADERS)
        hdrs["Referer"] = self.shared_init_url(shared_url)
        resp = self._request_get(vcode_img_url, headers=hdrs)
        return resp.content

    @assert_ok
    def shared_paths(self, shared_url: str):
        """Get shared paths

        Call `BaiduPCS.access_share` before calling the function
        """

        assert self._stoken, "`STOKEN` is not in `cookies`"

        resp = self._request(Method.Get, shared_url, params=None)
        html = resp.text

        m = re.search(r"yunData.setData\((.+?)\);", html)
        assert m
        shared_data = m.group(1)
        return json.loads(shared_data)

    @assert_ok
    def list_shared_paths(self, sharedpath: str, uk: int, share_id: int):
        assert self._stoken, "`STOKEN` is not in `cookies`"

        url = self._form_url(PcsNode.SharedPathList, domain=PAN_BAIDU_COM)
        params = {
            "channel": "chunlei",
            "clienttype": "0",
            "web": "1",
            "num": "10000",
            "dir": sharedpath,
            "t": str(int(time.time() * 1000)),
            "uk": str(uk),
            "shareid": str(share_id),
            # 'desc': 1,   ## reversely
            "order": "name",  # sort by name, or size, time
            "_": str(int(time.time() * 1000)),
            # 'bdstoken': self._get_bdstoken()
        }
        resp = self._request(Method.Get, url, params=params)
        return resp.json()

    @assert_ok
    def transfer_shared_paths(
        self,
        remotedir: str,
        fs_ids: List[int],
        uk: int,
        share_id: int,
        bdstoken: str,
        shared_url: str,
    ):
        """`remotedir` must exist"""

        url = self._form_url(PcsNode.TransferShared, domain=PAN_BAIDU_COM)
        params = {
            "shareid": str(share_id),
            "from": str(uk),
            "bdstoken": bdstoken,
            "channel": "chunlei",
            "clienttype": "0",
            "web": "1",
        }
        data = {
            "fsidlist": dump_json(fs_ids),
            "path": remotedir,
        }
        hdrs = dict(PAN_HEADERS)
        hdrs["X-Requested-With"] = "XMLHttpRequest"
        hdrs["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        hdrs["Origin"] = "https://pan.baidu.com"
        hdrs["Referer"] = shared_url  # WARNING: Referer must be set to shared_url

        resp = self._request(Method.Post, url, headers=hdrs, params=params, data=data)
        return resp.json()

    @assert_ok
    def user_info(self):
        bduss = self._bduss
        timestamp = str(int(time.time()))
        model = get_phone_model(bduss)
        phoneIMEIStr = sum_IMEI(bduss)

        data = {
            "bdusstoken": bduss + "|null",
            "channel_id": "",
            "channel_uid": "",
            "stErrorNums": "0",
            "subapp_type": "mini",
            "timestamp": timestamp + "922",
        }
        data["_client_type"] = "2"
        data["_client_version"] = "7.0.0.0"
        data["_phone_imei"] = phoneIMEIStr
        data["from"] = "mini_ad_wandoujia"
        data["model"] = model
        data["cuid"] = (
            calu_md5(
                bduss
                + "_"
                + data["_client_version"]
                + "_"
                + data["_phone_imei"]
                + "_"
                + data["from"]
            ).upper()
            + "|"
            + phoneIMEIStr[::-1]
        )
        data["sign"] = calu_md5(
            "".join([k + "=" + data[k] for k in sorted(data.keys())]) + "tiebaclient!!!"
        ).upper()

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": "ka=open",
            "net": "1",
            "User-Agent": "bdtb for Android 6.9.2.1",
            "client_logid": timestamp + "416",
            "Connection": "Keep-Alive",
        }

        resp = requests.post(
            "http://tieba.baidu.com/c/s/login", headers=headers, data=data
        )
        return resp.json()

    @assert_ok
    def tieba_user_info(self, user_id: int):
        params = f"has_plist=0&need_post_count=1&rn=1&uid={user_id}"
        params += "&sign=" + calu_md5(params.replace("&", "") + "tiebaclient!!!")
        url = "http://c.tieba.baidu.com/c/u/user/profile?" + params
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": "ka=open",
            "net": "1",
            "User-Agent": "bdtb for Android 6.9.2.1",
            "client_logid": str(int(time.time() * 1000)),
            "Connection": "Keep-Alive",
        }
        resp = requests.get(url, headers=headers, params=None)
        return resp.json()

    @assert_ok
    def user_products(self):
        url = self._form_url(PcsNode.UserProducts, domain=PAN_BAIDU_COM)
        params = {
            "method": "query",
        }
        resp = self._request(Method.Get, url, params=params)
        return resp.json()

    @assert_ok
    @timeout_cache(1 * 60 * 60)  # 1 hour timeout
    def download_link(self, remotepath: str, pcs: bool = False):
        if pcs:
            return {
                "errno": 0,
                "urls": [
                    {
                        "url": (
                            "http://c.pcs.baidu.com/rest/2.0/pcs/file"
                            f"?method=download&app_id={PCS_APP_ID}&path={quote_plus(remotepath)}"
                            "&ver=2.0&clienttype=1"
                        )
                    }
                ],
            }

        bduss = self._bduss
        uid = str(self._user_id) or ""

        timestamp = str(int(time.time() * 1000))
        devuid = "0|" + calu_md5(bduss).upper()

        enc = calu_sha1(bduss)
        rand = calu_sha1(
            enc + uid + "ebrcUYiuxaZv2XGu7KIYKxUrqfnOfpDF" + timestamp + devuid
        )

        url = self._form_url(PcsNode.File, domain=PCS_BAIDU_COM)
        params = {
            "method": "locatedownload",
            "ver": "2",
            "path": remotepath,
            "time": timestamp,
            "rand": rand,
            "devuid": devuid,
        }

        resp = self._request(Method.Get, url, params=params)
        return resp.json()

    def file_stream(
        self,
        remotepath: str,
        max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE,
        callback: Callable[..., None] = None,
        encrypt_key=Optional[str],
    ) -> RangeRequestIO:
        info = self.download_link(remotepath)
        url = info["urls"][0]["url"]
        headers = {
            "Cookie": "; ".join(
                [f"{k}={v if v is not None else ''}" for k, v in self._cookies.items()]
            ),
            "User-Agent": PCS_UA,
            "Connection": "Keep-Alive",
        }
        return RangeRequestIO(
            Method.Get.value,
            url,
            headers=headers,
            max_chunk_size=max_chunk_size,
            callback=callback,
            encrypt_key=encrypt_key,
        )

    # Playing the m3u8 file is needed add `--stream-lavf-o-append="protocol_whitelist=file,http,https,tcp,tls,crypto,hls,applehttp"` for mpv
    # https://github.com/mpv-player/mpv/issues/6928#issuecomment-532198445
    @assert_ok
    def m3u8_stream(self, remotepath: str, type: M3u8Type = "M3U8_AUTO_720"):
        """Get content of the m3u8 stream file"""

        url = self._form_url(PcsNode.File, domain=PCS_BAIDU_COM)
        params = {
            "method": "streaming",
            "path": remotepath,
            "type": type,
        }

        resp = self._request(Method.Get, url, params=params)
        cn = resp.text
        if cn.startswith("{"):  # error
            return resp.json()
        else:
            return {"m3u8_content": cn}
