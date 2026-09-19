# herta-agent

一个边实现边学习的独立桌面 Agent 项目。当前完成 **Phase 1：最小 Python Runtime 骨架**，还没有桌面 UI、工具执行、Persona 或 RAG。

## 直接运行当前成果（PowerShell）

独立 Python 3.12.13 环境已经建立在本项目的 `.venv`。无需激活环境：

```powershell
Set-Location -LiteralPath 'D:\Desktop\herta-agent'
.\.venv\Scripts\python.exe -m herta_agent --message '你好，解释一下 Agent Loop'
.\.venv\Scripts\python.exe -m herta_agent
```

默认是明确标注的离线回显演示，不调用 LLM。交互模式中输入 `/exit` 退出；进程退出后历史消失。

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

已通过 26 项离线自动测试。HTTP 适配器使用 MockTransport 验证请求、响应及异常；尚未验证真实供应商和 API Key。

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

- [Phase 1 逐文件复现教程](D:/Desktop/herta-agent/docs/phase-1-walkthrough.md)
- [完整架构方案](D:/Desktop/herta-agent/docs/architecture.md)
- [Hermes 源码分析](D:/Desktop/herta-agent/docs/hermes-analysis.md)
- [复用计划与许可证记录](D:/Desktop/herta-agent/docs/reuse-plan.md)

当前核心：`用户消息 → 内存历史 → 普通 System Message → Provider → 完整文本 → 历史回填`。Phase 2 将加入工具调用与多步骤闭环；只在用户确认后继续。
