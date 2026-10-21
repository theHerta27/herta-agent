# 单元06：在终端看见Agent的执行进度

## 背景问题

当前CLI主要显示最后回答，用户难以跟上工具执行和多次Provider请求。单元06把已有RuntimeEvent接到终端，用一项`--trace`完成可观察的工具闭环；不增加面板、工具或日志存储。用户已明确要求继续，本单元完成后暂停。

核对Session/SQLite后确认，持久化适配仍关联服务RunManager与恢复/并发管理；本轮不把这个较大的改造夹带进进度显示，也不新写JSON会话存储。存储源码已读，本轮没有把它接入CLI或访问已有数据库。

## 核心原理

像施工现场的进度提示，告诉用户“准备开始、已经完成、哪一步没完成”。Agent原本就在关键位置发出事件；observer接收这些通知，终端呈现器只决定怎样展示。

`EventSink`是接收事件的接口，`TerminalEventSink`是它的一个实现，`emit`表示接收并处理一条通知。`observer`由CLI传给原Loop；省略`--trace`时仍使用原NullSink。事件不会成为对话消息，不占模型历史，也不代替工具回填。

`tool.started`在参数校验与批准后、handler前发出。参数错误、未知工具或审批拒绝可能直接产生`tool.failed`，所以显示“未完成”而不虚构“已经开始”。`tool.completed`只说明工具调用完成；`run_tests`还须看`data.status`。取消时没有完成事件就不打印完成；原CLI继续负责取消提示。

## 真实源码和调用链

| 文件 / 函数 | 实际职责 |
|---|---|
| [cli.py](../../backend/herta_agent/cli.py) `main/run_cli/chat/run_turn` | 解析trace；组装终端sink；单条和交互两条路径均将observer传给Agent.run |
| [cli_events.py](../../backend/herta_agent/cli_events.py) `TerminalEventSink.emit` | 选择有限元数据写入stderr；分别处理上下文、Provider开始、工具开始/完成/失败 |
| 同上 `label` | 复用原terminal_text，额外转义换行/制表符并限制标签长度，保持一条事件一行 |
| [runtime/agent.py](../../backend/herta_agent/runtime/agent.py) `Agent.run` | 未修改；已有事件发出位置、工具顺序、提交与取消规则继续生效 |
| [runtime/events.py](../../backend/herta_agent/runtime/events.py) `RuntimeEvent/EventSink/NullSink` | 未修改；事件契约与默认无输出实现 |
| [tools/executor.py](../../backend/herta_agent/tools/executor.py) `execute` | 未修改；真正决定是否调用on_started与handler，不由trace决定权限 |

真实输入为读取公开演示笔记：

```powershell
Set-Location -LiteralPath 'D:\Desktop\herta-agent\.local\worktrees\unit-01-cli-read'
$env:PYTHONPATH = (Join-Path (Get-Location) 'backend')
& 'D:\Desktop\herta-agent\.venv\Scripts\python.exe' -B -X utf8 -m herta_agent --repo examples/cli-read --demo-read-file notes/demo.md --message '请读取演示笔记' --trace
```

实际链路是`main → run_cli创建TerminalEventSink → chat → run_turn → Agent.run(observer=...) → emit`。ReadDemoProvider在第1次请求提出read_file；Executor批准其只读调用，发出started，实际读取后沿TurnIO/Session提交结果，再发出completed；第2次请求接到工具结果后返回正文。

本轮真实输出的轨迹为：

```text
[步骤1] 上下文：估算输入 1948/30464 Token，省略 0 条历史消息
[步骤1] 请求 Provider
[步骤1] 开始工具 read_file
[步骤1] 工具 read_file 调用完成
[步骤2] 上下文：估算输入 2393/30464 Token，省略 0 条历史消息
[步骤2] 请求 Provider
```

随后回答显示演示笔记的真实行号/正文及`steps=2`。第二步估算输入增加，是因为回填了工具调用与结果；数字来自本机估算，不是账单用量，后续代码/文本变化也会改变它。一次Step表示一次Provider请求，不是一个工具；本演示沿用固定Provider，不证明真实模型会选择Read。无须输入yes，无API Key或模型调用。

## 关键设计取舍

- **直接接已有通知**：只新建一个小呈现器，不改Loop、Executor、事件类型、权限、Provider或持久化；不增加依赖和第二套事件历史。
- **输出分工**：轨迹写stderr，原回答和CLI提示继续写stdout。部分PowerShell会给stderr不同颜色，颜色不等于失败。需要看状态和最终退出结果；两种流被外部合并时，显示顺序也可能受终端影响。
- **有限元数据**：只取步骤、工具名、错误代码、测试状态和数值型上下文用量；不打印事件中的系统文本、参数、用户消息、模型文本或工具正文。错误标签转义并有长度上限。原工具/最终回答的显示行为保持不变，这不是全进程的日志脱敏机制。
- **可观察性不干扰工作**：进度流发生OSError/ValueError（例如被关闭）时停用该sink，不因可选进度输出失败中断实际工具。未吞掉其他EventSink或原Runtime的异常。
- **结果语义**：真实失败测试产生`工具 run_tests 调用完成；测试状态=failed`；未知工具等产生“未完成（错误代码）”。未完成不能一概推断从未发生副作用，需看真实工具收据/结果。

## 测试验证

本轮相关基线30项通过；新增8项先失败后通过，最终相关38项通过。完整后端417项中414通过、3项旧语音检查跳过（136.213秒）；规则及本轮3个Python文件格式检查通过。独立静态审查未发现P0–P2实质问题。真实Provider分支的observer接线仅静态核对，运行验证使用离线Provider。

具体命令、实际结果和关键Diff见[执行记录](verification/unit-06/verification.md)及[本单元差异](verification/unit-06/key-diff.patch)。测试走原CLI/Loop/Session/Executor和新建临时文件，覆盖默认关闭、单条及交互接线、实际读取顺序、拒绝前不显示开始、原对话结果保持、错误码单行转义及长度、坏输出流、真实unittest断言失败、取消后不显示完成。

本轮不调用真实模型，不读取私人资料、旧数据库；旧桌面语音和前端未做新的效果验收。当前CLI依然没有会话持久化。单元04～06的本地改动未提交或推送，私密GitHub仍是01～03检查点。

## 动手练习

可选5分钟：先运行上面的演示，再去掉`--trace`运行一次。观察笔记正文和`steps=2`仍存在，而进度提示消失。再把`notes/demo.md`改成`notes/missing.md`：预期显示`path_missing`，最终回答给出工具错误，不会声称读到了正文。只改命令参数，无须改源码或删除任何文件。
