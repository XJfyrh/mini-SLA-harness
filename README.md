# mini-sla-harness

Mini-SLA 的 Python CLI 开发骨架。Windows 项目位置：`E:\dev\mini-SLA-harness`。

## 开始使用

需要 Python 3.14。以下入口自动使用项目 `.venv`，无需激活脚本或修改 PowerShell 执行策略。

```powershell
Set-Location -LiteralPath 'E:\dev\mini-SLA-harness'
python scripts/dev.py bootstrap
python scripts/dev.py check
python scripts/dev.py demo
```

首次安装从官方 PyPI 获取锁定工具；check 和 demo 离线运行。任何检查失败均返回非零退出码。

## 使用 CLI

```powershell
.\.venv\Scripts\mini-sla.exe --help
.\.venv\Scripts\mini-sla.exe --version
.\.venv\Scripts\mini-sla.exe demo --output-dir artifacts/another-demo --json
```

demo 输出人可读摘要，生成 `artifacts/demo/demo.sqlite3` 和 `artifacts/demo/result.json`。`--json` 使 stdout 只包含 JSON。

macOS/Linux 使用相同的开发入口；直接调用 CLI 使用 `.venv/bin/mini-sla`。若系统命令叫 `python3`，将入口中的 `python` 换成 `python3`。实际验证平台见验证记录。

## 按需阅读

| 要做的事 | 唯一详细说明 |
| --- | --- |
| 修改代码、理解数据流与模块边界 | [当前架构](docs/architecture.md) |
| 维护环境、依赖或排查安装问题 | [开发环境](docs/development.md) |
| 修改测试或了解检查边界 | [测试说明](docs/testing.md) |
| 查看设计目标与未实现范围 | [设计范围](docs/scope.md) |
| 查看实际验证结果 | [验证记录](docs/verification.md) |
| 开始一次 agent 开发任务 | [常驻规则](AGENTS.md) |
