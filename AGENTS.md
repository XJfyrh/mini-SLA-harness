# 常驻开发规则

- 从 [README](README.md) 进入；按任务阅读 [架构](docs/architecture.md)、[测试](docs/testing.md) 或 [依赖维护](docs/development.md)，不复制其细节。
- 本仓库按 [设计范围](docs/scope.md) 推进；保持 fake 确定性，不读凭据或接真实模型 API，不把基础设施检查写成 M0 协议验收。
- 保留用户文件与修改。使用独立分支、阶段提交，提交消息用简体中文 Conventional Commits；未获授权不执行远端操作。
- 标准库优先；第三方工具纳入 `requirements-dev.lock`。生成物进入忽略的 `artifacts/` 或 `dist/`。
- 新行为验证实际输出和副作用；仓库约束要有破坏规则会失败的负例。修改后执行 README 的完整 check 和 demo。
- 事实放在负责该主题的文档，其他位置链接过去。决策说明只记录真实取舍；不为机械修改新建流程或决策文档。
