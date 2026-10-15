# mini SLA harness 设计文档

本文定义可实施、可评审的 Mini-SLA Harness 目标设计。这里的 SLA 指 Stateless Language Agents（无状态语言智能体）。

## 文档导航

建议按 01 → 02 → 03 → 04 阅读；当前实现状态见 [当前架构](../architecture.md)。

| 顺序 | 设计文档 | 主要内容 |
| --- | --- | --- |
| 01 | [产品需求设计](01-requirements.md) | 目标用户、首版范围、任务契约、功能需求与成功标准 |
| 02 | [总体架构与接口设计](02-architecture.md) | 组件边界、运行流程、角色上下文、CLI 与内部命令接口 |
| 03 | [状态存储与事务协议](03-state-transactions.md) | 数据模型、状态机、幂等、预算账本、事务与崩溃恢复 |
| 04 | [实施与验收设计](04-implementation-validation.md) | 开发阶段、验收用例、故障注入、消融实验与交付标准 |

[Mini-SLA 想法与探索](exploration.md) 单独收录备选方向与待验证的小实验，不修改正式契约或当前 M0 范围。

## 项目目标

通过无状态 Advisor 与 Worker 会话持续优化一个可机器验证的程序，让候选代码、评估结果、分支进展、预算用量和恢复状态都可追溯。首个贯通案例为 Python JSONL 聚合程序的吞吐量优化。

## 首版范围

- Linux 单机、CLI、Python asyncio 与本地 SQLite WAL，由一个控制器写入权威状态。

- 1 个 Advisor，最多 3 个 Worker 槽位，每个 Assignment 最多 3 个逻辑 Trial。

- 不可变候选快照、独立评估、分支 Head 与 Global Best、模型调用预算账本。

- 支持暂停、恢复、停止、崩溃对账与过期执行权隔离。

- 尽早执行环境、provider 和计量探针；用 fake 验证预算门控、fencing 与事务，逐步交付真实单 Worker、恢复、Advisor 与并发，阶段条件见实施与验收设计。

## 研究参考

[Stateless Language Agents 论文](https://arxiv.org/abs/2610.07625) · [论文全文](https://arxiv.org/html/2610.07625v1)
