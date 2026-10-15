# Mini-SLA 想法与探索

集中记录 Mini-SLA 的设计启发、备选方向和待验证的小实验。这里的想法尚未决定实现，不修改正式契约，也不加入当前 M0 范围。

[返回设计总览](00-overview.md) · [总体架构与接口设计](02-architecture.md)

每个想法按主题独立记录，保留记录日期、启发来源、可能的用途、适用边界与验证方式；采纳与否另行决定。

## 待探索的记忆层

AgentMemoryRepo 值得借鉴的是可追溯的轻量知识组织：Git 中的 Markdown、短 `MEMORY.md` 入口、主题链接、来源与日期，以及可复用的查询和脚本。[格式规范](https://github.com/AgentMemoryRepo/agentmemoryrepo/blob/main/SPEC.md) 当前公开 [skill](https://github.com/AgentMemoryRepo/agentmemoryrepo/blob/main/skills/agent-memory-repo/SKILL.md) 按需调用、默认本地运行，不自带启动钩子、后台调度或并发自动合并；[官网](https://cognition.com/agent-memory-repo) 的多人协作与周期整理愿景不等于这些能力已由该 skill 实现。

- **知识与执行状态分层**：可探索保存策略理由、失败尝试、可复用方法和经核验摘要。任务状态、预算、评估结果与最终结算仍由 StateStore 权威记录；知识条目引用规范对象 ID 与证据，不能另写一套执行真相。

- **按需读取**：ContextBuilder 可先读小索引，再按任务读取相关条目，继续保持每次 Advisor／Worker 会话全新。若采用，需冻结所用记忆版本／内容哈希，纳入上下文复现与 token 预算。

- **继承证据边界**：读取及摘要均须执行现有角色、run、branch 与 BASELINE／SEARCH 白名单。FINAL_AUDIT 输入、结果和诊断不得经记忆摘要回流未来搜索；引用不能绕过访问控制。条目保留来源、日期及 OBSERVED／HYPOTHESIS 等标签，过期或冲突信息不能悄悄变成事实。

- **协作限制**：Git 文本合并不保证语义一致，也不能替代任务认领、租约、fencing 和幂等事务。文件协作仍需明确何时通知、何时只记录，否则同样可能产生重复消息。

- **暂缓扩张**：先考虑人工整理的本地小型知识集，不提前引入向量数据库、Git 多人写入或周期整理调度器。是否需要、何时实施，等核心闭环验证后再决定。

可选小实验（未运行）：保持可信状态、任务、模型和总预算相同，让全新 Worker 分别使用与不使用经审核且符合访问边界的记忆；比较重复探索、正式评估质量和总 token／成本，包含读取与维护开销。收益和失真风险均待验证，不预设记忆一定更好。
