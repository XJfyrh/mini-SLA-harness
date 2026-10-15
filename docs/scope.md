# 当前范围与下一步

## 本次交付

Python 3.14 项目内虚拟环境、带锁定版本和 SHA-256 的开发依赖、可安装的 CLI、
格式与静态类型检查、标准库离线测试，以及 fake provider → SQLite → JSON 的 smoke demo。
这条链路验证包安装、命令入口和本地持久化连通性。

## 后续实施

以下仍为设计目标：TaskSpec、权威 StateStore、不可变候选快照、独立可信评估、
预算预留与 UNKNOWN 对账、controller/attempt fencing、强停竞态、暂停/恢复、
Advisor 规划、Workers 并发、最终审计与消融实验。当前 demo 表不是 StateStore 的正式 schema。

先补齐设计 M0 的契约与协议测试，再考虑真实 API。当前没有 API 适配器、密钥配置、
模型调用或性能分数；固定 fake 响应不代表研究效果，也不说明 M0 Gate 已通过。
未来 Linux 运行时的进程隔离、计时与并发验收须另行实施。

## 已读取的参考

2026-10-15 读取以下 v0.2 Page 正文；使用的是正文，未读取旧版附件或原始会话：

- [设计总览](https://chatgpt.com/space/page_4df769bdb30c8191aa5ecd611fdd1870)：版本 0.2，2026-10-11；当前为修订设计稿。
- [实施与验收设计](https://chatgpt.com/space/page_02ab1ff0cbe08191832190d785c66f5c)：版本 0.2，2026-10-11；M0～M4 为待实现 Gate。

## 模块定位

| 位置 | 当前职责 |
| --- | --- |
| `src/mini_sla_harness/cli.py` | 参数与人可读/JSON 输出 |
| `src/mini_sla_harness/fake.py` | 固定请求/响应 fixtures |
| `src/mini_sla_harness/store.py` | demo 专用 SQLite WAL 写入与回读 |
| `src/mini_sla_harness/demo.py` | 串联 smoke 流程并写 `result.json` |
| `tests/` | 离线持久化、确定性、CLI 与错误路径验证 |
| `scripts/dev.py` | 跨平台 bootstrap/check/demo，自动选择 `.venv` 解释器 |

每增加一项协议功能，再引入对应接口、schema 和设计链接；不提前搭建空模块。
