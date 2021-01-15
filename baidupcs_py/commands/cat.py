from baidupcs_py.baidupcs import BaiduPCSApi
from baidupcs_py.common.io import RangeRequestIO, DEFAULT_MAX_CHUNK_SIZE


def cat(
    api: BaiduPCSApi,
    remotepath: str,
    max_chunk_size: int = DEFAULT_MAX_CHUNK_SIZE,
    encoding: str = "utf-8",
):
    rangeRequestIO = api.file_stream(remotepath)
    cn = rangeRequestIO.read()
    if cn:
        print(cn.decode(encoding))
