# Phase 5 初步分析：后端服务、持久化与执行事件

状态：2026-09-21，设计讨论稿，未批准实施。未写业务代码、安装依赖或创建服务。基线为Phase 4 commit ae72541ea9ea7c64d768d2b469c479a311661828；Phase 4工程完成，真实RAG服务合约、效果评测和阈值校准仍待配置后验收。

## 1. 本阶段要兑现的能力

后续桌面UI能够创建/重新打开会话，提交一轮输入，观察模型和工具的执行进度，取消当前轮，并在服务重启或HTTP断连后查询可靠的历史与Run状态。成功标准是这些事实一致，而不只是接口能返回200。

范围：本机单用户、单服务进程，FastAPI、SQLite SessionStore、RunManager、SSE及roadmap已经预定的Provider文本流式入口。保留原CLI使用方式与离线测试。不加入Phase 6 UI、鉴权系统、多用户、分布式队列、后台任务续跑、SSE历史重放或新的RAG算法。只绑定127.0.0.1，不做公网部署。

## 2. 实际代码与roadmap之间的差距

| 当前事实 | Phase 5需要解决 |
| --- | --- |
| Agent.run直接调用Session的同步内存方法 | 引入可等待的持久化边界，关键消息提交后才推进下一步 |
| Session仅有_messages、_busy、_pending；无恢复入口 | 从已验证的有序记录恢复，不从路由直接修改私有字段 |
| Session._busy只保护同一个Python对象 | 服务统一接纳Run，防止不同HTTP请求各自加载同一会话并同时运行 |
| RunResult只在成功时返回；没有持久Run对象 | 独立run_id、开始/结束时间、状态、错误、步数及context_hash |
| Provider.complete使用stream=False | 真正解析流式响应，区分文本delta与完成后的Message，累积完整tool_calls后才执行 |
| Executor把未知异常变成工具失败 | 持久化/事件基础设施异常不能被误吞成可恢复工具错误 |
| CLI负责HTTP客户端、Persona与RAG装配 | 服务生命周期拥有这些资源，路由不逐次创建客户端或重建索引 |
| RAG有固定索引快照和结构化来源 | 复用现有Tool；事件展示实际结果，不改变检索触发方式或宣称效果已验证 |

阅读范围：runtime/agent.py、session.py、messages.py、context.py、persona.py、llm/base.py及openai_compatible.py、tools/executor.py及search_knowledge.py、CLI装配、RAG服务接口、配置/依赖与相关测试；architecture.md、Phase 1教程、Phase 2–4设计及进度记录。

## 3. 三种接入方式

1. 路由直接await Agent.run，结束时一次存库：改动少，适合只有请求/响应的原型；不能保住执行中已完成的工具结果，也不能兑现roadmap的中途事件与崩溃恢复。
2. **建议：RunManager + 小型SessionStore + 通用Runtime通知/提交接口**：保留一份Loop，由服务层承担持久化与连接生命周期，按消息边界提交。满足本阶段需要。
3. 将全部事件作为数据库日志，并从事件重建会话：适合完整重放需求，但引入事件版本、恢复与重放协议，本阶段没有这个需求，不采用。

以上是建议，尚不是用户已批准的最终实现方案。

## 4. 职责边界

- FastAPI路由：校验请求、映射HTTP错误、输出SSE；不复制Agent Loop。
- RunManager：接纳/拒绝Run、持有Task、会话占用、取消请求、唯一终态裁决、服务退出清理。
- SessionStore：SQLite事务、会话与有序消息、Run事实、重启恢复；不调用模型。
- Runtime：继续负责模型→工具→模型、预算、工具配对和Context Builder。通过小型接口提交消息并报告执行节点，不导入FastAPI、SQLite或SSE响应对象。
- Provider：真实文本增量、协议分片累计、最终响应校验；只有完整且合法的ToolCall能进入执行器。
- 事件适配层：将通用执行节点映射为外部事件。rag.retrieved来自知识工具适配层的实际返回值，不在Loop硬编码search_knowledge分支。

需要修改Runtime接口以暴露可靠提交点，但不改变人格和RAG职责。CLI可使用内存实现/空事件接收器；服务使用持久化实现。用户消息的首次追加只能有一个所有者，不能RunManager存一次、Agent.begin_turn再存一次。

## 5. Session持久化建议

沿用roadmap中的SQLite，不重新选数据库。最小事实模型是sessions、runs、messages三类记录；Message序号、message_id、run_id、step与状态属于存储元数据，传给模型仍只使用Message.to_wire允许的字段。

建议保存边界：

1. 接纳Run与保存user消息在同一事务完成；输入不合法/会话忙则不追加消息。
2. 完整assistant.tool_calls提交后才执行工具；每个工具结果提交后才推进下一个动作。
3. 最终assistant与completed状态在同一事务提交，之后才发run.completed。
4. 取消/失败补齐pending工具结果并提交终态；不自动重试有副作用的工具。

不要只在Run结束时dump整个Session，也不要把SSE当数据库。数据库操作采用明确的异步边界、有限锁等待和短事务；SQLite驱动/线程封装属于实现取舍，无需用户为库名决策，但必须验证取消时写入不会在释放会话后偷偷继续。

数据库故障时停止推进Run；不能承诺已经持久化failed。保留故障状态、禁止该会话继续写入，待存储恢复或重启恢复后再继续。事件发送失败不能回滚已经提交的事实。消息入库不代表与外部工具副作用实现了分布式原子性；崩溃窗口只能记录中断/结果未知，不重复执行工具去猜结果。

Persona按现有约定在每Run加载一次；失败保留已接纳的user消息、Run失败，修复后新Run再读取。记录context_hash而非把system写入会话历史。RAG不可用保留明确工具失败，普通交流仍可进行。

## 6. Run生命周期与取消

建议持久状态：created → running → completed / failed / cancelled；重启恢复把遗留非终态改为interrupted。取消请求与最终cancelled不同：先提出请求，关闭模型流/清理工具、闭合配对并持久化后才确认终态。

已有roadmap决定：

- 同Session只允许一个活跃Run，冲突拒绝，不排队。
- 断连取消对应Run，不让生成在后台自动继续。
- 取消幂等；已完成的Run再次取消返回其原状态。
- 崩溃后标记interrupted，修复悬空工具配对，不恢复执行或重放工具。

需要覆盖Task尚未开始就被取消、取消与最后提交同时发生、重复取消、取消期间再次断连。RunManager负责最终裁决，不能只依赖Agent finally，也不能收到cancel请求就立刻释放会话占用。正常服务退出先停止接纳，再取消/等待清理，最后关闭客户端与数据库；硬退出交给下次启动恢复。

用户已确认不同Session可并行，受服务级全局活跃Run上限保护；同Session仍互斥，满额立即拒绝，不排队，见第9节。

## 7. SSE与模型流式的两个层次

roadmap已把Provider流式入口列入Phase 5。建议遵循：SSE承载执行进度，llm.delta必须来自真实Provider增量，不能把完整回答切字符假装流式。已有complete路径保留兼容；内部尽可能共用解析验证，避免第二份Loop。

初步事件集合：run.started、llm.started、llm.delta、llm.completed、tool.started、rag.retrieved、tool.completed、tool.failed、run.completed、run.failed、run.cancelled。llm.completed补足单次模型消息完成边界；它不等于整个Run完成。每条含type、session_id、run_id、递增seq、timestamp、payload；模型事件另含step/message_id，工具事件含tool_call_id。

- delta是暂态展示；完整Message通过协议校验并提交后才算持久事实。
- tool.started只在参数校验成功、即将执行时发；非法参数直接tool.failed。
- tool.completed/failed在对应工具结果持久化后发；rag.retrieved不能冒充答案质量判定。
- 终态提交成功后尝试发唯一终态事件，无法保证断开的客户端收到。
- 有界队列与有限发送等待；慢客户端长期消费不了则结束连接并触发取消，不无限缓存、不静默丢关键事件。终态保存不依赖队列有空位。
- SSE心跳仅维持连接，不伪造执行进度；不输出模型隐藏推理或凭据。

继续采用POST /sessions/{id}/runs直接返回SSE；收到run_id后可POST取消。首事件前断连也必须清理已接纳的Run。GET Session/Run用于事后核对，不自动重发POST；不实现Last-Event-ID恢复。创建Run与另行订阅的双接口可服务脱离连接的后台执行，但与当前断连即取消目标相比会增加订阅窗口，不建议本期引入。

## 8. API最小范围与验证

沿用GET /health、POST/GET /sessions、GET /sessions/{id}、POST /sessions/{id}/runs、POST /runs/{id}/cancel、GET /runs/{id}。建议本期不做PUT /settings：Key继续只读环境、服务/Persona/RAG配置不做运行中热改；health只给安全的能力/可用性信息，不探测远程API、不返回Key。

HTTP接纳前发现的静态请求/模型配置错误用普通错误响应；已接纳Run的Persona/执行错误写入Run并经SSE报告。不要在响应headers发出后尝试改HTTP状态码。

保留既有93项离线回归，补充：重启续聊、消息/Run事务失败、工具已声明但未完成时崩溃、同会话并发冲突、Task启动前取消、完成/取消竞争、关闭服务、SSE事件顺序与边界、慢消费者、真实本机HTTP断连。Provider用分片MockTransport验证中文、tool_calls累计与异常结束；本机HTTP测试不等于真实供应商验证，不补做Phase 4效果验收。

## 9. 用户决策与剩余选择

### 已确认：A，partial仅实时展示

用户明确选择A：流式partial仅作为SSE实时展示，不保存为正式消息，也不做partial快照或重启恢复。只有完整协议校验通过并提交成功的assistant消息进入Session历史；取消、失败、崩溃留下的半截文本均不进入下一轮模型上下文。

实时展示状态与持久事实明确分离：llm.delta不能证明消息已经保存；完整消息提交后才能发出相应完成通知。即使文本看起来完整，若协议校验或提交失败，也不能加入历史。已提交的用户消息、完整工具调用及工具结果仍保留，按既定规则闭合pending配对并记录Run终态。

验收需覆盖：发出若干delta后取消/失败/崩溃；完整文本到达但结束协议非法；协议有效但提交失败。这些路径都不得在恢复会话或下一轮请求中包含未提交assistant文本。

### 已确认：A，不同会话并行并限制全局活跃Run

用户明确选择不同Session允许并行，同Session只允许一个活跃Run。全局上限可配置，达到上限立即明确拒绝，不建立等待队列。该限制只保护服务资源，不改变各Session历史和Run生命周期。默认数值、同步原语由实现按现有配置体系设计，不引入分布式队列或额外调度系统。

收敛设计见phase-5-design.md；上述两项架构选择均已确认。正式设计仍待整体核对，本轮不编码。

## 10. 官方资料核对与本轮操作边界

FastAPI的[lifespan文档](https://fastapi.tiangolo.com/advanced/events/)支持在服务生命周期内统一创建和释放共享资源；[SSE文档](https://fastapi.tiangolo.com/tutorial/server-sent-events/)覆盖结构化事件和POST SSE。Python 3.12 [sqlite3文档](https://docs.python.org/3.12/library/sqlite3.html)用于核对显式事务与线程约束。具体依赖版本及断连行为仍须在实现时锁定并做Windows本机验证，不能仅依赖框架宣传。

本轮只做阅读与设计记录；未改backend、依赖、Persona或语料，未切分支、提交、push、运行服务或调用真实模型/Embedding。浏览的是官方框架文档。Starlette页面抓取失败，改查FastAPI官方资料；一次PowerShell命令误用花括号路径展开导致解析失败，已改为显式路径，无文件改动。
