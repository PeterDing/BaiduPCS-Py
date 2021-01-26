from typing import Optional, Dict
from pathlib import Path

import uvicorn

from baidupcs_py.baidupcs import BaiduPCSApi
from baidupcs_py.common.io import RangeRequestIO, READ_SIZE
from baidupcs_py.common.constant import CPU_NUM
from baidupcs_py.utils import format_date

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from jinja2 import Template

app = FastAPI()

_api: Optional[BaiduPCSApi] = None
_root_dir: str = "/"

# This template is from https://github.com/rclone/rclone/blob/master/cmd/serve/httplib/serve/data/templates/index.html
_html_tempt: Template = Template((Path(__file__).parent / "index.html").open().read())


def fake_io(io: RangeRequestIO, start: int = 0, end: int = -1):
    while True:
        length = len(io)
        io.seek(start, 0)
        size = length if end < 0 else end - start + 1

        ranges = io._split_chunk(size)
        for _range in ranges:
            with io._request(_range) as resp:
                stream = resp.raw
                while True:
                    b = stream.read(READ_SIZE)
                    if not b:
                        break
                    yield b
        return


@app.get("{remotepath:path}")
async def http_server(
    request: Request,
    remotepath: str,
    order: str = "asc",  # desc , asc
    sort: str = "name",  # name, time, size
):
    desc = order == "desc"
    name = sort == "name"
    time = sort == "time"
    size = sort == "size"

    global _root_dir
    global _api
    assert _api

    remotepath = remotepath.strip("/")

    _rp = Path(_root_dir) / remotepath
    _rp_str = _rp.as_posix()

    _range = request.headers.get("range")

    if not _api.exists(_rp_str):
        raise HTTPException(status_code=404, detail="Item not found")

    is_dir = _api.is_dir(_rp_str)
    if is_dir:
        chunks = ["/"] + (remotepath.split("/") if remotepath != "" else [])
        navigation = [
            (i - 1, "../" * (len(chunks) - i), name) for i, name in enumerate(chunks, 1)
        ]
        pcs_files = _api.list(_rp_str, desc=desc, name=name, time=time, size=size)
        entries = []
        for f in pcs_files:
            p = Path(f.path)
            entries.append((f.is_dir, p.name, f.size, format_date(f.mtime or 0)))
        cn = _html_tempt.render(
            root_dir=remotepath, navigation=navigation, entries=entries
        )
        return HTMLResponse(cn)
    else:
        range_request_io = _api.file_stream(_rp_str)
        length = len(range_request_io)
        headers: Dict[str, str] = {
            "accept-ranges": "bytes",
            "connection": "Keep-Alive",
        }

        if _range:
            assert _range.startswith("bytes=")

            status_code = 206
            start, end = _range[6:].split("-")
            _s, _e = int(start or 0), int(end or length - 1)
            _io = fake_io(range_request_io, _s, _e)
            headers["content-range"] = f"bytes {_s}-{_e}/{length}"
            headers["content-length"] = str(_e - _s + 1)
        else:
            status_code = 200
            _io = fake_io(range_request_io)
            headers["content-length"] = str(length)
        return StreamingResponse(_io, status_code=status_code, headers=headers)


def start_server(
    api: BaiduPCSApi,
    root_dir: str = "/",
    host: str = "localhost",
    port: int = 8000,
    workers: int = CPU_NUM,
):
    """Create a http server on remote `root_dir`"""

    global _root_dir
    _root_dir = root_dir

    global _api
    if not _api:
        _api = api

    uvicorn.run(
        "baidupcs_py.commands.server:app",
        host=host,
        port=port,
        log_level="info",
        workers=1,
    )
