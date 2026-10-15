# 工作入口

- 先读 [README.md](README.md)，按需阅读 `docs/`。当前是开发骨架，完整 Harness 与 M0 协议待实现。
- 环境：`python scripts/dev.py bootstrap`；验证：`python scripts/dev.py check`；演示：`python scripts/dev.py demo`。
- 代码位于 `src/mini_sla_harness/`，离线测试位于 `tests/`，开发入口位于 `scripts/dev.py`。
- 保持标准库优先；开发依赖锁在 `requirements-dev.lock`，运行产物写入忽略的 `artifacts/`。
- 保持 demo 确定性；不读凭据，不接真实 API，不把 fake 输出当作研究效果。
- 修改后运行 check 和 demo；新行为用有意义的离线测试验证。
- 使用独立分支、阶段提交，提交消息用简体中文 Conventional Commits。无远端操作授权时只提交本地。
