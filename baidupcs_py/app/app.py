from typing import Optional

import click

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


@click.group(cls=AliasedGroup, help='-------')
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
@click.option('--desc', is_flag=True)
@click.option('--name', is_flag=True)
@click.option('--time', is_flag=True)
@click.option('--size', is_flag=True)
@click.option('-R', '--recursive', is_flag=True)
@click.option('--include', type=str)
@click.option('--include-regex', type=str)
@click.option('--exclude', type=str)
@click.option('--exclude-regex', type=str)
@click.option('--is-file', is_flag=True)
@click.option('--is-dir', is_flag=True)
@click.option('--highlight', is_flag=True, default=True)
@click.option('--show-size', is_flag=True)
@click.option('--show-date', is_flag=True)
@click.option('--show-md5', is_flag=True)
@click.option('--show-absolute-path', is_flag=True)
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
    highlight,
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
        highlight=highlight,
        show_size=show_size,
        show_date=show_date,
        show_md5=show_md5,
        show_absolute_path=show_absolute_path,
    )


@app.command()
@click.argument('keyword', nargs=1, type=str)
@click.argument('remotedir', nargs=1, type=str, default='/')
@click.option('-R', '--recursive', is_flag=True)
@click.option('--include', type=str)
@click.option('--include-regex', type=str)
@click.option('--exclude', type=str)
@click.option('--exclude-regex', type=str)
@click.option('--is-file', is_flag=True)
@click.option('--is-dir', is_flag=True)
@click.option('--highlight', is_flag=True, default=True)
@click.option('--show-size', is_flag=True)
@click.option('--show-date', is_flag=True)
@click.option('--show-md5', is_flag=True)
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
    highlight,
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
        highlight=highlight,
        show_size=show_size,
        show_date=show_date,
        show_md5=show_md5,
    )


@app.command()
@click.argument('remotedirs', nargs=-1, type=str)
@click.option('--show', is_flag=True)
@click.pass_context
def mkdir(ctx, remotedirs, show):
    api = recent_api(ctx)
    if not api:
        return

    file_operators.makedir(api, *remotedirs, show=show)


@app.command()
@click.argument('remotepaths', nargs=-1, type=str)
@click.option('--show', is_flag=True)
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
@click.option('--show', is_flag=True)
@click.pass_context
def rename(ctx, source, dest, show):
    api = recent_api(ctx)
    if not api:
        return

    file_operators.rename(api, source, dest, show=show)


@app.command()
@click.argument('remotepaths', nargs=-1, type=str)
@click.option('--show', is_flag=True)
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
@click.option('--dir', nargs=1, type=str, default='.')
@click.option('-R', '--recursive', is_flag=True)
@click.option('--include', type=str)
@click.option('--include-regex', type=str)
@click.option('--exclude', type=str)
@click.option('--exclude-regex', type=str)
@click.option(
    '-d',
    '--downloader',
    type=click.Choice([d.name for d in Downloader]),
    default=DEFAULT_DOWNLOADER.name
)
@click.option('-s', '--concurrency', type=int, default=DEFAULT_CONCURRENCY)
@click.option('-k', '--chunk-size', type=str, default=DEFAULT_CHUNK_SIZE)
@click.option('-q', '--quiet', is_flag=True)
@click.pass_context
def download(
    ctx,
    remotepaths,
    dir,
    recursive,
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
        dir,
        sifters=sifters,
        recursive=recursive,
        downloader=getattr(Downloader, downloader),
        downloadparams=DownloadParams(concurrency=concurrency, chunk_size=chunk_size, quiet=quiet)
    )


@app.command()
@click.argument('localpaths', nargs=-1, type=str)
@click.argument('remotedir', nargs=1, type=str)
@click.option('-s', '--max-workers', type=int, default=CPU_NUM)
@click.option('--no-ignore-existing', is_flag=True)
@click.option('--no-show-progress', is_flag=True)
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
@click.option('-p', '--password', type=str)
@click.pass_context
def share(ctx, remotepaths, password):
    api = recent_api(ctx)
    if not api:
        return

    _share.share_files(api, *remotepaths, password=password)


@app.command()
@click.option('--show-all', is_flag=True)
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
@click.option('-p', '--password', type=str)
@click.option('--no-show-vcode', is_flag=True)
@click.pass_context
def save(ctx, shared_url, remotedir, password, no_show_vcode):
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
