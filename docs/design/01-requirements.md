# mini SLA harness 产品需求设计

> 来源：[mini SLA harness 产品需求设计](https://chatgpt.com/space/page_3e7e4a9aa9c8819195c8e21e75f6073d) · 导入：2026-10-15 06:05:42 UTC
> 以下正文描述设计目标，当前实现见[当前架构](../architecture.md)。快照与维护约定见[本地索引](README.md)。

<!-- pages-snapshot-body:start -->
版本 0.2 · 2026年10月11日 · 建议方案，尚未实现

[返回设计总览](00-overview.md)

本项目中的 SLA 指 Stateless Language Agents。本文把共享会话中的研究执行框架细化为可开发、可验收的单机产品。核心交互采用 CLI；产品价值在于外部可信状态、上下文重建、受控探索和可复核的实验。数值均为工程默认，必须在 Run 启动前冻结；Python、SQLite 与容器方案仍须通过实现验收。

## 1 定位与目标与成功定义

目标用户是希望让编码 Agent 对一个程序进行持续优化的开发者和研究者。适用任务应具有明确输入输出、固定修改范围、机器可检验的正确性与可重复计算的主指标。本版以 Python JSONL 聚合程序的吞吐量优化为贯通案例。

用户提交一次任务契约后，Harness 负责启动新的 Advisor／Worker 会话、生成实验安排、冻结候选、独立评估、更新局部与全局成果，并在暂停或崩溃后从持久状态继续。模型负责提出方向和生成代码，不直接拥有数据库状态迁移权。

| 目标 | 可观察结果 |
| --- | --- |
| 可信研究状态 | 每个分数都能追溯到不可变代码、评估版本、数据与环境；无效候选不能提升最优。 |
| 长程可恢复 | 停止 Agent 会话或重启控制器后仍能定位最佳候选、分支头、未完成 Trial 和已消耗预算。 |
| 保留探索空间 | 新方向首个有效候选允许弱于全局最优；后续从该分支保留候选继续改进。 |
| 可比较的研究效率 | 统一预算下比较不同会话和协调策略，报告结果曲线、成本、失败类型及不确定性。 |

工程成功与研究效果分别验收：未找到更快实现不代表 Harness 失败；找到高分也不能掩盖恢复、隔离或计费缺陷。本文不承诺相对基线的性能优势，也不把“至少提高某个百分比”作为功能验收条件。

## 2 来源与设计决策与范围

来源标签：[S1] 原共享会话中的 Mini-SLA 与 StateStore 方案；[S2] 原论文 §2.2、§3、§5 和附录 B.1。论文支持 Harness 持久状态、全新 Advisor／Worker、并行与局部保留；原会话建议单 Worker→可靠恢复→Advisor／并行→消融的实施顺序。具体 Schema、CLI、可信 IPC 计时、防缓存、整数阈值和最终审计属于工程细化，不能作为论文公开协议或已证实效果。

| 编号／来源 | 决策 | 本版处理 |
| --- | --- | --- |
| D-01 · [S1] 延续 | Harness 持有状态，Agent 每个 Trial／Epoch 重建会话 | 使用 ContextBuilder，禁止以聊天历史作为权威当前状态。 |
| D-02 · [S1] 延续 | 局部与全局成果分离 | Branch 拥有局部候选；Worker 只是执行槽位。 |
| D-03 · [S1] 延续 | 单机 Python、SQLite、CLI、独立评估器 | 一个控制器写库，WAL 模式；无 Redis 或跨机器调度。 |
| D-04 · [S1] 细化 | 三个 Worker，各方向连续尝试 | 建议上限 3 个槽位×每个 Assignment 3 次 Trial；参数可配置。 |
| D-05 · 本次新增 | 任务、交互与停止语义 | 固定 JSONL 语义、CLI 输出、Run 状态、排空及强制停止规则。 |
| D-06 · 本次新增 | 评估与准入阈值 | 独立进程预热2次、fresh-process测量5次、可信IPC中位数；整数bps默认100（ε=1%），仅作噪声过滤。 |
| D-07 · 本次新增 | 交付与效果证据分开 | 先 fake 验证预算/fencing/协议，再接真实模型、恢复、Advisor并发与公平消融。 |

目标 MVP 包含 TaskAdapter、AgentAdapter、StateStore、ArtifactStore、ContextBuilder、AdvisorScheduler、WorkerRuntime、ProtectedEvaluator 与 Orchestrator，保留 Advisor 和最多三个并行 Worker。交付先用 fake 验证事务、最小预算门控与 fencing，再形成单 Worker 纵向闭环、恢复、Advisor 与并发；这是降低调试复杂度的实施顺序，不是删除完整研究方案。真实模型先支持一个提供方。

- 不做通用聊天助手、自然语言任意任务自动接入、多租户平台、网页后台或完整 REST 服务。

- 不做 Worker 直接通信、分布式队列、向量检索、跨机器 Worker、长期驻留 Agent 或任意时刻自动分支合并。

- 不默认安装未知依赖，不让 Worker 修改评估器、保护测试、运行配置或其它 Worker 私有目录。

- 不承诺完整复现论文效果；JSONL 单任务结果只能支持这个任务与实验条件下的判断。

## 3 用户旅程与 CLI 反馈

典型旅程是“校验任务→运行→观察→解释失败→暂停或恢复→导出结果”。以下命令为建议接口，所有写操作通过同一受控状态入口执行。

| 步骤／命令 | 用户获得的结果 |
| --- | --- |
| task validate TASK | 检查任务 Schema、编辑范围、起始代码、依赖锁、评估指纹和资源限额；配置错误在调用模型前失败。 |
| run --task TASK --preset sla --token-budget N | 建立 run_id 和配置快照，正式评估起始代码；基线有效后再启动模型。 |
| status RUN --watch / --json | 显示 Run 状态、当前 Epoch、有效／失败 Trial、全局最佳、在途数及 spent／reserved／uncertain。 |
| inspect trial TRIAL | 展示分支、父候选、任务假设、结果候选、正式评估、用量和采纳／拒绝原因，并提供证据引用。 |
| pause RUN / resume RUN | 停止新派发，排空当前 Trial 后暂停；恢复先对账和校验，再以新会话继续未执行配额。 |
| stop RUN / stop RUN --force | 默认排空当前 Trial 后完成；force 终止执行并撤销有效 fence，迟到提交不得生效。 |
| export RUN --out DIR | 导出冻结最终候选、搜索成绩、独立审计状态/成绩、指纹、谱系、事件、用量和失败摘要；未审计明确标注。 |

```text
mini-sla run --task tasks/jsonl/task.yaml --preset sla --token-budget 100000
mini-sla status run_001 --watch
mini-sla inspect trial trial_007
mini-sla pause run_001
mini-sla resume run_001
mini-sla export run_001 --out exports/run_001
```

100000 Token 仅为命令示例，不代表推荐研究预算。控制台默认聚合重大变化，不逐条广播心跳、哈希校验和例行工具调用。详细过程通过 inspect 查阅。Token 未知时明确显示“待对账”，不能显示为 0。终端关闭与用户请求停止不同，不应无意重复开启 Run。

若新候选都未通过，可导出已验证起始基线并注明“无有效改进”；其搜索验证不替代最终审计。正常预算结束或无提升不属于 CLI 故障。候选最终审计失败显示 REJECTED，设施耗尽显示 INCONCLUSIVE；配置错误、状态损坏和不可恢复环境错误返回非零退出码。

## 4 Run与Epoch 与 Trial 的用户可见语义

| 状态 | 含义与后续动作 |
| --- | --- |
| CREATED | 配置、baseline Candidate 和唯一 baseline job 已持久化；尚无模型调用。 |
| RUNNING | 允许符合预算与租约条件的新派发。 |
| PAUSING | 已接受暂停请求；禁止新 Trial／Advisor 调用，排空已开始 Trial、baseline 或已发出的规划请求。 |
| PAUSED | 可保留未领取 PENDING、待发规划和已验证未提交计划；无活跃执行／未完成 finalization。resume 按 resume_phase 续接初始化、规划或剩余配额。 |
| STOPPING | 取消未领取PENDING，不再派发；排空在途或处理强制终止。 |
| COMPLETED | 正常完成、预算结束或用户结束；用 completion_reason 区分原因。 |
| FAILED | Run 遭遇不可恢复错误；保留已有可信成果和诊断。 |

一个 Epoch 创建一次 Advisor 规划；一个 Assignment 对应一个研究方向和试验配额。每个 Worker 槽位顺序执行所属 Trial，不同 Branch 可并行。暂停或可恢复中断后，保留本 Epoch 尚未执行配额，不自动消费完，也不直接开启新 Epoch。

Assignment 必须具有明确终态；用完配额正常完成，停止或方向取消时把剩余次数明确标为跳过，并记录理由。Epoch 只在全部 Assignment 进入终态后关闭，不能以“Worker 进程退出”或“刚好完成三个 Trial”推断闭合。暂停时尚有剩余配额的 Assignment 保持可续跑。

默认 pause／stop 排空已开始 Trial，后续必要调用仍受原逻辑 Trial 累计预算与超时约束。规划时 pause 只接收当前已发请求，不新发修复；保留 PLAN_RECEIVED 结果，resume 校验后提交。stop 不提交新计划，取消未执行配额；已有 Trial 的有效结果可晋升。force 在一个事务中写 stop_mode=FORCE、撤销代次、取消全部非终态 Trial／规划／未完成评估，再在事务外终止进程。DONE 评估若尚未 finalize，也不能在 force 后晋升。最终记录 USER_STOP 或 USER_FORCE_STOP；未知费用继续对账。 初始化尚未领取 baseline 时 pause 保留 job 并记录 INITIALIZING；stop 则取消该未启动 job，可无候选完成。基线已开始则按排空规则处理。

Run 进入终态后不可原地继续消费预算。若希望延长研究，未来可提供显式 fork／extend 协议；本版应拒绝含糊的 resume。停止后已有正式最优可导出，迟到候选仅保留诊断证据，不得回写已结束状态。

## 5 JSONL 聚合任务的精确契约

允许修改 src/processor.py；依赖固定为运行镜像中的 Python 标准库。可公开函数签名、语义、样例和开发测试；保护正确性数据、正式执行驱动及私有诊断只供受保护评估流程使用。

```text
def aggregate(data: bytes) -> list[tuple[str, int, int, int]]:
    # (user_id, event_count, purchase_count, total_amount_cents)
    ...

# 输入（三行 JSONL）
{"user_id":"u2","event":"view"}
{"user_id":"u1","event":"purchase","amount_cents":1200}
{"user_id":"u1","event":"purchase","amount_cents":300}

# 返回
[("u1", 2, 2, 1500), ("u2", 1, 0, 0)]
```

| 维度 | 固定语义 |
| --- | --- |
| 编码／分行 | 严格 UTF-8，以 LF 分行；允许 CRLF、空行及只含空格／Tab／CR 的行；最后一行可无换行；空输入返回 []。 |
| 记录结构 | 每个非空行为 JSON 对象；user_id 为非空字符串；event 仅允许 view、click、purchase。 |
| 金额 | purchase 必须有非负整数 amount_cents；bool 不算整数。view／click 不计金额。使用整数精确累加。 |
| 聚合 | 所有事件计入 event_count；purchase 还计入 purchase_count 和金额。重复记录重复计数。 |
| 排序／归一化 | 按 user_id 精确分组，不做大小写或 Unicode 归一化；按 Python 字符串比较顺序排序输出。 |
| 额外字段 | 未知字段忽略；重复 JSON 属性以后出现的值为准；NaN／Infinity 等非标准 JSON 值非法。 |
| 无效输入 | 任何一行编码、JSON、必需字段不合法，整个调用抛 ValueError；不返回部分结果；错误文字不参与判等。 |
| 调用独立性 | 不得依赖上次调用、输入对象地址、调用次序或固定数据答案；同内容不同 bytes 实例应返回相同结果。 |

正确性集覆盖大／小用户基数、Unicode、金额边界、空输入、重复记录、无尾换行、无效记录，以及同进程多次调用和同内容不同 bytes 实例。正式性能每个样本使用全新候选进程，只调用一次 aggregate；两次预热使用独立进程和独立输入，不给五次测量预填缓存。五份固定、互异的测量输入对同一 Run 的所有候选一致，清单和顺序纳入私有评估指纹。公开开发、正式反馈、最终审计数据分离；审计结果不得回流搜索。

## 6 正式评估与采纳规则

主指标为受控协议下的 end_to_end_records_per_second，越高越好。可信 supervisor 用单调时钟从发送输入帧前计时，到完整、有大小上限的输出帧收齐后结束；计时包括 IPC、解析、聚合、排序、输出编码及传输，不采用候选报告的时间，也不事后减去 IPC。容器启动、import、输入生成和参考答案计算在计时外；候选在计时开始前接触不到本次输入。2 次独立预热后，对 5 个全新进程的一次性调用分别测量，取吞吐量中位数。记录 elapsed_ns、记录数、字节数、进程身份、原始样本、峰值 RSS 和指纹；超时包含协议等待。此口径测量的是完整接口吞吐量，不声称是纯函数内部耗时。

只有正式正确性通过且性能测量有效的候选才有可比较 score。BUILD_FAIL、INCORRECT、CANDIDATE_TIMEOUT 和 CANDIDATE_RESOURCE_LIMIT 是候选 verdict，score 为 null；INFRA_ERROR 属于评估 attempt 的设施错误，按有界策略重试而不伪造候选成绩。Worker 自测不能成为晋升依据。正式性能测量在独立槽位执行，避免编程负载争用主导评分。

默认 ε=1%，用整数 min_improvement_bps=100 表示（1 basis point = 0.01%）；允许 0～10000，Run 内不可修改。score_i 由可信 elapsed_ns 和记录数算出并量化至每秒记录数的千分位。已有局部／全局成绩时，只有 new−old≥max(1,(abs(old)×min_improvement_bps+9999)//10000) 才更新；全部中间计算用任意精度整数，入库检查 int64 范围。恰好达阈值允许采纳。新 Branch 的 head 初始为空，首个有效候选直接成为 head，即使低于 Global Best；Branch.base 保留创建时起点。

阈值只是噪声过滤，不是显著性证明。Global Best 指已晋升的 incumbent，可能不等于 raw 最大测量值；近似分数的完成顺序可能影响晋升。搜索比较只允许同 evaluation_spec_hash 的 SEARCH 结果。结束搜索后冻结 final_candidate_id 与 export_manifest_hash，单独运行 FINAL_AUDIT；审计使用独立 audit_spec_hash 和数据身份，不更新 Head/Best、不反馈 Advisor/Worker、不触发换候选重搜。审计不正确标记 REJECTED，设施失败耗尽标记 INCONCLUSIVE，均不得发布“已验证最优”；历史搜索成绩和 Run 终态保留。

## 7 功能需求与可追踪约束

| 编号 | 需求与验收要点 |
| --- | --- |
| FR-01 任务校验 | 调用模型前验证任务 Schema、允许改动范围与环境；冻结配置和起始代码。 |
| FR-02 新会话执行 | 每个 Advisor Epoch 和 Worker Trial 创建新会话；保存上下文版本、快照引用与 hash。 |
| FR-03 方向调度 | Advisor 输出结构化 Assignment；校验父候选、方向、配额和作用范围；非法计划有限次修复。 |
| FR-04 分支成果 | Branch 与槽位分离；首个有效结果可比全局差；后续按 ε 保留局部改进。 |
| FR-05 候选与评估 | 先冻结不可变产物再记录引用；正式评估验证正确性后评分；候选与证据可校验。 |
| FR-06 一致性 | 受控事务更新 head／best／事件；命令幂等；同 Branch 单活跃 Trial；旧 fence 不得生效。 |
| FR-07 预算 | 逐模型调用记账；Advisor、Worker、失败、修复与重试均纳入；预留、已用和未知消耗分开；Run 与逻辑 Trial／Advisor invocation 双层累计门控，覆盖重试与修复。 |
| FR-08 生命周期 | 支持 status、pause、resume、stop 与 force；包括 CREATED 基线和 PLANNING 的暂停／恢复，明确强停线性化点。 |
| FR-09 恢复 | 校验产物、对账、租约和评估记录；不重复完成／重复结算，不依赖恢复旧对话。 |
| FR-10 诊断与导出 | 按阶段、错误码和证据引用解释结果；正常无提升可导出基线，完整保留终止原因及独立审计状态。 |
| FR-11 运行边界 | 由挂载、进程／容器权限与工具门控落实文件和网络范围；模型凭证不进入候选执行环境。 |
| FR-12 实验比较 | 固定模型和环境；输出按预算的质量曲线、有效率、失败分层与重复运行结果。 |

可靠性、可诊断性和隔离是实现门槛，不依赖 Agent 自觉遵守。完整对话与假设可留作分析，但不能升级成权威观测事实；事实、假设和 Advisor 决策必须标注来源。正式验收用例与阶段 Gate 见《实施与验收设计》。

## 8 默认决策与来源引用

本版默认选择单机 CLI、Python、SQLite WAL、一个控制器、三个可配置执行槽位、每 Assignment 最多三个 Trial、先 fake 后真实模型、2 次独立进程预热＋5 次 fresh-process 协议测量中位数、min_improvement_bps=100（ε=1%）、pause／stop 排空当前 Trial。它们是为了尽快形成可验证闭环的建议，不是已经实现的能力。

实现前需固定真实模型适配器、可用 Token 预算、评估机器规格、数据规模与容器镜像。若暂时没有用户偏好，先使用 fake 适配器和固定本地样例推进协议开发；真实付费运行前必须使用用户配置的模型与额度。

[S1] 原始共享会话：https://chatgpt.com/share/6ac9ad68-27d4-83ec-a674-df6e7b748739?ogimg=plain

[S2] 原会话关联论文：https://arxiv.org/abs/2610.07625 。本版工程需求主要由 [S1] 延展；新增产品协议不归因于论文。
<!-- pages-snapshot-body:end -->
