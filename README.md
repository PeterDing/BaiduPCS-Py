# BaiduPCS-Py

[![PyPI version](https://badge.fury.io/py/baidupcs-py.svg)](https://badge.fury.io/py/baidupcs-py)
![Build](https://github.com/PeterDing/BaiduPCS-Py/workflows/BaiduPCS-Py%20Build%20&%20Test/badge.svg)

A BaiduPCS API and An App

BaiduPCS-Py 是百度网盘 pcs 的非官方 api 和一个命令行运用程序。

> 也是 https://github.com/PeterDing/iScript/blob/master/pan.baidu.com.py 的重构版。

## 安装

需要 Python 版本大于或等于 3.6

```
pip3 install BaiduPCS-Py
```

## 用法

```
BaiduPCS-Py --help
```

## 添加用户

BaiduPCS-Py 目前不支持用帐号登录。需要使用者在 pan.baidu.com 登录后获取 cookies 和其中的 bduss 值，并用命令 `useradd` 为 BaiduPCS-Py 添加一个用户。

使用者可以用下面的方式获取用户的 cookies 和 bduss 值。

1. 登录 pan.baidu.com
2. 打开浏览器的开发者工具(如 Chrome DevTools)。
3. 然后选择开发者工具的 Network 面板。
4. 在登录后的页面中任意点开一个文件夹。
5. 在 Network 面板中找到 `list?....` 一行，然后在右侧的 Headers 部分找到 `Cookie:` 所在行，复制 `Cookie:` 后的所有内容作为 cookies 值，其中的 `BDUSS=...;` 的 `...` (没有最后的字符;)作为 bduss 值。

![cookies](./imgs/cookies.png)

现在找到了 cookies 和 bduss 值，我们可以用下面的命令添加一个用户。

交互添加：

```
BaiduPCS-Py useradd
```

或者直接添加:

```
BaiduPCS-Py useradd --cookies "cookies 值" --bduss "bduss 值"
```
