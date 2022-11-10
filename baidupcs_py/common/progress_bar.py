from typing import Optional

from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn,
    TaskID,
)

_progress = Progress(
    SpinnerColumn(),
    TextColumn("[bold blue]{task.fields[title]}", justify="right"),
    BarColumn(bar_width=40),
    "[progress.percentage]{task.percentage:>3.1f}%",
    "•",
    DownloadColumn(binary_units=True),
    "•",
    TransferSpeedColumn(),
    "•",
    TimeRemainingColumn(),
)


def init_progress_bar():
    if not _progress.live._started:
        _progress.start()


def exit_progress_bar():
    if _progress.live._started:
        _progress.stop()


def progress_task_exists(task_id: Optional[TaskID]) -> bool:
    if task_id is None:
        return False
    return task_id in _progress.task_ids
