# 实际验证记录

执行日期：2026-10-15。平台：用户本地 Windows x64，Python 3.14.7，SQLite 3.50.4。
仓库：`E:\dev\mini-SLA-harness`。
分支：`chore/initial-dev-environment`。

## 验证结果

| 操作 | 实际结果 |
| --- | --- |
| 项目 `.venv` | `sys.prefix` 等于项目 `.venv`，与 `sys.base_prefix` 不同 |
| `python scripts/dev.py bootstrap` | 退出 0；锁定工具与 editable 包安装成功；`pip check` 通过 |
| 锁文件发行包下载 | 11 个 wheel 按 SHA-256 校验成功，留在忽略的 `artifacts/wheelhouse/` |
| 锁文件离线安装 | 在目标新建的 `.venv` 中使用 wheelhouse、`--require-hashes --no-deps` 实际安装；pip 由 ensurepip 提供锁定版本 |
| `python scripts/dev.py check` | Ruff format、Ruff lint、Mypy strict、11 项 unittest、pip check 全部通过 |
| `python scripts/dev.py demo` | 退出 0；3 条固定响应，SQLite 新连接回读一致，JSON 已生成 |
| `mini-sla --help` / `--version` | 退出 0；已安装 CLI 可用，版本 `0.0.1` |
| JSON 与重复运行 | 独立 CLI 进程 stdout 可解析并与文件一致；同目录重复/新目录运行 JSON 逐字节一致 |
| Windows 路径与清理 | 含中文、空格、`#` 的 SQLite/CLI 输出路径测试通过，连接可关闭并清理 |

最后一次在最终提交上的复验记录位于本地 `artifacts/verification/summary.json`，
包含实际 HEAD、分支、解释器、锁文件与 demo JSON 的 SHA-256、每条命令退出码、
数据库行数/WAL 和工作区状态。对应 `bootstrap.log`、`check.log`、`demo.log`、
`cli-version.log`、`cli-help.log`、`cli-json.log` 及 `locked-install.log` 均在同目录。
运行产物和复验日志被忽略，源码与指引已提交。

demo 摘要：

```text
Offline smoke demo: ok (3 cases)
Provider: deterministic-fake-v1
SQLite round-trip: passed
Research effect: not evaluated
```

## 执行中修复的问题

- 默认沙箱临时目录不能完成 pip 写入；开发入口将临时文件改到项目 `artifacts/tmp`，随后安装成功。
- 第一轮 Windows 清理测试发现测试连接未关闭；改用显式关闭后，11 项测试全部通过。
- 官方 PyPI 查询有过 DNS/TLS 超时；经执行环境允许的网络访问完成下载，未关闭证书校验。
- 原目录执行时的工具日志中 Python 启动可见 `Failed to find real location of C:\Python314\python.exe`；
  实际解释器、虚拟环境隔离与上述命令退出码均已检查，最终验证通过。

## 交付边界

这是开发骨架验收。TaskSpec、正式 StateStore、候选快照、独立评估、预算、fencing、
恢复、Advisor、Workers 与研究实验仍待实现；设计 M0 Gate 未验收。
没有读取模型凭据、调用真实 API、创建远端、推送、部署或发布。现有用户文件未改动。

## 迁移记录

2026-10-15 按用户指定迁移到 `E:\dev\mini-SLA-harness`。目标目录已存在且为空，经执行环境标准审批允许写入后操作。

Git 历史保留 `834c1eb`、`94bb44b`、`6885438`，沿用原开发分支，目标仓库无远端。源码通过不共享硬链接的本地 clone 复制。

源虚拟环境未复制；在目标重新创建 `.venv`，使用已校验的 wheelhouse 按锁文件安装，随后在目标实际运行 bootstrap、check 和 demo。最终 HEAD 及新位置验证结果以本目录所述 `artifacts/verification/summary.json` 为准。

原目录 `C:\Users\12898\Documents\Codex\2026-10-15\task-2\mini-sla-harness` 保留为迁移备份。后续开发入口为 E 盘目录。
