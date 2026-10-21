# 单元04：运行测试，核对修改是否有效

## 背景问题

单元03能修改文件，但写入成功不能证明代码正确。现在补一条小闭环：先运行测试看到真实失败 → 读取代码 → 确认修改 → 再测试。用户已要求继续下一单元；本单元结束暂停，不进入05。仍只执行新建演示代码，不调用真实模型。

## 核心原理

像修电器：换好零件，还要通电检查。编辑收据只说明文件写好了，测试结果才说明给定检查是否通过；测试也只覆盖它实际检查的行为。

`ok`回答“测试工具是否正常完成”，`status`回答“测试结果是什么”。断言失败可以是`ok=true, status=failed`；没有找到测试是`no_tests`，全部跳过是`skipped`，都不能当通过。模块/类初始化出错也属于`failed`，即使用例运行数为0。

## 真实源码和调用链

| 文件与函数 | 本单元职责 |
|---|---|
| [cli.py](../../backend/herta_agent/cli.py) `create_agent` | 在原Registry注册`run_tests`，不另建Agent循环 |
| [permissions.py](../../backend/herta_agent/tools/permissions.py) `TerminalApproval/confirm_once` | 复用同一个确认入口，展示工作目录和程序参数；每次测试执行另行确认 |
| [run_tests.py](../../backend/herta_agent/tools/coding/run_tests.py) `test_directory/test_command` | 参数和起始目录检查，构造固定Python参数列表，不执行Shell字符串 |
| 同上 `run_owned/run_tests` | 启动并持有进程树、限制输出、读取报告；取消时等待自己启动的进程收尾 |
| [test_worker.py](../../backend/herta_agent/tools/coding/test_worker.py) `CountingResult/main` | 使用标准库unittest收集/运行测试，直接从结果对象生成JSON，不解析终端文字猜成功 |
| [演示](../../examples/cli-test/demo.py)、[测试](../../backend/tests/test_cli_run_tests.py) | 固定Provider与本次新建真实文件/进程，不是已验证的模型自动修复能力 |

实际演示中，`add_one(1)`错误地返回3，而测试要求2：

1. 第1次Provider请求`run_tests`；Executor校验参数→TerminalApproval确认→handler启动worker，返回`ok=true, status=failed`及真实`3 != 2`。
2. 第2次请求Read，取得源码及指纹；第3次请求Edit，把`return value + 2`改为`return value + 1`，先展示差异再确认。
3. 第4次请求重新测试，新的Python进程实际得到`status=passed`；第5次请求输出回答，因此`steps=5`。

三次人工确认分别是首次测试、编辑、再次测试；确认次数不等于`steps`。此顺序由明确标注的演示脚本决定，不是经过真实模型选择工具。

```powershell
Set-Location -LiteralPath 'D:\Desktop\herta-agent\.local\worktrees\unit-01-cli-read'
$env:PYTHONPATH = (Join-Path (Get-Location) 'backend')
& 'D:\Desktop\herta-agent\.venv\Scripts\python.exe' -B -X utf8 examples/cli-test/demo.py
```

三行分别是：进入本教学目录、告诉Python从backend寻找Herta包、运行演示。按顺序在三次提示中输入`yes`并回车：第一次允许测试，预期出现`FAIL`和`3 != 2`；第二次允许把`return value + 2`改成`return value + 1`；第三次允许重测，预期出现`OK`、`status=passed`，最后`steps=5`。第一次失败是故意设置的错误，不是演示坏了。任意一次输入`no`就拒绝当次操作并结束任务。临时文件会在演示结束时清理，不修改你的项目代码。

## 关键设计取舍

- **先用已有实现**：选择Python自带unittest，不安装pytest或JSON插件。只复用原`documents/process.py::attach_job`及`companion/worker_process.py::resume_process`两个进程助手，执行测试时才导入；没有复制第二套进程框架。旧`coding-agent@e121d82`的run_tests绑定Docker，已读源码但未移植执行链，只沿用“工具完成不等于测试通过”的结果设计。来源哈希和Python版本见执行记录。
- **进程归谁收尾**：Windows子进程先暂停启动，挂到现有Job后再恢复，避免先运行再接管的空隙。Job用来收尾普通子进程树，不限制测试的文件/网络访问。审查发现未经验证的POSIX进程组不能同样处理脱离组的后代，所以本版明确拒绝非Windows测试执行。
- **不从输出猜结果**：worker用unittest公开的结果钩子计数，报告最多8KB，终端输出最多24KB；超出、无报告、退出码不一致均不判通过。`tests_run/successful_tests`数方法，failure/error/skipped等记录的是事件，含subTest时不能简单相加当总方法数。新进程也避开项目旧字节码缓存，防止刚修改同尺寸代码却测到旧版本。
- **保留执行边界**：默认未配置确认器时拒绝；每次只批准本次参数。测试使用当前Python和已有依赖，移除HERTA_*与DEEPSEEK_API_KEY以减少偶然继承，但这不是密钥或文件隔离。项目代码仍拥有当前账号权限；只校验起始目录，不能阻止测试自身导入其他路径。没有通用Shell、Docker、pytest或自动安装机制。

## 测试验证

先观察未注册工具失败，再接入。真实夹具覆盖成功、断言失败、无测试、类/模块初始化错误、整体与子用例跳过、拒绝后不导入代码、起始范围、输出上限、异常退出、旧字节码、取消前未启动，以及超时/反复取消后子进程心跳停止。取消测试同时检查及时返回，避免等夹具自然退出后假称清理成功。

最终完整后端400项中397通过、3项可选语音测试跳过，相关局部68项通过；规则与8个相关Python文件格式检查通过。审查提出的初始化结果优先级、POSIX收尾边界两项问题已修正并复核。实际命令、失败及跳过记录见[执行记录](verification/unit-04/verification.md)，[本单元Diff](verification/unit-04/key-diff.patch)以私密仓库提交`e765b48`为基线。源码检查、固定Provider闭环和真实模型能力分别说明；没有用测试数量宣布产品完整。

“可选语音测试”来自旧桌面版，仍被全量测试发现：`test_herta_speech`中的独立语音解释器取消测试，因该解释器不存在而跳过；`test_herta_voice_acceptance`中的短句完整性测试，需显式开启本机GPU模型验收，本轮未开启；`test_speech`中的本机TTS/ASR链路测试，因本环境缺少就绪的模型/运行时而跳过。跳过不等于通过，也不是单元04的依赖；当前CLI不装配语音服务，本轮没有新增或验收语音功能。单元04归档保留当时快照，本段操作解释在单元05补入。

## 动手练习

可选5分钟观察，不要求写代码：看演示第一次的`ok=True, status=failed`，再看第二次的`ok=True, status=passed`，解释为什么两个`ok`都是真。如果第一次确认输入`no`，程序会在执行测试前停止该任务；可以按自己的进度尝试。单元04到此停止，等待下一次明确指派。
