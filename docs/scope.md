# 设计范围

## 当前边界

当前交付是可安装的 Python CLI、固定 fake provider 与 SQLite smoke 流程，以及开发环境和验证工具。固定响应没有模型调用、候选优化或性能评分；`research_effect: not_evaluated` 表示未评估研究效果。当前运行行为见 [架构](architecture.md)。

## 后续设计

TaskSpec、权威 StateStore、不可变候选快照、独立可信评估、预算预留与 UNKNOWN 对账、controller/attempt fencing、强停竞态、暂停/恢复、Advisor 规划、Workers 并发、最终审计与消融实验仍待实现。当前 demo 表不是正式 StateStore schema。

下一步同时取得目标环境、provider 契约和最小编辑—评估链路的真实反馈，并实现 M0 协议测试。探索按 [实施与验收](design/04-implementation-validation.md) 的前置条件推进；持续自主运行逐阶段满足对应 Gate。Linux 隔离、可信计时、并发和模型效果分别需要实际验收记录。

## 设计文档

需求、规划架构、状态事务和实施验收见 [设计索引](design/README.md)；探索构想独立保存，不构成正式契约。
