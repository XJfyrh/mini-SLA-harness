# mini-sla-harness

Mini-SLA Harness 探索如何让无状态 Agent 围绕可验证任务持续改进程序。当前版本提供一个可重复运行的本地开发起点：Python CLI、确定性 fake provider、SQLite 持久化和离线 smoke demo。

项目处于初始骨架阶段，完整优化循环尚未实现。首版目标为 Windows 宿主 + Docker Desktop/WSL2 Linux 容器，职责与实现进度见 [设计范围](docs/scope.md)；以下离线 demo 无需 Docker。

## 先跑一个 Demo

需要 Python 3.14。Windows 本地仓库位于 `E:\dev\mini-SLA-harness`，无需手动激活虚拟环境：

```powershell
Set-Location -LiteralPath 'E:\dev\mini-SLA-harness'
python scripts/dev.py bootstrap
python scripts/dev.py demo
```

首次安装从官方 PyPI 获取锁定工具，demo 使用固定响应，无需模型账号。成功后会看到 `Offline smoke demo: ok (3 cases)`，得到可检查的 SQLite 数据库和 JSON 结果：

- `artifacts/demo/demo.sqlite3`
- `artifacts/demo/result.json`

## 接下来

| 想了解什么 | 从这里开始 |
| --- | --- |
| 数据怎样流动、代码各自负责什么 | [当前架构](docs/architecture.md) |
| 参与开发、运行完整验证或排查环境 | [开发指南](docs/development.md) |
| 使用作战手册与短原则指导 agent | [作战手册](.agents/skills/playbook/SKILL.md) |
| 验证方法与实际运行结果 | [测试说明](docs/testing.md)、[验证记录](docs/verification.md) |
| 阅读需求、规划架构与实施设计 | [设计文档](docs/design/README.md) |
| 确认当前边界与后续范围 | [设计范围](docs/scope.md) |
