from typing import Optional
from functools import wraps
import os
import sys
import signal

from baidupcs_py import __version__
from baidupcs_py.baidupcs import BaiduPCSApi, BaiduPCSError
from baidupcs_py.app.account import Account, AccountManager, DEFAULT_DATA_PATH
from baidupcs_py.commands.sifter import (
    IncludeSifter,
    ExcludeSifter,
    IsFileSifter,
    IsDirSifter,
)
from baidupcs_py.commands.display import display_user_info, display_user_infos
from baidupcs_py.commands.list_files import list_files
from baidupcs_py.commands.cat import cat as _cat
from baidupcs_py.commands import file_operators
from baidupcs_py.commands.search import search as _search
from baidupcs_py.commands import cloud as _cloud
from baidupcs_py.commands.download import (
    download as _download,
    Downloader,
    DownloadParams,
    DEFAULT_DOWNLOADER,
    DEFAULT_CONCURRENCY,
    DEFAULT_CHUNK_SIZE,
)
from baidupcs_py.commands.play import play as _play, Player, DEFAULT_PLAYER
from baidupcs_py.commands.upload import upload as _upload, from_tos, CPU_NUM
from baidupcs_py.commands import share as _share

import click

from rich import print
from rich.prompt import Prompt, Confirm
from rich.console import Console

DEBUG = os.getenv("DEBUG")


def handle_signal(sign_num, frame):
    sys.exit(1)


signal.signal(signal.SIGINT, handle_signal)


def handle_error(func):
    """Handle command error wrapper"""

    @wraps(func)
    def wrap(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except BaiduPCSError as err:
            print(f"[bold red]ERROR[/bold red]: BaiduPCSError: {err}")
            if DEBUG:
                console = Console()
                console.print_exception()
        except Exception as err:
            print(f"[bold red]System ERROR[/bold red]: {err}")
            if DEBUG:
                console = Console()
                console.print_exception()

    return wrap


ALIAS = {
    "w": "who",
    "su": "su",
    "ul": "userlist",
    "ua": "useradd",
    "ud": "userdel",
    "l": "ls",
    "f": "search",
    "md": "mkdir",
    "mv": "move",
    "rn": "rename",
    "cp": "copy",
    "rm": "remove",
    "d": "download",
    "p": "play",
    "u": "upload",
    "S": "share",
    "sl": "shared",
    "cs": "cancelshared",
    "s": "save",
    "a": "add",
    "t": "tasks",
    "ct": "cleartasks",
    "cct": "canceltasks",
}


class AliasedGroup(click.Group):
    def get_command(self, ctx, cmd_name):
        # As normal command name
        rv = click.Group.get_command(self, ctx, cmd_name)
        if rv is not None:
            return rv

        # Check alias command name
        if cmd_name not in ALIAS:
            ctx.fail(f"No command: {cmd_name}")

        normal_cmd_name = ALIAS[cmd_name]
        return click.Group.get_command(self, ctx, normal_cmd_name)


_APP_DOC = f"""BaiduPCS App v{__version__}

    \b
    如果第一次使用，你需要运行 `BaiduPCS-Py useradd` 添加 `bduss` 和 `cookies`。
    如何获取 `bduss` 和 `cookies` 见 https://github.com/PeterDing/BaiduPCS-Py#useradd
    用 `BaiduPCS-Py {{command}} --help` 查看具体的用法。"""

_ALIAS_DOC = "Command Alias:\n\n\b\n" + "\n".join(
    [f"{alias: >3} : {cmd}" for alias, cmd in sorted(ALIAS.items(), key=lambda x: x[1])]
)


@click.group(cls=AliasedGroup, help=_APP_DOC, epilog=_ALIAS_DOC)
@click.option(
    "--account-data", type=str, default=DEFAULT_DATA_PATH, help="Account data file"
)
@click.pass_context
def app(ctx, account_data):
    ctx.obj.account_manager = AccountManager.load_data(account_data)


# Account
# {{{


@app.command()
@click.argument("user_id", type=int, default=None, required=False)
@click.pass_context
@handle_error
def who(ctx, user_id):
    """显示当前用户的信息

    也可指定 `user_id`
    """

    am = ctx.obj.account_manager
    account = am.who(user_id)
    if account:
        display_user_info(account.user)
    else:
        print("[italic red]No recent user, please adding or selecting one[/]")


@app.command()
@click.pass_context
@handle_error
def su(ctx):
    """切换当前用户"""

    am = ctx.obj.account_manager
    ls = sorted([a.user for a in am.accounts])
    display_user_infos(*ls)

    user_ids = [str(u.user_id) for u in ls] + [""]
    i = Prompt.ask("Select an user", choices=user_ids)
    user_id = int(i)
    am.su(user_id)
    am.save()


@app.command()
@click.pass_context
@handle_error
def userlist(ctx):
    """显示所有用户"""

    am = ctx.obj.account_manager
    ls = sorted([a.user for a in am.accounts])
    display_user_infos(*ls)


@app.command()
@click.option("--bduss", prompt="bduss", hide_input=True, help="用户 bduss")
@click.option("--cookies", prompt="cookies", hide_input=True, help="用户 cookies")
@click.pass_context
@handle_error
def useradd(ctx, bduss, cookies):
    """添加一个用户并设置为当前用户"""

    cookies = dict([c.split("=", 1) for c in cookies.split("; ")])
    account = Account.from_bduss(bduss, cookies=cookies)
    am = ctx.obj.account_manager
    am.useradd(account.user)
    am.su(account.user.user_id)
    am.save()


@app.command()
@click.pass_context
@handle_error
def userdel(ctx):
    """删除一个用户"""

    am = ctx.obj.account_manager
    ls = sorted([a.user for a in am.accounts])
    display_user_infos(*ls)

    user_ids = [str(u.user_id) for u in ls] + [""]
    i = Prompt.ask("Delete an user", choices=user_ids)
    if not i:
        return

    user_id = int(i)
    am.userdel(user_id)
    am.save()

    print(f"Delete user {user_id}")


def recent_api(ctx) -> Optional[BaiduPCSApi]:
    """Return recent user's `BaiduPCSApi`"""

    am = ctx.obj.account_manager
    account = am.who()
    if not account:
        print("[italic red]No recent user, please adding or selecting one[/]")
        return None
    return account.pcsapi()


# }}}

# Files
# {{{


@app.command()
@click.argument("remotepaths", nargs=-1, type=str)
@click.option("--desc", "-r", is_flag=True, help="逆序排列文件")
@click.option("--name", "-n", is_flag=True, help="依名字排序")
@click.option("--time", "-t", is_flag=True, help="依时间排序")
@click.option("--size", "-s", is_flag=True, help="依文件大小排序")
@click.option("--recursive", "-R", is_flag=True, help="递归列出文件")
@click.option("--include", "-I", type=str, help="筛选包含这个字符串的文件")
@click.option("--include-regex", "--IR", type=str, help="筛选包含这个正则表达式的文件")
@click.option("--exclude", "-E", type=str, help="筛选 不 包含这个字符串的文件")
@click.option("--exclude-regex", "--ER", type=str, help="筛选 不 包含这个正则表达式的文件")
@click.option("--is-file", "-f", is_flag=True, help="筛选 非 目录文件")
@click.option("--is-dir", "-d", is_flag=True, help="筛选目录文件")
@click.option("--no-highlight", "--NH", is_flag=True, help="取消匹配高亮")
@click.option("--show-size", "-S", is_flag=True, help="显示文件大小")
@click.option("--show-date", "-D", is_flag=True, help="显示文件创建时间")
@click.option("--show-md5", "-M", is_flag=True, help="显示文件md5")
@click.option("--show-absolute-path", "-A", is_flag=True, help="显示文件绝对路径")
@click.pass_context
@handle_error
def ls(
    ctx,
    remotepaths,
    desc,
    name,
    time,
    size,
    recursive,
    include,
    include_regex,
    exclude,
    exclude_regex,
    is_file,
    is_dir,
    no_highlight,
    show_size,
    show_date,
    show_md5,
    show_absolute_path,
):
    """列出网盘路径下的文件"""

    api = recent_api(ctx)
    if not api:
        return

    sifters = []
    if include:
        sifters.append(IncludeSifter(include, regex=False))
    if include_regex:
        sifters.append(IncludeSifter(include, regex=True))
    if exclude:
        sifters.append(ExcludeSifter(exclude, regex=False))
    if exclude_regex:
        sifters.append(ExcludeSifter(exclude_regex, regex=True))
    if is_file:
        sifters.append(IsFileSifter())
    if is_dir:
        sifters.append(IsDirSifter())

    list_files(
        api,
        *remotepaths,
        desc=desc,
        name=name,
        time=time,
        size=size,
        recursive=recursive,
        sifters=sifters,
        highlight=not no_highlight,
        show_size=show_size,
        show_date=show_date,
        show_md5=show_md5,
        show_absolute_path=show_absolute_path,
    )


@app.command()
@click.argument("keyword", nargs=1, type=str)
@click.argument("remotedir", nargs=1, type=str, default="/")
@click.option("--recursive", "-R", is_flag=True, help="递归搜索文件")
@click.option("--include", "-I", type=str, help="筛选包含这个字符串的文件")
@click.option("--include-regex", "--IR", type=str, help="筛选包含这个正则表达式的文件")
@click.option("--exclude", "-E", type=str, help="筛选 不 包含这个字符串的文件")
@click.option("--exclude-regex", "--ER", type=str, help="筛选 不 包含这个正则表达式的文件")
@click.option("--is-file", "-f", is_flag=True, help="筛选 非 目录文件")
@click.option("--is-dir", "-d", is_flag=True, help="筛选目录文件")
@click.option("--no-highlight", "--NH", is_flag=True, help="取消匹配高亮")
@click.option("--show-size", "-S", is_flag=True, help="显示文件大小")
@click.option("--show-date", "-D", is_flag=True, help="显示文件创建时间")
@click.option("--show-md5", "-M", is_flag=True, help="显示文件md5")
@click.pass_context
@handle_error
def search(
    ctx,
    keyword,
    remotedir,
    recursive,
    include,
    include_regex,
    exclude,
    exclude_regex,
    is_file,
    is_dir,
    no_highlight,
    show_size,
    show_date,
    show_md5,
):
    """搜索包含 `keyword` 的文件"""

    api = recent_api(ctx)
    if not api:
        return

    sifters = []
    if include:
        sifters.append(IncludeSifter(include, regex=False))
    if include_regex:
        sifters.append(IncludeSifter(include, regex=True))
    if exclude:
        sifters.append(ExcludeSifter(exclude, regex=False))
    if exclude_regex:
        sifters.append(ExcludeSifter(exclude_regex, regex=True))
    if is_file:
        sifters.append(IsFileSifter())
    if is_dir:
        sifters.append(IsDirSifter())

    _search(
        api,
        keyword,
        remotedir,
        recursive=recursive,
        sifters=sifters,
        highlight=not no_highlight,
        show_size=show_size,
        show_date=show_date,
        show_md5=show_md5,
    )


@app.command()
@click.argument("remotepath", nargs=1, type=str)
@click.option("--encoding", "-e", type=str, default="utf-8", help="文件编码，默认为 utf-8")
@click.pass_context
@handle_error
def cat(ctx, remotepath):
    api = recent_api(ctx)
    if not api:
        return

    _cat(api, remotepath)


@app.command()
@click.argument("remotedirs", nargs=-1, type=str)
@click.option("--show", "-S", is_flag=True, help="显示目录")
@click.pass_context
@handle_error
def mkdir(ctx, remotedirs, show):
    """创建目录"""

    api = recent_api(ctx)
    if not api:
        return

    file_operators.makedir(api, *remotedirs, show=show)


@app.command()
@click.argument("remotepaths", nargs=-1, type=str)
@click.option("--show", "-S", is_flag=True, help="显示结果")
@click.pass_context
@handle_error
def move(ctx, remotepaths, show):
    """移动文件

    \b
    examples:
        move /file1 /file2 /to/dir
    """

    api = recent_api(ctx)
    if not api:
        return

    if len(remotepaths) < 2:
        ctx.fail("remote paths < 2")
    file_operators.move(api, *remotepaths, show=show)


@app.command()
@click.argument("source", nargs=1, type=str)
@click.argument("dest", nargs=1, type=str)
@click.option("--show", "-S", is_flag=True, help="显示结果")
@click.pass_context
@handle_error
def rename(ctx, source, dest, show):
    """文件重命名

    \b
    examples:
        rename /path/to/far /to/here/foo
    """

    api = recent_api(ctx)
    if not api:
        return

    file_operators.rename(api, source, dest, show=show)


@app.command()
@click.argument("remotepaths", nargs=-1, type=str)
@click.option("--show", "-S", is_flag=True, help="显示结果")
@click.pass_context
@handle_error
def copy(ctx, remotepaths, show):
    """拷贝文件

    \b
    examples:
        copy /file1 /file2 /to/dir
    """

    api = recent_api(ctx)
    if not api:
        return

    if len(remotepaths) < 2:
        ctx.fail("remote paths < 2")
    file_operators.copy(api, *remotepaths, show=show)


@app.command()
@click.argument("remotepaths", nargs=-1, type=str)
@click.pass_context
@handle_error
def remove(ctx, remotepaths):
    """删除文件"""

    api = recent_api(ctx)
    if not api:
        return

    file_operators.remove(api, *remotepaths)


@app.command()
@click.argument("remotepaths", nargs=-1, type=str)
@click.option("--outdir", "-o", nargs=1, type=str, default=".", help="指定下载本地目录，默认为当前目录")
@click.option("--recursive", "-R", is_flag=True, help="递归下载")
@click.option(
    "--from-index", "-f", type=int, default=0, help="从所有目录中的第几个文件开始下载，默认为0（第一个）"
)
@click.option("--include", "-I", type=str, help="筛选包含这个字符串的文件")
@click.option("--include-regex", "--IR", type=str, help="筛选包含这个正则表达式的文件")
@click.option("--exclude", "-E", type=str, help="筛选 不 包含这个字符串的文件")
@click.option("--exclude-regex", "--ER", type=str, help="筛选 不 包含这个正则表达式的文件")
@click.option(
    "-d",
    "--downloader",
    type=click.Choice([d.name for d in Downloader]),
    default=DEFAULT_DOWNLOADER.name,
    help="""指定下载应用

    \b
    默认为 me (BaiduPCS-Py 自己的下载器，不支持断续下载)
        me 使用多文件并发下载。

    除 me 外，其他下载器，不使用多文件并发下载，使用一个文件多链接下载。
    如果需要下载多个小文件推荐使用 me，如果需要下载少量大文件推荐使用其他下载器。

    \b
    aget_py (https://github.com/PeterDing/aget) 默认安装
    aget_rs (下载 https://github.com/PeterDing/aget-rs/releases)
    aria2 (下载 https://github.com/aria2/aria2/releases)
    """,
)
@click.option(
    "--concurrency",
    "-s",
    type=int,
    default=DEFAULT_CONCURRENCY,
    help="下载同步链接数，默认为5。数子越大下载速度越快，但是容易被百度封锁",
)
@click.option(
    "--chunk-size", "-k", type=str, default=DEFAULT_CHUNK_SIZE, help="同步链接分块大小"
)
@click.option("--quiet", "-q", is_flag=True, help="取消第三方下载应用输出")
@click.pass_context
@handle_error
def download(
    ctx,
    remotepaths,
    outdir,
    recursive,
    from_index,
    include,
    include_regex,
    exclude,
    exclude_regex,
    downloader,
    concurrency,
    chunk_size,
    quiet,
):
    """下载文件"""

    api = recent_api(ctx)
    if not api:
        return

    sifters = []
    if include:
        sifters.append(IncludeSifter(include, regex=False))
    if include_regex:
        sifters.append(IncludeSifter(include, regex=True))
    if exclude:
        sifters.append(ExcludeSifter(exclude, regex=False))
    if exclude_regex:
        sifters.append(ExcludeSifter(exclude_regex, regex=True))

    _download(
        api,
        remotepaths,
        outdir,
        sifters=sifters,
        recursive=recursive,
        from_index=from_index,
        downloader=getattr(Downloader, downloader),
        downloadparams=DownloadParams(
            concurrency=concurrency, chunk_size=chunk_size, quiet=quiet
        ),
    )


@app.command()
@click.argument("remotepaths", nargs=-1, type=str)
@click.option("--recursive", "-R", is_flag=True, help="递归播放")
@click.option(
    "--from-index", "-f", type=int, default=0, help="从所有目录中的第几个文件开始播放，默认为0（第一个）"
)
@click.option("--include", "-I", type=str, help="筛选包含这个字符串的文件")
@click.option("--include-regex", "--IR", type=str, help="筛选包含这个正则表达式的文件")
@click.option("--exclude", "-E", type=str, help="筛选 不 包含这个字符串的文件")
@click.option("--exclude-regex", "--ER", type=str, help="筛选 不 包含这个正则表达式的文件")
@click.option(
    "-p",
    "--player",
    type=click.Choice([d.name for d in Player]),
    default=DEFAULT_PLAYER.name,
    help="""指定第三方播放器

    \b
    默认为 mpv (https://mpv.io),
    """,
)
@click.option("--m3u8", "-m", is_flag=True, help="获取m3u8文件并播放")
@click.option("--quiet", "-q", is_flag=True, help="取消第三方播放器输出")
@click.pass_context
@handle_error
def play(
    ctx,
    remotepaths,
    recursive,
    from_index,
    include,
    include_regex,
    exclude,
    exclude_regex,
    player,
    m3u8,
    quiet,
):
    """下载文件"""

    api = recent_api(ctx)
    if not api:
        return

    sifters = []
    if include:
        sifters.append(IncludeSifter(include, regex=False))
    if include_regex:
        sifters.append(IncludeSifter(include, regex=True))
    if exclude:
        sifters.append(ExcludeSifter(exclude, regex=False))
    if exclude_regex:
        sifters.append(ExcludeSifter(exclude_regex, regex=True))

    _play(
        api,
        remotepaths,
        sifters=sifters,
        recursive=recursive,
        from_index=from_index,
        player=getattr(Player, player),
        m3u8=m3u8,
        quiet=quiet,
    )


@app.command()
@click.argument("localpaths", nargs=-1, type=str)
@click.argument("remotedir", nargs=1, type=str)
@click.option("--max-workers", "-w", type=int, default=CPU_NUM, help="同时上传文件数")
@click.option("--no-ignore-existing", "--NI", is_flag=True, help="上传已经存在的文件")
@click.option("--no-show-progress", "--NP", is_flag=True, help="不显示上传进度")
@click.pass_context
@handle_error
def upload(
    ctx, localpaths, remotedir, max_workers, no_ignore_existing, no_show_progress
):
    """上传文件"""

    api = recent_api(ctx)
    if not api:
        return

    from_to_list = from_tos(localpaths, remotedir)
    _upload(
        api,
        from_to_list,
        max_workers=max_workers,
        ignore_existing=not no_ignore_existing,
        show_progress=not no_show_progress,
    )


# }}}


# Share
# {{{
@app.command()
@click.argument("remotepaths", nargs=-1, type=str)
@click.option("--password", "-p", type=str, help="设置秘密，4个字符。默认没有秘密")
@click.pass_context
@handle_error
def share(ctx, remotepaths, password):
    """分享文件

    \b
    examples:
        share /path1 path2
    """
    assert not password or len(password) == 4, "`password` must be 4 letters"

    api = recent_api(ctx)
    if not api:
        return

    _share.share_files(api, *remotepaths, password=password)


@app.command()
@click.option("--show-all", "-S", is_flag=True, help="显示所有分享的链接，默认只显示有效的分享链接")
@click.pass_context
@handle_error
def shared(ctx, show_all):
    """列出分享链接"""

    api = recent_api(ctx)
    if not api:
        return

    _share.list_shared(api, show_all=show_all)


@app.command()
@click.argument("share_ids", nargs=-1, type=int)
@click.pass_context
@handle_error
def cancelshared(ctx, share_ids):
    """取消分享链接"""

    api = recent_api(ctx)
    if not api:
        return

    _share.cancel_shared(api, *share_ids)


@app.command()
@click.argument("shared_url", nargs=1, type=str)
@click.argument("remotedir", nargs=1, type=str)
@click.option("--password", "-p", type=str, help="链接密码，如果没有不用设置")
@click.option("--no-show-vcode", "--NV", is_flag=True)
@click.pass_context
@handle_error
def save(ctx, shared_url, remotedir, password, no_show_vcode):
    """保存其他用户分享的链接"""

    assert not password or len(password) == 4, "`password` must be 4 letters"

    api = recent_api(ctx)
    if not api:
        return

    _share.save_shared(
        api,
        shared_url,
        remotedir,
        password=password,
        show_vcode=not no_show_vcode,
    )


# }}}

# Cloud
# {{{


@app.command()
@click.argument("task_urls", nargs=-1, type=str)
@click.argument("remotedir", nargs=1, type=str)
@click.pass_context
@handle_error
def add(ctx, task_urls, remotedir):
    """添加离线下载任务"""

    api = recent_api(ctx)
    if not api:
        return

    for url in task_urls:
        _cloud.add_task(api, url, remotedir)


@app.command()
@click.argument("task_ids", nargs=-1, type=str)
@click.pass_context
@handle_error
def tasks(ctx, task_ids):
    """列出离线下载任务。也可列出给定id的任务"""

    api = recent_api(ctx)
    if not api:
        return

    if not task_ids:
        _cloud.list_tasks(api)
    else:
        _cloud.tasks(api, *task_ids)


@app.command()
@click.pass_context
@handle_error
def cleartasks(ctx):
    """清除已经下载完和下载失败的任务"""

    api = recent_api(ctx)
    if not api:
        return

    _cloud.clear_tasks(api)


@app.command()
@click.argument("task_ids", nargs=-1, type=str)
@click.pass_context
@handle_error
def canceltasks(ctx, task_ids):
    """取消下载任务"""

    api = recent_api(ctx)
    if not api:
        return

    for task_id in task_ids:
        _cloud.cancel_task(api, task_id)


@app.command()
@click.option("--yes", is_flag=True, help="确定直接运行")
@click.pass_context
@handle_error
def purgetasks(ctx, yes):
    """删除所有离线下载任务"""

    api = recent_api(ctx)
    if not api:
        return

    if not yes:
        if not Confirm.ask("确定删除[i red]所有的[/i red]离线下载任务?", default=False):
            return
    _cloud.purge_all_tasks(api)


# }}}
