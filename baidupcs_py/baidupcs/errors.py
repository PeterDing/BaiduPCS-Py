from typing import Optional, Any
from functools import wraps

ERRORS = {
    0: 0,
    -1: "由于您分享了违反相关法律法规的文件，分享功能已被禁用，之前分享出去的文件不受影响。",
    -2: "用户不存在,请刷新页面后重试",
    -3: "文件不存在,请刷新页面后重试",
    -4: "登录信息有误，请重新登录试试",
    -5: "host_key和user_key无效",
    -6: "请重新登录",
    -7: "该分享已删除或已取消",
    -8: "该分享已经过期",
    -9: "文件不存在 或 提取密码错误",
    -10: "分享外链已经达到最大上限100000条，不能再次分享",
    -11: "验证cookie无效",
    -12: "访问密码错误",
    -14: "对不起，短信分享每天限制20条，你今天已经分享完，请明天再来分享吧！",
    -15: "对不起，邮件分享每天限制20封，你今天已经分享完，请明天再来分享吧！",
    -16: "对不起，该文件已经限制分享！",
    -17: "文件分享超过限制",
    -19: "需要输入验证码",
    -21: "分享已取消或分享信息无效",
    -30: "文件已存在",
    -31: "文件保存失败",
    -33: "一次支持操作999个，减点试试吧",
    -62: "可能需要输入验证码",
    -70: "你分享的文件中包含病毒或疑似病毒，为了你和他人的数据安全，换个文件分享吧",
    2: "参数错误",
    3: "未登录或帐号无效",
    4: "存储好像出问题了，请稍候再试",
    12: "文件已经存在",
    105: "啊哦，链接错误没找到文件，请打开正确的分享链接",
    108: "文件名有敏感词，优化一下吧",
    110: "分享次数超出限制，可以到“我的分享”中查看已分享的文件链接",
    112: "页面已过期，请刷新后重试",
    113: "签名错误",
    114: "当前任务不存在，保存失败",
    115: "该文件禁止分享",
    132: "您的帐号可能存在安全风险，为了确保为您本人操作，请先进行安全验证。",
    31001: "数据库查询错误",
    31002: "数据库连接错误",
    31003: "数据库返回空结果",
    31021: "网络错误",
    31022: "暂时无法连接服务器",
    31023: "输入参数错误",
    31024: "app id为空",
    31025: "后端存储错误",
    31041: "用户的cookie不是合法的百度cookie",
    31042: "用户未登陆",
    31043: "用户未激活",
    31044: "用户未授权",
    31045: "用户不存在",
    31046: "用户已经存在",
    31061: "文件已经存在",
    31062: "文件名非法",
    31063: "文件父目录不存在",
    31064: "无权访问此文件",
    31065: "目录已满",
    31066: "文件不存在",
    31067: "文件处理出错",
    31068: "文件创建失败",
    31069: "文件拷贝失败",
    31070: "文件删除失败",
    31071: "不能读取文件元信息",
    31072: "文件移动失败",
    31073: "文件重命名失败",
    31081: "superfile创建失败",
    31082: "superfile 块列表为空",
    31083: "superfile 更新失败",
    31101: "tag系统内部错误",
    31102: "tag参数错误",
    31103: "tag系统错误",
    31110: "未授权设置此目录配额",
    31111: "配额管理只支持两级目录",
    31112: "超出配额",
    31113: "配额不能超出目录祖先的配额",
    31114: "配额不能比子目录配额小",
    31141: "请求缩略图服务失败",
    31201: "签名错误",
    31203: "设置acl失败",
    31204: "请求acl验证失败",
    31205: "获取acl失败",
    31079: "未找到文件MD5，请使用上传API上传整个文件。",
    31202: "文件不存在",
    31206: "acl不存在",
    31207: "bucket已存在",
    31208: "用户请求错误",
    31209: "服务器错误",
    31210: "服务器不支持",
    31211: "禁止访问",
    31212: "服务不可用",
    31213: "重试出错",
    31214: "上传文件data失败",
    31215: "上传文件meta失败",
    31216: "下载文件data失败",
    31217: "下载文件meta失败",
    31218: "容量超出限额",
    31219: "请求数超出限额",
    31220: "流量超出限额",
    31298: "服务器返回值KEY非法",
    31299: "服务器返回值KEY不存在",
    31304: "file type is not supported",
    31341: "be transcoding, please wait and retry",
    31326: "user is not authorized, hitcode:117",  # Hit when request download link
    31626: "user is not authorized, hitcode:122",  # Hit when request download link
    36001: "离线下载错误",
    36032: "hit sexy spam",
    36037: "source url not support",
    100001: "文件被封",
}

UNKNOWN_ERROR = "未知错误"


class BaiduPCSError(Exception):
    def __init__(self, message: str, error_code: Optional[int] = None, cause=None):
        self.__cause__ = cause
        self.error_code = error_code
        super().__init__(message)


def parse_errno(error_code: int, info: Any = None) -> Optional[BaiduPCSError]:
    if error_code != 0:
        mean = ERRORS.get(error_code, info or UNKNOWN_ERROR)
        msg = f"error_code: {error_code}, message: {mean}"
        return BaiduPCSError(msg, error_code=error_code)
    return None


def assert_ok(func):
    """Assert the errno of response is not 0"""

    @wraps(func)
    def check(*args, **kwargs):
        info = func(*args, **kwargs)
        error_code = info.get("errno")
        if error_code is None:
            error_code = info.get("error_code")
        if error_code is None:
            error_code = 0
        error_code = int(error_code)

        if error_code not in ERRORS:
            err = parse_errno(error_code, str(info))
        else:
            err = parse_errno(error_code)

        if err:
            raise err
        return info

    return check
