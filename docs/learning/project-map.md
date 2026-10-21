# Herta 项目地图

地图建立日期：2026-10-19，单元03更新于2026-10-21；基线 `phase-6-ui@9ab9796d819216a64c783eeba75f7ac804441a23`。教学继续复用隔离分支 `learning/unit-01-cli-read`，尚未提交或合并回主线。原始只读结论见单元00；CLI读取见[单元01](unit-01-cli-read.md)，搜索与工具组合见[单元02](unit-02-search-read.md)，确认编辑见[单元03](unit-03-confirmed-edit.md)。

## 先建立直觉

把 Agent 看成工作室：入口接待任务，Loop 安排“问模型还是执行工具”，Registry 保存工具说明书，Executor 执行并返回结果，Context Engine 整理工作台，Session 记住当前对话，SQLite 保存档案。

对应的正式术语是：程序入口、Agent Loop、工具注册、工具执行、上下文预算、会话状态、持久化。模型决定调用什么工具；Harness 检查、执行和记录这些调用。

## 现在实际有哪些入口

| 入口 | 真实位置 | 当前行为 |
|---|---|---|
| Python CLI | [backend/herta_agent/__main__.py](../../backend/herta_agent/__main__.py) 转发到 [cli.py](../../backend/herta_agent/cli.py)，`main → run_cli → create_agent → chat → run_turn`；沿用 `herta-agent` 脚本 | 默认离线回显；注册Read、字面Search和需逐次确认的Edit，不强制人格/RAG；只有进程内Session。examples/cli-search与cli-edit是固定Provider夹具，调用同一组装入口与Loop |
| 桌面启动 | `启动Herta.cmd → scripts/Start-Herta.ps1 → Electron`；Python 服务入口 [service/__main__.py](../../backend/herta_agent/service/__main__.py) | 启动本机 HTTP 服务及桌面生命周期 |
| 服务组装 | [service/app.py](../../backend/herta_agent/service/app.py) 的 `create_app`/`lifespan` | 创建人格、RAG、陪伴、语音、工作台和工具；这里是主要业务耦合点 |

目标版本只保留 CLI 产品入口。旧桌面服务入口的源码和数据未修改；单元01没有做打包、依赖裁剪或发行迁移，不能把旧桌面启动脚本当成当前CLI入口。

## 核心模块与调用关系

```mermaid
flowchart TD
    Entry[入口组装 Provider、工具和 Session] --> Loop[Agent.run]
    Loop --> Ctx[ContextEngine.prepare]
    Ctx --> Provider[Provider.complete 或 stream]
    Provider --> Decision{是否有 tool_calls}
    Decision -- 有 --> Exec[ToolExecutor.execute]
    Exec --> Registry[ToolRegistry.get → ToolSpec.handler]
    Registry --> Feedback[TurnIO.append → Session.record_result]
    Feedback --> Loop
    Decision -- 无 --> Finish[TurnIO.complete → RunResult]
    Loop -. 事件通知 .-> Events[EventSink]
    Feedback -. 持久化适配 .-> Store[SQLiteSessionStore]
    Finish -. 持久化适配 .-> Store
```

SQLite 虚线是适配器可选行为，**不是** `Agent.run` 直接写数据库。内存入口用 `MemoryTurn`；现有服务通过 `PersistentTurn` 持久化。

| 模块 | 真实文件/关键符号 | 要理解的核心 |
|---|---|---|
| CLI组装 | [cli.py](../../backend/herta_agent/cli.py)，`main/run_cli/create_agent/chat/run_turn` | 入口负责组装；循环、上下文和执行仍使用已有核心 |
| 只读文本 | [tools/coding/read_file.py](../../backend/herta_agent/tools/coding/read_file.py)，`ReadParameters/read_file/_read_file`；[paths.py](../../backend/herta_agent/tools/coding/paths.py)，`Repository.path` | Executor校验参数后，handler在线程中进行路径检查和有界读取；超过1MiB拒绝，结果分页保持完整行；目录限制不是操作系统沙箱 |
| 字面搜索 | [grep_code.py](../../backend/herta_agent/tools/coding/grep_code.py)，`GrepParameters/grep_code/_search`；`Repository.files` | 搜索普通UTF-8文件，返回路径与行号供后续Read；不跟随链接/特殊文件，明确预算和跳过。与Read共用`read_bounded_bytes/decode_utf8`，没有第二套文件服务 |
| 确认编辑 | [edit_file.py](../../backend/herta_agent/tools/coding/edit_file.py)，`EditParameters/prepare_edit/commit_edit`；[permissions.py](../../backend/herta_agent/tools/permissions.py)，`TerminalApproval` | Read新增全文件字节指纹；仅唯一文本替换。Executor先校验再请求一次确认；内容变化则拒绝，临时文件替换单个目标，再沿原Loop回读 |
| Loop | [runtime/agent.py](../../backend/herta_agent/runtime/agent.py)，`Agent.run:104`、`_request:70` | 每步问一次模型；有工具调用就执行并回填，无调用则返回；限制步数，取消时收尾；单元03只调整构造参数转发 |
| 工具说明与查找 | [tools/registry.py](../../backend/herta_agent/tools/registry.py)，`ToolSpec:17`、`ToolRegistry:44` | 名称、参数模型、handler、权限元数据放在一起；`definitions` 生成模型看到的 JSON Schema |
| 工具执行 | [tools/executor.py](../../backend/herta_agent/tools/executor.py)，`ToolExecutor.execute:67` | 查找、权限判断、参数校验、当前调用确认、期限、执行和结构化结果；工具错误可回到模型继续处理 |
| 上下文 | [runtime/context_engine.py](../../backend/herta_agent/runtime/context_engine.py)，`prepare:206`、`_turn_groups:117` | 保留完整用户轮次和工具配对；估算输入预算，必要时节录旧历史 |
| 系统文本 | [runtime/context.py](../../backend/herta_agent/runtime/context.py)，`ContextSnapshot`、`StaticContextBuilder` | Loop 可以使用普通系统文本，不强制加载大黑塔人格 |
| 会话 | [runtime/session.py](../../backend/herta_agent/runtime/session.py)，`Session.restore/begin_turn/record_calls/record_result` | 维护历史、忙碌状态和未完成工具 ID；阻止错配的结果进入历史 |
| 每轮写入边界 | [runtime/turn.py](../../backend/herta_agent/runtime/turn.py)，`TurnIO`、`MemoryTurn` | 同一 Loop 能换内存或持久化适配器，不再造一套循环 |
| 持久化 | [storage/sqlite.py](../../backend/herta_agent/storage/sqlite.py)，`SQLiteSessionStore:149`、`admit_run:412`、`finish_run:498`、`recover_interrupted:586` | 事务保存消息与运行状态，恢复中断状态；数据库线程归单独 worker 所有 |
| 服务适配 | [service/turn.py](../../backend/herta_agent/service/turn.py)，`PersistentTurn:10`；[service/runs.py](../../backend/herta_agent/service/runs.py)，`RunManager._execute:239` | 现有持久化适配依赖 RunManager；CLI 不能原样接上就宣称脱离服务层 |
| 模型适配 | [llm/base.py](../../backend/herta_agent/llm/base.py)、[llm/openai_compatible.py](../../backend/herta_agent/llm/openai_compatible.py)、[llm/streaming.py](../../backend/herta_agent/llm/streaming.py) | Provider 协议可替换；HTTP 与流式协议解析不进入 Loop；本轮未调用远程模型 |

服务中持久化的实际顺序为：`RunManager.submit → _admit_and_launch → store.admit_run → _execute → store.start_run → Session.restore → PersistentTurn → Agent.run`。`PersistentTurn.complete` 再经 `manager._finish → store.finish_run` 事务提交；它不是一个只靠替换 import 就可复用的 CLI 适配器。

## 跟踪一个真实输入

以下使用仓库已有 [test_tool_loop.py](../../backend/tests/test_tool_loop.py) 中 `test_multiple_steps_and_tool_errors_are_fed_back_in_order` 的输入 `go`。**这是静态读源追踪，本轮没有执行该测试。** `ScriptedProvider` 是测试夹具，不是会理解 `go` 的真实模型。

1. 测试构造 `Session()`、`echo_registry()` 和 `ScriptedProvider`，调用 `Agent.run(session, "go")`。
2. `MemoryTurn.begin → Session.begin_turn` 添加用户消息；`ContextEngine.prepare` 拼入系统文本、完整历史和工具 Schema。
3. 第一次 `Provider.complete` 按测试脚本声明两个调用：`echo({"text":"你好"})` 和不存在的 `unknown`。
4. `ToolExecutor.execute → registry.get → EchoParameters.model_validate_json → echo` 得到 `{"text":"你好"}`；另一个调用得到 `unknown_tool`。`MemoryTurn.append → Session.record_result` 按各自 ID 回填。
5. 第二次 Provider 声明参数为不完整 JSON `{` 的 echo，Executor 返回 `invalid_arguments`，Loop 继续回填，不伪造成功。
6. 第三次 Provider 返回文本 `done`；`MemoryTurn.complete` 添加最终回答，Loop 构造 `RunResult(reply="done", steps=3, ...)`。

测试源码断言的角色序列为 `user → assistant → tool → tool → assistant → tool → assistant`，工具结果 ID 为 `a、b、c`。这是可核对的预期，不是本轮新获得的运行结果。

几个容易混淆的名称：`Session` 是持续对话；一次用户消息触发一个 `Run`；`Step` 是一次模型请求，同一步可以有多个 `ToolCall`。`spec` 指工具说明，`parameters` 指校验后的参数，`turn` 指本轮提交边界。`ToolResult.ok` 只表示工具是否完成其调用，不能自动等同于业务测试通过。

## 当前能力边界

- Context Engine 是可替换的词面 Token 估算与历史节录；不等于供应商精确计费，也不等于 Claude Code 的完整自动压缩。当前单轮必需内容过大时会拒绝，不能保证长 Coding 任务连续完成。
- Executor保留旧`tool_policy(spec)`兼容原服务，CLI改选`authorize(spec, parameters)`，二者互斥，不叠加两套审批。编辑按本次参数和文件指纹展示差异、逐次确认；未实现命令审批或Shell。目录检查和工具确认不是操作系统沙箱。
- 旧陪伴 Skills 在 `companion/personalization.py:208` 的 `context_skills` 中作为已审核文字进入 `CompanionContext.snapshot`；不是 CLI 的目录发现与按需加载。
- `RuntimeEvent/EventSink` 可以观察运行，不是完整 Hooks 系统；多个 Session 也不等于已实现子 Agent。
- 用户级 `$guided-development` Skill 管理 **Codex 和用户的教学协作**，适用于不同项目；Herta 的专属约定保留在根目录 `AGENTS.md`。这不表示 Herta 产品已经具备同名 Skill 运行能力。

## 阅读顺序

先沿上面的 `go` 输入阅读 Loop、Registry、Executor、Session，再看 Context Engine；理解内存提交边界后再看 SQLite 和服务适配。旧 coding 工具的价值与后续目录方案见 [单元00审计](unit-00-architecture-audit.md)。
