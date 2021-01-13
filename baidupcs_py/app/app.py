from typing import Optional

import click

from baidupcs_py import __version__
from baidupcs_py.baidupcs import BaiduPCSApi
from baidupcs_py.app.account import Account, AccountManager, DEFAULT_DATA_PATH
from baidupcs_py.commands.sifter import IncludeSifter, ExcludeSifter, IsFileSifter, IsDirSifter
from baidupcs_py.commands.display import display_user_info, display_user_infos
from baidupcs_py.commands.list_files import list_files
from baidupcs_py.commands import file_operators
from baidupcs_py.commands.search import search as _search
from baidupcs_py.commands import cloud as _cloud
from baidupcs_py.commands.download import (
    download as _download, Downloader, DownloadParams, DEFAULT_DOWNLOADER, DEFAULT_CONCURRENCY,
    DEFAULT_CHUNK_SIZE
)
from baidupcs_py.commands.upload import upload as _upload, from_tos, CPU_NUM
from baidupcs_py.commands import share as _share

from rich import print
from rich.prompt import Prompt

ALIAS = {
    'w': 'who',
    'su': 'su',
    'ul': 'userlist',
    'ua': 'useradd',
    'ud': 'userdel',
    'l': 'ls',
    'f': 'search',
    'md': 'mkdir',
    'mv': 'move',
    'rn': 'rename',
    'cp': 'copy',
    'rm': 'remove',
    'd': 'download',
    'u': 'upload',
    'S': 'share',
    'sl': 'shared',
    'cs': 'cancelshared',
    's': 'save',
    'a': 'add',
    't': 'tasks',
    'ct': 'cleartasks',
    'cct': 'canceltasks',
}


class AliasedGroup(click.Group):

    def get_command(self, ctx, cmd_name):
        # As normal command name
        rv = click.Group.get_command(self, ctx, cmd_name)
        if rv is not None:
            return rv

        # Check alias command name
        if cmd_name not in ALIAS:
            ctx.fail(f'No command: {cmd_name}')

        normal_cmd_name = ALIAS[cmd_name]
        return click.Group.get_command(self, ctx, normal_cmd_name)


_APP_DOC = f"""BaiduPCS App v{__version__}

    \b
    如果第一次使用，你需要运行 `BaiduPCS-Py useradd` 添加 `bduss` 和 `cookies`。
    如何获取 `bduss` 和 `cookies` 见 https://github.com/PeterDing/BaiduPCS-Py#useradd
    用 `BaiduPCS-Py {{command}} --help` 查看具体的用法。"""

_ALIAS_DOC = 'Command Alias:\n\n\b\n' + '\n'.join(
    [f'{alias: >3} : {cmd}' for alias, cmd in sorted(ALIAS.items(), key=lambda x: x[1])]
)


@click.group(cls=AliasedGroup, help=_APP_DOC, epilog=_ALIAS_DOC)
@click.option('--account-data', type=str, default=DEFAULT_DATA_PATH, help='Account data file')
@click.pass_context
def app(ctx, account_data):

    ctx.obj.account_manager = AccountManager.load_data(account_data)


# Account
# {{{


@app.command()
@click.argument('user_id', type=int, default=None, required=False)
@click.pass_context
def who(ctx, user_id):
    am = ctx.obj.account_manager
    account = am.who(user_id)
    if account:
        display_user_info(account.user)
    else:
        print('[italic red]No recent user, please adding or selecting one[/]')


@app.command()
@click.pass_context
def su(ctx):
    am = ctx.obj.account_manager
    ls = sorted([a.user for a in am.accounts])
    display_user_infos(*ls)

    user_ids = [str(u.user_id) for u in ls] + ['']
    i = Prompt.ask("Select an user", choices=user_ids)
    user_id = int(i)
    am.su(user_id)
    am.save()


@app.command()
@click.pass_context
def userlist(ctx):
    am = ctx.obj.account_manager
    ls = sorted([a.user for a in am.accounts])
    display_user_infos(*ls)


@app.command()
@click.option('--bduss', prompt='bduss', hide_input=True)
@click.option('--cookies', prompt='cookies', hide_input=True)
@click.pass_context
def useradd(ctx, bduss, cookies):
    cookies = dict([c.split('=', 1) for c in cookies.split('; ')])
    account = Account.from_bduss(bduss, cookies=cookies)
    am = ctx.obj.account_manager
    am.useradd(account.user)
    am.su(account.user.user_id)
    am.save()


@app.command()
@click.pass_context
def userdel(ctx):
    am = ctx.obj.account_manager
    ls = sorted([a.user for a in am.accounts])
    display_user_infos(*ls)

    user_ids = [str(u.user_id) for u in ls] + ['']
    i = Prompt.ask("Delete an user", choices=user_ids)
    if not i:
        return

    user_id = int(i)
    am.userdel(user_id)
    am.save()

    print(f'Delete user {user_id}')


def recent_api(ctx) -> Optional[BaiduPCSApi]:
    am = ctx.obj.account_manager
    account = am.who()
    if not account:
        print('[italic red]No recent user, please adding or selecting one[/]')
        return None
    return account.pcsapi()


# }}}

# Files
# {{{


@app.command()
@click.argument('remotepaths', nargs=-1, type=str)
@click.option('--desc', '-r', is_flag=True)
@click.option('--name', '-n', is_flag=True)
@click.option('--time', '-t', is_flag=True)
@click.option('--size', '-s', is_flag=True)
@click.option('--recursive', '-R', is_flag=True)
@click.option('--include', '-I', type=str)
@click.option('--include-regex', '--IR', type=str)
@click.option('--exclude', '-E', type=str)
@click.option('--exclude-regex', '--ER', type=str)
@click.option('--is-file', '-f', is_flag=True)
@click.option('--is-dir', '-d', is_flag=True)
@click.option('--no-highlight', '--NH', is_flag=True)
@click.option('--show-size', '-S', is_flag=True)
@click.option('--show-date', '-D', is_flag=True)
@click.option('--show-md5', '-M', is_flag=True)
@click.option('--show-absolute-path', '-A', is_flag=True)
@click.pass_context
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
@click.argument('keyword', nargs=1, type=str)
@click.argument('remotedir', nargs=1, type=str, default='/')
@click.option('--recursive', '-R', is_flag=True)
@click.option('--include', '-I', type=str)
@click.option('--include-regex', '--IR', type=str)
@click.option('--exclude', '-E', type=str)
@click.option('--exclude-regex', '--ER', type=str)
@click.option('--is-file', '-f', is_flag=True)
@click.option('--is-dir', '-d', is_flag=True)
@click.option('--no-highlight', '--NH', is_flag=True)
@click.option('--show-size', '-S', is_flag=True)
@click.option('--show-date', '-D', is_flag=True)
@click.option('--show-md5', '-M', is_flag=True)
@click.pass_context
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
@click.argument('remotedirs', nargs=-1, type=str)
@click.option('--show', '-S', is_flag=True)
@click.pass_context
def mkdir(ctx, remotedirs, show):
    api = recent_api(ctx)
    if not api:
        return

    file_operators.makedir(api, *remotedirs, show=show)


@app.command()
@click.argument('remotepaths', nargs=-1, type=str)
@click.option('--show', '-S', is_flag=True)
@click.pass_context
def move(ctx, remotepaths, show):
    api = recent_api(ctx)
    if not api:
        return

    if len(remotepaths) < 2:
        ctx.fail('remote paths < 2')
    file_operators.move(api, *remotepaths, show=show)


@app.command()
@click.argument('source', nargs=1, type=str)
@click.argument('dest', nargs=1, type=str)
@click.option('--show', '-S', is_flag=True)
@click.pass_context
def rename(ctx, source, dest, show):
    api = recent_api(ctx)
    if not api:
        return

    file_operators.rename(api, source, dest, show=show)


@app.command()
@click.argument('remotepaths', nargs=-1, type=str)
@click.option('--show', '-S', is_flag=True)
@click.pass_context
def copy(ctx, remotepaths, show):
    api = recent_api(ctx)
    if not api:
        return

    if len(remotepaths) < 2:
        ctx.fail('remote paths < 2')
    file_operators.copy(api, *remotepaths, show=show)


@app.command()
@click.argument('remotepaths', nargs=-1, type=str)
@click.pass_context
def remove(ctx, remotepaths):
    api = recent_api(ctx)
    if not api:
        return

    file_operators.remove(api, *remotepaths)


@app.command()
@click.argument('remotepaths', nargs=-1, type=str)
@click.option('--outdir', '-o', nargs=1, type=str, default='.')
@click.option('--recursive', '-R', is_flag=True)
@click.option('--from-index', '-f', type=int, default=0)
@click.option('--include', '-I', type=str)
@click.option('--include-regex', '--IR', type=str)
@click.option('--exclude', '-E', type=str)
@click.option('--exclude-regex', '--ER', type=str)
@click.option(
    '-d',
    '--downloader',
    type=click.Choice([d.name for d in Downloader]),
    default=DEFAULT_DOWNLOADER.name
)
@click.option('--concurrency', '-s', type=int, default=DEFAULT_CONCURRENCY)
@click.option('--chunk-size', '-k', type=str, default=DEFAULT_CHUNK_SIZE)
@click.option('--quiet', '-q', is_flag=True)
@click.pass_context
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
        downloadparams=DownloadParams(concurrency=concurrency, chunk_size=chunk_size, quiet=quiet)
    )


@app.command()
@click.argument('localpaths', nargs=-1, type=str)
@click.argument('remotedir', nargs=1, type=str)
@click.option('--max-workers', '-w', type=int, default=CPU_NUM)
@click.option('--no-ignore-existing', '--NI', is_flag=True)
@click.option('--no-show-progress', '--NP', is_flag=True)
@click.pass_context
def upload(ctx, localpaths, remotedir, max_workers, no_ignore_existing, no_show_progress):
    api = recent_api(ctx)
    if not api:
        return

    from_to_list = from_tos(localpaths, remotedir)
    _upload(
        api,
        from_to_list,
        max_workers=max_workers,
        ignore_existing=not no_ignore_existing,
        show_progress=not no_show_progress
    )


# }}}


# Share
# {{{
@app.command()
@click.argument('remotepaths', nargs=-1, type=str)
@click.option('--password', '-p', type=str)
@click.pass_context
def share(ctx, remotepaths, password):
    assert not password or len(password) == 4, '`password` must be 4 letters'

    api = recent_api(ctx)
    if not api:
        return

    _share.share_files(api, *remotepaths, password=password)


@app.command()
@click.option('--show-all', '-S', is_flag=True)
@click.pass_context
def shared(ctx, show_all):
    api = recent_api(ctx)
    if not api:
        return

    _share.list_shared(api, show_all=show_all)


@app.command()
@click.argument('share_ids', nargs=-1, type=int)
@click.pass_context
def cancelshared(ctx, share_ids):
    api = recent_api(ctx)
    if not api:
        return

    _share.cancel_shared(api, *share_ids)


@app.command()
@click.argument('shared_url', nargs=1, type=str)
@click.argument('remotedir', nargs=1, type=str)
@click.option('--password', '-p', type=str)
@click.option('--no-show-vcode', '--NV', is_flag=True)
@click.pass_context
def save(ctx, shared_url, remotedir, password, no_show_vcode):
    assert not password or len(password) == 4, '`password` must be 4 letters'

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
@click.argument('task_urls', nargs=-1, type=str)
@click.argument('remotedir', nargs=1, type=str)
@click.pass_context
def add(ctx, task_urls, remotedir):
    api = recent_api(ctx)
    if not api:
        return

    for url in task_urls:
        _cloud.add_task(api, url, remotedir)


@app.command()
@click.argument('task_ids', nargs=-1, type=str)
@click.pass_context
def tasks(ctx, task_ids):
    api = recent_api(ctx)
    if not api:
        return

    if not task_ids:
        _cloud.list_tasks(api)
    else:
        _cloud.tasks(api, *task_ids)


@app.command()
@click.pass_context
def cleartasks(ctx):
    api = recent_api(ctx)
    if not api:
        return

    _cloud.clear_tasks(api)


@app.command()
@click.argument('task_ids', nargs=-1, type=str)
@click.pass_context
def canceltasks(ctx, task_ids):
    api = recent_api(ctx)
    if not api:
        return

    for task_id in task_ids:
        _cloud.cancel_task(api, task_id)


@app.command()
@click.pass_context
def purgetasks(ctx):
    api = recent_api(ctx)
    if not api:
        return

    _cloud.purge_all_tasks(api)


# }}}
