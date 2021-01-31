import os
from pathlib import Path

from baidupcs_py.common.log import LogLevels, get_logger as _get_logger
from baidupcs_py.commands.env import LOG_LEVEL, LOG_PATH


def get_logger(name: str):
    _LOG_PATH = Path(os.getenv("LOG_FILENAME") or LOG_PATH)
    _LOG_LEVEL = os.getenv("LOG_LEVEL", LOG_LEVEL).upper()
    assert _LOG_LEVEL in LogLevels

    return _get_logger(name, filename=_LOG_PATH, level=_LOG_LEVEL)
