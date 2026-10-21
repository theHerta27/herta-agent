> 仓库备份副本：保留该单元结束时的真实结果和当时状态；后续提交不改写历史结论。本目录附最终回归及关键失败摘录，其余原始日志/完整before快照仍在开发机.local/unit-01中。文中的“未提交/未推送”和HEAD指当时，不代表之后的上传状态。

# 单元01执行记录

工作目录：`D:/Desktop/herta-agent/.local/worktrees/unit-01-cli-read`。
分支：`learning/unit-01-cli-read`，基线`9ab9796d819216a64c783eeba75f7ac804441a23`。
主目录原有未提交改动保留；当前单元未提交或推送。

## 实际测试环境

复用原主目录已有Python虚拟环境，通过PYTHONPATH明确导入隔离目录的backend，避免editable install指向旧目录。每次全量运行移除HERTA_*和DEEPSEEK_API_KEY，再仅为旧文档测试设置本机已有LibreOffice路径；没有打印或使用真实密钥，没有下载依赖。

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

Windows原生文件句柄测试须在本机足够权限的终端运行；沙箱内首次失败不是通过。受控HTTP测试使用MockTransport，API Key是专门的fixture-key，不发送到网络。

针对性回归实际命令（23项通过）：

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'backend') + ';' + (Join-Path (Get-Location) 'backend/tests')
& 'D:\Desktop\herta-agent\.venv\Scripts\python.exe' -B -X utf8 -m unittest test_cli test_cli_read test_persona_integration test_rag_integration -v
```

## 记录索引

| 日志 | 观察到的结果 |
|---|---|
| baseline.log | 业务代码未改时的全量基线347项：10 failures、40 errors、3 skipped，主要为原生目录句柄在沙箱内受限 |
| baseline-native-check.log | 沙箱外两个相同Windows句柄用例通过，未改业务源码 |
| baseline-native-full.log | 350项（含当时新增的3项RED测试）：新CLI参数失败；另有旧LibreOffice缺失与服务就绪文件时序2个错误 |
| red-cli-read.log | 新CLI参数尚不存在，实际失败 |
| red-utf8-prefix.log | 发现无效UTF-8被忽略，实际失败；最终采用大文件先拒绝、其余严格解码策略 |
| red-oversized-contract.log | 旧前缀读取将超大文件报为成功，实际失败 |
| red-real-read-cancel.log | 保留真实handler时取消未抛出CancelledError，实际失败 |
| regression-native-full.log | 356项：3 failures、2 errors均为旧人格/RAG的CLI绑定；旧功能改为显式组件组装测试 |
| focused-regression.log | 修正后23项通过（CLI、Read、人格和RAG集成） |
| final-backend.log | 357项：2 errors、3 skipped；两个旧服务测试均因读取空端口文件失败，原日志保留 |
| final-backend-atomic-ready.log | 修正夹具后完整357项：354通过、3 skipped，耗时108.943秒，退出码0 |
| ruff-check.log | 全库代码规则检查通过 |
| ruff-format.log | 全库格式检查不通过：test_desktop_start_guard.py原有一处换行，未修改该文件 |
| changed-format.log | 本单元11个Python文件格式检查通过 |
| demo-read.log | 实际离线读文件演示，真实三行、steps=2 |
| source-evidence.json | 关键符号行号、旧分支固定commit与移植源文件SHA256 |

初次工具调用试图用内置worktree工具，返回Not a git repository；回退到Git创建已忽略目录下的隔离worktree。一次计划文档补丁因上下文不匹配未应用，随后用真实上下文补齐，没有改到业务文件。首次局部lint报告3处长行，格式化后局部规则/格式检查通过；未掩盖失败。

## 其他实际检查

- `ruff check backend evals/harness`。
- `ruff format --check backend evals/harness`及针对改动Python文件的格式检查。
- `git diff --check`；CLI导入模块检查未加载persona、rag、service、companion或numpy。
- Runtime、Registry/Executor、config、SQLite、service、pyproject.toml、frontend和scripts均无本单元diff。
- 一次独立静态审查发现旧CLI测试、真实同步读取阻塞及前缀分页问题；修正后只读复核确认三项解决，未发现新的重要问题。审查代理没有运行测试或修改文件。
- 最后两个时序错误名称为`test_completed_fact_survives_unread_notification`和`test_slow_socket_consumer_is_cancelled`；在开始业务修改前，`test_parallel_capacity_cancel_and_reuse`也发生同类空文件错误。检查`service_probe.py`发现写入时先创建可见空文件，改为先写`port.tmp`再原子替换`port.txt`，保持原测试断言不变。最终全量通过，不用重跑掩盖这些失败。
- 关键Diff保存在`key-diff.patch`，逐文件清单在`changed-files.json`；路径链接校验通过。全量格式警告属于基线文件，未顺手格式化旧桌面测试。

没有进行真实模型路由、私人文件、GPU语音、前端、Electron或发布验收。源码检查、测试夹具和真实模型能力分别说明，不能相互替代。
