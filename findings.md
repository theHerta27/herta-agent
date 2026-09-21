# Phase 0 发现

## Phase 4 设计收敛
- 用户锁定现有大黑塔事实/关系/故事corpus，不加入技术笔记、不扩充；正式聊天模型调用search_knowledge，主路径Embedding+本地精确检索，无向量数据库。
- 词面baseline降为可选离线实验，不实现多路融合或通用检索框架。
- 知识正文整理为20个K单元，机器chunk之后映射这些稳定ID；题集28题，区分17题有答案、7题资料不足、4题无需检索。
- 保留原文不确定性：咖啡评价的幽默、视力猜测、年龄/镜中问题的遮蔽、假死报道与阿哈反转。K13与K17保留不同证据，避免跨段题因重复整理而变成单段题。
- 工具失败需保持外层ok=false；计划用可预期工具错误映射，不能把失败对象包成成功data。计划增加每工具可选timeout，echo沿用现状，检索默认20秒。
- 当前唯一实施前阻塞是Embedding运行方式（数据是否出机、Windows依赖、编码约束），已询问，未代选或调用远程服务。

## Phase 3 阅读与设计发现
- 完整读取大黑塔原始语料.md（275 行，含互动/战斗语音、宣传介绍及四段角色故事）和整理思路全文。后者是分析建议，不冒充原始角色证据。
- 已有架构明确每 Run 读取全文、记录哈希，该 Run 所有 Step 使用同一快照；不用重新询问已确认的加载周期。
- 现有 Agent.run 内拼接 DEFAULT_SYSTEM + history，需要移至可注入 Context Builder。Runtime 不应知道大黑塔名字、soul 路径或 Persona 规则。
- 主要人格证据：自然自信、问题驱动、敢于质疑、把失败视为研究信息、按能力评价他人、轻微戏谑与审美偏好。故事三的事务委托与研究专注、故事四的求问和怀疑具有较强行为证据；战斗语音只辅助风格，空的 2x 条目不作为证据。
- Windows CLI 路径须与启动工作目录解耦，UTF-8/BOM 和 CRLF 需要测试；不采用 Hermes 配置目录、Unix 信号或 shell 脚本。
- 用户已确认 A：soul 缺失/空/不可读/解析失败均停止当前轮，不降级；Session 保留，修复后下一轮重新读取。
- 11 条 evidence 已完成并校验原文行号；两份原始文件 SHA256 未变。未重新抓取线上语料，没有把分析建议当成原作证据。
- 已实现冻结快照和实际注入正文哈希，system 单次注入、不存 Session.history；BOM 去除、CRLF 保留。CLI 的默认资源路径与 cwd 无关，自定义 Windows 路径通过测试。

## Phase 1 决策
- Phase 1 已完成，26 项离线测试与 Ruff 检查通过。教学说明见 docs/phase-1-walkthrough.md；真实模型联调尚未执行。
- 默认 Python 是 Hermes 的 3.11.9，改用 uv 在项目 .local/python 内安装 3.12，再建立根目录 .venv；不在 Hermes 环境安装依赖。
- 原生异步 HTTPX 实现最小 Chat Completions 适配器，避免引入供应商 SDK；Pydantic 验证内部消息、配置和响应结构。
- 默认 DemoProvider 完全离线且明确标注为固定回显；真实模型使用 --provider openai 显式开启。
- Phase 1 每次正常 run 只调用一次模型。for 循环和 max_steps 是 Phase 2 的结构边界；不制造无意义多次请求来演示循环，不声称已经测试工具预算耗尽。
- 会话失败/取消保留用户消息，不追加假 assistant 回复；finally 释放会话占用。

- 输入文件：hermes-agent-main.zip、大黑塔原始语料.md、大黑塔原始语料的整理思路.md。
- 当前目录没有业务代码，未发现适用的 AGENTS.md。
- 用户要求每次只做一个阶段，本次交付仅为 Phase 0。
- ZIP SHA256：3F5F65CE7BDBE33B59463CBDF20E73CEA5930FBA5B2B9C4515663F5EB2CD72D3；不把 main 文件名当作确定的 Git commit。
- 压缩包含独立桌面应用、分拆后的 agent 模块及多个子目录许可证，需追踪实际调用链，不能按旧版 Hermes 的文件布局推断。
- 角色输入包含台词/角色故事与整理建议；本阶段只检查目录和内容类型，不生成衍生材料。
- 根 LICENSE 实测为 MIT，Copyright (c) 2025 Nous Research；已保留解压源码原许可证，子目录许可证需逐项判断。
- 入口声明 pyproject.toml:413 → hermes_cli.main:main；AIAgent 位于 run_agent.py:229，经 TurnFacadeMixin 转发到 agent/conversation_loop.py。
- tools/registry.py 的 register 接收现成 schema 字典，get_definitions 包装为 function schema；dispatch 做名称查找与结果/异常统一，并非统一 Pydantic 参数验证器。
- Hermes 的 SOUL 由 prompt_builder.load_soul_md 从 HERMES_HOME 读取，可能扫描/截断；Herta 需要另行实现整份稳定注入。
- 真实循环在 conversation_loop._run_conversation_turn:1429；1520 行检查 max_iterations 与 iteration_budget，另有 grace call，不能将其说成绝无额外调用的简单 for 循环。
- turn_context.build_api_messages:1155 在每次 API 请求前添加 system message；system_prompt 将 stable/context/volatile 三段拼接，含许多 V1 不需要的能力。
- 工具结果通过 tool_executor.py:1074 配对 tool_call_id，先持久化再发 tool.completed。
- SessionDB 使用 SQLite，默认 HERMES_HOME/state.db；JSONL 有故障转存等用途，并非主会话存储。
- 工具 timeout 是等待截止时间与工作线程中断信号组合；放弃等待不能保证强制终止非协作线程。Herta 拟采用 asyncio 原生异步工具和有限网络 deadline。
- 参考官方 Python 3.12 asyncio、Pydantic JSON Schema、MDN SSE、Electron security 文档核验方案；没有用线上 Hermes 替代本地快照。
- 最终决策：本阶段仅复用 LICENSE 文本，无业务代码 reuse/adapt；核心机制参考后重写。V1 采用独立异步 Runtime、SSE、本地 SQLite 历史及简单 NumPy 向量存储方案。
- 三份原始输入哈希复核未变；24 个被行号引用的源码文件与 ZIP 哈希一致，13,888 个压缩包文件均已解压存在。
# Phase 2 补充：Windows 工具闭环

- 用户确认 Ctrl+C 取消当前轮、保留 Session。同步输入循环外持有 Runner，每轮只运行一个可取消任务；不用 stdin 线程、loop.add_signal_handler 或 Linux 进程信号写法。
- 工具调用记录与结果必须配对。取消时只为 pending id 回填 cancelled，已完成结果保持不变；max_steps 最后一轮仍要求工具时不执行，而回填预算耗尽结果。
- Registry 的同一参数模型既生成 schema，也供 Executor 严格验证 JSON；失败以 ok/data/error 回填，不把底层异常正文发给模型。
- Windows 子进程内定时触发 SIGINT 已验证模型等待、工具等待、后续轮继续及单条消息退出 130；本地取消不保证远端模型停止计费。
- 本阶段未引入新依赖或复制 Hermes 业务代码，原始语料仍留待 Phase 3。

# Phase 4 补充：可解释检索

- 主路径固定为模型主动Tool → 独立远程Embedding → NumPy精确余弦；Runtime/Persona不含检索逻辑。
- 文档/query向量空间用服务/模型/前缀/输入上限指纹约束，维度一致不足以证明兼容。Key变化不改变指纹，Key不序列化。
- 索引在Windows写新目录并自检后替换current指针，不覆盖正在使用的矩阵；文件校验和与正文/来源hash防止静默使用不匹配数据。
- 小语料top-k常返回相关但不能回答的资料；不足题不能用空结果作为唯一验收。引用来源正确也不证明答案语义正确。
- 28题固定为dev17/check11；直接检索和正式聊天分开，工程fixture不冒充远程模型效果。当前无HERTA配置，真实校准/效果仍待验收。

# Phase 5设计发现

- 用户已确认跨Session并行且全局满额立即拒绝，无等待队列。取消清理未结束前仍占用名额，同Session占用与全局容量必须一起原子检查/预占，不能先await再分别更新。

- 用户已锁定partial不持久化：实时delta与已提交Message是不同事实；文本到达但协议校验/提交失败也不进入Session或后续上下文。

- 当前Session只内存保存且_busy只对同一个对象生效；服务需要统一Run接纳和持久化恢复，不能每请求各自创建Session后依赖_busy防并发。
- Agent.run当前没有中间提交或事件出口，Provider只有complete(stream=False)。仅在路由外包SSE或结束时dump历史，不能兑现roadmap。
- 数据库错误应停止Run，不得落入Executor的通用异常清洗后被当作普通工具错误继续运行；终态数据库提交与通知必须有先后规则。
- roadmap已明确断连取消、无事件重放、崩溃interrupted与配对修复。未决的是partial持久化保证和不同Session并发，分析稿将其显式分开。
