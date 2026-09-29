# run_tests：pytest + Docker 迁移

本计划先于五阶段真实模型验收；沿用 coding-agent 分支及当前工作树。

1. 将本地执行改为 pytest + pytest-json-report，固定依赖版本，保留 unittest
   测试内容；先测 JSON、路径与空收集，再实现。实测 subTest 计数，记录 Windows 依赖。
2. 仅 run_tests 改为 Docker 执行；非 root、无网络、资源上限，只挂载隔离副本。
   镜像按靶场依赖文件构建及哈希复用。启动检测，不可用明确拒绝，不回退本地。
   唯一容器名；超时/取消显式 kill 并清理。真实 Docker 测试独立报告。
3. 重跑后端、前端、Electron、10 个参考修复及涉及执行的评审样本；记录真实数字、
   限制和 Ruling。未完成迁移与复验前，不调用真实模型。

不修改其他 Coding Tools、Agent Loop、Persona、RAG 或 Store 语义。
Docker Desktop 为新增前置依赖；暂不优化容器启动延迟，不引入容器池。

## 执行记录

- 基线：195 后端测试，24 前端测试，10 Electron 测试（此前离线记录）。
- 已保留迁移前所有 test*.py 的 SHA256，供验证旧测试未改写。
- 环境预检：未找到 Docker CLI 或默认路径 Docker Desktop；已请用户准备环境。
- 当前 .venv 是原项目环境的 junction。本次先使用 .local/pytest-venv 独立环境，
  避免依赖安装污染原项目。
- Ruling：全量测试中调用 run_tests 的测试属于宿主机 Docker 集成测试，不能在沙箱
  内挂 Docker socket 进行嵌套测试；普通测试在容器内运行，这部分另列宿主集成验证。
  代价：容器内的单次通过数不能直接等同全部 195，必须报告分项覆盖。
- 接口依赖：阶段 1 JSON 结果供阶段 2 原样解析；阶段 2 的容器命令/清理与阶段 3
  的真实 Docker 验收共用生产路径，不把 mock 通过当成容器隔离通过。
- 阶段 1 RED：6 个新增行为测试中 5 个按预期失败（缺 JSON 详情/空收集处理/
  报告验证），路径缺失已有明确错误。GREEN：新增测试 + 原写工具测试 13 项通过。
- pytest 迁移前实际收集 195 方法、146 subTests，全部通过；迁移后 201 方法、
  149 subTests 全部通过（48.77 秒）。一次输出暂未刷新被误判为停滞，之后取回
  完整正常退出结果；没有修改既有时序测试。
- subTest 实测：pytest-json-report 1.5.0 会丢子测试细节并将子测试跳过投射到
  方法 outcome。添加小型 pytest 报告 hook 保留每条子测试证据，按方法汇总。
- Windows/容器差异清单：test_coding_tools_readonly 的 Windows 路径和 symlink；
  test_coding_context 的盘符/SystemRoot；test_coding_tools_write 的宿主 PID 检查
  与 2 秒本地时限；test_coding_evals 会嵌套调用执行器。前三者需明确容器/宿主
  语义差异，后两者属于宿主集成验证。service_integration/CLI 使用子进程与
  loopback socket，看起来可跨平台，但未实际 Linux 容器验证前不作通过声明。
- 阶段 1 生产工具在完整源码副本执行 backend/tests：status=passed、exit_code=0、
  total=201、passed=201；真实失败/跳过/subTest 详情验证通过。原 195 项文件哈希未变。
- Ruling：保持旧测试文件内容，3 项旧本地 PID/2 秒执行契约通过 conftest 显式跳过，
  用新的真实 Docker 结果、超时、取消集成测试接替。代价：新 Docker 验收完成前，
  这 3 项不能算有已验证的等价覆盖。调用测试工具的测试只能在宿主驱动，不能递归
  在沙箱启动 Docker，更不能为通过测试挂载 Docker socket。
- Ruling：ToolExecutor 只新增 ContextVar 传递 tool_call_id（finally 恢复），不改变
  handler 或模型参数接口。用于唯一容器名关联当前 tool call；代价是执行边界多一处
  身份上下文维护，已覆盖恢复与唯一性行为。其他 Coding Tools 实现未修改。
- Docker 命令、缺依赖拒绝、启动检查的 RED→GREEN 已完成；镜像脚本在 PowerShell
  7 / Windows PowerShell 5.1 的模拟 CLI 边界下，首次构建→复用→依赖改变重建通过。
  这不等于真实镜像已构建；实际 Docker 尚不可用。
- 一次独立审查返回两项 Important：清理中取消可打断回收；JSON 自相矛盾可误报成功。
  均新增失败测试后修复（清理任务 shield 并保留锁直到结束；逐条证据/汇总一致性校验）。
  审查随后因服务用量限制中断，没有取得完整最终结论，不能宣称独立审查全部完成。
- 待验收：真实 Docker 镜像构建/复用、普通后端测试容器内运行、网络限制、非 root、
  超时与取消后的 docker ps 清理、10 个调试参考补丁、Electron coding-flow。
  8 个评审样本本身没有 run_tests 执行脚本，readonly/submit_review 原回归继续运行；
  真实模型评审成绩仍待五阶段验收，不能用结构校验替代效果评估。

## 本轮最终离线结果（2026-09-27）

| 执行路径 | 实际结果 | 含义 |
| --- | --- | --- |
| 迁移前原测试由 pytest 调用 | 195 passed，146 subtests passed | 确认无需改写旧测试 |
| 阶段 1 本地 pytest + 新测试 | 201 passed | 包含 6 项新增行为测试 |
| 阶段 1 run_tests 完整副本自测 | 201/201 passed，exit_code=0 | 工具实际执行与 JSON 解析通过 |
| Docker 实现后的宿主离线回归 | 199 passed，11 skipped，153 subtests passed | 含审查修复，跳过不算通过 |
| 前端 unit | 24 passed | typecheck/lint 同时通过 |
| Electron 离线 E2E | 9 passed，1 skipped | coding-flow 缺真实 Docker，未验收 |
| Ruff check / format / diff check | 通过 | 原 195 项测试文件 SHA256 全部保持不变 |

11 项跳过：3 个真实 Docker 安全/生命周期集成测试、1 个聚合 10 样本核对测试、
4 个生产 pytest 执行行为测试、3 个已被替代但保留的旧本地执行契约。
Docker 镜像仍未真实构建，容器下通过数没有可报告结果。

当前状态：阶段 1 完成；阶段 2 代码已接入但实机验收未完成；阶段 3 仅完成不依赖
Docker 的检查，完整复验未完成。独立审查尚无完整最终结论（见上）。
没有真实模型/Embedding 调用，没有提交、push、merge。下一步需要本机安装并启动
Docker Desktop Linux containers，然后构建镜像并继续上述待验收清单。
