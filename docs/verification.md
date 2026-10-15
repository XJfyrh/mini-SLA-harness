# 实际验证记录

2026-10-15，分支 `XJfyrh/project-skills`，Windows x64、Python 3.14.7、SQLite 3.50.4。

| 命令或检查 | 实际结果 |
| --- | --- |
| `python scripts/dev.py bootstrap` | 通过：含锁定 PyYAML 的开发依赖、editable 安装和依赖一致性检查 |
| `python scripts/dev.py check` | 通过：环境、格式、lint、严格类型、仓库规则、36 项 unittest、依赖一致性、wheel 安装验收 |
| `python scripts/dev.py demo` | 通过：3 条固定记录、实际 SQLite 重开读取、稳定 JSON |
| `skill-creator` 的 `quick_validate.py` | 7 个项目技能全部通过，使用项目 Python 的 UTF-8 模式 |
| Codex app-server `skills/list` | 7 个项目技能均被发现并启用，项目加载错误为 0 |
| `.venv/Scripts/python.exe -m mypy --platform linux` | Linux 类型分支检查通过 |
| `python scripts/dev.py doctor --target` | 退出 1：目标要求 Linux，当前为 Windows；SQLite 3.50.4 未达到要求的 WAL-reset 修复版本 |
| Windows/Linux GitHub Actions | 已配置；尚未推送或执行云端工作流 |

12 项反馈测试通过真实子进程、数据库和文件变更验证：

- 多项检查失败后继续执行，汇总保留各自退出码。
- 命令启动前已有 `running` 记录；无法启动时保存具体失败。
- 超时前的 stdout/stderr 保留；父命令超时后，实际孙进程的监听端口关闭。
- 预期错误退出码可通过验收，错误地返回成功会被拒绝。
- 每次运行证据目录独立；源码变化、未跟踪文件变化和错误仓库归属能被识别。
- wheel 构建失败后不启动安装；环境探针遇到真实目录冲突时失败并保留原文件。
- SQLite 版本检查区分已修复分支及相邻未修复版本。

4 项技能检查测试覆盖相邻技能和参考文档链接、入口及正文缺失、损坏的 YAML、名称不匹配和 description 缺失/类型错误。实际执行检查命令，违规时退出 1、修复后退出 0。

安装验收继续验证全新 venv、已安装 CLI、真实导入位置、数据库完整行值、跨进程重开、JSON 字节稳定，以及未知命令、已有文件和数据库冲突的失败行为。

## 原则扩充与分类路由

2026-10-15，分支 `XJfyrh/principle-routing`：20 个技能通过 `quick_validate.py`，本机 Codex 的 `skills/list` 实际发现并启用全部 20 个技能，项目加载错误为 0。入口和分类链接的可达性检查覆盖 2 条核心原则、5 类路由和全部 19 条原则，没有遗漏或无效目标。

元数据、发现结果和链接连通性分别核验；后续使用中的决策效果按 [技能维护方法](development.md#作战手册) 观察具体任务的动作和产物。

2026-10-15，分支 `XJfyrh/playbook`：重命名后的 `playbook` 与 19 个 `principle-*` 技能通过格式和发现校验；Codex 返回的入口显示名称为“作战手册”。将整包复制到不含项目文档的隔离目录后，53 个本地链接全部有效，分类路由覆盖全部原则。

2026-10-15，分支 `XJfyrh/show-me-your-work`：新增技能通过格式校验，Codex 实际发现并启用全部 21 个技能，路由没有遗漏；隔离复制后的 56 个本地链接有效。日志辅助脚本的 6 项测试通过真实子进程和文件验证追加、会话接手、损坏拒绝与更正保留；脚本已纳入格式、lint 和严格类型检查。

每次执行输出对应的证据目录，`summary.json` 记录 HEAD 与开始/结束源码指纹；日志和结果格式见 [测试说明](testing.md)。历史记录只证明其记录的源码与环境，检查当前代码时重新运行 [开发入口](development.md)。

目标运行环境的下一步是：在 Linux 上选择含 WAL-reset 修复的 Python/SQLite 组合，重跑 `doctor --target`，再逐项执行 [早期环境与集成探针](design/04-implementation-validation.md)。当前尚未运行真实模型、目标容器隔离或性能校准。
