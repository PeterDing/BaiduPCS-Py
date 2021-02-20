# Changelog

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
