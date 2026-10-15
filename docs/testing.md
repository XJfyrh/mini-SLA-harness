# 测试与仓库检查

贡献者运行入口见 [开发指南](development.md)，完整顺序以 [dev.py](../scripts/dev.py) 为准。当前测试验证离线开发基础设施；协议验收范围见 [设计范围](scope.md)。

## 行为测试

[test_smoke.py](../tests/test_smoke.py) 使用标准库 unittest，保留真实文件系统、SQLite 与 CLI 子进程，只固定 provider 边界。断言持久化内容、重新连接、重复运行、冲突回滚和退出码。fake/demo 测试禁止 socket 创建。

测试各自拥有临时目录，关闭数据库连接并等待子进程退出后清理。超时、未预期退出或内容不一致均失败，不因环境问题自动跳过。真实模型、研究效果和其他操作系统尚未在这些测试中验证。

## 两类仓库规则

[repo_check.py](../scripts/repo_check.py) 纳入完整 check，仅执行当前有用的规则：

1. 根 README 和 AGENTS 存在；它们及 docs 中的本地 Markdown 内联链接必须指向仓库内存在的目标。识别普通与尖括号目标、百分号编码，忽略代码块和行内代码。外部 URL 不联网查询；片段锚点不校验。引用式链接和 HTML 链接不在当前解析范围。
2. pyproject 的 `mini-sla` 入口必须指向 src 中可解析的 Python 模块和顶层函数定义。它检查声明与实际文件/AST 的关系；运行行为由 CLI 测试验证。

[test_repo_check.py](../tests/test_repo_check.py) 在独立 fixture 中实际破坏链接、删除入口文件、修改 TOML 或重命名入口函数。命令级负例检查非零退出，修复后恢复成功。检查不设中文词数预算。

## 安装制品验收

[package_check.py](../scripts/package_check.py) 使用已有 pip/setuptools 构建 wheel，不新增构建管理器依赖。运行时只有标准库，干净安装可以直接暴露遗漏文件或开发环境依赖。

验收在项目 `artifacts/tmp` 下创建全新 venv，只安装本次 wheel，不安装 editable 包或开发工具。实际 CLI 从独立的临时工作目录启动；子进程只保留操作系统与临时目录所需环境，禁用用户 site 和路径注入。工作目录放置同名干扰模块，另用隔离 Python 进程核实导入路径位于临时环境内。

首次 CLI 退出后，父进程直接打开 SQLite，核对三条 fixture 的全部字段、WAL 与完整性，并对照 JSON 实际内容。第二次 CLI 重启不得增加记录或改变 JSON 字节；第三个只读进程从已安装包重新读取数据库。这里验证的是 demo 跨进程持久化，不是正式恢复协议。

错误路径要求未知命令退出 2、输出目标为已有文件和数据库冲突退出 1。已有文件、冲突数据与上一次 JSON 必须保持原样。每个子进程有 60 秒上限，任一步异常均失败；临时环境在退出时清理。

成功 wheel 留在 `dist/`；逐命令日志、SQLite 实际行值、导入位置和 wheel SHA-256 写入 `artifacts/package-check/summary.json`，正常 demo JSON 另存为 `demo-result.json`。这些路径是本地生成物，不作为文档本地链接。当前验证平台由 [验证记录](verification.md) 负责。

## 工程参考

参考官方 deepseek-ai/deepseek-harness 的固定提交 `571902028a75c64c1d767f4ae5fd099485f0ddf0`：

- [文档归属](https://github.com/deepseek-ai/deepseek-harness/blob/571902028a75c64c1d767f4ae5fd099485f0ddf0/docs/AGENTS.md)：常驻规则、主题说明与导航分别负责各自信息。
- [测试原则](https://github.com/deepseek-ai/deepseek-harness/blob/571902028a75c64c1d767f4ae5fd099485f0ddf0/docs/testing.md)：保留真实下游实现，外部读取实际结果。
- [运行闭包负例](https://github.com/deepseek-ai/deepseek-harness/blob/571902028a75c64c1d767f4ae5fd099485f0ddf0/scripts/verify-runtime-closure.spec.ts)：破坏依赖关系后验证失败。
- [构建 CLI 验收](https://github.com/deepseek-ai/deepseek-harness/blob/571902028a75c64c1d767f4ae5fd099485f0ddf0/apps/cli/tests/built-bin.e2e.ts)：执行构建入口并核对退出、输出与生命周期。

本项目保留单个完整本地 check，不引入参考仓库的插件体系、覆盖率配额或专属 CI 调度。
