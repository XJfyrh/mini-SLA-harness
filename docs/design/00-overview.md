# mini SLA harness 设计文档

> 来源：[mini SLA harness 设计文档](https://chatgpt.com/space/page_4df769bdb30c8191aa5ecd611fdd1870) · 导入：2026-10-15 06:05:42 UTC
> 以下正文描述设计目标，当前实现见[当前架构](../architecture.md)。快照与维护约定见[本地索引](README.md)。

<!-- pages-snapshot-body:start -->
版本 0.2 · 2026年10月11日

将原始会话细化为可实施、可评审的 mini-SLA-harness 设计。这里的 SLA 指 Stateless Language Agents（无状态语言智能体）。

> [!CALLOUT]
>
> **当前状态：修订设计稿，尚未开工**
>
> 目标保留无状态 Advisor、并行 Worker、局部探索和公平消融。已将可信计时、强停竞态、基线／规划恢复、分层预算和最终审计纳入正式协议与验收用例；不代表代码已实现或技术栈与效果已验证。

## 文档导航

建议按 01 → 02 → 03 → 04 阅读；四份文档均已转换为可编辑的 Page 正文。

| 顺序 | 设计文档 | 主要内容 |
| --- | --- | --- |
| 01 | [产品需求设计](01-requirements.md) | 目标用户、首版范围、任务契约、功能需求与成功标准 |
| 02 | [总体架构与接口设计](02-architecture.md) | 组件边界、运行流程、角色上下文、CLI 与内部命令接口 |
| 03 | [状态存储与事务协议](03-state-transactions.md) | 数据模型、状态机、幂等、预算账本、事务与崩溃恢复 |
| 04 | [实施与验收设计](04-implementation-validation.md) | 开发阶段、验收用例、故障注入、消融实验与交付标准 |

[Mini-SLA 想法与探索](exploration.md)：单独收录设计启发、备选方向与待验证的小实验；已记录 AgentMemoryRepo 带来的记忆层想法（2026年10月12日）。项目尚未开工，这些想法不修改 v0.2 契约或当前 M0 范围。

## 项目目标

通过无状态 Advisor 与 Worker 会话持续优化一个可机器验证的程序，让候选代码、评估结果、分支进展、预算用量和恢复状态都可追溯。首个贯通案例为 Python JSONL 聚合程序的吞吐量优化。

## 首版范围

- Linux 单机、CLI、Python asyncio 与本地 SQLite WAL，由一个控制器写入权威状态。

- 1 个 Advisor，最多 3 个 Worker 槽位，每个 Assignment 最多 3 个逻辑 Trial。

- 不可变候选快照、独立评估、分支 Head 与 Global Best、模型调用预算账本。

- 支持暂停、恢复、停止、崩溃对账与过期执行权隔离。

- 先 fake 验证预算门控、fencing 与事务，再接真实单 Worker、完整恢复、Advisor 与并发；阶段缩小不改变完整 Mini-SLA 目标。

## 历史版本下载

[Mini\_SLA\_设计文档包\_v0.1.zip](library-file:fde1_bGliZmlsZV9YSlBJMEk4cmRfUzdWbjhRMVc0SWJn_FileDrive_573a227bacd88191b1e2ee06cc519444)

以下 ZIP、Word 文档及 Mermaid 图源为 v0.1 历史附件。本次修订以以上四个可编辑 Page 的 v0.2 正文为准，旧附件未同步更新。

- [Mini\_SLA\_01\_产品需求设计.docx](library-file:fde1_bGliZmlsZV9Db3NrOFd6NXNvLWl3c1MtUEV5UENB_FileDrive_573a227bacd88191b1e2ee06cc519444)

- [Mini\_SLA\_02\_总体架构与接口设计.docx](library-file:fde1_bGliZmlsZV8zSTM1ZGtad2p6d2F2RWktZGtHM0hn_FileDrive_573a227bacd88191b1e2ee06cc519444)

- [Mini\_SLA\_03\_状态存储与事务协议.docx](library-file:fde1_bGliZmlsZV9zNjlzSkxhWU05a1IwRWhnVVA0WFJn_FileDrive_573a227bacd88191b1e2ee06cc519444)

- [Mini\_SLA\_04\_实施计划与验收设计.docx](library-file:fde1_bGliZmlsZV9rS3ZpUGxwYkpiX1dvc1J4WVhrd3VR_FileDrive_573a227bacd88191b1e2ee06cc519444)

## 原始来源

[原始会话讨论](https://chatgpt.com/share/6ac9ad68-27d4-83ec-a674-df6e7b748739) · [原论文](https://arxiv.org/abs/2610.07625) · [论文全文](https://arxiv.org/html/2610.07625v1)
<!-- pages-snapshot-body:end -->
