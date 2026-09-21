# Herta Agent 分阶段任务计划

目标：按用户逐阶段授权实现 Windows 桌面 Agent，并提供可亲手复现的教程。

## 阶段
- [x] 检查输入文件、源码快照和实际许可证。
- [x] 追踪入口、Agent Loop、Tools、Context、Persona、Session、timeout/cancel。
- [x] 编写 docs/hermes-analysis.md、docs/architecture.md、docs/reuse-plan.md。
- [x] 补充手动复现步骤，核验源码引用和交付范围。
- [x] 汇报并停在 Phase 0，等待用户确认。

## 当前状态
phase-5-service已完成Task 1–7；本批Task 4–7及其142项完整回归/Ruff核验完成，提交并push后停止，不merge、不进入Task 8。Phase 4真实RAG效果仍待验收。

## Phase 5设计讨论
- [x] 阅读Phase 1–4实际代码、设计和roadmap，区分既定约定与未决项。
- [x] 分析服务边界、持久化提交点、Run生命周期、SSE与断连语义。
- [x] 用户选择A：partial仅SSE展示，不持久化、不恢复、不进入下一轮上下文。
- [x] 用户确认跨Session并行、同Session互斥、服务全局上限满额立即拒绝，不排队。
- [x] 用户已确认docs/phase-5-design.md整体设计。
- [x] 编写docs/phase-5-plan.md，按指定依赖顺序拆成12个可独立验证任务。
- [x] 用户授权创建phase-5-service并仅执行Task 1，已观察失败测试后实现。
- [x] Task 1最终测试/代码核验与交付；13项定向、106项全套及Ruff检查通过，停止，不进入Task 2。

## Phase 4 设计与资料准备
- [x] 阅读 Phase 1–3 架构、Persona 与现有角色材料，讨论检索目标与取舍。
- [x] 按用户决定锁定现有角色事实、人物关系、故事事件；不扩充语料。
- [x] 整理20个知识单元、来源manifest和28题评测集（dev17/check11）。
- [x] 完成 docs/phase-4-design.md、phase-4-plan.md，不写业务代码。
- [x] 静态核验JSON、唯一ID、预期证据引用、原始来源行号与SHA256。
- [x] 用户确认一个远程兼容Embedding适配器，独立配置，Key只读本地环境。
- [x] 完成Phase 4切分、索引、检索、Tool、评测和教学文档。
- [x] 回归、Ruff、独立局部审查及原始材料hash核验。
- [ ] 本地配置真实服务后验证合约、校准dev、冻结参数跑check及28题正式聊天。

## Phase 3 任务
- [x] 阅读 Phase 2 架构、Runtime 和完整角色语料及整理建议；重跑 42 项基线测试与 Ruff。
- [x] 确定 Persona 文件加载失败策略，完成最小设计。
- [x] 从原文形成带来源的 evidence 和 soul.md，保留原始文件。
- [x] 实现独立 Context Builder、每 Run 快照及 CLI 装配，补充测试。
- [x] 更新教程与架构文档，验证后停在 Phase 3。

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
