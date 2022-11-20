from typing import Optional
from typing_extensions import Literal, Final
from pathlib import Path
from os import PathLike

import logging
from logging import Logger


TLogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LogLevels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
DEFAULT_LOG_LEVEL: Final = "ERROR"

_LOG_FORMAT = "%(asctime)-15s | %(levelname)s | %(module)s: %(message)s"


def get_logger(
    name: str,
    fmt: str = _LOG_FORMAT,
    filename: Optional[PathLike] = None,
    level: TLogLevel = DEFAULT_LOG_LEVEL,
) -> Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)

    stream_handler = logging.StreamHandler()  # stdout
    stream_handler.setFormatter(logging.Formatter(fmt))
    logger.addHandler(stream_handler)

    if filename:
        filename = Path(filename)
        _dir = filename.parent
        if not _dir.exists():
            _dir.mkdir()

        file_handler = logging.FileHandler(filename)
        file_handler.setFormatter(logging.Formatter(fmt))
        logger.addHandler(file_handler)

    return logger
