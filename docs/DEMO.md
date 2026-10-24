# 面试演示：先看这一页

这次建议讲“跨模块修复结算Bug”，再用保存的JSON功能记录说明失败反馈和会话恢复。两个都是自建的小型演示项目，由真实DeepSeek选择工具并完成操作；不是生产用户项目，也不是固定工具脚本。

## 已有结果，打开就能看，不调用模型

| 案例 | 实际结果 | 打开这些文件 |
|---|---|---|
| 结算Bug | 先运行看见3失败，修改2个模块，7测试通过；6组独立输入核查通过，原测试未改 | [执行过程](verification/coding-cases-20261024/checkout/trajectory.md)、[真实差异](verification/coding-cases-20261024/checkout/changes.diff)、[检查结果](verification/coding-cases-20261024/checkout/check.json) |
| 字频CLI增加JSON | 新建模块、修改CLI、补5个测试；首次复测发现新增断言漏了换行，修正后8测试通过；原3测试未改 | [执行过程](verification/coding-cases-20261024/wordcount/trajectory.md)、[真实差异](verification/coding-cases-20261024/wordcount/changes.diff)、[检查结果](verification/coding-cases-20261024/wordcount/check.json) |
| 用户拒绝 | 原生确认输入no，工具返回permission_denied，文件仍是原来的2 | [执行过程](verification/coding-cases-20261024/denial/trajectory.md) |
| 外部编辑冲突 | 预览后把文件改为7，再批准原修改；工具拒绝旧快照，外部内容未被覆盖 | [执行过程](verification/coding-cases-20261024/conflict/trajectory.md)、[实际核查](verification/coding-cases-20261024/conflict/check.json) |

这些是历史执行记录，不是正在运行。完整请求次数、外部编辑注入及中断记录见[本轮验证](verification/coding-cases-20261024/verification.md)。

## 想现场再跑一次，照着做

**1. 打开PowerShell，复制这一行并回车。**

```powershell
Set-Location 'D:\Desktop\herta-agent\.local\worktrees\unit-01-cli-read'
```

**2. 创建一份没修过的新练习。**

```powershell
$p = & '.\.venv-cli\Scripts\python.exe' -B -X utf8 examples/coding-task/prepare.py --case checkout | ConvertFrom-Json
$p.project
$p.task
```

屏幕显示新目录和要交给Agent的任务。每次都会新建副本，之前修好的文件保留。

**3. 加载本机已有密钥并运行Agent。** 不会显示密钥；接下来的真实模型请求会产生服务费用。

```powershell
if (-not $env:DEEPSEEK_API_KEY) {
    $env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY', 'User')
}
& '.\.venv-cli\Scripts\herta-agent.exe' --provider openai --repo $p.project --instructions AGENTS.md --max-steps 16 --message $p.task
```

它会先请求运行现有测试。核对项目目录后，选“确认运行”再回车，或输入完整yes再回车。初始3个测试失败是练习故意保留的Bug。

接下来它会自己搜索和读取文件。看到编辑差异时检查内容，再逐次确认；最后确认复测。正常结果是修改shop/cart.py和shop/checkout.py，7项测试通过。步骤顺序和耗时可能变化；16次请求是这一轮的上限，不是费用金额上限。模型失败要如实展示，不要现场手改后说是Agent修好的。

**4. Agent退出后，独立检查实际结果。** 这条命令不调用模型。

```powershell
& '.\.venv-cli\Scripts\python.exe' -B -X utf8 examples/coding-task/check.py $p.project
```

看到passed、tests_passed、independent_behavior_passed、original_tests_unchanged都为true才算这次检查通过。还能直接打开$p.project中的实际文件。

换一台电脑时先按[安装指南](CLI_GUIDE.md)准备Python环境；第一步改成新电脑的仓库路径。想演示新功能，将第2步的checkout换成wordcount，其他步骤相同。

## 3～5分钟怎么讲

1. **约30秒：说任务。** “这个结算项目有数量计算和折后运费两个错误。我只给业务要求，模型自己选择工具。”
2. **约1分钟：看读取与预览。** “模型决定做什么；Harness校验参数、展示真实差异，得到本次确认后才能执行。”
3. **约1分钟：看测试和独立结果。** “工具返回成功不等于业务通过。我检查测试状态、额外输入和原测试指纹，不相信一句已修复。”
4. **约1分钟：解释两个取舍。** “用Read的SHA256防止旧内容覆盖新文件；用完整轮次选择上下文，保留tool_call和tool_result配对。目前工具顺序执行，测试不是沙箱。”
5. **剩余时间：打开JSON案例记录。** 指出新增断言出错后的实际修正，以及终端丢失后恢复历史、先核对文件再继续；不声称中断是专门设计的成功演示。

请求慢时，直接说明正在等待模型，并打开上面的历史记录讲解。可以提前自己录一遍作为备用；本项目目前提供的是录制顺序与真实记录，没有声称已生成演示录像。

## 面试官追问时看哪里

- [核心架构](architecture/cli-v1.md)：用户输入怎样经过唯一Loop、工具执行器和SQLite。
- [Claude Code源码对照](architecture/claude-code-2.1.88-audit.md)：固定快照中的真实调用关系，以及Herta简化了什么。
- [面试问答与简历要点](INTERVIEW.md)：权限、上下文、Provider解耦、异步取消等。

当前GitHub是私密仓库，交付分支为learning/unit-01-cli-read；不要把默认main当成CLI最新版。4821d53是2026-10-23检查点，新增案例与材料维护在同一交付分支，演示前以实际分支提交为准。是否公开或授予面试官访问权由用户决定。
