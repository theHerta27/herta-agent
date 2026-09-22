# Phase 5：本机后端服务复现

Phase 5 将已有唯一 Agent Loop 暴露为本机 HTTP 服务。SQLite 保存完整消息和 Run 事实；SSE 只负责实时展示。本阶段没有 Electron/React UI，也没有鉴权、多用户、分布式队列、长期 Memory、Skills 或 MCP。

Phase 4 工程链路已完成，**真实 RAG 效果仍未验收**。Phase 5 的流式协议与服务测试使用离线 fixture，**真实供应商流式兼容性也仍待验证**。demo 是固定回显，不是语言模型。

## 新增代码与执行链

- `storage/models.py`、`storage/sqlite.py`：Session、Run、消息记录，SQLite 原子提交和崩溃恢复；单独工作线程拥有连接。
- `runtime/turn.py`、`runtime/events.py`：通用提交接口及执行事件；原 Agent Loop 消费这些接口，不依赖 FastAPI。
- `service/turn.py`、`service/runs.py`：持久 Turn、接纳、同会话互斥、全局容量、取消及唯一终态。
- `llm/streaming.py`：字节流的 SSE 帧解析、tool_calls 片段拼接和完整协议校验。
- `service/app.py`、`schemas.py`、`settings.py`、`__main__.py`：启动恢复、独立客户端装配、请求校验与 HTTP 入口。
- `service/events.py`、`sse.py`：版本化事件、内存缓冲、POST SSE、心跳、背压和断连清理。
- `tests/test_service_api.py`、`test_service_sse.py`、`test_service_integration.py`、`service_probe.py`：普通接口、事件传输、Windows 真实 socket 及故障恢复验证。probe 只供测试。

启动顺序：打开 SQLite → 修复上次未结束的 Run → 装配 Persona、RAG 快照及独立 HTTP 客户端 → 开放接纳。停机先停止接纳，取消并等待 Run/在途事务，再关闭资源。协作清理超时会明确失败，不假称强制停止了工作线程；硬退出后的状态由下次启动恢复。

一条 POST 的路径：FastAPI 验证 → RunManager 无 await 预占名额 → 原子写入 user + created Run → 单一 Loop → PersistentTurn 提交完整消息 → 最终 assistant 与 completed 同事务 → SSE 通知。不同 Session 可并行，单 Session 只允许一个活跃 Run；默认全局最多 4 个，满额立即返回 429，没有队列。

取消、断连、发送超时走同一取消入口。先接受取消则不能再提交成功；已进入最终事务则等待它完成，已提交 completed 不因通知丢失改成 cancelled。取消请求的 accepted 不是“已经取消”。重启只修复未完成配对并标记 interrupted，不重放工具，也不续跑 Run。

`llm.delta` 没有持久化资格；只有完整协议校验且提交成功的消息进入历史。persona/soul.md 每 Run 重读，同 Run 使用同一快照；加载失败停止该轮，修复后同 Session 可继续。RAG 证据仍由模型主动调用工具取得，服务只将已提交结果派生为 rag.retrieved 摘要。

## PowerShell 启动与请求

在第一个终端启动明确的离线演示：

```powershell
Set-Location -LiteralPath 'D:\Desktop\herta-agent'
.\.venv\Scripts\python.exe -m herta_agent.service --provider demo
```

默认只监听 `127.0.0.1:8765`，单 worker；默认数据库为项目 `.local/sessions.sqlite3`。`--db`、`--soul` 支持中文和空格路径，路径不依赖当前工作目录。`--host` 只接受 127.0.0.1，`--workers` 只接受 1。不要用多个进程访问同一运行数据库来绕过入口限制。

第二个终端：

```powershell
$base = 'http://127.0.0.1:8765'
Invoke-RestMethod "$base/health"
$session = Invoke-RestMethod "$base/sessions" -Method Post
$sid = $session.session_id
# curl.exe 的 -N 实时打印事件；使用临时 UTF-8 JSON 避免 PowerShell 原生命令引号问题。
$bodyFile = Join-Path $env:TEMP 'herta-request.json'
[IO.File]::WriteAllText($bodyFile, '{"text":"你好，黑塔"}', [Text.UTF8Encoding]::new($false))
try {
    curl.exe -N -H 'Content-Type: application/json' --data-binary "@$bodyFile" "$base/sessions/$sid/runs"
} finally {
    Remove-Item -LiteralPath $bodyFile
}
Invoke-RestMethod "$base/sessions/$sid"
```

真实长请求可以在另一个终端用首个 run.started 的 run_id 主动取消；也可以关闭 curl 连接触发取消。demo 通常已立即完成，此时取消不会改写结果。

```powershell
$base = 'http://127.0.0.1:8765'
$runId = '替换为实际run_id'
Invoke-RestMethod "$base/runs/$runId/cancel" -Method Post
Invoke-RestMethod "$base/runs/$runId"
```

服务终端 Ctrl+C 停止后，重新运行相同启动命令，再 GET 原来的 session_id，完整历史仍在。演示测试不会自动删历史；更换 `--db` 可隔离实验。强制终止和 pending 修复由集成测试覆盖，正常 Ctrl+C 与进程骤停不同。

真实服务使用 `python -m herta_agent.service --provider openai`；此命令会在聊天时访问已配置服务，本文测试未执行。聊天配置沿用 `HERTA_BASE_URL`、`HERTA_MODEL`、`HERTA_API_KEY`；Embedding 沿用独立的 `HERTA_EMBEDDING_*`。Key 仅从本地环境进入内存。建库仍通过 Phase 4 命令显式进行。没有聊天配置时可以读取历史和 health，运行返回 503；不会自动改用 demo。

可配置环境：`HERTA_SERVICE_DB`、`HERTA_SOUL_PATH`、`HERTA_KNOWLEDGE`、`HERTA_RAG_INDEX`、`HERTA_SERVICE_PROVIDER`、`HERTA_SERVICE_PORT`、`HERTA_MAX_ACTIVE_RUNS`。`WEB_CONCURRENCY` 必须为 1。RAG 索引在启动时加载，更新后重启服务。

## HTTP 与事件约定

| 请求 | 结果 |
| --- | --- |
| POST /sessions | 201，新 session_id |
| GET /sessions?after_id=...&limit=20 | 按 ID 分页，默认/上限 100 |
| GET /sessions/{id}?after_seq=0&limit=100 | 完整已提交消息页、Session、最近 Run |
| POST /sessions/{id}/runs，正文仅 text | 接纳后返回 SSE |
| POST /runs/{id}/cancel | accepted、持久 status、瞬时 cancel_requested |
| GET /runs/{id} | 持久 Run 与瞬时取消标志 |
| GET /health | 存储可写性、已装配聊天/RAG、活跃数；不探测外部服务 |

输入 text 为 1–10000 字符且不能全空白；额外字段拒绝，不能提交 system、Key、任意模型历史或文件路径。404 表示不存在，422 无效请求，409 同会话占用，429 全局满额，503 能力或存储不可用。

事件公共字段为 schema_version=1、type、session_id、run_id、seq、timestamp、payload。帧格式：

```text
id: <run_id>:<seq>
event: llm.delta
data: {"schema_version":1,...}

```

正常顺序是 run.started → llm.started → 若干 llm.delta → llm.completed → run.completed；工具轮还包含 tool.started、tool.completed/tool.failed，知识工具成功后再派生 rag.retrieved。每 Step 有独立 message_id。来源与 score 可解释检索过程，不能证明语义正确。

事件队列最多 128 条、累计 2 MiB、单事件最多 256 KiB。生产端默认等待 2 秒，发送端 5 秒，心跳 10 秒（ServiceSettings 可调整）。正常消费不丢事件；持续背压会取消执行，故障清理可以腾掉旧缓冲为终态留位置，不能靠 SSE 重建事实。存储提交失败发送 service.error，明确 persisted=false，GET 保留磁盘事实。Last-Event-ID 请求返回 400；不保存或重放 SSE，不自动重发 POST，通知丢失时 GET 核对。

## 值得精读的五处

1. `SQLiteSessionStore.finish_run`：最终消息、pending 闭合及终态如何在同一事务里保持一致。
2. `PersistentTurn.append`：为什么先 SQLite 成功，再更新当前内存 Session。
3. `RunManager._finish`：取消与完成竞争怎样只确定一个持久结果。
4. `llm/streaming.py:parse_stream`：为何网络块不等于 SSE 帧，结束校验前不能提交完整消息。
5. `RunResponse.__call__`：为什么监听断连必须覆盖接纳期间，而不只是拿到 run_id 之后。

## 实际验证与边界

本批 Task 10 普通 API 6 项、Task 11 SSE 9 项、Task 12 真实 socket 6 项。完整 unittest 已通过 178 项（25.977 秒）；最终复核记录见 progress.md。原 Phase 1–4 的 93 项离线回归继续保留。

Windows 子进程测试动态绑定端口，通过 health 等待就绪，在中文空格临时目录运行。测试涵盖跨会话并行、409/429、增量先于完成到达、主动取消、直接关 socket、接纳期间断连、慢消费者、同会话继续、SQLite 事务失败、通知丢失和重启修复。崩溃夹具通过 stdin 让实际解释器 os._exit(91)，不执行 finally；这是为了绕过 Windows venv 启动器的子进程层，随后父测试等待进程退出并清理文件，不依赖 Linux 信号。不会向生产服务加入崩溃测试接口。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\.venv\Scripts\ruff.exe check backend
.\.venv\Scripts\ruff.exe format --check backend
git -c safe.directory=D:/Desktop/herta-agent diff --check
```

新增 FastAPI/Uvicorn 由 uv 锁定，原有依赖版本未升级。本环境官方 PyPI TLS 失败后使用公开清华镜像，地址记录在 pyproject.toml/uv.lock。服务生命周期使用 FastAPI 的 lifespan 入口，参见 [官方说明](https://fastapi.tiangolo.com/advanced/events/)。

停在 Phase 5；下一阶段 UI 需要消费这套协议，但本阶段不实现 UI。
