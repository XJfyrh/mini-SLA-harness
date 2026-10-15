# mini-sla-harness

Mini-SLA 的初始 Python CLI 开发仓库，当前交付开发环境及离线 smoke demo。
完整 Harness 尚未实现，设计 M0 的协议验收也尚未完成。

使用 Python 3.14；项目虚拟环境位于 `.venv`。开发入口无需激活环境或修改 PowerShell 执行策略。
在项目根目录运行：

```powershell
python scripts/dev.py bootstrap
python scripts/dev.py check
python scripts/dev.py demo
```

安装从 PyPI 获取锁定的开发工具；运行时使用 Python 标准库。`check` 与 `demo` 离线运行。

`bootstrap` 创建或复用 `.venv`，按 `requirements-dev.lock` 的版本与 SHA-256 安装工具，
再以 editable 模式安装本包。所有临时文件写入 `artifacts/tmp`。
`check` 依次执行 Ruff 格式检查、Ruff lint、Mypy strict、`unittest` 离线测试及 `pip check`。
命令失败返回非零退出码。

## 直接使用 CLI

```powershell
.\.venv\Scripts\mini-sla.exe --help
.\.venv\Scripts\mini-sla.exe --version
.\.venv\Scripts\mini-sla.exe demo
.\.venv\Scripts\mini-sla.exe demo --output-dir artifacts/another-demo --json
```

macOS/Linux 可用同一 `python scripts/dev.py ...` 入口；直接调用解释器时使用
`.venv/bin/python -m mini_sla_harness`。本次实际验收平台为 Windows、Python 3.14；
其他平台尚未实机验证。若系统命令叫 `python3`，将入口命令中的 `python` 换成 `python3`。

## Demo 输出

demo 固定处理三个 fixture，写 SQLite WAL 并通过新连接回读，输出摘要和两项产物：

- `artifacts/demo/demo.sqlite3`：demo 专用数据表。
- `artifacts/demo/result.json`：稳定 JSON，含 `status`、`case_count`、`records`、`sqlite_round_trip`。

重复运行产生相同 JSON，不累积相同记录。已有同名记录内容冲突时退出失败并回滚本批写入；
fixture 变化时请指定新的输出目录。JSON 文件是可重建的 demo 产物，重复运行会重写该文件。
`--json` 使 stdout 只包含 JSON。运行产物、虚拟环境与缓存均不入 Git。

固定响应没有模型调用、候选优化或性能评分；`research_effect: not_evaluated` 标明尚未评估研究效果。
未实现功能、设计来源和模块定位见 [范围说明](docs/scope.md)。

## 继续开发

- 新行为放入 `src/mini_sla_harness/`，有意义的离线测试放入 `tests/`。
- 格式修复：`.\.venv\Scripts\python.exe -m ruff format .`。
- 当前依赖只用于构建与开发；运行时不需要第三方包。依赖维护步骤见 [开发环境](docs/development.md)。
- 修改后运行 `check` 和 `demo`。交付验收记录见 [实际验证](docs/verification.md)。
