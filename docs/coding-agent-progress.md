# Coding Agent 执行记录
计划：docs/coding-agent-pivot-plan.md
基线：81a1d740f7b92a6124dc0f29773b417af6b606f6
工作树：D:/Desktop/herta-agent-coding，分支 coding-agent；原工作目录/分支保持不变。
Ruling: 使用独立 linked worktree 实施，复用已安装依赖（只读 junction），PYTHONPATH 指向新 backend；不复制或升级依赖。
Ruling: 原 service 在未设置 coding root 时保留旧装配以保留回归；设置 HERTA_CODING_REPO_ROOT 后切换开发工具和代码上下文，不改 Runtime/Store/SSE。
Ruling: 阶段3统一读取与写入同一个源码副本，防止读取原文件却修改另一个文件；副本在 root/.coding-agent-workspace，持久保存，不自动覆盖。
Ruling: 用户确认使用工具检索、unittest 和启动时选择 review；不新增 Embedding 或 UI 模式切换。
前检：阶段1路径检查供阶段3补丁复用；阶段2结果由普通工具消息持久化；阶段3测试结果供阶段4验收；阶段5只读注册表不含写工具。
阶段0 Settings 不在本次范围。真实模型/Embedding API 不由自动测试调用；模型能力评测与离线工具闭环验证分别记录。

阶段1：路径/读取/搜索测试先失败后通过；185项后端（含后续配置装配检查）保留原有179项。
阶段2：计划结构与前端列表测试先失败后通过；前端23项测试通过，不将计划提议标记为完成。
阶段3：冲突不写盘、源文件不变、真实失败/通过计数、超时及取消回收测试先失败后通过；全量后端190项通过。
Ruling: 补丁限严格 UTF-8 unified diff（新增/删除/修改），无模糊应用、rename或binary；测试输出超过64KB明确报错并终止，要求缩小范围，不截断后冒称通过。

阶段4工程：10个已知缺陷样本，全部初始失败→参考修复通过（并非模型成绩）；有手工诊断路径/行号与测试结果分开的辅助脚本。
阶段5工程：review注册表仅只读工具和结构化submit_review；分类字段校验/空意见测试通过。5个问题diff与3个干净diff样本已准备。
Electron离线闭环：coding-flow通过，真实窗口展示只读工具、计划、成功补丁、真实测试先失败后通过、故意破坏后失败、review只读投影；未调用真实API。
Ruling: 默认靶场为整个本工作树而非仅backend，因为测试依赖根目录persona/knowledge/evals；代价是副本更大，run_tests需path=backend/tests。
Ruling: 调试初版用10个微型可信仓库夹具而非修改实际基础设施；隔离验证更明确，但不能据此推断大型仓库能力。
Ruling: 评审结构化输出用无文件副作用的submit_review工具实现，不修改Agent最终回复协议；模型未调用该工具时不算结构化评审完成。
真实模型验收：阶段4至少3例、阶段5问题/干净diff效果待手工验证，Settings前置也未完成；不能宣称计划所有验收条款已通过。

独立审查：两项Important（subTest计数、删除SQL注释的合法diff）已用RED→GREEN修复。
Ruling: 将仅有diff头却报告applied=true的问题从Minor提升为需修复，因为会误导模型认为修改已落盘；新增独立失败测试后拒绝无文件变更的补丁。
Final: fixed 三项审查问题 — test_subtest_counts_do_not_become_negative、test_patch_sql_comment_hunk、test_header_only_patch_cannot_claim_applied 均RED→GREEN，定向7项通过。
Final: Ruling: 审查未判断的OS沙箱、Embedding、pytest迁移、Settings和UI模式切换按用户确认排除；真实模型质量仍待验收，代价是不具备不可信代码执行安全或完整对外演示保证。

最终验证中：主工作树后端195项通过；前端24项、typecheck/lint通过；完整Electron前轮10项通过，修复后正在复验。
副本自测首次在并行负载下195项中193通过，两项既有时序测试失败（test_crash_restart_repairs_pending_without_reexecution 读到空ready文件；test_post_frames_unicode_order_and_no_replay 未收到终态）。工具正确返回failed/2，待无并行测试时单独复核，不修改原测试掩盖问题。
当前执行进程缺少真实聊天配置，未执行真实模型评测。

最终完整Electron复验：10/10通过（含build，修复后版本）；主工作树后端195/195通过，前端24/24通过；Ruff check/format、typecheck/lint通过。原工作树仍为phase-6-ui，仅原用户计划文件未跟踪，其余未改动。没有提交、push或merge。

副本自测单独复核：run_tests(path=backend/tests) 返回status=passed、exit_code=0、total=195、passed=195、failed=0；此前并行时两项时序失败记录保留。不修改既有测试。报告位于.local/self-workspace-tests-repeat.json（不入库）。

## pytest + Docker 迁移（后续迭代，真实模型验收之前）

Ruling：此前基于"匹配现有测试基建、不引入新依赖"选择 unittest + 本地子进程执行；现基于企业级项目定位的明确目标，改为 pytest 作为测试运行器、Docker 作为 `run_tests` 的执行沙箱；已有测试内容不做风格重写，仅替换执行与解析层。

详见 `run-tests-sandbox-plan.md`。阶段 1 已实际完成：原 195 项由 pytest 收集并通过，
新增测试后 201 项通过；生产 run_tests 在完整隔离副本也返回 201/201。
当前 Docker Desktop/CLI 缺失，阶段 2 实现已接入但真实容器验收未完成；阶段 3 完整
复验未完成，10 个调试样本及 Electron coding-flow 不能沿用旧后端的通过记录。
未调用真实模型或 Embedding API，未使用/保存用户给出的模型 Key，未提交或 push。

2026-09-27 新离线复验：后端 199 passed / 11 skipped（153 subtests passed）；
前端 24 passed；Electron 9 passed / 1 skipped；typecheck、lint、build、Ruff check/format、
diff check 通过。跳过明细与原因见迁移记录，不把这些数字当作 Docker 验收完成。
独立审查已返回的两项 Important 均 RED→GREEN 修复：清理中重复取消不能释放工作副本锁；
JSON 汇总或逐条失败证据矛盾时不能报告通过。审查因服务用量限制中断，完整结论待补。
