# 单元07：经确认创建新文件，再回读核对

## 背景问题

edit_file只能修改已有文件，因此Agent还不能完成“新增一个函数文件或测试文件”。本单元补一个create_file工具，沿原审批和Loop完成确认、真实创建、收据、Read核对。只创建单个文件，不自动建目录、不覆盖已有目标；不执行新文件代码。用户明确要求继续，完成后停在07。

## 核心原理

像先填好一份表，再把它放进空的文件格：确认时先看完整内容；提交时还要检查文件格是否已被别人占用。先检查一次并不能保证之后没人创建同名文件，因此发布操作自身也必须拒绝覆盖。

这里直接用Python标准库：先在目标目录写好临时文件，关闭写入流；再用os.link为同一份完整内容建立目标文件名，最后去掉临时名字。临时名和目标名短暂指向同一份数据，去掉临时名后目标文件仍在，这叫硬链接。正常结束后只有目标文件名。已有文件不会被替换；不支持该发布操作的文件系统会报错。它不提供操作系统沙箱，也不承诺断电持久性或防恶意并发换目录。

## 真实源码和调用链

| 文件 / 函数 | 实际职责 |
|---|---|
| [cli.py](../../backend/herta_agent/cli.py) `create_agent` | 在唯一Registry注册create_file，说明何时使用及创建后回读；未另建Agent循环 |
| [paths.py](../../backend/herta_agent/tools/coding/paths.py) `Repository.path` | 只新增默认False的allow_missing；Read/Search/Edit仍保持原来的“路径必须存在”规则 |
| [create_file.py](../../backend/herta_agent/tools/coding/create_file.py) `CreateParameters/create_path` | 校验path/content；仅项目相对路径、已有父目录、无链接，不接收覆盖或自动建目录开关 |
| 同上 `prepare_create` | 编码/校验UTF-8，生成完整新建差异；原始差异超过16000字节拒绝，不截断让用户盲批 |
| [permissions.py](../../backend/herta_agent/tools/permissions.py) `TerminalApproval/confirm_once` | 复用原逐次确认，只补create_file分支；先预览，只有yes批准 |
| create_file.py的 `commit_create/create_file` | handler再次准备并检查取消，进入有界同步提交；复查目标，暂存、拒绝覆盖式发布、清理并生成SHA256收据 |
| [演示](../../examples/cli-create/demo.py) `CreateReadFixture.complete` | 固定Provider提出创建answer.py，再要求原read_file回读；不是模型自主选择工具 |

PreparedCreate意为“准备好的新建方案”：path是目标路径，data是准备写入的UTF-8字节，diff是供用户审核的文字。方案准备不写文件；commit_create才进行提交。收据里的after_sha256是实际提交内容的指纹，用于与Read读到的字节比较。

真实输入为`创建answer.py并回读核对。`，文件内容是`answer = 42\n`：

`create_agent → chat/run_turn → Agent.run → Provider提出create_file → 原Executor参数校验/权限 → TerminalApproval.prepare_create/confirm_once → create_file.handler → prepare_create → commit_create → 原TurnIO/Session回填收据 → Provider提出Read → 回读 → 最终回答`。

演示命令：

```powershell
Set-Location -LiteralPath 'D:\Desktop\herta-agent\.local\worktrees\unit-01-cli-read'
$env:PYTHONPATH = (Join-Path (Get-Location) 'backend')
& 'D:\Desktop\herta-agent\.venv\Scripts\python.exe' -B -X utf8 examples/cli-create/demo.py
```

预览中`--- /dev/null`表示旧文件不存在，是差异格式的记法，不是在Windows读写一个/dev/null目录；`+++ b/answer.py`表示新文件，`+answer = 42`是准备新增的一行。此时目标尚未创建。

输入yes并回车：实际创建，收据created=true；Read返回第1行answer = 42，sha256与收据after_sha256一致，steps=3。输入no：permission_denied，steps=2，最后实际文件不存在。两种情况均由本机实际运行观察。Step仍是Provider请求次数：成功是创建→读取→回答；拒绝是创建请求被拒绝→回答。演示结束会清理临时项目，当前源码目录不会留下answer.py，也没有运行其中代码或调用模型。

## 关键设计取舍

- **复用边界**：原Repository、decode_utf8、Executor、TerminalApproval/confirm_once、terminal_text、Loop/Session、Read与指纹继续使用。只补新工具，不新建文件服务、审批或Runtime。原Edit使用os.replace替换已有文件，不能拿来直接发布新文件，因为新建必须拒绝覆盖。
- **成熟原语**：使用[Python os.link](https://docs.python.org/3.12/library/os.html#os.link)与tempfile，不增加依赖，也不移植整个旧工作台。实际Windows链接接口及文件系统限制见[Microsoft CreateHardLinkW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createhardlinkw)。本机普通文件系统真实碰撞测试已运行；其他文件系统不能据此宣称支持，失败时无覆盖式降级。
- **确认与冲突**：批准的是本次参数副本；handler不接受外部修改后的内容，重新准备后才提交。确认期间或最终发布瞬间出现同名目标均拒绝，保留别人的文件。路径检查不是恶意并发文件系统隔离。
- **显示与内容**：可创建空文件，UTF-8字节与换行按原内容保存。预览转义控制字符，完整保留可审核内容；不成对的Unicode代理字符在Pydantic JSON参数校验时就被拒绝，不会到达写入。NUL由复用的文本校验拒绝。
- **取消与异常**：准备在线程中只计算，不写文件；取消前置阶段不会发生迟到创建。同步提交开始后不承诺取消回滚。暂存清理失败会明确返回create_cleanup_failed，提示目标可能已创建，要求回读核查；不会谎称毫无副作用。

## 测试验证

相关基线63项通过；新增12项先失败后通过；最终相关75项通过。完整后端429项中426通过、3项旧语音检查跳过（129.131秒）；规则和本轮8个Python文件格式检查通过。独立静态审查未发现P0–P2实质问题；Windows本机发布行为由真实碰撞测试验证，其他文件系统和恶意并发场景未验收。

新增检查覆盖默认拒绝、真实预览先于yes/no、空文件/中文/CRLF与指纹、已有文件/目录、确认期间碰撞、发布瞬间碰撞、不支持链接时不降级写入、清理失败的诚实错误、路径/预览/类型/文本边界、普通/悬空/循环链接、取消准备无迟到创建，以及原Loop创建后回读。批准回调只用于本次新建测试夹具，不是产品自动放行。

实际命令、失败修正、版本/来源和Diff见[执行记录](verification/unit-07/verification.md)、[本单元差异](verification/unit-07/key-diff.patch)。Read/Search的模拟HTTP测试同时确认模型接口看到新工具Schema，未发送真实模型请求。仅本次新建临时资料，无私人文件、已有数据库、音频、前端或GPU语音验收。04～07改动仍在本地，未提交或推送。

## 动手练习

可选5～10分钟：先输入no运行一次，再输入yes运行一次。指出哪一行是“尚未写入的计划”，哪一行是“实际写入的收据”；对比after_sha256与Read的sha256，解释为什么预览本身不能证明文件已创建。无需改源码，演示自动清理。本单元结束等待下一次明确指派，不进入08。
