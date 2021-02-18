import os

# Enable UTF-8 Mode for Windows
# https://www.python.org/dev/peps/pep-0540/
if os.name == "nt":
    os.environ["PYTHONUTF8"] = "1"

from typing import Optional, List
from collections import OrderedDict
from functools import wraps
from multiprocessing import Process
import signal
import time
import logging
import traceback

from baidupcs_py import __version__
from baidupcs_py.baidupcs import BaiduPCSApi, BaiduPCSError
from baidupcs_py.app.account import Account, AccountManager
from baidupcs_py.commands.env import ACCOUNT_DATA_PATH
from baidupcs_py.common.progress_bar import _progress
from baidupcs_py.common.path import join_path
from baidupcs_py.common.net import random_avail_port
from baidupcs_py.common.io import EncryptType
from baidupcs_py.common.event import keyboard_listener_start
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
from baidupcs_py.commands.sync import sync as _sync
from baidupcs_py.commands import share as _share
from baidupcs_py.commands.server import start_server
from baidupcs_py.commands.log import get_logger

import click

from rich import print
from rich.console import Console
from rich.prompt import Prompt, Confirm

logger = get_logger(__name__)

DEBUG = logger.level == logging.DEBUG


def handle_signal(sign_num, frame):
    logger.debug("`app`: handle_signal: %s", sign_num)

    if _progress.live._started:
        print()
        # Stop _progress, otherwise terminal stdout will be contaminated
        _progress.stop()

    # No use sys.exit() which only exits the main thread
    os._exit(1)


signal.signal(signal.SIGINT, handle_signal)


def handle_error(func):
    """Handle command error wrapper"""

    @wraps(func)
    def wrap(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except BaiduPCSError as err:
            logger.debug("`app`: BaiduPCSError: %s", traceback.format_exc())

            print(f"(v{__version__}) [bold red]ERROR[/bold red]: BaiduPCSError: {err}")
            if DEBUG:
                console = Console()
                console.print_exception()
        except Exception as err:
            logger.debug("`app`: System Error: %s", traceback.format_exc())

            print(f"(v{__version__}) [bold red]System ERROR[/bold red]: {err}")
            if DEBUG:
                console = Console()
                console.print_exception()

    return wrap


def _user_ids(ctx) -> Optional[List[int]]:
    """Select use_ids by their name probes"""

    am = ctx.obj.account_manager
    user_name_probes = ctx.obj.users

    user_ids = []
    for user_id, account in am._accounts.items():
        user_name = account.user.user_name
        for probe in user_name_probes:
            if probe in user_name:
                user_ids.append(user_id)
                break
    return user_ids


def _change_account(ctx, user_id: int):
    """Change recent account with `user_id`"""

    am = ctx.obj.account_manager
    am.su(user_id)


def multi_user_do(func):
    """Run command on multi users"""

    @wraps(func)
    def wrap(*args, **kwargs):
        ctx = args[0]
        user_ids = _user_ids(ctx)
        if not user_ids:
            return func(*args, **kwargs)

        am = ctx.obj.account_manager
        for user_id in user_ids:
            accout = am.who(user_id)
            if not accout:
                continue

            user_name = accout.user.user_name
            print(
                "[i yellow]@Do[/i yellow]: "
                f"user_name: [b]{user_name}[/b], "
                f"user_id: [b]{user_id}[/b]"
            )
            _change_account(ctx, user_id)
            func(*args, **kwargs)
            print()

    return wrap


def _recent_account(ctx) -> Optional[Account]:
    """Return recent user's `BaiduPCSApi`"""

    am = ctx.obj.account_manager
    account = am.who()
    if account:
        return account
    else:
        print("[italic red]No recent user, please adding or selecting one[/]")
        return None


def _recent_api(ctx) -> Optional[BaiduPCSApi]:
    """Return recent user's `BaiduPCSApi`"""

    account = _recent_account(ctx)
    if account:
        return account.pcsapi()
    else:
        return None


def _pwd(ctx) -> str:
    """Return recent user's pwd"""

    am = ctx.obj.account_manager
    return am.pwd


def _encrypt_password(ctx) -> bytes:
    """Return recent user's encryption key"""

    account = _recent_account(ctx)
    if account:
        ep = account.encrypt_password
        return bytes(ep or "", encoding="utf-8")
    else:
        return b""


def _salt(ctx) -> bytes:
    """Return recent user's encryption key"""

    account = _recent_account(ctx)
    if account:
        salt = account.salt
        return bytes(salt or "", encoding="utf-8")
    else:
        return b""


ALIAS = OrderedDict(
    **{
        "w": "who",
        "uu": "updateuser",
        "su": "su",
        "ul": "userlist",
        "ua": "useradd",
        "ud": "userdel",
        "ep": "encryptpwd",
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
        "sn": "sync",
        "S": "share",
        "sl": "shared",
        "cs": "cancelshared",
        "s": "save",
        "a": "add",
        "t": "tasks",
        "ct": "cleartasks",
        "cct": "canceltasks",
        "sv": "server",
    }
)


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

    def list_commands(self, ctx):
        return self.commands


_APP_DOC = f"""BaiduPCS App v{__version__}

    \b
    如果第一次使用，你需要运行 `BaiduPCS-Py useradd` 添加 `bduss` 和 `cookies`。
    如何获取 `bduss` 和 `cookies` 见 https://github.com/PeterDing/BaiduPCS-Py#%E6%B7%BB%E5%8A%A0%E7%94%A8%E6%88%B7
    用 `BaiduPCS-Py {{command}} --help` 查看具体的用法。"""

_ALIAS_DOC = "Command 别名:\n\n\b\n" + "\n".join(
    [f"{alias: >3} : {cmd}" for alias, cmd in ALIAS.items()]
)


@click.group(cls=AliasedGroup, help=_APP_DOC, epilog=_ALIAS_DOC)
@click.option(
    "--account-data", type=str, default=ACCOUNT_DATA_PATH, help="Account data file"
)
@click.option("--users", type=str, default=None, help="用户名片段，用“,”分割")
@click.pass_context
def app(ctx, account_data, users):
    ctx.obj.account_manager = AccountManager.load_data(account_data)
    ctx.obj.users = [] if users is None else users.split(",")


# Account
# {{{


@app.command()
@click.argument("user_id", type=int, default=None, required=False)
@click.option("--show-encrypt-password", "-K", is_flag=True, help="显示加密密码")
@click.pass_context
@handle_error
def who(ctx, user_id, show_encrypt_password):
    """显示当前用户的信息

    也可指定 `user_id`
    """

    am = ctx.obj.account_manager
    account = am.who(user_id)
    if account:
        display_user_info(account.user)
        if show_encrypt_password:
            encrypt_password = _encrypt_password(ctx)
            salt = _salt(ctx)

            print(f"[red]encrypt password[/red]: {encrypt_password}")
            print(f"[red]salt[/red]: {salt}")
    else:
        print("[italic red]No recent user, please adding or selecting one[/]")


@app.command()
@click.argument("user_ids", type=int, nargs=-1, default=None, required=False)
@click.pass_context
@handle_error
def updateuser(ctx, user_ids):
    """更新用户信息 （默认更新当前用户信息）

    也可指定多个 `user_id`
    """

    am = ctx.obj.account_manager
    if not user_ids:
        user_ids = [am._who]

    for user_id in user_ids:
        am.update(user_id)
        account = am.who(user_id)
        display_user_info(account.user)

    am.save()


@app.command()
@click.pass_context
@handle_error
def su(ctx):
    """切换当前用户"""

    am = ctx.obj.account_manager
    ls = sorted([(a.user, a.pwd) for a in am.accounts])
    display_user_infos(*ls, recent_user_id=am._who)

    indexes = list(str(idx) for idx in range(1, len(ls) + 1))
    i = Prompt.ask("Select an user index", choices=indexes, default="")
    if not i:
        return

    user_id = ls[int(i) - 1][0].user_id
    am.su(user_id)
    am.save()


@app.command()
@click.pass_context
@handle_error
def userlist(ctx):
    """显示所有用户"""

    am = ctx.obj.account_manager
    ls = sorted([(a.user, a.pwd) for a in am.accounts])
    display_user_infos(*ls, recent_user_id=am._who)


@app.command()
@click.option("--bduss", prompt="bduss", hide_input=True, default="", help="用户 bduss")
@click.option(
    "--cookies", prompt="cookies", hide_input=True, default="", help="用户 cookies"
)
@click.pass_context
@handle_error
def useradd(ctx, bduss, cookies):
    """添加一个用户并设置为当前用户"""

    if cookies:
        cookies = dict([c.split("=", 1) for c in cookies.split("; ")])
        bduss = bduss or cookies.get("BDUSS")
    else:
        cookies = {}
    if not bduss:
        raise ValueError("bduss must be specified or be included in cookie")
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
    ls = sorted([(a.user, a.pwd) for a in am.accounts])
    display_user_infos(*ls, recent_user_id=am._who)

    indexes = list(str(idx) for idx in range(1, len(ls) + 1))
    i = Prompt.ask("Delete an user index", choices=indexes, default="")
    if not i:
        return

    user_id = ls[int(i) - 1][0].user_id
    am.userdel(user_id)
    am.save()

    print(f"Delete user {user_id}")


@app.command()
@click.option(
    "--encrypt-password",
    "--ep",
    prompt="encrypt-password",
    hide_input=True,
    help="加密密码，任意字符",
)
@click.option(
    "--salt", "-s", type=str, default=None, help="加密salt，不限字符 (^v0.5.17 后不使用)"
)
@click.pass_context
@handle_error
def encryptpwd(ctx, encrypt_password, salt):
    """设置加密密码"""

    assert len(encrypt_password) > 0, "No encrypt-password"

    am = ctx.obj.account_manager
    am.set_encrypt_password(encrypt_password, salt)
    am.save()


@app.command()
@click.argument("remotedir", type=str, default="/", required=False)
@click.pass_context
@handle_error
def cd(ctx, remotedir):
    """切换当前工作目录"""

    am = ctx.obj.account_manager
    am.cd(remotedir)
    am.save()


@app.command()
@click.pass_context
@handle_error
@multi_user_do
def pwd(ctx):
    """显示当前工作目录"""

    pwd = _pwd(ctx)
    print(pwd)


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
@multi_user_do
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

    api = _recent_api(ctx)
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

    pwd = _pwd(ctx)
    remotepaths = (join_path(pwd, r) for r in list(remotepaths) or (pwd,))

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
@click.argument("remotedir", nargs=1, type=str, default="")
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
@multi_user_do
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

    api = _recent_api(ctx)
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

    pwd = _pwd(ctx)
    remotedir = join_path(pwd, remotedir)

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
@click.option("--encoding", "-e", type=str, help="文件编码，默认自动解码")
@click.option("--no-decrypt", "--ND", is_flag=True, help="不解密")
@click.option(
    "--encrypt-password", "--ep", type=str, default=None, help="加密密码，默认使用用户设置的"
)
@click.pass_context
@handle_error
@multi_user_do
def cat(ctx, remotepath, encoding, no_decrypt, encrypt_password):
    """显示文件内容"""

    api = _recent_api(ctx)
    if not api:
        return

    pwd = _pwd(ctx)
    remotepath = join_path(pwd, remotepath)

    if no_decrypt:
        encrypt_password = b""
    else:
        encrypt_password = encrypt_password or _encrypt_password(ctx)

    _cat(api, remotepath, encoding=encoding, encrypt_password=encrypt_password)


@app.command()
@click.argument("remotedirs", nargs=-1, type=str)
@click.option("--show", "-S", is_flag=True, help="显示目录")
@click.pass_context
@handle_error
@multi_user_do
def mkdir(ctx, remotedirs, show):
    """创建目录"""

    api = _recent_api(ctx)
    if not api:
        return

    pwd = _pwd(ctx)
    remotedirs = (join_path(pwd, d) for d in remotedirs)

    file_operators.makedir(api, *remotedirs, show=show)


@app.command()
@click.argument("remotepaths", nargs=-1, type=str)
@click.option("--show", "-S", is_flag=True, help="显示结果")
@click.pass_context
@handle_error
@multi_user_do
def move(ctx, remotepaths, show):
    """移动文件

    \b
    examples:
        move /file1 /file2 /to/dir
    """

    api = _recent_api(ctx)
    if not api:
        return

    pwd = _pwd(ctx)
    remotepaths = [join_path(pwd, r) for r in remotepaths]

    if len(remotepaths) < 2:
        ctx.fail("remote paths < 2")
    file_operators.move(api, *remotepaths, show=show)


@app.command()
@click.argument("source", nargs=1, type=str)
@click.argument("dest", nargs=1, type=str)
@click.option("--show", "-S", is_flag=True, help="显示结果")
@click.pass_context
@handle_error
@multi_user_do
def rename(ctx, source, dest, show):
    """文件重命名

    \b
    examples:
        rename /path/to/far /to/here/foo
    """

    api = _recent_api(ctx)
    if not api:
        return

    pwd = _pwd(ctx)
    source = join_path(pwd, source)
    dest = join_path(pwd, dest)

    file_operators.rename(api, source, dest, show=show)


@app.command()
@click.argument("remotepaths", nargs=-1, type=str)
@click.option("--show", "-S", is_flag=True, help="显示结果")
@click.pass_context
@handle_error
@multi_user_do
def copy(ctx, remotepaths, show):
    """拷贝文件

    \b
    examples:
        copy /file1 /file2 /to/dir
    """

    api = _recent_api(ctx)
    if not api:
        return

    pwd = _pwd(ctx)
    remotepaths = [join_path(pwd, r) for r in remotepaths]

    if len(remotepaths) < 2:
        ctx.fail("remote paths < 2")
    file_operators.copy(api, *remotepaths, show=show)


@app.command()
@click.argument("remotepaths", nargs=-1, type=str)
@click.pass_context
@handle_error
@multi_user_do
def remove(ctx, remotepaths):
    """删除文件"""

    api = _recent_api(ctx)
    if not api:
        return

    pwd = _pwd(ctx)
    remotepaths = (join_path(pwd, r) for r in remotepaths)

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
    默认为 me (BaiduPCS-Py 自己的下载器，支持断续下载)
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
@click.option("--no-decrypt", "--ND", is_flag=True, help="不解密")
@click.option("--quiet", "-q", is_flag=True, help="取消第三方下载应用输出")
@click.option("--out-cmd", "--OC", is_flag=True, help="输出第三方下载应用命令")
@click.option(
    "--encrypt-password", "--ep", type=str, default=None, help="加密密码，默认使用用户设置的"
)
@click.pass_context
@handle_error
@multi_user_do
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
    no_decrypt,
    quiet,
    out_cmd,
    encrypt_password,
):
    """下载文件"""

    if out_cmd:
        assert downloader != Downloader.me.name, "输出命令只能用于第三方下载应用"

    api = _recent_api(ctx)
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

    pwd = _pwd(ctx)
    remotepaths = [join_path(pwd, r) for r in remotepaths]

    if no_decrypt:
        encrypt_password = b""
    else:
        encrypt_password = encrypt_password or _encrypt_password(ctx)

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
        out_cmd=out_cmd,
        encrypt_password=encrypt_password,
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
@click.option("--player-params", "--PP", multiple=True, type=str, help="第三方播放器参数")
@click.option("--m3u8", "-m", is_flag=True, help="获取m3u8文件并播放")
@click.option("--quiet", "-q", is_flag=True, help="取消第三方播放器输出")
@click.option("--shuffle", "--sf", is_flag=True, help="随机播放")
@click.option("--ignore-ext", "--IE", is_flag=True, help="不用文件名后缀名来判断媒体文件")
@click.option("--out-cmd", "--OC", is_flag=True, help="输出第三方播放器命令")
@click.option(
    "--use-local-server",
    "-s",
    is_flag=True,
    help="使用本地服务器播放。大于100MB的媒体文件无法直接播放，需要使用本地服务器播放",
)
@click.option(
    "--encrypt-password", "--ep", type=str, default=None, help="加密密码，默认使用用户设置的"
)
@click.pass_context
@handle_error
@multi_user_do
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
    player_params,
    m3u8,
    quiet,
    shuffle,
    ignore_ext,
    out_cmd,
    use_local_server,
    encrypt_password,
):
    """播放媒体文件"""

    api = _recent_api(ctx)
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

    pwd = _pwd(ctx)
    remotepaths = [join_path(pwd, r) for r in remotepaths]

    local_server = ""
    if use_local_server:
        encrypt_password = encrypt_password or _encrypt_password(ctx)

        host = "localhost"
        port = random_avail_port(49152, 65535)

        local_server = f"http://{host}:{port}"

        ps = Process(
            target=start_server,
            args=(
                api,
                "/",
            ),
            kwargs=dict(
                host=host,
                port=port,
                workers=CPU_NUM,
                encrypt_password=encrypt_password,
                log_level="warning",
            ),
        )
        ps.start()
        time.sleep(1)

    _play(
        api,
        remotepaths,
        sifters=sifters,
        recursive=recursive,
        from_index=from_index,
        player=getattr(Player, player),
        player_params=player_params,
        m3u8=m3u8,
        quiet=quiet,
        shuffle=shuffle,
        ignore_ext=ignore_ext,
        out_cmd=out_cmd,
        local_server=local_server,
    )

    if use_local_server:
        ps.terminate()


@app.command()
@click.argument("localpaths", nargs=-1, type=str)
@click.argument("remotedir", nargs=1, type=str)
@click.option(
    "--encrypt-password", "--ep", type=str, default=None, help="加密密码，默认使用用户设置的"
)
@click.option(
    "--encrypt-type",
    "-e",
    type=click.Choice([t.name for t in EncryptType]),
    default=EncryptType.No.name,
    help="文件加密方法，默认为 No 不加密",
)
@click.option("--max-workers", "-w", type=int, default=CPU_NUM, help="同时上传文件数")
@click.option("--no-ignore-existing", "--NI", is_flag=True, help="上传已经存在的文件")
@click.option("--no-show-progress", "--NP", is_flag=True, help="不显示上传进度")
@click.pass_context
@handle_error
@multi_user_do
def upload(
    ctx,
    localpaths,
    remotedir,
    encrypt_password,
    encrypt_type,
    max_workers,
    no_ignore_existing,
    no_show_progress,
):
    """上传文件"""

    # Keyboard listener start
    keyboard_listener_start()

    api = _recent_api(ctx)
    if not api:
        return

    encrypt_password = encrypt_password or _encrypt_password(ctx)
    if encrypt_type != EncryptType.No.name and not encrypt_password:
        raise ValueError(f"Encrypting with {encrypt_type} must have a key")

    pwd = _pwd(ctx)
    remotedir = join_path(pwd, remotedir)

    from_to_list = from_tos(localpaths, remotedir)
    _upload(
        api,
        from_to_list,
        encrypt_password=encrypt_password,
        encrypt_type=getattr(EncryptType, encrypt_type),
        max_workers=max_workers,
        ignore_existing=not no_ignore_existing,
        show_progress=not no_show_progress,
    )


@app.command()
@click.argument("localdir", nargs=1, type=str)
@click.argument("remotedir", nargs=1, type=str)
@click.option(
    "--encrypt-password", "--ep", type=str, default=None, help="加密密码，默认使用用户设置的"
)
@click.option(
    "--encrypt-type",
    "-e",
    type=click.Choice([t.name for t in EncryptType]),
    default=EncryptType.No.name,
    help="文件加密方法，默认为 No 不加密",
)
@click.option("--max-workers", "-w", type=int, default=CPU_NUM, help="同时上传文件数")
@click.option("--no-show-progress", "--NP", is_flag=True, help="不显示上传进度")
@click.pass_context
@handle_error
@multi_user_do
def sync(
    ctx,
    localdir,
    remotedir,
    encrypt_password,
    encrypt_type,
    max_workers,
    no_show_progress,
):
    """同步本地目录到远端"""

    # Keyboard listener start
    keyboard_listener_start()

    api = _recent_api(ctx)
    if not api:
        return

    pwd = _pwd(ctx)
    remotedir = join_path(pwd, remotedir)

    encrypt_password = encrypt_password or _encrypt_password(ctx)
    if encrypt_type != EncryptType.No.name and not encrypt_password:
        raise ValueError(f"Encrypting with {encrypt_type} must have a key")

    _sync(
        api,
        localdir,
        remotedir,
        encrypt_password=encrypt_password,
        encrypt_type=getattr(EncryptType, encrypt_type),
        max_workers=max_workers,
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
@multi_user_do
def share(ctx, remotepaths, password):
    """分享文件

    \b
    examples:
        share /path1 path2
    """
    assert not password or len(password) == 4, "`password` must be 4 letters"

    api = _recent_api(ctx)
    if not api:
        return

    pwd = _pwd(ctx)
    remotepaths = (join_path(pwd, r) for r in remotepaths)

    _share.share_files(api, *remotepaths, password=password)


@app.command()
@click.option("--show-all", "-S", is_flag=True, help="显示所有分享的链接，默认只显示有效的分享链接")
@click.pass_context
@handle_error
@multi_user_do
def shared(ctx, show_all):
    """列出分享链接"""

    api = _recent_api(ctx)
    if not api:
        return

    _share.list_shared(api, show_all=show_all)


@app.command()
@click.argument("share_ids", nargs=-1, type=int)
@click.pass_context
@handle_error
@multi_user_do
def cancelshared(ctx, share_ids):
    """取消分享链接"""

    api = _recent_api(ctx)
    if not api:
        return

    _share.cancel_shared(api, *share_ids)


@app.command()
@click.argument("shared_url", nargs=1, type=str)
@click.argument("remotedir", nargs=1, type=str)
@click.option("--password", "-p", type=str, help="链接密码，如果没有不用设置")
@click.option("--no-show-vcode", "--NV", is_flag=True, help="不显示验证码")
@click.pass_context
@handle_error
@multi_user_do
def save(ctx, shared_url, remotedir, password, no_show_vcode):
    """保存其他用户分享的链接"""

    assert not password or len(password) == 4, "`password` must be 4 letters"

    api = _recent_api(ctx)
    if not api:
        return

    pwd = _pwd(ctx)
    remotedir = join_path(pwd, remotedir)

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
@multi_user_do
def add(ctx, task_urls, remotedir):
    """添加离线下载任务"""

    api = _recent_api(ctx)
    if not api:
        return

    pwd = _pwd(ctx)
    remotedir = join_path(pwd, remotedir)

    for url in task_urls:
        _cloud.add_task(api, url, remotedir)


@app.command()
@click.argument("task_ids", nargs=-1, type=str)
@click.pass_context
@handle_error
@multi_user_do
def tasks(ctx, task_ids):
    """列出离线下载任务。也可列出给定id的任务"""

    api = _recent_api(ctx)
    if not api:
        return

    if not task_ids:
        _cloud.list_tasks(api)
    else:
        _cloud.tasks(api, *task_ids)


@app.command()
@click.pass_context
@handle_error
@multi_user_do
def cleartasks(ctx):
    """清除已经下载完和下载失败的任务"""

    api = _recent_api(ctx)
    if not api:
        return

    _cloud.clear_tasks(api)


@app.command()
@click.argument("task_ids", nargs=-1, type=str)
@click.pass_context
@handle_error
@multi_user_do
def canceltasks(ctx, task_ids):
    """取消下载任务"""

    api = _recent_api(ctx)
    if not api:
        return

    for task_id in task_ids:
        _cloud.cancel_task(api, task_id)


@app.command()
@click.option("--yes", is_flag=True, help="确定直接运行")
@click.pass_context
@handle_error
@multi_user_do
def purgetasks(ctx, yes):
    """删除所有离线下载任务"""

    api = _recent_api(ctx)
    if not api:
        return

    if not yes:
        if not Confirm.ask("确定删除[i red]所有的[/i red]离线下载任务?", default=False):
            return
    _cloud.purge_all_tasks(api)


# }}}

# {{{ Server


@app.command()
@click.argument("root_dir", type=str, default="/", required=False)
@click.option("--host", "-h", type=str, default="localhost", help="监听 host")
@click.option("--port", "-p", type=int, default=8000, help="监听 port")
@click.option("--workers", "-w", type=int, default=CPU_NUM, help="进程数")
@click.option(
    "--encrypt-password", "--ep", type=str, default=None, help="加密密码，默认使用用户设置的"
)
@click.option("--username", type=str, default=None, help="HTTP Basic Auth 用户名")
@click.option("--password", type=str, default=None, help="HTTP Basic Auth 密钥")
@click.pass_context
@handle_error
@multi_user_do
def server(ctx, root_dir, host, port, workers, encrypt_password, username, password):
    """开启 HTTP 服务"""

    api = _recent_api(ctx)
    if not api:
        return

    encrypt_password = encrypt_password or _encrypt_password(ctx)

    if username:
        assert password, "Must set password"

    start_server(
        api,
        root_dir=root_dir,
        host=host,
        port=port,
        workers=workers,
        encrypt_password=encrypt_password,
        username=username,
        password=password,
    )


# }}}
