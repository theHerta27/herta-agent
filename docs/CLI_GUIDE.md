# 安装与演示

## 你现在这台电脑，先这样用

软件已经装好了，先不用看后面的安装命令。

新版现在有终端界面。如果你还停在旧的`You:`提示处，先输入`/exit`并回车，等出现`PS ...>`后重新运行：

```powershell
& 'D:\Desktop\herta-agent\.local\worktrees\unit-01-cli-read\启动CLI.cmd'
```

**第一步：告诉Herta要处理哪个文件夹。**

看到“请输入要处理的项目文件夹路径，然后按回车”时，粘贴下面这一行并回车，不要加引号。这是新准备的一份练习，与你刚才修好的那份分开：

```text
D:\Desktop\herta-agent\.local\worktrees\unit-01-cli-read\.local\coding-demo\average-co6whj8z
```

**第二步：像聊天一样交代任务。**

接下来会出现写着“Herta Agent”的启动画面。在`›`后面输入下面这句话，再按回车：

```text
请检查这个项目里的average函数，修复传入空列表时的报错。空列表应该返回0，其他情况保持不变。先读代码和测试，再修改，最后运行测试。不要删除或修改现有测试。
```

这个练习项目只有一个求平均值的小函数和3个测试。我特意保留了一个Bug，方便你亲眼看Herta怎么找到问题、修改文件并检查结果。它不是你的私人项目。

**第三步：看到修改内容时，再决定是否同意。**

Herta会显示准备改动的内容。绿色`+`是准备新增的行，红色`-`是准备删除的行，此时还没写入。菜单默认选中“取消”。看过差异后，可以按左右键选“确认修改”再按回车；也可以直接输入`yes`再回车。直接回车或输入`no`都不会批准修改。

询问是否运行测试时，会显示项目、测试目录和执行方式。按`D`可查看完整命令，看完仍需要单独确认。决定运行时选“确认运行”并回车，或输入`yes`再回车。每次同意只对眼前这一次操作生效。

**第四步：看结果。**

正常情况下，它会说明为什么空列表会报错、实际改了哪里，并报告3个测试通过。你也可以打开练习目录中的`metrics.py`查看实际修改。工具步骤可能每次不同。

完成后仍可在`›`后继续提问，例如“解释一下刚才为什么这样改”。退出时输入`/exit`并回车。上下键可以找本次进程之前输入的任务；可以直接粘贴多行文字，手动换行则先按Esc再按Enter，最后单独按Enter发送。

这份练习修好后，再次运行就不会有同一个Bug；想重新看修复过程，需要再准备一份新练习。后面的安装和配置说明主要用于换电脑或自己开发时查阅，现在可以先不看。

---

本版交付是Windows、Python 3.12+的CLI Coding Agent。使用`learning/unit-01-cli-read`工作区；`启动Herta.cmd`仍然是旧桌面入口。直接依赖为httpx、pydantic、Rich和prompt_toolkit；不需Electron、模型权重或Node.js。

## 从源码安装

在本分支仓库根目录的PowerShell中：

```powershell
py -3.12 -m venv .venv-cli
.\.venv-cli\Scripts\python.exe -m pip install ./backend
.\.venv-cli\Scripts\herta-agent.exe --help
```

如果使用uv，也可运行`uv venv --python 3.12 .venv-cli`和`uv pip install --python .venv-cli/Scripts/python.exe ./backend`。修改代码后需重新安装；开发时可用`pip install -e ./backend`。不需要激活环境，完整路径可避免误用旧桌面环境。

本机已在工作区`.venv-cli`安装验证过wheel。新机器请使用上述命令创建自己的环境，不直接拷贝虚拟环境。

## 配置模型

默认API根地址`https://api.deepseek.com`，模型`deepseek-flash`。程序使用兼容OpenAI Chat Completions的`tool_calls`协议；自定义服务必须支持工具调用。真实模式需显式指定`--provider openai`；默认demo固定回显，不调用模型。

已有Windows用户级`DEEPSEEK_API_KEY`时，在新终端通常自动继承。若终端是在设置密钥之前打开的，只在当前进程补读：

```powershell
$env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY', 'User')
```

也可通过环境变量`HERTA_BASE_URL`、`HERTA_MODEL`、`HERTA_API_KEY`切换服务。DeepSeek域名优先使用`DEEPSEEK_API_KEY`；其他域名只使用`HERTA_API_KEY`，不会转发DeepSeek专用密钥。密钥不写入会话库、不输出。CLI不会自动读取`.env`。发送真实任务会将当前任务、选中项目资料和必要会话发给模型服务。

## 一个完整的真实任务

先创建只含演示代码的新目录，每次执行都会创建新副本，避免复用已经修好的文件：

```powershell
.\.venv-cli\Scripts\python.exe examples/coding-task/prepare.py
```

输出JSON中的`project`是本次项目目录。复制该目录填入`$project`，然后启动：

```powershell
$project = '这里填写刚输出的project目录'
.\.venv-cli\Scripts\herta-agent.exe --provider openai --repo $project --instructions AGENTS.md --max-steps 8 --context-window 16384
```

输入：

> 修复average在空列表上的异常：空列表应返回0，保留非空列表行为。先搜索并读取代码和测试，修复后运行unittest并解释结果。不要删除或弱化测试。

你能在终端看到模型等待提示和工具活动。看到编辑差异时先阅读，选中“确认修改”后回车，或输入完整`yes`再回车才写入。测试也单独展示范围并确认，按`D`可看完整命令。合理结果是在`metrics.py`增加空输入判断，保留3个测试并报告`passed`。模型可能选择不同步骤，不能要求每次恰好6步。8步是每轮模型请求上限，不是费用金额上限；达到上限会明确报错。

任务结束后，在另一个终端独立核查：

```powershell
.\.venv-cli\Scripts\python.exe examples/coding-task/check.py $project
```

最后JSON应包含`"passed": true`。核查器只检查已有文件和行为，不调用模型、也不会代替Agent修复。

正常使用默认显示简短中文进度、排版后的回答和确认菜单。遇到问题要看步骤编号、上下文用量和会话位置时，加`--trace`；想用原来的普通文字显示时，加`--plain`。把输出写进文件、通过管道运行，或终端声明`TERM=dumb/unknown`时，也会自动使用普通文本，仍需完整`yes`确认。启动器对应支持`-Trace`和`-Plain`。回答目前仍是一次显示完整内容；等待动画表示正在请求模型，不是流式输出。

本机也可双击当前工作区的`启动CLI.cmd`，输入项目目录后进入真实交互；它会补读用户级密钥。该便利入口不自动加载项目约定，需加载时使用上面的完整命令。

## 多轮、保存与恢复

- 不加`--message`时持续对话；`/exit`或输入EOF退出。`--message '任务'`执行一轮后退出。
- 真实模式默认自动保存；正常界面隐藏长编号和数据库路径，加`--trace`可查看。默认在`%LOCALAPPDATA%\HertaAgent\cli\项目路径哈希\sessions.sqlite3`。`--data-dir`可改父目录，仍按项目分库，CLI不读取旧桌面数据库。
- `--list-sessions --repo $project`只列本机会话，无须API Key、不发模型请求，最多100个。
- `--provider openai --repo $project --resume 会话ID --trace`恢复同一项目会话，再次输入任务才请求模型。退出后保存的是消息和真实工具结果，审批不会继承。
- `--no-save`只保留进程内历史，不能与保存/恢复参数同用。默认demo不落库；若要本地体验保存，可显式指定`--data-dir .local/demo-state`。
- 每个项目数据库同一时间只允许一个CLI持有；进程崩溃后，下次打开会把未完成轮次标为`interrupted`、补齐未知工具结果，不自动重试。其他数据目录是独立库，不提供跨库或外部编辑器互斥。

会话库以明文保存任务、读到的代码、工具结果和回答，请按项目资料管理；恢复并发送下一轮时，必要历史也会发送给所选模型。

## 边界与故障

`grep_code`按字面、区分大小写搜索；`read_file`读取有界UTF-8文本；`edit_file`只替换一处唯一文字，并要求最近Read的SHA256；`create_file`只在已有目录创建新文本，不覆盖、不删除；`run_tests`仅支持Windows、本环境的Python unittest，不提供通用Shell、pytest、自动安装依赖。目标项目需要自己的依赖时，应先由用户准备适用环境。

编辑、新建、测试每次都确认；输入`no`、回车或EOF拒绝该调用。确认时Ctrl+C也是拒绝；等待模型/运行工具时Ctrl+C取消本轮并收尾自有进程树，交互模式可继续。若写入或提交已经成功，取消不会回滚文件；“工具结果未知”时先检查文件，不要盲目重试。单轮取消退出码130；普通失败1；参数错误2。

文件冲突会拒绝覆盖。工具出错会返回结构化结果给模型；服务失败、模型超时或预算耗尽会结束本轮，不自动重试付费请求。测试`ok=true`表示工具完成，只有`status=passed`和实际断言才支持任务完成；无测试、跳过、输出过大不算通过。

目录校验和审批约束内置工具，不是操作系统沙箱。测试会执行项目Python代码，拥有当前账号权限；仅对可信项目批准。上下文Token是估算，旧历史按完整轮次选取、必要时程序摘录；不等于精确计费、模型语义摘要或服务端输出上限。

已知小限制：在Herta仓库本身搜索时，`.venv-cli`安装副本未纳入工具排除名单，可能额外命中已安装源码。可把搜索范围设为`backend`；普通目标演示项目不含这个环境目录。本轮保留该项，不为此增加新的搜索系统。
