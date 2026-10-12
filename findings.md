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


## Phase 5 服务验收发现
- SQLite保存事实，SSE保存不了事实；通知失败不能反过来修改已提交completed。生产缓冲有数量、字节和等待期限三种边界。
- 断连所有权必须覆盖admit事务等待；单靠拿到run_id后的finally会留下孤儿Run。
- Windows venv的python.exe可能只是启动器。集成夹具通过stdin命令让真实解释器os._exit，绕过finally，再等待启动器退出；不能把杀启动器等同于服务进程已退出。
- sqlite3连接的with块提交/回滚事务但不关闭连接；Windows测试需显式关闭以释放数据库文件。
- 实际HTTPX事件迭代器必须保留至消费/关闭，不应丢弃临时迭代器后还假定连接保持活跃。
- 官方PyPI本环境TLS失败，通过公开清华镜像安装FastAPI/Uvicorn，锁定原依赖版本；无真实LLM/Embedding调用。

## Phase 6 设计事实
- 当前前端目录只有8张用户素材，尚无Electron/React工程；已有Phase 5工作区不能丢失或用旧HEAD覆盖。
- Session列表默认limit=50、最大100，按session_id升序；walkthrough“默认100”须以app.py纠正。历史after_seq分页，current_run为最近Run，可能已终结。
- llm.completed带完整message；tool.started只有name等公共关联字段，参数来自此前assistant.tool_calls；tool结果在payload.result；rag.retrieved含query/index_id/chunks。终态事件没有详细error，需GET Run。
- Provider/Persona等错误目前常被归为run_aborted；UI不能伪造401/精确原因。标题、近期排序和Tool历史摘要可以由已有GET数据派生，不要求新后端业务接口。
- Electron主进程窄桥接HTTP/SSE可避免新增CORS，同时让切换会话不关闭流；Renderer只呈现，不持有凭据，不执行Agent Loop。

## Phase 6 阶段1 Windows实测
- Windows GUI Electron的stdin会立即结束，不能套用控制台进程的父进程EOF约定；开发脚本使用Node IPC，真正的Python控制台子进程继续使用stdin命令/EOF。
- Windows venv解释器的真实PID与启动器PID不同；必须等stdio句柄全部关闭，不能只看启动器exit事件。连续启动/关闭与EOF测试均确认实际解释器退出。
- Playwright主进程evaluate环境无全局require，测试使用process.getBuiltinModule('module').createRequire。Windows process.title不适合充当测试信号，单实例测试直接验证已最小化窗口恢复。
- 受限工具环境中Electron renderer/GPU进程失败；正常桌面权限运行6项真实测试通过，未关闭contextIsolation/sandbox或webSecurity来绕过。
- stage1.css仅服务最小启动状态页，未接入角色图或开始阶段2Design System。后端已有业务文件无改动。


## Phase 6 阶段2–5交付（2026-09-23）
- 阶段1已单独提交 a36613061886e89d7dd1535ea081ee9fb16e5e28。按本轮授权连续完成阶段2–5，不进入Settings或阶段7。
- 新增会话/流式传输与应用级状态、Sidebar/Welcome/Composer、Markdown回答、工具/RAG活动、取消及持久历史恢复。后端业务源码未修改。
- 行为测试先失败再实现；真实桌面测试发现并修复中文组字事件读取问题。独立只读审查无阻塞发现。提前取消但未找到持久Run时按既定设计保持未知并禁止重复提交，不凭空推断失败。
- typecheck、lint、21项unit、7项真实Electron e2e（含build）通过；178项后端unittest、Ruff check/format、diff check通过。没有真实API调用。
- e2e以测试专用入口注入离线Provider/检索夹具，走真实HTTP、Runtime与SQLite；不把夹具检索当成真实RAG效果验证。
- 本批提交与push仅面向phase-6-ui，不合并；操作结果以Git实际记录为准。

## 2026-10-09 Harness V1
- 本地 HEAD 与设计基线完全一致；只有用户的两个 docs 文件未跟踪，保留不改。
- 后端 179 和前端 22 项基线测试通过，不能复用历史 178 数字。
- 当前环境没有 HERTA_* 配置；已向用户询问公开的真实服务地址/模型，密钥仅本机输入。
- 三个独立职责并行：root Context/API/评测/启动，desktop 仅 frontend，tools_mcp 仅 tools 和 SDK/示例。

## Harness 首版结论（2026-10-09）
- 最新验收范围仅本地。原设计P1真实模型评测及P4真实回归出口暂缓，不能由Mock或本地证据召回替代。
- 用户级DEEPSEEK_API_KEY可用且可由启动器补读；密钥未打印或写入公共配置。聊天默认https://api.deepseek.com/deepseek-flash；HERTA_*显式配置优先。
- 没有找到项目内完整千问权重；本机HF缓存BAAI/bge-large-zh可直接复用，本地指纹与已有远端BGE-m3不同，必须另建版本索引。
- MCP SDK上下文必须在专属异步任务内同任务进入/退出，否则解码异常会取消FastAPI lifespan；已隔离并验证。
- 词法Token估算与实际计费严格区分；extractive-v1摘要不会创造事实但有信息损失。设置候选仅在服务可用/明确缺配置时保存，重启失败恢复旧值。
- 交付证据集中在docs/IMPLEMENTATION_STATUS.md、docs/HARNESS_EVAL_REPORT.md；.local日志不进入Git，可复现。

## 2026-10-11 Cyrene 产品调研
- 用户粘贴材料是既有建议，主要依据README，不能当成已经验证的功能证据。用户本次实际选择以日常陪伴为首要用途，优先级需从文件/知识库转向音乐、语音、提醒及轻量操作。
- 本地Cyrene package.json版本1.2.2，Electron/TypeScript，带独立音乐、Learn、Skills、Memory、Scheduler等模块；当前未启动/测试其程序，没有调用模型。
- Gitee页面无法由浏览工具读取；已核对官方GitHub仓库，旧Playa-0v0 URL重定向至Playa-Cyrene/Cyrene-Agent。线上README/目录与本地快照存在差异，方案以本地源码证据为主，不能称本地是最新Commit。
- 桌面审阅初步发现：Learn的后台进度提取会发送当轮内容到配置模型；文档索引file-ingest明确拒绝PDF/DOCX/XLSX/PPTX，文档生成与索引读取要分别核实。不要照搬“不上传”或多格式通吃的口径。

### 2026-10-11 源码与README差异复核
- 实读 src/main/orchestrator/cyrene-agent.ts:430–481：Chat在options.tools非空时也走runHarnessWithAdapter，仅无工具时走ChatLoop；README的“Chat无工具”已落后于这份本地源码。Herta日常聊天可包含音乐/提醒等必要工具，并继续使用自身唯一Agent.run。
- Scheduler初审：有工具白名单和授权规格指纹，但all-enabled及runner allow_all不能直接作为Herta默认权限策略；关闭后的提醒需要独立生命周期设计。Skills的已证实能力是发现/选择/加载/读取引用，尚未证实自动经验转Skill闭环。

### 2026-10-11 完整审阅结论与推荐方向
- 三项只读审阅完成并交叉核对关键源码。推荐保留Herta Python单Agent.run与Electron，先做日常陪伴闭环，再扩展文件/网页/资料学习和可复用经验。
- Herta executor.py:56仍拒绝所有非read_only工具；音乐播放、创建提醒、偏好写入须扩展有范围的副作用策略，不能伪标只读。main.ts:94关窗退出、:53退出清理后端；托盘、关闭隐藏/显式退出、持久调度是提醒前置工程。main.ts:83拒绝所有浏览器权限，麦克风须窄范围许可。
- 语音应转为普通文本输入同一Harness。Cyrene call-manager.ts:453直接模型请求；照搬会使语音与文字工具能力不一致。Herta需要统一音频协调：录音/朗读时降低音乐，停止时取消合成和播放；首版不承诺连续通话随时打断。
- Cyrene music-tools.ts:97–120播放返回dispatched仅表示命令已发；Herta播放器状态应以实际回读为准。本地音乐入口已有源码机制，但参考副本没有播放器二进制/模型权重，未证明本机可运行。
- 纯提醒按时间直接通知，不每次调用模型；复杂定时任务才进入Harness。Herta宜SQLite记录任务、领取、真实结果与错过策略，避免照搬Cyrene scheduler-runner allow_all或固定success历史。完全退出时不执行，重启须呈现漏提醒。
- Skills与Memory分开：用户明确偏好记忆可早做；任务经验→草稿→验证→版本→复用反馈作为后期学习闭环。Cyrene skill-tools.ts:63/117证实加载正文/附件，没有发现自动创作并验证的闭环。Hermes官方Skills文档证实skill_manage及从任务/资料生成Skill机制，仍需自行实现和验证。
- 文件/个人知识库后续从指定目录和Markdown/文本开始，PDF/Office解析及截图图片消息能力分别实现；不把当前角色RAG/抽取摘要视为通用资料导入/长期Memory。
- 文件导入file-ingest.ts:58明确拒绝PDF/Office；Learn进度提取learn-progress-extractor.ts:85–125把当轮消息发给配置模型。当前范围下不触发这些后台请求，不照搬本地存储等于离线推理的表述。
- 推荐正式路线：基础动作权限/托盘/持久调度→聊天+本地音乐+朗读+按键录音+提醒的陪伴版→轻量桌面/网页/文件助手→个人知识学习与经验证Skills。Live2D与代码协作保持排除，插件市场和多渠道统一后置。

## 2026-10-12 用户最终目标与文件工作台设计
- 用户附件明确五轮路线，第一轮是指定目录的安全文件操作，第二轮为桌面/文档/个人知识，第三轮陪伴，第四轮Skills/MCP/自动作业，第五轮高级能力。第三轮主体已由abd7835本机版本完成；不重做已交付音乐/提醒/语音。
- 附件引用f1f6be0和“全部副作用拒绝”属于旧状态。当前身份白名单允许7个日常工具，执行前再次检查撤销；文件系统权限、审批收据和撤销仍未实现。
- 已读Hermes tools/write_approval.py：候选写入独立持久记录，经审阅再执行；其默认不审批不是Herta要继承的产品策略。agent/file_safety.py明确防御检查不是OS沙箱，原始Windows命名空间在resolve前拒绝，不能把Path.resolve误称安全隔离。
- 下一版应通过Electron主进程文件夹选择器授予root_id，模型/renderer只持有相对路径和不透明ID。保存方案不授予执行权限；具体动作和文件快照绑定审批，后续Skills也不应绕过。
- 所有测试目录需为专用临时夹具，产品未操作真实下载目录。当前只进行静态设计，既有243/46/14是上一版证据，不能作为文件功能验收。

## 2026-10-12 音乐业务退役
- 用户指定的新docs/herta-agent-plan.md含现有音乐能力、外部播放器章节、V2.6外部控制及架构业务列表，需要移除；语音音量/音色/音频播放属于独立语音规划，保留。
- CompanionStore在同库创建tracks，并从settings读playback与preferences.volume；提醒/记忆不能通过重建数据库清理。旧字段仅兼容读取，既有音乐元数据留存但运行层不暴露。
- AudioCoordinator同时管理音乐与语音；CompanionRuntime启动时创建音乐Audio并根据快照播放，focus触发播放。保留生成号、blob释放、语音停止/录音协调与订阅，删除音乐部分。
- 主进程有herta-media协议、导入文件选择器和playback-report IPC；CSP含herta-media许可。移除这些不影响现有voice IPC与blob音频许可。

## 2026-10-12 V2.1实施与theHerta资源
- 用户当前目录有1个GPT .ckpt（155313011字节）、1个SoVITS .pth（172765299字节）及5种情绪中文参考音频；均为48kHz单声道，约3.25–7.62秒。原始大黑塔.zip保留可恢复备份。
- .ckpt起始PK，.pth起始ASCII 06但zipfile可读取内部目录；不能直接将自定义头视为坏文件，需对照官方process_ckpt识别版本，不改字节或绕过pickle保护。
- 当前模型目录和ZIP尚未被Git忽略，已补精确ignore规则防止用户权重进入源码提交；既有Piper/Whisper保留。
- 按用户现行规划先交付只读桌面/磁盘工作台，写入/移动用户普通文件仍为V2.2，不提前实现。音色资源仅在用户指定范围内规范化，区别于产品普通文件自动操作。
- 原先对.pth头部异常的推测已更正：GPT-SoVITS官方v2ProPlus使用ASCII06；两组权重仅在内存适配并weights_only加载，未修改原始字节。
- 音色规范目录models/voice/the-herta/v2proplus，原ZIP7成员哈希与整理后文件逐项吻合；参照文本取原文件名，未人工核听；角色推理尚未接入。
- Windows仅属性目录句柄不阻止替换，实际竞态测试复现；最终使用GENERIC_READ + SHARE_READ + BACKUP_SEMANTICS + OPEN_REPARSE_POINT锁定目录及祖先，测试证明rename被阻止；不得退化为普通路径快照。

## 2026-10-13持续实施
- V2.2-V2.6功能已接通，仍以Hermes工程结构为参考，Cyrene仅产品启发；无音乐/Live2D/代码协作。
- 已有角色模型真实CUDA推理通过，所有原始音色权重与录音保留；独立stdio环境采用安全加载。
- 私人发行目录約12GB，uv启动器必须重新建立为可移动环境，不能只修改pyvenv.cfg；真实移动、取消及桌面重开通过。
- 仅本地Provider/模型/夹具验收，未进行真实聊天服务或远程Embedding测试。
