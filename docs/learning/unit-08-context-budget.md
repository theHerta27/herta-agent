# 单元08：配置上下文窗口，观察历史如何取舍

## 背景问题

对话越来越长，每次都把全部记录发给模型会超过容量。可以把Session看成完整笔记本，把一次Provider请求看成有限大小的桌面：笔记本保留原文，桌面只摆本次需要的材料。

项目已有Context Engine，负责估算预算、选择完整轮次和摘取旧历史。本单元只把它的窗口设置接到CLI，增加离线观察演示与验证，不重写上下文算法。

## 核心原理

`window_tokens`是本机预算采用的总窗口；可用输入预算是：

```text
输入预算 = 总窗口 - 输出预留 - 安全余量
默认：32768 - 2048 - 256 = 30464
本次演示：8192 - 2048 - 256 = 5888
```

Token是模型处理文字的单位，这里使用程序估算，不能当作精确计费。预算包含系统文本、所选消息和工具说明。`output_reserve`表示为回答留出空间；当前Provider并未据此发送`max_tokens`，所以2048不是服务端强制输出上限。CLI参数也不能扩大模型实际支持的窗口。

不够放时，先保证系统文本、工具说明和当前用户轮次完整，再从近到远选择旧轮次，必要时增加旧历史节录。当前轮次自身已经放不下，就明确报`context_budget_exceeded`，停止请求Provider；不会截断当前工具结果来假装任务成功。

## 真实源码和调用链

| 实际文件与符号 | 本单元的关系 |
|---|---|
| [cli.py](../../backend/herta_agent/cli.py) `main/run_cli/create_agent` | 修改：解析`--context-window`，构造原ContextSettings，传入原RunSettings；先校验预算，再读取Provider配置 |
| [config.py](../../backend/herta_agent/config.py) `RunSettings.context` | 原有：携带上下文配置，没有另造配置对象 |
| [runtime/agent.py](../../backend/herta_agent/runtime/agent.py) `Agent.__init__/run` | 原有：创建ContextEngine；每个Step准备上下文，再交给Provider |
| [runtime/context_engine.py](../../backend/herta_agent/runtime/context_engine.py) `ContextSettings/_turn_groups/ContextEngine.prepare/_summary` | 原有：验证预算、按用户轮次分组、选择消息、摘取旧记录；本单元未修改 |
| [runtime/session.py](../../backend/herta_agent/runtime/session.py) `Session` | 原有：保存完整消息；prepare返回独立的消息包，不删除Session记录 |
| [演示](../../examples/cli-context/demo.py) `ObservedReadFixture.complete/main` | 新建：记录固定Provider实际收到的消息，并执行原Read工具；不调用模型 |
| [测试](../../backend/tests/test_cli_context.py) | 新建：CLI参数、超限、完整历史、工具配对和失败后的继续使用 |

正式入口的调用链是：`main → run_cli → ContextSettings → RunSettings → create_agent → Agent.__init__ → chat/run_turn → Agent.run → ContextEngine.prepare → Provider.complete`。演示直接用相同组装函数与Loop，不经过CLI参数解析；CLI参数本身另由子进程测试验证。

例如传入`--context-window 8192`，解析后`args.context_window`为整数8192，`ContextSettings.window_tokens`收到它，`prepare`算出5888。`package.messages`是这一次实际交给Provider的消息；`session.history`仍是完整记录。名称中的`package`表示打包好的请求材料，二者不能混为一谈。

实际运行三轮输入`任务1/2/3`，每轮附带800个汉字的模拟背景，并读取自己新建的临时`note.md`。每轮经历“Provider提出Read → 真实读盘和回填 → Provider回答”，因此均为`steps=2`。最终观测：

| 总窗口 | 第三轮最后一次Provider输入 | Session原始消息 | 工具调用与结果 |
|---|---|---|---|
| 8192 | 任务3的完整轮次，另有旧历史节录；估算5144/5888，省略8条原始消息 | 12条 | 全部配对 |
| 32768 | 任务1、2、3的完整轮次，无需节录 | 12条 | 全部配对 |

“省略8条”表示这些原始消息未完整进入本次请求，节录仍可能包含其中片段。每轮4条记录是用户、工具调用、工具结果、最终回答。窗口改变后`context_sha256`仍相同：它是系统文本快照指纹，不是全部请求消息的指纹，不能据此判断是否裁剪。

## 关键设计取舍

- 直接复用原ContextSettings、ContextEngine、Session和事件显示，不增加依赖、第二套Loop或持久化。默认值仍为32768；受原校验约束，CLI整数窗口须大于2304且不超过2000000。窗口有效不代表必然放得下某次任务。
- 按完整用户轮次取舍，保留工具调用与结果的对应关系；不用“随便删前几条”的方式破坏工具协议。节录是`extractive-v1`程序摘取，不是额外模型生成的语义总结。
- [Claude Code官方机制说明](https://code.claude.com/docs/en/how-claude-code-works)介绍了上下文窗口与自动压缩。本项目借鉴容量管理这个机制；当前实现仍是已有的估算和节录，不宣称实现了Claude Code完整自动压缩。
- 超限会结束本次Run，但保留会话；测试直接核对5000字工具结果完整留存，并验证同一Session随后可完成短任务。它不代表超大的当前任务能够自动压缩并继续。

## 测试验证

相关基线44项通过。最初5项测试中3项因CLI不认识新参数失败，原有引擎行为验证已通过；接线后5项全部通过。审查后另补1项会话留存与恢复验证，属于加强证据，没有把已有行为虚构成新修复。初次规则检查的4处长行也已保留记录并修正。

最终相关50项全部通过（17.069秒）；完整后端435项中432通过、3项可选语音跳过（133.841秒）。本轮3个Python文件规则与格式检查通过；独立静态审查无P0–P2问题。实际命令、审查边界与原始日志见[执行记录](verification/unit-08/verification.md)；本轮7个文件的关键差异见[Git Diff](verification/unit-08/key-diff.patch)。两种窗口演示均在本机实际运行；没有真实模型调用、私人文件或原数据库访问，也没有验证供应商的精确Token计数和语义回答质量。

单元01～07已备份到私密GitHub的`learning/unit-01-cli-read`，检查点`683b38a`。本单元08在本地，尚未提交推送；完成后暂停，不进入09。

## 动手练习

可选5分钟，无须修改代码或输入yes。分别运行：

```powershell
Set-Location -LiteralPath 'D:\Desktop\herta-agent\.local\worktrees\unit-01-cli-read'
$env:PYTHONPATH = (Join-Path (Get-Location) 'backend')
& 'D:\Desktop\herta-agent\.venv\Scripts\python.exe' -B -X utf8 examples/cli-context/demo.py --context-window 8192
& 'D:\Desktop\herta-agent\.venv\Scripts\python.exe' -B -X utf8 examples/cli-context/demo.py --context-window 32768
```

找到最后的“Provider收到的完整任务轮次”和“Session保存的原始消息数”。尝试解释为什么前者会变化、后者都是12，以及为什么两个`context_sha256`相同仍不代表请求内容相同。以上表格和源码中的`package.messages/session.history`可作为提示。演示结束自动清理临时资料，不用配置Key。
