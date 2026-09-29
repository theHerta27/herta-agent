# Coding Agent 改造计划：5个可见交付阶段

> 目标：把现有 Runtime（`Agent` 循环、`ToolRegistry`/`ToolExecutor`、Session/存储、SSE、Electron 壳）演进为一个能对真实代码库做理解、规划、修改、调试、评审的 Coding Agent。不新建通用多 Agent 抽象，不为尚不存在的功能预留接口。本计划范围之外的任何集成、协议统一、跨系统设计都不在本轮考虑范围内。

## 全局约束与入口

- 在新分支上开始（例如 `coding-agent`），不修改 `phase-6-ui` 分支上与角色陪伴（persona、search_knowledge、Herta 素材）相关的现有代码；那部分保持原样，作为独立功能保留。
- 复用已有框架，不重写：`runtime/agent.py` 的循环、`tools/registry.py`/`tools/executor.py` 的工具契约、`storage/`、`service/sse.py` 均视为稳定基础设施，仅在确有必要时改动。
- 新工具接入点固定为 `service/app.py` 的 `create_app`：替换 `echo_registry()` 为新的开发工具注册表，替换 `context_builder=PersonaContextBuilder(...)` 为新的代码语义检索 `ContextBuilder`。除此之外不改 `app.py` 其他逻辑。
- 命名保持通用（如 `tools/coding/`、`CodeContextBuilder`），不写死与角色陪伴场景耦合的命名。
- 延续现有测试纪律：先写行为测试确认预期失败，再最小实现；不伪造"通过"，真实失败要如实展示。
- 目标代码库（下称"靶场仓库"）默认建议直接使用 `backend/` 自身（已有 178 项测试、结构清楚，无需额外准备）。Coding Agent 的所有写操作只能作用于靶场仓库的一个隔离 git worktree 或副本，禁止触碰 Electron 正在运行所依赖的工作目录。
- 每阶段结束能在 Electron 窗口里亲手验证；不要求每行代码都有单测，但关键工具行为、路径校验、取消/超时路径需要行为测试覆盖。

---

## 阶段0（前置依赖，非本计划范围）

在 `phase-6-ui` 分支按已有 `docs/phase-6-plan.md` 阶段6完成 Settings（Base URL / 模型可配置持久化，Key 仅认环境变量不落盘）。本阶段不在这里重复设计或实现，只作为并行前置任务标注：Coding Agent 分支可以在阶段6完成之前并行开始，两者互不阻塞，但正式对外演示前两者都应完成。

---

## 阶段1：只读代码理解闭环

**亲手可见：** 在 Electron 窗口里对着靶场仓库提问（例如"`ToolExecutor.execute` 在哪个文件里定义，超时是怎么处理的"），Agent 能调用工具读取真实文件并给出准确引用，界面上能看到具体调用了哪些工具、读了哪些文件。不支持修改、不支持调试、不支持评审。

**主要文件：**
- 新增 `backend/herta_agent/tools/coding/paths.py`：仓库根目录白名单校验（参考 `config.py` 里 `validate_base_url` 的"提前拒绝非法输入"写法）
- 新增 `backend/herta_agent/tools/coding/read_file.py`、`list_directory.py`、`grep_code.py`
- 修改 `backend/herta_agent/service/app.py`：注册表替换为只含以上三个工具（本阶段不注册 `search_knowledge`，也不注册写操作工具）
- 新增 `backend/tests/test_coding_tools_readonly.py`

**工作：**
- [x] 定义靶场仓库根路径配置（新增环境变量，例如 `HERTA_CODING_REPO_ROOT`），启动时校验路径存在且为目录，校验方式与 `ProviderSettings.from_env()` 的失败提示风格一致
- [x] `read_file`：支持可选行号区间参数，超过大小阈值时截断并在返回结构里明确标注截断，不静默丢内容
- [x] `list_directory`：默认排除 `.git`、`node_modules`、虚拟环境目录
- [x] `grep_code`：对关键词做文本检索，返回文件路径 + 行号 + 匹配行，限制单次返回条数并在超限时明确提示
- [x] 三个工具共用路径校验：任何解析后路径落在仓库根目录之外一律拒绝，返回结构化 `ToolResult.failure`，覆盖 `../` 穿越、绝对路径穿越、符号链接指向外部三种用例的行为测试
- [x] 先写"路径穿越必须拒绝""正常路径必须成功""不存在路径返回明确错误"的测试，确认先失败，再实现

**验收：** 单元测试覆盖上述三类路径校验用例全部通过；真实 Electron 窗口下，对靶场仓库提出一个需要跨文件查找的问题，能在工具活动区看到 `read_file`/`grep_code` 的调用记录与真实返回内容，最终回答引用的文件路径和行号与实际代码一致。

---

## 阶段2：任务规划可视化

**亲手可见：** 给一个明确需要多步骤的需求（例如"给某个模块新增一个函数并补充对应测试"），Agent 先输出一份分步清单，清单在界面上以独立的打勾列表形式展示，而不是和最终回复混在一起或以原始 JSON 呈现。

**主要文件：**
- 新增 `backend/herta_agent/tools/coding/plan.py`（`propose_plan` 工具）
- 新增 `frontend/src/components/PlanActivity.tsx`
- 修改 `frontend/src/state/tool-activity.ts`：为 `propose_plan` 增加专门的结果投影逻辑（参照现有对 `search_knowledge` 的特判方式）

**工作：**
- [x] 定义 `PlanStep`（`title`、`rationale`，本阶段不含状态字段，重新规划留到阶段3再评估是否需要）
- [x] `propose_plan` 工具本身不执行任何操作，只承载结构化清单，供前端渲染和供模型在后续步骤里引用
- [x] 前端新增 `PlanActivity.tsx`，渲染清单条目而非 JSON dump；接入 `RunGroup.tsx` 现有的工具活动区域
- [x] 先写"清单结构缺字段时的校验失败""清单正确渲染成列表"的测试

**验收：** 对一个跨文件需求，界面上能看到独立于最终文字回复的 Plan 面板，列出两个以上步骤，且步骤内容与 Agent 随后实际执行的工具调用大致对应（允许人工目测核对，不要求自动化一致性检验）。

---

## 阶段3：自动修改与验证闭环

**亲手可见：** 针对靶场仓库里一个明确的小需求，Agent 生成补丁、先做"能否干净应用"的校验、应用到隔离副本后自动跑测试，测试结果（通过或失败的具体报错）如实展示在界面上，不伪装成功。

**主要文件：**
- 新增 `backend/herta_agent/tools/coding/apply_patch.py`
- 新增 `backend/herta_agent/tools/coding/run_tests.py`
- 新增 `backend/tests/test_coding_tools_write.py`

**工作：**
- [x] `apply_patch` 接收 unified diff，先在内存/临时区做"能否干净应用"的检查（拒绝冲突、拒绝目标路径超出白名单），校验通过才实际写入隔离副本；返回结构包含应用前后的文件差异摘要
- [x] `run_tests` 在隔离副本内跑 `pytest` 子进程，复用 `ToolExecutor` 已有的 per-tool timeout；返回结构包含通过/失败用例数与失败详情（不截断关键报错信息）
- [x] 明确隔离边界：写操作只作用于阶段1配置的仓库根目录下的一个专用 worktree（例如 `<repo_root>/.coding-agent-workspace/`），不得写入该目录之外的任何路径，也不得触碰 `.git` 内部对象
- [x] 先写"patch 冲突时拒绝且不写盘""测试失败时原样展示报错""测试通过时展示准确的通过数"三类测试

**验收：** 对靶场仓库提出一个具体小需求（例如"给某个函数增加一个边界条件检查"），能在界面上依次看到 Plan → 补丁生成 → 校验通过 → 应用 → 测试通过的完整链路；额外构造一个必然导致测试失败的需求，确认失败信息被如实展示，没有出现"测试通过"的误报。

---

## 阶段4：调试辅助评测集

**亲手可见：** 针对预先埋入靶场仓库副本的一个已知 bug，Agent 能给出诊断（文件、行号范围、病因描述）和对应修复补丁；诊断的准确性与补丁是否让失败测试转为通过，分开判断。

**主要文件：**
- 新增 `evals/coding/bugs/`，每个 bug 一个独立目录，包含：注入 bug 后的代码状态、一个能复现问题的失败测试、一份人工标注的 ground truth（应定位到的文件与行号范围、病因一句话描述）
- 新增 `evals/coding/run_debug_eval.py`（人工核对辅助脚本，本阶段不要求全自动打分）

**工作：**
- [x] 在靶场仓库副本上人工构造 10–15 个已知 bug，覆盖边界条件错误、逻辑判断取反、变量未初始化、异常处理遗漏等常见类型，每个配一条能复现的失败测试
- [x] 为每个 bug 写 ground truth 标注（文件路径、行号范围、病因描述）
- [x] 复用阶段1/3已有工具（`read_file`/`grep_code`/`run_tests`），不新增专门的"调试工具"，调试能力体现在 Agent 如何组合调用已有工具
- [ ] 诊断输出与 ground truth 的比对本阶段先做人工核对，记录命中/未命中，不强求自动化评分公式

**验收：** 至少 3 个预埋 bug 的诊断文件路径与 ground truth 一致，行号范围有重叠；对应修复补丁应用后，原本失败的测试转为通过。

---

## 阶段5：代码评审模式

**亲手可见：** 给一个包含人为埋入问题（风格问题、潜在 bug、缺测试等）的 diff，Agent 输出分类的评审意见；给一个干净的 diff，Agent 不应编造问题。

**主要文件：**
- 新增 `backend/herta_agent/service/review_mode.py`（或在现有 `Agent` 构造时切换只读工具集 + 独立 system 设定，具体实现方式在动手前先确认）
- 新增 `evals/coding/reviews/`，包含 5–8 个标注过问题的 diff 样本与 3–5 个干净 diff 样本

**工作：**
- [x] 评审场景复用 `agent.run` 循环本身，只切换工具集为只读组合（`read_file`/`grep_code`，可选 `git_diff` 只读封装）与专门的评审 system 设定
- [x] 评审输出要求结构化分类（风格规范 / 潜在 bug 或边界条件 / 缺失测试），而不是一段笼统点评
- [x] 先写"评审输出必须包含分类字段"的行为测试，再实现

**验收：** 标注过问题的 diff 样本中，评审结果至少命中一部分已知问题；干净 diff 样本上评审结果不产生编造的问题（允许合理的风格建议，但不能报告不存在的 bug）。

---

## 五个阶段之外，明确不做的事

- 不构建"多 Agent 共享 Workspace 壳"的通用抽象。
- 不实现 Git 提交/合并到正式分支的能力，写操作严格限制在隔离副本内。
- 不为诊断/评审做自动化打分公式，本轮以人工核对为准。
- 不修改 `persona`、`search_knowledge`、`rag/` 中面向角色陪伴场景的现有逻辑。

## 2026-09-26 已确认的实施决定
- 代码上下文使用通用 coding system context + 模型主动调用文件/目录/关键词工具，不增加代码 Embedding。
- run_tests 沿用现有 unittest，不引入 pytest。
- 本阶段 run_tests 不提供操作系统级隔离，仅限执行仓库自身可信代码，后续若靶场扩展到不可信代码需重新设计。
- 通过启动环境变量选择 coding/review；review 使用只读工具集和独立 system context，复用现有 Agent Loop。

## 本次交付状态（2026-09-26）
五阶段工程已实现，见 coding-agent-walkthrough.md 和 coding-agent-progress.md。勾选表示实现/离线检查完成，不代表每段真实模型验收已经完成；阶段4至少3个模型诊断命中与修复、阶段5真实模型评审效果仍待手工记录，阶段0 Settings 未实施。
