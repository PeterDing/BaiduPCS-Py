from typing import Optional
from typing_extensions import Literal
from pathlib import Path
from os import PathLike

import logging
from logging import Logger


TLogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LogLevels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_LOG_FORMAT = "%(asctime)-15s | %(levelname)s | %(module)s: %(message)s"


def get_logger(
    name: str,
    fmt: str = _LOG_FORMAT,
    filename: Optional[PathLike] = None,
    level: TLogLevel = "ERROR",
) -> Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)

    handler = logging.StreamHandler()  # stdout
    handler.setFormatter(logging.Formatter(fmt))
    logger.addHandler(handler)

    if filename:
        filename = Path(filename)
        _dir = filename.parent
        if not _dir.exists():
            _dir.mkdir()

        handler = logging.FileHandler(filename)
        handler.setFormatter(logging.Formatter(fmt))
        logger.addHandler(handler)

    return logger
