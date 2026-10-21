# 单元00：教学约定与只读架构审计

日期：2026-10-19。状态：审计与教学配置已完成；以下目录和单元01是提案，等待用户确认，尚未修改或迁移业务代码。

## 背景问题

目标是可解释的 Python CLI Coding Agent。要避免两种浪费：因为界面变化重写正确核心，或把旧桌面/旧 coding 分支整包搬来。当前用户已授权本单元的只读审计、Skill 和学习文档，不需要重复确认开始；下一实现单元仍需确认。

主线本地与远端均为 `phase-6-ui@9ab9796`。旧 coding 候选以本机 `D:/Desktop/herta-agent-coding@e121d82` 为准；远端 `coding-agent@544d680` 是它的祖先，本地多出 `c8afb78` 和 `e121d82` 两个修复。没有切换、合并或推送任何分支。

## 核心原理

像拆工作室：保留能独立工作的设备，换掉把所有业务接在一起的接待台。正式说法是保留低耦合的 Runtime、工具契约和存储，重建 CLI 的组装入口。

Claude Code 官方资料把核心描述为收集上下文、行动、验证的工具循环；Permissions 决定调用能否执行，Context 控制模型看到的内容，Skills/Hook/Subagent 是外围机制。我们的实现不使用 Claude Agent SDK 代替核心，不复制非官方还原源码，不预先把所有扩展做成子系统。

## 真实源码和调用链

整体入口、模块图和已有测试输入 `go` 的逐函数追踪见 [项目地图](project-map.md)。本节给出复用清单；“已有”是源码事实，“保留/修改/移植/新建/退出”是推荐处理，不是完成状态。

| 分类 | 已有实现或候选 | 建议及短理由 |
|---|---|---|
| 保留 | `runtime/agent.py:Agent.run`、`runtime/messages.py` | 已有有界循环、工具配对、取消收尾；不依赖 Electron 或具体人格，无需另写 Loop |
| 保留 | `tools/registry.py:ToolSpec/ToolRegistry` | 参数模型与 handler 合一，已生成 JSON Schema；沿用契约 |
| 保留并修改 | `tools/executor.py:ToolExecutor` | 复用校验/期限/结果封装；现有权限只看 spec，CLI 审批需要接收调用参数与执行上下文 |
| 保留并修改 | `runtime/context_engine.py` | 复用整轮保留与工具配对；节录不是语义总结，长工具输出与 Coding 任务事实保留需另立小单元 |
| 保留 | `runtime/session.py`、`runtime/turn.py` | Session 与 TurnIO 已分开；CLI 使用同一 Session/Loop，不复制 Runtime |
| 保留并调整接线 | `storage/models.py`、`storage/sqlite.py` | SQLite 实现不依赖 FastAPI；保留事务/恢复，不清空旧数据库；新 CLI 使用独立数据目录 |
| 修改后迁移职责 | `service/turn.py:PersistentTurn`、`service/runs.py` | 目前依赖 manager/handle 和服务事件，需做 CLI 适配；不启动整套 HTTP 服务来复用持久化 |
| 保留 | `llm/base.py`、`openai_compatible.py`、`streaming.py`、`config.py` | 模型协议已可替换；复用 HTTP/流式解析与配置校验，模型厂商客户端不等于 Agent SDK |
| 修改 | `herta_agent/__main__.py`、`backend/pyproject.toml` | 旧 CLI 强制人格，实际模型分支还装配 RAG；入口与依赖收敛，避免连离线入口也牵入旧业务 |
| 值得移植 | 旧 `tools/coding/paths.py:Repository` + `read_file.py` | 81+54行，已有实际行号、UTF-8/大小限制、目录检查；先移植只读能力及行为测试，重新验证主线契约 |
| 值得移植 | 旧 `list_directory.py`、`grep_code.py` | 33+55行，真实路径/行号和截断；Search 是字面检索，不是语义检索。先沿用，范围扩大后再评估成熟 `rg` |
| 有条件移植 | 旧 `apply_patch.py:checked_changes/apply_patch` | 185行自写 unified-diff 校验/写入回滚，依赖 workspace.path/lock；不能原封复制。保留参数、回执和测试思路，补丁后端与成熟 `git apply --check` 对照后再定 |
| 保留设计经验，暂不移植执行链 | 旧 `run_tests.py`、`sandbox.py`、`pytest_report.py` | 166+201+52行，绑定 Docker 镜像/副本/pytest JSON插件/容器清理；与本机执行、无沙箱决策不符。可借鉴退出码与测试状态分离、输出限额和取消清理 |
| 暂不移植 | 旧 `workspace.py:Workspace.open`、`plan.py` | 自动复制仓库、固定Plan面板不是首版CLI前提；开发时的Git隔离不等于产品必须维护另一套副本服务 |
| 需要新建 | 薄 CLI 组装/终端事件呈现、本机命令进程生命周期、面向参数的审批接线 | 当前代码缺少目标产品链路；使用 stdlib `argparse/asyncio/subprocess` 等现成机制，不自研进程或沙箱 Runtime |
| 后续单元再定 | Skills、Hooks、Subagent | 已有陪伴文字 Skills 和 EventSink 可研究，但不等于按需加载、完整Hook执行或子Agent；不提前建立空框架 |
| 可以退出目标运行路径 | Electron/FastAPI服务组装、人格、陪伴、语音、文档/磁盘/学习工作台、RAG装配 | 与目标CLI无关，保留旧版本历史与用户数据；本轮不删除 |
| 后续候选 | `tools/mcp.py` | 已有适配器，但不是首个CLI闭环必需；不让它带来第一版所有扩展依赖 |

**移植前必须解决的契约差异：**旧分支的 `ToolSpec` 没有 `permission` 字段；主线默认 `read_only`。旧 Patch 和测试工具若只复制构造代码，会被主线默认视为只读。必须重新声明副作用并验证审批，不能用“以前有测试”替代主线集成回归。这是静态风险判断，本轮未运行越权实验。

旧工作台的 `workspace/file_plans.py:78` 明确拒绝工程目录，不宜通过删掉几条判断就兼作 Coding 文件服务；目标使用一套面向工程的工具与路径规则。新版本不并存两套同职责服务或审批。

## 关键设计取舍

### 实际规模与两种路线

用标准库 AST 读取 import，未导入或运行业务模块。以下为物理行数，含注释和包初始化文件；条件/函数内 import 也计入，不包含动态 import 和第三方传递依赖。

| 静态范围 | 本仓文件/行数 | 直接第三方 import 根 |
|---|---|---|
| 只以 `runtime.agent` 为种子 | 17 / 1293 | pydantic |
| Loop + OpenAI兼容Provider + SQLite | 21 / 2161 | httpx、pydantic |
| 现有教学CLI入口 | 31 / 2620 | httpx、pydantic、numpy，另含条件导入torch/transformers |
| 桌面服务组装入口 | 75 / 9089 | 包含FastAPI/MCP/文档/向量等依赖，见原始清单 |

`backend/pyproject.toml` 当前有10个必需第三方依赖；CLI候选核心直接需要的是httpx和pydantic，SQLite/argparse/asyncio属于标准库。不能把“静态闭包”当实际启动了全部条件依赖，也不能据行数预测开发时长或Token节省。

本机元数据读取为 `httpx 0.28.1`、`pydantic 2.13.5`；当前声明范围分别为 `>=0.28,<0.29` 和 `>=2.10,<3`。Git候选工具为本机 `2.49.0.windows.1`。这些是审计环境版本，不表示新CLI依赖锁或补丁后端已经选定；本轮未安装、升级任何依赖。

| 成本项 | A：在现有主线隔离分支收敛 | B：新建干净Python核心 |
|---|---|---|
| 依赖 | 拆入口、调整包依赖；核心闭包已有证据 | 从小依赖清单开始容易，但重写核心不会进一步消除httpx/pydantic需求 |
| 耦合 | 主要处理`__main__`、服务组装、持久化适配、权限入口 | 不带旧业务容易；若复制相同核心到新目录，本质是迁移，仍要维护import与契约 |
| 正确性 | 保留Session配对、取消和SQLite事务已有实现 | 若真从零写，须重新实现并验证上述行为，不能靠一个while循环替代 |
| 测试 | 已识别14个核心候选测试文件、100个测试函数；逐组迁移运行，本轮未运行 | 仍应迁移这些行为断言；换接口/包路径会增加适配；若丢弃它们需重建证据 |
| 学习复杂度 | 先讲清21文件的核心，可按单元保留路径 | 全新命名较整齐，但初学者同时面对新框架和旧代码对照；复制两份Runtime会造成歧义 |

**推荐A：保留核心、重建组装入口，得到干净目标目录；不是从零重写，也不是保留所有旧业务。** 实现时从已核对的phase-6-ui新建隔离分支；按单元收敛。旧coding分支只选择性移植，不整支合并。新目录、新入口、依赖收敛与持久化适配均须在对应单元确认后实施。

### 推荐的目标目录（提案，尚未创建）

```text
herta-agent/
  AGENTS.md                       # 项目约定；调用用户级 guided-development
  backend/
    pyproject.toml                 # 调整：最小依赖与唯一CLI脚本
    herta_agent/
      __main__.py                 # 修改：只转到CLI main
      cli.py                      # 新增：参数、交互、组装、取消及终端事件
      config.py                   # 保留适用配置
      llm/                        # 保留Provider协议和HTTP/流式适配
      runtime/                    # 保留唯一Loop/消息/Session/上下文/TurnIO
      tools/
        registry.py               # 保留
        executor.py               # 局部修改权限接线
        permissions.py            # 后续单元新增，唯一权限决策入口
        coding/                   # 逐单元移植Read/Search，再确定Edit和本机命令
      storage/
        models.py                 # 保留
        sqlite.py                 # 保留
        turn.py                   # 后续从service/turn提取CLI持久化接线
    tests/                        # 迁移核心行为测试，增加CLI集成测试
  docs/learning/
    project-map.md
    unit-00-architecture-audit.md
    unit-01-cli-read.md            # 完成单元01后才写总结
```

树中的“新增/后续”都不是当前已存在文件。Skills/Hooks/Subagent模块不预建；旧桌面业务从目标分支/发行内容退出时保持旧分支与用户数据。产品入口和测试夹具分开，测试中的确定性Provider不能冒充真实Coding能力。

### 首个学习单元01提案：CLI读一份真实文件并回传结果

- 需求：在指定普通项目目录启动CLI，给出读取Markdown的请求，工具返回真实行号和正文，再进入同一Loop形成回答。第一步不修改目标文件、不运行shell、不接持久化服务。
- 保留并讲解：现有`Agent.run`、`ToolRegistry.definitions`、`ToolExecutor.execute`、`Session`、`StaticContextBuilder`和Provider接口。
- 拟修改：`backend/herta_agent/__main__.py`；拟新增`backend/herta_agent/cli.py`及`backend/tests/test_cli_read.py`；拟选择性移植旧`tools/coding/paths.py`、`read_file.py`，只注册read工具。所有新符号在设计时标为拟新增，不冒充现有函数。
- 验证：使用临时UTF-8文件和可注入的确定性测试Provider，沿真实入口验证“工具声明→实际读盘→结果回填→回答”；缺文件、越界、错误参数、取消如实呈现。没有真实模型验收授权时，不发送任何Herta请求到DeepSeek。
- 预计练习：用户亲手补一个`start_line=0`的参数边界测试，解释为什么错误应来自Executor校验而非读盘函数，约5～15分钟。
- 单元结束：展示关键diff与实际命令、逐函数讲解、写`unit-01-cli-read.md`，等待“继续”。当前尚未进入此单元；实现前还需把小范围设计/计划与开始确认对齐，不自动执行整个里程碑。

## 测试验证

本轮没有运行业务测试、CLI、Electron、Docker、真实Provider或已有私人数据库。核心正确性只做源码审计；上述100个测试函数是迁移候选的静态数量，**不是本轮100项通过**。

实际完成的检查：远端只读`git ls-remote`与本地commit核对；`static_inventory.py`对本仓Python源码进行AST解析和依赖统计；skill-creator初始化与`quick_validate.py`；一次基线与独立Skill行为检查。Skill未启用时测试助手会继续下一单元；启用后能在结束/只读/架构变更处停止，并允许同单元常规修复。

Skill脚本首次因Windows默认GBK解码UTF-8失败；改为当前进程`python -X utf8`后生成和结构校验通过，没有修改系统编码或技能工具。结构校验不保证未来行为永不出错。

详细命令、检查结果与可核对证据位于项目`.local/guided-audit/`，不把原始日志塞进本篇。协作Skill已创建，不意味着Herta产品新增了Skills工具；也没有提交或推送本轮改动。

本轮官方架构依据（2026-10-19读取，内容副本与SHA256在本地审计清单）：[Loop与Context](https://code.claude.com/docs/en/how-claude-code-works)、[Tools](https://code.claude.com/docs/en/tools-reference)、[Permissions](https://code.claude.com/docs/en/permissions)、[Skills](https://code.claude.com/docs/en/skills)、[Hooks](https://code.claude.com/docs/en/hooks)、[Subagent](https://code.claude.com/docs/en/sub-agents)。教学候选固定到[learn-claude-code@ce8f9f1](https://github.com/shareAI-lab/learn-claude-code/tree/ce8f9f186058939da54c9d6fead78dfb5d0fd6c3)，已读取其MIT LICENSE，保留许可/署名是实际复用的前提；本轮未复制其业务代码。Patch替代候选参照[Git apply官方说明](https://git-scm.com/docs/git-apply)，本轮未执行补丁。

## 动手练习

可选的10分钟读源练习：打开项目地图所用的`test_multiple_steps_and_tool_errors_are_fed_back_in_order`，写出输入`go`经历的三次Provider请求和三个工具结果，并指出Session用什么标识将结果对应到调用。再判断`max_steps=1`时第一个工具会不会执行，并在`Agent.run`中找到依据。本练习只读、不需要模型或私人文件；本轮不替用户修改业务代码。
