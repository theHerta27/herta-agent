# Herta CLI v1：现状审计与交付标准

后续交付状态：A/B/C已实施，实际结果见[CLI v1验收](verification/cli-v1-20261022/verification.md)。以下保留实施前审计时间点的判断；“未验证/等待同意”不表示最新状态。

审计日期：2026-10-22。目标是面向2027届AI Agent开发岗的完整Python CLI Coding Agent：自然语言任务经过同一个Harness，自主选工具、读取/修改项目并验证结果；工程优先，教学伴随。以下阶段是实施建议，不是已完成的产品功能声明。

## 基线与边界

- 工作目录：`D:\Desktop\herta-agent\.local\worktrees\unit-01-cli-read`，分支`learning/unit-01-cli-read`，HEAD为`683b38a78b30ff01cd68bc6cb850db3decb4b5fa`。单元08的未提交源码、测试、示例与文档继续保留，没有重置工作区。
- 主目录仍为`phase-6-ui@9ab9796d819216a64c783eeba75f7ac804441a23`，原有文档改动未覆盖。旧桌面业务、用户数据库及模型不迁移、不清空。
- 本轮只读检查业务代码、查阅上游、运行离线测试，新增审计和证据；同步AGENTS协作约定与规划记录。没有产品代码修改、依赖安装、付费模型调用、提交或推送。

## 当前能力与缺口

| 能力 | 真实代码与已确认行为 | v1判断 |
|---|---|---|
| 单一Agent Loop | `runtime/agent.py:Agent.run/_request`；每步准备上下文、调用Provider，有tool_calls则执行回填，否则完成。限制步数、每次最多4个工具调用；异常/取消补齐待返回结果并释放会话 | 保留，避免第二套循环 |
| 工具契约与执行 | `tools/registry.py:ToolSpec/ToolRegistry`生成Schema；`tools/executor.py:ToolExecutor.execute`查找、参数校验、确认、限时执行、返回结构结果 | 保留；真实模型选工具尚未验收 |
| 编码工具 | `tools/coding/`已有read_file、grep_code、edit_file、create_file、run_tests | 已做真实临时文件/进程的离线验证；Search为字面检索，Edit为单处唯一替换，新建不自动建目录/覆盖，不夸大为通用开发环境 |
| 权限与写入 | `tools/permissions.py:TerminalApproval/confirm_once`显示真实差异或测试范围，只有yes批准当前调用；Edit用Read指纹拒绝过期内容，新建拒绝覆盖 | 保留同一审批；拒绝后的真实模型回答/重试行为待验收 |
| 测试执行 | `tools/coding/run_tests.py:run_owned`与test_worker，Windows当前Python执行unittest，处理输出限制、超时与自有进程树收尾；status区分passed/failed/no_tests/skipped | v1先明确支持Windows与unittest；当前用户权限，不是沙箱，不提供Shell/pytest/自动安装 |
| 上下文 | `runtime/context_engine.py:ContextEngine.prepare/_turn_groups/_summary`；估算预算、完整轮次选择、extractive-v1旧文字节录，保留Session原文，当前轮次超限明确失败 | 保留并说明简化；没有模型语义压缩，估算不是计费Token |
| 模型接入 | `llm/openai_compatible.py`接收标准tool_calls，配置在`config.py:ProviderSettings.from_env`；DeepSeek域名优先DEEPSEEK_API_KEY，不打印Key；HTTP失败不自动重试 | 适配器已有MockTransport验证，真实服务当前未调用。未发送服务端输出上限，也未向上返回usage，验收前需明确请求/输出边界与费用记录办法 |
| CLI入口与交互 | `cli.py:main/run_cli/create_agent/chat/run_turn`，多轮进程内Session、/exit、Ctrl+C、可选--trace/--instructions/--context-window | 入口可运行，但默认demo是固定回显；正式交付需让真实模式/离线演示清晰可辨 |
| 持久化 | `Session.restore`、`storage/sqlite.py:SQLiteSessionStore`已有历史、事务与中断恢复；CLI.chat每次新建内存Session，没有恢复参数 | 需要接线，不重写存储。`service/turn.py:PersistentTurn`仍依赖RunManager/handle，不能直接导入当作独立CLI适配器 |
| 独立安装 | `backend/pyproject.toml`基础依赖仍有10项，含FastAPI、MCP、PDF/DOCX等旧功能；静态CLI导入闭包29个Herta模块，主要第三方根为httpx/pydantic，部分进程助手路径仍在旧业务目录 | 未做干净环境安装。优先同一源码包分离核心依赖与desktop extras，并保持旧安装路径可用；不另拷一份Runtime |
| 执行证据 | `RuntimeEvent`已有模型完成、工具结果与上下文事件，`cli_events.py`只显示简短元数据，不落盘 | 复用事件生成验收记录；持久会话后再接必要轨迹，不引入Hooks/监控平台 |

当前静态调用链：`main → run_cli → create_agent → chat/run_turn → Agent.run → ContextEngine.prepare → Provider.complete → ToolExecutor.execute → ToolSpec.handler → MemoryTurn/Session → 下一步Provider → 最终回答`。例如“定位函数并解释”的自然语言输入将沿这条链执行，但模型是否真正选择Search和Read，仍须P0验证，不能以固定ReadDemoProvider代替。

## 本轮实际验证

使用现有Python3.12环境，PYTHONPATH明确指向当前工作区backend及backend/tests；测试进程移除HERTA_*和DEEPSEEK_API_KEY，不打印凭据。CLI组含新建临时文件/Windows测试进程，按原有边界在沙箱外运行；没有执行已有私人项目。

```powershell
& 'D:\Desktop\herta-agent\.venv\Scripts\python.exe' -B -X utf8 -m unittest discover -s backend/tests -p 'test_cli*.py' -v
& 'D:\Desktop\herta-agent\.venv\Scripts\python.exe' -B -X utf8 -m unittest test_runtime test_runtime_commits test_runtime_events test_runtime_streaming test_tool_loop test_tool_permissions test_tool_provider test_tools test_context test_context_engine test_project_context test_provider test_provider_env test_provider_streaming test_session_store -v
```

- CLI相关84项通过，27.825秒；核心相关103项通过，6.508秒；两组不重叠，共187项，均无跳过。
- 验证包含真实临时文件操作、确认/拒绝、指纹冲突、测试失败/跳过分类、取消、上下文超限、Mock HTTP协议与临时SQLite恢复；这些不是187个真实模型任务。
- 2026-10-21的完整后端435项/3跳过保留为历史证据，本轮未重跑全量旧后端、前端、Electron或可选语音；不据历史数量声明当前产品完整可用。
- 原始日志与来源清单见[本轮证据](verification/v1-audit-20261022/verification.md)。本轮不引入新业务测试来包装审计成果。

## 建议的三个交付阶段

### A：P0真实任务闭环与最小修复

先用现有Harness建立一份小型、非私人Python演示项目及独立验收断言；模型决定工具和参数，验收驱动只负责初始化、记录与核查，不预先编排工具调用。复用现有事件与Provider，不写第二套Agent。先在本地验证任务、确认、异常注入与记录方式，实际付费前单独征求同意，明确模型、发送资料、调用次数/输出上限及中止条件。当前没有这次同意，也没有真实调用。

按用户后续明确要求，首轮验收收敛为一条简单真实闭环：模型搜索并读取average代码与测试，确认后修复空列表除零，再执行测试并说明真实结果。使用[演示资料](../examples/coding-task/README.md)，拒绝/冲突/取消继续沿用现有本地测试，不额外建设评测平台。下面五项是机制与结果检查点，不要求额外做五次真实任务：

| 场景 | 通过条件 |
|---|---|
| 搜索、读取、解释 | 真实HTTP返回的tool_calls由模型生成；实际Search/Read结果与源码一致；解释命中独立核对点，不靠固定回答 |
| 简单Bug修复并测试 | 先读取真实代码；人工查看差异并确认；改动符合需求；实际unittest有非零有效测试并通过；独立验收断言通过，不能靠删测试或放宽断言过关 |
| 用户拒绝 | 显示预览后拒绝，目标字节保持不变，返回permission_denied；模型不声称已经修改，不能绕过再次确认 |
| 文件冲突 | 在预览停顿期间只修改本次自建夹具，制造指纹变化；旧修改不得覆盖新内容，反馈edit_conflict；模型核查后停止或提出新的、再次确认的操作 |
| 测试失败 | 故意提供未通过的自建测试；真实工具status=failed，模型如实解释；修复若获许可必须重新运行并核查，不把ToolResult.ok当成通过 |

证据至少保存模型/配置、真实Provider身份、每次模型返回的tool_calls、工具结果、人工确认、文件前后指纹/差异、测试报告与最终回答。服务响应提供usage时记录原值；没有usage就注明，不能虚构费用或精确Token。记录不含鉴权头、Key、私人会话。对失败只做必要小修复，再重跑受影响场景；不为一次任务新增复杂平台。

### B：P1独立CLI交付

在阶段A验证的工具链上，收敛同一Python包的依赖/安装入口，并以原SQLite与TurnIO协议接CLI持久化。允许薄适配器承担CLI生命周期，不复制现有存储或把整个HTTP服务引入CLI；若确需共享适配层调整，先说明设计并确认，再实施。

阶段验收：

- 全新环境按文档安装、配置、启动；不装Electron，不需要语音/文档业务依赖；发布内容明确排除缓存、模型、密钥与用户数据。
- 默认/真实/demo模式清楚，Key留在环境中；无Key/无效地址给出可理解错误。
- 多轮对话、退出后恢复同一会话可实际演示；恢复绑定正确项目目录，不继承旧审批，不自动重放副作用；CLI使用独立新数据位置，不开旧桌面数据库。
- 保留预览和逐次人工确认；取消模型、工具及测试进程后可继续使用，会话中的未完成调用有明确状态。
- 明确Windows/unittest范围、当前用户权限和失败行为；不会把目录检查称为操作系统沙箱。
- 共享代码/元数据调整有相关旧后端与旧安装入口回归；旧桌面功能和旧数据保留。

### C：P2证据、文档与面试交付

用已经跑通的产品更新README：安装与配置、一个完整任务、能力边界、架构与调用链。保留docs/learning，不再把历史单元清单当成产品首页。整理三类上游源码对照（[本轮初步研究](architecture/claude-code-2.1.88-audit.md)）、真实任务记录、简短录屏/可复现脚本，以及常见追问。发布说明只写有代码和验证支持的能力；不写未实现的多Agent/MCP/复杂Hooks/完整自动压缩。

若阶段A的付费调用暂未获准，可先做B的离线准备与C的已有证据整理，但A必须保持未完成，不能宣布v1验收。

## v1完成标准

以下条件全部满足才标记完成：

1. 指定支持平台上，新环境能按文档独立安装并运行CLI。
2. 经用户事先批准，真实模型完成一条搜索/读取→确认修改→运行测试的简单编码闭环，工具由模型选择，独立核查通过；拒绝/冲突/取消等保护有现有本地测试证据。失败项如实记录，不用模拟任务冒充真实验收。
3. 同一会话可多轮使用、退出后恢复；权限、文件冲突、取消、异常和上下文超限行为与文档一致。
4. 演示项目、实际改动和真实测试报告一致；工具执行成功、模型文字回答、业务任务成功分别判定。
5. 核心架构/三类源码对照/设计取舍/面试追问齐备；来源标明版本、提交、函数与未确认项。
6. 不破坏旧桌面业务，不引入第二套Loop/文件服务/审批/存储，不自动提交推送，不扩大私人数据授权。

当前状态：审计完成；阶段A已经开始准备非私人演示任务，本地准备不代表真实模型通过。付费调用前单独确认；B/C尚未完成。
