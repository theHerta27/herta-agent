# Herta Agent 分阶段任务计划

目标：按用户逐阶段授权实现 Windows 桌面 Agent，并提供可亲手复现的教程。

## 阶段
- [x] 检查输入文件、源码快照和实际许可证。
- [x] 追踪入口、Agent Loop、Tools、Context、Persona、Session、timeout/cancel。
- [x] 编写 docs/hermes-analysis.md、docs/architecture.md、docs/reuse-plan.md。
- [x] 补充手动复现步骤，核验源码引用和交付范围。
- [x] 汇报并停在 Phase 0，等待用户确认。

## 当前状态
Phase 5最终基线6679dfeda6535d4e33d8e24e7d042d0b5f6f7b84已按授权提交并push，干净基线上创建phase-6-ui。现只完成Phase 6阶段1：真实Windows窗口、自启Python、状态与关闭清理；9项进程测试、6项Electron测试及178项后端回归通过。停止，不进入阶段2；Phase 6未提交、未push、无merge。真实API未调用，真实RAG效果与供应商流式兼容性仍待验收。

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

## Phase 6 本轮（仅设计）
- [x] 读取用户完整要求、Phase 5实际能力与文档。
- [x] 查看Codex/Cyrene截图、Cyrene关键UI源码、ui-ux-pro-max及全部Herta素材。
- [x] 确认最小Settings与环境Key约束。
- [x] 完成docs/phase-6-ui-design.md与7阶段phase-6-plan.md，核对接口和范围后停止，不编码。


## Phase 6 阶段2–5交付（2026-09-23）
- 阶段1已单独提交 a36613061886e89d7dd1535ea081ee9fb16e5e28。按本轮授权连续完成阶段2–5，不进入Settings或阶段7。
- 新增会话/流式传输与应用级状态、Sidebar/Welcome/Composer、Markdown回答、工具/RAG活动、取消及持久历史恢复。后端业务源码未修改。
- 行为测试先失败再实现；真实桌面测试发现并修复中文组字事件读取问题。独立只读审查无阻塞发现。提前取消但未找到持久Run时按既定设计保持未知并禁止重复提交，不凭空推断失败。
- typecheck、lint、21项unit、7项真实Electron e2e（含build）通过；178项后端unittest、Ruff check/format、diff check通过。没有真实API调用。
- e2e以测试专用入口注入离线Provider/检索夹具，走真实HTTP、Runtime与SQLite；不把夹具检索当成真实RAG效果验证。
- 本批提交与push仅面向phase-6-ui，不合并；操作结果以Git实际记录为准。

## Herta Harness V1 — 2026-10-09
用户授权按 docs/Herta_Agent_Harness_v1.md 连续实现可直接使用的首版。实施清单：docs/V1_IMPLEMENTATION_PLAN.md。
- [x] P0 基线：179 后端、22 前端通过；基线提交 81a1d740。
- [x] Context Engine / 诊断持久化。
- [x] 工具可靠性 / 最小只读 MCP。
- [x] 桌面 Settings / Context 面板。
- [x] 一键启动 / 固定本地评测；真实服务验收按最新用户指令暂缓。
- [x] 完整本地回归 / 独立审查 / 首版交付。
错误：Windows 沙箱 setup refresh 失败；只读和开发命令使用自动审批的非沙箱执行。apply_patch 同样失败，改用项目内 UTF-8 文件写入。

最新约束：用户明确“目前阶段不允许真实验收，本地测试就行”；真实系统评测停止，未完成报告。首版本机交付完成，不宣称真实 V1 效果验收完成。

## 2026-10-11 Cyrene 功能借鉴与产品推荐（仅设计分析）
- 目标：继续学习Hermes源码并自研Herta Harness；从Cyrene本地源码提取实用功能，提出产品范围和分期建议，不开始实现。
- 已确认首要用途：日常桌面陪伴（聊天、音乐、语音、提醒、轻量自动化）。Live2D和代码协作不做；其他能力可纳入分阶段路线。真实验收仍未获得重新许可。
- [x] 阅读用户粘贴说明、当前Herta状态、Cyrene README/目录与依赖。
- [x] 核对关键源码：Harness/权限/Skills/Memory，以及音乐/语音/提醒/文件/学习的实际实现与边界。
- [x] 比较产品路线，给出推荐功能、用户流程、机制优先级与分期出口。
- [x] 交叉核对证据并交付推荐方案。
- 调研错误：一个推测的tool-registry路径不存在，使用rg定位实际built-in-tools和harness/adapter/tool-runtime，未执行或修改参考代码。

## 2026-10-11 日常陪伴版实施
- 用户授权开始实现；Hermes为主要工程参考，Cyrene用于产品思路。设计：docs/companion-v1-design.md；执行计划：docs/superpowers/plans/2026-10-11-companion-v1.md；持续记录：.local/companion-work/progress.md。
- 本轮交付推荐第一批陪伴能力，后续文件/网页/学习/自动Skills路线保留。验收仅本地，不push/merge，不改参考源码或原有用户文档。
- [x] 基线223后端/35前端、新版设计和接口。
- [x] SQLite日常服务/可信工具/提醒及偏好。
- [x] 桌面桥接/媒体/托盘/通知。
- [x] 本地语音/取消/音频协调。
- [x] 日常面板/录音输入/回复朗读/专注流程。
- [x] 全量本地回归/独立审查/一键交付（2026-10-12：243后端、46前端单元、14真实Electron全部通过）。

## 2026-10-12 个人桌面助手路线推进
- 用户提供最终产品目标并要求继续推进。日常陪伴已完成；下一子项目采用目标中的第一轮“安全操作文件”，后续接文档/桌面内容、个人知识与Skills。
- 工程继续以Hermes源码为参考；Cyrene提供产品思路。沿用仅本地验收、排除Live2D和代码协作、保留原用户文档的约束。
- [x] 读取目标附件、当前提交与执行/桥接/权限接口。
- [x] 将目标拆成可交付里程碑，写文件工作台v1具体设计并自查。
- [x] 设计与实施计划已完成，按用户连续授权实施。
- [x] 文件工作台读取、受控执行、确认/收据/取消/撤销及本地回归已完成。

## 2026-10-12 移除音乐业务（当前任务）
- 用户明确取消全部音乐产品方向，要求完成代码清理，不重新设计。计划：docs/superpowers/plans/2026-10-12-remove-music.md。
- [x] 后端音乐模型/工具/路由/存储逻辑移除，兼容旧偏好与数据库。
- [x] AudioCoordinator简化纯语音；前端/IPC/协议/专注清理，保留语音行为。
- [x] 修订用户herta-agent-plan及其他产品文档，给出后续任务顺序。
- [x] 完整本地回归、一次独立审查、记录结果和本地交付（247后端/49单元/14Electron通过）。

## 2026-10-12 V2.1只读工作台与音色资源（当前实施）
- 用户明确开始实施既有开发计划，并授权任意使用/改名/移动theHerta资源；音乐方向保持取消。
- [x] 目录授权、路径范围、项目识别、浏览/搜索/文本读取与受控只读工具。
- [x] 可取消磁盘分析、占用统计、重复候选与持久结果。
- [x] Electron安全桥/原生目录选择/文件工作台/授权提示。
- [x] 核查theHerta权重及参考音频，规范命名目录并保存原始哈希；接入前保持原始字节。
- [x] 全量本地回归、一次独立审查、文档与可用构建交付。

## 2026-10-13 V2.2-V2.6持续实施
- [x] 受控文件、文档/知识、学习任务、人格/记忆/Skills与大黑塔音色。
- [x] 快捷面板、主动共享/OCR、只读多MCP与私人发行目录移动后启动。
- [ ] 最后完整回归、一次独立审查及重要问题修复、交付。
