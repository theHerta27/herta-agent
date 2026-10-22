# Herta Agent

参考Claude Code核心机制、使用Python独立实现的轻量CLI Coding Agent。指定项目目录，用自然语言提出编码任务，模型自主搜索、读取、修改文件并执行受控测试；Harness负责工具调度、权限、上下文、会话与错误处理。

当前交付分支：`learning/unit-01-cli-read`。支持Windows、Python 3.12+；不需要Electron。旧桌面源码保留，但不是本版入口。**`启动CLI.cmd`打开CLI，`启动Herta.cmd`仍打开旧桌面。**

## 安装与启动

在本分支仓库根目录：

```powershell
py -3.12 -m venv .venv-cli
.\.venv-cli\Scripts\python.exe -m pip install ./backend
.\.venv-cli\Scripts\herta-agent.exe --provider openai --repo '你的项目目录'
```

默认DeepSeek配置为`https://api.deepseek.com` / `deepseek-flash`，密钥从`DEEPSEEK_API_KEY`环境变量读取。其他兼容服务可设置`HERTA_BASE_URL`、`HERTA_MODEL`、`HERTA_API_KEY`。详情见[安装与演示指南](docs/CLI_GUIDE.md)。真实请求会发送当前任务及必要项目资料；密钥不落库。

本机工作区已准备`.venv-cli`，可直接运行其中的`herta-agent.exe`，或双击当前工作区的`启动CLI.cmd`并输入项目目录。默认不指定Provider时是明确标注的离线回显模式。

## 当前能力

| 工具/机制 | 实际范围 |
|---|---|
| grep_code / read_file | 项目内字面搜索与有界UTF-8读取，返回路径、行号、截断信息和指纹 |
| edit_file / create_file | 逐次预览并确认；单处唯一替换、SHA256冲突检查；只在已有目录新建，不覆盖 |
| run_tests | 逐次确认后执行Windows Python unittest，区分passed/failed/no_tests/skipped，处理超时、输出限制和进程树收尾 |
| Agent Loop / Provider | 同一模型→工具→模型循环，参数校验、结构化错误、步数和期限限制；模型适配器可替换 |
| Context / 项目约定 | 完整轮次预算与旧历史摘录；显式`--instructions AGENTS.md`每轮加载项目约定 |
| Session / SQLite | 多轮、自动保存、`--list-sessions`和`--resume ID`，项目分库；中断标记、不重放副作用 |

终端中默认显示简洁启动画面、可编辑输入区、中文进度、代码排版与红绿差异。输入`/exit`退出；Ctrl+C取消当前轮。编辑、新建和测试每次单独确认：菜单默认取消，左右键选择后回车，或输入完整`yes`再回车。读取和搜索无须逐次确认。测试具有当前账号权限；审批和目录检查不是操作系统沙箱。详细日志用`--trace`，普通文本用`--plain`，管道自动使用普通文本。

第一版不提供通用Shell、pytest、自动安装依赖、目录创建/删除、多Agent、MCP或复杂Hooks。旧桌面业务的同名能力不计入CLI。一次真实小任务通过不代表任意代码库都能自动修好。

## 真实演示与工程证据

已用真实DeepSeek完成平均值函数的空列表Bug修复：模型自主Search/Read，经确认Edit、回读、运行3个unittest，独立行为检查通过且测试未变。独立安装版退出后恢复同一会话，再由真实模型说明上轮修改。真实行为与本地固定Provider测试分别记录。

- [五分钟演示步骤](docs/CLI_GUIDE.md)：准备新演示项目、运行Agent、独立检查。
- [本次验收与限制](docs/verification/cli-v1-20261022/verification.md)：真实会话、差异、安装和本地回归证据。
- [终端界面验证](docs/verification/terminal-ui-20261022/verification.md)：新界面、键盘确认和安装检查；区分本轮本地测试与此前真实模型演示。
- [架构及真实调用链](docs/architecture/cli-v1.md)：从一句任务走到结果。
- [Claude Code源码对照](docs/architecture/claude-code-2.1.88-audit.md)：固定提交、关键函数与取舍。
- [面试介绍与追问](docs/INTERVIEW.md)、[学习地图](docs/learning/project-map.md)。

直接依赖为httpx、pydantic、Rich与prompt_toolkit；旧桌面依赖在`desktop`可选组，本地模型与语音依赖仍为可选。源码研究以官方文档为主要机制依据，第三方2.1.88还原快照只读学习；未直接复制非开源代码，也未用Claude Agent SDK代替核心Harness。

历史资料：[旧桌面使用说明](docs/legacy-desktop.md)、[v1初始审计](docs/CLI_V1_AUDIT.md)。不把历史功能计划当作本版待办。
