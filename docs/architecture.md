# 当前架构

本页描述已运行的开发骨架。后续协议范围与设计入口由 [设计范围](scope.md) 负责。

## 运行路径

安装后的 `mini-sla` 和 `python -m mini_sla_harness` 进入同一个 CLI。`demo` 顺序调用固定 provider、写入 demo 专用 SQLite 表、用新连接回读，再生成稳定的 JSON 文件。运行时使用 Python 标准库。

| 模块 | 当前职责 |
| --- | --- |
| [cli.py](../src/mini_sla_harness/cli.py) | 参数、摘要/JSON stdout、错误退出码 |
| [fake.py](../src/mini_sla_harness/fake.py) | 三个固定请求/响应；未知请求显式失败 |
| [store.py](../src/mini_sla_harness/store.py) | `demo_records` 表、SQLite WAL、事务写入与只读回读 |
| [demo.py](../src/mini_sla_harness/demo.py) | 串联流程、核对持久化结果、写 `result.json` |

## 数据与失败行为

相同记录重复提交不会增加行数；同一 case_id 内容冲突时回滚该批写入并退出失败。已有数据库不会被清空。fixture 变化可指定新的输出目录。

`result.json` 是可重建产物，成功运行会重写；没有时间和机器路径，重复运行可逐字节对比。数据库校验失败时不会重写 JSON。它与数据库之间没有跨文件原子事务：JSON 写入失败时数据库可能已提交，下一次运行可再次回读。

CLI 参数错误退出 2；文件系统、SQLite 或 demo 校验错误退出 1；成功退出 0。这些错误显示诊断，不输出 traceback。

## 开发工具边界

[dev.py](../scripts/dev.py) 负责跨平台环境和检查入口；[repo_check.py](../scripts/repo_check.py) 负责本地文档链接与 CLI 声明检查。[package_check.py](../scripts/package_check.py) 负责 wheel 的隔离安装验收。这些脚本不随运行包安装。测试方法由 [测试说明](testing.md) 负责，依赖安装由 [开发环境](development.md) 负责。
