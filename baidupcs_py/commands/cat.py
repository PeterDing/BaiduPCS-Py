from typing import Optional

from baidupcs_py.baidupcs import BaiduPCSApi
from baidupcs_py.common.io import DEFAULT_MAX_CHUNK_SIZE
from baidupcs_py.commands.display import display_blocked_remotepath

import chardet


def cat(
    api: BaiduPCSApi,
    remotepath: str,
    max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE,
    encoding: Optional[str] = None,
    encrypt_password: bytes = b"",
):
    fs = api.file_stream(remotepath, encrypt_password=encrypt_password)
    if not fs:
        display_blocked_remotepath(remotepath)
        return

    cn = fs.read()
    if cn:
        if encoding:
            print(cn.decode(encoding))
        else:
            r = chardet.detect(cn)
            if r["confidence"] > 0.5:
                print(cn.decode(r["encoding"]))
            else:
                print(cn)
