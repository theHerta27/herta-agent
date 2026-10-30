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

**先按Ctrl+C，确认光标前面是正常的PS提示符。** 如果看到单独的`>>`，说明上一条命令还没结束，不要继续粘贴新命令。只复制下面代码框里的内容，不复制`PS ...>`或`>>`。

**演示结算任务，只需复制这一整行并回车。** 在下载后的仓库根目录运行，不需要设置$p或粘贴if代码。

```powershell
.\启动CLI.cmd -Case checkout
```

启动器会创建一份没修过的新副本、显示目录和任务，自动读取本机已有密钥，再进入真实模型任务。密钥不会显示；请求会产生所选模型服务的费用。之前修好的目录会保留。

它会先请求运行现有测试。核对项目目录后，选“确认运行”再回车，或输入完整yes再回车。初始3个测试失败是练习故意保留的Bug。

接下来它会自己搜索和读取文件。看到编辑差异时检查内容，再逐次确认；最后确认复测。正常结果是修改shop/cart.py和shop/checkout.py，7项测试通过。步骤顺序和耗时可能变化；16次请求是这一轮的上限，不是费用金额上限。模型失败要如实展示，不要现场手改后说是Agent修好的。

**任务结束后，独立检查实际结果。** 启动器会打印“要独立检查，请复制下一整行”，后面是包含本次实际目录的完整命令。需要检查时复制那一行并回车；它运行演示代码，不调用模型。不会在你拒绝操作后偷偷自动执行。

看到passed、tests_passed、independent_behavior_passed、original_tests_unchanged都为true才算这次检查通过。也可以直接打开屏幕显示的演示目录查看文件。

想演示JSON新功能，把同一命令末尾的checkout换成wordcount即可。换电脑时先按[安装指南](CLI_GUIDE.md)准备环境，并把命令中的安装位置改为新电脑实际路径。

## 平时处理自己的项目，怎样启动

在Herta仓库目录打开PowerShell，把目标目录传给启动器：

```powershell
.\启动CLI.cmd -Repo '你的项目目录'
```

这里填写要分析和修改的项目目录。看到Herta输入提示后，直接用中文交代任务；输入/exit退出。这是持续聊天方式，和上面“一次性演示任务”分开。

也可以双击当前工作区的启动CLI.cmd，再按提示输入项目目录。启动Herta.cmd仍然是旧桌面入口。

脚本化使用prepare.py | ConvertFrom-Json的方式仍保留；2026-10-25已修复Windows PowerShell 5.1的中文JSON乱码。普通使用无需手动处理JSON、环境变量或多行代码。

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

当前CLI入口在[GitHub主干](https://github.com/theHerta27/herta-agent)。`learning/unit-01-cli-read`保留开发历史；较早记录中的提交号用于定位当时的代码。
