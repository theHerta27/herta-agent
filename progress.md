# Herta Agent 工作记录

## Phase 6 阶段1实施（2026-09-22）
- 用户授权先固定 Phase 5 再只实现阶段1。核对 Task 10–12，178项 unittest、Ruff check、74文件 format check、diff check 通过。Phase 6文档/素材曾用专属 stash 保留，Phase 5提交并推送6679dfeda6535d4e33d8e24e7d042d0b5f6f7b84，远端SHA一致，确认干净后创建phase-6-ui并恢复素材；无merge。
- Ruling: 沿用户指定分支原位实施，不额外建worktree；继续用本文件作ledger，不执行Linux/Bash工作流。原因是明确的分支顺序与Windows环境；代价是需明确保留原有未提交资料。
- Pre-flight: 本轮只有阶段1，唯一消费接口为既有create_app/ServiceSettings/health/Manager.shutdown；后续会话、Run与设置桥不提前实现。
- RED: 生命周期空契约的5项测试中4项失败（尚无启动、就绪、异常处理与退出等待）；真实Electron缺入口测试失败。随后实现安全窄Preload、最小窗口、Python host与自管进程。
- Ruling: Node22.16现有环境选择Vite6.4.3兼容版本；不升级全机Node。Electron官方Windows归档通过既有本机代理下载并校验SHA256；不把代理写入配置。
- Windows实测发现Electron GUI stdin立即EOF，开发命令退出；开发入口测试以未创建真实SQLite复现。Ruling: 仅dev runner→Electron使用Node IPC退出通知，Electron→Python保持计划的stdio协议。无业务API或整体架构调整。
- Stage 1 complete: npm typecheck/lint/build通过；Vitest 9项通过，Playwright真实Electron 6项通过（包含3次启动/关闭、中文空格路径、目录外启动、单实例、缺配置/解释器、意外退出、开发入口）。EOF测试验证实际解释器退出、SQLite重开和其他Python进程不受影响。
- 最后独立审查1项P2：停机失败Promise被永久缓存。测试先确认失败，再清除失败缓存允许重试；完整9项及6项桌面测试通过。无minor遗留。审查未判断阶段2以后、真实API和打包：均不属本轮，继续保留待验收状态。
- 全套178项后端回归保持通过；Ruff check/format check含薄host共75文件；无backend业务代码变更、无真实API。保留8张原素材，未进入阶段2。Phase 6改动保持未提交、未push。

## Phase 5 Task 10–12实施
- 沿用户手动提交后的33f10e2基线实施最后三项，不调整12个Task，不自动提交/push/merge；无真实API。
- Task 10 complete：先写API测试确认缺模块失败，最小实现后6项及完整163项通过。缺聊天配置保留health/历史、运行503；独立入口只允许loopback单worker。
- Task 10 Ruling：PyPI官方源连续TLS失败，uv通过公开清华镜像安装并锁定FastAPI/Uvicorn；原有依赖版本未升级。代价是后续安装依赖该镜像可达性。
- Task 11 complete：SSE测试先因events缺失失败，UTF-8帧、有界队列、发送期限、接纳断连所有权实现后8项/完整171项通过。额外rag摘要只在服务适配层派生，终态不可被通知失败改写。
- Task 12：6项真实socket测试先因probe不存在失败。实现离线子进程夹具后，修正临时事件迭代器提前关闭连接和SQLite测试连接句柄未关闭；最终6项通过（11.251秒）。
- Task 12 Ruling：Windows venv的python.exe是启动器，杀启动器无法可靠证明实际解释器退出；测试通过stdin触发实际解释器os._exit(91)，不执行finally/lifespan，再等待启动器回收。这是真实进程骤停和SQLite恢复验证，不宣称验证任意系统强杀方式。清理此前夹具遗留进程后不使用Linux信号。
- 独立只读审查发现P2：取消后仍可发送队列中尚未显示的delta。新增test_cancelled_run_does_not_send_buffered_delta实际复现取消终态后仍有llm.delta（RED），发送前过滤后9项SSE测试通过（GREEN）。首轮测试夹具发送期限过短，调大该屏障测试期限后确认真实缺陷；生产期限未改。
- Final: fixed 取消后缓冲delta仍发送 — 上述测试RED→GREEN，完整178/178通过（25.977秒）；无待处理minor。没有第二次审查或扩展功能。
- Final: Ruling: 审查不判断真实供应商流式/RAG效果与任意系统强杀方式 — 保持原验收边界：离线fixture只证明协议、实际socket和os._exit后的恢复；错误外推会误认为真实服务或所有终止方式已验收，文档明确不作该声明。
- Task 12 complete：本批21项（API6/SSE9/socket6），累计178项，原93项保留；Ruff check、format --check（74文件）、git diff --check均通过。文档、教程、12项清单及规划记录已更新，Phase 5完成。保留工作区不提交/push/merge，不进入Phase 6。

## Phase 5 Task 8–9实施
- 用户已手动推送e8d0fa7并要求下一步；沿现有计划执行Task 8、9，完成后停，不进入FastAPI装配，无真实API调用。沿用executing-plans/TDD及当前分支。
- Task 8 complete：测试先因streaming模块缺失失败；实现字节级SSE帧、工具分片累计、结束校验和256KiB帧/4MiB总响应上限。补测CR-only末帧先失败后修复；8项定向与完整150项通过。
- Task 9：5项测试先因streaming构造参数缺失失败；单一Loop的请求位置接入stream，增量只发observer。实现后5项及完整155项通过；新增HTTP流式、知识Tool与真实PersonaContextBuilder组合离线验收。
- 独立审查：公共AsyncIterator契约不要求aclose，原清理代码错误地强制调用。新增测试观察AttributeError后改为仅在可用时关闭；真实HTTP生成器关闭保障不变。
- Task 9 complete：最终Provider定向8项、Runtime定向7项及完整157项通过；Ruff check与format --check通过（65文件）。停止于Task 9，不进入Task 10；更新文档后提交当前分支。


## Phase 5 Task 4–7实施
- 用户继续下一批；按现有依赖执行Task 4–7，完成验证后提交/push当前分支，不merge，不调用真实API。沿用executing-plans和TDD，保留既有工作区及根记录。
- Task 4 complete：新测试先因TurnIO模块缺失失败，实现后定向3项/完整121项通过。单一Loop委托提交，MemoryTurn保持原CLI行为；restore只接收闭合历史。
- Task 5 complete：事件测试先因events模块缺失失败；实现后定向3项/完整124项通过。参数验证成功才发tool.started，提交后发completed，基础设施错误不清洗为工具错误。
- Task 6 complete：接纳测试先因service模块缺失失败；定向5项/完整129项通过。预占在await前，跨Session并行，满额拒绝，user只入库一次，正常及失败终态释放名额。
- Task 7 complete：失败测试复现cancel/shutdown缺失和admit取消留下created Run；实现接纳所有权、终态优先级与关闭等待后通过。补齐任务创建失败、关闭超时、通知失败不改变终态等测试。
- Final review：独立审查发现取消被模型适配器吞掉后仍执行新工具；测试先实际观察工具执行（RED），再在PersistentTurn.append/RunHandle.emit检查取消标志；模型/handler吞取消两种路径均通过。
- 最终定向3+3+5+13项，完整142项通过；Ruff check和format --check通过（62文件）。Task 4–7已完成，停止于Task 7，按本批授权提交/push，不merge。没有真实API调用，真实RAG仍未验收。


## Phase 5 Task 2–3实施（2026-09-21）
- 本轮授权连续完成Task 2、3并提交/push phase-5-service，完成后停止。沿用当前分支和根目录执行记录，不引入额外工作树或Linux脚本。
- Task 2：6项行为测试先观察恢复接口缺失/非成功终态拒绝/缺少接纳门禁的失败；最小实现后定向6项及全套112项通过。恢复显式调用，单事务按持久历史闭合pending，已完成结果不修改，不执行工具。
- Task 3完成：6项线程/取消测试先确认事件循环阻塞、writable缺失、close泄露底层异常等失败；实现专用线程及受跟踪Future后全部通过。锁等待1秒、重复取消、close排空、故障停止写入已覆盖。
- 原Task 1故障测试保留回滚断言，重试须关闭重开与恢复；这是Task 3新增故障停止写入语义，未弱化原93项回归。
- 最终：恢复6项、取消6项通过，完整118项通过（10.860秒）；Ruff check与format --check通过（52文件）。独立只读审查未发现重要正确性问题，另行运行12项定向测试通过。
- Task 2、3 complete；Task 4–12保持未实施。按用户授权提交并push phase-5-service，不merge，不调用真实API。


## Phase 5 Task 1实施（2026-09-21）
- 用户仅授权Task 1，不提交、不push、不merge、不执行后续任务。从phase-4-rag/ae72541创建phase-5-service，保留此前未提交设计文档。
- 先读现有Message/Session/测试及Task 1契约，重跑原93项全部通过；新增13个存储行为测试，首次因storage模块不存在而按预期失败，再实现后13项通过。
- 新增storage包和test_session_store.py；故障触发器验证真实SQLite事务回滚，包含中文路径、重复调用ID、非法消息、状态、配置白名单、版本不匹配等。
- Ruling：按用户限定停在Task 1，非成功终态/中断恢复不实现（Task 2）；async接口当前内部同步短SQL，线程与取消保障不提前实现（Task 3）。原CLI与Agent仍只用内存。
- Ruling：使用当前项目中新建的用户指定分支和已有progress/task_plan作为执行记录，不复制未提交设计到另一工作树，不使用Linux脚本或自动提交。
- 首轮Ruff发现新文件排版/长行，已针对新文件格式化；最终定向13项通过，全套106项通过（原93项保留），Ruff check通过，format --check共50文件通过。独立只读审查未发现Task 1范围内具体缺陷。新增docs/phase-5-task-1.md说明数据入口和未实现边界，停在Task 1。

## Phase 5设计讨论（2026-09-21）
- 用户确认整体设计，仅授权实施计划。新增phase-5-plan.md，按SessionStore→Runtime边界→RunManager→Provider真流式→FastAPI/SSE与Windows集成拆为12任务，明确文件、接口、失败测试和验收。未编码、安装、启动服务或执行API调用。
- 用户确认并发方案A，授权默认数值/同步细节按现有配置体系设计。收敛设计建议默认4（可配置1–32），区分接纳容量与Session生命周期；新增phase-5-design.md，仍未编码。
- 用户确认partial方案A：仅SSE展示；assistant必须完整协议校验并提交成功才进入历史。已更新分析与验收条件，尚未编码；下一项讨论不同会话并发。
- Phase 4实际已按用户要求提交并push ae72541；历史条目中的“未提交”描述当时状态，真实RAG效果仍未验收。
- 用户授权本轮分析，不授权编码。核对Agent.run、内存Session、非流式Provider、工具执行、Context/Persona、RAG装配与roadmap。
- 新增docs/phase-5-analysis.md，建议RunManager + SQLite SessionStore + 通用提交/事件边界，保留一个Loop。
- 不重新询问roadmap已经规定的断连取消、不重放、重启interrupted；先询问未完成回答的持久化程度，不同会话并发随后讨论。
- 本轮无业务代码、依赖安装、服务启动、模型API调用或Git发布。官方文档浏览与本地分析不构成真实效果验证。

## Phase 4 工程实现（2026-09-20）
- 用户确认独立远程Embedding与Key边界后授权编码，从Phase 3建立本地phase-4-rag。
- 先观察ingest/store/retriever/adapter/tool/CLI测试失败，再实现相应行为。只新增NumPy到项目venv和锁文件；网络受限后使用批准的安装权限，未修改其他项目环境。
- 完成白名单切分/来源、不可变索引/原子指针、精确余弦排名/过滤说明、单一远程适配器、search_knowledge装配、独立检索及正式聊天评测。
- 独立局部审查发现NPZ载入、bool数组、来源行号类型问题，已复现并修复；补齐总HTTP期限，保留Windows Runner取消路径。
- 更新README、架构、复用记录和Phase 4教程。93项离线测试覆盖原52项回归；真实服务环境未配置，实际模型质量与阈值校准未执行。
- 原始两份材料hash未变；main=32f2c29、phase-2-tools=7e5fa96、phase-3-context=66a5d17未移动。不提交、推送、合并或进入Phase 5。

## Phase 4 设计与资料准备（2026-09-20）
- 用户明确“仍先不要编码”，本轮只新增knowledge/evals资料及设计/计划文档，backend和依赖文件未变。
- 按Superpowers brainstorming与writing-plans收敛已确认范围；未开始实施任务、安装依赖、建库或调用Embedding。
- 完成knowledge/herta.md（20单元）、sources.json、README；完成evals/rag/questions.jsonl（28题）及评测说明；dev17/check11。
- 资料问题分为13可回答、4跨段、7不足、4无需检索；required_evidence绑定稳定K单元，公开检查题不冒称盲测。
- 静态验证全部JSON可解析、ID唯一、证据引用有效、source spans合法、原始快照SHA256不变；git diff --check通过。没有执行新业务测试或声称检索效果已通过。
- 完成docs/phase-4-design.md与phase-4-plan.md，保留单一Embedding适配器的未决执行方式；已单独询问用户，其他工作先完成。
- 当前文档/数据未提交或推送，停在设计阶段。

## Phase 3 完成（2026-09-20）
- 用户确认 A 后，更新设计并写实施计划；从 Phase 2 新建本地 phase-3-context 分支，未移动 main/phase-2-tools。
- 先写 Context/Persona 和 CLI 测试，观察模块缺失、参数未支持等预期失败，再实现并验证。初次 Ruff 提示长行与未使用导入，格式化/导入修复后通过。
- 新增 ContextBuilder/ContextSnapshot/StaticContextBuilder 与 PersonaContextBuilder；Agent 只委托构建并记录哈希，不认识角色文件。CLI 两条 Provider 装配路径均要求 soul 成功加载。
- 新增 persona/soul.md、11 条 persona_evidence.jsonl 与来源说明；全部读完的两份原始材料保留原位，SHA256 复核一致，证据行号有效。
- Windows 完整 52 项 unittest 通过（Phase 2 的 42 项保留），Ruff check 与 format --check 通过（27 个 Python 文件）；独立审查无问题且再次验证 52 项通过。git diff --check、教程文件链接检查通过。
- CLI 实测工具两步闭环与 context_sha256；测试验证人格加载失败不调用模型、修复后同会话恢复、文件中途修改不影响本轮、下一轮重载、HTTP 每 Step 注入全文、BOM/CRLF 和中文路径。
- 已更新 README、架构、复用记录，新增 phase-3-walkthrough.md。真实供应商及人格生成表现尚未验证；未加入 RAG/Memory/Skills/MCP/UI。
- 工作区改动未提交或推送；main=32f2c29，phase-2-tools=7e5fa96，停在 Phase 3 等待后续指示。

## Phase 3 开始（2026-09-20）
- 用户授权 Context Builder + soul.md，明确 Runtime 解耦且不做 RAG/长期 Memory/Skills/MCP/UI。
- 起点为已推送的 Phase 2 commit 7e5fa9634fb3e84ac230b3350db7ca5a41ecc446；开始时工作区干净。
- 阅读当前架构、Runtime、CLI/测试接口及两份角色材料全文；基线 42 项测试、Ruff check 通过。
- 按既有设计采用每 Run 全文快照；向用户询问 Persona 加载失败策略，其余工作先做设计和来源整理。

## Phase 2 实施与交付
- 用户明确选择 Ctrl+C 取消当前轮并保留会话；据此采用 Windows 标准 asyncio.Runner，多轮共用事件循环和 Session。
- 在 phase-2-tools 分支原地实现，保留用户中文学习注释；未修改 Hermes 参考源码、原始语料或系统环境。
- 先增加工具、循环、HTTP 与 CLI 测试并观察预期失败，再逐步实现；基线 26 项扩展到 42 项。
- 完成 ToolSpec/Registry、Pydantic schema/严格校验、Executor/统一结果、echo、多 Step 回填、预算与取消闭合。
- Windows 子进程验证模型和工具 SIGINT 取消后清理及第三轮同会话继续；补充实际 main 单条消息取消退出 130 的验证。
- 独立审查没有阻塞问题；两项低优先级覆盖建议（退出 130、超量调用零执行）均已补齐。
- 实测离线 echo 两步成功、工具超时回填、max_steps=1 停止；编写 phase-2-walkthrough.md 并更新 README、架构状态与复用记录。
- 真实模型未联调；网络合约由 MockTransport 验证。Phase 3 未开始。
- 最终验证：42 项 unittest 全部通过，Ruff check 与 format --check（23 个 Python 文件）通过，git diff --check 通过。本轮改动留在本地 phase-2-tools 分支工作区，未提交或推送。

## Phase 2 设计核对
- 用户要求启动 Phase 2，明确面向 Windows、架构疑点先问。
- 检查到 agent.py 和 session.py 中的用户中文注释；保留，不覆盖。
- 当前基线重新验证：26 项 unittest 与 Ruff check 全部通过。
- 已提交澄清问题：Ctrl+C 取消当前轮后保留 Session，还是沿用 Phase 1 退出 CLI。
- 编写 docs/phase-2-design.md 草案，区分已确认架构与待决定的取消交互；尚未写 Phase 2 业务代码。

## Phase 1 最终交付与验证
- 已完成最小 Python Runtime、内存历史、Provider 接口、Demo/HTTP Provider、CLI、配置与清晰异常。
- Phase 1 的正常 Run 只有一次模型调用。工具循环、预算耗尽路径、Persona、RAG、API、SSE 和桌面尚未实现。
- 最终运行 `python -m unittest discover -s backend/tests`：26 项全部通过（包含 Windows 中文管道修复后的回归）。
- `ruff check backend` 通过；`ruff format --check backend` 通过，15 个 Python 文件排版一致。
- 默认离线中文单轮启动成功；交互两轮与退出由 CLI 子进程测试验证。
- 安装后的模块及 herta-agent 命令能从 D:\Desktop 运行；隔离模式 sys.path 没有 Hermes 路径。
- `uv sync --project backend --extra dev --python 3.12 --locked --offline` 成功，锁文件与安装一致。
- README 和 Phase 1 教程的链接/函数行号已核验；后续阶段业务目录未创建。
- 真实供应商联调未执行：没有使用任何真实模型 Key，也没有发真实模型请求。HTTP 契约测试使用 MockTransport。
- 完成 docs/phase-1-walkthrough.md、README；更新架构状态和复用记录，无 Hermes 业务代码移植。
- 本阶段已停止，等待用户确认 Phase 2。

## Phase 1 开始
- 用户“下一步”授权进入 Phase 1；读取已有计划、发现、架构与工作记录。
- py 启动器未发现已注册 Python，继续检查 PATH 上的解释器；不修改现有 Hermes 环境。
- 沙箱首次下载 Python 被网络权限阻止；通过工具自动审批的联网权限在项目内继续下载。
- uv 默认全局缓存不可写；后续所有 uv 命令显式指定项目 .local/uv-cache。
- 已建立 Phase 1 消息/会话/Provider/循环骨架与 CLI，准备依赖安装和离线测试。
- 独立环境：Python 3.12.13；uv 生成 backend/uv.lock 并将项目 editable 安装到根目录 .venv。
- 首轮 26 项 unittest 全部通过；Ruff 发现测试闭包绑定、排版及 CLI input 的异步检查提示。
- 修正测试循环闭包绑定并统一排版。教学 CLI 的输入阶段无后台任务，保留同步 input 并作精确单行豁免，避免使用不可取消的 stdin 工作线程。
- 增加 timeout 布尔值拒绝和 API Key 换行校验；Ruff check 已通过。正在编写教程与运行说明。
- 最后从项目目录外实测发现 Windows 管道编码造成中文显示乱码；修复 CLI 重定向标准流为 UTF-8，并将交互测试改为中文且不依赖 PYTHONIOENCODING 环境变量。

## 2026-09-18
- 读取完整用户需求并检查项目目录。
- 使用 planning-with-files-zh 技能建立三份进度记录。
- 开始检查参考源码和许可证。
- 已记录压缩包哈希，并校验 ZIP 路径不会越出 references；正在解压到独立参考目录。
- 首次工具调用工作目录不存在，未执行；已修正。
- 完成解压和根 MIT 许可证核查；定位实际循环、工具注册/派发和 Persona 入口。
- Windows 下 rg 路径通配符未展开；后续改用目录检索或 rg -g。
- 已追踪循环、持久化、超时与中断；开始编写三份正式文档和 Phase 0 手动复现说明。
- 部分大段工具输出被截断，改为读取关键函数附近的小段并定位精确行号。
- 完成三份正式文档及 phase-0-walkthrough.md：包含目录职责、执行链、精读函数、PowerShell 复现步骤和自测问题。
- 新增 .gitignore；根 LICENSE 原样复制到 LICENSES/Hermes-MIT.txt。
- 静态阅读 registry 与 sequential timeout 的测试文件，未执行其测试或导入 Hermes。
- 开始核验文档行号、参考源码与 ZIP 一致性、原文件哈希和 Phase 0 范围。

## 最终静态核验（已通过）
- 4 份 docs 文件存在且非空，Markdown 代码围栏成对。
- 文档里的显式 .py/.toml 行号引用路径存在且没有越界，共涉及 24 个不同源码文件。
- 这 24 个源码文件逐项与 ZIP 内对应文件做 SHA256 比较，全部一致。
- ZIP 内 13,888 个文件均能在 references 中找到；该项检查完整解压存在性，不声称逐个审计全部代码。
- 3 份原始输入 SHA256 与开始记录一致，未改动原文件。
- LICENSES/Hermes-MIT.txt 与参考根 LICENSE 哈希一致。
- backend、apps、persona、knowledge、.venv、.local 均未创建，范围仍为 Phase 0。
- 手工对照核心分支：循环 1520/1555、工具结果 1074/1075、system 注入 1155、取消 109、许可证原文。
- 新增源码快捷链接指向前述已验证的 5 个函数。

## 验证边界与交付状态
- 未运行 Hermes、未导入其模块、未安装项目依赖、未调用真实模型。
- 本阶段不含业务代码，未运行 pytest；上述是文档与来源静态检查，不是 Runtime 功能测试。
- 三份正式分析文档及手动复现教程已交付。Phase 0 完成，停在这里等待用户确认，未进入 Phase 1。

## Phase 6 设计阅读（2026-09-22）
- 用户仅授权设计与两个文档，不创建Electron工程、不安装依赖、不改Runtime。沿用文件规划记录，当前phase-5-service仍包含上批未提交实现和用户新增frontend素材，不把HEAD当完整Phase 5基线。
- 已阅读实际service/storage/runtime接口、Phase 5设计/12项计划/walkthrough；旧architecture中Settings API、事件arguments/duration/final_message_id是规划字段，实际不存在。design/plan开头“Task 1–9”也是过期批次描述。
- 参考图各1张，均为浅色；Codex侧栏约占21%，正文/输入区同轴且留白，Cyrene参考图是Work界面，不能当Herta要复制的聊天需求。
- 已查看全部8张Herta素材；bust 900x764、avatar 1490x1490、rag-reading 1024x1024首选，其余先不用。bust含原图文字标识，不作为Herta应用品牌。
- Cyrene已阅读ChatPage装配、ChatComposer、ChatMessageList关键渲染/滚动/Activity、Sidebar、RunStageIndicator、StatusFloat和theme/tokens/base；只学职责和布局，不复制庞大业务/资源/浮动装饰/未知状态默认成功逻辑。
- ui-ux-pro-max搜索的营销落地页、活泼色块、远程英文字体建议不匹配，不采用；采用对比度、键盘焦点、reduced motion、排版和稳定滚动原则。拟议token关键文字对比度已离线计算达到4.5:1以上。
- 用户已确认Settings：可改非敏感Base URL/模型名，Key仅读环境，无活跃Run时重启桌面自管后端。
- 后端可支撑核心UI；列表无标题且按ID分页、无CORS/Settings/结构化启动握手、错误原因多为run_aborted、无SSE重放。设计使用有限桌面传输/进程适配，不擅自扩展业务API。
- PowerShell内嵌Python引号导致一次只读图片元数据命令失败，改here-string后读取成功；没有修改图片。

- Phase 6设计交付：新增两份文档，设计覆盖布局/素材/Token/组件/三层职责/状态与实际API缺口，计划7阶段均含可见成果、文件、行为测试和验收。用户确认的Settings决定已写入。
- 自检：两份文档UTF-8正常、代码围栏成对、无TODO/TBD；7个实施阶段；Codex图片尺寸实读为1603×915并修正文案；关键文字Token对比度实算通过；git diff --check通过。无工程代码/依赖/图片修改，无真实API，不重跑既有178项测试，不提交/push/merge。


## Phase 6 阶段2–5交付（2026-09-23）
- 阶段1已单独提交 a36613061886e89d7dd1535ea081ee9fb16e5e28。按本轮授权连续完成阶段2–5，不进入Settings或阶段7。
- 新增会话/流式传输与应用级状态、Sidebar/Welcome/Composer、Markdown回答、工具/RAG活动、取消及持久历史恢复。后端业务源码未修改。
- 行为测试先失败再实现；真实桌面测试发现并修复中文组字事件读取问题。独立只读审查无阻塞发现。提前取消但未找到持久Run时按既定设计保持未知并禁止重复提交，不凭空推断失败。
- typecheck、lint、21项unit、7项真实Electron e2e（含build）通过；178项后端unittest、Ruff check/format、diff check通过。没有真实API调用。
- e2e以测试专用入口注入离线Provider/检索夹具，走真实HTTP、Runtime与SQLite；不把夹具检索当成真实RAG效果验证。
- 本批提交与push仅面向phase-6-ui，不合并；操作结果以Git实际记录为准。
