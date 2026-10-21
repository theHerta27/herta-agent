# 单元04执行记录

日期：2026-10-21。目录`D:/Desktop/herta-agent/.local/worktrees/unit-01-cli-read`，分支`learning/unit-01-cli-read`。

## 上传检查点

用户先要求上传当时版本，再继续下一单元。GitHub API实际返回`theHerta27/herta-agent`为PRIVATE；单元01～03提交`e765b48059379ae79e0b62744d98dd6b3563688a`已推送，API再次查询的远端SHA完全相同。本单元以它为基线，本地完成，未自动追加提交或推送。

上传前53项相关回归通过（12.825秒，开发机`.local/upload-units-01-03.log`）。GitHub访问先遭遇沙箱网络限制，后遇到管理员与沙箱账户的Git所有权差异及SChannel握手失败；单次`-c safe.directory=精确工作区 -c http.sslBackend=openssl`成功，无全局配置更改、无证书验证关闭。没有上传模型、密钥、用户数据或忽略目录完整快照。归档补丁的空白上下文行和原日志末尾空行导致上传前`git diff --cached --check`提示，它们按原始证据保留，不宣称通过了这项检查；源码检查另行列明。

## 变更与复用

- 原Registry/Executor/Agent Loop/Session/Context继续使用；只新增工具注册，复用原`authorize`和TerminalApproval。没有新Agent Runtime、审批服务、Shell或依赖安装器。
- `run_tests.py`使用当前Python启动绝对路径的stdlib `test_worker.py`。worker从unittest结果对象生成报告，不用终端文本解析成功与失败；failure/error/skipped可包含子测试事件，不能直接相加作方法总数。
- Windows进程生命周期直接复用`documents/process.py::attach_job`与`companion/worker_process.py::resume_process`，没有复制它们或改旧语音/文档实现。它们在执行测试时才导入；Job用memory_limit=0，只取普通进程树收尾职责，未称为文件/网络沙箱。
- 已读旧`coding-agent@e121d8207f74af98e22f2c100348b05160a0560b`的run_tests.py；因绑定Docker/pytest报告，未移植执行链，只沿用工具完成与测试结果区分的经验。标准库提供Popen、threading、tempfile、unittest；无新增依赖。
- `source-evidence.json`保留实际版本、复用函数文件SHA256、旧候选SHA和当前函数行号。`key-diff.patch`只比较e765b48与本单元12个代码/说明文件；验证归档自身不再次递归加入补丁。

## 实际最终命令

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

完整回归使用经工具自动审查批准的本机环境，支持旧工作台的Windows目录句柄测试；没有因此调用模型或打开已有数据库。`backend-final.log`记录`Ran 400 tests in 128.584s; OK (skipped=3)`，退出码0，即397通过、3跳过。原有可选语音跳过原因分别为optional local voice runtime、opt-in GPU model、local voice models are optional。

相关局部68项通过（19.203秒），命令如下；同样使用上述已有Python的完整路径，并将`backend/tests`加进PYTHONPATH：

```powershell
python -m unittest test_cli_run_tests test_cli_edit test_cli_read test_cli_search test_tools test_tool_permissions test_cli -v
python -m ruff check backend evals/harness examples/cli-test
```

最后规则检查通过。`ruff format --check`指定本轮8个Python文件，8 files already formatted。全量通过之后只将测试夹具中的相邻字符串分行消除一处E501，字符串值和控制逻辑未变；之后规则/格式重新检查。全库格式检查未重跑，旧桌面测试的基线格式问题未处理。

## 失败与通过记录

| 日志 | 实际结果 |
|---|---|
| red-run-tests.log | 初次4项测试5处失败（含子用例），工具未注册，unknown_tool |
| first-run-tests.log | 初次接入后4项通过，1.145秒 |
| boundaries.log | 增补边界后8项通过，3.096秒 |
| red-subtest-skips.log | 全部子用例跳过被误判passed；增加成功方法计数后修正 |
| red-late-start.log | 已取消工作线程仍尝试启动进程；启动前及Windows恢复前检查取消后修正 |
| red-stale-bytecode.log | 同尺寸、同mtime的旧pyc被读取，实际断言失败；项目导入改用本次私有空缓存前缀 |
| red-unsupported-platform.log | 明确不支持非Windows的断言先失败；移除未验证的POSIX执行路径后修正 |
| red-setup-verdict.log | 初始化错误/初始化跳过被判no_tests，2项失败；改为失败优先，再跳过，再零测试 |
| core-final.log | 中间15项中1项失败：旧0.7秒截止早于子进程心跳启动；没有当作树清理通过 |
| focused-final.log | 修正夹具启动预算为1.5秒后68项通过；保留心跳、重复取消及小于3秒收尾断言，不靠等五秒自然退出获得假阳性 |
| backend-final.log | 最终400项，397通过、3跳过 |
| demo.log | 真实失败3 != 2 → 原Read/Edit → 实际重测通过，steps=5，均为本次临时文件/进程 |
| ruff-check-passed.log / format-check-passed.log | 最后规则与8文件格式检查通过；之前的导入/长行失败仍在本机日志中 |

一次文档/示例补丁因测试文件格式化后上下文不符而未应用，核对实际文件后重新补齐；没有当成已修改。初始私有pycache前缀在进程启动时也令标准库冷启动变慢，最终在worker预导入stdlib之后再设置项目导入缓存前缀；旧字节码夹具继续覆盖该行为。

演示实际命令是`@('yes','yes','yes') | python -B -X utf8 examples/cli-test/demo.py`。固定Provider提出两次运行测试和一次编辑，均走真实TerminalApproval；未使用自动放行开关。单独测试的允许回调只存在于unittest夹具，不属于产品默认许可。

## 独立审查与能力边界

独立静态审查提出两项重要问题：POSIX脱离进程组后代可能令输出线程无法收尾，以及初始化错误优先级不正确。前者以显式Windows限定解决，不自建通用进程框架；后者加真实失败夹具并修正分类。复核确认两项关闭，未发现其他重要问题。审查代理未执行测试、联网或修改文件。

本轮验证的是Windows标准进程树、可信演示代码、工具接线和已覆盖结果语义，不是恶意代码沙箱或跨平台认证。项目Python代码仍可读写账号有权访问的资料、启动网络请求和其他程序；起始目录检查不限制执行期Python import范围。HERTA_*及DEEPSEEK_API_KEY不继承到测试进程只是减少偶然泄露，不是环境隔离保证。

只运行本次新建测试代码，没有真实模型、私人资料、原数据库、前端、Electron或真实GPU语音验收。单元04本地完成后停止，不进入05；此前要求的私密仓库备份已完成。
