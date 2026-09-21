# Phase 5 实施计划：本机服务、持久会话与SSE

> 执行者须同时阅读本计划与设计。真正获准实施后使用 `superpowers:executing-plans` 按任务执行；如用户另选逐任务子代理方式，则使用 `superpowers:subagent-driven-development`。当前用户授权在phase-5-service完成Task 2、3并提交/push；完成后停止，不执行Task 4及后续，不调用真实API、不merge。

**目标：** 在现有单一Agent Loop上接入SQLite SessionStore、RunManager、真实模型流式和FastAPI/SSE，使后续UI能可靠读取历史、观察及取消执行。

**架构：** Runtime通过可等待的提交边界维护消息，通过独立事件接收器报告执行。服务层负责持久化、Run接纳/取消及HTTP连接；Provider只处理模型协议。实时partial与持久消息严格分离。

**技术：** Windows、项目独立Python 3.12、asyncio、Pydantic、HTTPX；SQLite使用标准库sqlite3及Store专用串行线程。FastAPI/Uvicorn只在Task 10引入并锁定兼容版本；不引入ORM、队列系统或UI依赖。

**设计依据：** [已确认的Phase 5设计](D:/Desktop/herta-agent/docs/phase-5-design.md)。基线为phase-4-rag / ae72541ea9ea7c64d768d2b469c479a311661828。

## 全局约束

- 按用户逐批授权执行；当前Task 2、3完成并提交/push后停止，不进入Task 4，不merge。
- 保留现有唯一的 `Agent.run` 模型→工具→模型循环；CLI和HTTP服务不各写一份Loop。
- 保留原有93项离线回归的行为含义，不删除、跳过或弱化断言以迁就新接口。
- 单进程、单worker，绑定127.0.0.1，支持Windows中文/空格路径、目录外启动；无fork或Unix信号依赖。
- 同Session一个活跃Run；不同Session可并行；全局默认4，可配置1–32。满额立即拒绝、不排队，不改变Session历史或生命周期。
- partial仅SSE实时展示，不持久化、不恢复、不进入下一轮模型上下文；assistant须完整协议校验且提交成功才进入历史。
- complete兼容入口、Persona每Run快照/失败保留会话、RAG模型主动Tool、预算与工具配对保持不变。
- 断连取消；无自动重试、Run续跑或SSE重放。中断恢复只能修复历史与状态，不再次执行工具。
- Key仅从本地环境读入内存，不进入数据库、事件、日志或测试文件。测试用进程内动态生成的假凭据，不读取实际Key。
- 不做Phase 6 UI、鉴权、多用户、分布式调度、长期Memory、settings热更新或新RAG能力。
- Phase 4工程完成，真实RAG效果、阈值校准仍待真实服务配置；本阶段工程测试不得改写此状态。

## 依赖顺序与核验规则

```text
1 Store消息事务 → 2 Store中断恢复 → 3 Store取消/线程关闭
→ 4 Runtime通用提交 → 5 Runtime执行事件
→ 6 RunManager接纳/并发 → 7 RunManager取消/终态
→ 8 Provider真流式 → 9 单一Loop接入流式
→ 10 FastAPI资源装配/普通API → 11 POST SSE/断连
→ 12 Windows集成与交付文档
```

不调整用户指定的主顺序。先用现有complete Provider验证Manager，再验证流式协议，最后连接传输层。Task 4–5定义流式也能复用的消息ID和提交接口，但不提前实现Provider流式。

每个任务按“写行为测试 → 确认预期失败 → 最小实现 → 定向测试 → 完整回归”执行。使用unittest，不迁移测试框架。故障/竞争测试优先用Event/Barrier控制先后，不用随意sleep猜时序；所有等待设置测试上限。

下文 `backend/...` 均相对项目根目录 `D:\Desktop\herta-agent`；文件清单中的 `runtime/`、`storage/`、`service/`、`llm/`、`tools/` 简写均位于 `backend/herta_agent/` 下。每个新类型/方法是计划契约，可在实现中做不改变行为的局部命名调整，但必须同步调用方和测试；改变已确认语义须先讨论。

通用回归命令：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\.venv\Scripts\ruff.exe check backend
.\.venv\Scripts\ruff.exe format --check backend
```

每个任务完成记录验证结果和差异；失败先定位当前任务，不继续堆下一层。提交/发布单独按用户授权处理，不把计划中的阶段完成视为push授权。

## 五项重点审查

1. 同一供应商tool_call_id在不同Step/Session重复：按所属assistant消息配对，不能全局唯一。Task 1、2。
2. 接纳事务已落库但HTTP请求在获得handle前断开：有所有者收尾，不留下无人管理Run。Task 7、11。
3. 写入线程收到外部取消后仍可能完成提交：不得提前释放名额或关闭DB。Task 3、7。
4. 文本已全部到达，但finish标志、工具参数或最后提交非法：不得把内容当成功历史。Task 8、9。
5. 慢客户端在最终提交后断开：不能把已完成Run改成cancelled，不能为发事件阻塞存储清理。Task 7、11、12。

## Task 1：SQLite记录与原子消息提交

**文件：** 新增 `backend/herta_agent/storage/__init__.py`、`models.py`、`sqlite.py`；新增 `backend/tests/test_session_store.py`。本任务不改Agent或引入FastAPI。

**接口：** `storage/models.py`定义不可变的SessionRecord、RunRecord、MessageRecord、Admission及安全StoreError。RunStatus限定created/running/completed/failed/cancelled/interrupted；MessageRecord包含message_id、session_id、run_id、seq、step、Message。Admission包含新Run和已提交的user记录。RunRecord记录配置白名单（模型标识、RunSettings）、context_hash、步骤、时间与安全错误，不接收ProviderSettings整体转储。

SQLiteSessionStore提供下列异步边界；记录类型即上文类型，Message沿用现有runtime/messages.py：

```python
await store.open()
await store.create_session()                          # -> SessionRecord
await store.get_session(session_id)                   # -> SessionRecord
await store.list_sessions(after_id=None, limit=50)    # -> tuple[SessionRecord, ...]
await store.load_history(session_id, before_seq=None) # -> tuple[MessageRecord, ...]
await store.list_messages(session_id, after_seq=0, limit=100)
await store.admit_run(session_id, run_id, user, config) # -> Admission
await store.start_run(run_id)                         # -> RunRecord
await store.set_context(run_id, context_hash)
await store.append_message(run_id, message_id, step, message)
await store.finish_run(run_id, status, *, steps, final_message=None, error=None)
await store.get_run(run_id)                           # -> RunRecord
await store.close()
```

`final_message`为MessageRecord或None；completed必须携带无tool_calls的完整assistant。非成功终态的pending闭合在Task 2加入。schema版本不符启动失败，不删除/重建用户数据库。消息唯一顺序约束以session_id/seq为键；分页按确定性顺序且限制1–100，客户端分页不影响内部加载完整模型历史。

- [x] 写测试：创建/关闭/重开会话；顺序完整保存user、assistant.tool_calls、tool和最终assistant；现代Message字段不丢失；原始system与partial不被接收入库；非法消息/终态转换失败。
- [x] 写故障测试：admit事务中断时Run和user都不存在；completed事务失败时最终assistant和completed都不存在；末次合法提交前记录保持完整。使用测试注入的事务故障，不模拟“已保存但返回假数据”。
- [x] 执行并确认失败：`python -m unittest discover -s backend/tests -p test_session_store.py -v`，通过项目 `.venv\Scripts\python.exe`运行。
- [x] 实现显式短事务、外键/唯一约束、JSON消息验证、白名单配置及安全错误；SQL值全部参数化。只保存正式Message，不创建partial/events表。
- [x] 验收重复tool_call_id：两个不同Step可各出现一次相同ID，分别配对；同一批重复ID仍拒绝。验证中文/空格临时目录与保存后原样恢复。
- [x] 定向及全套回归通过；数据库文件只产生在临时目录或.local，不进入Git。

核心断言形状（测试构造事务失败后查询实际数据库）：

```python
self.assertEqual(await store.load_history(session_id), committed_before)
self.assertEqual((await store.get_run(run_id)).status, "running")
# completed事务失败不能留下最终assistant或假成功状态。
```

## Task 2：恢复历史与中断工具配对

**文件：** 修改 `storage/sqlite.py`、`storage/models.py`；新增 `backend/tests/test_store_recovery.py`。

**消费/产出：** 使用Task 1的事务与记录；新增 `await store.recover_interrupted() -> tuple[RunRecord, ...]`，完成finish_run的非成功分支。读取已提交消息推导pending，不能依赖崩溃前内存字典。

- [x] 写测试：遗留created、模型等待中的running、工具声明后部分完成的running；重开DB后修复为interrupted，仅给真正pending调用追加中断/结果未知结果，保留成功结果。
- [x] 写测试：连续恢复两次不重复补工具结果、不改变已有终态；恢复事务失败不得部分修复后接受新Run；损坏的历史配对明确失败，不编造或删除历史。
- [x] 运行 `test_store_recovery.py`确认失败，再实现单事务修复；错误结果使用现有ToolResult格式，但保留中断原因，不假称用户取消。
- [x] 验证两个Session、跨Step重复tool_call_id均不串线；没有模型、Embedding或工具handler被恢复流程调用。
- [x] 定向和全套回归通过。验收恢复后的历史可以构造合法下一轮模型输入。

```python
await store.recover_interrupted()
once = await store.load_history(session_id)
await store.recover_interrupted()
self.assertEqual(await store.load_history(session_id), once)
self.assertEqual(tool_handler_calls, 0)
```

## Task 3：Store线程、在途事务与取消边界

**文件：** 完成 `storage/sqlite.py`执行边界；必要时将专用执行器拆为 `storage/worker.py`；新增 `backend/tests/test_store_cancellation.py`。

**接口：** Task 1外部异步方法不变。Store内部单个专用线程拥有连接，提交的工作有受跟踪的Future；本任务完成后才让Runtime依赖其取消保证。增加只读 `store.writable`供服务健康与接纳检查。

- [x] 使用threading.Event控制事务“执行中/已提交/释放”，编写调用协程被取消但底层事务尚未结束的测试；同时断言事件循环能继续执行另一个协程。
- [x] 写锁冲突、open/close失败、重复close以及close期间仍有事务的测试；错误不得泄露SQL参数、配置或动态生成的假凭据。
- [x] 运行 `test_store_cancellation.py`确认失败，再实现短事务串行执行、有限SQLite锁等待（起点1秒）及在途工作跟踪；禁止把一个连接任意交给线程池多线程使用。
- [x] 取消时受控等待已提交线程工作的真实结果，再传播取消；不能将 `shield` 当作工作已经完成，也不能让被取消的await丢掉Future所有权。
- [x] 提交失败标记不可写；不做后台重试。close等待在途工作完成后由所属线程关闭连接，拒绝close后的新操作。
- [x] 验收：在途Future完成前close不能宣称结束；取消后的“晚写”不会与下一轮写入交叉。保留硬进程退出只能依靠下次恢复的边界。

```python
caller.cancel()
self.assertFalse(close_finished.is_set())
allow_transaction_to_finish.set()
# 之后等待caller取消和store.close完成，再重开检查实际提交结果。
```

## Task 4：Runtime通用提交边界，保持单一Loop

**文件：** 新增 `runtime/turn.py`；修改 `runtime/agent.py`、`runtime/session.py`、`runtime/errors.py`；新增 `backend/tests/test_runtime_commits.py`。不改Persona/检索算法。

**接口：** 定义TurnIO协议及MemoryTurn实现。沿用 `Agent.run(session, user_text)`，新增可选关键字 `turn_io`；未提供时使用MemoryTurn，使原93项调用方式继续有效。

```python
await turn.begin(user: Message)
await turn.set_context(context_hash: str)
await turn.append(message: Message, *, message_id: str, step: int)
await turn.complete(message: Message, *, message_id: str, step: int)
await turn.abort(*, cancelled: bool, error_code: str, safe_message: str, step: int)
```

协议绑定本Run的Session；history仍由Session提供。增加 `Session.restore(session_id, history)`公共恢复入口，验证完整历史与配对，不允许路由修改私有属性。message_id由Runtime在每次模型请求前分配，供后续delta/提交共用。

- [ ] 写RecordingTurn测试：begin→context→assistant调用提交→tool结果提交→最终complete顺序；提交抛错后不执行下一个工具或再次请求模型。
- [ ] 写恢复测试：非法历史拒绝，两个恢复的Session不共享可变列表，缺失Persona仍保留本轮user且不请求模型。
- [ ] 运行 `test_runtime_commits.py`确认失败，然后把现有Loop里的同步追加转为await TurnIO；MemoryTurn内部使用原Session行为，工具、步数限制不变。
- [ ] 完成仅一次的abort/清理路径；提交失败后不把未提交内容追加到内存。取消、预算到顶、协议失败仍闭合pending调用。
- [ ] 服务的PersistentTurn留给Task 6，实现时begin只映射Task 1已落库user到内存，不能再次调用admit_run。此任务通过假Turn证明接口，而非提前写服务层。
- [ ] 定向及全部93项基线保持通过；若需要适配测试内部观察点，只能保留或加强原行为断言。

```python
self.assertEqual(provider_call_count, 1)
self.assertEqual(executed_tool_names, [])
# assistant.tool_calls提交失败时，任何工具均不得执行。
```

## Task 5：Runtime通用执行事件

**文件：** 新增 `runtime/events.py`；修改 `runtime/agent.py`、`tools/executor.py`；新增 `backend/tests/test_runtime_events.py`。

**接口：** RuntimeEvent包含type、step、message_id、tool_call_id及JSON安全payload；不含SSE格式。EventSink协议 `async emit(event: RuntimeEvent) -> None`；Agent.run新增可选observer，默认空接收器。Executor增加可选 `on_started`异步回调，在参数验证成功后、进入handler前调用。

- [ ] 写事件测试：llm.started→已提交的llm.completed；合法工具的started/结果顺序；unknown_tool/参数错误不产生虚假的tool.started；每Step独立message_id。
- [ ] 写基础设施错误测试：on_started/消息提交失败不能被Executor转换为execution_error后继续循环；handler普通异常仍按原约定清洗为ToolResult失败。
- [ ] 运行 `test_runtime_events.py`确认失败；在唯一Loop的实际节点发事件，完成类事件只在相应提交成功后发。当前complete Provider不产生llm.delta。
- [ ] 验收工具结果包含完整既有JSON格式；Runtime不判断search_knowledge名称，RAG专用事件映射推迟Task 11。
- [ ] 定向和全套回归通过。终态服务事件由Manager负责，Runtime不再次发送run.completed/failed/cancelled。

```python
self.assertNotIn("tool.started", event_types_for_invalid_arguments)
self.assertLess(commit_position, completed_event_position)
```

## Task 6：RunManager接纳、容量与持久Turn

**文件：** 新增 `service/__init__.py`、`service/settings.py`、`service/runs.py`、`service/turn.py`；新增 `backend/tests/test_run_admission.py`。暂不依赖FastAPI。

**接口：** ServiceSettings沿用冻结、禁止额外字段、严格有限值的Pydantic方式；max_active_runs默认4、1–32，支持启动环境 `HERTA_MAX_ACTIVE_RUNS`。RunManager构造接收Store、Agent及ServiceSettings；`await submit(session_id, user_text) -> RunHandle`，handle含run_id/session_id和内部有界事件通道；`await get(run_id)`区分持久Run与瞬时取消标志；`await shutdown()`在Task 7完成。

增加只读 `manager.active_count`供测试和安全健康摘要使用；它包含预占/created/running及清理中的Run，不只统计正在请求模型的数量。

PersistentTurn消费Task 4的TurnIO，调用Task 1 Store。接纳后从Admission定位user序号，恢复此前已提交历史；begin校验同一user已落库，再映射到内存一次。append先Store提交后更新Session；complete/abort委托Manager统一终态操作，不各自独立决定状态。

- [ ] 写测试：两个Session同时进入阻塞Provider；同Session第二次submit立即失败；全局设1时其他Session满额失败；失败前后历史和Run数量完全不变。
- [ ] 使用同时到达的协程测试原子预占；不得先await DB再记占用。接纳写入失败、Task创建失败须释放预占，若Run已落库则进入Task 7收尾，不静默遗留。
- [ ] 运行 `test_run_admission.py`确认失败；实现同步短临界段检查/预占，不用await semaphore排队。给拒绝定义服务错误码session_busy、run_capacity_exceeded，HTTP映射留Task 10。
- [ ] start_run提交后才emit run.started；RunTask强引用保留到完成和清理。不同Run的Session、事件序号、取消状态互相隔离。
- [ ] 本任务同时实现正常complete和普通异常abort的最小持久闭环，验证提交最终回答并释放名额后可接纳下一Run；Task 7在同一入口补强取消竞争与关闭，不留下只能启动不能收尾的组件。
- [ ] 验证严格配置拒绝bool、0、负数、>32和非整数；配置改变不影响单Session消息语义。显式测试user只追加一次。
- [ ] 定向和全套回归通过；测试使用现有complete Provider，不等待流式功能。

```python
before = await store.load_history(second_session)
with self.assertRaises(RunCapacityError):
    await manager.submit(second_session, "另一轮")
self.assertEqual(await store.load_history(second_session), before)
```

RunCapacityError与SessionConflictError定义于service/runs.py，均携带固定安全code；不复用数据库异常来猜HTTP冲突。

## Task 7：Run终态、取消竞争与服务关闭

**文件：** 完成 `service/runs.py`、`service/turn.py`；新增 `backend/tests/test_run_lifecycle.py`。

**接口：** 新增 `await manager.cancel(run_id, reason) -> CancelResult`；CancelResult含accepted、持久status和cancel_requested，不能把请求成功称为已经cancelled。实现PersistentTurn complete/abort与Manager共享的终态提交入口，调用Store.finish_run。

- [ ] 写屏障测试：Task尚未进入Runtime就取消；重复cancel；工具中途取消；模型超时/Persona失败；completed后再cancel；完成提交与cancel两种先后顺序。
- [ ] 写在途事务测试：submit调用方在admit事务中取消，事务最终成功时仍必须由Manager收尾；terminal提交中取消不能提前释放Session或全局名额。
- [ ] 运行 `test_run_lifecycle.py`确认失败；Manager登记接纳过程的所有权，不能到返回RunHandle后才登记。首次取消中断工作；重复取消不再打断最终清理。
- [ ] 在同一Run终态临界段裁决：已进入最终提交则等待提交结果；此前已接受取消则拒绝新成功提案。Store终态不可重复改写，completed后的通知失败不回滚为cancelled。
- [ ] 清理资源、闭合pending和终态提交结束后释放名额。Task从未开始的路径由Manager补收尾，不依赖Agent finally。存储不可写则拒绝新Run，发persisted=false服务故障，保留磁盘事实供重启修复。
- [ ] shutdown停止接纳→取消/等待任务及在途事务→关闭资源；设置有限协作清理等待，超时不能假称线程已停或数据已提交，硬退出留给恢复。测试不引入Linux信号。
- [ ] 定向与全套回归通过；下一Session和同Session后续Run都能在真实释放后继续。

```python
await manager.cancel(run_id, "user")
self.assertEqual(manager.active_count, 1)  # 被屏障卡住的清理尚未完成
allow_cleanup.set()
await run_finished.wait()
self.assertEqual(manager.active_count, 0)
```

## Task 8：Provider真正解析流式Chat Completions

**文件：** 新增 `llm/streaming.py`；修改 `llm/base.py`、`llm/openai_compatible.py`；新增 `backend/tests/test_provider_streaming.py`。保留现有非流式测试。

**接口：** 定义TextDelta(text:str)、ReplyCompleted(reply:ModelReply)不可变类型；StreamingLLMProvider提供 `stream(messages, *, tools=()) -> AsyncIterator[TextDelta | ReplyCompleted]`。complete签名保持不变。流式和非流式共用最终Message/ToolCall校验，不共享不兼容的原始响应结构假设。

- [ ] 用HTTPX AsyncByteStream/MockTransport编写分片fixture：中文UTF-8跨字节块、SSE行/JSON跨块、空注释、role片段、多段content、分片工具参数、多个tool index交错和尾部合法usage记录。
- [ ] 写失败fixture：提前EOF、无合法finish_reason、无结束标志、截断/过滤、非法JSON、冲突id/类型、重复终结、零个/多个最终reply、超大帧或累计响应、旧function_call。均不得产出ReplyCompleted。
- [ ] 运行 `test_provider_streaming.py`确认失败；请求stream=True，使用HTTPX响应流生命周期，按SSE帧解析，不假设每个网络chunk就是一个事件。仅支持单choice与现代tool_calls。
- [ ] 按tool index累计调用，finish_reason与结束标志验证成功后只产出一次ReplyCompleted；不向工具执行器暴露未完成arguments，不转发隐藏推理字段。
- [ ] 定义明确的帧/累计响应大小保护并写边界测试；HTTP错误只报安全状态，不转发body/URL。取消关闭响应，超时不隐式重试。完整流总期限由Task 9的Runtime包围，HTTP连接/读取期限继续有效。
- [ ] 验收时间顺序：服务器被屏障阻塞在结束标志前时，消费者已能收到TextDelta，但尚未有ReplyCompleted；拒绝“收到完整JSON再切字”。
- [ ] 定向及全套回归通过，仍无真实服务请求。

```python
self.assertIsInstance(await anext(events), TextDelta)
self.assertFalse(server_finish_released.is_set())
# 放行结束帧后才允许唯一ReplyCompleted，内容须通过原Message校验。
```

## Task 9：同一Agent Loop使用流式入口

**文件：** 修改 `runtime/agent.py`、`runtime/events.py`；新增 `backend/tests/test_runtime_streaming.py`。不复制工具循环，不修改RAG算法。

**接口：** Agent构造新增显式 `streaming=False`选项；服务真实模式使用True，CLI原默认False。选择流式但Provider不支持时明确配置错误，不悄悄退回或伪造delta。演示模式可明确使用complete，仅测试fixture提供可控假增量并标注其用途。

- [ ] 写单一Loop测试：流式文本→完整工具调用→工具结果→下一Step流式回答；每次请求使用同Run Persona快照，历史仅包含已提交Message。
- [ ] 写partial隔离测试：输出数个delta后取消、协议失败、总超时、提交失败；关闭/重开Store后不含未提交assistant，下一轮Provider输入也不含它。即便全部文本已到达但finish非法也不例外。
- [ ] 运行 `test_runtime_streaming.py`确认失败；在原请求位置消费stream或complete，二者得到同一个ModelReply后走原工具/终止分支。
- [ ] llm.delta绑定请求前分配的message_id且仅送observer；llm.completed在完整消息提交后发。请求期限包围整个流消费，timeout/cancel清理迭代器与HTTP响应。
- [ ] 验证最后Step工具预算、最多4个调用、工具错误回填、无partial落库、RAG工具结果照常传给下一步。Task 7唯一终态规则不被事件发送失败绕过。
- [ ] 定向与全套回归通过，演示不会被称为真实流式模型验证。

```python
self.assertTrue(any(e.type == "llm.delta" for e in events))
self.assertNotIn(uncommitted_text, next_model_request_text)
self.assertFalse(any(m.message.role == "assistant" for m in failed_turn_records))
```

末条只用于尚无完整assistant提交的fixture；已有合法工具调用消息的失败轮必须保留那些记录，不能一律删除所有assistant。

## Task 10：FastAPI生命周期与普通API

**文件：** 新增 `service/app.py`、`service/schemas.py`、`service/__main__.py`；修改 `service/settings.py`、`backend/pyproject.toml`、`backend/uv.lock`；新增 `backend/tests/test_service_api.py`。

**接口：** `create_app(settings, *, provider=None) -> FastAPI`允许测试注入Provider；生产设置从环境/启动参数读取。新增 `python -m herta_agent.service`入口；不要改原 `python -m herta_agent` 的CLI行为。FastAPI/Uvicorn选兼容Python 3.12的明确版本范围并用项目uv更新锁文件；不顺带升级无关依赖。

- [ ] 写lifespan测试：open Store→recover_interrupted→装配独立HTTP客户端、Persona/RAG和Manager→接纳；退出先manager.shutdown再关客户端和Store；启动失败关闭已创建资源。
- [ ] 写普通API测试：创建/分页列表/读取会话、读取Run、幂等取消、404、422、409、429、存储不可写503、未配置模型时health/读历史可用但运行不可用。POST runs在本任务先验证接纳前拒绝路径，成功SSE由Task 11验证；不以临时JSON成功响应代替。health不访问远程接口、不泄露Key。
- [ ] 运行 `test_service_api.py`确认预期失败；在本任务才安装依赖并实现上述API。POST runs的接纳逻辑复用Manager，SSE完整传输在Task 11交付，不先做另一种JSON后台Run接口。
- [ ] DTO仅接受用户文本和指定标识，拒绝客户端注入system、任意文件路径、Key或模型消息历史；限制输入长度与分页范围并写边界测试。
- [ ] 真模型与显式demo分别装配；缺聊天配置不暗自用demo，RAG不可用只影响工具能力；Key不通过API更新。入口只启单worker/loopback，拒绝不支持的多worker使用方式。
- [ ] 定向及全套回归通过。默认DB位于.local、配置路径不依赖cwd；不同客户端使用共享资源但不共享Session状态。

```python
self.assertEqual(conflict.status_code, 409)
self.assertEqual(full.status_code, 429)
self.assertEqual(no_model_calls, 0)
self.assertNotIn(dynamic_test_secret, response.text)
```

## Task 11：POST SSE、断连与背压

**文件：** 新增 `service/sse.py`、`service/events.py`；修改 `service/app.py`、`service/runs.py`；新增 `backend/tests/test_service_sse.py`。

**接口：** ServiceEvent为schema_version=1的外部JSON事件，含设计规定的公共字段；内部RunHandle通道消费RuntimeEvent并赋予run_id/session_id/seq。`encode_event(event) -> bytes`固定UTF-8 SSE编码。SSE实现可使用锁定FastAPI版本的响应支持，但实际断连/取消职责必须在测试中验证，不靠默认行为猜测。

- [ ] 写POST SSE协议测试：Content-Type、id/event/data、换行边界、中文、心跳、seq递增、first run.started、每Step独立message_id、唯一终态、提交前失败仍返回普通HTTP错误。
- [ ] 写有界通道测试：起点128条事件，生产端/发送端有限等待；单事件与累计缓冲有大小限制。正常压力下不静默丢关键事件，持续背压则关闭流并请求取消，清理和DB终态不能等待消费者腾空队列。
- [ ] 运行 `test_service_sse.py`确认失败；POST /sessions/{id}/runs直接返回流。接纳过程与响应finally都有明确Run所有权，首事件前断连、接纳await期间取消和流生成器关闭都要触发同一Manager取消路径。
- [ ] 映射Runtime提交后的tool事件；对已成功提交的search_knowledge结果额外派生rag.retrieved（query、index_id、chunk来源摘要）。映射位于服务事件适配层，不能改Agent按工具名分支。
- [ ] 全局资源故障发送service.error/persisted=false，不能冒充run.failed已落库。终态已提交后断连只丢通知，不改变事实。拒绝SSE恢复请求或明确不支持，不重发原POST，不新增事件数据库。
- [ ] 验证真实结果中source/score可展示但不表示效果通过；事件不暴露Key、供应商错误正文或隐藏推理。
- [ ] 定向、全套回归通过；再由Task 12证明真实socket行为，不能仅用内存ASGITransport宣称断连取消成立。

```python
self.assertEqual(terminal_events, ["run.completed"])
await disconnect_after_commit()
self.assertEqual((await store.get_run(run_id)).status, "completed")
```

## Task 12：Windows完整集成、故障验收与教学交付

**文件：** 新增 `backend/tests/test_service_integration.py`、`backend/tests/service_probe.py`（仅测试用离线Provider服务）；新增 `docs/phase-5-walkthrough.md`；更新README、architecture.md、reuse-plan.md及三份规划记录。必要测试数据仅临时生成，不提交Key、DB或SSE日志。

- [ ] 用sys.executable在Windows启动本机子进程服务，动态分配端口并用health等待就绪；设置进程超时和finally清理，避免遗留服务器。只有显式注入的离线Provider，禁止真实远程API。
- [ ] 真实HTTP验证：两Session并行、同Session冲突、全局拒绝、事件逐步到达、主动cancel、消费端直接关socket、首事件前断连、慢消费者、取消后同会话继续。
- [ ] 强制结束测试子进程后重启同一临时DB：created/running变interrupted，pending配对被修复，已完成结果不丢、不重复；partial无历史记录，工具执行计数无重放。
- [ ] 验证事务故障和通知丢失：先完成再断连仍能GET到completed；存储不可写不向UI报告持久成功、不放行新Run。原材料、Persona和RAG语义不改。
- [ ] 执行完整unittest、Ruff check、format --check、git diff --check；所有原93项仍通过，记录实际新增测试数，不预填通过数量。检查依赖锁与`.local`忽略规则。
- [ ] 文档写新增文件、生命周期执行链、3–5个精读函数（Store事务、Turn提交、Manager终态、Provider流解析、SSE清理）、PowerShell启动/请求/取消/重启命令，以及实际测试结果。
- [ ] 逐项核对设计第9节，并保留真实供应商流式与Phase 4真实RAG效果待验收的声明。停止Phase 5，不进入UI、不自动提交/push/合并。

最终验证命令：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\.venv\Scripts\ruff.exe check backend
.\.venv\Scripts\ruff.exe format --check backend
git -c safe.directory=D:/Desktop/herta-agent diff --check
```

## 设计覆盖与计划自检

| 设计条目 | 所属任务 |
| --- | --- |
| 单Loop、CLI兼容、通用边界 | 4、5、9 |
| Session事务、配置白名单、来源消息、恢复 | 1、2、3 |
| 全局容量/会话互斥/拒绝无副作用 | 6、7、10 |
| partial隔离、完整校验后提交 | 1、4、8、9、12 |
| cancel/终态竞争/断连/退出 | 3、7、11、12 |
| 真流式与工具分片 | 8、9 |
| SSE时序/背压/故障非持久标记 | 5、7、11 |
| API与共享资源/Windows路径 | 10、12 |
| Persona/RAG边界与真实效果声明 | 4、9、10、11、12 |

任务完成状态以勾选及progress.md实测记录为准，未勾选任务尚未实现。保留全部12个Task与依赖顺序；Store专属线程不是Run队列，框架事件传输不是数据库事实。
