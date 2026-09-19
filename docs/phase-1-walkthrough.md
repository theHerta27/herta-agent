# Phase 1：亲手实现最小 Python Agent Runtime

本阶段完成了可运行的基础骨架：独立 Python 包、类型明确的消息、内存会话、可替换 Provider、受限请求、CLI 与自动测试。你可以先离线运行，再自己填 API 配置接入模型。

**没有工具时，正常每个 Run 只需要调用模型一次。** 所以当前实现是 Agent Loop 的基础骨架；真正的“模型 → 工具 → 模型”多步骤循环留在 Phase 2。不会为了演示 while/for 人为连续调用模型。

## 1. 先运行，再读代码

打开 PowerShell，执行：

```powershell
Set-Location -LiteralPath 'D:\Desktop\herta-agent'
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m herta_agent --message '你好'
```

本次环境输出 Python 3.12.13。单轮演示的预期输出：

```text
模式：离线演示（固定逻辑，不调用 LLM，不读取 API Key）
Assistant: [离线演示，第 1 轮] 收到：你好
[steps=1]
```

离线演示只回显输入与历史用户消息数量，它不会真的回答问题，也不是大黑塔 Persona。它的用途是让你在没有 Key 时先验证程序各层接起来了。

再体验连续两轮：

```powershell
.\.venv\Scripts\python.exe -m herta_agent
```

分别输入“第一句”“第二句”，第二次输出应包含“第 2 轮”。输入 `/exit` 退出。重新启动后又从第 1 轮开始，因为目前历史只保存在内存。

## 2. 实际新增目录及每个文件的职责

```text
herta-agent/
├─ backend/
│  ├─ pyproject.toml                 # 包元信息、Python 要求、依赖和 lint 配置
│  ├─ uv.lock                        # uv 自动生成；记录精确依赖与哈希
│  ├─ herta_agent/
│  │  ├─ __init__.py                 # 标记 Python 包
│  │  ├─ __main__.py                 # 命令行入口、选择 Provider、读取输入
│  │  ├─ config.py                   # 配置边界、SecretStr、超时/步数验证
│  │  ├─ runtime/
│  │  │  ├─ __init__.py
│  │  │  ├─ messages.py              # Message、ModelReply、RunResult
│  │  │  ├─ session.py               # 有序内存历史与同会话忙碌状态
│  │  │  ├─ agent.py                 # run 的执行路径
│  │  │  └─ errors.py                # 可辨识的预期异常
│  │  └─ llm/
│  │     ├─ __init__.py
│  │     ├─ base.py                  # LLMProvider 接口
│  │     ├─ demo.py                  # 明确标注的离线模拟
│  │     └─ openai_compatible.py     # 真实兼容 HTTP 接口适配
│  └─ tests/
│     ├─ test_runtime.py             # 历史、隔离、异常、超时、取消、配置
│     ├─ test_provider.py            # HTTP 契约与错误响应
│     └─ test_cli.py                 # CLI 子进程与交互模式
├─ .venv/                           # 本项目虚拟环境，已忽略
├─ .local/                          # Python 安装和 uv 缓存，已忽略
├─ README.md                        # 日常运行入口
└─ docs/phase-1-walkthrough.md       # 本教程
```

只引入两个直接运行依赖：Pydantic、HTTPX；Ruff 是开发检查工具，测试使用 Python 自带 unittest。uv.lock 中还会看到它们的传递依赖，这是正常的。

没有创建 tools、rag、api、apps 或 persona 的占位实现。现有角色原始语料与参考源码没有修改。工作记录、架构状态、复用记录和 .gitignore 随本阶段更新。

目录为什么这样拆：Runtime 应该能在没有 HTTP/桌面的情况下工作；Provider 应该能被假的实现替换；Session 应该负责消息顺序，而不是让 CLI 和 Provider 各维护一份历史。

## 3. 程序从哪里开始，数据往哪里走

```text
python -m herta_agent
  → __main__.main()：解析命令行，启动 asyncio
  → run_cli()：校验配置，选择 Demo 或 HTTP Provider
  → chat()：创建一个 Session，接收用户输入
  → Agent.run(session, text)
      → Message 校验用户内容
      → Session.begin_turn()：防止重叠执行，保存 user
      → 普通 system + Session.history 快照
      → await provider.complete(messages)
      → Session.complete_turn()：保存完整 assistant
      → RunResult(reply, steps, session_id)
      → finally: Session.end_turn()
  → CLI 显示结果
```

第二次请求看到的内容大致是：

```text
system: 普通助手规则
user: 第一轮输入
assistant: 第一轮回答
user: 第二轮输入
```

System Message 每次请求添加一次，但不保存在普通会话历史里，因此不会随着轮次越来越多地重复叠加。当前普通助手规则不是 soul.md；Persona 注入在 Phase 3 实现。

## 4. 你最值得精读的 5 个函数

| 阅读顺序 | 函数 | 重点 |
| --- | --- | --- |
| 1 | [Agent.run](D:/Desktop/herta-agent/backend/herta_agent/runtime/agent.py:19) | 一轮输入如何形成请求、保存输出和清理状态 |
| 2 | [Session.begin_turn](D:/Desktop/herta-agent/backend/herta_agent/runtime/session.py:21) | 为什么先拒绝同会话重叠执行，再追加用户消息 |
| 3 | [OpenAICompatibleProvider.complete](D:/Desktop/herta-agent/backend/herta_agent/llm/openai_compatible.py:39) | HTTP 请求发送的究竟是什么，与 Runtime 如何隔开 |
| 4 | [OpenAICompatibleProvider._parse_reply](D:/Desktop/herta-agent/backend/herta_agent/llm/openai_compatible.py:64) | 为什么 HTTP 200 不一定意味着得到有效完整回答 |
| 5 | [run_cli](D:/Desktop/herta-agent/backend/herta_agent/__main__.py:47) | 谁创建配置和网络客户端，谁负责关闭资源 |

第一遍只读这些函数。第二遍再打开 messages.py、config.py 和测试，不需要从所有文件的第一行开始逐字读。

## 5. 需要理解的 Python 知识点

**Pydantic**：Message 限制 role 和非空文本；RunSettings 拒绝非法步数、非有限超时；ProviderSettings 隐藏 Key 的 repr，验证 Base URL。`frozen=True` 防止历史消息在别处被直接改写。配置与消息不是任意 dict，这让错误更早出现。参考 [Pydantic Models](https://docs.pydantic.dev/latest/concepts/models/)。

**Protocol**：LLMProvider 描述一个 `async complete(messages) -> ModelReply` 能力。DemoProvider 和 OpenAICompatibleProvider 无需继承同一个大基类，只要提供这个接口，Agent 就能使用。它是类型契约，不是运行时插件系统。

**async / await**：请求模型期间允许事件循环处理取消。`await` 不是开启一个新线程；`async def` 也不会让同步死循环自动变成可取消任务。

**try/finally**：即使 Provider 超时、抛异常或被取消，end_turn 仍执行。这比只在成功分支把 busy 改回 False 更可靠。取消异常继续向外传播，不变成一条假的 assistant 回复。

**HTTPX 客户端生命周期**：CLI 创建一次 AsyncClient，在多轮之间复用，退出时用 async with 关闭；Provider 接收这个客户端而不控制其生命周期。测试可以注入 MockTransport，不产生外部网络请求。参考 [HTTPX 异步支持](https://www.python-httpx.org/async/)与 [MockTransport 文档](https://www.python-httpx.org/advanced/transports/)。

**CLI 输入的局部取舍**：等待键盘时没有正在运行的模型任务，因此教学 CLI 使用普通 input，并对这一行作 Ruff 豁免。不要把这段输入代码搬进未来 FastAPI；Runtime 和 Provider 的网络路径仍是异步的。Ctrl+C 在 CLI 中取消并退出，尚未实现“取消当前轮后继续停留在 UI”。

Windows 的管道默认编码可能不是 UTF-8。CLI 入口仅对重定向的标准输入/输出设置 UTF-8，使终端、测试子进程与应用捕获输出时中文保持一致；真实交互控制台继续使用其原有编码处理。

## 6. 在你的学习目录里按顺序实现

如果你已在 Phase 0 建立 `D:\Desktop\herta-agent-study`，直接用它。没有建立也可以先新建；不要把我的 .venv 复制过去。

```powershell
$studyRoot = 'D:\Desktop\herta-agent-study'
New-Item -ItemType Directory -Path $studyRoot -Force | Out-Null
Set-Location -LiteralPath $studyRoot
foreach ($folder in @('backend\herta_agent\runtime', 'backend\herta_agent\llm', 'backend\tests')) {
    New-Item -ItemType Directory -Path (Join-Path $studyRoot $folder) -Force | Out-Null
}
```

按下面顺序逐个创建文件。可以对照本项目文件亲手敲，或一次复制一个文件后逐行解释；不要一次性复制整个项目而跳过数据流。

| 步骤 | 写哪些文件 | 写完应能回答什么 |
| --- | --- | --- |
| A | backend/pyproject.toml；三个 __init__.py | 包名为何是 herta-agent，而 import 用 herta_agent？ |
| B | config.py、runtime/messages.py、runtime/errors.py | 输入与输出各是什么类型，哪些值不合法？ |
| C | runtime/session.py | 历史属于哪个对象，失败时保留什么？ |
| D | llm/base.py、llm/demo.py | Agent 为什么不用知道供应商名称？ |
| E | runtime/agent.py | 一次完整执行在哪里结束，finally 为什么不能省？ |
| F | llm/openai_compatible.py、__main__.py | HTTP 与命令行怎样接到同一套 Runtime？ |
| G | tests/ 下三个文件 | 不花模型费用如何测试失败与取消？ |

在 F 完成后安装项目。已有 uv 的 PowerShell 可以直接运行：

```powershell
$env:UV_PYTHON_INSTALL_DIR = Join-Path $studyRoot '.local\python'
$env:UV_CACHE_DIR = Join-Path $studyRoot '.local\uv-cache'
$env:UV_PROJECT_ENVIRONMENT = Join-Path $studyRoot '.venv'
uv sync --project backend --extra dev --python 3.12
```

这条命令会取得所需 Python、创建自己的 .venv、安装项目及依赖，并生成自己的 backend/uv.lock。需要网络；不同时间首次解析可能产生不同依赖版本。若要与本次版本完全对齐，先把本项目 backend/uv.lock 复制到学习目录 backend，再在 sync 命令末尾加 `--locked`。

本机已经有 uv；它的可执行文件位于现有工具目录，但这里安装目标和 Python 完全属于你的学习项目。不要直接使用当前 PATH 的 `python`，本机那个解释器属于 Hermes 3.11。

没有 uv 但已安装 Python 3.12+ 的机器，也可以用标准 venv 与 pip：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.\backend[dev]'
```

这条替代路线不读取 uv.lock；要求机器确实已安装、注册 Python 3.12。本次机器的 py 启动器找不到已注册解释器，因此我实际使用的是上面的 uv 路线。

后续运行统一使用 `.\.venv\Scripts\python.exe`，无需执行 Activate.ps1，也不用修改 PowerShell 执行策略。

## 7. 自己接入真实模型

在项目根目录设置服务商实际给你的 API 根地址和模型标识：

```powershell
$env:HERTA_BASE_URL = 'https://你的服务地址/v1'
$env:HERTA_MODEL = '你的模型名'
.\.venv\Scripts\python.exe -m herta_agent --provider openai --message '用一句话解释 Agent Loop'
```

此命令会提示输入 API Key，不回显、不写文件。不需要将 Key 发给我。已经通过环境变量设置 `HERTA_API_KEY` 时，不再提示输入。

如果服务提供的是 `/api/v1` 根路径，就原样填写 `/api/v1`；程序只在末尾加 `/chat/completions`，不会猜测或改写根路径。无鉴权本地兼容服务可显式填写占位 Key `local`。

当前协议只接受一条正常结束的文本回答；工具调用、截断、过滤、空回答或错误结构会明确报错，不当成成功。没有自动重试，也没有自动续写。本阶段没有提供真实端点与 Key，所以已完成的是适配器及离线契约测试，尚未完成真实模型联调。

## 8. max_steps 和 timeout 到底限制什么

```powershell
.\.venv\Scripts\python.exe -m herta_agent --max-steps 1 --timeout 30 --message 'hello'
```

max_steps 限制一个 Run 内模型请求尝试数，不限制一段对话可聊几轮，也不限制输出 token。当前所有合法回复都直接结束，因此 steps=1；最大步数之后的 StepLimitExceeded 分支是 Phase 2 工具循环的预留边界，目前不可达。

本阶段实际验证的是：max_steps 必须是 1–100 的整数、设置为 1 时能完成且只请求一次、不对错误暗中重试。**没有宣称已经验证多步工具循环或预算耗尽行为。** 等 Phase 2 引入 continue 分支，再添加一直要求调用工具的模拟模型，验证真实的预算耗尽。

timeout 限制本次模型调用的整体等待时间；HTTPX 另有连接/读取超时。用户取消、超时和 Provider 错误都不会追加假的 assistant 回复，用户输入仍留在历史里，下一次调用可继续使用该 Session。退出 CLI 会丢失内存历史；数据库恢复属于后续阶段。

## 9. 运行测试并理解它们证明了什么

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\.venv\Scripts\ruff.exe check backend
.\.venv\Scripts\ruff.exe format --check backend
```

当前共有 26 项测试：

| 范围 | 验证行为 |
| --- | --- |
| CLI 4 项 | 默认离线启动、连续两轮、真实模式缺配置、非法预算提前失败 |
| HTTP 8 项 | URL/请求体/鉴权、历史传递、正常响应、错误状态、非法 JSON、工具拒绝、网络错误、总超时取消 |
| Runtime 与配置 14 项 | 历史顺序、会话隔离、不可变快照、空输入、失败不重试、超时/取消清理、重叠执行、单步预算、配置边界 |

真实 HTTP 适配器也参与测试，只有网络传输被 MockTransport 替换。它证明请求和响应转换符合我们约定，不证明任意兼容服务商都一定能工作。

## 10. 三个动手练习

1. 在你自己的 DemoProvider 中改变回复文字，重新运行。观察 Agent.run 为什么不需要改。
2. 把 `--max-steps` 改成 0，再把 `--timeout` 改成 -1。观察错误发生在配置阶段，而不是请求模型之后。
3. 阅读 test_cancellation_propagates_without_fake_answer：它先等 Provider 真正进入等待，再 cancel，最后验证同一个 Session 可以再次运行。解释为什么它比单纯检查一个 cancel 标志更有意义。

完成后你应能亲口解释：Provider 接口隔离了什么、历史为什么不含重复 system、异常为什么不会让 busy 永远锁住、离线演示与真实模型分别验证了哪些部分。

本阶段到此结束。下一阶段才增加 Tool Registry、一个无副作用测试工具、参数 schema/验证和工具结果回填，等你确认后继续。
