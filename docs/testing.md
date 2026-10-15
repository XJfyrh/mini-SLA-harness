# 测试与仓库检查

贡献者运行入口见 [开发指南](development.md)，完整顺序以 [dev.py](../scripts/dev.py) 为准。当前测试验证离线开发基础设施；协议验收范围见 [设计范围](scope.md)。

## 行为测试

[test_smoke.py](../tests/test_smoke.py) 使用标准库 unittest，保留真实文件系统、SQLite 与 CLI 子进程，只固定 provider 边界。断言持久化内容、重新连接、重复运行、冲突回滚和退出码。fake/demo 测试禁止 socket 创建。

测试各自拥有临时目录，关闭数据库连接并等待子进程退出后清理。超时、未预期退出或内容不一致均失败，不因环境问题自动跳过。真实模型、研究效果和其他操作系统尚未在这些测试中验证。

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
