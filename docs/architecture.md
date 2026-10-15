# 当前架构

本页描述已运行的 M0 离线内核和开发基础设施。后续协议范围与设计入口由 [设计范围](scope.md) 负责。

## 运行路径

安装后的 `mini-sla` 和 `python -m mini_sla_harness` 进入同一个 CLI。`demo` 顺序调用固定 provider、写入 demo 专用 SQLite 表、用新连接回读，再生成稳定的 JSON 文件。运行时使用 Python 标准库。

| 模块 | 当前职责 |
| --- | --- |
| [cli.py](../src/mini_sla_harness/cli.py) | 参数、摘要/JSON stdout、错误退出码 |
| [fake.py](../src/mini_sla_harness/fake.py) | 三个固定请求/响应；未知请求显式失败 |
| [store.py](../src/mini_sla_harness/store.py) | `demo_records` 表、SQLite WAL、事务写入与只读回读 |
| [demo.py](../src/mini_sla_harness/demo.py) | 串联流程、核对持久化结果、写 `result.json` |
| [contracts.py](../src/mini_sla_harness/contracts.py) | JSON TaskSpec、Assignment 范围、规范化哈希、命令与可信进程内主体 |
| [artifacts.py](../src/mini_sla_harness/artifacts.py) | 白名单文件封存、同卷不覆盖发布、hash 校验和全新目录重建 |
| [state.py](../src/mini_sla_harness/state.py) | 权威事务、receipt/事件、基线与规划、预算、租约和强停；独立于 demo 表 |
| [m0.py](../src/mini_sla_harness/m0.py) | 固定 Agent/Evaluator/provider 行为，驱动实际协议和文件/进程，生成验收报告 |

## M0 协议路径

`task validate` 解析 JSON 契约并输出指纹；`m0-check` 使用公开小文件运行固定场景。每个场景拥有数据库和 CAS；Run 创建时绑定唯一 baseline job，合法基线初始化后才允许规划和 Trial。评估分数来自可信 fake Evaluator，M0 不执行候选程序。

StateStore 当前每库一个 Run，一个控制器实例持整个数据库的排他文件锁；Windows 使用字节范围锁，跨进程竞争实际拒绝。唯一写连接由进程内锁串行访问，命令在 `BEGIN IMMEDIATE` 中检查所属关系、代次和租约，再同步写事实、事件和 receipt；文件读取/发布在写事务外完成。只读快照使用新连接和短事务，并核对 Run、scope 与逐调用账本守恒。

Worker、Advisor 和 Evaluator 的执行记录共用 `attempts` 表，以 kind/object_id/generation 区分；每个逻辑对象最多三个 attempt，Advisor 格式修复与重规划另各限一次，均不重置 scope。`Principal` 是可信宿主进程内身份；公开 RPC、Windows named pipe 和容器权限还未实现。

双层额度在事务中同时预留。DISPATCH_INTENT/UNKNOWN 不能直接释放；cached input 是 input 子集。可信 usage 可在研究终态或旧代次后结算；重复 receipt 不重复入账，冲突显式失败，超出预留仍保留实际用量并阻断新授权。快照另给出 confirmed、held_reserved、held_unknown、available 与 OPEN/CLOSED。

force 事务先撤销执行权并取消未完成研究对象；DONE 评估保留，未 finalize 的 Trial 不得晋升。M0 的 OS 终止验证使用受控假进程；Linux 容器树的停止与恢复留给目标执行器验收。控制器重开验证已引用候选和规划对象，旧发送意图转 UNKNOWN，未接受的响应不能自动变成计划。暂停/停止/恢复目前用于协议状态验证；完整运行时恢复矩阵属于 M2。

CAS 使用规范化 JSON bundle，包含路径、内容 hash、size、显式非可执行标记和 base64 字节。拒绝路径逃逸、Windows 别名、硬链接和 reparse point；候选还须遵守所属 Assignment 的编辑范围。Windows 文件刷新和同卷发布已用于协议路径；控制器进程死亡测试不等同于断电持久性验收。

## Smoke 数据与失败行为

相同记录重复提交不会增加行数；同一 case_id 内容冲突时回滚该批写入并退出失败。已有数据库不会被清空。fixture 变化可指定新的输出目录。

`result.json` 是可重建产物，成功运行会重写；没有时间和机器路径，重复运行可逐字节对比。数据库校验失败时不会重写 JSON。它与数据库之间没有跨文件原子事务：JSON 写入失败时数据库可能已提交，下一次运行可再次回读。

CLI 参数错误退出 2；文件系统、SQLite 或 demo 校验错误退出 1；成功退出 0。这些错误显示诊断，不输出 traceback。

## 开发工具边界

[dev.py](../scripts/dev.py) 负责跨平台环境和检查入口；[repo_check.py](../scripts/repo_check.py) 负责本地文档链接与 CLI 声明检查。[package_check.py](../scripts/package_check.py) 负责 wheel 的隔离安装验收。[evidence.py](../scripts/evidence.py) 记录命令生命周期、日志和源码身份，[doctor.py](../scripts/doctor.py) 实测环境前置条件。这些脚本不随运行包安装。测试方法由 [测试说明](testing.md) 负责，依赖安装由 [开发环境](development.md) 负责。
