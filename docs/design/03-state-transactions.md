# mini SLA harness 状态存储与事务协议

[返回设计总览](00-overview.md)

本文规定单机 MVP 的权威状态、事务接口与故障恢复协议。设计采用 Python asyncio、SQLite WAL 单写入者与不可变 Artifact Store；SLA 指 Stateless Language Agents。

## 1 状态承诺与初始化

StateStore 保存研究事实与当前指针；Agent 会话可以销毁，已提交 Candidate、Evaluation 和研究进展必须可以恢复。系统允许重试造成重复的物理模型调用或评估，保证同一业务结果最多接受一次。模型用量独立记账，不能随 Trial 失败、过期或取消而被丢弃。

- 候选不可变：进入数据库的 Candidate 绑定完整、可校验的代码产物；修改必须生成新 Candidate。

- 分数可追溯：Global Best 与 Branch Head 同时保存 candidate_id、evaluation_id、score_i，三者在同一事务内更新。

- 执行权有代次：Worker、Evaluator 与控制进程分别有 fencing generation；过期结果不能改变研究状态。

- 局部探索可退步：新 Branch 的首个有效候选可以低于 Global Best；后续 Head 与 Global 提升遵循固定阈值。

- 预算可审计：每次真实模型请求具有独立 call_id；未知用量保留预留额，不按零消耗处理。

CreateRun 在一个事务冻结 task_spec_hash、search evaluation_spec_hash、audit_spec_hash、模型与预算策略，并注册 baseline Candidate、唯一 BASELINE evaluation job 及 runs.baseline_evaluation_id，状态为 CREATED。对象先可靠落盘再引用。StartRun 只驱动该 job；InitializeBaseline 在事务中校验 job DONE/VALID_SCORED、候选/spec/purpose 一致且 stop_mode!=FORCE，幂等设置初始 Best。正常进入 RUNNING；PAUSING 则保留基线、进入 PAUSED（resume_phase=READY_TO_RUN）；DRAIN 则保存基线后完成，不启动模型。基线候选失败或设施重试耗尽为 FAILED，不用 0 分开跑。 evaluation_spec_hash 覆盖任务语义、SEARCH 数据清单、计时/IPC/进程策略、整数评分与bps、镜像/依赖、CPU/内存限制；audit_spec_hash 另含 FINAL_AUDIT purpose 与隔离数据清单。

Baseline Candidate 的 parent、origin_trial_id 可为空，request_key 固定为 baseline:{run_id}:{evaluation_spec_hash}。SEARCH 的 request_key 由 trial_id/candidate/spec 唯一派生；主动复测使用显式新的 replication_id。FINAL_AUDIT 使用 audit:{audit_id}:{audit_spec_hash}，其中 audit_spec_hash 含 purpose 和独立数据清单，必须区别于搜索 spec。新 Branch.base 指规划时 Global Best，Head 为空；Trial.base 创建时固定为 head ?? base，全局变化不改写已有 Trial。

## 2 核心数据字典与约束

时间、JSON 诊断和展示字段可补充；下表给出实现协议所需的字段。所有跨实体引用均检查同一 run_id；FK 只证明对象存在，不能替代所属 Run、Branch 和 Trial 的一致性校验。本章 SQL 为关键约束片段，省略完整建表与迁移定义，不可当作完整 DDL 直接执行。

| 实体 | 关键字段 | 约束或用途 |
| --- | --- | --- |
| runs | id、status、resume_phase、stop_mode（NONE/DRAIN/FORCE）、completion_reason、baseline_evaluation_id、evaluation_spec_hash、audit_spec_hash、min_improvement_bps、best_candidate_id / best_evaluation_id / best_score_i、version | best 三字段同时为空或同时非空；version 随研究状态事务递增。 |
| runs（控制/预算） | controller_generation、budget_limit、confirmed_tokens、held_tokens、accounting_state | 额度均非负；研究结束与费用对账完成分别表示。 |
| epochs | run_id、epoch_no、status、snapshot_version、snapshot_event_seq、context_hash、plan_hash、advisor_invocation_id | UNIQUE(run_id, epoch_no)；记录 Advisor 实际看到的证据快照。 |
| assignments | epoch_id、worker_slot、branch_id、mode、spec_hash、max_trials、trials_created、status、end_reason | UNIQUE(epoch_id, worker_slot)；同 Epoch 的 Branch 不重复分配；默认 max_trials=3。 |
| branches | run_id、base_candidate_id、head_candidate_id / head_evaluation_id / head_score_i、status、version | Head 三字段一起更新；切方向创建新 Branch，旧 Branch 保留。 |
| trials | run_id、assignment_id、branch_id、trial_no、base_candidate_id、state、accepted_attempt_id、result_candidate_id、evaluation_id、finalization_hash | UNIQUE(assignment_id, trial_no)；base 创建后不可变；一个 Trial 最多接受一个 Candidate。 |
| trial_attempts | trial_id、generation、controller_generation、owner、lease_deadline、state、sandbox_id、context_hash | UNIQUE(trial_id, generation)；每次物理重试使用新会话、新目录。 |
| candidates | run_id、parent_candidate_id、origin_trial_id、origin_attempt_id、artifact_hash | 正式候选 parent 必须等于 Trial.base；内容与来源不修改。 |
| evaluations | run_id、candidate_id、purpose（BASELINE/SEARCH/FINAL_AUDIT）、request_key、evaluation_spec_hash、job_state、started_at、active_generation、verdict、score_i、metrics_hash | request_key 唯一；SEARCH 才绑定 Trial；BASELINE 绑定 Run；FINAL_AUDIT 绑定 audit_record；DONE 后 verdict、score 和结果产物不可更改；主动复测创建新 job。 |
| evaluation_attempts | evaluation_id、generation、controller_generation、owner、lease_deadline、state、result_hash、error_kind | UNIQUE(evaluation_id, generation)；只有当前 attempt 可提交正式结果。 |

| 辅助实体 | 关键字段与唯一性 |
| --- | --- |
| command_receipts | command_id 主键、command_type、request_hash、result_json；请求摘要和处理结果与业务写入同事务提交。 |
| model_calls | call_id 主键、role、owner_attempt_id、controller_generation、request_hash、reserved_tokens、state、provider_request_id、raw_usage_json。另存 budget_scope_id、trial_id 或 advisor_invocation_id（恰一归属）；物理重试新 call_id，归属 scope 不变。 |
| usage_ledger | call_id 唯一结算业务键、规范化 input/output/cached_input、receipt_hash；修正采用显式对账流程，不重复结算或静默覆盖。 |
| events | seq、run_id、entity_id、type、payload、command_id；与对应状态更新同事务追加。一个命令可以产生多条事件，幂等性放在 command_receipts。 |
| advisor_invocations | id、epoch_id UNIQUE、state、active_generation、context_hash、snapshot_version、response_hash、plan_hash、format_repairs_used、replans_used、terminal_reason；每 Epoch 唯一逻辑规划，预算与修复次数跨 attempt 保存。 |
| advisor_attempts | invocation_id、generation、controller_generation、owner、lease_deadline、state；UNIQUE(invocation_id,generation)；新会话重试不生成新逻辑额度。 |
| budget_scopes | id、run_id、kind（TRIAL/ADVISOR）、owner_id、limit_tokens、confirmed_tokens、held_tokens；UNIQUE(kind,owner_id)，Trial/Invocation 建立时同步创建。 |
| audit_records | audit_id、run_id UNIQUE、final_candidate_id、export_manifest_hash、audit_spec_hash、evaluation_id UNIQUE、status、verdict、failure_kind；搜索结束时冻结身份；不持有晋升权限。 |

```text
CREATE UNIQUE INDEX ux_active_trial_per_branch
ON trials(branch_id)
WHERE state IN (
  'PENDING', 'RUNNING', 'CANDIDATE_READY', 'EVALUATING'
);

CREATE UNIQUE INDEX ux_assignment_trial
ON trials(assignment_id, trial_no);
CREATE UNIQUE INDEX ux_trial_attempt
ON trial_attempts(trial_id, generation);
CREATE UNIQUE INDEX ux_eval_attempt
ON evaluation_attempts(evaluation_id, generation);
CREATE UNIQUE INDEX ux_eval_request
ON evaluations(request_key);
CREATE UNIQUE INDEX ux_usage_call
ON usage_ledger(call_id);
```

候选与 Run 存在循环引用时，创建 Run 先不设置 best，再注册 baseline 并完成评估。SQLite 每个连接启用 foreign_keys=ON；采用 WAL、synchronous=FULL 与有限 busy_timeout。WAL 支持读写并发，但同时只有一个写入者且依赖本机存储；FULL 在提交时同步 WAL。[SQLite WAL](https://sqlite.org/wal.html) 单写入队列执行短事务，BEGIN IMMEDIATE 的争用须有界处理。[SQLite 事务](https://sqlite.org/lang_transaction.html) 数据库事务内禁止网络 await、模型调用和评估执行。

目标环境探针先运行 `python scripts/dev.py doctor --target`，记录 Python 实际 sqlite_version；要求含官方 WAL-reset 修复的版本：3.51.3 及以后，或 3.44 分支的 3.44.6+、3.50 分支的 3.50.7+。[SQLite WAL-reset 修复](https://sqlite.org/wal.html#walresetbug) 版本不足时停止相关多连接写入/Checkpoint 验收，升级后重跑。Checkpoint 与写入由同一控制器协调。

## 3 生命周期与调度屏障

| 对象 | 状态转移与语义 |
| --- | --- |
| Run | CREATED → RUNNING；CREATED/RUNNING → PAUSING → PAUSED；resume 按 resume_phase 回 CREATED 或 RUNNING；CREATED/RUNNING/PAUSING/PAUSED → STOPPING → COMPLETED；不可恢复故障 → FAILED。 |
| Epoch | PLANNING → READY → EXECUTING → CLOSED；规划失败／停止可直接 FAILED/CANCELLED。暂停保留 PLANNING/READY/EXECUTING；无 Assignment 的规划也必须有终结路径。 |
| Assignment | READY → RUNNING → DONE；取消/失败以 CANCELLED/FAILED 结束；end_reason 记录 MAX_TRIALS、BUDGET、STOPPED 等。 |
| Trial | PENDING → RUNNING → CANDIDATE_READY → EVALUATING → COMPLETED；无候选执行失败或评估基础设施耗尽 → FAILED；未启动任务撤销或 force 取消任何非终态 Trial → CANCELLED。 |
| Worker Attempt | 领取时创建 ACTIVE；接受候选后 SUCCEEDED；超时/失效为 EXPIRED 或 FAILED。重试先终结旧 attempt，再将 Trial 回到 PENDING。 |
| Evaluation Job | QUEUED → RUNNING → DONE；基础设施异常可回 QUEUED；重试耗尽 → FAILED；显式撤销 → CANCELLED。 |
| Evaluation Attempt | 每次物理执行独立；成功、基础设施失败或失效后终结。重试递增 generation，不复用旧执行权。 |
| Advisor Invocation | PLANNED → REQUESTING → PLAN_RECEIVED → COMMITTED；格式修复／过期重规划可回 PLANNED；耗尽 → FAILED，停止 → CANCELLED。响应内容先落不可变 artifact，再以当前 attempt 记录。 |
| Final Audit | PENDING → RUNNING → PASSED/REJECTED/INCONCLUSIVE；搜索结束后一次逻辑审计，可有最多 2 次设施重试。候选不正确立即 REJECTED，不换候选重测。 |

Evaluation 的 job_state 与 verdict 分离。DONE 才有 verdict：VALID_SCORED、BUILD_FAIL、INCORRECT、CANDIDATE_TIMEOUT、CANDIDATE_RESOURCE_LIMIT。后四类是有效研究反馈，Trial 仍可 COMPLETED，但不更新 Head/Best。INFRA_ERROR 是 attempt 的 failure_kind，不是候选成绩；每个 job 最多初次执行加 2 次基础设施重试，耗尽后 job FAILED、Trial FAILED。

PAUSING 禁止新 Trial、领取 PENDING 和新 Advisor 请求；当前 Trial 在原逻辑累计预算内继续，baseline 可排空。已发 Advisor 请求可 RecordAdvisorResponse 至 PLAN_RECEIVED，既不修复也不 CommitPlan。暂停屏障要求无活动 baseline/Trial/Evaluator/Advisor attempt、无已接受结果待 finalize，保留 PLANNED／PLAN_RECEIVED、PENDING 及 resume_phase 后进入 PAUSED。恢复初始化回 CREATED；规划或执行回 RUNNING。DRAIN 停止取消规划、PENDING 与未创建配额，排空已开始 Trial／baseline，随后关闭或取消 Epoch。在 STOPPING 中只有 DRAIN 允许晋升；PAUSING 也允许已开始 Trial 排空晋升；FORCE 绝不允许。 resume_phase 枚举为 INITIALIZING、READY_TO_RUN、PLANNING、EXECUTING。baseline 从未 claim 时 pause 直接保留 QUEUED job 并以 INITIALIZING 进入 PAUSED；DRAIN stop 则 CANCELLED 并以 NO_CANDIDATE 导出。baseline 首次 claim 已提交则属于在途，可在 PAUSING／DRAIN 有界重试与初始化。

下一 Trial 惰性创建，base 取当前 Head；Epoch Barrier 检查所有 Assignment 终态、剩余 slots 已处置、无非终态 Trial/job。规划中的 stop 直接将 invocation 与无 Assignment 的 Epoch CANCELLED，不能因空集合误判规划成功。CommitPlan 成功前不存在部分 Assignment；恢复看到 COMMITTED/READY 则使用已提交计划，不再调用 Advisor。暂停留存的 PLAN_RECEIVED 在 resume 时重新校验 snapshot_version；失效则记录 STALE_SNAPSHOT，最多一次重规划，仍共用原 invocation 额度。 规划请求超时按可信网关分类并结算／保留 UNKNOWN，终结当前 attempt；PAUSING 下回 PLANNED 但不发送，随后可达 PAUSED。stop 撤销规划 attempt，迟到响应只允许费用对账，不接受计划。 Advisor 格式修复／重规划耗尽时 invocation、Epoch 和 Run 均 FAILED（ADVISOR_PLAN_EXHAUSTED）；设施耗尽为 ADVISOR_INFRA_EXHAUSTED。逻辑规划 scope 预算不足则 invocation FAILED、Epoch CANCELLED、Run COMPLETED，reason=SCOPE_BUDGET_EXHAUSTED；不得开新 Epoch 绕过该停止条件。

## 4 命令幂等性与事务前置条件

公共命令信封包含 schema_version、command_id、type、run_id、payload；仅依赖快照的规划操作在 payload 中携带 expected_version。数据库 receipt 可将 type 存为 command_type。request_hash 使用规范化 JSON 计算，不包含每次重试都会变化的发送时间。业务错误返回明确错误码，不能使用可能被 Python 优化关闭的 assert 承担生产校验。

```text
BEGIN IMMEDIATE;
receipt = lookup(command_id)
if receipt exists:
    require(receipt.request_hash == canonical_hash(cmd),
            'IDEMPOTENCY_CONFLICT')
    return receipt.result_json

validate_business_preconditions(cmd)
result = apply_state_change(cmd)
append_events(cmd, result)
insert_receipt(cmd.id, canonical_hash(cmd), result)
COMMIT;
```

换一个 command_id 不得绕过业务唯一性。已完成 Trial 收到 FinalizeTrial 时，还需比较已记录的 candidate、evaluation 与结果 hash；一致返回原结果，不一致返回 RESULT_CONFLICT。command_receipts 的主键处理传输重试，Trial.finalization_hash 和各唯一索引处理业务重复。

| 命令 | 关键前置条件与原子写入 |
| --- | --- |
| CreateRun / StartRun / InitializeBaseline | 注册唯一 baseline job；恢复同 job；初始化只允许 BASELINE，且非 FORCE；重复初始化返回原结果，不重新置 Best。 |
| OpenEpoch / ClaimAdvisor | Run RUNNING；创建唯一 invocation 及 budget_scope；Claim 递增 attempt generation，原修复／重规划次数不清零。 |
| RecordAdvisorResponse / CommitPlan | 当前 controller/attempt/lease；先保存响应再落 PLAN_RECEIVED；Commit 仅 Run RUNNING、当前快照、完整合法计划，一次生成所有实体；唯一 epoch/invocation 保证业务幂等。 |
| CreateTrial | Run RUNNING；Assignment 有剩余 slots；Branch ACTIVE 且无非终态 Trial；原子读取 head ?? base、创建 PENDING Trial 及持久 budget_scope 并递增 trials_created。 |
| ClaimTrial | Trial PENDING、Run RUNNING、重试额度足够；创建新 generation 的 attempt、设置 owner/lease，Trial RUNNING；提交后才启动容器。 |
| RenewLease | 匹配 controller/attempt/generation/owner；attempt ACTIVE、尚未过期；只能延长当前代次租约。 |
| SubmitCandidate | CAS 已持久；匹配有效 Worker attempt/lease、Trial RUNNING、归属一致；同一事务创建 Candidate 和 QUEUED Evaluation job，绑定 accepted_attempt/evaluation，Trial CANDIDATE_READY，并结束 Worker 写权限。 |
| ClaimEvaluation | 绑定 job QUEUED、Candidate 可校验、按 purpose 检查授权；BASELINE 首次 claim 仅 CREATED，已有 started_at 的 job 也允许 PAUSING／DRAIN 重试，SEARCH 允许既有工作 drain，FINAL_AUDIT 仅走审计授权；创建独立 eval attempt/generation，job RUNNING；首次将 Trial CANDIDATE_READY→EVALUATING，重试时保持 EVALUATING。 |
| RecordEvaluation | 可信 Evaluator supervisor 返回；job 未终态，attempt/controller/generation 当前且 lease 有效；持久结果后写 DONE/verdict 或基础设施重试状态。 |
| FinalizeTrial | Trial EVALUATING、绑定 job DONE、Candidate/Run/spec 一致；purpose=SEARCH、stop_mode!=FORCE；原子更新 Head/Best、Trial 终态、事件和 receipt。 |
| CloseEpoch | Assignment 均终态、剩余 slots 已明确处置，无非终态 Trial/job；关闭 Epoch；若停止则推进 Run COMPLETED。 |
| ForceStop | 同一事务设置 stop_mode=FORCE、递增 controller_generation、取消所有非终态 Trial/规划/未完成 baseline 与 SEARCH job、撤销全部 attempt；DONE 结果保留但未完成 Trial 仍取消，跳过剩余配额并终结 Epoch/Run。提交后终止所属进程；重复请求不重复撤销。 |
| FreezeFinal / RecordAudit | Run 终态且无活动搜索；冻结唯一 final_candidate 与 manifest；审计提交仅改 audit_record 与事件，不改 Run best／Branch／Trial，不进入模型可读反馈。 |

StateStore 是唯一变更入口。Worker 无数据库和正式分数写权限；Agent 输出只构成提案。Evaluator 的正式结果由沙箱外可信 supervisor 形成，不能把候选 stdout 自报的分数当作权威结果。

## 5 评分口径与 FinalizeTrial

SEARCH 和 BASELINE 使用相同计时口径：独立进程／输入预热，正式样本均为全新进程一次调用，次数按 [T-30](04-implementation-validation.md) 校准并冻结；可信 supervisor 的 monotonic_ns 从输入帧发送前到完整限长输出帧接收后计时，包含 IPC 与序列化。输入此前不可见；各样本之间无可写共享状态。令样本吞吐量为 record_count×10^9/elapsed_ns，以精确有理数选中位数再 floor(×1000) 得 score_i；保存计时原值、输入清单身份、process_instance_id、单位、输出 hash、环境指纹。elapsed_ns<=0、非法值、溢出、错误输出均不得 VALID_SCORED；计时不接受候选自报。

提升条件统一为 new−old≥max(1,(abs(old)×min_improvement_bps+9999)//10000)，bps 为 Run 固定整数，默认 100 即 1%。新 Branch 首个有效 SEARCH 结果无提升门槛；Head 与 Global 独立比较。DONE 成绩不可改写，主动复测新建 job；BASELINE 仅用于初始化，FINAL_AUDIT 只记录审计，均不走 Trial 晋升。Global Best 为按阈值晋升的 incumbent，raw 最大值另报；近似结果完成顺序可能影响选择，MVP 保留此限制。

```text
def finalize_trial(cmd):
    with store.immediate_transaction() as tx:
        replay = tx.validate_command_replay(cmd)
        if replay is not None:
            return replay
        t, e, branch, run = tx.load_bound_entities(cmd)
        if t.state == 'COMPLETED':
            return tx.return_if_same_finalization(t, e, cmd)
        require(t.state == 'EVALUATING')
        require(e.job_state == 'DONE')
        require(e.purpose == 'SEARCH')
        require(run.stop_mode != 'FORCE', 'RUN_FORCE_STOPPED')
        require(e.id == t.evaluation_id)
        require(e.candidate_id == t.result_candidate_id)
        require(e.run_id == run.id == t.run_id)
        require(e.evaluation_spec_hash == run.evaluation_spec_hash)
        require(run.status in {'RUNNING', 'PAUSING', 'STOPPING'})
        require(branch.status == 'ACTIVE')
        # 此事务与 ForceStop 串行；已 COMPLETED 的幂等重放不重新晋升
        if e.verdict == 'VALID_SCORED':
            tx.promote_branch_by_policy(branch, e)
            tx.promote_global_by_policy(run, e)
        tx.complete_trial_and_record_hash(t, e)
        return tx.commit_result_events_and_receipt(cmd)
```

RecordEvaluation(DONE) 与 FinalizeTrial 是两个提交点。force 先提交：所有未完成 Trial 即使绑定 DONE 评估也 CANCELLED，后续 finalize 返回 RUN_FORCE_STOPPED／STATE_CONFLICT；DONE 不变，只保留历史证据。finalize 先提交：该成果保持，force 不回滚已完成 Trial。恢复先检查终态与 stop_mode，再决定是否 finalize。Worker TTL 在候选接受后不再参与 finalize；未知用量独立对账，不阻塞已授权结果。

```text
UPDATE runs
SET best_candidate_id = :candidate_id,
    best_evaluation_id = :evaluation_id,
    best_score_i = :score_i,
    version = version + 1
WHERE id = :run_id
  AND status IN ('RUNNING', 'PAUSING', 'STOPPING')
  AND stop_mode <> 'FORCE'
  AND evaluation_spec_hash = :spec_hash
  AND (best_score_i IS NULL OR :score_i >= :threshold_i);
```

threshold_i 在同一 BEGIN IMMEDIATE 事务中从旧 best 与 runs.min_improvement_bps 计算为 old+max(1,(abs(old)*bps+9999)//10000)，用 Python 整数并检查入库范围；不从客户端接收阈值。Branch 同理，空 Head 直接接受。bps 及测量协议进入 evaluation_spec_hash；改变参数需新 Run。检查 UPDATE 行数后记录晋升事件；正式 Evaluator 并发为 1。

## 6 租约与控制代次与恢复权限

Worker、Advisor、Evaluator 均有独立 owner、lease、attempt generation；重新领取必须递增代次。合法条件 deadline>now，过期 deadline<=now；续租不得复活过期 attempt。命令同时校验 controller_generation。时钟来自可信 supervisor；模型调用发送前再次校验代次和取消状态。Advisor attempt 耗尽最多初次＋2 次基础设施重试，格式修复最多 1 次，过期快照重规划最多 1 次，计数属于逻辑 invocation，不随重启清零。

MVP 运行时用当前 controller 的单调时钟判断 lease；持久 wall-clock 时间仅用于审计。重启后不比较旧进程的单调 deadline：先取得本机 Run 级排他 OS 锁，再在事务中递增 controller_generation，使旧控制代次失去新调用和结果写入权限。第二个 controller 取不到锁就拒绝启动。此协议限定本机本地文件系统，不宣称多机协调。

恢复只清理带匹配 run_id/controller_generation/attempt_id 标签的本 Harness 容器。MVP 不收养旧 Worker／Advisor／Evaluator 执行权；撤销后终止所属沙箱。DB 已接受候选继续同 job；已接受 Advisor 响应可验证并 CommitPlan，不必重调模型。尚未被 DB 接受的旧响应不能改变计划，可信 usage 仍须入账。

Fencing 不会撤销已经发往模型服务的请求，也不会自动停止旧进程。模型网关在每次 dispatch 前检查控制/attempt 代次，拒绝旧 Agent 发新请求；已发送的请求保留预算预留直到对账。评估重试同样必须验证 eval_generation，避免前一次慢执行迟到并覆盖后一次结果。

## 7 模型调用预留与 UNKNOWN 用量

每次真实模型请求独立 call_id，绑定不可变 budget_scope_id。Worker scope 是逻辑 trial_id；Advisor scope 是每 Epoch 唯一逻辑 invocation_id，不是物理 API 调用。原请求、工具续轮、失败、格式修复、重规划和跨 attempt 重发全部累计到同 scope；scope 额度在创建时冻结，不能以新会话／attempt 绕过。规范 total=input_tokens+output_tokens；cached_input 为 input 子集，reasoning 包含关系由 adapter 明示，原始 provider usage 留存。

| 阶段 | 事务与恢复语义 |
| --- | --- |
| RESERVED | 校验当前角色、Run/attempt/fence、scope 归属。R=input_upper_bound+output_cap；同一事务同时验证 Run.confirmed+Run.held+R<=Run.limit 与 Scope.confirmed+Scope.held+R<=Scope.limit，成功后两者 held+=R 并插入 call。 |
| DISPATCH_INTENT | 发送前事务复查授权并持久记录 DISPATCH_INTENT；以该提交为调用已开始的线性化点，暂停前仅 RESERVED 的 Advisor 请求释放为未发送并回 PLANNED，禁止新发。随后发送；远端 API 无原子提交保证，崩溃可能未知是否收费。attempt 更换不释放该调用额度。 |
| SETTLED | 可信 U 到达，唯一 call 账本事务同步在 Run 与 Scope held-=R、confirmed+=U；重复 receipt 无影响，不同 receipt 进入显式冲突对账。 |
| UNKNOWN | 超时／取消／崩溃无法确定 U 时保留同一 R，仍包含在两层 held，不再额外加一次 unknown；重发新 call_id 重新预留。 |
| RELEASED_UNSENT | 仅 RESERVED 且有可信未 dispatch 证据才同步释放两层 R；杀死进程不是未收费证据。 |
| 范围耗尽 | Scope 不足返回 SCOPE_BUDGET_EXHAUSTED；不新发请求，已有候选可评估，否则 Trial FAILED 或 invocation FAILED，并记录原因。Run 总额不足走 BUDGET_EXHAUSTED 的停止／排空规则。 |

预算结算不依赖 Trial／invocation 的终态或 attempt 有效性。Run 可 COMPLETED 而 accounting_state=OPEN；CLI 显示 confirmed、held_reserved、held_unknown 与 available，其中 held=held_reserved+held_unknown。scope 同样可审计，未知不填零、不重复扣减。无法对账继续保留 held；估算若未来支持须标 ESTIMATED，不混入 confirmed。所有 scope confirmed／held 汇总应与 Run 模型用量一致。

严格上限依赖所有请求都经过网关，而且 input_upper_bound/output_cap 真正覆盖服务端计费。只在会话结束报告用量、内部自行重试的黑盒 Agent CLI 属于 soft budget adapter。实际 U>R 时记录 BUDGET_BOUND_BREACH 并停止新授权，真实用量不能截断。MVP 优先实现可逐请求门控的 adapter，并通过模拟 provider 验证预算协议。

## 8 产物提交与崩溃一致性与 Checkpoint

MVP 以内容寻址 bundle 为候选代码权威产物，Git 可作导出用途。manifest 固定相对路径、字节 hash、size、可执行位与格式版本；去除 mtime/uid/gid 等非语义差异。拒绝路径逃逸、绝对路径、symlink/hardlink/device 等不受支持条目。完整 bundle 可独立重建工作区，避免依赖已经丢失的父 diff。

- 先停止 Worker 新的模型/工具行为，并等待或终止子进程，冻结工作区；不能在 Worker 继续写入时复制候选。

- 写同一文件系统的临时 bundle，计算并复核 hash；fsync 文件后原子发布到 CAS，再 fsync 对象目录及新创建的必要父目录。

- 已存在相同 hash 时验证后复用，禁止覆盖不可变对象；只有发布完成后才提交数据库 Candidate 引用。

- DB 事务失败可留下 orphan；DB 提交成功后必须能恢复对应对象。MVP 不在 Run 活跃期间 GC，离线 GC 取得排他锁并保留全部 DB/backup 引用。

- 恢复发现已引用对象缺失或 hash 错误，Run FAILED，reason=ARTIFACT_CORRUPT；保留证据，不自动换成另一代码版本。

Checkpoint 是可恢复的 DB 快照及其引用产物集合：使用 SQLite backup API 创建一致快照，再解析该快照的全部对象引用，复制/验证 CAS 对象并生成备份 manifest。禁止仅复制运行中的 main.db 而遗漏 WAL；WAL checkpoint 本身不等于 Run 备份。SQLite 和 fsync 的持久性仍依赖底层文件系统的实际保证。

Advisor 证据在短读事务获取 run.version／event_seq，生成不可变 context。OpenEpoch／invocation 绑定 context_hash、prompt_version、model_config_hash。响应 artifact 先落盘，RecordAdvisorResponse 再以当前 attempt 写 response_hash/plan_hash 与 PLAN_RECEIVED；CommitPlan 后 invocation COMMITTED、Epoch READY、Assignment／Branch 与事件同事务提交。崩溃若只有响应文件而无 DB 引用，文件只是 orphan，不能自动当成有效计划。格式修复与重规划不得覆盖旧响应证据。

## 9 故障恢复矩阵

新进程首次取得 Run 排他锁后建立新的 controller_generation；同一进程重复 recover_run 复用本代次，不再反复撤销自己的任务。恢复校验引用产物、识别旧执行与未知调用，然后按持久状态处理。重复调用必须收敛，不能多创建有效 Trial、多接受评估或重复扣账。

| 持久状态或崩溃点 | 恢复动作 |
| --- | --- |
| Run CREATED，baseline job QUEUED/RUNNING | 校验 starter；撤销旧 evaluator，继续同 baseline_evaluation_id／request_key，新 attempt；不调用模型。 |
| Run CREATED/PAUSING/STOPPING，baseline job DONE | 非 FORCE 按 InitializeBaseline 完成一次初始化，并按 pause／drain 分支收敛；FORCE 仅保留 DONE，不设置 Best。 |
| baseline job FAILED 或无效 verdict | FAILED，记录 BASELINE_INVALID 或 BASELINE_INFRA_EXHAUSTED；不能默认 score=0。 |
| Epoch PLANNING，invocation PLANNED | RUNNING 才 claim；暂停保持；停止 CANCELLED。 |
| invocation REQUESTING，旧 attempt／发送意图 | 撤销旧 attempt；逐 call 对账，未知保留 held；允许时按原预算／次数用新 attempt，新会话；不假定上次免费。 |
| invocation PLAN_RECEIVED，尚未 CommitPlan | 校验 artifact 和 snapshot；RUNNING 时幂等 CommitPlan；PAUSED 保留；STOPPING/FORCE 取消；失效按有界原 scope 重规划。 |
| invocation COMMITTED，Epoch READY/EXECUTING | 已提交计划为权威；不再次调用 Advisor／创建 Assignment；恢复剩余配额。 |
| 临时 bundle 或 CAS 完整但 DB 未引用 | 半对象清理、完整 orphan 保留；不能自动宣称 Trial／计划完成。 |
| Trial PENDING | RUNNING 才 claim；暂停保留，停止取消。 |
| Trial RUNNING，旧 controller/lease | 撤销并清理旧沙箱；在持久重试次数、逻辑 scope 余额内回 PENDING，新会话；耗尽明确 FAILED。 |
| Trial CANDIDATE_READY | 校验已接受 bundle，继续唯一 evaluation job；不重新生成候选。 |
| Trial EVALUATING，job DONE | 先检查 Run.stop_mode、Trial 终态：FORCE 则 CANCELLED；否则合法 drain 可 finalize，不重评。 |
| Trial EVALUATING，job QUEUED/RUNNING | 非 FORCE 则同 job、同 Candidate、新 eval_generation，有界重试；FORCE 取消。 |
| job FAILED，设施重试耗尽 | Trial FAILED/EVAL_INFRA_EXHAUSTED；不产生伪造分数。 |
| finalize 或 ForceStop 事务前后崩溃 | DB 全提交／全回滚；按持久 stop_mode 和终态收敛，不能把已取消 Trial 再 finalize。 |
| Run PAUSING/PAUSED | 检查 baseline、Advisor、Trial、Evaluator 暂停屏障；保留 resume_phase、计划与配额；PAUSED 不自动发新调用。 |
| Trial／Run 已终态 | 不重新研究；允许可信 usage 对账及已授权独立审计，不改历史 Best。 |
| DISPATCH_INTENT/UNKNOWN call | 两层 scope/Run 都保留预留；重发必须新 call_id 与双层准入。 |
| Final Audit PENDING/RUNNING | 使用已冻结 candidate/manifest/audit_spec，同审计 job 有界设施重试；候选失败不换候选，不回流搜索。 |

旧评估实际完成但结果尚未进 DB 时，恢复可能再次执行同一候选。系统承诺结果接受幂等，不承诺物理评估只运行一次。Worker 代码修改已完成但尚未被接受时也存在同样边界；先持久化再引用降低损失范围，不能消除所有未提交工作损失。

## 10 实现验收与不变量测试

以下用例随对应状态协议实现验收。fake Worker/Evaluator/provider 用于重复触发故障；真实集成按 [早期探索](04-implementation-validation.md) 尽早验证。故障注入覆盖文件发布、数据库提交和外部请求三个边界。

| 用例 | 必须观察到的结果 |
| --- | --- |
| 两个候选乱序返回，分数 110000/120000 | 两者均满足当前提升门槛时，最终 Global 为 120000；不存在覆盖倒退。 |
| Global=90000，新分支首个=85000 | Branch Head=85000，Global 不变；下一 Trial.base 为该 Head。 |
| old=100000，new=100999/101000 | 前者不提升，后者提升；first branch head 不套用门槛。 |
| 同 key 同 payload / 同 key 不同 payload | 前者返回相同结果；后者 IDEMPOTENCY_CONFLICT；新 key 不能重复完成同一业务。 |
| Worker 过期后提交 / 接受后 TTL 到期 | 前者 STALE_CLAIM；后者仍能完成评估与 finalize。 |
| eval attempt 1 比 attempt 2 更晚返回 | 旧代次结果不覆盖已接受的 verdict/score。 |
| 暂停/DRAIN 停止期间有效候选返回 | 可更新 Head/Best；暂停保留 PENDING、停止取消 PENDING；不创建新 Trial；剩余 slots 有明确去向。 |
| 一条 Trial 完成，Assignment 还有 slots | Epoch 不会提前 CLOSED；resume 可继续惰性创建下一条。 |
| 调用超时后重发，后来两份 usage 均到达 | 两个物理 call 都计费；重复 receipt 不重复结算；UNKNOWN 额度不提前释放。 |
| CAS 发布与 DB 提交前后分别崩溃 | 最多产生 orphan；已接受 Candidate 可恢复；发现悬空引用时明确失败。 |
| finalize 前后崩溃、重复 recover、双 controller | 无半完成事务、无重复成果/结算；第二 controller 被排他锁拒绝。 |
| force 与 DONE/finalize 两种提交顺序 | force 先则 Trial CANCELLED、Best 不变；finalize 先则成果保留；重启后同结果。 |
| CREATED 基线与 PLANNING 各落盘点崩溃 | 同 baseline job、同逻辑 invocation 收敛；响应已入库无需重调；暂停计划恢复后提交一次。 |
| Scope 额度小于 Run 剩余额，跨 attempt 重试/修复 | Scope confirmed+held 限制仍生效；UNKNOWN 不释放，结算两层一致。 |
| bps=250、old=100000、new=102499/102500 | 前者拒绝、后者晋升；bps=0 仍至少提升 1；配置变更拒绝原 Run。 |
| Audit 不正确或设施耗尽 | REJECTED/INCONCLUSIVE；不晋升、不换候选、不反馈模型，不发布已审计成功。 |

实现完成的核心证据是：每个 Best 可定位精确代码和正式评估，每次失败／重复调用可定位真实成本，每个初始化／规划／执行状态有可解释恢复路径。FreezeFinal 在搜索终态原子冻结 final_candidate_id、export_manifest_hash、audit_spec_hash，建立一个独立 FINAL_AUDIT job；只能写 audit_record，禁止写 Branch／Trial／Best。审计正确且性能测量有效为 PASSED；候选错误为 REJECTED；设施重试耗尽为 INCONCLUSIVE。报告显示搜索成绩与审计成绩各自的数据／环境身份，不直接混排；失败只发布明确未验证的研究记录，不能悄悄选择另一候选继续试。 若基线从未有效且 Best 为空，则不创建审计，导出 NO_CANDIDATE 与失败／强停原因；不能虚构最终成果。

## 11 技术依据

- [SQLite Write-Ahead Logging](https://sqlite.org/wal.html)：WAL 并发、本机存储和同步语义。
- [SQLite Transaction](https://sqlite.org/lang_transaction.html)：事务控制与写入争用语义。
