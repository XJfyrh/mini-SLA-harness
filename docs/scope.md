# 设计范围

## 当前边界

当前交付包含可安装的 Python CLI、原有 SQLite smoke 流程，以及 M0 离线协议内核：JSON TaskSpec、候选 CAS、权威 StateStore、命令幂等与事务、Run/Trial/Advisor scope、逐调用预留/UNKNOWN、controller/attempt fencing、强停线性化、基线与规划状态。`m0-check` 驱动固定 Agent/Evaluator/provider，生成逐场景 JSON 和可回读数据库；入口见 [测试](testing.md#m0-离线协议验收)。当前运行行为见 [架构](architecture.md)。

M0 使用假分数与模拟 token 用量，外部模型请求为零；`research_effect: not_evaluated` 表示未评估研究效果。跨进程排他、进程死亡后的事务结果和受控假进程终止已有行为测试；容器隔离、Windows 控制管道和断电持久性分别保留为待验收。

## 后续设计

首版平台采用 Windows 宿主 + Docker Desktop/WSL2 Linux 容器：宿主负责 CLI、控制器、SQLite、权威候选快照和可信评估 supervisor，容器执行工具与候选。具体边界由 [总体架构](design/02-architecture.md#1-架构决策与运行边界) 负责；原生 Windows 候选执行和其他宿主部署不在首版内。

M1 的真实编辑—评估链路、ContextBuilder、模型适配器与目标执行器，M2 的完整生命周期/崩溃矩阵，M3 的真实 Advisor 与 Worker 调度并发，以及 M4 的审计与消融实验仍待实现。M0 的状态测试不替代这些运行时能力；原有 demo 表仍不属于 StateStore schema。

下一步取得 Docker Desktop/WSL2 执行边界、provider 契约和最小编辑—评估链路的真实反馈。探索按 [实施与验收](design/04-implementation-validation.md) 的前置条件推进；持续自主运行逐阶段满足对应 Gate。Windows x64 的默认 M0 验收使用 [固定仓库运行时](development.md#尽早检查环境)，开发工具仍使用 `.venv`；实际结果记录在 [验证记录](verification.md)，不把单个解释器通过扩展为整机已升级。

## 设计文档

需求、规划架构、状态事务和实施验收见 [设计索引](design/README.md)；探索构想独立保存，不构成正式契约。
