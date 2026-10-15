# pstack 吸收映射

维护原则或追溯来源时使用本表。来源固定到 pstack 提交 `e5136d82418d2db3165ea1050d17577cd618cc05` 的 [24 条原则索引](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/docs/guide/08-principles.md)。本项目按触发条件合并相近规则，正文使用项目的语言、契约和验证入口。

“尽早暴露错误”和“取得真实反馈”由用户明确提出，作为常驻原则；后者也吸收 Prove It Works。其余原则由五类路由按需选择。

| pstack 原则 | 项目原则 | 吸收与调整 |
| --- | --- | --- |
| [Laziness Protocol](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-laziness-protocol/SKILL.md) | [先减后加](../../mini-sla-subtract-first/SKILL.md) | 把最小改动与删除重复决策合并。 |
| [Foundational Thinking](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-foundational-thinking/SKILL.md) | [用模型表达规则](../../mini-sla-model-domain/SKILL.md) | 先确定身份、状态、所有权和访问路径；基础能力按当前依赖建设。 |
| [Redesign from First Principles](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-redesign-from-first-principles/SKILL.md) | [比较方案再定设计](../../mini-sla-compare-designs/SKILL.md) | 用新需求检验旧假设，确定最小迁移范围。 |
| [Attack the Premise](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-attack-the-premise/SKILL.md) | [修复根因](../../mini-sla-fix-root-causes/SKILL.md) | 重复失败时直接检验共同前提。 |
| [Subtract Before You Add](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-subtract-before-you-add/SKILL.md) | [先减后加](../../mini-sla-subtract-first/SKILL.md) | 按真实调用和契约删除当前范围内失效路径。 |
| [Minimize Reader Load](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-minimize-reader-load/SKILL.md) | [降低阅读成本](../../mini-sla-reader-first/SKILL.md) | 同时减少无效跳转和隐式可变状态。 |
| [Outcome-Oriented Execution](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-outcome-oriented-execution/SKILL.md) | [迁移调用方再删除旧接口](../../mini-sla-migrate-callers/SKILL.md) | 围绕目标契约设置验证边界并完成迁移。 |
| [Experience First](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-experience-first/SKILL.md) | [以使用结果为目标](../../mini-sla-outcome-first/SKILL.md) | 以 CLI、接口和维护者的实际操作为完成条件。 |
| [Exhaust the Design Space](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-exhaust-the-design-space/SKILL.md) | [比较方案再定设计](../../mini-sla-compare-designs/SKILL.md) | 仅对有实质分歧的方案做能区分结果的原型。 |
| [Build the Lever](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-build-the-lever/SKILL.md) | [把重复工作做成工具](../../mini-sla-build-tools/SKILL.md) | 以重复成本和复核价值决定工具投入，优先复用现有命令。 |
| [Model the Domain](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-model-the-domain/SKILL.md) | [用模型表达规则](../../mini-sla-model-domain/SKILL.md) | 把散落规则收敛到类型、状态转换和所有权。 |
| [Boundary Discipline](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-boundary-discipline/SKILL.md) | [在边界建立信任](../../mini-sla-boundary-validation/SKILL.md) | 输入解析后，仍在事务边界校验会变化的状态。 |
| [Type System Discipline](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-type-system-discipline/SKILL.md) | [用模型表达规则](../../mini-sla-model-domain/SKILL.md) | 类型收窄与运行时约束互补，不把 Python 注解当校验。 |
| [Make Operations Idempotent](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-make-operations-idempotent/SKILL.md) | [让重复执行收敛](../../mini-sla-idempotent-operations/SKILL.md) | 区分结果接受幂等与真实调用、未知费用。 |
| [Migrate Callers Then Delete Legacy APIs](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-migrate-callers-then-delete-legacy-apis/SKILL.md) | [迁移调用方再删除旧接口](../../mini-sla-migrate-callers/SKILL.md) | 内部调用方同步迁移，外部与持久化契约按实际兼容需求处理。 |
| [Separate Before Serializing Shared State](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-separate-before-serializing-shared-state/SKILL.md) | [先隔离共享状态](../../mini-sla-isolate-state/SKILL.md) | 独立尝试隔离；必须共享的权威状态保持事务约束。 |
| [Prove It Works](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-prove-it-works/SKILL.md) | [取得真实反馈](../../mini-sla-real-feedback/SKILL.md) | 验证实际路径和产物，绑定本次源码与环境。 |
| [Fix Root Causes](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-fix-root-causes/SKILL.md) | [修复根因](../../mini-sla-fix-root-causes/SKILL.md) | 复现、追查首次错误决策，再验证同类原因。 |
| [Sequence Work into Verifiable Units](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-sequence-verifiable-units/SKILL.md) | [小步验证](../../mini-sla-small-steps/SKILL.md) | 按完整行为分步取得反馈，保留阶段证据。 |
| [Test Behavior, Not Implementation](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-test-behavior-not-implementation/SKILL.md) | [验证行为](../../mini-sla-test-behavior/SKILL.md) | 检查调用者可观察结果与副作用。 |
| [Explain the Number](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-explain-the-number/SKILL.md) | [解释测量结果](../../mini-sla-explain-measurements/SKILL.md) | 核对工作量、口径、噪声和原始样本，解释必须有运行证据。 |
| [Guard the Context Window](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-guard-the-context-window/SKILL.md) | [保留关键上下文](../../mini-sla-context-discipline/SKILL.md) | 定向读取与可追溯摘要；任务是否委派遵循当前授权。 |
| [Never Block on the Human](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-never-block-on-the-human/SKILL.md) | [主动推进可逆工作](../../mini-sla-advance-work/SKILL.md) | 在已有范围内继续执行，把真实依赖与常规选择分开。 |
| [Encode Lessons in Structure](https://github.com/cursor/plugins/blob/e5136d82418d2db3165ea1050d17577cd618cc05/pstack/skills/principle-encode-lessons-in-structure/SKILL.md) | [把规则变成检查](../../mini-sla-encode-invariants/SKILL.md) | 机械规则进入结构或检查，需要判断的内容留为短原则。 |
