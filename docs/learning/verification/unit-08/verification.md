# 单元08执行记录

日期：2026-10-21。隔离工作区：`D:\Desktop\herta-agent\.local\worktrees\unit-01-cli-read`；分支`learning/unit-01-cli-read`。本单元基线为已上传的`683b38a78b30ff01cd68bc6cb850db3decb4b5fa`，之后没有提交或推送08。

## 本轮上传

用户要求“把当前为止的进度都上传github，再进行下一单元”。先通过`gh repo view theHerta27/herta-agent --json isPrivate,visibility,url,defaultBranchRef`实际确认PRIVATE；相关97项回归通过（21.086秒），扫描95个待上传源码/文档/证据文件约987KB，无凭据模式或异常路径/体积命中。上传检查日志留在本机`.local/upload-units-04-07.log`。

提交`683b38a`：`feat: add guided test context trace and file creation units`，95文件。推送同一教学分支，未合并主线、未新建公开仓库或PR。GitHub API读取远端分支指针与该SHA一致；[上传检查点](upload-checkpoint.json)保存结果。

```powershell
git -c safe.directory=D:/Desktop/herta-agent/.local/worktrees/unit-01-cli-read -c http.sslBackend=openssl -C 'D:\Desktop\herta-agent\.local\worktrees\unit-01-cli-read' push -u origin HEAD:refs/heads/learning/unit-01-cli-read
gh api repos/theHerta27/herta-agent/git/ref/heads/learning/unit-01-cli-read --jq '.object.sha'
```

网络推送在授权的沙箱外执行；只用单次Git配置，未改全局配置或关闭证书校验。上传范围为01～07，不包括后续08、模型、.local、用户数据库或私人资料。扫描无命中不是对所有历史提交的安全审计。

## 范围与来源

唯一生产改动是`cli.py`：导入原ContextSettings、解析--context-window、通过RunSettings传递。新增test_cli_context.py、examples/cli-context/demo.py、学习总结；更新README、项目地图及任务计划，共7个源码/文档文件。另生成本证据目录。主目录progress.md只追加完成记录，主目录产品代码未动。

ContextEngine/Session/Provider/Executor/Registry/配置模型/存储、工具权限和依赖均未修改。实际复用符号、文件指纹、版本及官方概念参考见[source-evidence.json](source-evidence.json)；本单元不复制Claude Code非官方源码。逐文件前后指纹见[清单](changed-files.json)，[关键差异](key-diff.patch)由本单元开始前快照生成，包含未跟踪的新文件，排除证据目录避免递归。

## 实际检查

以下是实际检查命令主体，均在隔离工作区运行。执行测试前设置PYTHONPATH指向该工作区backend（局部unittest额外包括backend/tests），设置UTF-8及PYTHONDONTWRITEBYTECODE，并从测试进程环境移除HERTA_*和DEEPSEEK_API_KEY，不打印凭据。完整旧后端回归仅重新加入HERTA_LIBREOFFICE，指向本机已有转换程序，供临时文档测试使用。

```powershell
& 'D:\Desktop\herta-agent\.venv\Scripts\python.exe' -B -X utf8 -m unittest test_context_engine test_context test_cli test_cli_trace test_project_context test_runtime_events -v
& 'D:\Desktop\herta-agent\.venv\Scripts\python.exe' -B -X utf8 -m unittest test_cli_context -v
& 'D:\Desktop\herta-agent\.venv\Scripts\python.exe' -B -X utf8 -m unittest test_cli_context test_context_engine test_context test_cli test_cli_trace test_project_context test_runtime_events -v
& 'D:\Desktop\herta-agent\.venv\Scripts\python.exe' -B -X utf8 -m unittest discover -s backend/tests -v
& 'D:\Desktop\herta-agent\.venv\Scripts\ruff.exe' check backend/herta_agent/cli.py backend/tests/test_cli_context.py examples/cli-context/demo.py
& 'D:\Desktop\herta-agent\.venv\Scripts\ruff.exe' format --check backend/herta_agent/cli.py backend/tests/test_cli_context.py examples/cli-context/demo.py
& 'D:\Desktop\herta-agent\.venv\Scripts\python.exe' -B -X utf8 examples/cli-context/demo.py --context-window 8192
& 'D:\Desktop\herta-agent\.venv\Scripts\python.exe' -B -X utf8 examples/cli-context/demo.py --context-window 32768
```

| 阶段 | 实际结果 | 原始记录 |
|---|---|---|
| 相关基线 | 44项通过，9.735秒 | [baseline.log](baseline.log) |
| 原5项新增检查，接线前 | 3失败、2通过，6.131秒；CLI不识别新参数。已有引擎集成检查本来就通过 | [red-budget.log](red-budget.log) |
| CLI接线后 | 原5项通过，6.918秒 | [green-budget-initial.log](green-budget-initial.log) |
| 首次规则检查 | 4处E501长行；运行格式化后通过，不改核心行为 | [ruff-initial.log](ruff-initial.log)、[format.log](format.log) |
| 审查时第一轮回归 | 相关49项通过，16.279秒；完整434项，431通过、3跳过，135.751秒 | [focused-final.log](focused-final.log)、[backend-final.log](backend-final.log) |
| 审查后补强证据 | 单独新增“超限后完整工具结果保留且可继续短任务”的第6项检查通过，0.093秒；原实现已满足，非新修复 | [session-overflow.log](session-overflow.log) |
| 最终相关回归 | 50项全部通过，17.069秒 | [focused-passed.log](focused-passed.log) |
| 最终完整后端 | 435项中432通过、3项跳过，133.841秒，退出0 | [backend-passed.log](backend-passed.log) |
| 最终规则/格式 | All checks passed；3 files already formatted，退出0 | [ruff-passed.log](ruff-passed.log)、[format-passed.log](format-passed.log) |
| 两种窗口真实离线演示 | 两次退出0；8192选任务3并带节录，32768选完整任务1/2/3；两次Session12消息、工具配对True | [demo-small.log](demo-small.log)、[demo-large.log](demo-large.log) |

最终完整回归重跑的原因是增加了第6项测试，避免将此前434项的结果冒充最终435项。完整旧后端包含Windows进程行为，按既有本地测试边界在沙箱外执行；测试只运行仓库代码和自己创建的临时资料，不执行已有私人项目。

三项跳过为：test_herta_speech的optional local voice runtime、test_herta_voice_acceptance的opt-in GPU model、test_speech的local voice models are optional。它们不是本单元失败，也没有补做语音/GPU验收。

## 审查与证据强度

独立审查范围是CLI、本单元原5项测试及离线演示，静态审查无P0–P2。确认本地预算接线与校验顺序正确，并提醒两处表述边界：2048预留不是API max_tokens；“磁盘文件没变”本身不能证明Session保存的工具结果完整。

后一个提醒通过第6项集成测试补强：直接捕获ContextError，断言Session最后一条为tool，完整5000字内容、truncated=false，再在同一Session完成短任务。没有因此修改产品算法。补充测试已纳入最终50/435项回归；没有声称它单独做过先红后绿。

多轮集成检查观察固定Provider实际收到的消息，逐次校验预算、当前任务、旧轮次取舍、工具调用ID与结果ID一一对应，并验证Session保留12条消息。这能证明本地控制流和数据选择，不能证明真实模型理解了材料、供应商精确Token计数正确，或达到Claude Code完整自动压缩效果。

## 最终边界

未调用真实DeepSeek/Embedding；未读取用户私人文档、旧会话数据库或音频；未运行前端/Electron。无新依赖、无沙箱、无CLI持久化、无新的工具或第二套审批。总窗口改变不扩大模型能力；当前必需内容过大仍明确失败。ContextSnapshot.sha256只覆盖系统文本，不是整次Provider消息哈希。

完成单元08后停止；08本地未提交推送，HEAD及upstream保持683b38a，等待用户学习或明确继续09。最终静态清单另见[final-static-check.log](final-static-check.log)。
