# 单元06执行记录

日期：2026-10-21。目录`D:/Desktop/herta-agent/.local/worktrees/unit-01-cli-read`，分支`learning/unit-01-cli-read`。HEAD仍为e765b48059379ae79e0b62744d98dd6b3563688a，01～03已备份至私密仓库，04～06未提交/推送。本轮不合并、不发布。

## 范围和基线

用户明确继续下一单元。使用guided-development先核对真实代码和前轮记录；阅读Session、MemoryTurn、SQLite与服务PersistentTurn后，确认CLI持久化需要处理服务管理、并发和中断恢复，因此未顺手添加新存储。单元06限定为--trace终端进度，直接复用原RuntimeEvent/EventSink。先向用户说明真实调用链和权限/上下文结果含义，再实现。

真实基线是05结束的未提交工作区，保存在.local/unit-06/before；before-files.json记实际文件哈希。key-diff.patch只比较本轮7个源码/说明文件，不拿HEAD将04/05工作混进来，也不将证据归档递归加入Diff。没有清理用户资料或原数据库。

## 实际测试命令

主仓既有Python为3.12.13；所有命令使用`D:/Desktop/herta-agent/.venv/Scripts/python.exe`，不安装依赖。完整回归的实际命令：

```powershell
Set-Location -LiteralPath 'D:\Desktop\herta-agent\.local\worktrees\unit-01-cli-read'
$env:PYTHONPATH = (Join-Path (Get-Location) 'backend')
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
foreach ($taskEnvName in @([Environment]::GetEnvironmentVariables().Keys)) {
    if ($taskEnvName -like 'HERTA_*' -or $taskEnvName -eq 'DEEPSEEK_API_KEY') {
        [Environment]::SetEnvironmentVariable($taskEnvName, $null, 'Process')
    }
}
$env:HERTA_LIBREOFFICE = 'D:\Desktop\herta-agent\.local\libreoffice\unpacked\program\soffice.com'
& 'D:\Desktop\herta-agent\.venv\Scripts\python.exe' -B -X utf8 -m unittest discover -s backend/tests -v
```

旧Windows目录句柄测试沿用经工具自动审查批准的本机环境执行；不因此调用模型或读取私人资料。最终日志`backend-final.log`：417项、136.213秒、`OK (skipped=3)`，退出0，即414通过。3项跳过仍来自旧语音专用解释器、本机GPU语音验收未开启及本机TTS/ASR环境不可用；无新增语音工作或通过声明。

局部检查在PYTHONPATH同时加入backend与backend/tests，使用同一绝对Python路径：

```powershell
python -B -X utf8 -m unittest test_cli test_cli_read test_project_context test_runtime_events -v
python -B -X utf8 -m unittest test_cli_trace -v
python -B -X utf8 -m unittest test_cli_trace test_cli test_cli_read test_project_context test_runtime_events -v
python -B -X utf8 -m ruff check backend evals/harness
python -B -X utf8 -m ruff format --check backend/herta_agent/cli.py backend/herta_agent/cli_events.py backend/tests/test_cli_trace.py
```

第一项是变更前基线30项，13.867秒；新增8项初次接入后通过，2.149秒；格式化后的相关38项通过，16.033秒。规则检查及3文件格式检查通过。全库格式未重跑，保留此前旧桌面基线格式问题。

## 演示与真实记录

```powershell
python -B -X utf8 -m herta_agent --repo examples/cli-read --demo-read-file notes/demo.md --message '请读取演示笔记' --trace
```

实际分别重定向stdout/stderr保存为demo-stdout.log、demo-stderr.log，退出0。只读取仓库已有公开演示笔记，使用原ReadDemoProvider固定脚本、原CLI/Loop/Executor；没有新增演示Provider或真实模型调用。stderr实际6条进度：步骤1上下文1948/30464、请求Provider、read_file开始/完成，步骤2上下文2393/30464、请求Provider；stdout返回笔记真实行号/正文，steps=2、context指纹20435f44342acab462148f0abdf5873c17816764b0baeffb8e360ce23b8a14c6。Token数字只是本机估算。

| 日志 | 实际结果 |
|---|---|
| baseline.log | 30项通过，13.867秒 |
| red-trace.log | 8项中2失败6错误：CLI不认识--trace，终端sink模块不存在 |
| green-trace-initial.log | 8项通过，2.149秒 |
| focused-final.log | 最后相关38项通过，16.033秒 |
| backend-final.log | 417项中414通过，3项旧语音跳过，136.213秒 |
| ruff-initial.log | 6处E501长行提示；格式化修正 |
| ruff-final.log / format-final.log | 规则和3文件格式检查通过 |
| demo-stdout.log / demo-stderr.log | 原Read演示实际结果和6条进度，分流保存 |

曾按推测读取test_storage.py但文件不存在，随后通过rg定位实际文件并直接核对SQLite实现；没有将推测当成真实模块。本轮完整回归含旧异步调试慢回调提示，按原日志保留，不把提示计作失败或声称零诊断输出。

## 复用与审查

新增cli_events.py的TerminalEventSink/label；CLI新增--trace并将observer从单条/交互两条入口传给原Agent.run。原RuntimeEvent/EventSink/NullSink、Agent事件顺序、Executor权限/参数校验与on_started、ContextPackage.diagnostic、Session/MemoryTurn保持不变。直接复用permissions.terminal_text，没有第二套权限或历史，也没有复制上游源码、新工具、新依赖。具体版本、复用路径/符号/哈希在source-evidence.json。

独立代理读取精确单元06 Diff及必要既有事件契约，没有修改、联网、运行测试或读取用户资料；未发现P0–P2实质问题。它核对单条/交互/真实Provider分支observer传递、有限字段、安全显示、业务测试status分离、关闭进度流不传播到工具。真实Provider分支只静态核对，本轮仍未进行真实模型验收。

## 验证边界与结束状态

新增测试使用真实临时文件、原CLI/Loop/Session/Executor，验证默认关闭、单条/交互进度、观察者不改变回答/历史，拒绝与无效参数不虚构started，真实工具错误码单行转义并有界，坏输出流不取消工具，Windows真实unittest断言失败显示调用完成但status=failed，以及取消时不显示完成。测试中的批准回调只用于本次新建unittest夹具，产品默认权限未变。

轨迹只显示有限元数据，不额外打印系统文本、用户输入、参数、模型文本或结果正文。原工具和最终回答的输出保持，不承诺全进程日志脱敏。stdout/stderr显示颜色和外部合并时序未做GUI终端认证；关闭或损坏流时禁用进度，原任务继续。没有事件落盘系统、CLI持久化、Hooks、子Agent或其他扩展。

最终静态校验见final-static-check.log。只用临时资料/原公开演示笔记，无真实模型、已有私人数据库、前端或GPU语音验收。完整回归与本轮交付结束后停止，未进入07，未提交推送。
