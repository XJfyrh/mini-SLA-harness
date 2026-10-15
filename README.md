# mini-sla-harness

Mini-SLA 的初始 Python CLI 开发仓库，当前交付开发环境及离线 smoke demo。
完整 Harness 尚未实现，设计 M0 的协议验收也尚未完成。

使用 Python 3.14；项目虚拟环境位于 `.venv`。开发入口无需激活环境或修改 PowerShell 执行策略。

```powershell
python scripts/dev.py bootstrap
python scripts/dev.py check
python scripts/dev.py demo
```

安装从 PyPI 获取锁定的开发工具；运行时使用 Python 标准库。`check` 与 `demo` 离线运行。
