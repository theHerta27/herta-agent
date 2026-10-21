# 单元05执行记录

日期：2026-10-21。目录`D:/Desktop/herta-agent/.local/worktrees/unit-01-cli-read`，分支`learning/unit-01-cli-read`。

## 基线与范围

用户要求解释单元04的语音跳过、操作方法与预期，并继续下一单元。先读取旧测试条件和演示源码，向用户提供完整PowerShell命令与三次yes流程；解释写回单元04文档。本单元选择显式项目约定载入，只改CLI上下文组装，不增工具/服务/依赖。用户已明确指派下一单元，沿用guided-development检查点，完成后暂停。

HEAD和此前已核验的私密远端仍是`e765b48059379ae79e0b62744d98dd6b3563688a`（01～03）。04未提交，所以本轮Diff基于实际04结束的工作区快照`.local/unit-05/before`，而不是拿HEAD错误地把04也算进来。快照元数据见`before-files.json`，当前差异见`key-diff.patch/changed-files.json`。没有提交、推送、合并或修改主目录业务代码。

## 实际命令与结果

使用主仓已有Python 3.12.13；没有使用worktree内另一份Python。所有模型调用保持关闭。完整回归的真实命令：

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

旧Windows目录句柄测试沿用经工具自动审查批准的本机执行环境；不因此访问私人资料或调用模型。`backend-final.log`记录409项、128.489秒、`OK (skipped=3)`，退出0，即406通过。跳过仍是旧语音专用解释器不存在、GPU语音验收未显式开启、本机TTS/ASR运行时/模型不可用；不是本单元新增依赖，也不能宣称语音验收通过。

局部检查把`backend/tests`也加入PYTHONPATH，使用同一绝对Python路径：

```powershell
python -B -X utf8 -m unittest test_cli test_cli_read test_cli_search test_cli_edit test_cli_run_tests test_tool_permissions test_tools -v
python -B -X utf8 -m unittest test_project_context -v
python -B -X utf8 -m ruff check backend evals/harness examples/cli-instructions
python -B -X utf8 -m ruff format --check backend/herta_agent/cli.py backend/herta_agent/project_context.py backend/tests/test_project_context.py examples/cli-instructions/demo.py
python -B -X utf8 examples/cli-instructions/demo.py
```

首个命令是变更前相关基线68项，18.444秒；最终新增9项，2.113秒，均无跳过。规则检查通过；4文件格式检查通过。全库格式未重跑，保留此前旧桌面基线问题。演示退出0，两轮各steps=1，输出实际收到的两句不同约定，指纹变化True；不是用演示脚本证明模型理解了约定。

## 真实失败和修复

| 记录 | 实际结果 |
|---|---|
| baseline.log | 相关68项通过，18.444秒 |
| red-context.log | 初始7项：1失败、14错误（含子用例）；create_agent不识别instructions，CLI也没有该参数 |
| green-context-initial.log | 初次接入后7项通过，1.814秒 |
| context-final.log | 增补项目内链接边界后8项通过，2.266秒；是中间检查，不是最后9项 |
| red-cyclic-links.log | 独立审查指出Python3.12兼容性后，用真实循环链接复现RuntimeError；1项错误 |
| context-cyclic-fixed.log | 捕获3.12路径解析的RuntimeError并转为ContextError后，9项通过、无跳过 |
| backend-final.log | 最终409项，406通过、3项旧语音跳过，128.489秒 |
| ruff-initial.log / ruff-fix.log | 首次规则检查5处问题，均为长行提示；保留本机原记录 |
| ruff-final.log / format-final.log | 最后规则与4文件格式检查通过 |
| demo.log | 两轮真实上下文观察，规则及指纹变化；退出0 |

曾读取一个推测的test_context_builder.py路径但文件不存在，随后直接核对runtime/context.py真实实现；没有把推测当成事实。一次task_plan补丁因原段落文字不一致未应用，读取实际末尾后修正。没有将这些操作报告为成功。

独立代理只做静态审查，未运行全量测试、联网、修改文件或访问用户数据。它指出循环链接P2问题；本机Python3.12.13实际复现后修复，再核对RED/GREEN与代码，未发现剩余P0–P2问题。没有据此宣称已验证恶意并发换文件、真实模型服从规则或其他平台。

## 复用与边界

直接复用原Repository、read_bounded_bytes/decode_utf8、ContextSnapshot、ContextBuilder协议、ContextEngine、Loop、Session和Executor。新适配器位于CLI组装侧，Runtime没有反向依赖Coding模块。具体版本、源文件哈希/行号及官方资料来源见`source-evidence.json`；没有新增依赖或复制上游代码。

只支持明确选入单个项目相对路径，非空UTF-8、允许BOM、最多16KiB，不加载链接、内部排除文件或其他目录。不自动扫描或解析@导入。错误在Provider请求前报告，不静默退回旧规则；同一Run保持原ContextSnapshot，下一个用户消息才读取新内容。系统规则指纹变化不是训练、Skills执行或对话保存。

参数省略时沿用原StaticContextBuilder。真实测试确认约定写着“无需确认”也不能绕过Executor。文件范围检查和JSON编码不是操作系统隔离或提示词注入防护；真实模型表现仍未确认。仅用新建临时文件/离线Provider，未读取旧数据库、私人资料或API Key，没有前端、Electron或GPU语音验收。

仓库归档保留本次关键日志，开发机.local还保留完整中间日志与变更前文件。最终静态校验另见`final-static-check.log`。单元05结束，未进入06，未自动提交或推送。
