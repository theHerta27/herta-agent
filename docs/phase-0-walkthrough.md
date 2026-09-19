# Phase 0 手动复现：从源码找到自己的架构

本阶段练习的产物是分析文档，不是能运行的 Agent。完成后你应该能解释：入口在哪里、循环为什么继续、工具如何返回、Persona 如何进入请求、取消后如何结束。

## 1. 这次新增了什么，为什么

| 新增内容 | 用途 |
| --- | --- |
| references/hermes-agent-main/ | 将参考源码与自己的代码隔开，可以随时查阅；没有安装或运行它 |
| docs/hermes-analysis.md | 记录真实源码位置，避免只凭经验猜实现 |
| docs/architecture.md | 把产品要求拆成模块、数据流和异常路径 |
| docs/reuse-plan.md | 明确复用、重写、跳过的边界及许可证来源 |
| docs/phase-0-walkthrough.md | 本手册，让你自己重做 Phase 0 |
| LICENSES/Hermes-MIT.txt | 原样保留根许可证副本 |
| .gitignore | 把源码参考包、原始材料、密钥及后续本地产物排除在默认 Git 跟踪之外 |
| task_plan.md、findings.md、progress.md | 本次分析的工作记录；不是 Runtime 的组成部分 |

三份原始输入没有修改、移动或重命名；没有创建 backend、apps、soul.md、向量索引、数据库或虚拟环境。

## 2. 先画两条链，不要先搭框架

第一条是程序调用链：

```text
启动入口 → CLI/API → Agent Loop → Provider → Tool Executor → 再回 Loop
```

第二条是数据链：

```text
用户文本 + 历史 + Persona → 模型消息
模型 tool_calls → 参数校验 → 函数结果 → tool message → 下一次模型请求
```

沿函数调用能知道程序往哪里走；沿数据能知道为什么要有这个模块。画图时如果不知道箭头上传的是什么，回到源码看参数和返回值，不急着照抄类名。

## 3. 在桌面新文件夹中复现

下面是给你手动执行的 PowerShell 命令。示例使用 `D:\Desktop\herta-agent-study`，与本次项目分开。为了避免覆盖已有学习成果，第一段在同名目录已存在时会停止；此时改一个新名称。

```powershell
$studyRoot = 'D:\Desktop\herta-agent-study'
if (Test-Path -LiteralPath $studyRoot) {
    throw '这个目录已经存在，请改用一个新的学习目录名。'
}
New-Item -ItemType Directory -Path $studyRoot | Out-Null
foreach ($folder in @('docs', 'references', 'LICENSES')) {
    New-Item -ItemType Directory -Path (Join-Path $studyRoot $folder) | Out-Null
}

Copy-Item -LiteralPath 'D:\Desktop\herta-agent\hermes-agent-main.zip' `
    -Destination (Join-Path $studyRoot 'hermes-agent-main.zip')
Get-FileHash -LiteralPath (Join-Path $studyRoot 'hermes-agent-main.zip') -Algorithm SHA256
```

这里 `Join-Path` 的作用是拼目录，不是字符串硬接反斜杠。你应看见 SHA256 为：

```text
3F5F65CE7BDBE33B59463CBDF20E73CEA5930FBA5B2B9C4515663F5EB2CD72D3
```

然后解压这份已核对的参考包，并阅读实际许可证：

```powershell
Expand-Archive -LiteralPath (Join-Path $studyRoot 'hermes-agent-main.zip') `
    -DestinationPath (Join-Path $studyRoot 'references')
$sourceRoot = Join-Path $studyRoot 'references\hermes-agent-main'
Get-Content -LiteralPath (Join-Path $sourceRoot 'LICENSE') -Raw
Copy-Item -LiteralPath (Join-Path $sourceRoot 'LICENSE') `
    -Destination (Join-Path $studyRoot 'LICENSES\Hermes-MIT.txt')
```

解压可能需要一些时间。不要运行 Hermes 的安装脚本，不需要填写 API Key；静态阅读源码不需要创建虚拟环境或安装依赖。也暂时不需要复制角色原始语料到学习目录。

## 4. 从命令入口找到 while 循环

有 rg 时先执行：

```powershell
Set-Location -LiteralPath $sourceRoot
rg -n 'project.scripts|hermes =' pyproject.toml
rg -n '^def main|^def cmd_chat|cli_main' hermes_cli/main.py
rg -n '^class AIAgent|TurnFacadeMixin|_execute_tool_calls' run_agent.py
rg -n 'def run_conversation|_run_conversation_turn|while |run_tool_round' agent/conversation_loop.py
```

Windows PowerShell 下不要依赖 `rg agent/*loop*.py` 这样的路径通配符展开。用 `rg -g '*loop*.py' 'pattern' agent`，或像上面那样指定明确文件名。

如果你的机器没有 rg，不必为这个阶段安装它，可使用自带的 Select-String：

```powershell
Select-String -LiteralPath '.\pyproject.toml' -Pattern 'project.scripts','hermes ='
Select-String -LiteralPath '.\agent\conversation_loop.py' `
    -Pattern 'def run_conversation','_run_conversation_turn','while ','run_tool_round'
```

不建议从 run_agent.py 第一行一路读到最后。先定位 `agent/conversation_loop.py` 第 1520 行附近，把 while 中的分支读明白，再沿 helper 函数进入下层。

想打印带行号的小段，可以在当前 PowerShell 定义一个只读辅助函数：

```powershell
function Show-SourceLines($Path, $Start, $End) {
    $lineNumber = 0
    Get-Content -LiteralPath $Path | ForEach-Object {
        $lineNumber++
        if ($lineNumber -ge $Start -and $lineNumber -le $End) {
            '{0}: {1}' -f $lineNumber, $_
        }
    }
}
Show-SourceLines '.\agent\conversation_loop.py' 1520 1576
```

这只是终端里的阅读辅助，不是项目业务代码。

## 5. 本阶段精读的 5 个函数

| 函数 | 源码位置 | 你需要亲自找到的内容 |
| --- | --- | --- |
| _run_conversation_turn | agent/conversation_loop.py:1429 | 初始化、while 条件、工具/最终文本分支、收尾 |
| run_tool_round | agent/turn_tool_round.py:45 | assistant tool_calls 入历史、执行工具前持久化、派发调用 |
| ToolRegistry.dispatch | tools/registry.py:874 | 名称查找、handler(args)、未知工具与异常处理 |
| build_system_prompt_parts | agent/system_prompt.py:659 | stable/context/volatile；继续追 _identity_parts 与 load_soul_md |
| InterruptControlMixin.interrupt | agent/interrupt_control.py:109 | 取消状态、请求中止、工具线程信号 |

围绕第 3 个函数再看 register:649 和 get_definitions:824：你会发现“schema 已存在”和“自动从参数类生成 schema”是两回事。

围绕第 4 个函数再看 `agent/turn_context.py:1151–1155`：找到 system 消息真的加入模型请求的位置。只有读到了实际请求组装处，才能证明 Persona 被模型看见。

围绕第 5 个函数再看 `agent/tool_executor.py:895–935`：找到超时后放弃等待的位置，解释为什么这不能保证线程已经停止。

## 6. 自己写三份文档

先创建空文档，然后用自己的话填写，不建议直接复制本项目的成品：

```powershell
foreach ($name in @('hermes-analysis.md', 'architecture.md', 'reuse-plan.md')) {
    New-Item -ItemType File -Path (Join-Path $studyRoot "docs\$name") | Out-Null
}
notepad (Join-Path $studyRoot 'docs\hermes-analysis.md')
```

hermes-analysis.md 每节按这个模式写：问题 → 实际文件与函数 → 关键行为 → Herta 如何处理。至少覆盖入口、循环、工具、上下文、Persona、会话、超时、取消。

architecture.md 先写完整请求链，再按责任分目录。对每个模块回答三个问题：收什么、产出什么、不该负责什么。最后补上超时、取消、预算耗尽和断线后的行为。

reuse-plan.md 每行写清：Hermes 文件 → Herta 目标职责 → reuse/adapt/rewrite/skip → 原因。不能只写“参考 Hermes”，也不要因为可复用就整体复制。

此时实际目录仍只需 docs、references、LICENSES。最终目录树写在 architecture.md 中即可；等下一阶段真正要实现 Provider 时，才创建 llm/base.py。

## 7. 用一组纸面消息走完 Agent Loop

请自己写下这五步，并在每步旁边标出对应模块：

1. messages 先有 system 和 user。
2. 模型返回 assistant，内含 id 为 call_1 的 search_knowledge 调用。
3. 参数校验后执行工具，拿到 chunks。
4. 历史追加 role=tool、tool_call_id=call_1 的结果。
5. messages 再次交给 LLM，它输出普通文本，本轮结束。

然后分别替换第 3 步：非法 JSON、工具超时、用户取消。前两种可以返回错误工具结果并在预算内继续；取消则关闭工具配对、保存取消状态并停止，不再请求模型。

最后问自己：如果只把 chunks 数量显示在界面，但没有第 4 步，模型能看到检索结果吗？如果不知道两次模型请求为什么都需要带 soul.md，再回看 Context 一节。

## 8. 本阶段的运行命令和测试

Phase 0 没有应用启动命令，也没有项目单元测试；不能用 `pytest 通过` 来描述这次结果。你现在能运行的是上面的源码阅读命令，以及下面的文档/来源检查。

在前面变量仍存在的同一个 PowerShell 中执行：

```powershell
$phase0Docs = @('hermes-analysis.md', 'architecture.md', 'reuse-plan.md')
foreach ($name in $phase0Docs) {
    $path = Join-Path $studyRoot "docs\$name"
    if (-not (Test-Path -LiteralPath $path)) { throw "缺少文档：$name" }
    if ((Get-Item -LiteralPath $path).Length -eq 0) { throw "文档仍为空：$name" }
}
$originalLicense = (Get-FileHash -LiteralPath (Join-Path $sourceRoot 'LICENSE')).Hash
$savedLicense = (Get-FileHash -LiteralPath (Join-Path $studyRoot 'LICENSES\Hermes-MIT.txt')).Hash
if ($originalLicense -ne $savedLicense) { throw '许可证副本与原文件不一致' }
'Phase 0 文件与许可证检查通过'
```

注意：文件存在不证明分析正确。还需要在源码里逐项确认文档中的函数和行号，并口头解释这五个问题：

- 为什么 Runtime 与桌面 UI 应该独立？
- schema、参数解析和参数校验的区别是什么？
- tool_call_id 配对解决什么问题？
- Always-on Persona 与 RAG 的差别是什么？
- max_steps、timeout 和 cancellation 分别限制什么？

本项目的实际静态核验记录在 progress.md。业务自动测试从 Phase 1 开始，每个阶段同步加入必要用例。

## 9. 到这里停下来

本阶段交付完成的标准是：三份分析文档能从源码找到证据，你能画出正常和异常路径，并知道为什么选这些目录。

下一阶段只会做最小 Python Agent Loop，不提前实现 Persona、RAG、FastAPI 或 Electron。根据你的原始要求，必须等你确认 Phase 0 后才开始。
