# 开发指南

面向参与开发的人和 agent。首次体验看 [README](../README.md)，实现边界看 [架构](architecture.md)，验证方法看 [测试说明](testing.md)。

## 日常开发

首次或锁定依赖变化后执行 `python scripts/dev.py bootstrap`。在仓库根目录修改代码后运行：

```powershell
python scripts/dev.py check
python scripts/dev.py demo
```

check 先观察开发环境，再执行格式、lint、严格类型、仓库规则、全部 unittest、依赖一致性和 wheel 安装验收。独立检查全部执行并汇总失败，任一失败返回非零退出码；wheel 构建失败则停止依赖它的安装和运行。每次运行打印独立证据目录，格式见 [测试说明](testing.md)。单独重跑制品验收：

```powershell
python scripts/dev.py package-check
```

成功 wheel 留在 `dist/`；验收内容和证据格式由测试说明负责。Windows 直接使用 CLI 可运行：

```powershell
.\.venv\Scripts\mini-sla.exe --help
.\.venv\Scripts\mini-sla.exe --version
.\.venv\Scripts\mini-sla.exe demo --output-dir artifacts/another-demo --json
```

`--json` 使 stdout 只包含 JSON。macOS/Linux 使用同一开发入口，直接 CLI 路径为 `.venv/bin/mini-sla`；若系统命令叫 `python3`，替换入口中的 `python`。实际测试平台见验证记录。

## 按任务建立反馈

| 任务 | 最早要取得的证据 | 完成条件 |
| --- | --- | --- |
| 修复错误 | 用真实入口、输入与副作用复现失败 | 原复现通过，相关负例仍失败，完整 check 和 demo 通过 |
| 新增行为 | 写明可观察的输入、输出、失败行为；先跑最小纵向路径 | 行为测试检查结果和持久化内容，安装后的入口行为一致 |
| 协议修改 | 对应 T 编号、受影响的不变量与故障触发点 | 实际注入故障并检查状态、产物和计量；更新负责该契约的正文 |
| 外部集成或环境假设 | 最小真实探针，记录版本、响应、错误与耗时 | 探针结果支持继续实现，或据失败结果修订方案 |

先执行与问题直接相关的检查，在局部闭环后运行完整验证。遇到重复失败时，检查原始输出与前提是否成立；不要靠扩大 mock、吞掉异常、自动 skip 或放宽断言消除失败。新增检查也应通过实际破坏规则来证明能发现问题。

真实模型探索的调用范围、额度和停止条件见 [实施与验收](design/04-implementation-validation.md)。已有授权覆盖的可逆工作直接推进；需要新授权的调用先准备可审查的探针与配置。

交付说明写明改动、实际执行的命令、证据路径和剩余失败。未运行的检查标为未运行；设计预期写在验收条件中。验证期间源码变化会使本次结果失败，需在稳定工作区重跑。

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
