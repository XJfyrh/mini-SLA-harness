# 测试与仓库检查

贡献者运行入口见 [开发指南](development.md)，完整顺序以 [dev.py](../scripts/dev.py) 为准。当前覆盖离线开发基础设施和 M0 协议内核；后续协议验收范围见 [设计范围](scope.md)。

## M0 离线协议验收

```powershell
python scripts/dev.py m0-check
python scripts/dev.py check
```

`m0-check` 每次创建独立 `artifacts/verification/m0-*/`，成功输出 `M0 offline acceptance: passed`。入口无需模型账号、付费额度、私有数据或 Docker；fake 分数与 token 用量用于验证协议，实际文件、SQLite、线程竞争和受控子进程保留。当前开发解释器的 SQLite 版本和目标解释器探针分别报告，M0 通过不代表 Docker 或真实模型已验收。

打开打印路径下的 `acceptance/report.json`：10 组场景均应为 passed，`external_model_requests=0`、`usage_kind=simulated_tokens`。每组列出需求编号、实际观测和数据库相对路径；同一输出目录禁止覆盖。安装后也可运行 `mini-sla m0-check --output-dir NEW_DIR --json`；默认不指定目录时生成新的目录。

| 检查内容 | 应观察的结果 |
| --- | --- |
| 任务/候选 | 缺失字段拒绝；候选可按 hash 重建，损坏引用阻断恢复。 |
| 局部保留与幂等 | 全局 90000，新分支依次 85000、83000、96000，head 为 85000、85000、96000；重复 finalize 不增加采纳事件。 |
| 预算竞争 | 两个真实线程各预留 80、Run 余额 100，只有一个成功，held=80。 |
| UNKNOWN 与 scope | 重开后未知预留保留；新 attempt 不重置额度；两次物理假请求合计 confirmed=1150、held=0，cached input 不重复累加。 |
| 强停与执行权 | force/finalize 两种顺序分别保留原 Best 或已采纳 Best；DONE 证据保留；旧提交拒绝；受控假进程退出，迟到用量仍结算。 |
| 基线/规划 | 初始化三个暂停位置与规划五个重开位置收敛到原 job/invocation；未接受响应不采纳；已接受响应恢复提交一次。 |
| 整数评分 | bps=250、old=100000 时，102499 拒绝、102500 晋升；bps=0 仍至少提升 1。 |

[test_protocol.py](../tests/test_protocol.py) 额外覆盖跨进程抢锁、六处直接终止进程、未提交事务回滚、错误角色/编辑范围、无效成绩、usage 冲突/超额、持久重试上限、计划原子回滚和未开始配额的跳过计数。离线场景禁止 socket 创建。既有 demo 测试继续保留。

你可直接打开场景列出的 SQLite；例如 `unknown-scope-accounting/state.sqlite3` 的 runs 应为 confirmed=1150、held=0，逐调用明细在 model_calls/usage_ledger，scope 合计在 budget_scopes。正式 StateStore 与 `demo_records` 使用不同数据库；不要把 demo 结果当 M0 验收。

## 行为测试

[test_smoke.py](../tests/test_smoke.py) 使用标准库 unittest，保留真实文件系统、SQLite 与 CLI 子进程，只固定 provider 边界。断言持久化内容、重新连接、重复运行、冲突回滚和退出码。fake/demo 测试禁止 socket 创建。

测试各自拥有临时目录，关闭数据库连接并等待子进程退出后清理。超时、未预期退出或内容不一致均失败，不因环境问题自动跳过。真实模型、研究效果和 Docker/WSL2 执行边界尚未在这些测试中验证。

## 仓库规则

[repo_check.py](../scripts/repo_check.py) 纳入完整 check，仅执行当前有用的规则：

1. 根 README 和 AGENTS 存在；它们、docs 及 `.agents/skills/` 中的本地 Markdown 内联链接必须指向仓库内存在的目标。识别普通与尖括号目标、百分号编码，忽略代码块和行内代码。外部 URL 不联网查询；片段锚点不校验。引用式链接和 HTML 链接不在当前解析范围。
2. pyproject 的 `mini-sla` 入口必须指向 src 中可解析的 Python 模块和顶层函数定义。它检查声明与实际文件/AST 的关系；运行行为由 CLI 测试验证。
3. `.agents/skills/` 下每个技能目录必须有 `SKILL.md`；YAML 元数据可解析，名称与目录一致且符合命名规则，description 为非空文本，正文存在。

[test_repo_check.py](../tests/test_repo_check.py) 在独立 fixture 中实际破坏链接、删除入口文件、修改 TOML 或重命名入口函数。技能检查覆盖相邻技能引用、参考文档及元数据；删除被引用技能或损坏 YAML 后命令非零退出，恢复后通过。

[test_decision_log.py](../tests/test_decision_log.py) 从独立工作目录运行技能的 Python 日志脚本，读取实际 TSV 和原始字节，验证追加不改旧行、会话接手、失败与更正保留、UTF-8 与单行单元格。表头错误、损坏或截断、空字段与目录冲突均须非零退出，并保留已有内容。

## 安装制品验收

[package_check.py](../scripts/package_check.py) 使用已有 pip/setuptools 构建 wheel，不新增构建管理器依赖。运行时只有标准库，干净安装可以直接暴露遗漏文件或开发环境依赖。

验收在项目 `artifacts/tmp` 下创建全新 venv，只安装本次 wheel，不安装 editable 包或开发工具。实际 CLI 从独立的临时工作目录启动；子进程只保留操作系统与临时目录所需环境，禁用用户 site 和路径注入。工作目录放置同名干扰模块，另用隔离 Python 进程核实导入路径位于临时环境内。

首次 CLI 退出后，父进程直接打开 SQLite，核对三条 fixture 的全部字段、WAL 与完整性，并对照 JSON 实际内容。第二次 CLI 重启不得增加记录或改变 JSON 字节；第三个只读进程从已安装包重新读取数据库。

错误路径要求未知命令退出 2、输出目标为已有文件和数据库冲突退出 1。已有文件、冲突数据与上一次 JSON 必须保持原样。每个子进程有 60 秒上限，任一步异常均失败；临时环境在退出时清理。

成功 wheel 留在 `dist/`；SQLite 实际行值、导入位置和 wheel SHA-256 写入本次安装验收的 `summary.json`，正常 demo JSON 另存为 `demo-result.json`。当前验证平台由 [验证记录](verification.md) 负责。

干净 wheel 验收还从独立工作目录执行完整 M0 CLI，回读 UNKNOWN 场景的实际预算行，并验证已有 M0 输出目录被拒绝且报告字节不变。结果另存为 `m0-result.json`；临时安装环境仍在检查结束时清理。

## 反馈与证据

[evidence.py](../scripts/evidence.py) 为 check、demo、doctor 和独立 package-check 创建 `artifacts/verification/<类型>-<时间>-<随机标识>/`。完整 check 的环境和安装验收放在同次目录的 `doctor/`、`package/` 中，避免覆盖旧结果。

- `summary.json`：HEAD、Git 管理及未忽略文件的内容指纹、实际解释器/平台/SQLite、开始与结束时间；逐命令参数、工作目录、预期与实际退出码、耗时、状态和日志路径。环境变量和凭据不写入报告。
- `*.stdout.log`、`*.stderr.log`：子进程直接写入的原始输出；超时或中断前的内容仍保留。`*.log` 汇合完成后的两路输出，便于阅读。
- 命令启动前落盘 `running`；启动失败、非预期退出、超时分别记录。中断遗留的 `running` 表示未完成，不能当作通过。超时终止进程树后记录实际退出码。
- 任一检查失败、源码在验证期间改变或源码身份无法取得，整体返回非零。指纹覆盖新增、修改和删除，忽略 Git 忽略的生成物；阅读历史结果时必须核对源码身份。

[test_feedback.py](../tests/test_feedback.py) 启动实际报错、超时、无法启动的命令，检查继续执行、退出码与持久日志；破坏构建后端验证后续安装不执行；改动源码验证旧结果不能证明新代码通过；阻塞数据库目录验证环境探针真实失败。

## 工程参考

参考官方 deepseek-ai/deepseek-harness 的固定提交 `571902028a75c64c1d767f4ae5fd099485f0ddf0`：

- [文档归属](https://github.com/deepseek-ai/deepseek-harness/blob/571902028a75c64c1d767f4ae5fd099485f0ddf0/docs/AGENTS.md)：常驻规则、主题说明与导航分别负责各自信息。
- [测试原则](https://github.com/deepseek-ai/deepseek-harness/blob/571902028a75c64c1d767f4ae5fd099485f0ddf0/docs/testing.md)：保留真实下游实现，外部读取实际结果。
- [运行闭包负例](https://github.com/deepseek-ai/deepseek-harness/blob/571902028a75c64c1d767f4ae5fd099485f0ddf0/scripts/verify-runtime-closure.spec.ts)：破坏依赖关系后验证失败。
- [构建 CLI 验收](https://github.com/deepseek-ai/deepseek-harness/blob/571902028a75c64c1d767f4ae5fd099485f0ddf0/apps/cli/tests/built-bin.e2e.ts)：执行构建入口并核对退出、输出与生命周期。
