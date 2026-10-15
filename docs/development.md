# 开发指南

面向参与开发的人和 agent。首次体验看 [README](../README.md)，实现边界看 [架构](architecture.md)，验证方法看 [测试说明](testing.md)。

## 日常开发

在仓库根目录执行；修改后运行完整 check 和 demo：

```powershell
python scripts/dev.py bootstrap
python scripts/dev.py check
python scripts/dev.py demo
```

check 包含格式、lint、严格类型、仓库规则、全部 unittest、依赖一致性和 wheel 安装验收，任何一步失败都会返回非零退出码。单独重跑制品验收：

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
