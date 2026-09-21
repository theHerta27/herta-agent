# Phase 5 收敛设计：本机后端服务

状态：2026-09-21，用户已确认整体设计，现已编写phase-5-plan.md；尚未授权编码、尚未实施。两个用户决策已确定：partial仅SSE展示；不同Session并行、同Session互斥、全局满额立即拒绝。

基线：phase-4-rag / ae72541ea9ea7c64d768d2b469c479a311661828。Phase 4工程已完成，真实RAG服务与效果验收仍待后续配置，不纳入本阶段已验证结论。前期分析见phase-5-analysis.md。

## 1. 目标与范围

将现有Agent暴露为后续Electron/React可用的本机服务：创建/恢复会话、提交Run、流式观察执行、取消、查询持久历史与Run终态。运行于Windows，单进程、单worker、绑定127.0.0.1；不使用Linux信号或fork。全局并发依赖这个单服务实例的所有权，不宣称多进程共享数据库下也有相同保证。

增加FastAPI与ASGI服务入口；SQLite保存会话、消息和Run；Provider支持roadmap规定的真实流式响应。保留CLI、Persona快照、工具预算、RAG接口和原有离线回归。

不实现UI、鉴权/多用户、后台脱离连接续跑、分布式任务队列、SSE重放、自动模型/工具重试、长期Memory或新的RAG功能。配置来自环境和启动参数，不提供运行中修改配置的settings写接口。

## 2. 模块边界

| 边界 | 职责 | 不承担 |
| --- | --- | --- |
| API入口/路由 | 请求校验、HTTP错误、SSE编码与断连通知 | Agent Loop、SQL、检索算法 |
| RunManager | 接纳与容量、Task引用、会话占用、取消与终态裁决 | 模型协议解析 |
| SessionStore | 事务、顺序消息、Run记录、恢复 | 模型/工具调用、SSE发送 |
| Runtime | 唯一的模型→工具→模型循环、Context、预算、配对 | FastAPI、SQLite、角色或RAG硬编码 |
| Provider | 完整响应/增量、工具参数累计、协议验证 | 执行工具、持久化 |
| 事件适配 | 将实际执行节点映射为服务事件 | 用日志猜执行状态、把事件塞进模型上下文 |

Runtime增加可等待的消息提交与执行通知边界；内存实现用于原CLI/测试，服务实现连接Store与事件通道。只有一份Loop。服务已接纳的user不能被Agent再次追加；持久化成功后才更新对应内存历史，存储失败不继续使用分叉的内存状态。

Executor的handler错误清洗只包围工具本身。数据库/基础设施故障必须传播到Run顶层，不转换成可恢复tool error后继续模型请求。工具参数校验成功后才产生tool.started。

## 3. 接纳与并发

服务配置新增严格正整数max_active_runs，建议默认4、范围1–32，作为教学版资源上限；不是性能承诺。用户已授权默认数值与同步细节按现有配置体系设计。

接纳顺序：

1. 验证请求、会话存在与执行配置。
2. 在不可分割的短临界段内检查同Session占用和全局容量，并预占名额。
3. 用一次事务创建created Run与user消息。提交失败释放预占名额，不调用模型。
4. 创建受管理Task；保存running状态，发run.started，然后进入Runtime。

同会话忙返回409/session_busy；其他会话在全局满额时返回429/run_capacity_exceeded。拒绝不写user、不创建Run、不启动等待Task，不用阻塞等待信号量形成隐藏Run队列。短事务的内部串行化不等同于等待执行的Run队列。

created/running、已请求取消但仍在清理的Run都占名额。终态处理与资源清理完成后才释放，不在收到cancel请求时提前放行。每个Run拥有独立Session工作状态、事件通道与取消状态；共享HTTP客户端和只读RAG快照不共享会话历史。

## 4. SessionStore与提交边界

最小记录：sessions保存ID与创建/更新时间；runs保存run_id/session_id、状态、时间、步数、安全错误、context_hash及无Key的配置标识；messages保存message_id/session_id/run_id、会话内顺序、step及完整Message内容。数据库schema具有版本检查，不引入ORM/通用迁移框架。

ToolCall的配对依据其所属assistant消息和调用ID，不能假设供应商的tool_call_id跨所有会话/所有Step全局唯一。读取历史验证角色与调用配对；不以直接写Session私有字段绕过约束。

事务规则：

- Run接纳与user消息一起提交。
- 完整assistant.tool_calls提交后才执行工具。
- 单个完整tool结果提交后才推进下一工具/模型请求。
- 最终assistant与completed状态同事务提交。
- 取消/失败时，待闭合的工具结果与对应终态在事务中提交。

数据库通过专属串行执行边界执行短事务，不在事件循环中直接等待磁盘/锁。可采用标准库sqlite3与单个专用工作线程；这是Store内部I/O适配，不是Run调度系统。事务取消不能被当成线程已经停止：必须跟踪在途提交的实际结果，再释放会话、名额或关闭连接。有限锁等待、异常清洗和正常退出需测试。

写入失败停止Run，不能把未保存结果通知为成功。若连failed终态都无法保存，进程将存储标为不可写并拒绝新Run，查询也不能把旧running记录包装成确定终态；SSE可报告明确标记persisted=false的服务错误后结束。恢复写入由重启时的恢复流程处理，不引入自动重试/后台修复任务。

持久化不保证外部工具副作用与数据库原子一致。工具已执行但结果提交前崩溃，重启只能闭合为结果未知/中断，不自动再执行。

## 5. partial与模型历史

用户已选A：partial仅SSE实时展示，不存数据库、不保存partial快照、不做重启恢复。完整文本到达也不自动成为消息；还必须通过完整协议校验并提交成功。

取消、失败、崩溃时丢弃未提交的assistant缓存；已提交的user、assistant工具调用和tool结果保留。后续模型上下文只来自已提交历史与本Run的Context快照，不从SSE缓冲反向构造。

Persona保持每Run读一次、全Step同一快照；加载失败使已接纳Run失败并保留user，修复后下一Run再读。RAG配置/索引不可用保持显式工具失败，不影响无需检索的普通交流；不因Phase 5改成自动检索或后台建库。

## 6. Run终态与取消

持久状态：created → running → completed / failed / cancelled。服务重启将遗留created/running修复为interrupted，先补齐悬空工具结果再接受新请求。interrupted不表示可以从断点续跑。

取消请求是控制动作，不是立即确认cancelled。RunManager记录请求、取消工作Task、等待Runtime关闭流/清理工具，再提交取消终态。重复取消不重复打断正在进行的最终清理；Task启动前就收到取消也由Manager负责收尾。

完成与取消在同一Run的终态临界段裁决：先进入并完成最终提交的一方决定结果，提交期间不被重复cancel打断。已经completed的Run再次取消返回completed。没有多个终态、终态后新增消息或迟到delta。

SSE断连请求取消该Run，包括首事件发送前。正常服务退出停止接纳，取消并等待受管理任务，完成终态/资源清理后关闭HTTP与DB；异常退出交由下次启动恢复。客户端不自动重发原POST，不自动重试模型或工具。

## 7. Provider流式与SSE事件

Provider输出真实文本增量，并累计完整assistant响应；工具调用的name/id/arguments分片必须全部组装和验证，流结束前不执行工具。总模型请求期限覆盖整个流，外部取消关闭响应。异常结束、缺少合法结束标志或非法工具结构丢弃未提交内容。保留现有complete入口及兼容测试，不另写第二份Loop。

事件公共字段：type、session_id、run_id、seq、timestamp、payload。seq在单Run内递增，SSE id为run_id:seq。模型节点带step/message_id，工具节点带tool_call_id；schema带明确版本约定。

| 事件 | 含义 |
| --- | --- |
| run.started | 已接纳并进入运行 |
| llm.started | 开始一次模型请求 |
| llm.delta | 暂态文本，仅展示，未提交 |
| llm.completed | 该完整assistant消息已校验并提交，不等于Run终态 |
| tool.started | 参数合法，即将执行handler |
| tool.completed / tool.failed | 对应完整tool结果已经提交 |
| rag.retrieved | 已提交知识工具结果的检索摘要、index_id、来源；不表示答案正确 |
| run.completed / failed / cancelled | 已提交对应唯一终态 |
| service.error | 存储等基础设施故障，明确persisted=false，不伪造已提交Run终态 |

正常最终回答先提交消息与Run终态，再按顺序发送llm.completed和run.completed。中间tool-call响应也有自己的message_id，UI不能把多Step文本都当最终回答拼接。

SSE使用有界队列、有限发送等待与心跳；慢消费者超限则断开并请求取消。DB提交/清理不等待客户端永远消费终态。取消之后不再发送新delta，已写到网络的partial不能撤销，但终态和持久历史可说明其未完成；UI展示属于Phase 6。

不保存/重放事件，也不承诺网络恰好投递一次。客户端丢失终态后通过GET核对。rag.retrieved由知识工具结果适配产生，不向Runtime加入工具名判断。

## 8. API与装配

| API | 行为 |
| --- | --- |
| GET /health | 本机服务/存储/能力状态，不探测远程API、不返回Key |
| POST /sessions | 创建持久会话 |
| GET /sessions | 有界分页列表 |
| GET /sessions/{id} | 有序已提交消息与当前Run信息，历史可分页 |
| POST /sessions/{id}/runs | 提交文本，返回SSE；首事件给run_id |
| POST /runs/{id}/cancel | 幂等请求取消，返回当前状态/是否接受请求，不提前承诺已cancelled |
| GET /runs/{id} | 查询持久事实及必要的服务内取消请求状态，二者明确区分 |

接纳前的输入/配置/冲突用普通HTTP错误；接纳后的Persona或执行失败用Run记录及SSE。缺少聊天配置可提供会话读取/health，但运行请求明确拒绝，不偷偷调用demo；离线demo必须显式选择。

服务启动统一建立数据库、执行中断恢复并装配独立聊天/Embedding客户端、Persona Builder、固定RAG快照和RunManager；退出统一释放。默认数据位于项目.local，显式绝对路径支持Windows中文和空格，不依赖cwd。Key继续仅从环境读入内存，所有记录/事件/日志排除Key。

## 9. 验收与下一步

保留93项既有工程测试，并覆盖：

- 会话跨重启恢复，完整消息、工具配对和context_hash正确。
- 不同Session并行互不污染，同Session冲突，全局满额立即拒绝且历史不变。
- 协议错误/取消/崩溃/提交失败后的partial不入库、不进入下一轮上下文。
- 消息与终态事务，存储错误停止运行，在途DB提交取消不造成晚写与提前释放。
- Task开始前取消、重复取消、完成/取消竞争、首事件前断连、慢消费者和服务关闭。
- 中文分片与tool_calls组装、结束条件、请求总期限；不以切割完整文本冒充流式。
- Windows真实本机HTTP连接的事件顺序与断连清理，以及重启interrupted修复。

这些是工程验收，不代表真实供应商流式能力或Phase 4语义质量已验证。当前只有设计文档变更，没有业务代码、依赖安装、API调用、提交或push。

整体设计核对后编写逐任务实施计划，再按用户授权开始实现；不会因两项选择确认就自动跨入编码阶段。
