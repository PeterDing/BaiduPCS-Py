# Changelog

## v0.7.6 - 2023-03-22

### Added

- 增加 `--downloader-params` 参数，支持给第三方下载器加参数。

### Fixed

- 修复「转存文件数超限」错误。

## v0.7.5 - 2023-01-30

### Fixed

- 修复安装失败。(#105)
- 修复用第三方下载器时进度条闪烁的问题。

### Changed

- 目前不支持 Python3.11

## v0.7.4 - 2022-11-10

### Changed

- 在下载和上传时，让调用者去初始化进度条。

### Updated

- 更新依赖。

## v0.7.3 - 2022-11-09

### Updated

- `BaiduPCSApi.list` 支持 `recursive` 参数，递归遍历目录。

## v0.7.2 - 2022-10-31

### Added

- `updateuser` 命令支持 更新所有用户信息。

### Updated

- 等上传时用户空间不足时，抛出 `error_code: 31112, 超出配额` 异常。

## v0.7.1 - 2022-08-04

### Fixed

- 修复 `play` 命令。

## v0.7.0 - 2022-08-03

### Added

- 支持设置帐号名。
- 支持命令行自动完成。

## v0.6.32 - 2022-01-23

### Updated

- 增加 `du` 命令，统计网盘路径下的文件所占用的空间。(#80)

## v0.6.31 - 2022-01-15

### Updated

- 更新依赖。

### Fixed

- 修复没有检查 "剩余空间不足，无法转存" 的错误。

## v0.6.30 - 2022-01-13

### Fixed

- 修复所有 `--include-regex` 选项。

## v0.6.29 - 2021-10-24

### Fixed

- 修复不能上传空文件的问题。(#76)

### Changed

- `--shuffle` 选项使用系统随机函数。

## v0.6.28 - 2021-10-03

### Updated

- 更新下载连接接口。
- 现在所有的分享都必须设置密码。
- 无 `MAX_CHUNK_SIZE` 限制。

## v0.6.27 - 2021-08-25

### Changed

- 更新 `PCS_UA`，解决 SVIP 下载限速的问题。 (#66)
- `download` 命令的 `--chunk-size` 选项最大为 `5M`。这是百度服务端的限制。

## v0.6.26 - 2021-07-29

### Changed

- 设置 HTML 页面宽度为 80% 当页面宽度大于 1000px。

### Fixed

- 修复上传时，文件路径错误的问题。

## v0.6.25 - 2021-07-11

### Added

- 支持多种分享连接。

  如：

  - https://pan.baidu.com/s/...
  - https://pan.baidu.com/wap/init?surl=...
  - https://pan.baidu.com/share/init?surl=...

### Changed

- 上传块默认大小调整为 30M。

## v0.6.24 - 2021-07-10

### Added

增加 `upload` 命令选项 `--upload-type`。

指定上传方式：

`--upload-type Many`: 同时上传多个文件。

适合大多数文件长度小于 100M 以下的情况。

```
BaiduPCS-Py upload --upload-type Many [OPTIONS] [LOCALPATHS]... REMOTEDIR
```

`--upload-type One`: 一次只上传一个文件，但同时上传文件的多个分片。

适合大多数文件长度大于 1G 以上的情况。

```
BaiduPCS-Py upload --upload-type One [OPTIONS] [LOCALPATHS]... REMOTEDIR
```

## v0.6.23 - 2021-07-08

### Fixed

- 修复 `me` 下载器文件大小显示错误的问题。

## v0.6.22 - 2021-07-06

### Fixed

- 修复保存分享连接时重复检查路径。

## v0.6.21 - 2021-06-21

### Changed

- 设置 HTML 页面宽度为 80%。
- 设置 IO `READ_SIZE` 为 65535，减少下载时的 CPU 使用。
- 下载 url 移除 `&htype=`。

### Fixed

- 修复保存分享连接时出错。(`error_code: 31066, message: 文件不存在`)

## v0.6.20 - 2021-05-15

### Fixed

- 移除 debug print。

## v0.6.19 - 2021-05-14

### Added

- 支持为分享连接设置有效时间。 (#42)

## v0.6.18 - 2021-04-26

### Fixed

- 修复 Windows 上下载出错。 (#40)
- 修复 `--chunk-size 50m` 出错。

## v0.6.17 - 2021-04-18

### Fixed

- 修复 http server 中 url 出错。
- 修复 `play -s` 时 url 出错。

### Changed

- 下载 `--chunk-size` 选项不能大于 50M。
- 过滤已经存在的文件，加快保存速度。

## v0.6.16 - 2021-03-29

### Fixed

- 修复在非终端中上传时出错。 (#34)

### Added

- `search` 命令增加 `--csv` 选项。

## v0.6.15 - 2021-03-22

### Fixed

- 修复在 bash 用 `ctl-c` 退出后，终端无法显示输入。 (#31)

## v0.6.14 - 2021-03-19

### Fixed

- 修复 `su` 命令出错。
- 修复 `userlist` 命令出错。（确保 `PcsUserProduct.name` 不为空）(#30)

## v0.6.13 - 2021-03-18

### Fixed

- 修复保存分享连接时，文件路径消失。

### Added

- 切换当前用户支持指定用户所在位置。 (#29)

## v0.6.12 - 2021-03-17

### Fixed

- 修复解析分享连接信息出错。

## v0.6.11 - 2021-03-13

### Fixed

- 修复保存部分分享连接时出错。

### Changed

注意，下面几个 api 不是线程安全的：

- `BaiduPCSApi.access_shared`
- `BaiduPCS.access_shared`
- `BaiduPCSApi.shared_paths`
- `BaiduPCS.shared_paths`

## v0.6.10 - 2021-03-13

### Fixed

- 修复保存分享连接时出错。 #19 #24

## v0.6.9 - 2021-03-06

### Fixed

- 更新 rich，修复进度条死锁的问题。

## v0.6.8 - 2021-03-05

### Changed

- 小于 v0.6.8 的版本，如果上传本地目录 `localdir` 到远端目录 `remotedir`，BaiduPCS-Py 是将 `localdir` 下的所有文件（包括下级目录）上传到远端目录 `remotedir` 下。

  比如，`localdir` 下有 2 个文件 `a`，`b` 和一个下级目录 `sub/`，如果运行 `BaiduPCS-Py upload localdir remotedir`，结果是远端目录 `remotedir` 下增加了 2 个文件 `a`，`b` 和一个下级目录 `sub/`。

- 大于或等于 v0.6.8 的版本，如果上传本地目录 `localdir` 到远端目录 `remotedir`，BaiduPCS-Py 是将 `localdir` 这个目录上传到远端目录 `remotedir` 下。

  比如，`localdir` 下有 2 个文件 `a`，`b` 和一个下级目录 `sub/`，如果运行 `BaiduPCS-Py upload localdir remotedir`，结果是远端目录 `remotedir` 下增加了 1 个下级目录和它的所有文件 `localdir/a`，`localdir/b` 和一个下级目录 `localdir/sub/`。

  如果要将 `localdir` 下的所有文件（包括下级目录）上传到远端目录 `remotedir`，用 `BaiduPCS-Py upload localdir/* remotedir`

- 在命令 `ls`，`download`，`play` 中，如果选用了递归参数 `--recursive`，那么对于所有的过滤选项都**不会**作用在目录上。

### Added

- 增加 traceback 到 log

## v0.6.7 - 2021-03-03

### Fixed

- 修复添加离线下载任务总是显示 “资源存在但下载失败”。

### Changed

- `BaiduPCSApi.add_task` 只能添加 http/s 任务。
- 用 `BaiduPCSApi.add_magnet_task` 添加 magnet 任务。

## v0.6.6 - 2021-03-01

### Added

- 增加 `listsharedpaths` 命令，列出其他用户分享链接中的文件。

### Fixed

- 修复保存分享连接时，保存的文件不全。

## v0.6.5 - 2021-03-01

### Added

- 为只显示下载连接或秒传连接，`ls`，`rplist`，`rpsearch` 命令增加 `--only-dl-link`, `--only-hash-link` 选项。

### Changed

- `ls` 和 `server` 显示的文件修改时间从服务器文件修改时间改为本地文件修改时间。

## v0.6.4 - 2021-02-28

### Added

- 支持从指定文件获取要使用的秒传连接。

### Changed

- 在获取秒传连接时，保持远端文件创建时间和最后修改时间不变。

### Fixed

- 修复 `ls --csv`。
- 修复获取下载连接和请求下载连接错误。

## v0.6.3 - 2021-02-27

### Changed

- 更新上传 api。
- 上传和同步支持本地文件创建时间和最后修改时间。
- 同步是不再比对 md5，只比对文件大小和最后修改时间。
- 秒传连接中文件名的空格改为 `%20`。
- 删除文件时，如果文件不存在，不再报错。

## v0.6.2 - 2021-02-27

### Added

- `rp` 命令支持 `--input-file`

### Fixed

- 修复打印错误

### Changed

- 本地储存表 `rapid_upload` 移除 `content_crc32` 作为 key。
- 选项 `--SA` 改为 `-A`，`--hlp` 改为 `--HLP`。

## v0.6.1 - 2021-02-26

### Fixed

- 修复列出“已过期的”分享连接时出错。

## v0.6.0 - 2021-02-26

### Added

#### 支持秒传连接

- 支持秒传信息的本地存储，查看，搜索。
- 支持远端文件秒传信息读取。
- 支持使用 `cs3l`，`short`，`bpban` 协议。

## v0.5.19 - 2021-02-20

### Added

- HTTP 服务支持设置服务路径

## v0.5.18 - 2021-02-19

### Changed

#### Encryption File Version 3

使用 openssl 加密文件的方式来生成 encrypt key 和 nonce or iv 来加密文件 head。文件内容使用 encrypt password 和 随机 salt 生成 encrypt key 和 nonce or iv 来加密。

同时兼容 Encryption File Version 1

不兼容 Encryption File Version 2

## v0.5.17 - 2021-02-18

### Changed

#### Encryption File Version 2

使用 openssl 加密文件的方式来生成 encrypt key 和 nonce or iv 来加密文件 head。文件内容使用 encrypt key 和 随机 nonce or iv 来加密。

同时兼容 Encryption File Version 1

## v0.5.16 - 2021-02-16

### Added

- 支持同时对多个帐号进行操作

  下面的命令支持对多个帐号进行操作:

  - pwd
  - ls
  - search
  - cat
  - mkdir
  - move
  - rename
  - copy
  - remove
  - download
  - play
  - upload
  - sync
  - share
  - shared
  - cancelshared
  - save
  - add
  - tasks
  - cleartasks
  - canceltasks
  - purgetasks
  - server

### Changed

- 更新依赖

## v0.5.15 - 2021-02-16

### Fixed

- 修复第三方下载程序解密错误

### Changed

- Set `encrypt_key` and `salt` to bytes

## v0.5.14 - 2021-02-15

### Changed

- `useradd` 命令支持只提供 cookies, (#11)

### Fixed

- 修复 Windows 远端路径错误 (#9)

## v0.5.13 - 2021-02-13

### Fixed

- 修复 aes256cbc 加密解密数据读取错误

## v0.5.12 - 2021-02-13

### Fixed

- 改正打字错误 `265` -> `256`

## v0.5.11 - 2021-02-07

### Fixed

- 修复帐号文件配置出错

### Added

- HTTP 服务返回头加 `content-type`

## v0.5.10 - 2021-02-04

### Fixed

- 修复 Windows 下编码错误 (#7)
- 修复同步上传错误

## v0.5.9 - 2021-02-04

### Fixed

- 修复用户相关服务有效时间

### Changed

- `PcsUser.products: Optional[List[PcsUserProduct]] = None`

### Added

- 自动适应不同版本的 `AccountManager`

## v0.5.8 - 2021-02-03

### Fixed

- BaiduPCS-Py 需要 Python ^3.7

## v0.5.7 - 2021-02-02

### Added

- HTTP 服务支持基本认证
- HTTP 服务支持反目录遍历

## v0.5.6 - 2021-02-02

### Added

- 支持随机播放

## v0.5.5 - 2021-02-01

### Changed

- 上传时开启事件监听

## v0.5.4 - 2021-02-01

### Fixed

- pynput 不能在无 x server 的 linux 服务器上用，换成 https://stackoverflow.com/a/22085679/2478637 的解决方法

## v0.5.3 - 2021-02-01

### Added

- 增加监听事件
- 支持在上传过程中按 ”p“ 暂停或开始上传

## v0.5.2 - 2021-01-31

### Added

- 增加环境变量 `LOG_LEVEL`。`LOG_LEVEL=DEBUG` 开启 debug 模式
- 增加 `--ignore_ext` 选项给 `play`，这样可以不过滤媒体文件。如果媒体文件被命名为`abc.txt`，加这个选项后也可以播放

### Fixed

- 增加下载和上传出错重试
