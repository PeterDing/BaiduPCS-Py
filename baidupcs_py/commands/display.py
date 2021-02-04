from typing import Optional, List, Tuple, Union, Pattern
from pathlib import Path
import time
import datetime


from baidupcs_py.baidupcs import PcsFile, FromTo, CloudTask, PcsSharedLink, PcsUser
from baidupcs_py.commands.sifter import Sifter, sift
from baidupcs_py.utils import format_date, human_size

from rich.console import Console
from rich.table import Table
from rich.box import SIMPLE
from rich.text import Text
from rich.highlighter import Highlighter as RichHighlighter
from rich.panel import Panel
from rich.style import Style


class Highlighter(RichHighlighter):
    def __init__(self, patterns: List[Union[Pattern, str]], style: Union[str, Style]):
        super().__init__()
        self.patterns = patterns
        self.style = style

    def highlight(self, text: Text):
        for pat in self.patterns:
            if isinstance(pat, Pattern):
                for m in pat.finditer(text.plain):
                    text.stylize(style=self.style, start=m.start(), end=m.end())
            else:
                pat_len = len(pat)
                start = 0
                while True:
                    idx = text.plain.find(pat, start)
                    if idx == -1:
                        break
                    text.stylize(style=self.style, start=idx, end=idx + pat_len)
                    start = idx + 1


def display_files(
    pcs_files: List[PcsFile],
    remotepath: Optional[str],
    sifters: List[Sifter] = [],
    highlight: bool = False,
    show_size: bool = False,
    show_date: bool = False,
    show_md5: bool = False,
    show_absolute_path: bool = False,
):
    pcs_files = sift(pcs_files, sifters)
    if not pcs_files:
        return

    table = Table(box=SIMPLE, padding=0, show_edge=False)
    table.add_column()
    if show_size:
        table.add_column("Size", justify="right")
    if show_date:
        table.add_column("Modified Time", justify="center")
    if show_md5:
        table.add_column("md5", justify="left")
    table.add_column("Path", justify="left", overflow="fold")

    for pcs_file in pcs_files:
        row: List[Union[str, Text]] = []
        tp = Text("-", style="bold red")
        row.append(tp)
        if show_size:
            size = human_size(pcs_file.size) if pcs_file.size else ""
            row.append(size)
        if show_date:
            date = format_date(pcs_file.mtime) if pcs_file.mtime else ""
            row.append(date)
        if show_md5:
            md5 = pcs_file.md5 or ""
            row.append(md5)

        path = pcs_file.path if show_absolute_path else Path(pcs_file.path).name
        background = Text()
        if pcs_file.is_dir:
            tp._text = ["d"]
            background.style = "blue"

        if highlight and sifters:
            pats: List[Union[Pattern, str]] = list(
                filter(
                    None, [sifter.pattern() for sifter in sifters if sifter.include()]
                )
            )
            highlighter = Highlighter(pats, "yellow")
            _path = highlighter(path)
        else:
            _path = Text(path)

        row.append(background + _path)

        table.add_row(*row)

    console = Console()
    if remotepath:
        title = Text(remotepath, style="italic green")
        console.print(title)
    console.print(table)


def display_from_to(*from_to_list: FromTo):
    if not from_to_list:
        return

    table = Table(box=SIMPLE, padding=0, show_edge=False)
    table.add_column("From", justify="left", overflow="fold")
    table.add_column("To", justify="left", overflow="fold")

    for from_to in from_to_list:
        table.add_row(from_to.from_, from_to.to_)

    console = Console()
    console.print(table)


_TASK_FORMAT = (
    "task_id: [bold white]{task_id}[/bold white]\n"
    "task name: [bold green]{task_name}[/bold green]\n"
    "source_url: [bold]{source_url}[/bold]\n"
    "remotepath: {path}\n"
    "status: [red]{status}[/red]\n"
    "[bold white]{percent}[/bold white]  "
    "[bold yellow]{finished_size}/{size}[/bold yellow]"
)


def display_tasks(*tasks: CloudTask):
    panels = []
    for task in tasks:
        status = task.status_mean()
        size = human_size(task.size)
        finished_size = human_size(task.finished_size)
        if task.size != 0:
            percent = f"{task.finished_size / task.size * 100:.1f}%"
        else:
            percent = "0%"

        info = task._asdict()
        info["status"] = status
        info["percent"] = percent
        info["finished_size"] = finished_size
        info["size"] = size

        panel = Panel(_TASK_FORMAT.format(**info), highlight=True)
        panels.append(panel)

    console = Console()
    console.print(*panels)


_SHARED_LINK_FORMAT = (
    "share id: {share_id}\n"
    "shared url: [bold]{url}[/bold]\n"
    "password: [bold red]{password}[/bold red]\n"
    "paths: {paths}"
)


def display_shared_links(*shared_links: PcsSharedLink):
    panels = []
    for shared_link in shared_links:
        share_id = shared_link.share_id
        url = shared_link.url
        password = shared_link.password or ""
        paths = "\n       ".join(shared_link.paths or [])

        panel = Panel(
            _SHARED_LINK_FORMAT.format(
                share_id=share_id, url=url, password=password, paths=paths
            ),
            highlight=True,
        )
        panels.append(panel)

    console = Console()
    console.print(*panels)


def display_user_info(user_info: PcsUser):
    user_id, user_name, auth, age, sex, quota, products, level = user_info
    bduss = auth and auth.bduss
    quota_str = ""
    if quota:
        quota_str = human_size(quota.used) + "/" + human_size(quota.quota)

    products_str = ""
    for p in products or []:
        name = p.name
        start_date = format_date(p.start_time)
        end_date = format_date(p.end_time)
        avail = str(datetime.timedelta(seconds=(int(p.end_time - time.time()))))
        value = f"From {start_date} to {end_date}, left {avail}"
        products_str += f"\n    {name}: {value}"

    _tempt = (
        f"user id: {user_id}\n"
        f"user name: {user_name}\n"
        f"bduss: {bduss}\n"
        f"age: {age}\n"
        f"sex: {sex}\n"
        f"quota: {quota_str}\n"
        f"level: {level}\n"
        f"products:{products_str}\n"
    )

    console = Console()
    console.print(_tempt, highlight=True)


def display_user_infos(
    *user_infos: Tuple[PcsUser, str], recent_user_id: Optional[int] = None
):
    """
    Args:
        user_infos (*Tuple[PcsUser, pwd: str])
    """

    table = Table(box=SIMPLE, show_edge=False, highlight=True)
    table.add_column("Index", justify="left")
    table.add_column("Recent", justify="left")
    table.add_column("User Id", justify="left", overflow="fold")
    table.add_column("User Name", justify="left", overflow="fold")
    table.add_column("Quota", justify="left")
    table.add_column("SVIP", justify="left", overflow="fold")
    table.add_column("VIP", justify="left", overflow="fold")
    table.add_column("Level", justify="left")
    table.add_column("pwd", justify="left", overflow="fold")

    for idx, (user_info, pwd) in enumerate(user_infos, 1):
        user_id, user_name, auth, age, sex, quota, products, level = user_info

        is_recent = "[green]✔[/green]" if user_id == recent_user_id else ""

        quota_str = ""
        if quota:
            quota_str = human_size(quota.used) + "/" + human_size(quota.quota)

        svip = "[red]✘[/red]"
        vip = "[red]✘[/red]"

        assert products
        for p in products or []:
            avail = str(datetime.timedelta(seconds=(int(p.end_time - time.time()))))
            if p.name.startswith("svip2_nd"):
                svip = f"Left [green]{avail}[/green]"
                continue
            if p.name.startswith("contentvip_nd"):
                vip = f"Left [green]{avail}[/green]"
                continue

        table.add_row(
            str(idx),
            is_recent,
            str(user_id),
            user_name,
            quota_str,
            svip,
            vip,
            str(level),
            pwd,
        )

    console = Console()
    console.print(table)
