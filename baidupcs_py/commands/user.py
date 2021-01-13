from baidupcs_py.baidupcs import BaiduPCSApi
from baidupcs_py.commands.display import display_user_info


def show_user_info(api: BaiduPCSApi):
    info = api.user_info()
    display_user_info(info)
