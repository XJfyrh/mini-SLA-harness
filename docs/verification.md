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
| `python scripts/dev.py doctor --target`（平台修订前） | 退出 1：当时目标要求 Linux，当前为 Windows；SQLite 3.50.4 未达到要求的 WAL-reset 修复版本 |
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

## Windows 宿主首版平台

2026-10-15，分支 `XJfyrh/windows-host-scope`：首版平台修订为 Windows 宿主 + Docker Desktop/WSL2 Linux 容器，职责见 [设计范围](scope.md)。`python scripts/dev.py doctor --target` 实测 Windows 平台检查通过，SQLite WAL 写入、重开读取与完整性检查通过；宿主 SQLite 3.50.4 未满足 WAL-reset 修复版本要求，因此目标前置检查仍未通过。证据位于 `artifacts/verification/doctor-20261015T104108.125531Z-89b5fb18/summary.json`。

下一步是在 Windows 宿主选择含修复的 Python/SQLite 组合，重跑 `doctor --target`，再逐项执行 [早期环境与集成探针](design/04-implementation-validation.md)。Docker Desktop/WSL2 后端、Windows 控制管道、目标容器隔离、产物发布与性能校准均待验收；当前尚未运行真实模型。

## M0 离线协议内核

2026-10-15，`main`：新增正式 StateStore、候选 CAS、TaskSpec 与 M0 验收入口，当前能力与剩余阶段见 [设计范围](scope.md)。`python scripts/dev.py m0-check` 的 10 组离线场景通过，原始报告位于 `artifacts/verification/m0-20261015T112924.702672Z-721739c5/`；外部模型请求为零，分数与 token 用量均为 fake。

系统 Python 和项目 `.venv` 保持原样（3.14.7／SQLite 3.50.4）。另在忽略的 `artifacts/runtime/python-3.14.8/` 准备隔离 CPython，并将该目录的 SQLite DLL 替换为官方 3.54.0，原 DLL 保留备份；没有替换系统文件或注册解释器。该组合的 WAL 写入、重开、完整性及 `doctor --target` 全部通过，记录位于 `artifacts/verification/doctor-20261015T111947.724484Z-c548b892/`；这证明宿主基础前提，不证明 Docker 执行边界。

下载来源及校验：

- [CPython 3.14.8 Windows x64 embeddable](https://www.python.org/downloads/release/python-3148/)：SHA-256 `a93abe456ab01bd96d7a085b3cdb6566b3063f4241360d114142fbdb07f0a310`。原包仍含 SQLite 3.50.4，不能仅靠 Python 版本号判断修复。
- [SQLite 3.54.0 Windows x64 DLL](https://www.sqlite.org/download.html)：归档名 `sqlite-dll-win-x64-3540000.zip`，SHA3-256 `f5fb500c73a3afd89976386bb8e4fdc8b5b65c052e187fb1ada1f5de034cd45b`。

隔离解释器的 `python314._pth` 显式加入本仓库根目录与 src，供本地源码测试；这与干净 wheel 安装验收是两条独立路径。工作依据日志在 `artifacts/audit/m0.tsv`，最终所选检查的源码指纹、日志与退出码由本次 `artifacts/verification/` 报告记录。

## 固定环境与 M0 独立审查修复

2026-10-15，阶段分支 `XJfyrh/m0-delivery-foundation`：将上述手工环境改为 [可重复准备入口](development.md#尽早检查环境)，Windows 默认 M0 验收和目标 doctor 使用固定运行时。真实归档下载、首次准备、重复复用、文件漂移拒绝及 WAL 重开已通过，记录为 `artifacts/verification/runtime-slice-20261015T120818.747200Z-61742d96/summary.json`。首次整目录发布曾连续遇到 WinError 5，失败记录保留在 `runtime-slice-20261015T120639.623059Z-22c2a431/` 和 `runtime-reproduce-20261015T120747.789481Z-274efaab/`；当前以最后写入的完整清单标记就绪，中断目录保留并拒绝执行。

一个未参与实现的代理独立审查固定提交 `631a04e`：现有 20 项协议测试通过，独立探针仍复现了已开始基线的停止屏障错误和 SEARCH 设施耗尽后 Assignment/Epoch 未终结。报告及原始数据库见 `artifacts/review/m0-631a04e.md` 和同目录探针；固定环境切片 `1fef2a5` 另经该代理检查归档哈希、真实版本与中断保留，没有发现已复现缺陷。

实现者新增回归先复现失败，再分别修复停止排空和重试耗尽收尾。失败证据为 `artifacts/verification/drain-regression-before-20261015T121316.359101Z-27284785/`、`drain-trial-before-20261015T121335.405712Z-6052bd40/`、`exhaustion-regression-before-20261015T121527.467451Z-119abd0a/` 与 `worker-exhaustion-before-20261015T121556.402693Z-b970a6dd/`。修复后的 25 项协议测试在固定运行时通过，证据为 `artifacts/verification/exhaustion-regression-after-20261015T121628.301328Z-dcf68366/summary.json`。这些是各切片的历史结果；交付时仍按当前稳定源码运行完整 check 与 m0-check，并复核修复提交。GitHub CI 尚未执行。

本阶段关键失败、方案调整、独立复核与交付记录集中在 `artifacts/audit/m0-delivery.tsv`，不覆盖早期失败，也不补造缺失输出。
