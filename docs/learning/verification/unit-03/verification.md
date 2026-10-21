> 仓库备份副本：保留该单元结束时的真实结果和当时状态；后续提交不改写历史结论。本目录附最终回归及关键失败摘录，其余原始日志/完整before快照仍在开发机.local/unit-03中。文中的“未提交/未推送”和HEAD指当时，不代表之后的上传状态。

# 单元03执行记录

日期：2026-10-21。目录：`D:/Desktop/herta-agent/.local/worktrees/unit-01-cli-read`。
分支：`learning/unit-01-cli-read`；HEAD仍为`9ab9796d819216a64c783eeba75f7ac804441a23`。
用户明确要求开发单元03，单元内自主完成测试/修复，结束暂停。本轮没有提交、合并或推送。

## 变更范围与来源

- 新增`tools/coding/edit_file.py`和`tools/permissions.py`；复用既有路径、读取、Executor与Loop。Read新增原始字节指纹，CLI组装确认器；`runtime/agent.py`只向原Executor转发新增构造参数，循环主体未改。
- 参数级`authorize`与旧`tool_policy`互斥，旧服务继续沿原策略；未建立第二套Agent Loop、存储、文件服务或审批服务。每次确认只适用于当前调用，无会话自动放行。
- 已读旧分支固定`e121d8207f74af98e22f2c100348b05160a0560b`的`apply_patch.py`，未移植其多文件补丁解析器；当前输入是唯一文本替换，直接使用Python字符串及标准库`difflib/hashlib/tempfile/os.replace`。未运行git apply，没有增加依赖。
- 架构参考是2026-10-19审计保留的官方tools-reference与permissions快照，本轮在本地读取；不冒充今天重新检索的最新行为。`source-evidence.json`保存文档、旧文件SHA256、依赖实际版本和当前符号行号。未复制非官方Claude Code还原源码。
- `before/`保留本轮开始时382份Git跟踪或非忽略的工程文件，不包含忽略目录中的用户数据。`key-diff.patch`与单元02结束快照比较；`changed-files.json`是本单元16个变更文件及哈希。直接对Git HEAD做Diff会混入前两单元的未提交改动。

## 实际测试命令与环境

沿用现有Python环境，通过PYTHONPATH确保导入隔离目录。完整最终回归使用下列命令，输出保存到`backend-final.log`：

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

工具自动审查批准后，在沙箱外运行本机Windows原生句柄测试；不扩大模型或私人资料授权。最终退出码0：`Ran 385 tests in 109.956s; OK (skipped=3)`，即382通过、3跳过。跳过原因沿用可选语音环境：`optional local voice runtime`、`opt-in GPU model`、`local voice models are optional`。只有其中一项明确是GPU模型验收。

局部基线、局部回归的PYTHONPATH还包含`backend/tests`，其实际模块命令分别为：

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'backend') + ';' + (Join-Path (Get-Location) 'backend/tests')
# 基线51项：同组沙箱内5项失败，本机复核51项通过
python -m unittest test_cli test_cli_read test_cli_search test_tools test_tool_permissions test_companion test_note_agent -v
# CLI/工具相关51项：修正Read新增字段的旧预期后通过
python -m unittest test_cli_edit test_cli_read test_cli_search test_tool_permissions test_tools test_cli -v
# 最后两处修正后，编辑/权限局部21项通过
python -m unittest test_cli_edit test_tool_permissions -v
```

上述`python`均通过实际路径`D:\Desktop\herta-agent\.venv\Scripts\python.exe -B -X utf8`执行；简写不表示调用过另一个系统Python。HTTP协议测试走MockTransport和专用fixture-key，未请求任何模型服务。

规则检查实际命令：`python -m ruff check backend evals/harness examples/cli-read examples/cli-search examples/cli-edit`，通过。格式检查用`ruff format --check`指定本轮12个Python文件，结果`12 files already formatted`；具体文件见来源清单。未重跑全库格式检查，前两单元已记录的原有`test_desktop_start_guard.py`换行问题保留，没有修改该文件。

## 原失败与日志

| 日志 | 实际结果与处理 |
|---|---|
| baseline.log | 沙箱内51项中3失败、2错误，均为旧note_agent用例的目录访问；旧源码未改 |
| baseline-native.log | 同组同源码在本机51项通过，16.882秒，确认是Windows原生目录句柄限制 |
| red-cli-edit.log | 新4项测试共6处失败（含子用例）；Read无指纹，Edit未注册，确认后文件不变；无测试错误 |
| green-cli-edit.log | 首次接入后4项通过 |
| red-approval-sigint.log | 首次子进程日志按GBK输出而父进程按UTF-8读取，造成解码和测试错误；给子进程显式加-X utf8，未改系统编码 |
| red-approval-sigint-behavior.log | 修正夹具编码后真实失败：第一次SIGINT只取消异步任务，模拟输入仍等到INPUT_STALLED |
| green-approval-sigint.log | 确认期间临时使用默认SIGINT处理后5项通过；退出确认时恢复原处理 |
| focused.log | 51项中1失败，旧Read整体字典预期缺新增sha256；补独立实际字节指纹预期，保留原行号/正文断言 |
| focused-fixed.log | 修正旧Read契约预期后，CLI/Read/Search/Executor等51项通过，10.149秒 |
| red-newline-readonly.log | 2项先失败：CRLF被展示层归一化而不可见；只读文件写失败后只读临时文件清理异常。改为显示CR转义、只读目标提前拒绝 |
| green-newline-readonly.log | 修正后编辑与权限21项通过，1.029秒 |
| backend-full.log | 最终两项边界修正之前启动的中间版本383项，3跳过，123.593秒；不是最终版本验收 |
| backend-final.log | 修正后的最终385项：382通过、3跳过，109.956秒 |
| ruff-initial.log | 初次23项问题，4项导入由规则工具修正，其余为长行；格式化后解决 |
| ruff-check.log | 初次完整规则剩1项ASYNC250；确认输入有意在主线程等待，加入理由明确的局部豁免，避免不可取消的输入工作线程 |
| ruff-check-final.log / format-check-final.log | 最后完整规则与局部格式检查通过 |
| demo-approved-final.log | 管道传入yes：实际收据、回读value=2、相同after指纹、steps=4 |
| demo-denied-final.log | 管道传入no：permission_denied、value=1、steps=3 |

沙箱基线失败的具体名称为`test_chat_result_route_rejects_unshared_read_while_local_preview_remains`、`test_existing_loop_proposes_note_without_vault_then_same_executor_publishes`、`test_note_tool_and_status_recheck_shared_scope_and_confirmation_rejects_revoke`、`test_old_completed_plan_status_is_not_lost_after_twenty_later_jobs`、`test_result_read_returns_actual_file_hash_for_verification`。全部保留原日志，没有通过更改旧工作台逻辑解决。

两条演示都实际执行`examples/cli-edit/demo.py`，使用相同create_agent/chat/TerminalApproval及新建临时文件，结束清理。SIGINT测试在独立子进程中模拟等待输入并发送一次真实Python SIGINT，未将其称为手工Windows键盘验收。

## 审查、边界与停止点

按requesting-code-review执行一次独立静态审查，未发现P0–P2实质问题。核查了审批参数深拷贝、字面True、单次批准、指纹绑定、提交检查、旧策略兼容与测试真实字节；审查代理未修改文件、运行测试或联网。

当前证据覆盖成功、拒绝、EOF、Ctrl+C、内容变化、唯一匹配、路径与链接、只读文件、失败清理、准备期间取消，以及同一Loop的真实回读。SHA不是“当前会话读过此文件”的安全凭证，仅用于版本冲突检测；没有实现读取历史授权库。确认在顺序CLI主线程等待，handler超时不包含人工思考时间；有界同步写入仍不提供OS级隔离或硬I/O超时，也不承诺阻止恶意外部进程的并发路径替换。

本轮没有真实模型、GPU语音、前端、Electron或私人数据库验收，没有安装依赖或写入外部服务。单元03完成后暂停，未进入单元04。
