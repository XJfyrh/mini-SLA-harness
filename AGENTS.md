# 常驻开发规则

- 从 [README](README.md) 进入；按任务阅读 [当前架构](docs/architecture.md)、[测试](docs/testing.md) 或 [依赖维护](docs/development.md)，不复制其细节。
- 本项目的开发、修复、审查和设计调整使用 [作战手册](.agents/skills/playbook/SKILL.md)，遵循尽早暴露错误、取得真实反馈、敏捷轻量三条核心原则，按任务选择需要展开的方法。
- 涉及协议设计时，从 [设计索引](docs/design/README.md) 按任务阅读正式正文；[设计范围](docs/scope.md) 记录实现进度。真实集成按 [实施与验收](docs/design/04-implementation-validation.md) 的探索条件尽早验证；fake 用于可重复的协议与故障测试。
- 保留用户文件与修改。使用独立分支、阶段提交，提交消息用简体中文 Conventional Commits；未获授权不执行远端操作。
- 标准库优先；第三方工具纳入 `requirements-dev.lock`。生成物进入忽略的 `artifacts/` 或 `dist/`。
- 尽早暴露错误，反馈必须来自实际观察。先复现问题或验证关键假设，再扩展实现；新行为检查实际输出和副作用，仓库约束须有破坏规则会失败的负例。按 [开发指南](docs/development.md) 完成验证，交付时引用本次代码对应的结果与失败证据。
- 事实放在负责该主题的文档，其他位置链接过去。决策说明只记录真实取舍；不为机械修改新建流程或决策文档。
