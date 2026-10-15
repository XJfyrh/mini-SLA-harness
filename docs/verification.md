# 实际验证记录

2026-10-15，在 `E:\dev\mini-SLA-harness` 的 `chore/repo-verification` 分支执行。平台为 Windows x64、Python 3.14.7、SQLite 3.50.4。

## 本轮结果

| 验证对象 | 实际结果 |
| --- | --- |
| 项目环境 bootstrap | 锁定依赖、editable 安装和 pip check 成功 |
| 格式 / lint / 严格类型 | Ruff format、Ruff check、Mypy strict 全部通过 |
| 仓库规则 | 本地文档链接与 CLI 声明/AST 解析通过 |
| 全部 unittest | 20 项通过：原有 11 项行为测试，新增 9 项仓库检查测试 |
| 规则负例 | 删除导航文件、断链、越出仓库、缺失声明/模块/函数、畸形 TOML/Python 均被拒绝；命令失败后修复可恢复成功 |
| wheel 构建与安装 | 构建普通 wheel，在项目内全新 venv 仅安装本次 wheel；未复用 editable 环境 |
| 真正安装的 CLI | 从独立临时工作目录执行，版本/帮助/demo 退出 0；导入文件位于临时 site-packages，未导入 src |
| SQLite 与重启 | 外部读取 3 条完整 fixture、WAL 与完整性；第二次 CLI 不重复写入，第三个只读进程读回一致 |
| JSON | 实际内容与已知 fixture 一致，重启运行逐字节相同 |
| 安装后失败边界 | 未知命令退出 2；已有文件目标、数据库冲突退出 1；既有文件/行值/上次 JSON 保持原样 |
| 资源清理 | 安装验收创建的临时环境与工作目录已清理 |

完整 check 已包含 wheel 验收；运行命令见 [开发指南](development.md)，方法与解析范围见 [测试说明](testing.md)。

## 可检查的交付证据

- `dist/mini_sla_harness-0.0.1-py3-none-any.whl`：最后一次成功验收构建的 wheel。
- `artifacts/package-check/summary.json`：wheel SHA-256、真实导入位置、工作目录、实际数据库行值、错误退出和清理结果；同目录含逐命令日志与正常 `demo-result.json`。
- `artifacts/verification/summary.json`：最终 HEAD、分支、各入口退出码、实际测试数量、制品证据与工作区状态。
- `artifacts/verification/check.log`、`bootstrap.log`、`demo.log`：最终提交上的完整运行日志。

这些是本地生成物，不进入 Git。临时环境路径保留在证据中用于审计，验收结束后路径本身已不存在。

## 验证边界

本轮使用确定性 fake、真实 SQLite 与实际安装制品，没有真实模型调用或研究效果测量。当前结果证明开发与安装链路，协议范围由 [设计范围](scope.md) 负责。其他操作系统尚未实机验证，链接检查不验证外部站点与标题锚点。

初始化和迁移历史保留在 `5de972d` 及其父提交；本轮在其基础上创建独立分支。原目录仍保留迁移备份，后续入口使用 E 盘仓库。
