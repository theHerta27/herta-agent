# 一条真实编码任务

目标：让真实模型通过现有CLI修复`average([])`的除零异常，使其返回0，并运行测试验证。模型自主选择工具；这里没有固定工具调用Provider或另一套Agent Loop。

`project/`是故意保留缺陷的模板。三个测试中，空列表测试在修复前报ZeroDivisionError，另两个通过；这是任务起点，不是Herta回归失败。每次prepare新建副本，不修改模板，不覆盖原项目。

## 准备（不调用模型）

在当前教学分支根目录运行，Python需为3.12或以上：

```powershell
$taskPrepared = python -B -X utf8 examples/coding-task/prepare.py | ConvertFrom-Json
$taskPrepared.project
```

只在本仓库`.local/coding-demo/average-*`创建三份演示文件和标记，不读取Key、不联网。请记录输出路径；结束后保留副本便于查看实际改动。

## 正式运行（付费前需同意）

以下命令会把CLI系统说明、工具定义、演示项目约定、该任务和工具读取的演示资料发送到已配置的模型服务。API Key只用于鉴权，不写入日志。默认DeepSeek地址/模型沿用现有配置；使用前核对自己的配置和付费授权。

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'backend')
python -B -X utf8 -m herta_agent --provider openai --repo $taskPrepared.project --instructions AGENTS.md --message $taskPrepared.task --max-steps 8 --context-window 16384 --timeout 60 --trace
```

每次编辑和运行测试仍由原TerminalApproval展示范围并确认，输入yes才执行。最多8次模型请求，每次最长60秒；这不是金额硬上限。现有Provider没有发送服务端max_tokens，16384只是本机上下文预算，不保证费用或实际输出长度。本例不会自动安装依赖或开启其他工具。

本机演示先只需完成这一条任务；拒绝/冲突/取消等保护沿用已有本地测试，不扩建评测平台。请保留终端实际轨迹、预览和测试结果，明确这次使用的是openai真实Provider。

## 独立核查（不调用模型）

```powershell
python -B -X utf8 examples/coding-task/check.py $taskPrepared.project
```

检查器只接受本准备脚本生成目录中的演示标记。它会执行该自建项目的Python代码，具有当前用户权限；不是沙箱。要求至少三个项目测试通过，并独立核对空列表、整数、负数和小数的实际返回值。通过时退出0、`passed=true`；未修复时退出1。它不根据模型自述判定成功，也不单独证明模型选择过工具。

当前本地准备完成与真实模型验收是两个状态：只有实际使用真实Provider完成修改、确认、测试，再通过独立核查，才能记录真实闭环通过。首次准备并未调用模型。
