---
name: Bug report / Bug 报告
about: Create a report to help us improve /  创建一份报告来帮助我们改进
title: ''
labels: ''
assignees: ''

---

> **WARNNING**: Please to search the similar bugs, before you report a bug. Don't report a similar bug which existed.
> **注意**：在你提交一份报告前，请先搜索是否存在类似的报告。请勿重复提交内容相同的报告。

**Prerequisites / 报告前提**
Before you report a bug, please let the bug to be reproduced at the latest verion of BaiduPCS-Py.
在你提交报告前，请在 BaiduPCS-Py 的最新版本上复现问题。

At sometimes, there are errors occured by an expired cookie. Before you commit the report, please to check whether cookies are expired.
有时一些错误是由于某个 cookie 超期导致的。在你提交报告前，请先检查你的 cookies 是否超期。

**Describe the bug / 描述 bug**
A clear and concise description of what the bug is.
请清楚的描述你遇到的问题。

**To Reproduce / 复现问题**
Steps to reproduce the behavior:
1. Do '...'
2. Do '....'
3. ...
4. See error

按照下面的步骤可以复现问题：
1. 做 '...'
2. 做 '...'
3. ...
4. 问题出现

**Screenshots / 问题截图**
If applicable, add screenshots to help explain your problem.
> **Don't show `BDUSS` and `cookies`**.

如果可能，请附加问题截图。
> **不要出现 `BDUSS` 和 `cookies`**。

**Envrionment / 运行环境**
 - OS: [e.g. Windows]
 - Python [e.g. Python3.8]
 - BaiduPCS-Py Version [e.g. 0.6.9]

**Runing log / 运行日志**
Please follow steps to paste the content of file `~/.baidupcs-py/running.log`.
1. Remove the file `~/.baidupcs-py/running.log` if it exists.
2. Run the command where the bug occurs with envrionment variable `LOG_LEVEL=DEBUG`.
  e.g. `LOG_LEVEL=DEBUG BaiduPCS-Py upload /abc /`
3. Paste the content of file `~/.baidupcs-py/running.log` after the bug occurs.

> **Don't show `BDUSS` and `cookies`**.

请按照下面的步骤贴出运行日志 `~/.baidupcs-py/running.log` 中的内容。
1. 删除 `~/.baidupcs-py/running.log`，如果存在。
2. 在问题发生的命令前加入环境变量 `LOG_LEVEL=DEBUG`。
  例如：`LOG_LEVEL=DEBUG BaiduPCS-Py upload /abc /`
3. 在问题出现后，贴出 `~/.baidupcs-py/running.log` 中的内容。

> **不要出现 `BDUSS` 和 `cookies`**。

**Additional context / 补充内容**
Add any other context about the problem here.
在这里增加补充内容。
