# mini SLA harness 实施与验收设计

[返回设计总览](00-overview.md)

本文规定如何把设计推进到可运行闭环，以及如何区分可靠性通过与研究效果成立。所有参数为建议默认；本文中的命令、测试和报告是待实施的验收方案，不代表已经运行或通过。产品需求编号 FR-01～FR-12 与本文件测试和阶段 Gate 对应。

## 1 实施顺序与交付 Gate

按纵向闭环开发，保留最终 Advisor＋并行 Worker 与研究对照目标。先用 fake 验证预算、代次和事务，再接真实调用，随后完成恢复和规划并发。单 Worker 是缩小排障范围的中间交付，不替代完整 Mini-SLA。以下阶段是进入下一阶段的前置 Gate，不能以演示通过绕开。

| 阶段／依赖 | 可审查交付 | 离开阶段的 Gate |
| --- | --- | --- |
| M0 契约与安全闭环／无 | TaskSpec、fake Agent/Evaluator/provider、SQLite 与产物、Run/Trial/Advisor 预算 scope、逐调用预留/UNKNOWN、controller/attempt fencing、force 线性化、baseline/规划状态模型。 | 离线验证幂等、范围预算、旧代次拒绝、强停竞态；T-15～18、T-24～26 的最小协议测试通过，禁止先接付费 API。 |
| M1 单 Worker 真实闭环／M0 | JSONL 可信 IPC 评估、fresh-process 测量、候选快照、ContextBuilder、一个真实 AgentAdapter、CLI。 | T-23 计时/缓存/协议隔离通过；真实调用前双层预算和 hard-limit 能力验证；三个 Trial 新会话、无效候选无分数。 |
| M2 完整生命周期与恢复／M1 | pause/resume/stop、baseline CREATED 恢复、全故障注入、持久计数、对账与产物校验；沿用 M0 fencing。 | T-12～17、T-24～26 所有崩溃点通过；恢复不重不漏，未知费用不释放。 |
| M3 Advisor 与并发／M2 | 真实 Advisor 结构化规划、持久响应/修复/重规划、3 槽位×3 Trial、Branch/Epoch 屏障。 | T-25 规划全状态与暂停/停止通过；同分支单活跃，跨分支并发与预算不超授，force 无迟到晋升。 |
| M4 效果与消融／M3 | A/B/C/D、预算曲线、失败分层、重复运行、冻结最终候选和独立最终审计、可核验导出。 | T-27～29 与审计失败路径通过；所有 Run 入报告，预算/计时口径一致，不以 Mini-SLA 获胜为通过条件。 |

fake Evaluator 的固定分数只用于协议测试，不能作为优化效果证据。M0、M2 和 M3 的故障／并发用例先以 fake provider 运行，无需付费。真实模型必须在最小预算门控与 fence 已通过后，才使用用户明确配置的小额度试运行。

## 2 可靠性与效果的两类门槛

| 门槛 | 必须满足 | 不允许替代的证据 |
| --- | --- | --- |
| 可靠性发布 Gate | 候选不可变；指针由有效同口径评分更新；事务和幂等正确；lease／fence 生效；预算可解释；权限边界与恢复通过。 | 一次演示成功、较高代码覆盖率或模型表示遵守约束，均不能替代故障与并发验收。 |
| 研究效果报告 Gate | 统一模型、任务、环境和预算；重复运行；包含失败与未知消耗；最终审计；结论限定实验条件。 | 单次最好结果、只保留成功种子、不同预算曲线或以一个任务推断普适能力。 |

工程 Gate 采用明确断言；研究 Gate 采用透明报告。优化未提升可正常结项；若公平对照显示 Advisor 没有收益，也应如实记录。ε=1% 只过滤微小波动，不是统计显著性阈值，更不应直接解释为真实速度提高至少 1%。

发布阻断条件包括：无效成绩晋升、产物引用失真、迟到 Worker 写入、重复结算、隐藏测试／凭证越界、恢复丢失已提交事实，以及预算未知却显示为精确值。普通候选构建失败或有效但无改善属于研究过程，不阻断发布。

## 3 核心验收用例 状态与产物与分支

| ID／关联需求 | 前提与操作 | 必须断言 |
| --- | --- | --- |
| T-01／FR-01 | 缺少 editable_files 或主 metric；执行 task validate 和 run。 | 模型调用数为 0；返回具体字段错误；不创建可派发的 Run。 |
| T-02／FR-02 | fake Agent 在第一个对话输出唯一标记；连续三个 Trial。 | session_id 均不同；新上下文不含旧聊天标记；合法候选与正式反馈仍在。 |
| T-03／FR-04 | Global=90，新 Branch：有效 85、83、96，依次 finalize。 | head 先85，再保持85，后96；global先保持90，后96；每次父候选可追踪。 |
| T-04／FR-04 | 已有 head=100；正式有效结果100.5、101，ε=1%。 | 100.5 不替换；101 达阈值可替换；两次测量均保存。新 Branch 首次有效不受此门槛。 |
| T-05／FR-05 | 候选修改测试文件，或正确性失败，或评估器异常。 | 分别拒绝范围／记录失败／标记可重试；score=null；head 与 best 均不被污染。 |
| T-06／FR-05,09 | 冻结候选后删除或修改其对象文件，再恢复／导出。 | 发现缺失或 hash 不匹配；阻断相关引用采纳；报告具体证据链，不能悄悄重新生成替代。 |
| T-07／FR-06 | 已知合法结果；同 command_id 同载荷重复两次，再换载荷。 | 前两次返回同结果且仅生效一次；不同载荷冲突；换 ID 重复完成也不重复结算。 |
| T-08／FR-06 | 两个 Branch 结果110与120，在Global=100时交换提交顺序。 | 两次排列最终 global=120；不发生旧读覆盖；事件与指针原子一致。 |
| T-09／FR-06 | 同一 Branch 同时尝试领取两个活跃 Trial。 | 只有一个符合活跃唯一约束；另一个明确拒绝，不靠调用方自觉串行。 |
| T-10／FR-05,12 | 更换 evaluator 或 dataset fingerprint 后提交高分。 | 不得与原 Run 最优比较；明确不兼容原因；原最优保持。 |

这些用例优先使用 fake 模型与固定评分运行，使失败能定位到 Harness 协议。真实模型只用于后续集成验证，不依靠模型恰好生成指定分数来测试数据库一致性。

## 4 核心验收用例 恢复与预算与控制

| ID／关联需求 | 前提与操作 | 必须断言 |
| --- | --- | --- |
| T-11／FR-06,09 | Trial generation=1 租约过期，被 generation=2 认领；旧提交迟到。 | 旧提交 STALE_CLAIM；旧心跳不能续租；新提交可正常完成且候选谱系正确。 |
| T-12／FR-09 | 在落盘、候选落库、评估记录、finalize提交前后分别 kill 控制器；恢复两次，恢复持久状态并启动新会话，不恢复对话。 | 已提交事实保留；未提交事务无半状态；不重复完成／结算；已有候选续评而非重新生成。 |
| T-13／FR-08 | Assignment 配额3，当前第1次运行时 pause，排空后 resume。 | PAUSING→PAUSED；可留PENDING但无RUNNING／CANDIDATE_READY／EVALUATING；恢复续跑第2、3次，不新开Epoch。 |
| T-14／FR-08 | 配额3，当前第1次运行时 stop。 | STOPPING取消PENDING并排空第1次；剩余2次标跳过且Assignment终结；全部Assignment终态才关闭Epoch；COMPLETED并记录USER_STOP。 |
| T-15／FR-06,08 | 有执行中Trial与模型请求；stop --force 后提交旧结果。 | 终止可控制进程并撤销全部活跃fence；旧提交拒绝；DONE 尚未 finalize 的 Trial 也 CANCELLED、不能晋升；记录USER_FORCE_STOP；未知用量继续对账。 |
| T-16／FR-07 | 可用预算仅足一个调用；两个Worker并发申请预留。 | 至多一个预留成功；spent＋reserved＋uncertain不被重复扣算；预算不足不派发。 |
| T-17／FR-07 | 请求成功但响应丢失，无法立即取得usage；恢复并尝试重试。 | 首请求保留未知消耗；不直接释放全部预留；真实第二次请求独立记账，逻辑幂等不抹除费用。 |
| T-18／FR-07,12 | 提供input=1000，其中cached=600，output=100；另有Advisor和修复调用。 | 本调用total=1100而非1700；所有其它实际调用纳入Run；缓存用量作为子项另列。 |
| T-19／FR-11 | Worker尝试访问其它私有目录、保护测试和凭证、越界写文件或联网。 | 由实际进程／挂载／工具权限阻断；不只是Prompt拒绝；候选运行环境不继承模型密钥。 |
| T-20／FR-10,12 | 全部新候选失败后预算结束，导出与再次resume。 | 导出已验证起始基线和失败摘要；正常completion_reason；终态Run拒绝直接续费续跑。 |
| T-23／FR-05,11 | 恶意候选伪造计时字段、预热记忆输入、延迟输出、畸形/超大协议帧；记录五次进程与输入身份。 | 分数只由 supervisor elapsed_ns 生成；每样本新进程、一次调用、无共享缓存；IPC/序列化计入；输出完整接收后停表，错误帧不计有效分；import 前无本次输入。 |
| T-24／FR-06,08,09 | 设置 job DONE、Trial EVALUATING；分别让 ForceStop 与 FinalizeTrial 先提交，随后崩溃恢复并重放。 | force 先则 CANCELLED、Best 不变；finalize 先则保持已采纳；DONE 证据不删除；两种顺序均唯一终结。 |
| T-25／FR-03,08,09 | CREATED 基线排队/执行/DONE；PLANNING 在预留/发送/响应落盘/响应入库/计划提交各点崩溃，并分别 pause/stop/resume。 | 同 baseline job 与 invocation 收敛；已接受响应无需重调；READY 不重复建 Assignment；暂停无新修复/派发，恢复按 resume_phase；未领取 baseline 暂停保留/停止取消，已领取可排空；空计划 Epoch 明确终结。 |
| T-26／FR-07 | Run 余额充足但 scope 接近上限；Worker 换 attempt，Advisor 格式修复/重规划，旧请求 UNKNOWN 后再申请。 | 原逻辑 scope 计数不清零；两层 confirmed+held+R 同时检查；拒绝越额调用；结算/释放在两层一致且重复 receipt 无作用。 |
| T-27／FR-04 | bps=250、old=100000，尝试102499/102500；另测 bps=0、非法小数/负数和溢出。 | 边界确定；0 仍至少加1；不合法配置在调用前拒绝，修改 bps 不得沿用旧 Run/spec。 |
| T-28／FR-10,12 | 冻结最终候选后审计错误、审计设施失败耗尽、正确通过；尝试带审计高分 FinalizeTrial。 | 分别 REJECTED/INCONCLUSIVE/PASSED；审计身份独立；高分不得晋升；失败不换候选、不回流搜索；导出明确验证状态。 |
| T-29／FR-05,12 | 同样本以可信整数 ns/记录数重复算中位数与 score_i，且搜索与审计数据身份不同。 | 分数量化可精确复算；保存原始样本；两类成绩分栏且指纹不混排；不把 IPC 吞吐量标成纯函数耗时。 |

pause／DRAIN stop 允许已开始 Trial 在原逻辑累计预算／超时内完成必要调用。规划暂停仅接收当前请求结果，修复等 resume；停止取消计划。force 的研究状态边界是数据库 ForceStop 事务提交，不是 OS kill 完成或远端费用停止。远端已接收请求可能继续收费，必须保留 call_id、scope 和待对账额度。

## 5 诊断与导出验收

inspect trial 按六个阶段解释：计划校验、Agent 调用、候选提交、正确性、性能、状态采纳。每个阶段保存 status、error_code、retryable 与 evidence_refs；人可读摘要不替代结构化恢复依据。

| 故障类别 | 用户可见解释 | 恢复动作 |
| --- | --- | --- |
| AGENT_OUTPUT_INVALID | 指出不合法字段和已修复次数。 | 修复次数封顶，超限结束该计划或尝试。 |
| BUILD_FAIL／INCORRECT | 展示允许公开的最小诊断与产物引用，无有效分数。 | 下一次同分支Trial可利用反馈；不作无限基础设施重试。 |
| 候选超时／Evaluator基础设施超时 | 明确超时属于候选程序还是评估环境。 | 前者为候选结果；后者用稳定请求键重试同一快照。 |
| STALE_CLAIM／IDEMPOTENCY_CONFLICT | 解释提交被拒绝的代次或命令冲突。 | 权威指针不变；保留attempt证据与真实费用。 |
| VALID_NO_IMPROVEMENT | 列出候选成绩、比较基准和该 Run 的 bps 门槛（默认1%）。 | 正常保留历史，无需恢复或标记Run故障。 |

每份导出至少含 Run/配置、task/search spec/audit spec/environment 指纹、incumbent 与 lineage、原始计时样本、采纳事件、逐 call 的 scope 归属/用量/未知项、上下文版本、Trial 结果、completion_reason，以及 frozen final_candidate_id、export_manifest_hash、audit_status。T-21：随机曲线点能定位评分、代码、父版本、预算和采纳原因。审计未完成/失败时导出显著标为未验证，不能仅展示搜索高分。

T-22：对冻结最终候选运行一次逻辑 FINAL_AUDIT，独立 audit_spec_hash/输入清单；正确性一致，性能可波动，不要求与搜索分数逐位相等。设施失败仅重试同一候选与审计 job，最多 2 次；候选错误不重试挑结果、不改选其他候选。审计结果保存为独立 Evaluation/audit_record，不能覆盖搜索测量或进入后续模型上下文；REJECTED/INCONCLUSIVE 阻止宣称已验证完成。

## 6 公平消融 比较什么与保持什么

| 组别 | 唯一主要变化 | 固定条件 |
| --- | --- | --- |
| A 持续会话单Agent | 保留会话历史；达到上下文上限时采用预声明压缩策略。 | 与B使用同样外部状态、工具、正式评估器和预算规则。 |
| B 无状态单Worker | 每Trial新会话，按同一规则重建结构化上下文。 | 与A固定模型、起始代码、Trial规则与环境；比较会话生命周期。 |
| C 三个无状态Worker | 各自按预声明策略选择方向，无Advisor。 | 与D均为3槽位、局部保留和新会话；方向生成调用照常计费。 |
| D 完整mini-SLA | Advisor根据事实摘要分配方向。 | 与C相同总预算，Advisor没有额外免费Token。 |

A/B 比较会话生命周期，C/D 比较协调；跨这两对同时改变并行度，不能把全部差异归因于无状态或 Advisor。若之后需要验证局部保留机制，增加 D-minus-local：新方向首个较差有效候选不保留，其余条件不变。初版先完成四组，不提前扩大矩阵。

- 锁定task、起始Candidate、完整模型标识和参数、工具权限、依赖镜像、数据、评估硬件、资源限制、超时和主评分规则；不同指纹拒绝直接混排。

- 所有调用纳入总Token：Advisor、Worker、计划修复、失败与实际重试。cached input是input子集，不能重复相加；美元费用按固定价目快照另报。

- 按配对任务／数据种子重复运行；模型seed不必然保证确定性。预算允许时建议先做每组5次探索性运行，报告个体曲线与分布，不据少量样本声称统计显著。

- 所有运行和失败保留；不可按结果选种子。搜索终态先冻结候选、清单和审计协议，再运行一次逻辑最终审计；审计不回流优化，失败不悄悄换候选。BASELINE／SEARCH 与 FINAL_AUDIT 的数据及 spec 身份分别记录。

- Budget-matched结果与同硬件wall-clock结果分别报告；并行更快不自动等于Token更省。独占评估槽和Worker负载干扰必须一致控制。

测量统一为 2 次独立进程/输入预热＋5 次 fresh-process 单调用中位数，指标 end_to_end_records_per_second，包含输入/输出 IPC 和编码，排除启动/import；计时前不向候选暴露本次输入。min_improvement_bps 默认100（ε=1%）并锁入 evaluation_spec_hash。独占评估槽、五份固定互异输入与进程隔离对所有组一致。报告基线和最终候选分布；阈值不构成显著性证明。

## 7 指标与预算口径

| 指标 | 计算与解释 |
| --- | --- |
| Best accepted score vs. tokens | 按累计已发生总input＋output排列正式采纳事件；保留阶梯曲线。它指已晋升候选incumbent，不是历史绝对最大值；raw最大值另列，近似分数完成顺序可能影响晋升。 |
| Tokens to target | 达到预先固定目标分数时Run总Token；未达到标记未达到／右删失，不能当0或删除。 |
| Valid Trial Rate | 获得有效正式分数的逻辑Trial／进入终态且实际执行的逻辑Trial；跳过配额另列，不进分母。 |
| Duplicate Trial Rate | 精确定义为重复candidate_hash且同evaluation fingerprint的非计划提交比例；意图相似只作辅助人工分析。 |
| Advisor Token Share | Advisor相关实际input＋output／Run全部实际input＋output；计划修复计入Advisor。 |
| Recovery Success Rate | 预定义故障注入中满足全部不变量并可继续的案例数／已执行案例数；同时报告失败位置。 |
| Time Since Improvement | 从最近一次正式采纳改进到观察时点的墙钟时间；同时报告是否暂停与等待评估。 |
| Budget／Cost | spent、reserved、uncertain分别显示；实际费用与Token分开；unknown不填0。 |

并行曲线的横轴必须计入整个Run，而非只计获胜Worker。对每次模型调用记录开始／结束、可信usage和与Trial的归属；在结果提交时汇总当时已确认实际用量，对仍在途且未知的消耗标记区间或待对账状态。完全对账前不提供假装精确的公平预算结论，也不把未来已知费用倒填成当时已确定值。

已开始 Trial 可在停止后按原 scope 余额排空，各组一致；Advisor 所有修复/重规划和 Worker 所有 attempt 计入原逻辑 scope 与 Run。最终报告实际消耗和未决 held。无法给出可信逐调用上限/usage 的适配器拒绝严格预算模式，仅能明确标识 soft budget；预留不能消除远端费用暂时未知。

## 8 演示脚本与交付检查

演示A：5分钟协议闭环。用fake Agent固定输出四个结果：新分支85、退步83、改进96、构建失败；起始全局90。展示新会话ID、局部保留、全局晋升和失败不污染最佳。再重复finalize并展示仅一次生效。示例分数仅服务协议演示。

演示B：5分钟恢复。启动三次配额，在第1次候选持久化后终止控制器；resume两次，展示从已存在候选继续评估、没有重复模型调用／结算；pause排空后保留第2、3次配额；resume继续。再演示旧generation提交被拒绝。

演示C：真实小预算。先核验 M0/M1 的预算、fencing 和可信评估 Gate，用用户已配置额度运行一 Epoch；查看 Advisor 计划、Branch 谱系、正式评价和 usage。结果允许无提升。停止搜索后冻结最终候选，运行独立审计，展示 PASSED／REJECTED／INCONCLUSIVE 与可追溯报告；失败不继续拿审计反馈优化。

```text
mini-sla task validate tasks/jsonl/task.yaml
mini-sla run --task tasks/jsonl/task.yaml --preset sla --token-budget 100000
mini-sla status RUN_ID --watch
mini-sla inspect trial TRIAL_ID
mini-sla pause RUN_ID
mini-sla resume RUN_ID
mini-sla stop RUN_ID
mini-sla export RUN_ID --out exports/RUN_ID
```

- 交付代码必须有可复现环境、示例TaskSpec、fake与真实适配器入口、迁移／启动说明及密钥配置说明。

- 交付证据应附关键测试结果、故障注入位置、版本锁定信息、样例Run导出与已知限制。

- 演示不展示模型密钥、隐藏测试内容或用户私有路径；诊断引用可用脱敏样例。

- 未实际运行的项目只能标记“待验收”；不得将设计文档中的预期断言写成已经通过。

## 9 风险与默认处理与待固定参数

| 风险／未决项 | 建议默认与处理 |
| --- | --- |
| 评估噪声与同机争用 | 独占评估槽，固定资源，2次独立预热＋5次fresh-process测量，默认bps=100；最终复核；不将阈值当显著性证明。 |
| 保护测试被候选读取 | 只读不等于不可读。驱动与候选进程分离，保护文件不挂载；可信外部计时含IPC，测量前无输入，样本无共享缓存；仍不承诺抵御宿主内核漏洞。 |
| 预算或模型usage缺失 | 先fake推进；真实适配器明确usage能力，未知消耗保留；用户额度必须显式配置。 |
| 停止过程过长 | 排空受现有Trial超时约束；需要立即停止使用force并撤销fence，仍保留对账。 |
| Advisor无收益或反复重复方向 | 固定修复／重复上限；保留B/C对照，结论允许无收益；后续再改调度。 |
| 配置漂移和数据泄露 | Run启动时冻结指纹；禁止中途改评估规则；日志与导出脱敏。 |
| 最终审计不通过 | 标记 REJECTED 或 INCONCLUSIVE，保留搜索历史；不宣称已验证，不使用审计反馈换候选。 |
| 具体模型、机器、数据规模待定 | 先使用fake、公开小样例与固定本地环境实现；付费实验前固定模型ID、Token额度、镜像、硬件与数据版本。 |

设计目标仍为 Python CLI＋SQLite WAL＋单控制器、Advisor 与最多3 Worker／每Assignment最多3 Trial。先实现预算门控和fencing，再真实调用和恢复；不是已经验证的技术栈。阈值统一整数bps；force阻断未finalize晋升；初始化与规划也可恢复；最终审计独立且不可回流。

研究背景见 [Stateless Language Agents 论文](https://arxiv.org/abs/2610.07625)。本文阶段、测试编号、CLI 与预算细则为项目工程设计，不等同于论文原始实验实现。
