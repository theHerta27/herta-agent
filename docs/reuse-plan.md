# Phase 0：Hermes 复用计划与许可证记录

状态：2026-09-18；Phase 1 已独立实现最小 Python 骨架，未复制或导入 Hermes 业务代码。Herta 是独立项目，不是 Hermes 插件，也不以导入 run_agent.AIAgent 为实现方式。下文矩阵保留 Phase 0 决策，实际落地记录见末节。

## 1. 先区分“机制复用”和“代码复用”

机制复用，是采用同一种问题解决方式，例如工具结果必须带 tool_call_id 回填消息。代码复用，是把源文件或函数的实现复制、修改后纳入自己的项目。两者必须分开记录。

本文用四个标记：

| 标记 | 含义 |
| --- | --- |
| reuse | 保留实现本体，原样或接近原样使用；要登记来源及许可证 |
| adapt | 以原代码为基础修改移植；仍登记来源、改动与许可证 |
| rewrite | 阅读机制后，依据 Herta 自己的接口独立实现；不导入 Hermes 模块 |
| skip | V1 不做该能力，不创建占位实现 |

“rewrite”不是免除署名的标签。如果实际写代码时复制了原函数主体、独特结构或其他实质片段，应改记 adapt/reuse 并保留通知。本阶段代码决策以 rewrite/skip 为主，这是为了控制学习复杂度，不是因为根许可证禁止复用。

## 2. 实际许可证核查

读取的是这份压缩包中真实的 `references/hermes-agent-main/LICENSE`：

- 标题：MIT License。
- 版权声明：Copyright (c) 2025 Nous Research。
- 文本允许使用、复制、修改、分发等，并要求在软件副本或实质部分中包含版权与许可通知。
- 原始文件已随参考源码完整保留；另原样保存 `LICENSES/Hermes-MIT.txt`，作为来源记录。

这些是所提供 LICENSE 文本的记录，不将其扩展成对全部子目录和所有依赖的统一判断。压缩包中还存在额外许可证，例如：

| 位置 | 本次处置 |
| --- | --- |
| apps/desktop/src/plugins/hermes-bots/LICENSE | 发现独立文件；不移植此插件 |
| plugins/security-guidance/LICENSE、NOTICE | 发现独立文件和 NOTICE；V1 跳过该插件，未做条款适用分析 |
| plugins/hermes-achievements/LICENSE | V1 跳过 |
| skills/、optional-skills/ 内多个 LICENSE | V1 不搬 Skills；不能假设一律由根 MIT 覆盖 |

没有把 Hermes 的 MIT 许可证设成 Herta 自己的根 LICENSE；Herta 自有代码的发布许可证留待有代码并准备发布时确定。角色语料和资产也不因参考源码是 MIT 就自动获得相同授权。

## 3. 逐模块处理矩阵

以下 Hermes 路径相对 `references/hermes-agent-main/`，Herta 路径是计划目标，尚未创建。

| Hermes source/module | Herta Agent 怎么处理 | 决策 | 原因 |
| --- | --- | --- | --- |
| pyproject.toml → hermes_cli/main.py → cli.py | backend/herta_agent/__main__.py 提供小型教学 CLI；后续另设 FastAPI 入口 | rewrite | 不依赖 Hermes 安装、配置、TUI 和命令分发 |
| run_agent.py / AIAgent | 用小型 runtime/agent.py 装配 Provider、Registry、Context、Session | rewrite | 原类及 Mixin 连接大量成熟系统；不利于解释最小执行链 |
| agent/turn_facade.py | api/runs.py 管理 Task 和同会话单个 Run | rewrite | 本地单后端进程不需要跨进程 lease、relay 和后台 review |
| agent/conversation_loop.py | run()：检查预算 → 构建请求 → 模型 → 工具或结束 | rewrite | 保留闭环机制，去掉多层恢复、模型回退和压缩 |
| agent/iteration_budget.py | 单 Run 的明确 max_steps 计数 | rewrite；摘取候选未采用 | 原实现小且可读，但锁、refund 和额外预算机制不是 V1 必需 |
| agent/transports/base.py | llm/base.py 的 LLMProvider 与内部返回类型 | rewrite | Hermes transport 主要负责格式转换，尚不足以作为 Herta 完整异步 Provider |
| agent/transports/chat_completions.py | llm/openai_compatible.py；仅约定协议的模型接入 | rewrite | 不复制供应商特例树；先验证一条通用路径 |
| agent/chat_completion_helpers.py 及监控模块 | 原生 async 调用、有限网络期限、流关闭 | rewrite | 不搬同步 Runtime 的线程桥接和供应商专用 watchdog |
| tools/registry.py | ToolSpec + 显式注册 + Pydantic schema 导出 | rewrite | 只需少量工具；不需要插件作用域、自动发现和工具集缓存 |
| model_tools.py | tools/executor.py：校验、执行、错误结果 | rewrite | 去掉 hooks、bridge、legacy aliases 和全局状态 |
| agent/tool_executor.py | 按响应顺序执行异步工具；单工具 timeout | rewrite | 保留生命周期、tool_call_id、耗时机制，不搬审批等待与并发线程池 |
| agent/turn_tool_round.py | 在 agent.py 中保存 assistant tool_calls，结果回填再请求 LLM | rewrite | 这是学习核心；保持代码直接可读 |
| agent/message_sanitization.py | 用清晰消息类型和取消收尾保证工具配对 | rewrite | 不先引入全部兼容修复规则；遇到真实兼容问题再做精确适配 |
| agent/system_prompt.py | runtime/context.py：稳定 system + 会话工作消息 | rewrite | 不带入编码指导、Skills、Memory、插件和动态环境内容 |
| agent/prompt_builder.py / load_soul_md | 每轮读取独立 persona/soul.md 全文快照 | rewrite | 符合用户的 Always-on Persona 要求，不采用 Hermes 的截断行为 |
| 根 SOUL.md / 默认 identity | 不作为大黑塔人设来源；Phase 3 从用户语料生成 | skip | 角色身份与原始证据不同，不能替换文件名就算完成 Persona |
| agent/session_persistence.py、hermes_state*.py | 小型 SQLite SessionStore，逐步保存消息与 Run 状态 | rewrite | 借鉴持久化时机，不照搬庞大迁移、全文搜索及修复体系 |
| agent/interrupt_control.py、tools/interrupt.py | Run Task 取消、流关闭、状态收尾 | rewrite | 单进程 async 设计不需要跨 Agent/线程中断信号树 |
| agent/stream_delivery.py、tool_progress_callback | runtime/events.py → api/sse.py → React reducer | rewrite | 显式、可测试事件协议，UI 不依赖 Hermes 输出格式 |
| tools/ 内既有搜索/记忆能力 | 自建 rag/ 与 tools/search_knowledge.py | rewrite（需求驱动的新实现） | 这里只借鉴“检索作为工具”，未认定 Hermes 存在与本需求一一对应的 RAG 模块 |
| apps/desktop/ | 独立 Electron + React 应用 | rewrite（按用户 UI 要求独立设计） | 不移植 Hermes 桌面代码；Phase 0 未详细分析该桌面的实现 |
| tests/tools/test_registry.py | 借鉴注册、派发、错误边界测试场景 | rewrite | 对 Herta 自己的契约写测试，不复制依赖 Hermes fixture 的测试 |
| tests/agent/test_sequential_tool_timeout.py | 对可协作 async 工具验证 timeout/cancel | rewrite | 线程超时测试不能直接证明异步 Runtime 的取消契约 |
| tests/agent/test_soul_md_profile_isolation.py | 验证 soul 路径固定、每 Step 全文注入 | rewrite | V1 单角色，不引入 profile，但保留路径可控原则 |
| tools/mcp*、mcp_serve.py、Skills、Memory | 只保留未来接口边界 | skip | V1 明确不做 |
| 多 Agent、Cron、Gateway、Voice、TTS、自改进 | 无目标实现 | skip | 不扩大范围 |
| 根 LICENSE | 原样保留到 LICENSES/Hermes-MIT.txt | reuse（仅许可文本） | 记录参考来源；不代表已复用业务实现 |

当前没有标为 adapt 的业务模块，也没有任何 Herta 业务模块标为 reuse。若后续发现适合的小函数，不需要因为此方案一概拒绝，但应先说明实际收益与依赖，再更新此表。

## 4. 允许复用但仍不应整体复制的原因

MIT 允许的操作范围，与适合这个学习项目的工程选择，是两个问题。

Hermes 要支持多前端、多供应商、历史兼容、插件、工作线程、恢复与持久化一致性；这些复杂度有其真实需求。Herta 当前只需一个本机后端、一个 Persona、少量工具和小型知识库。照搬会让你难以分清“Agent 必须具备的部分”和“Hermes 为生产需求添加的部分”。

尤其不采用 `class HertaAgent(AIAgent)` 再替换 System Prompt 的方式。这样入口虽然换名，核心 Runtime、全局配置和依赖仍属于 Hermes，无法满足独立实现与逐步学习目标。

## 5. 后续真的摘取代码时怎样记录

每次复制或修改实质源码时，在本文件新增一条来源记录，至少写明：

| 字段 | 应记录的内容 |
| --- | --- |
| source snapshot | 当前 ZIP SHA256；若后续获得真实 commit，再补 commit |
| source path / symbol | 原文件路径、函数/类名、当时行号 |
| target path | Herta 文件路径 |
| decision | reuse 或 adapt |
| changes | 保留什么、修改什么、为何修改 |
| notices | 适用 LICENSE/NOTICE 及归档路径 |
| validation | 在 Herta 内验证的行为和实际测试结果 |

目标文件旁保留清楚的来源说明，分发产物带相应许可证通知。按被摘取文件和所属子模块检查额外声明；使用新的依赖时再记录依赖自己的许可证。不要只留下一个“参考 Hermes”的模糊链接。

## 6. 当前范围和后续触发点

当前参考快照与原始角色材料已列入 .gitignore，避免默认混入未来仓库；并未执行 git init、提交或发布。忽略规则不移动文件，也不能替代后续发布前的内容检查。

Phase 1 开始前仍需用户确认本次分析。Phase 3 才整理角色证据。Phase 4 再确定可用 embedding 端点。Phase 6 再做桌面视觉。实际摘取业务源码时更新本复用记录，不能提前声称已经实现或复用。

## 7. Phase 1 实际落地

用户“下一步”已确认进入 Phase 1。Agent、Session、消息模型、Provider 接口和 HTTP 适配器均为本项目独立编写，不依赖 references 目录、Hermes 配置或其虚拟环境。没有新增业务源码 reuse/adapt 条目。

HTTP 适配器直接使用 HTTPX，而不是引入供应商 SDK；这使请求体、响应验证和取消边界更直观。运行依赖 Pydantic / HTTPX 及传递依赖由 backend/uv.lock 记录，开发工具为 Ruff。新增依赖不因 Hermes 的 MIT 许可证而自动归入该许可证；最终分发时按锁定依赖的实际元数据处理通知。

## 8. Phase 2 实际落地

Registry、ToolSpec、Executor、echo、工具消息与循环、Windows Runner CLI 均独立编写。没有复制 Hermes 业务源码，没有引入其 Linux 信号/进程实现，也没有新增第三方依赖。本次仅借鉴“显式注册 → schema 验证 → 执行 → 结果回填”的职责拆分。项目已在 Phase 1 后上传至用户私密 GitHub 仓库，上文 Phase 0 未发布状态为历史记录。

## 9. Phase 3 实际落地

Context Builder、冻结快照与 Persona 文件加载器为本项目独立实现，没有复制 Hermes SOUL 加载、扫描或截断逻辑，没有新增第三方依赖。角色证据来自用户提供的本地快照，输入哈希与定位见 data/derived/README.md；衍生观察、行为规则和原创示例不代表原始角色材料属于 Hermes MIT 许可证。原始资料仍按原忽略规则留在本机，未随代码复制进运行包。

## 10. Phase 4 实际落地

切分、远程Embedding适配器、精确检索、版本化索引、Tool装配和评测均独立编写，没有复制Hermes业务模块或Linux进程/信号代码。只新增NumPy，版本由backend/uv.lock锁定；许可证为BSD-3-Clause，二进制发行附带的组件声明应在最终打包时按安装包元数据保留，不由Hermes MIT代替。知识正文是用户现有快照的人工转述，来源与边界见knowledge/README.md；没有新增外部抓取语料。
