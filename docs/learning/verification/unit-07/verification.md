# 单元07执行记录

日期：2026-10-21。工作目录`D:/Desktop/herta-agent/.local/worktrees/unit-01-cli-read`，分支`learning/unit-01-cli-read`。HEAD仍为e765b48059379ae79e0b62744d98dd6b3563688a（此前01～03私密备份），本轮没有提交、推送、合并或发布。

## 范围与基线

用户明确继续下一单元。使用guided-development先读取真实入口、路径、Edit、审批和现有规划；说明新增单文件创建、确认、回读的真实调用链后实现。复用原Registry/Executor/TerminalApproval/Loop/Session，不增加依赖、存储、工作台或通用命令工具。没有把旧业务候选清单当必须实现项。

04～06尚未提交，因此Diff以实际06结束的工作区快照为准（.local/unit-07/before，元数据before-files.json），不是以HEAD把前几单元算入本轮。key-diff.patch只包括本轮12个源码/说明文件，归档证据不递归放进Diff。

## 实际命令和结果

使用主仓既有Python3.12.13，所有python调用实际为`D:/Desktop/herta-agent/.venv/Scripts/python.exe`；没有安装或升级依赖。完整回归：

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

旧Windows目录句柄测试沿用经工具自动审查批准的本机环境；不因此读取私人资料或调用模型。backend-final.log实际为429项、129.131秒、`OK (skipped=3)`，退出0：426通过。3项跳过仍是旧语音专用解释器、本机GPU语音验收未开启、本机TTS/ASR环境不可用；不能当作语音通过。

局部将backend/tests也加入PYTHONPATH，使用同一绝对Python：

```powershell
python -B -X utf8 -m unittest test_cli_read test_cli_search test_cli_edit test_tool_permissions test_cli_trace test_project_context test_tools -v
python -B -X utf8 -m unittest test_cli_create -v
python -B -X utf8 -m unittest test_cli_create test_cli_read test_cli_search test_cli_edit test_tool_permissions test_cli_trace test_project_context test_tools -v
python -B -X utf8 -m ruff check backend evals/harness examples/cli-create
python -B -X utf8 -m ruff format --check backend/herta_agent/cli.py backend/herta_agent/tools/coding/paths.py backend/herta_agent/tools/permissions.py backend/herta_agent/tools/coding/create_file.py backend/tests/test_cli_create.py backend/tests/test_cli_read.py backend/tests/test_cli_search.py examples/cli-create/demo.py
```

变更前相关基线63项通过，12.429秒；新增12项修正预期后通过，0.373秒；最后相关75项通过，11.771秒。最后规则通过，8文件格式通过。全库格式未重跑，原旧桌面基线问题未改。

## 原始失败与修正

| 日志 | 实际结果 |
|---|---|
| baseline.log | 63项通过，12.429秒 |
| red-create.log | 初始12项：23失败、4错误（含子用例），工具未注册或新模块不存在 |
| green-create-initial.log | 接入后12项中1失败；不成对代理字符预期为handler的not_text，实际先被Pydantic拒绝为invalid_arguments |
| unicode-validation.log | 实际核对：NUL参数可解析，随后文本校验拒绝；不成对代理字符在JSON参数校验报json_invalid。修正测试预期，没有放宽业务校验 |
| green-create-corrected.log | 12项通过，0.373秒 |
| focused-final.log | 中间相关75项通过，12.352秒；当时仍有测试闭包规则提示 |
| focused-passed.log | 闭包绑定后最终75项通过，11.771秒 |
| backend-final.log | 最终429项，426通过、3旧语音跳过，129.131秒 |
| ruff-initial.log | 14处规则问题，包含长行及闭包变量绑定提示；格式化后保留4处B023 |
| ruff-final.log | 中间4处B023：循环中确认回调未显式绑定target/stream/answer；实际同步调用没有越轮使用，仍改为默认参数捕获 |
| ruff-passed.log / format-passed.log | 最后规则及8文件格式检查通过 |
| demo-yes.log / demo-no.log | 本机实际创建/拒绝演示，均退出0，steps分别3/2 |

Unicode诊断首次因未在新命令进程设置PYTHONPATH而找不到教学工具包，补设backend后重跑；没有把首次诊断写成通过。中间测试/规则失败都保留，不覆盖成成功记录。完整回归在最后源代码修正后运行，之后只补学习和证据文件。

## 演示实际结果

```powershell
'yes' | python -B -X utf8 examples/cli-create/demo.py
'no' | python -B -X utf8 examples/cli-create/demo.py
```

两次各自创建新临时项目，不调用模型、不读取API Key、不执行创建文件中的代码。yes时先预览/dev/null→answer.py与+answer = 42，再创建，收据created=true，after_sha256为0a775022744f64c352863f165f2e125898419999bc57c83204772036d0ef6b2e；Read回读sha256完全一致，steps=3，实际内容answer = 42加换行。no时permission_denied、steps=2、目标不存在。演示打印实际状态后，TemporaryDirectory正常清理本次项目。

## 实现和复用边界

create_file是side_effect，仍由原Executor先校验和确认；TerminalApproval只加新建预览分支，confirm_once/terminal_text逻辑保持原样。Repository.path只新增默认False的allow_missing，只有新建工具使用True，其他读取默认范围及必须存在规则不变。代码与版本/复用符号哈希、官方参考见source-evidence.json，无新依赖或上游源码复制。

选择同目录mkstemp写完、复查、os.link发布、移除暂存名；不能直接复用Edit的os.replace覆盖语义，也不引入另一套工作台写入服务。真实文件系统测试在确认期间、发布瞬间插入竞争目标，确认其字节保留；不支持link则失败且不降级写入。清理失败专门返回create_cleanup_failed并提示目标可能已创建，不虚报无副作用。新工具内容/原始完整差异有界，不截断后审批，空文件单独明确显示。

独立代理只读审查8个Python差异文件及原Repository/Executor/审批/Loop，未运行测试、联网、修改或读取用户数据，未发现P0–P2问题。审查中见到确认回调默认参数捕获修正，并注明无害。它的静态结论不能代替本机真实链接和碰撞检查，运行证据来自上述本机测试。

本轮验证普通本机文件系统与离线Provider链路；没有验证其他文件系统、恶意并发换目录/暂存文件、断电持久性或真实模型选工具。不承诺同步提交开始后取消可回滚。权限不是OS隔离；项目约定文字仍不能越过审批。

## 结束状态

只使用本次临时测试资料/演示项目，无私人文件、已有数据库、音频、前端或GPU语音验收。主目录业务源码未改；仅既有progress记录追加。归档保留关键日志和Diff，完整中间日志/变更前文件仍在开发机.local。最终静态检查见final-static-check.log。单元07结束，未进入08；04～07未提交或推送，本会话最近一次GitHub上传为先前01～03私密检查点，本轮未重新查询远端。
