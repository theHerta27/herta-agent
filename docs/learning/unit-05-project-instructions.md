# 单元05：把明确选择的项目约定送进上下文

## 背景问题

工具已经能读、搜、改、测，但每个项目还有命名习惯、目录结构和解释要求。像给新同事一页项目说明，先把这些约定交给模型，避免每轮重复输入。本单元只接已有ContextBuilder入口，不增加工具、服务、依赖或第二套Agent Loop。用户已要求继续下一单元；完成后停在05。

## 核心原理

上下文是每次请求模型时带上的材料，不是模型参数训练。项目约定是明确选入的指导文字；普通Read结果仍是文件数据。约定可以建议怎样工作，但“无需确认”这样的文字不能让Executor跳过权限检查。

| 名称 | 本单元中的含义 |
|---|---|
| 项目约定 | 通过`--instructions`选择的一个文件，例如AGENTS.md；扩展名不决定功能，参数才决定加载 |
| snapshot（快照） | 本轮开始读一次得到的不可变系统文本；中途改规则不会令同一轮前后矛盾 |
| 下一轮重新读取 | 下一个用户消息才使用新规则；不是自动学习，也没有会话持久化 |
| guided-development Skill | Codex与用户的教学约定；Herta本轮只加载一份文字，不会因此执行Skill流程 |

## 真实源码和调用链

| 文件 / 函数 | 实际职责 |
|---|---|
| [cli.py](../../backend/herta_agent/cli.py) `main/run_cli/create_agent` | 解析`--instructions`并传给上下文组装；省略时继续使用原StaticContextBuilder |
| [project_context.py](../../backend/herta_agent/project_context.py) `ProjectContextBuilder.snapshot` | 复用Repository与有界UTF-8读取；检查单个文件，把来源与正文编码成JSON，再返回原ContextSnapshot |
| [runtime/agent.py](../../backend/herta_agent/runtime/agent.py) `Agent.run` | 未修改；每Run调用一次snapshot，每Step用同一快照准备请求 |
| [runtime/context.py](../../backend/herta_agent/runtime/context.py) `ContextSnapshot` | 未修改；生成指纹，统一注入system消息，不把system写进Session历史 |
| [演示](../../examples/cli-instructions/demo.py) `InspectContextFixture.complete` | 观察真实Provider入口收到的system内容；离线脚本，不会理解并执行项目约定 |

真实演示第一轮创建`AGENTS.md`，内容为`- 解释改动时先说原因。`：

`create_agent(instructions="AGENTS.md") → run_turn → Agent.run → ProjectContextBuilder.snapshot → ContextSnapshot → ContextEngine.prepare → InspectContextFixture.complete → print_result`。

第一轮显示这句实际规则和`steps=1`；演示脚本修改自己的临时文件为`- 解释改动时给一个具体例子。`；第二轮通过同一Agent/Session显示新规则，`steps=1`，最后`两轮上下文指纹是否变化：True`。变化源自文件重读，不能解释成模型自行变聪明。另有测试在一次工具调用中间修改规则，确认同一Run仍使用原快照。

```powershell
Set-Location -LiteralPath 'D:\Desktop\herta-agent\.local\worktrees\unit-01-cli-read'
$env:PYTHONPATH = (Join-Path (Get-Location) 'backend')
& 'D:\Desktop\herta-agent\.venv\Scripts\python.exe' -B -X utf8 examples/cli-instructions/demo.py
```

演示无须输入yes，不调用模型、不读取API Key，只创建并清理本次临时项目。若通过生产CLI使用`--instructions`，必须明确选择项目相对路径；本轮没有在真实模型模式发送任何文件。

## 关键设计取舍

- **显式选择**：没有自动寻找根目录、父目录、用户目录或子目录规则，没有`@文件`导入。普通文件中的命令不会被程序执行，约定中的命令也不会自动运行；需要工具调用和原权限检查。
- **薄适配器**：新文件放在CLI组装侧，使用已有ContextBuilder协议；Runtime无需依赖Coding工具。Repository、有界读取、ContextSnapshot、ContextEngine和Executor均直接复用，不复制。没有新依赖或上游源码移植。
- **可解释失败**：仅项目内无链接的普通文件，非空、UTF-8（允许BOM）、最多16 KiB；无效输入在Provider请求前报ContextError，不默默使用缺失规则。范围检查不构成对恶意并发换文件的操作系统隔离。
- **保持权限边界**：文件文字写“允许所有编辑”也不会提供批准回调。JSON编码便于分清来源和正文，不是提示词注入防护保证；真实模型遵循与冲突处理效果仍未验证。
- **参考边界**：[Claude Code官方项目说明文档](https://code.claude.com/docs/en/memory)（2026-10-21读取）把项目说明作为上下文，区别于强制执行的配置。本单元只学习这个机制；单文件、显式选入、每Run刷新是Herta的小范围实现，不冒充Claude完整层级、自动记忆或Skills。

## 测试验证

本轮相关基线68项通过；新增9项检查通过；最终完整后端409项中406通过、3项旧语音检查跳过（128.489秒）。全后端/既有Harness评测/本演示规则检查通过，本轮4个Python文件格式检查通过。独立审查的循环链接异常已由真实失败夹具复现、修复并复核，无剩余重要问题。

具体命令、实际结果、原始失败、来源与本轮Diff见[执行记录](verification/unit-05/verification.md)。测试使用真实临时文件、原Agent Loop/Session/Executor和离线Provider边界，检查实际收到的上下文及真实文件未被越权修改；未读取现有私人资料、数据库，未调用模型，也未验收旧语音功能。单元04的3项语音跳过说明及完整演示操作已补入[单元04](unit-04-test-and-verify.md)。

## 动手练习

可选5分钟观察：运行本单元演示，指出哪一行说明第二轮读取了新约定，比较两轮`steps`和`context_sha256`。提示：`steps=1`表示一轮只请求一次Provider；指纹变化表示系统文本变化，不代表保存了对话或训练了模型。可以只读结果，不必手写代码。完成本单元后暂停，不进入06。
