---
name: mini-sla
description: "开发、修复、审查或调整 mini-SLA-harness 仓库时使用。按任务选择短原则、项目契约和真实验证入口，完成可审查的改动。"
---

# Mini-SLA 项目开发

先读 [AGENTS.md](../../../AGENTS.md) 与 [README](../../../README.md)，确认本次任务范围、当前代码和用户已有修改。路径相对本技能文件；执行命令时使用所在仓库的根目录。

## 原则

每次任务读 [尽早暴露错误](../mini-sla-fail-early/SKILL.md) 和 [取得真实反馈](../mini-sla-real-feedback/SKILL.md)。其余按触发条件读取：

| 遇到什么情况 | 使用哪条原则 |
| --- | --- |
| 修复错误、同一问题反复出现 | [修复根因](../mini-sla-fix-root-causes/SKILL.md) |
| 新增或修改测试 | [验证行为](../mini-sla-test-behavior/SKILL.md) |
| 新能力、重构或多步改动 | [小步验证](../mini-sla-small-steps/SKILL.md) |
| 重复纠正、维护仓库约束 | [把规则变成检查](../mini-sla-encode-invariants/SKILL.md) |

## 推进任务

先确定用户会观察到的完成条件，以及最值得先验证的一项假设。按 [开发指南的任务分类](../../../docs/development.md) 取得最小反馈，再扩展实现。

- 修改运行行为时，对照 [当前架构](../../../docs/architecture.md) 和实际入口；涉及状态、计量、隔离或恢复时，从 [设计索引](../../../docs/design/README.md) 定位契约和验收用例。
- 外部集成和性能工作先按 [早期探索与测量校准](../../../docs/design/04-implementation-validation.md) 运行对应探针，依据结果决定后续实现。
- 审查或调研任务先给出可定位的问题、证据和修正建议；用户要求实施时再修改代码。
- 已授权的实施持续推进到实现、验证和交付。碰到阻碍时完成不依赖它的工作，并说明缺失的具体条件。

修改完成后，按 [开发指南](../../../docs/development.md) 执行完整验证，读取 [本次证据](../../../docs/testing.md)。检查当前 diff、受影响调用方和失败路径；交付行为变化、实际结果及剩余问题。

技能迭代方法见 [项目技能包维护](../../../docs/development.md#项目技能包)。
