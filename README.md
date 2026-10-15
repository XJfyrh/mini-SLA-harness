# mini-sla-harness

Mini-SLA Harness 探索如何让无状态 Agent 围绕可验证任务持续改进程序。当前提供 M0 离线协议内核：任务校验、不可变候选、SQLite 权威状态、预算账本与执行代次，以及可重复的 fake 验收。

完整优化循环尚未实现。首版目标为 Windows 宿主 + Docker Desktop/WSL2 Linux 容器，职责与实现进度见 [设计范围](docs/scope.md)；以下离线流程无需 Docker、模型账号或付费额度。

## 先跑一个 Demo

需要 Python 3.14。Windows x64 的 bootstrap 同时准备固定 Python 3.14.8／SQLite 3.54.0 运行时，详见 [环境准备](docs/development.md#尽早检查环境)。本地仓库位于 `E:\dev\mini-SLA-harness`，无需手动激活虚拟环境：

```powershell
Set-Location -LiteralPath 'E:\dev\mini-SLA-harness'
python scripts/dev.py bootstrap
python scripts/dev.py demo
```

首次安装从官方 PyPI 获取锁定工具，demo 使用固定响应，无需模型账号。成功后会看到 `Offline smoke demo: ok (3 cases)`，得到可检查的 SQLite 数据库和 JSON 结果：

- `artifacts/demo/demo.sqlite3`
- `artifacts/demo/result.json`

## 验收 M0

```powershell
python scripts/dev.py m0-check
python scripts/dev.py check
```

Windows 上第一条使用固定运行时，先检查文件完整性、目标宿主基础条件和协议测试，再执行 10 组离线场景；最后汇总必须为 `m0: passed`。缺失或漂移的固定运行时会失败，已有开发环境可先运行 `python scripts/dev.py runtime-bootstrap`。`acceptance/report.json` 给出逐场景结果、观测值和 SQLite 路径。第二条验证代码、测试和干净 wheel 安装。详细断言与查看方法见 [M0 验收](docs/testing.md#m0-离线协议验收)。

任务契约使用 JSON，可单独校验公开示例：

```powershell
.\.venv\Scripts\mini-sla.exe task validate tasks/jsonl/task.json
```

fake 分数和 token 用量验证协议；真实模型效果、容器隔离和性能测量按后续阶段验收。

## 接下来

| 想了解什么 | 从这里开始 |
| --- | --- |
| 数据怎样流动、代码各自负责什么 | [当前架构](docs/architecture.md) |
| 参与开发、运行完整验证或排查环境 | [开发指南](docs/development.md) |
| 使用作战手册与短原则指导 agent | [作战手册](.agents/skills/playbook/SKILL.md) |
| 验证方法与实际运行结果 | [测试说明](docs/testing.md)、[验证记录](docs/verification.md) |
| 阅读需求、规划架构与实施设计 | [设计文档](docs/design/README.md) |
| 确认当前边界与后续范围 | [设计范围](docs/scope.md) |
