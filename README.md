# herta-agent

一个边实现边学习的 Windows 桌面 Agent 项目。当前实现 **Phase 5：本机后端服务**，包含 SQLite 会话持久化、Run 生命周期、真正的模型流式协议适配、FastAPI 与 POST SSE；保留独立 Persona/Context Builder 和 Phase 4 角色知识 RAG。真实供应商流式兼容性与真实 RAG 效果仍待配置后验收；桌面 UI 尚未实现。

## 运行持久化服务（PowerShell）

```powershell
Set-Location -LiteralPath 'D:\Desktop\herta-agent'
.\.venv\Scripts\python.exe -m herta_agent.service --provider demo
```

服务监听 `127.0.0.1:8765`，单 worker，SQLite 默认位于 `.local/sessions.sqlite3`。显式 demo 完全离线；默认 openai 未配置时运行请求明确拒绝。完整的创建会话、SSE、取消和重启命令见 [Phase 5 教程](D:/Desktop/herta-agent/docs/phase-5-walkthrough.md)。原 CLI 仍可独立使用，CLI 会话保存在内存中。

## 直接运行当前成果（PowerShell）

独立 Python 3.12.13 环境已经建立在本项目的 `.venv`。无需激活环境：

```powershell
Set-Location -LiteralPath 'D:\Desktop\herta-agent'
.\.venv\Scripts\python.exe -m herta_agent --message '你好，解释一下 Agent Loop'
.\.venv\Scripts\python.exe -m herta_agent --demo-tools --message '你好，黑塔'
.\.venv\Scripts\python.exe -m herta_agent
```

默认是明确标注的离线回显演示，不调用 LLM。`--demo-tools` 会通过真实执行器完成两步 echo 闭环。交互模式中 Ctrl+C 取消当前轮并保留会话，输入 `/exit` 退出；进程退出后历史消失。

CLI 必须成功加载 `persona/soul.md`，每轮重新读取、该轮所有 Step 使用同一份完整内容。加载失败明确报错，不降级；交互模式修复文件后可继续同一会话。默认路径不依赖启动目录；用 `--soul 'D:\路径\soul.md'` 可显式指定。输出的 `context_sha256` 标识实际注入正文。离线演示验证注入链路，角色语气需要真实模型验证。

## 使用真实模型

填写你实际使用的兼容服务地址与模型名，再运行。以下两个值是需要替换的占位符：

```powershell
$env:HERTA_BASE_URL = 'https://你的服务地址/v1'
$env:HERTA_MODEL = '你的模型名'
.\.venv\Scripts\python.exe -m herta_agent --provider openai
```

Key 仅从当前终端的 `HERTA_API_KEY` 环境变量读取，不再由应用提示输入。CLI 使用非流式 Chat Completions，服务使用流式入口；Base URL 不要包含 `/chat/completions`。

Embedding 使用独立的 `HERTA_EMBEDDING_BASE_URL`、`HERTA_EMBEDDING_MODEL`、`HERTA_EMBEDDING_API_KEY`，不默认复用聊天服务。Key 不写文件、索引或日志。本地安全输入方法、完整配置与评测说明见 [Phase 4 教程](D:/Desktop/herta-agent/docs/phase-4-walkthrough.md)。配置后：

```powershell
.\.venv\Scripts\python.exe -m herta_agent.rag build
.\.venv\Scripts\python.exe -m herta_agent.rag inspect '黑塔如何评价螺丝咕姆？'
.\.venv\Scripts\python.exe -m herta_agent.rag eval --mode retrieval --split dev
.\.venv\Scripts\python.exe -m herta_agent --provider openai
```

建库发送知识片段给 Embedding 服务；查询发送 query。检索证据经工具消息提供给聊天模型，不进入 system。默认阈值尚未校准，score 不代表事实置信度。RAG 不可用会明确提示，普通聊天仍可继续；人格文件失败仍停止当前轮。

## 检查代码

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\.venv\Scripts\ruff.exe check backend
.\.venv\Scripts\ruff.exe format --check backend
```

已通过 178 项离线自动测试，保留原 Phase 1–4 的 93 项。新增覆盖持久提交、取消竞争、流式协议、API/SSE、Windows 真实 socket、慢消费者和进程骤停恢复；本批真实 HTTP 使用注入的离线 Provider。未调用真实模型或 Embedding API，未验证实际语义召回、模型路由和据证回答。

## 安装或重新建立环境

使用已有 uv，在项目根目录运行：

```powershell
$env:UV_PYTHON_INSTALL_DIR = Join-Path (Get-Location) '.local\python'
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.local\uv-cache'
$env:UV_PROJECT_ENVIRONMENT = Join-Path (Get-Location) '.venv'
uv sync --project backend --extra dev --python 3.12 --locked
```

`backend/pyproject.toml` 声明依赖，`backend/uv.lock` 固定本次解析版本。不要把其他项目的 `.venv` 复制过来，也不要使用机器上指向 Hermes 的默认 Python 安装依赖。

## 学习入口

- [Phase 5 服务复现与验收边界](D:/Desktop/herta-agent/docs/phase-5-walkthrough.md)
- [Phase 5 设计](D:/Desktop/herta-agent/docs/phase-5-design.md) / [实施计划](D:/Desktop/herta-agent/docs/phase-5-plan.md)

- [Phase 4 RAG 复现教程与验收边界](D:/Desktop/herta-agent/docs/phase-4-walkthrough.md)
- [Phase 4 设计](D:/Desktop/herta-agent/docs/phase-4-design.md) / [实施计划](D:/Desktop/herta-agent/docs/phase-4-plan.md)
- [Phase 3 Persona 与 Context 复现教程](D:/Desktop/herta-agent/docs/phase-3-walkthrough.md)
- [Phase 2 工具闭环复现教程](D:/Desktop/herta-agent/docs/phase-2-walkthrough.md)
- [Phase 1 逐文件复现教程](D:/Desktop/herta-agent/docs/phase-1-walkthrough.md)
- [完整架构方案](D:/Desktop/herta-agent/docs/architecture.md)
- [Hermes 源码分析](D:/Desktop/herta-agent/docs/hermes-analysis.md)
- [复用计划与许可证记录](D:/Desktop/herta-agent/docs/reuse-plan.md)

当前核心：`用户消息 → 本轮人格快照 → system + 历史 → Provider → 工具执行与知识检索回填 → 同一快照 + 新历史 → 最终文本`。停在 Phase 4，未进入下一阶段。
