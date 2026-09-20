# Herta Agent 分阶段任务计划

目标：按用户逐阶段授权实现 Windows 桌面 Agent，并提供可亲手复现的教程。

## 阶段
- [x] 检查输入文件、源码快照和实际许可证。
- [x] 追踪入口、Agent Loop、Tools、Context、Persona、Session、timeout/cancel。
- [x] 编写 docs/hermes-analysis.md、docs/architecture.md、docs/reuse-plan.md。
- [x] 补充手动复现步骤，核验源码引用和交付范围。
- [x] 汇报并停在 Phase 0，等待用户确认。

## 当前状态
Phase 0、Phase 1 与 Phase 2 已完成。用户确认 Ctrl+C 取消当前轮、保留会话并继续输入。实现保留原有学习注释，独立审查无阻塞问题；停在 Phase 2，等待下一阶段授权。

## Phase 2 任务
- [x] 检查当前代码、已有设计和用户未提交的学习注释，运行基线测试。
- [x] 确认取消交互与 Phase 2 具体设计。
- [x] 实现并测试 Registry、参数验证、工具执行和工具结果回填。
- [x] 验证 Windows 下的预算、超时、取消和历史配对。
- [x] 编写复现教程并停在 Phase 2。

## Phase 1 任务
- [x] 确认独立 Python 3.12+ 环境及最小依赖。
- [x] 实现消息、Provider、单步循环骨架、内存会话和教学 CLI。
- [x] 验证离线运行、HTTP 协议适配、失败与取消边界。
- [x] 编写逐文件复现教程，更新架构状态并停在 Phase 1。

Phase 1 不实现工具执行、Persona、RAG、FastAPI、Electron 或 SSE。

## Phase 0 范围（历史记录）
角色语料本阶段只检查，不整理、不生成 soul.md。原始材料保留原位。
只解压参考源码，不安装或运行 Hermes，不生成 Herta 业务代码。

## 错误记录
- 首次解压命令指定了尚不存在的工作目录，进程未启动；改为在已存在的项目根目录执行。
- rg 的 shell 路径通配符在当前 Windows 环境未展开；改为 rg -g 或明确文件名。
