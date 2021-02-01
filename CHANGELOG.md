# Changelog

## v0.5.4 - 2021-02-01

### Fixed

- pynput 不能在无 x server 的 linux 服务器上用，换成 https://stackoverflow.com/a/22085679/2478637 的解决方法。

## v0.5.3 - 2021-02-01

### Added

- 增加监听事件。
- 支持在上传过程中按 ”p“ 暂停或开始上传。

## v0.5.2 - 2021-01-31

### Added

- 增加环境变量 `LOG_LEVEL`。`LOG_LEVEL=DEBUG` 开启 debug 模式。
- 增加 `--ignore_ext` 选项给 `play`，这样可以不过滤媒体文件。如果媒体文件被命名为`abc.txt`，加这个选项后也可以播放。

### Fixed

- 增加下载和上传出错重试。
