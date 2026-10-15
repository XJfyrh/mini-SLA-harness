# 开发环境与依赖

## 安装约定

Python 支持范围当前锁在 3.14；本机实际版本为 3.14.7，SQLite 为 Python 自带的 3.50.4。
`scripts/dev.py` 根据操作系统选择 `.venv/Scripts/python.exe` 或 `.venv/bin/python`，
以项目根目录为工作目录，因此可从其他目录通过脚本完整路径调用。
无需激活脚本、系统包安装或 PowerShell 执行策略调整。

依赖分为三个文件：

| 文件 | 用途 |
| --- | --- |
| `pyproject.toml` | 包元数据、固定构建后端、CLI、Ruff/Mypy 设置；运行时依赖为空 |
| `requirements-dev.in` | 希望维护的直接开发工具列表，用于有意更新依赖 |
| `requirements-dev.lock` | 已解析的全部直接/传递依赖和 pip，精确版本与发行文件 SHA-256 |

`bootstrap` 使用官方 PyPI、wheel、`--require-hashes --no-deps` 安装锁定工具，
再使用 `--no-index --no-build-isolation --no-deps -e .` 安装本包，最后执行 `pip check`。
这些参数使 editable 构建使用环境中已锁定的 setuptools/wheel。
依赖版本及哈希锁定方法见 [pip 官方重复安装说明](https://pip.pypa.io/en/stable/topics/repeatable-installs/)。
虚拟环境行为见 [Python venv 文档](https://docs.python.org/3.14/library/venv.html)。

锁文件包含各发行版的多平台哈希，安装时只选当前平台的 wheel。没有匹配 wheel 时安装会失败；
本次实机验证的是 Windows x64。仓库不携带完整离线安装包，首次 bootstrap 需要能访问 PyPI。

## 依赖更新

维护依赖时，在单独的项目内临时虚拟环境中按 `requirements-dev.in` 解析需要更新的工具，
导出全部依赖的精确版本（包括 pip）；不要直接覆盖用户环境的系统包。
从官方 `https://pypi.org/pypi/<name>/<version>/json` 的 `urls[].digests.sha256` 获取发行文件哈希，
更新 `requirements-dev.lock`，同步 `pyproject.toml` 中的构建后端版本。
包名遵循 PyPI 规范，`typing_extensions` 的发行 API 路径也可使用下划线形式。
重新 bootstrap、check、demo 并提交锁文件；不要在普通 check 中升级或联网解析依赖。

## 验证与产物

`check` 的离线测试使用 `unittest`，覆盖 fixture、SQLite WAL 与新连接回读、重复运行、
冲突回滚、缺失库只读失败、独立 CLI 进程、JSON 输出和错误退出。
测试中的 fake/demo 路径禁止 socket 创建，验证其运行不依赖网络。

demo 路径由 `--output-dir` 决定，默认 `artifacts/demo`。数据只写入 demo 专用表，
不自动清空现有数据库；遇到记录冲突可换新输出目录。`result.json` 不包含时间或机器路径，
便于重复运行逐字节对比。demo 没有正式状态机、schema 迁移或恢复承诺。

`artifacts/`、`.venv/`、缓存和包构建产物均被 Git 忽略。入口把 TEMP/TMP/TMPDIR 指向
`artifacts/tmp`，兼容本次执行沙箱对系统临时目录的写入限制。这只改变本次进程及其子进程的环境变量。

## 排错

- 缺少环境：运行 `python scripts/dev.py bootstrap`。
- `.venv` 已存在但没有解释器：脚本会停止。检查目录内容后再重建，脚本不会自动清空它。
- 下载失败：检查 PyPI 网络访问后重试 bootstrap；不修改证书校验或系统安全设置。
- demo 数据冲突：使用新的 `--output-dir`，保留原数据库用于检查。
- 若移动项目：在新位置重建 `.venv`；虚拟环境内的脚本包含安装位置。
