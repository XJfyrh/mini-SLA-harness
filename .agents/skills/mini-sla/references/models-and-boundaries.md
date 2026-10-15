# 模型与边界

| 触发条件 | 读取原则 |
| --- | --- |
| 选择核心类型、数据结构，或多处条件分支维护同一状态规则 | [用模型表达规则](../../mini-sla-model-domain/SKILL.md) |
| 处理 CLI、配置、provider 响应、数据库读取或状态提交校验 | [在边界建立信任](../../mini-sla-boundary-validation/SKILL.md) |
| 写入、恢复、重试或结算可能重复执行、被中断 | [让重复执行收敛](../../mini-sla-idempotent-operations/SKILL.md) |
| 多个进程、worker 或开发会话可能修改同一对象 | [先隔离共享状态](../../mini-sla-isolate-state/SKILL.md) |

恢复故障常同时触发后两条；接口解析与事务提交是不同的校验边界。具体字段、代次和事务承诺由 [状态协议](../../../../docs/design/03-state-transactions.md) 定义。
