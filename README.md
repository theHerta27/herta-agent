# herta-agent

一个边实现边学习的 Windows 桌面 Agent 项目。当前完成 **Phase 3：独立 Context Builder 与 Persona**，在 Phase 2 工具闭环上加入 soul.md 全文注入、每轮稳定快照与哈希；桌面 UI 与 RAG 属于后续阶段。

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

程序会提示输入不回显的 API Key，不保存到文件。也可由你自行设置当前终端的 `HERTA_API_KEY` 环境变量。接口是非流式 Chat Completions；Base URL 不要包含 `/chat/completions`。

## 检查代码

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\.venv\Scripts\ruff.exe check backend
.\.venv\Scripts\ruff.exe format --check backend
```

已通过 52 项离线自动测试，覆盖 Persona 快照与失败恢复、HTTP 全文注入、工具闭环、预算、取消后继续和 Windows SIGINT 路径。HTTP 适配器使用 MockTransport 验证请求、响应及异常；尚未验证真实供应商和实际人格表现。

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

- [Phase 3 Persona 与 Context 复现教程](D:/Desktop/herta-agent/docs/phase-3-walkthrough.md)
- [Phase 2 工具闭环复现教程](D:/Desktop/herta-agent/docs/phase-2-walkthrough.md)
- [Phase 1 逐文件复现教程](D:/Desktop/herta-agent/docs/phase-1-walkthrough.md)
- [完整架构方案](D:/Desktop/herta-agent/docs/architecture.md)
- [Hermes 源码分析](D:/Desktop/herta-agent/docs/hermes-analysis.md)
- [复用计划与许可证记录](D:/Desktop/herta-agent/docs/reuse-plan.md)

当前核心：`用户消息 → 本轮人格快照 → system + 历史 → Provider → 工具执行与回填 → 同一快照 + 新历史 → 最终文本`。停在 Phase 3，等待下一阶段确认。
