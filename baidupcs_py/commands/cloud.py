from baidupcs_py.baidupcs import BaiduPCSApi
from baidupcs_py.commands.display import display_tasks

from rich import print


def add_task(api: BaiduPCSApi, task_url: str, remotedir: str):
    task_id = api.add_task(task_url, remotedir)
    tasks(api, task_id)


def tasks(api: BaiduPCSApi, *task_ids: str):
    if not task_ids:
        return

    cloud_tasks = api.tasks(*task_ids)
    display_tasks(*cloud_tasks)


def list_tasks(api: BaiduPCSApi):
    cloud_tasks = api.list_tasks()
    tasks(api, *[t.task_id for t in cloud_tasks])


def clear_tasks(api: BaiduPCSApi):
    n = api.clear_tasks()
    print("clear tasks:", n)


def cancel_task(api: BaiduPCSApi, task_id: str):
    api.cancel_task(task_id)


def purge_all_tasks(api: BaiduPCSApi):
    clear_tasks(api)

    cloud_tasks = api.list_tasks()
    for task in cloud_tasks:
        cancel_task(api, task.task_id)
