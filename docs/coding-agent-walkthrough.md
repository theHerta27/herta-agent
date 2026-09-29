# Coding Agent：运行与验收

实现工作树为 `D:\Desktop\herta-agent-coding`，分支 `coding-agent`。原 `D:\Desktop\herta-agent` / `phase-6-ui` 保留角色陪伴功能。本轮不实施 Settings，不提交/合并到目标仓库。

## 启动

先按 README 安装 Python/Node 依赖，以及新增的 **Docker Desktop（Linux containers）**。
`uv sync --project backend --extra dev --locked` 安装固定的 pytest 9.0.2 与 pytest-json-report 1.5.0。
本工作树 `.venv` 已改指向独立环境，未向原 phase-6-ui 的 Python 环境安装新依赖。

构建镜像（仅依赖变化时重建；测试运行时不会自动构建或联网拉取）：

```powershell
cd D:\Desktop\herta-agent-coding
$env:HERTA_CODING_REPO_ROOT = "$PWD"
./scripts/build-coding-sandbox-image.ps1
```

脚本默认读取本靶场 `backend/pyproject.toml` 及相邻 `uv.lock`，可通过 `-RepoRoot`、
`-DependencyFile`、`-DependencyExtra`、`-Image` 指定另一靶场。当前支持 uv 锁定的 Python
依赖；新靶场必须在自己的依赖中包含固定版本 pytest/JSON 插件，不能直接假设复用 Herta
镜像。非 Python 靶场或不同依赖系统需要另行适配构建步骤。
自定义镜像同时设置 `$env:HERTA_CODING_SANDBOX_IMAGE='镜像名:标签'`。

关闭此工作树已有窗口，在同一个 PowerShell 中设置聊天环境并启动：

```powershell
cd D:\Desktop\herta-agent-coding
$env:HERTA_SERVICE_PROVIDER = 'openai'
$env:HERTA_BASE_URL = 'https://你的聊天服务/v1'
$env:HERTA_MODEL = '支持流式工具调用的模型'
$chatSecret = Read-Host 'Chat Key' -AsSecureString
$env:HERTA_API_KEY = [System.Net.NetworkCredential]::new('', $chatSecret).Password
Remove-Variable chatSecret
$env:HERTA_CODING_REPO_ROOT = 'D:\Desktop\herta-agent-coding'
$env:HERTA_CODING_MODE = 'coding'
npm --prefix frontend run dev
```

dev 默认选取本工作树整个仓库。选择整个仓库是因为现有 backend 测试还依赖根目录 Persona、knowledge 和 evals；仅复制 backend 不能承诺原测试全部通过。测试工具显式使用 `path="backend/tests"`；小靶场默认 `tests`。

启动会首次创建 `<HERTA_CODING_REPO_ROOT>/.coding-agent-workspace` 源码副本。以后重开不会覆盖它；读工具、补丁与测试均指向同一副本。修改没有自动回写源代码。若要刷新基线，先关闭服务，再手动移走旧副本并重开；应用不会替你销毁已有改动。排除 `.git`、依赖、环境、`.env*` 和工作副本等目录；文件内容会经工具返回发送给配置的聊天服务，不发送到 Embedding 服务。

单次最多复制 10000 个文件/100MB；补丁只支持 UTF-8 文本的新增、修改、删除，使用严格 unified diff，不支持模糊匹配、二进制、重命名或文件模式变更。全补丁先校验再写盘。read_file 与 grep_code 明确返回截断/跳过信息；可缩小范围继续读取。

`run_tests` 只执行 Docker 容器内的 pytest；`apply_patch` 仍在宿主执行确定性的副本
写入。容器只挂载 `.coding-agent-workspace`，无网络、非 root、只读系统盘，限制 1GiB
内存、2 CPU、128 PID；不挂 Docker socket 或真实源仓库。取消/超时后显式 kill、rm
并检查该唯一容器名；清理期间保留工作副本锁。Docker/镜像不可用时明确报错。

每次启动容器有额外延迟，暂不做容器池。stdout 超过 64KB 或 JSON 超过 4MB 明确报错，
不会截断后冒称通过。总数按测试方法/函数计算，失败 subTest 归到父方法，跳过的
subTest 单独计数；每条用例及子测试保留结构化证据。`ok=true` 只表示工具执行完成；
测试通过还需 `status=passed`、非零测试数及正常退出，矛盾报告拒绝判通过。

此前“本阶段 run_tests 不提供操作系统级隔离，仅限执行仓库自身可信代码，后续若靶场
扩展到不可信代码需重新设计”属于迁移前约定。当前已改为 Docker 执行，但**真实 Docker
验收尚未完成**，不可把实现参数当作已验证的隔离效果，也不承诺能抵御所有恶意代码。

## 离线检查与 Docker 验收

```powershell
$env:PYTHONPATH = "$PWD\backend"
.\.venv\Scripts\python.exe -m pytest backend/tests -q -rs
.\.venv\Scripts\ruff.exe check backend
.\.venv\Scripts\ruff.exe format --check backend
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend test
```

Docker 就绪并构建镜像后：

```powershell
$env:HERTA_DOCKER_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest backend/tests -q -rs
.\.venv\Scripts\python.exe -m pytest backend/tests/integration -q -rs
.\.venv\Scripts\python.exe evals/coding/run_debug_eval.py --verify-fixtures
npm --prefix frontend run test:e2e
```

这组命令不调用真实 LLM。宿主 pytest 是开发者启动的回归检查；Agent 的 `run_tests`
始终只走容器。调用 `run_tests` 的集成用例不能在同一沙箱里递归启动 Docker；
`HERTA_SANDBOX=1` 下明确跳过，另从宿主驱动生产执行器验证。原 195 项测试文件不改写；
其中 3 项绑定旧“本地 PID/2 秒”契约的测试由新的 Docker 结果/超时/取消集成测试接替，
保留原文件并明确跳过。替代集成测试真正跑通之前，这部分覆盖仍记待验收。
Windows 路径、symlink、进程与 socket 用例的 Linux 容器兼容性也仍待实测。

**完成迁移三个阶段与完整离线复验后，才能开始下面的真实模型验收。**

## 五个阶段的手工检查

1. **代码理解**：问“ToolExecutor.execute 在哪个文件里定义？它如何处理超时？请先查代码并引用行号。”展开工具活动核对 grep_code/read_file 的文件与行号。
2. **规划**：提出一个小的跨文件修改，要求先 propose_plan。展开活动可见独立的待执行清单；清单没有伪造完成状态。
3. **修改/验证**：建议先使用下面的迷你靶场。在副本上让模型修复已知失败测试，观察 Plan → read_file → apply_patch → run_tests。界面明确区分测试失败与通过。确认原文件不变，副本有 diff；再故意改错验证失败信息。
4. **调试**：`evals/coding/bugs` 有10个独立可信源码样本，覆盖边界、逻辑反转、未初始化、异常遗漏等。ground_truth 与参考补丁放在样本 src 外，避免被当作源码工具直接读取。各样本在旧后端已核对失败→参考修复通过；新 Docker 后端必须重新核对，当前待验收。这不等于模型诊断通过。
5. **评审**：完全关闭应用，设置 `$env:HERTA_CODING_MODE='review'` 再启动。仅有 read_file/grep_code/list_directory/submit_review，无 apply_patch/run_tests。正式分类意见经 submit_review 校验并持久显示；模型只输出普通文字而未调用它时，不算结构化评审验收完成。

## 准备调试靶场

```powershell
$env:PYTHONPATH = "$PWD\backend"
.\.venv\Scripts\python.exe evals/coding/run_debug_eval.py --case evals/coding/bugs/01-boundary --output .local/debug-trials
$env:HERTA_CODING_REPO_ROOT = "$PWD\.local\debug-trials\01-boundary"
$env:HERTA_CODING_MODE = 'coding'
npm --prefix frontend run dev
```

准备命令输出初始失败信息。给模型提供 ground_truth 中的行为约定（例如18岁算成年），不要提供病因和参考补丁；要求其读取、运行测试、先给诊断，再修复。记录实际诊断的 `path/start_line/end_line/cause`。至少3个样本路径命中、行号重叠且失败转通过，才满足阶段4模型验收。

辅助核对可用新 output 目录，并通过 `--diagnosis <实际诊断.json> --patch <模型补丁.diff>` 传入结果；脚本分别报告定位是否重叠与测试前后结果，病因仍人工核对。`--verify-fixtures` 只验证10个参考补丁，不是模型评测分数。

## 评审样本

`evals/coding/reviews` 含5个有标注问题的 diff、3个干净 diff，各有 brief、base 与 expected。先将一个样本的 base.py 复制到可信靶场的 subject.py，再把 brief 和 change.diff 提交给 review 模式。对照 expected 人工记录分类、定位和解释；干净 diff 不应虚构 bug。expected 不要放入模型可读靶场。

## 当前验收边界

离线 Electron 测试使用明确的 Scripted Provider，走真实 FastAPI、同一 Agent Loop、工具、SQLite 和测试执行器；证明代码装配与 UI 闭环，不证明真实模型推理能力。本轮没有调用真实模型或 Embedding API。阶段4的“至少3个模型诊断命中并修复”、阶段5真实模型在问题/干净 diff 上的效果仍需实际服务配置后手工验收。此前角色 RAG 的通过记录不适用于代码诊断或评审。

Settings 前置任务仍未实施，不将当前状态称为正式对外演示验收全部完成。

迁移前离线结果（历史记录）：后端195项、前端24项、真实Electron 10项通过；typecheck、lint、build、Ruff check/format、diff check通过。工具在本项目副本里运行195项测试也通过；首次并行执行遇到两项既有时序测试失败，单独复核通过，过程保留在执行记录。

当前 pytest/Docker 迁移的新结果和待验收项目见 `run-tests-sandbox-plan.md`；不沿用上面的旧成绩宣称迁移通过。
