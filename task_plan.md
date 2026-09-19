# Herta Agent 分阶段任务计划

目标：仅分析 Hermes 源码并产出教学用文档；不实现业务代码，不进入 Phase 1。

## 阶段
- [x] 检查输入文件、源码快照和实际许可证。
- [x] 追踪入口、Agent Loop、Tools、Context、Persona、Session、timeout/cancel。
- [x] 编写 docs/hermes-analysis.md、docs/architecture.md、docs/reuse-plan.md。
- [x] 补充手动复现步骤，核验源码引用和交付范围。
- [x] 汇报并停在 Phase 0，等待用户确认。

## 当前状态
Phase 0 与 Phase 1 已完成。当前停在 Phase 1，等待用户确认后才执行 Phase 2。

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
