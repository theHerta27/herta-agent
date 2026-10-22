# 简洁终端界面：本轮验证

范围：启动画面、可编辑输入、中文进度、Markdown/代码和差异排版、默认取消的确认菜单。沿用唯一Agent Loop、Executor、TerminalApproval、Session和SQLite。用户批准Rich与prompt_toolkit依赖；本轮未调用真实模型、未访问私人项目、未提交或推送。

## 实际验证

以下命令在本工作区运行。测试源码时设置`PYTHONPATH=backend`，Python为`.venv-cli/Scripts/python.exe`；静态检查用主目录已有开发环境。

| 检查 | 本轮结果 | 能证明的范围 |
|---|---|---|
| `python -B -X utf8 -m unittest discover -s backend/tests -p 'test_cli*.py' -v` | 113项通过，45.169秒 | CLI读取/搜索/编辑/新建/测试、上下文、保存恢复、拒绝和冲突，以及新UI |
| 上述命令改用`test_cli_terminal*.py` | 17项通过，4.029秒；审查者独立重跑也通过 | 真实Rich渲染、键盘输入、默认取消、完整yes、方向键确认、D不批准、Ctrl+C/EOF拒绝、两种换行差异、普通文本退回 |
| `python -m unittest test_tool_loop test_context_engine test_session_store -v` | 31项通过，2.608秒 | 原循环、上下文与SQLite核心；另将backend/tests加入模块路径 |
| `python -m ruff check backend` | 通过 | 静态规则；不代替运行验收 |
| `python -m ruff format --check`（本轮7个变更Python文件） | 7个文件已格式化 | 本轮CLI、UI、审批及测试；未改旧桌面测试格式 |
| `uv build backend --wheel --out-dir .local/terminal-ui-dist --offline`及安装 | 成功 | 独立wheel安装到现有`.venv-cli`，不是只改源码未安装 |
| 安装目录逐文件核对 | 98个Python文件字节与源码一致 | 安装版本已更新；无FastAPI/MCP/Torch/NumPy/Piper/Uvicorn依赖 |
| Windows PowerShell启动脚本，`-Demo`、管道输入`/exit` | 成功退出，中文正常 | 实际启动器编码、路径和普通文本退回；未读取密钥或调用模型 |
| 自建临时目录，实际终端输入、右键方向再回车、`/exit` | 观察到预览→明确选择→实际写入收据→排版回答→退出 | 使用真实安装版、原Loop与文件工具，但Provider为明确标注的固定脚本；不是模型自主选择验收 |

取消测试不是仅模拟返回值：`terminal_interrupt_probe.py`在独立子进程中使用真实PromptSession，输入后对模型等待和工具等待分别发SIGINT，验证清理、等待动画停止及第3轮可继续。方向键等输入用prompt_toolkit官方create_pipe_input/DummyOutput方法验证。实际终端检查使用本工具PTY，进程内设置`TERM=xterm-256color`，没有修改用户环境；未声称逐一人工检查所有终端/中文输入法。

原始本地日志保留在`.local/terminal-cli-final.log`、`terminal-fallback-red.log`、`terminal-fallback-green.log`、`terminal-core-final.log`、`terminal-installed-check.json`、`terminal-launcher-smoke.log`及构建/安装日志。新回归先观察失败再修复。

## 保留的失败与限制

旧完整后端跑了两轮，每轮461项、1 error、3项可选语音跳过，**没有得到全套通过**。第一轮156.207秒，旧服务测试读取临时port.txt发生PermissionError；未改代码单独重跑通过（2.418秒）。第二轮2213.163秒，旧MCP生命周期测试等待启动5秒超时；单独重跑通过（1.859秒）。错误来源不同，未确认根因，不凭重跑成功宣称已修复。日志为`.local/terminal-backend-full.log`、`terminal-backend-final.log`和各自retry日志。最后两处UI修正后跑了上表CLI/核心测试，未再重跑整个旧后端。未运行Electron、ASR/TTS或新的付费模型测试。

审查发现CRLF→LF和反向预览被统一换行而掩盖差异，已恢复显示字面`\r`，双向真实prepare_edit回归通过。实际PTY还发现TERM=dumb会让prompt_toolkit绕过自定义按键、返回文本：CLI现自动退回普通文本；直接使用UI时也只接受严格True或完整yes。默认回车、部分y、yes后附加另一行均拒绝。审查者复核后未发现新的Critical/Important；独立审查不代替上面的测试边界。

回答仍是非流式，等待动画只表示请求进行中。普通文本、管道和TERM=dumb/unknown使用原yes确认方式。上下键输入历史仅在进程内；跨进程对话恢复仍用原SQLite和--resume。宽度、颜色取决于终端；模型或文件中的控制字符先转义。确认菜单不能提供操作系统隔离。

## 具体复用与源码学习

直接使用Rich **14.3.4**（MIT）和prompt_toolkit **3.0.53**（BSD-3-Clause），兼容范围与传递依赖记录在backend/pyproject.toml和uv.lock。Rich使用Console/Panel/Markdown/Syntax；prompt_toolkit使用PromptSession、KeyBindings、InMemoryHistory及官方输入测试工具。依据：[Rich文档](https://rich.readthedocs.io/en/stable/)、[prompt_toolkit输入文档](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/asking_for_input.html)、[测试方法](https://python-prompt-toolkit.readthedocs.io/en/stable/pages/advanced_topics/unit_testing.html)。没有另写Markdown解析器或终端输入框。

Claude Code第三方2.1.88还原快照固定提交`554bc4514ebaf83ef54d95bc44f4add7272d4f46`，仓库Hyper66666/claude-code-sourcemap。本轮只读以下组件的导入、选定声明与渲染片段；未运行上游，未声称还原代码等同官方原始源码，未复制实现：

- `restored-src/src/components/LogoV2/Clawd.tsx`：`Clawd`使用React与Ink的Box/Text形成终端形象；Herta采用独立文字标识，不移植动画。
- `restored-src/src/components/PromptInput/PromptInput.tsx`：`PromptInput`含输入、状态和权限上下文协作；Herta仅用成熟库提供基本可编辑输入，没有移植大型组件。
- `restored-src/src/components/Markdown.tsx`：`Markdown → MarkdownBody/MarkdownWithHighlight`分开排版与高亮；Herta直接调用Rich.Markdown，不据此宣称复刻其流式渲染。
- `restored-src/src/components/permissions/FileEditPermissionRequest/FileEditPermissionRequest.tsx`：`FileEditPermissionRequest → parseInput → FilePermissionDialog`及确认回调传递；Herta只借鉴“实际差异和选择放在一起”的交互，执行仍由原Executor负责。

四份缓存的Git blob与SHA256清单在`.local/terminal-ui-research/manifest.json`。这类源码学习只说明设计来源，产品正确性依赖本项目测试和实际运行。
