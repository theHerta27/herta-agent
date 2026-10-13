# Agent 能力收敛审查

2026-10-13，基线 `8d085d9`。场景清单是候选，当前目标是少量从聊天完成的任务。本轮不新增业务、不引入第二套文件服务、审批或Agent Loop。

“本轮已运行”只指下列本机夹具或桌面流程，不能推断DeepSeek会正确选工具。真实模型及私人资料授权保持原边界。

| 能力 | 源码/运行证据 | 建议 |
| --- | --- | --- |
| Harness、工具执行与历史 | 已读runtime/agent.py、注册器及服务组装；文件/MCP夹具经过现有Loop | 保留唯一Loop；真实模型任务路由未确认 |
| 文件授权、列目录、搜索、读取 | 已读workspace/tools.py、service及Electron桥；本轮workspace19项通过 | 直接复用；关闭共享会隐藏工具，聊天缺授权引导 |
| 文件预览、执行、收据 | 已读FilePlans/FileJobs接口、FileActions及原生确认；本轮file_plans18项和桌面复制/撤销通过 | 直接复用；聊天缺确认入口和执行结果呈现 |
| 磁盘分析 | 已读分析服务及工具适配；本轮桌面扫描/取消通过 | 暂停扩展；Agent只能读现成报告，不能启动分析，不承诺清理 |
| 文档读取、PDF操作、DOCX转PDF | 已读文档service/worker及工具适配；本轮documents17项、桌面文档流程通过，含本机LibreOffice转PDF | 复用库；转换及保存主要是面板API，对话闭环未确认 |
| 个人索引/Vault笔记 | 已读部分服务；本轮临时文档索引和确认保存通过 | 暂停扩展；真实个人语义检索效果及完整Agent链路未确认 |
| 提醒、专注、任务 | 已读工具注册和部分上下文；本轮未重跑 | 保留原数据；复杂学习/目标/复习调度暂缓 |
| 记忆、人格、Skills | 已读部分上下文和Skills来源/审核代码；本轮未运行 | 保留；当前是审核后注入指令，自动学习执行经验闭环未确认 |
| MCP适配器 | 已读SDK接入及白名单/只读限制；本轮16项本机协议夹具通过 | 复用；外部业务Server未验收，写工具目前拒绝 |
| 语音 | 前轮已读并真实本机合成；本轮未重测 | 保留现状，暂停额外优化 |
| 截图/OCR/快捷共享 | 本轮未完整读源、未运行 | 未确认；暂停扩展，不纳入第一条任务 |
| 通用命令、文本写入/编辑 | 工具注册未提供 | 不能冒称已有；第一条任务不需要，暂不新增 |

## 具体复用来源

本轮核对的Herta环境：Python **3.12.13**、Pydantic **2.13.5**；backend/uv.lock记录的MCP SDK **1.30.0**、pypdf **6.20.0**、python-docx **1.2.0**、Pillow **12.3.0**与实际安装一致。文档排版使用本机LibreOffice **26.8.1.1**，其`--version`返回build `bf6ef2662401c7d6dce671ab4deb26ee0af3a7c1`。这是本机环境证据，没有重装或新增依赖。

| 来源 | 本轮读取的版本/代码 | 依赖与适用边界 |
| --- | --- | --- |
| 用户的Hermes源码快照 | references/hermes-agent-main/pyproject.toml声明**0.21.3**；读取file_tools、file_operations、write_approval相关入口/片段。没有独立.git，上游commit未确认 | MIT；文件工具依赖terminal backend、路径/写保护和读取状态等模块，不是复制单文件即可用。write_approval主要管理memory/skills，不能替换Herta文件审批。未安装运行该快照；本轮不移植 |
| [官方Filesystem MCP](https://github.com/modelcontextprotocol/servers/blob/bbb701e7ac1e57f3edd1c2836b94c5457eaf7b9c/src/filesystem/lib.ts) | commit **bbb701e7ac1e57f3edd1c2836b94c5457eaf7b9c**；读取入口、路径校验和写入片段。源码package.json声明**1.0.0**，不推断npm已发布 | Node/TypeScript；SDK ^1.31.0、diff ^8.0.3、glob ^13.0.6、minimatch ^10.0.1、zod ^4。提供读写/编辑/移动，但未安装运行。Herta已有同职责服务，当前只读MCP策略也不接写工具，本轮不并存引入 |
| [Codex apply_patch](https://github.com/openai/codex/blob/f82e36592278a0a782fb0d0fc97e5fa10e832ac2/codex-rs/core/src/tools/handlers/apply_patch.rs)和[exec_command](https://github.com/openai/codex/blob/f82e36592278a0a782fb0d0fc97e5fa10e832ac2/codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs) | commit **f82e36592278a0a782fb0d0fc97e5fa10e832ac2**；读取handler接口和部分验证/执行调用，未审计整个Runtime | Rust；handler耦合Session/Turn、环境、审批、sandbox及进程管理，不能直接作为Python函数导入。可对照工具→校验→执行→结果的接线；整段移植或独立patch库运行未确认 |

Hermes快照SHA256：file_tools.py `a7c0c5ce952b3e612fb43198cdd1b78f4e03c89f3bd7901c5f79b04edb05edec`；file_operations.py `cbdcdea5d242fa00bb670a38b6e129fe353d07c04ce2b1df736fd571c64752e0`；write_approval.py `ae46d3ff0fa7ae5bd3e03b59fc15d2a50b42295717bc4cbd2a2c97683dcafdf6`。

公开上游文件的提交、路径、URL和SHA256另存.local/capability-audit/sources.json。只读研究副本没有安装或执行。

## 第一条任务：读笔记，按内容命名归档副本

采用专用普通资料目录的一份短Markdown，只有演示学习记录，无私人资料。聊天请求：“读这份笔记，说出主题，按主题命名一个归档副本，先给我确认。”

复用链路：既有目录选择/共享 → list_workspace_roots/read_workspace_text → 模型概括并选择名称 → propose_file_plan → 聊天显示后端真实预览 → 同一原生确认/执行器 → 聊天显示实际收据及副本读取结果。原文保留，不需要磁盘扫描、文档转换、Shell或新文件服务。

只补接线：聊天的目录授权入口、方案确认呈现和实际结果呈现。使用现有WorkspaceBridge/FilePlans/FileJobs；模型描述不作为审批或完成证据。取消、重名、撤销授权、源文件变化沿用现有拒绝行为。不新增Agent Loop或审批系统。

目前接线**尚未实施，任务未交付**。用户审阅后选择先保留审查，不改产品代码；这项任务仅保留为下一项候选。现有4项工作台桌面用例本轮通过，不能代替上述聊天任务。

用户明确继续仅本地测试，**真实模型任务路由未确认**。若以后另行获准，使用独立会话/数据目录和上述演示资料，避免发送已有私人记忆、历史及其他目录资料。

## 后续实施：从资料生成新笔记

用户随后要求开始实施。第一条任务收敛为读取两份短 Markdown、按内容生成复习提纲，保留来源，经聊天预览和原生确认保存新 Markdown，再通过同一 Agent 查询实际状态、读取目标回报。此前“副本归档”仅保留为审查时的候选，不并行开发第二条工作流。

新增接线复用本仓库 `d36a8ad` 的 WorkspaceService、DocumentService.note、FilePlans/FileJobs、原生审批、ChatStore 和 Agent Loop，没有新增依赖或移植上游 Runtime。聊天现在具有目录授权入口、暂存正文绑定预览、确认保存、实际内容核对和原会话续接。具体复用、操作及未确认边界见 [笔记任务](NOTE_TASK.md)。

这条接线已用临时资料、本机确定性协议桩与真实 Electron 跑通。真实模型路由、整理质量及引用准确性仍未验收，不据本地测试数量宣布完整产品可用。
