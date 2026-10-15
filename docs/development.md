# 开发指南

面向参与开发的人和 agent。首次体验看 [README](../README.md)，实现边界看 [架构](architecture.md)，验证方法看 [测试说明](testing.md)。

## 日常开发

首次或锁定依赖变化后执行 `python scripts/dev.py bootstrap`。本地任务按下文的改动影响选择验证；代码、测试、脚本、依赖或构建变更在交付前运行完整检查：

```powershell
python scripts/dev.py check
```

check 先观察开发环境，再执行格式、lint、严格类型、仓库规则、全部 unittest、依赖一致性和 wheel 安装验收。独立检查全部执行并汇总失败，任一失败返回非零退出码；wheel 构建失败则停止依赖它的安装和运行。每次运行打印独立证据目录，格式见 [测试说明](testing.md)。单独重跑制品验收：

```powershell
python scripts/dev.py package-check
```

影响 demo 的调用方式、输出或持久化结果时，另运行 `python scripts/dev.py demo` 并读取实际产物。

成功 wheel 留在 `dist/`；验收内容和证据格式由测试说明负责。Windows 直接使用 CLI 可运行：

```powershell
.\.venv\Scripts\mini-sla.exe --help
.\.venv\Scripts\mini-sla.exe --version
.\.venv\Scripts\mini-sla.exe demo --output-dir artifacts/another-demo --json
```

`--json` 使 stdout 只包含 JSON。macOS/Linux 使用同一开发入口，直接 CLI 路径为 `.venv/bin/mini-sla`；若系统命令叫 `python3`，替换入口中的 `python`。实际测试平台见验证记录。

## 按影响选择验证与审查

依据影响范围、失败后果和已有证据选择下表；混合改动合并相应检查。判断会影响哪些调用方、契约和产物，不能只按文件扩展名或改动行数选择。

| 改动 | 最早反馈与审查重点 | 交付验证 |
| --- | --- | --- |
| 纯文字、链接、技能元数据 | 核对语义、触发条件与引用；确认没有改变命令或契约 | 阅读 diff，运行仓库规则检查 |
| 技能决策规则、开发流程 | 核对触发条件、任务范围与规则冲突 | 仓库规则检查；在适用的真实任务中观察实际动作和产物，未试用的场景标为待验证 |
| 代码、测试、可执行脚本 | 先复现或运行相关行为测试，沿调用方审查输出和失败路径 | 局部闭环后运行完整 check；涉及 demo 行为时另跑 demo |
| 依赖或构建配置 | bootstrap，确认安装与入口行为 | 完整 check；涉及 demo 行为时另跑 demo |
| 协议、持久化或并发实现 | 在代码检查基础上核对不变量，以及失败后的状态和副作用 | 增加对应故障、重复执行或竞态验证；数据库结果重开读取 |
| 外部集成、目标环境或性能 | 首次依赖前运行最小真实探针或测量校准 | 检查实际响应、原始样本及环境；代码变更同时遵循上述检查 |

仓库规则检查使用现有入口，覆盖本地链接、技能元数据和 CLI 声明。Windows：

```powershell
.\.venv\Scripts\python.exe scripts/repo_check.py
```

macOS/Linux 使用 `.venv/bin/python scripts/repo_check.py`。纯文字或技能规则变更按对应行验证；技能包含的 Python 脚本变更按代码验证。修改公开命令、验收条件或协议说明时，核对实际入口与契约依据，已有实现需验证相应行为。

审查测试改动时核对预期值的需求或契约依据；涉及持久化、重试或并发时追查中断和重复执行后的状态。重要改造存在未解决的语义疑点时，安排有针对性的复核，核实发现后修复或说明取舍。

完整 check 保留统一入口；本地先取得相关反馈，交付前在稳定代码上执行所选检查。检查通过后只在代码变化、出现新失败或未决问题时补跑受影响验证。CI 继续执行本页规定的完整工作流。

## 按任务建立反馈

| 任务 | 最早要取得的证据 | 完成条件 |
| --- | --- | --- |
| 修复错误 | 用真实入口、输入与副作用复现失败 | 证明原实现失败、修复后通过；相关非法输入仍被拒绝，完成按影响选择的检查 |
| 新增行为 | 写明可观察的输入、输出、失败行为；先跑最小纵向路径 | 行为测试检查结果和持久化内容，安装后的入口行为一致 |
| 协议修改 | 对应 T 编号、受影响的不变量与故障触发点 | 实际注入故障并检查状态、产物和计量；更新负责该契约的正文 |
| 外部集成或环境假设 | 最小真实探针，记录版本、响应、错误与耗时 | 探针结果支持继续实现，或据失败结果修订方案 |

验收条件从需求或契约确定，执行中发现遗漏则补齐。遇到重复失败时，检查原始输出与前提是否成立；不要靠扩大 mock、吞掉异常、自动 skip 或放宽断言消除失败。新增检查也应通过实际破坏规则来证明能发现问题。

真实模型探索的调用范围、额度和停止条件见 [实施与验收](design/04-implementation-validation.md)。已有授权覆盖的可逆工作直接推进；需要新授权的调用先准备可审查的探针与配置。

普通任务通过提交与验证输出交付，说明行为变化、实际执行的命令、结果和剩余问题。已有验证报告直接引用；单项检查保留可定位的命令与实际输出。未运行的检查标为未运行，设计预期写在验收条件中。验证期间源码变化会使本次报告失败，需在稳定工作区重跑所选检查。

重要取舍、失败转向、跨阶段推进或交接需要额外上下文时，再按下文的工作记录技能保留决策依据；用户明确要求记录时直接使用。达到验收条件即交付，额外改进留给后续任务。

## 作战手册

[作战手册](../.agents/skills/playbook/SKILL.md) 在入口展示三条核心原则摘要，详细方法由独立短原则与工作流技能维护，按目标与方案、模型与边界、实现与迁移、诊断与验证、协作与维护五类路由。技能源文件位于 `.agents/skills/`，随代码一起提交；Codex 会从仓库目录发现这些技能，见 [官方说明](https://learn.chatgpt.com/docs/build-skills#where-codex-loads-local-skills)。其他支持读取 Markdown 的 agent 可从 AGENTS.md 中的入口加载。

入口标识为 `playbook`，界面名称为“作战手册”；独立原则使用 `principle-*` 标识。手册维护通用开发方法，本仓库通过 AGENTS.md 接入以下具体约定：

| 需要落实的内容 | 项目入口 |
| --- | --- |
| 运行路径、当前模块职责 | [当前架构](architecture.md) |
| 状态、计量、隔离与恢复契约 | [设计索引](design/README.md)、[状态协议](design/03-state-transactions.md) |
| 环境与真实集成探针、性能校准 | 本页的环境检查、[实施与验收](design/04-implementation-validation.md) |
| 修改后的验证与证据 | 本页的验证选择表、[测试说明](testing.md) |

迁移到其他仓库时，一起复制 `playbook`、`principle-*` 和工作流技能目录（如 `show-me-your-work`），在目标仓库的 AGENTS.md 中连接手册入口及自己的开发约定。

可以用 `$playbook 修复这个问题` 开始任务，也可以点名“先隔离共享状态”“解释测量结果”等原则。入口先匹配分类，再从分类表选择当前决策需要的原则；跨类任务按依赖顺序读取，遇到新问题重新路由。每条原则的 description 负责触发条件，正文负责执行方法。

例如，排查恢复后重复结算，先读“修复根因”，再按观察进入“让重复执行收敛”和相关事务边界；比较性能收益时进入“解释测量结果”；只修改文档措辞时使用“降低阅读成本”。三条核心原则始终适用，按当前决策展开所需正文；同一会话已读且未变化的内容直接复用。

长时间自主执行、多阶段改造或交接需要保留重要取舍与未决事项，或用户要求展示过程时，使用 [show-me-your-work](../.agents/skills/show-me-your-work/SKILL.md)，也可直接指定 `$show-me-your-work`。本仓库的主日志放在 `artifacts/audit/<任务>.tsv`，引用已有验证报告与原始产物；格式和辅助命令由该技能维护。

迭代时，从一次实际失误或重复需求出发，修订能改变决策的最小规则。新增原则先检查是否与已有触发条件重叠，再挂到对应分类；分类负责选择，原则负责方法，项目文档负责命令与协议事实。可机械检查的约束优先放进现有检查入口，需要判断的部分保留短原则。

技能变更按本页验证选择表执行。新增或修改技能时，使用项目 Python 加 `-X utf8` 运行 `skill-creator` 的 `quick_validate.py` 验证 frontmatter。仓库规则检查使用锁定的 PyYAML 解析技能元数据；技能中的 Python 脚本也参与完整 check 的格式、lint 和类型检查，其行为由真实子进程测试验证。静态检查通过与实际任务中的行为有效分别报告。

上游来源、合并关系与调整见 [pstack 吸收映射](../.agents/skills/playbook/references/pstack-map.md)。

## 尽早检查环境

```powershell
python scripts/dev.py doctor
python scripts/dev.py doctor --target
```

doctor 实际观察 Python/SQLite/操作系统，并在临时数据库执行 WAL 写入、关闭连接、重开读取和完整性检查。默认退出码对应开发环境；`--target` 还要求 Linux 和 [状态协议要求的 SQLite 修复版本](design/03-state-transactions.md)。默认 check 也展示这两个目标条件的结果，开发检查与目标前置条件分别判定。

容器权限、Unix socket 访问、跨进程锁、进程树取消和计时校准由 [早期探索](design/04-implementation-validation.md) 逐项验收；doctor 把尚未执行的项目列为 pending_runtime_probes。

## 持续集成

[工作流](../.github/workflows/check.yml) 在 Windows 和 Linux 上执行相同的 bootstrap、check、demo，并在失败时上传已产生的证据。两个平台各自完成检查；check 失败后仍执行 demo。bootstrap 需要 PyPI，后续入口使用本地锁定工具和固定 fixture。

## 安装机制

[dev.py](../scripts/dev.py) 根据平台选择 `.venv/Scripts/python.exe` 或 `.venv/bin/python`，并以仓库根目录为工作目录。可从其他目录通过脚本完整路径调用。

| 文件 | 用途 |
| --- | --- |
| [pyproject.toml](../pyproject.toml) | 包元数据、固定构建后端、CLI、Ruff/Mypy 设置；运行时依赖为空 |
| [requirements-dev.in](../requirements-dev.in) | 有意更新依赖时使用的直接工具列表 |
| [requirements-dev.lock](../requirements-dev.lock) | 全部直接/传递开发依赖及 pip 的版本和发行文件 SHA-256 |

bootstrap 创建或复用 `.venv`，以官方 PyPI、wheel 和 `--require-hashes --no-deps` 安装锁定工具，再使用 `--no-index --no-build-isolation --no-deps -e .` 安装本包，最后执行 `pip check`。editable 构建因此使用已锁定的 setuptools/wheel。方法依据 [pip 重复安装说明](https://pip.pypa.io/en/stable/topics/repeatable-installs/) 与 [Python venv 文档](https://docs.python.org/3.14/library/venv.html)。

锁文件包含各发行版的多平台哈希，安装时选择当前平台 wheel；没有匹配 wheel 时安装失败。首次 bootstrap 需要 PyPI 网络访问。仓库不提交离线安装包，实际测试平台由 [验证记录](verification.md) 说明。

## 维护依赖

在项目内临时虚拟环境中按直接工具列表解析所需更新，导出所有依赖的精确版本，包括 pip。从官方 `https://pypi.org/pypi/<name>/<version>/json` 的 `urls[].digests.sha256` 更新锁文件；同步 pyproject 中的构建后端版本。不要改动系统包。

更新后重新 bootstrap、完整 check 和 demo。普通 check 不升级或联网解析依赖。

## 临时文件与排错

入口把本次进程及其子进程的 TEMP/TMP/TMPDIR 指向 `artifacts/tmp`，兼容执行沙箱的写入范围。虚拟环境、缓存和生成物被 Git 忽略。

- 环境缺失：按 README bootstrap。
- `.venv` 已存在但无解释器：脚本停止；检查内容后再重建，不会自动清空。
- 下载失败：恢复 PyPI 访问后重试，不关闭证书校验或调整系统安全设置。
- 移动仓库：在新位置重建 `.venv`，不要复制含绝对入口路径的环境。
- 格式修复：`.\.venv\Scripts\python.exe -m ruff format .`。
