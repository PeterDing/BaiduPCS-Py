# Changelog

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
