# Hermes 固定源码与 Herta Harness 映射

参考来源为用户提供的 `hermes-agent-main.zip`，现有静态分析见 `docs/hermes-analysis.md`。ZIP SHA256：`3F5F65CE7BDBE33B59463CBDF20E73CEA5930FBA5B2B9C4515663F5EB2CD72D3`。压缩包未提供可靠 Git Commit；名称 main 不表示在线最新。下表行号仅对本机这份固定快照有效。

Herta 不导入/运行 Hermes Runtime。本轮新增逻辑依照接口与机制独立实现，没有复制 Hermes 上下文压缩器、Mixin 或 MCP 运行时。MCP 接入依赖官方 Python SDK，非自建协议。

| 阅读机制 | 固定快照入口 | Herta 对应 | 采用与差异 |
| --- | --- | --- | --- |
| 模型—工具—再模型循环 | `agent/conversation_loop.py:1429` `_run_conversation_turn` | `runtime/agent.py:97` `Agent.run` | 保留唯一异步 Loop，按Step重建上下文；不复制复杂重试/预算退款 |
| 每请求选择，历史不改写 | `agent/context_engine.py:120` `ContextEngine.select_context`；`conversation_loop.py:1181` `_apply_context_engine_selection` | `runtime/context_engine.py:206` `prepare` | 返回请求专用包，存储历史不变；每Step含诊断 |
| 预算与压缩窗口 | `agent/context_compressor.py:4754` `compress` | `runtime/context_engine.py:165` `_summary` | 保留完整轮/Persona；首版预算内抽取旧片段，独立存来源与哈希；不执行上游模型摘要/阈值恢复策略 |
| assistant调用与tool结果配对 | `agent/turn_tool_round.py:45` `run_tool_round`、`:96`调用追加；`agent/tool_executor.py:1074`结果追加 | `runtime/agent.py`、`runtime/session.py`、`service/turn.py` | 调用先持久化，结果按ID回填；Context按完整回合选择 |
| 工具描述与派发 | `tools/registry.py:181` `ToolEntry`、`:824` `get_definitions`、`:874` `dispatch` | `tools/registry.py`、`tools/executor.py` | Pydantic参数校验、只读权限、工具期限、结构化错误和体积上限 |
| MCP生命周期 | `tools/mcp_tool.py:307` `MCPServerTask` | `tools/mcp.py` `connect_mcp_tools` | 单个显式本地Server/白名单/只读；专属SDK任务隔离故障；不做多Server、HTTP或自动发现 |
| Persona与请求上下文 | `agent/system_prompt.py:659` `build_system_prompt_parts`、`agent/turn_context.py:1053` `build_api_messages` | `persona.py`、`runtime/context.py` | 每Run完整人格冻结，下Run重读；文件错误明确失败 |
| 会话与派生诊断 | 只参考历史/请求上下文分离，不复制上游存储 | `storage/sqlite.py:595` `record_context`、`:644` `get_diagnostics` | 既有SQLite v2附加表，摘要单独存储；GET与SSE供桌面查看 |

## 当前源码文件校验

下面是本机快照文件的SHA256，可用于核对阅读版本；不是 Git Commit。

| 文件 | SHA256 |
| --- | --- |
| `agent/conversation_loop.py` | `d905a62f62b24922d317483ec0a3b96678448f2b03f08d97f07db61ede04b6c1` |
| `agent/turn_tool_round.py` | `ede47b95f18e289cfa86e367ac1cdd30be50d6477e80e3a31e7808c23c80dce7` |
| `agent/context_compressor.py` | `6718ad154f2a01816750d3b00dbb149915e44d7ede5ac363ddfbe50ab445f983` |
| `agent/context_engine.py` | `97c9c6f57a7c8a5e0f0dd6242d08b3417b8bbcfdf226eddf2d3b3af78cb42be5` |
| `tools/registry.py` | `5a3e232b8b0b6ec64a994efe1dc7309d9c733c813a3284d6df44f67cc1cb24a2` |
| `tools/mcp_tool.py` | `96ba2757575b98b17d9fab2ff92446346d28df16ab9c75250c22d96259e3edfb` |

原参考快照及其LICENSE保留原位、按既有.gitignore排除，不加入Herta构建。既有直接复用内容与许可证仍见 `docs/reuse-plan.md`；本轮没有增加Hermes直接源码复用。上述阅读是静态机制核对，未对整个上游仓库做全面审计。
