from typing import Optional

from baidupcs_py.baidupcs import BaiduPCSApi
from baidupcs_py.common.io import DEFAULT_MAX_CHUNK_SIZE

import chardet


def cat(
    api: BaiduPCSApi,
    remotepath: str,
    max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE,
    encoding: Optional[str] = None,
    encrypt_key=Optional[str],
):
    rangeRequestIO = api.file_stream(remotepath, encrypt_key=encrypt_key)
    cn = rangeRequestIO.read()
    if cn:
        if encoding:
            print(cn.decode(encoding))
        else:
            r = chardet.detect(cn)
            if r["confidence"] > 0.5:
                print(cn.decode(r["encoding"]))
            else:
                print(cn)
