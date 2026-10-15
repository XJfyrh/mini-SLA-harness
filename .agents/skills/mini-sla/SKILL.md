---
name: mini-sla
description: "开发、修复、审查或调整 mini-SLA-harness 仓库时使用。按目标设计、模型边界、实现迁移、诊断验证、协作维护分类路由到短原则和项目契约。"
---

# Mini-SLA 项目开发

先读 [AGENTS.md](../../../AGENTS.md) 与 [README](../../../README.md)，确认本次任务范围、当前代码和用户已有修改。路径相对本技能文件；执行命令时使用所在仓库的根目录。

## 分类路由

每次任务读 [尽早暴露错误](../mini-sla-fail-early/SKILL.md) 和 [取得真实反馈](../mini-sla-real-feedback/SKILL.md)。再按当前要做的决策选择下面的分类，在分类表中只读取命中触发条件的原则。

| 当前要做什么 | 从哪里选择原则 |
| --- | --- |
| 判断完成条件、功能取舍或备选方案 | [目标与方案](references/goals-and-design.md) |
| 设计状态、接口、输入校验、恢复或并发 | [模型与边界](references/models-and-boundaries.md) |
| 新增能力、重构、迁移或批量修改 | [实现与迁移](references/implementation-and-migration.md) |
| 定位失败、修改测试或判断性能与评估结果 | [诊断与验证](references/diagnosis-and-verification.md) |
| 等待用户、控制上下文、降低阅读成本或沉淀经验 | [协作与维护](references/collaboration-and-maintenance.md) |

任务可以跨类。先处理会阻断后续的判断，出现新的失败或设计问题时重新路由；不因为进入一类就加载该类全部原则。用户点名某条原则时直接读取它。交付时说明原则实际改变的决策和证据，不逐条汇报已读名称。

## 推进任务

先确定用户会观察到的完成条件，以及最值得先验证的一项假设。按 [开发指南的任务分类](../../../docs/development.md) 取得最小反馈，再扩展实现。

- 修改运行行为时，对照 [当前架构](../../../docs/architecture.md) 和实际入口；涉及状态、计量、隔离或恢复时，从 [设计索引](../../../docs/design/README.md) 定位契约和验收用例。
- 外部集成和性能工作先按 [早期探索与测量校准](../../../docs/design/04-implementation-validation.md) 运行对应探针，依据结果决定后续实现。
- 审查或调研任务先给出可定位的问题、证据和修正建议；用户要求实施时再修改代码。
- 已授权的实施持续推进到实现、验证和交付。碰到阻碍时完成不依赖它的工作，并说明缺失的具体条件。

修改完成后，按 [开发指南](../../../docs/development.md) 执行完整验证，读取 [本次证据](../../../docs/testing.md)。检查当前 diff、受影响调用方和失败路径；交付行为变化、实际结果及剩余问题。

技能迭代方法见 [项目技能包维护](../../../docs/development.md#项目技能包)；追溯上游或调整分类时读 [pstack 吸收映射](references/pstack-map.md)。
