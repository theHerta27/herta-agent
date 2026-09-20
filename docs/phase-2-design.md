# Phase 2 设计草案：Windows 工具调用闭环

状态：已实现并验证，42 项自动测试通过。用户已授权 Phase 2，并确认 Ctrl+C 取消当前轮后保留会话继续输入。

## 目标与已有约定

完成一次真正的 `用户 → 模型 → 工具 → 工具结果 → 模型 → 最终回答`，并能离线复现。沿用 Phase 0 已确认的架构：显式注册、Pydantic 参数 schema/校验、顺序执行、协作式异步 timeout/cancel、内存历史及 max_steps。

只实现 Tool Registry 和一个无副作用 echo 教学工具。Persona、RAG、FastAPI、SQLite、SSE、桌面 UI 仍属于后续阶段。

当前基线：26 项测试、Ruff 检查通过。用户已在 agent.py、session.py 增加中文说明，后续修改保留这些说明。

## Windows 实现约束

- Runtime 使用 Python asyncio 与 HTTPX，不照搬 Hermes 的线程中断树。
- 本阶段不执行 shell、不依赖 bash、fork、Unix socket、POSIX 进程组、SIGALRM 或 Unix 专属事件循环接口。
- 工具采用原生 async handler；超时/取消是协作式机制，不声称可以杀死任意同步阻塞代码。
- CLI 取消与 Runtime 取消分层。Runtime 不认识键盘或控制台信号；CLI 将用户动作转为当前执行任务的取消请求。
- 运行、环境及复现命令采用 PowerShell；保留现有 Windows 中文管道编码处理。

## 组件与文件职责

| 文件 | Phase 2 变化 |
| --- | --- |
| runtime/messages.py | 引入 ToolCall；支持 assistant.tool_calls 与 tool.tool_call_id，并校验角色字段组合 |
| runtime/session.py | 在活跃回合保存 assistant 工具调用与对应结果；取消/异常时关闭未完成配对 |
| runtime/agent.py | 调用模型后分流：文本结束，或执行工具并 continue；落实 max_steps |
| llm/base.py | complete 接收工具描述，返回含文本或 tool_calls 的内部响应 |
| llm/openai_compatible.py | 发布 tools 参数，解析 Chat Completions tool_calls，按角色编码请求消息 |
| llm/demo.py | 保留普通离线演示；增加明确标注的确定性工具闭环演示，不假装是模型推理 |
| tools/registry.py | ToolSpec 与显式注册、重复名称拒绝、按参数模型生成 schema |
| tools/executor.py | 名称查找、参数校验、async timeout、统一成功/错误结果 |
| tools/echo.py | 一个只返回输入、不修改文件或调用 shell 的教学工具 |
| __main__.py | 装配工具与演示模式；Runner 管理单轮取消，Session 跨轮保留 |
| tests/ | 参数验证、请求协议、闭环、配对、预算、超时、取消与回归测试 |

不预建通用插件框架、并发工具池或进程沙箱。

## 消息与 Provider 协议

模型可以返回纯文本，或一组 function tool_calls。每个调用包含稳定 id、名称和原始 JSON arguments。参数到 Executor 才按工具的参数模型验证，Provider 不执行工具。

assistant 工具调用可以没有文本；tool 结果必须关联 tool_call_id。模型响应若包含空/重复 id 或损坏的调用结构，在进入历史前作为协议错误拒绝。未知工具名称和参数错误由 Executor 形成可回填的失败结果。

发送给模型的消息只包含相应角色允许的字段，避免把内部 None、状态和计数一律 model_dump 到网络协议。无工具时保持现有普通聊天可用。仅实现现代 tool_calls，不悄悄猜测旧 function_call 的转换方式。

## 执行顺序与结果闭合

1. 校验并保存用户消息，取得会话执行权。
2. 在预算内请求模型，同时发送已注册工具 schema。
3. 纯文本：保存最终 assistant，返回结果。
4. 工具调用：保存 assistant.tool_calls，按返回顺序校验并执行工具。
5. 每个工具成功、参数错误、未知名称或超时，都追加一个匹配 id 的 tool 结果。
6. 再次请求模型；所有前置工具消息与结果均在上下文中。
7. 用户取消时，为尚无结果的调用补充取消结果，保留已完成结果，停止后续工具与模型调用，释放会话执行权。

统一结果遵循现有架构文档中的 `ok / data / error`。执行异常不把完整 traceback 或底层网络异常正文发给模型。

## 已确认的预算与失败策略

- max_steps 计算模型请求次数；默认 8。
- 最后一次允许的模型请求若仍产生工具调用，不执行这批无法反馈给模型的工具；闭合其失败结果后报告预算耗尽。
- 单次模型响应最多 4 个调用；超过上限时整批拒绝，不能偷偷只执行前几个。
- 多工具顺序执行；一个可恢复工具失败不会破坏其余调用的 id 配对。
- 超时返回错误工具结果，模型可在剩余预算内调整；用户取消则直接结束 Run。
- 不自动重试 HTTP 或工具，不增加供应商 SDK。

## 已确认：Ctrl+C 后的 CLI 生命周期

两个方案都可以实现 Runtime 的 Task 取消，但 CLI 的生命周期不同：

| 方案 | 行为 | 影响 |
| --- | --- | --- |
| A（建议） | 模型/工具执行期间 Ctrl+C 只取消当前轮，保留 Session，回到输入提示 | 本阶段即可手动验证取消后续聊；需拆分 CLI 生命周期与单轮任务 |
| B | 沿用 Phase 1：Ctrl+C 取消并退出 CLI | CLI 改动少；Runtime 可复用性由测试验证，交互内取消留到桌面阶段 |

用户选择 A。同步输入循环持有一个 Session 和 asyncio.Runner，每轮用 Runner.run 执行 Agent.run。标准 Runner 将第一次 Ctrl+C 转成当前任务取消，Runtime 清理后 CLI 捕获 KeyboardInterrupt 回到输入。输入时 Ctrl+C 清空本次输入并提示 /exit；单条 --message 模式取消后退出 130。重复快速 Ctrl+C 采用 Python 强制中断语义，不保证第二次中断下完成协作式清理。

参考：[Python 3.12 Runner](https://docs.python.org/3.12/library/asyncio-runner.html)、[Windows asyncio 限制](https://docs.python.org/3.12/library/asyncio-platforms.html)。不用 Windows 不支持的 loop.add_signal_handler，也不用阻塞 stdin 线程。验证在 Windows 子进程内触发 SIGINT，检查工具 finally、消息配对以及同一会话下一轮。

## 验证范围

保留 Phase 1 回归；增加 tool → text 两次模型调用、连续工具回合、同一回复多个工具、非法 JSON/字段/类型、未知工具、重复注册、模型协议错误、工具超时、执行中取消、取消后继续使用 Session、最后 Step 不执行工具、始终要求工具的模型达到预算后停止。

HTTP 测试验证 tools schema、arguments、tool_call_id 与角色编码；默认离线演示必须走同一个 Registry/Executor，不能用 CLI 假打印工具结果。

在 Windows 上运行全部测试和 PowerShell 教程命令；真实模型联调仍需要用户本地的可用配置，不能将 MockTransport 通过说成已验证真实服务商。

交付仍包含新增文件说明、执行路径、2–5 个精读函数、运行命令、实际测试结果和手动复现教程。Phase 2 完成后停止，等待下一阶段确认。
