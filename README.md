# BaiduPCS-Py

[![PyPI version](https://badge.fury.io/py/baidupcs-py.svg)](https://badge.fury.io/py/baidupcs-py)
![Build](https://github.com/PeterDing/BaiduPCS-Py/workflows/BaiduPCS-Py%20Build%20&%20Test/badge.svg)

A BaiduPCS API and An App

BaiduPCS-Py 是百度网盘 pcs 的非官方 api 和一个命令行运用程序。

> 也是 https://github.com/PeterDing/iScript/blob/master/pan.baidu.com.py 的重构版。

- [安装](#安装)
- [API](#API)
- [用法](#用法)
- [命令别名](#命令别名)
- [添加用户](#添加用户)
- [设置文件加密密钥和盐](#设置文件加密密钥和盐)
- [显示当前用户的信息](#显示当前用户的信息)
- [更新用户信息](#更新用户信息)
- [显示所有用户](#显示所有用户)
- [切换当前用户](#切换当前用户)
- [删除一个用户](#删除一个用户)
- [文件操作](#文件操作)
- [显示当前工作目录](#显示当前工作目录)
- [切换当前工作目录](#切换当前工作目录)
- [列出网盘路径下的文件](#列出网盘路径下的文件)
- [搜索文件](#搜索文件)
- [显示文件内容](#显示文件内容)
- [创建目录](#创建目录)
- [移动文件](#移动文件)
- [文件重命名](#文件重命名)
- [拷贝文件](#拷贝文件)
- [删除文件](#删除文件)
- [下载文件](#下载文件)
- [播放媒体文件](#播放媒体文件)
- [上传文件](#上传文件)
- [同步本地目录到远端](#同步本地目录到远端)
- [分享文件](#分享文件)
- [列出分享链接](#列出分享链接)
- [取消分享链接](#取消分享链接)
- [保存其他用户分享的链接](#保存其他用户分享的链接)
- [添加离线下载任务](#添加离线下载任务)
- [列出离线下载任务](#列出离线下载任务)
- [清除已经下载完和下载失败的任务](#清除已经下载完和下载失败的任务)
- [取消下载任务](#取消下载任务)
- [删除所有离线下载任务](#删除所有离线下载任务)
- [开启 HTTP 服务](#开启-HTTP-服务)

## 安装

需要 Python 版本大于或等于 3.7

```
pip3 install BaiduPCS-Py
```

## API

BaiduPCS-Py 的百度网盘 API 只依赖 requests，方便用户开发自己的运用。

```python
from baidupcs_py.baidupcs import BaiduPCSApi

api = BaiduPCSApi(bduss=bduss, cookies=cookies)
```

## 用法

```
BaiduPCS-Py --help
```

## 命令别名

可以用下面的命令别名代替原来的命令名。

| 别名 | 原名         |
| ---- | ------------ |
| w    | who          |
| uu   | updateuser   |
| su   | su           |
| ul   | userlist     |
| ua   | useradd      |
| ek   | encryptkey   |
| ud   | userdel      |
| l    | ls           |
| f    | search       |
| md   | mkdir        |
| mv   | move         |
| rn   | rename       |
| cp   | copy         |
| rm   | remove       |
| d    | download     |
| p    | play         |
| u    | upload       |
| sn   | sync         |
| S    | share        |
| sl   | shared       |
| cs   | cancelshared |
| s    | save         |
| a    | add          |
| t    | tasks        |
| ct   | cleartasks   |
| cct  | canceltasks  |
| sv   | server       |

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

或者直接添加：

```
BaiduPCS-Py useradd --cookies "cookies 值" --bduss "bduss 值"
```

你也可以只添加 `bduss`，省去 `cookies` (或 `cookies` 中没有 `STOKEN` 值)，但这会让你无发使用 `share` 和 `save` 命令来转存其他用法的分享文件。

BaiduPCS-Py 支持多用户，你只需一直用 `useradd` 来添加用户即可。

## 设置文件加密密钥和盐

BaiduPCS-Py 支持“无感的”文件加密。

BaiduPCS-Py 可以加密上传文件，在下载的时候自动解密，让使用者感觉不到加密解密的过程。

如果使用者需要将保密文件上传至百度网盘保存，可以使用这个方法。即使帐号被盗，攻击者也无法还原文件内容。

BaiduPCS-Py 支持以下加密方法：

- **Simple** 一种简单的加密算法。根据密钥生成一个字节对照表来加密解密文件。
  速度快，但**不安全**，不建议加密重要文件。
  因为这种算法加解密不需要知道上下文信息，所以，下载时支持分段下载，如果是媒体文件则支持拖动播放。
  推荐用于加密不重要的媒体文件。
- **ChaCha20** 工业级加密算法，速度快，推荐用于加密重要文件。不支持分段下载。
- **AES265CBC** 工业级加密算法，推荐用于加密重要文件。不支持分段下载。

**注意**：用命令 `encryptkey` 设置的密钥和盐**只是为当前用户**的。

为当前用户设置加密密钥和盐:

交互添加：

```
BaiduPCS-Py encryptkey
```

或者直接添加：

```
BaiduPCS-Py encryptkey --encrypt-key 'my-encrypt-key' --salt 'some-salt'
```

上传并加密文件：

上传和同步文件时只需要指定加密算法就可。如果不指定就不加密。

```
# 默认使用上面设置的 `encrypt-key`
BaiduPCS-Py upload some-file.mp4 some-dir/ /to/here --encrypt-type AES265CBC
```

下载并用上面设置的 `encrypt-key` 自动解密文件：

```
BaiduPCS-Py download /to/here/some-file.mp4 /to/here/some-dir/
```

也可以使用临时的 `encrypt-key`：

```
BaiduPCS-Py upload some-file.mp4 some-dir/ /to/here --encrypt-type Simple --encrypt-key 'onlyyou'
```

但在使用临时的 `encrypt-key` 后，`cat`、下载和播放这些文件时需要指定 `encrypt-key`，但不需要指定加密算法，程序会自动检查加密算法：

```
# 下载
BaiduPCS-Py download /to/here/some-file.mp4 /to/here/some-dir/  --encrypt-key 'onlyyou'

# 开启本地服务并播放
BaiduPCS-Py play /to/here/some-file.mp4 --encrypt-key 'onlyyou' --use-local-server
```

显示当前用户的密钥和盐：

```
BaiduPCS-Py who --show-encrypt-key
```

BaiduPCS-Py 下载时默认会解密文件，如果想要下载但不解密文件，需要加 `--no-decrypt`

```
BaiduPCS-Py download some-file --no-decrypt
```

## 显示当前用户的信息

```
BaiduPCS-Py who
```

或者：

```
BaiduPCS-Py who user_id
```

指明显示用户 id 为 `user_id` 的用户信息。

### 选项

| Option                 | Description  |
| ---------------------- | ------------ |
| -K, --show-encrypt-key | 显示加密密钥 |

## 更新用户信息

默认更新当前用户信息。

```
BaiduPCS-Py updateuser
```

也可指定多个 `user_id`

```
BaiduPCS-Py updateuser user_id
```

## 显示所有用户

```
BaiduPCS-Py userlist
```

## 切换当前用户

```
BaiduPCS-Py su
```

## 删除一个用户

```
BaiduPCS-Py userdel
```

## 文件操作

BaiduPCS-Py 操作网盘中的文件可以使用文件的绝对路径或相对路径（相对与当前目录 pwd）。

每一个用户都有自己的当前工作目录（pwd），默认为 `/` 根目录。

使用者可以用 `cd` 命令来切换当前的工作目录（pwd）。

下面所有涉及网盘路径的命令，其中如果网盘路径用的是相对路径，那么是相对于当前工作目录（pwd）的。
如果是网盘路径用的是绝对路径，那么就是这个绝对路径。

## 显示当前工作目录

```
BaiduPCS-Py pwd
```

## 切换当前工作目录

切换到绝对路径：

```
BaiduPCS-Py cd /to/some/path
```

切换到相对路径：

```
# 切换到 (pwd)/../path
BaiduPCS-Py cd ../path
```

## 列出网盘路径下的文件

```
BaiduPCS-Py ls [OPTIONS] [REMOTEPATHS]...

BaiduPCS-Py ls /absolute/path

# or
BaiduPCS-Py ls relative/path
```

### 选项

| Option                     | Description                          |
| -------------------------- | ------------------------------------ |
| -r, --desc                 | 逆序排列文件                         |
| -n, --name                 | 依名字排序                           |
| -t, --time                 | 依时间排序                           |
| -s, --size                 | 依文件大小排序                       |
| -R, --recursive            | 递归列出文件                         |
| -I, --include TEXT         | 筛选包含这个字符串的文件             |
| --include-regex, --IR TEXT | 筛选包含这个正则表达式的文件         |
| -E, --exclude TEXT         | 筛选 **不** 包含这个字符串的文件     |
| --exclude-regex, --ER TEXT | 筛选 **不** 包含这个正则表达式的文件 |
| -f, --is-file              | 筛选 **非** 目录文件                 |
| -d, --is-dir               | 筛选目录文件                         |
| --no-highlight, --NH       | 取消匹配高亮                         |
| -S, --show-size            | 显示文件大小                         |
| -D, --show-date            | 显示文件创建时间                     |
| -M, --show-md5             | 显示文件 md5                         |
| -A, --show-absolute-path   | 显示文件绝对路径                     |

## 搜索文件

搜索包含 `keyword` 的文件

```
BaiduPCS-Py search [OPTIONS] KEYWORD [REMOTEDIR]

# 在当前工作目录中搜索
BaiduPCS-Py search keyword

# or
BaiduPCS-Py search keyword /absolute/path

# or
BaiduPCS-Py search keyword relative/path
```

### 选项

| Option                     | Description                          |
| -------------------------- | ------------------------------------ |
| -R, --recursive            | 递归搜索文件                         |
| -I, --include TEXT         | 筛选包含这个字符串的文件             |
| --include-regex, --IR TEXT | 筛选包含这个正则表达式的文件         |
| -E, --exclude TEXT         | 筛选 **不** 包含这个字符串的文件     |
| --exclude-regex, --ER TEXT | 筛选 **不** 包含这个正则表达式的文件 |
| -f, --is-file              | 筛选 **非** 目录文件                 |
| -d, --is-dir               | 筛选目录文件                         |
| --no-highlight, --NH       | 取消匹配高亮                         |
| -S, --show-size            | 显示文件大小                         |
| -D, --show-date            | 显示文件创建时间                     |
| -M, --show-md5             | 显示文件 md5                         |

## 显示文件内容

```
BaiduPCS-Py cat [OPTIONS] REMOTEPATH
```

### 选项

| Option                   | Description                  |
| ------------------------ | ---------------------------- |
| -e, --encoding TEXT      | 文件编码，默认自动解码       |
| --no-decrypt, --ND       | 不解密                       |
| --encrypt-key, --ek TEXT | 加密密钥，默认使用用户设置的 |

## 创建目录

```
BaiduPCS-Py mkdir [OPTIONS] [REMOTEDIRS]...
```

### 选项

| Option     | Description |
| ---------- | ----------- |
| -S, --show | 显示目录    |

## 移动文件

移动一些文件到一个目录中。

```
BaiduPCS-Py move [OPTIONS] [REMOTEPATHS]... REMOTEDIR
```

### 选项

| Option     | Description |
| ---------- | ----------- |
| -S, --show | 显示结果    |

## 文件重命名

```
BaiduPCS-Py rename [OPTIONS] SOURCE DEST
```

### 选项

| Option     | Description |
| ---------- | ----------- |
| -S, --show | 显示结果    |

## 拷贝文件

拷贝一些文件到一个目录中。

```
BaiduPCS-Py move [OPTIONS] [REMOTEPATHS]... REMOTEDIR
```

### 选项

| Option     | Description |
| ---------- | ----------- |
| -S, --show | 显示结果    |

## 删除文件

```
BaiduPCS-Py remove [OPTIONS] [REMOTEPATHS]...
```

## 下载文件

```
BaiduPCS-Py download [OPTIONS] [REMOTEPATHS]...
```

### 选项

| Option                                         | Description                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| -o, --outdir TEXT                              | 指定下载本地目录，默认为当前目录                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| -R, --recursive                                | 递归下载                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| -f, --from-index INTEGER                       | 从所有目录中的第几个文件开始下载，默认为 0（第一个）                                                                                                                                                                                                                                                                                                                                                                                                             |
| -I, --include TEXT                             | 筛选包含这个字符串的文件                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| --include-regex, --IR TEXT                     | 筛选包含这个正则表达式的文件                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| -E, --exclude TEXT                             | 筛选 不 包含这个字符串的文件                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| --exclude-regex, --ER TEXT                     | 筛选 不 包含这个正则表达式的文件                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| -s, --concurrency INTEGER                      | 下载同步链接数，默认为 5。数子越大下载速度越快，但是容易被百度封锁                                                                                                                                                                                                                                                                                                                                                                                               |
| -k, --chunk-size TEXT                          | 同步链接分块大小                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| -q, --quiet                                    | 取消第三方下载应用输出                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| --out-cmd, --OC                                | 输出第三方下载应用命令                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| -d, --downloader [me\|aget_py\|aget_rs\|aria2] | 指定下载应用<br> <br> 默认为 me (BaiduPCS-Py 自己的下载器，支持断续下载)<br> me 使用多文件并发下载。<br> <br> 除 me 外，其他下载器，不使用多文件并发下载，使用一个文件多链接下载。<br> 如果需要下载多个小文件推荐使用 me，如果需要下载少量大文件推荐使用其他下载器。<br> <br> aget_py (https://github.com/PeterDing/aget) 默认安装<br> aget_rs (下载 https://github.com/PeterDing/aget-rs/releases)<br> aria2 (下载 https://github.com/aria2/aria2/releases)<br> |
| --encrypt-key, --ek TEXT                       | 加密密钥，默认使用用户设置的                                                                                                                                                                                                                                                                                                                                                                                                                                     |

## 播放媒体文件

```
BaiduPCS-Py play [OPTIONS] [REMOTEPATHS]...
```

**注意**: 大于 100MB 的媒体文件无法直接播放，需要加 `-s` 使用本地服务器播放。

### 选项

| Option                     | Description                                                                   |
| -------------------------- | ----------------------------------------------------------------------------- |
| -R, --recursive            | 递归播放                                                                      |
| -f, --from-index INTEGER   | 从所有目录中的第几个文件开始播放，默认为 0（第一个）                          |
| -I, --include TEXT         | 筛选包含这个字符串的文件                                                      |
| --include-regex, --IR TEXT | 筛选包含这个正则表达式的文件                                                  |
| -E, --exclude TEXT         | 筛选 不 包含这个字符串的文件                                                  |
| --exclude-regex, --ER TEXT | 筛选 不 包含这个正则表达式的文件                                              |
| --player-params, --PP TEXT | 第三方播放器参数                                                              |
| -m, --m3u8                 | 获取 m3u8 文件并播放                                                          |
| -q, --quiet                | 取消第三方播放器输出                                                          |
| --shuffle, --sf            | 随机播放                                                                      |
| --out-cmd, --OC            | 输出第三方播放器命令                                                          |
| -p, --player [mpv]         | 指定第三方播放器<br><br>默认为 mpv (https://mpv.io)                           |
| -s, --use-local-server     | 使用本地服务器播放。大于 100MB 的媒体文件无法直接播放，需要使用本地服务器播放 |
| --encrypt-key, --ek TEXT   | 加密密钥，默认使用用户设置的                                                  |

## 上传文件

上传一些本地文件或目录到网盘目录。

上传过程中，按 “p” 可以暂停或继续上传。

```
BaiduPCS-Py upload [OPTIONS] [LOCALPATHS]... REMOTEDIR
```

### 选项

| Option                                                     | Description                    |
| ---------------------------------------------------------- | ------------------------------ |
| --encrypt-key, --ek TEXT                                   | 加密密钥，默认使用用户设置的   |
| -e, --encrypt-type [No \| Simple \| ChaCha20 \| AES265CBC] | 文件加密方法，默认为 No 不加密 |
| -w, --max-workers INTEGER                                  | 同时上传文件数                 |
| --no-ignore-existing, --NI                                 | 上传已经存在的文件             |
| --no-show-progress, --NP                                   | 不显示上传进度                 |

## 同步本地目录到远端

同步本地目录到远端。

如果本地文件 md5 和远端不同则上传文件。对于本地不存在的文件但远端存在则删除远端文件。

```
BaiduPCS-Py sync [OPTIONS] LOCALDIR REMOTEDIR
```

### 选项

| Option                                                     | Description                    |
| ---------------------------------------------------------- | ------------------------------ |
| --encrypt-key, --ek TEXT                                   | 加密密钥，默认使用用户设置的   |
| -e, --encrypt-type [No \| Simple \| ChaCha20 \| AES265CBC] | 文件加密方法，默认为 No 不加密 |
| -w, --max-workers INTEGER                                  | 同时上传文件数                 |
| --no-show-progress, --NP                                   | 不显示上传进度                 |

## 分享文件

**注意：使用这个命令需要 cookies 中含有 `STOKEN` 值。**

```
BaiduPCS-Py share [OPTIONS] [REMOTEPATHS]...
```

### 选项

| Option              | Description                      |
| ------------------- | -------------------------------- |
| -p, --password TEXT | 设置秘密，4 个字符。默认没有秘密 |

## 列出分享链接

```
BaiduPCS-Py shared
```

### 选项

| Option         | Description                                  |
| -------------- | -------------------------------------------- |
| -S, --show-all | 显示所有分享的链接，默认只显示有效的分享链接 |

## 取消分享链接

```
BaiduPCS-Py cancelshared [OPTIONS] [SHARE_IDS]...
```

## 保存其他用户分享的链接

**注意：使用这个命令需要 cookies 中含有 `STOKEN` 值。**

保存其他用户分享的链接到远端目录。

```
BaiduPCS-Py save [OPTIONS] SHARED_URL REMOTEDIR
```

### 选项

| Option                | Description                        |
| --------------------- | ---------------------------------- |
| -p, --password TEXT   | 链接密码，如果没有不用设置         |
| --no-show-vcode, --NV | 不显示验证码，如果需要验证码则报错 |

## 添加离线下载任务

```
BaiduPCS-Py add [TASK_URLS]... REMOTEDIR
```

## 列出离线下载任务

```
# 列出所有离线下载任务
BaiduPCS-Py tasks

# 也可列出给定id的任务。
BaiduPCS-Py tasks [TASK_IDS]...
```

## 清除已经下载完和下载失败的任务

```
BaiduPCS-Py cleartasks
```

## 取消下载任务

```
BaiduPCS-Py canceltasks [TASK_IDS]...
```

## 删除所有离线下载任务

```
BaiduPCS-Py purgetasks
```

### 选项

| Option | Description  |
| ------ | ------------ |
| --yes  | 确定直接运行 |

## 开启 HTTP 服务

在远端 `ROOT_DIR` 目录下开启 HTTP 服务。

`ROOT_DIR` 默认为 `/`

```
BaiduPCS-Py BaiduPCS-Py server [OPTIONS] [ROOT_DIR]
```

如果需要设置认证，使用下面的选项设置用户名和密钥：

```
BaiduPCS-Py BaiduPCS-Py server [ROOT_DIR] --username 'foo' --password 'bar'
```

### 选项

| Option                   | Description                  |
| ------------------------ | ---------------------------- |
| -h, --host TEXT          | 监听 host                    |
| -p, --port INTEGER       | 监听 port                    |
| -w, --workers INTEGER    | 进程数                       |
| --encrypt-key, --ek TEXT | 加密密钥，默认使用用户设置的 |
| --username TEXT          | HTTP Basic Auth 用户名       |
| --password TEXT          | HTTP Basic Auth 密钥         |
