# 设计范围

## 当前边界

当前交付是可安装的 Python CLI、固定 fake provider 与 SQLite smoke 流程，以及开发环境和验证工具。固定响应没有模型调用、候选优化或性能评分；`research_effect: not_evaluated` 表示未评估研究效果。当前运行行为见 [架构](architecture.md)。

## 后续设计

TaskSpec、权威 StateStore、不可变候选快照、独立可信评估、预算预留与 UNKNOWN 对账、controller/attempt fencing、强停竞态、暂停/恢复、Advisor 规划、Workers 并发、最终审计与消融实验仍待实现。当前 demo 表不是正式 StateStore schema。

下一步先补齐 M0 的契约与协议测试；真实 API 接入另行安排。本轮离线基础设施通过不表示 M0 Gate 通过。未来 Linux 进程隔离、可信计时和并发验收须另行实施。

## 设计文档

需求、规划架构、状态事务和实施验收见 [设计索引](design/README.md)；探索构想独立保存，不构成正式契约。
