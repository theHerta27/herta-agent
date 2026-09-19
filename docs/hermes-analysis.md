# Phase 0：Hermes Runtime 源码分析

分析日期：2026-09-18。状态：静态源码分析完成；没有安装、导入或运行 Hermes，没有实现 Herta 业务代码。

本次最重要的结论：借鉴 Hermes 的「上下文 → 模型 → 工具 → 结果回填 → 再调用模型」机制，自己实现一个小型、原生异步的 Runtime。不要直接继承 AIAgent：它已承担大量与 Herta V1 无关的生产环境职责。

## 0. 分析依据与阅读边界

唯一 Hermes 依据是用户提供的 `hermes-agent-main.zip`，解压位置为 `references/hermes-agent-main/`。这是参考材料，不是 Herta 的依赖，也不进入 Herta 构建。

| 输入 | 本次检查结果 |
| --- | --- |
| hermes-agent-main.zip | 80,929,856 字节；完整解压，原 LICENSE 保留 |
| 大黑塔原始语料.md | 25,618 字节；抽查开头及标题，包含语音、角色故事；保持原位 |
| 大黑塔原始语料的整理思路.md | 15,544 字节；检查开头及目录，包含 Persona、Style、Relationship、Knowledge 分类建议；保持原位 |

ZIP 的 SHA256：`3F5F65CE7BDBE33B59463CBDF20E73CEA5930FBA5B2B9C4515663F5EB2CD72D3`。

压缩包名称中的 `main` 不能标识确定的 Git commit。本报告使用 ZIP 哈希和当前快照的行号定位，不声称对应在线最新版本。没有逐一审计整个仓库；阅读范围是 V1 相关的核心调用链，其他能力只识别边界。

用户开头明确说语料整理留到后续，因此本阶段不推导人格、不生成 evidence 或 soul.md，不将整理建议直接当成原作事实。Phase 3 再完整阅读两份材料并做证据抽象。

下文路径均相对 `references/hermes-agent-main/`，行号只适用于这份快照。

## 1. Runtime 启动入口在哪里

| 层级 | 位置 | 职责 |
| --- | --- | --- |
| 安装后的命令 | pyproject.toml:412–413 | `[project.scripts]` 将 hermes 指向 hermes_cli.main:main |
| 仓库根启动脚本 | hermes:9 | 调用同一个 main，支持命令分发 |
| CLI 分发入口 | hermes_cli/main.py:3431 | 顶层 main；聊天分支可见 3156–3168 |
| 聊天命令 | hermes_cli/main.py:1748 | cmd_chat；传统 CLI 路径在 1821–1823 调用 cli.main，其他分支也可走 TUI |
| CLI 界面入口 | cli.py:4591 | 创建/运行 CLI 会话；一次调用示例在 4073、4164 |
| Runtime 对象 | run_agent.py:229 | AIAgent 由多个 Mixin 和转发方法组成 |
| 回合门面 | agent/turn_facade.py:22、137 | run_conversation 处理回合准入等，再转发实际循环 |
| 独立脚本入口 | run_agent.py:1467、1525 | main 创建 AIAgent 并执行一轮，便于理解 Runtime 与 CLI 的区别 |

不要把 `cli.py` 的输入框、终端输出和 Runtime 混为一层，也不要认为所有 Hermes 桌面/TUI/Gateway 入口都经过传统 CLI 路径。本报告追踪的是理解核心 Runtime 所需的一条调用链。

Herta 将有两个入口：Electron 负责桌面进程生命周期，FastAPI 负责后端服务；`runtime/agent.py` 不应该导入 Electron 或 FastAPI。

## 2. Agent Loop 在哪里

真正主循环在 `agent/conversation_loop.py:1429` 的 `_run_conversation_turn()`。`run_conversation():1579` 是外层包装，负责导出回合边界，不是那个 while 循环本身。

按主干阅读：

1. `build_turn_context()`：准备消息列表、当前用户消息和稳定 System Prompt（1470）。
2. while 检查调用次数与 iteration budget（1520）。
3. `begin_iteration()`、`prepare_iteration()`、`assemble_api_request()`：准备本次请求（1521–1524）。
4. preflight 与 `_run_api_retry_loop()`：检查上下文并请求模型（1525–1540）。
5. `normalize_model_response()`：归一化响应（1549）。
6. 有 tool_calls 就 `run_tool_round()`，否则 `finish_text_response()`（1555）。
7. 工具回合继续循环；普通回复或错误触发收尾；`finalize_turn()` 统一处理退出（1568）。

```text
run_conversation
  → _run_conversation_turn
      → build_turn_context
      → while 预算允许
          → 组装请求 → 请求模型 → 归一化响应
          ├─ tool_calls → run_tool_round → tool messages → 下一次循环
          └─ 普通文本  → finish_text_response → 结束
      → finalize_turn
```

`agent/iteration_budget.py:25` 的 IterationBudget 用锁保护 consume/refund/remaining。循环同时检查 `max_iterations`，还有 `_budget_grace_call` 例外；API 重试也有独立预算。因此 Hermes 的上限不等价于简单的「所有 HTTP 请求绝不超过 N 次」。Herta 将明确 `max_steps` 的定义，先不引入 grace、refund 和多级重试。

## 3. Tool Registry、schema、校验和执行

| 环节 | 实际源码 | 观察 |
| --- | --- | --- |
| 工具条目 | tools/registry.py:181 | ToolEntry 保存 schema、handler、可用性条件等 |
| 注册 | tools/registry.py:649 | register 接收已经写好的 schema 字典，并做基本结构检查 |
| 发布给模型 | tools/registry.py:824 | get_definitions 输出 OpenAI function 格式，包含可用性过滤和动态 schema 覆盖 |
| 工具集选择 | model_tools.py:213、500 | get_tool_definitions / _compute_tool_definitions 负责会话需要哪些工具 |
| 参数 JSON 解析 | agent/tool_executor.py:152 | _parse_tool_arguments 要求合法 JSON object；失败返回错误结果 |
| 工具回合 | agent/turn_tool_round.py:45 | 记录 assistant tool_calls，检查名称、持久化后执行 |
| 执行策略选择 | run_agent.py:1302 | _execute_tool_calls 按条件选择顺序、并发或分段执行 |
| 顺序执行 | agent/tool_executor.py:1706、1718 | 解析每个调用，派发并处理结果 |
| 中间件入口 | model_tools.py:867 | handle_function_call 做参数转换、hooks、guard、派发和结果处理 |
| 最终名称派发 | tools/registry.py:874 | dispatch 查 handler，桥接异步 handler，并统一异常和结果类型 |

三个容易混淆的概念：

- schema 是告诉模型「工具接受什么参数」的描述。
- JSON 解析只证明参数能解码成对象，不证明字段、类型和范围符合业务规则。
- 参数校验应在执行前完成，不能只相信模型或兼容服务端会按 schema 约束输出。

这条 Hermes 通用路径不是「Pydantic 参数类自动生成 schema 并统一校验」；它还有参数 coercion、特定工具自己的检查，以及 Tool Search 延迟 schema 校验等路径。不能把本报告的观察扩大成「Hermes 完全没有参数验证」。

Herta 的教学版将使用同一个 Pydantic 参数类生成 schema 和执行校验，拒绝未知工具、额外字段、非法类型与范围。模型输出的字符串必须先累积完整，才能解析；不能收到半段 arguments 就调用工具。

## 4. Tool Result 怎么回填

`agent/turn_tool_round.py:96–99` 先追加含 tool_calls 的 assistant 消息。`agent/tool_executor.py:1074–1075` 创建并追加 tool 消息，使用同一个 tool_call_id；随后持久化，最后才发 tool.completed 回调（1076–1084）。

最小协议示意，下面是说明用数据，不是已实现的 Herta 输出：

```json
[
  {"role":"user","content":"查一下相关世界观资料"},
  {"role":"assistant","content":null,"tool_calls":[
    {"id":"call_1","type":"function","function":{
      "name":"search_knowledge","arguments":"{\"query\":\"黑塔 空间站\"}"
    }}
  ]},
  {"role":"tool","tool_call_id":"call_1","content":"{\"ok\":true,\"chunks\":[]}"}
]
```

下一次模型调用要能看见整组消息。只在 UI 显示「找到 4 条」而不回填模型上下文，不构成 Agent Tool Calling 闭环。未知工具、校验失败、超时和取消也必须处理配对关系，防止下一轮带着悬空 tool_call_id 请求模型。

## 5. Context 是怎么组装的

`agent/system_prompt.py:659` 的 `build_system_prompt_parts()` 分为三段：

| 段 | 主要内容 | Herta V1 处理 |
| --- | --- | --- |
| stable | identity/SOUL、工具指导、编码指导等 | 保留稳定 Persona 和少量 Runtime 规则的设计思路 |
| context | 调用方 system_message、项目上下文、工作区指导 | V1 不扫描 AGENTS.md 等工作区文件 |
| volatile | Skills、Memory、用户资料、插件段、时间和运行环境 | V1 大部分不做，也不创建这些系统 |

`build_system_prompt():722` 拼接这些段。`agent/turn_context.py:927–936` 从 conversation_history 复制列表并追加用户消息；957–959 使用或构造 `_cached_system_prompt`。

每次 API 请求前，`build_api_messages():1053` 建立发给模型的消息副本；1151–1155 将有效 System Prompt 放在消息列表开头。会话存储的 messages 与发给模型的 wire messages 不是必须完全相同的对象。

Herta 会明确区分稳定 system、持久化的会话历史和本轮工作消息。工具 schema 是 Provider 的 tools 参数，不是把 Python 函数代码塞进 System Prompt。

## 6. SOUL / Persona 怎么注入

`agent/system_prompt.py:542` 的 `_identity_parts()` 调用 `agent/prompt_builder.py:1492` 的 `load_soul_md()`。后者从 HERMES_HOME（或显式 home_override）下读取 `SOUL.md`；不是在向量库做检索。成功读取时放在 stable identity 的位置；没有可用内容时回退默认 identity。

需要准确区分：

- **每次 API 调用携带 Persona**：通过每次请求的 System Prompt 实现。
- **每次 API 调用重新读取文件**：Hermes 没有这样做，使用缓存及重建逻辑。
- **Persona 全文永不截断**：Hermes 读取路径里有扫描与 `_truncate_content()`，不能据此保证全文。

Herta 的方案是每个用户回合开始时读取完整 `persona/soul.md`，保存该轮不可变快照；本轮每次模型调用都注入全文。下一用户回合再读取，使修改在下一轮生效。若内容过大或不可读，明确报告错误，不静默改成 RAG 或截断 Persona。

## 7. Session 怎么保存

主会话存储为 SQLite：`hermes_state.py:441` 的 SessionDB。默认路径解析在 `hermes_state.py:178–181`，指向 HERMES_HOME/state.db。它包含 WAL、读连接池、全文检索、恢复和迁移等较复杂的数据库逻辑。

主要调用点：

- `hermes_state_sessions.py:381` create_session / 386 ensure_session：建立会话记录。
- `agent/session_persistence.py:303` _persist_session：保存当前会话状态。
- `agent/session_persistence.py:345` _flush_messages_to_session_db：加锁并增量写入。
- `agent/session_persistence.py:220–230`：批量调用 append_messages_batch 并同步写入标记。
- `agent/turn_tool_round.py:116–139`：执行工具前先确保调用记录可持久化；失败就停。

JSONL 出现在故障转存和其他辅助路径，不能把 Hermes 的主会话存储描述成「每次直接写一个 JSON 文件」。Herta 会借鉴增量保存、工具调用配对和失败可恢复的思路，重写成小型 SQLite SessionStore。当前阶段没有创建数据库。

## 8. timeout / cancel 怎么做

### 模型调用

`agent/turn_api_call.py:65` 的 perform_api_call 选择流式或非流式。相关入口经 `run_agent.py:1231–1232` 转发到 chat_completion_helpers。

`agent/chat_completion_nonstream.py:249–275` 展示了守护工作线程、短间隔等待以及首响应/无活动/整体等待检查；中断路径会尝试中止当前请求客户端。流式路径也有监控和中断处理，不能把这套机制概括成一个 HTTP timeout 参数。

### 工具调用

`agent/tool_executor.py:793` 解析顺序工具 deadline，166 解析并发 batch deadline；两者还有配置关闭、工具例外和人工等待排除规则。

顺序工具路径 `agent/tool_executor.py:850–935` 在线程池提交调用并轮询结果。超时会生成 timeout 结果、取消未开始的 future、设置工作线程中断信号；放弃时不等待卡死线程退出。

### 用户取消

`agent/interrupt_control.py:109` 的 interrupt 设置本 Agent 的状态；184–193 尝试中止请求并向对应执行线程、工具工作线程发信号；也会传播给子 Agent。`agent/turn_iteration_prep.py:331` 等位置检查中断。

**停止等待不等于强杀正在运行的线程。** 非协作工具仍可能继续执行。Herta V1 工具很少，应优先采用可取消的原生 async I/O；不要为了复用 Hermes 线程桥接，把 FastAPI 的事件循环也堵住。Herta 的取消方案与边界见 architecture.md。

## 9. Provider 与流式输出值得学什么

`agent/transports/base.py:12` 定义 ProviderTransport，职责是消息转换、工具转换、请求参数和响应归一化。文件开头明确指出：客户端创建、streaming、凭据、interrupt、retry 不属于这个抽象。

`agent/transports/chat_completions.py:361` 的 ChatCompletionsTransport 是 OpenAI-compatible 路径之一。它并非一个可直接搬走的纯净 Async LLM Provider：里面也包含许多模型兼容逻辑。

Herta 会重写更小的 `LLMProvider`，把 SDK 类型隔离在适配器里。只支持明确约定的 Chat Completions 兼容协议，不能因为服务商叫 OpenAI-compatible 就假设它支持所有工具或流式字段。

Hermes 的 `agent/stream_delivery.py:285` 处理文本 delta 分发，工具结果路径使用 tool_progress_callback。Herta 借鉴事件驱动思路，定义自己的 Pydantic AgentEvent，再交给 API 编码为 SSE，不复制 Hermes 的终端显示、插件 hooks 或桌面桥接层。

## 10. 哪些复用，哪些不复制

本阶段**未复制任何业务实现进 Herta**。只保留完整参考源码及原 LICENSE，并将根 MIT 许可证另存到 LICENSES/Hermes-MIT.txt 便于追踪来源。

- 直接采用机制：有界循环、显式工具 schema、tool_call_id 配对、结果回填、稳定 Persona 前缀、会话保存、事件驱动 UI。
- 参考后重写代码：Loop、Provider、Registry、Context Builder、SessionStore、超时/取消、事件协议。
- 可评估的小型摘取候选：IterationBudget；但 V1 单个异步 run 用简单计数器更易学，目前仍决定重写。
- 不整体复制：AIAgent、多 Mixin 门面、动态插件发现、完整线程调度器、多供应商兼容树、整套数据库恢复框架、Hermes 桌面。
- V1 跳过：MCP、Skills、长期 Memory、USER.md、自改进、多 Agent、Cron、IM Gateway、Voice/TTS、Live2D、多角色、复杂 RAG。

逐模块决策和许可证处理见 reuse-plan.md；完整 Herta 请求生命周期见 architecture.md。

## 11. 初学者最值得读的 5 个函数

按这个顺序，先看输入、输出和谁调用谁，再读细节：

| 顺序 | 函数 | 本次阅读问题 |
| --- | --- | --- |
| 1 | [_run_conversation_turn](D:/Desktop/herta-agent/references/hermes-agent-main/agent/conversation_loop.py:1429) | 为什么工具结果要回到同一个循环？ |
| 2 | [run_tool_round](D:/Desktop/herta-agent/references/hermes-agent-main/agent/turn_tool_round.py:45) | 为什么先记录 assistant tool_calls？ |
| 3 | [ToolRegistry.dispatch](D:/Desktop/herta-agent/references/hermes-agent-main/tools/registry.py:874) | 名字如何变成一次函数执行？ |
| 4 | [build_system_prompt_parts](D:/Desktop/herta-agent/references/hermes-agent-main/agent/system_prompt.py:659) | 稳定身份与动态上下文放在哪里？ |
| 5 | [InterruptControlMixin.interrupt](D:/Desktop/herta-agent/references/hermes-agent-main/agent/interrupt_control.py:109) | 取消信号如何跨到实际工作？ |

这些函数用于学习 Hermes，不要求照抄其长度和抽象层数。手动阅读命令与验收练习见 phase-0-walkthrough.md。
