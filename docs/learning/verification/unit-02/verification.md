> 仓库备份副本：保留该单元结束时的真实结果和当时状态；后续提交不改写历史结论。本目录附最终回归及关键失败摘录，其余原始日志/完整before快照仍在开发机.local/unit-02中。文中的“未提交/未推送”和HEAD指当时，不代表之后的上传状态。

# 单元02执行记录

日期：2026-10-19。工作目录：`D:/Desktop/herta-agent/.local/worktrees/unit-01-cli-read`。
分支仍为`learning/unit-01-cli-read`，基线`phase-6-ui@9ab9796d819216a64c783eeba75f7ac804441a23`。
复用上一单元的未提交隔离目录；没有提交、合并或推送。

## 范围及证据

用户要求回答单元01练习并继续。本单元补零行号校验测试，接入既有可移植的字面Search，完成真实搜索结果驱动Read的本地夹具。没有增加依赖，没有修改Runtime、Registry/Executor、config、SQLite或service业务实现，未修改pyproject.toml、frontend或scripts。

`before/`保存本单元开始时8份已存在文件，`key-diff.patch`与这些快照比较；本单元新文件以空文件为基线。`changed-files.json`保存本单元13个文件和哈希。与Git HEAD直接比较会同时包含尚未提交的单元01代码，不能用于计算本单元工作量。`source-evidence.json`保存固定移植来源和实际符号位置。

## 实际最终命令

复用现有虚拟环境，通过PYTHONPATH确保导入隔离目录而不是旧editable安装位置。完整回归命令如下，输出保存为`backend-final.log`，退出码0：

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

Windows原生句柄用例沿用上一单元已核实的运行要求，在获工具自动审查批准后于沙箱外运行本地回归；没有因此调用真实模型或扩大资料范围。HTTP协议用例使用MockTransport和fixture-key，不发到模型服务。

最终结果：`Ran 367 tests in 109.485s; OK (skipped=3)`，即364通过、3项原有可选语音测试跳过。原因分别为`optional local voice runtime`、`opt-in GPU model`及`local voice models are optional`；其中只有一项明确是GPU模型验收，不能将三项全部称作GPU验收。本单元没有进行语音验收。

局部Read/Search运行使用测试导入目录和下列命令，`focused-final.log`为20项通过、4.608秒：

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'backend') + ';' + (Join-Path (Get-Location) 'backend/tests')
& 'D:\Desktop\herta-agent\.venv\Scripts\python.exe' -B -X utf8 -m unittest test_cli_read test_cli_search -v
```

其他已实际执行的检查与演示：

```powershell
& 'D:\Desktop\herta-agent\.venv\Scripts\python.exe' -B -X utf8 -m ruff check backend evals/harness examples/cli-search
& 'D:\Desktop\herta-agent\.venv\Scripts\python.exe' -B -X utf8 -m ruff format --check backend/herta_agent/cli.py backend/herta_agent/tools/coding backend/tests/test_cli_read.py backend/tests/test_cli_search.py examples/cli-search
git diff --check
& 'D:\Desktop\herta-agent\.venv\Scripts\python.exe' -B -X utf8 examples/cli-search/demo.py
```

规则检查通过，涉及9个Python文件的格式检查通过。全库格式本轮未重跑；上一单元记录的未改动`test_desktop_start_guard.py`格式问题保留。`git diff --check`退出码0，有LF/CRLF提示。`git diff --name-only`核实上述核心与旧服务目录没有改动。新建文件另由局部规则、格式及快照Diff检查覆盖。

## 原失败与复核记录

| 文件 | 实际观察 |
|---|---|
| baseline.log | 改动前CLI、Read、人格、RAG相关23项通过 |
| red-search.log | 首批2项新测试：1失败、1错误。工具未注册；HTTP夹具当时还假设工具成功，因此访问空data出错，不把这次写成全通过 |
| focused.log | 初步Read/Search19项通过 |
| backend.log | 审查修正前366项、3跳过，耗时124.293秒；不是最终版本结果 |
| red-nonregular.log | 普通文件过滤测试先失败：模拟特殊文件也进入搜索 |
| fixture-alias-failure-excerpt.md | 加过滤后局部20项首次仍失败，原因是Windows短路径和规范路径使测试的Path比较不相等；改为使用Repository.root后通过。原局部日志被最终局部运行覆盖，因此仅保存工具输出摘录，不能称为完整原日志 |
| focused-final.log | 修正后的Read/Search20项通过 |
| cancel-mutation.log | 进程内将取消Event替换为无效信号，对应用例预期失败：取消后仍读b.txt；检查脚本确认这一次失败后退出0，表示变异被检出 |
| nonregular-mutation.log | 进程内移除普通文件过滤条件，对应用例预期失败：特殊文件夹具成为命中；检查脚本确认这一次失败后退出0，表示变异被检出 |
| backend-final.log | 最终367项，364通过、3跳过；109.485秒 |
| ruff-check.log / format.log | 最后重新执行检查，均通过 |
| demo.log | 搜索返回shop/billing.py第1行，然后实际读取两行；steps=3；演示Provider为固定脚本 |

独立静态审查发现两项：遍历需显式过滤普通文件，取消测试需等整个工作线程结束才能检查是否多读。均修正后复核，审查未发现新的重要问题；审查代理没有改文件、运行测试或联网。本机Windows通过受控文件类型信息验证特殊文件过滤，没有实际POSIX FIFO测试。变异验证只发生在单独Python进程内，产品源码没有被变异修改。

## 能证明与不能证明的事

已覆盖参数先校验、真实本地UTF-8读取与搜索、路径及排除边界、搜索预算和截断、跳过计数、取消后停止后续读取，以及同一Loop中的搜索结果驱动Read。已经开始的底层I/O不能强杀；目录检查不是操作系统沙箱，不能宣称抵御其他进程恶意并发替换。

没有运行真实模型、真实GPU语音、前端或Electron验收，没有访问已有私人文件或数据库。没有把固定Provider演示当作自然语言理解验收。单元02到此停止，等待用户理解并明确继续。
