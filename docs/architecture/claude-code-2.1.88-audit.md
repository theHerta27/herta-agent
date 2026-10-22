# Claude Code核心机制：固定版本源码对照

日期：2026-10-22。只读研究，用于Herta独立实现的设计解释；不复制上游非开源代码，不运行其Runtime，不声称本项目复刻了全部Claude Code。

交付更新：Herta真实模型任务、独立安装与恢复已在后续阶段验证，见[CLI v1验收](../verification/cli-v1-20261022/verification.md)。下列源码研究边界保持不变。

## 查阅版本与可信边界

| 材料 | 本轮实际固定的信息 |
|---|---|
| [官方机制文档](https://code.claude.com/docs/en/how-claude-code-works) | 2026-10-22读取；滚动网页，没有可核实的本次Git提交SHA，不把今天文档全部当作2.1.88行为 |
| [Source Map镜像](https://github.com/Hyper66666/claude-code-sourcemap/tree/554bc4514ebaf83ef54d95bc44f4add7272d4f46) | 提交`554bc4514ebaf83ef54d95bc44f4add7272d4f46`，Git提交日期2026-03-31；其package/package.json声明@anthropic-ai/claude-code 2.1.88。提交SHA与包版本分别记录 |
| [Python学习实现](https://github.com/shareAI-lab/learn-claude-code/tree/ce8f9f186058939da54c9d6fead78dfb5d0fd6c3) | 提交`ce8f9f186058939da54c9d6fead78dfb5d0fd6c3`，Git提交日期2026-09-28；读取s01/s03/s08关键函数及MIT LICENSE。不是Claude Code原始Python版本 |

24份选定文件保存于Git忽略的`.local/v1-audit-20261022/`，逐份核对Git blob SHA、SHA256及固定文件树；其中4份仅缓存、不作行为结论。清单在[来源证据](../verification/v1-audit-20261022/source-evidence.json)。缓存没有进入产品源码或发布目录。

该核对只能证明缓存与指定镜像提交的字节一致；本轮未下载并逐字比对完整npm原始归档/60MB source map，不能保证镜像等于完整内部源码仓库。未构建运行上游；query.ts含bun:bundle与feature门控，源码里存在的分支未必在公开二进制启用。useCanUseTool.tsx还包含React compiler生成代码，不能称所有文件都是未经变换的手写原文。初次按.ts查找该Hook返回404，之后按完整文件树的.tsx实际路径读取成功，不是缺文件。

## Agent Loop：谁组织输入，谁反复执行

直觉：外层负责接收这一次任务、维护会话；内层负责反复“问模型、执行工具、带结果再问”。

本轮静态追踪的真实路径：

1. [`QueryEngine.ts:submitMessage`，209行](https://github.com/Hyper66666/claude-code-sourcemap/blob/554bc4514ebaf83ef54d95bc44f4add7272d4f46/restored-src/src/QueryEngine.ts#L209)整理输入/状态并包裹权限回调，在675行调用query；这里querySource明确为sdk，不能据此断言所有交互式终端入口都必经QueryEngine。
2. [`query.ts:query/queryLoop`，219/241行](https://github.com/Hyper66666/claude-code-sourcemap/blob/554bc4514ebaf83ef54d95bc44f4add7272d4f46/restored-src/src/query.ts#L219)通过异步生成器产出事件和消息；queryLoop在307行进入while循环，维护跨步state。
3. [`query/deps.ts:productionDeps`，33行](https://github.com/Hyper66666/claude-code-sourcemap/blob/554bc4514ebaf83ef54d95bc44f4add7272d4f46/restored-src/src/query/deps.ts#L33)把callModel接到queryModelWithStreaming，microcompact/autocompact接到对应服务；query.ts:659调用deps.callModel。函数实现本身的全部网络路径本轮未展开。
4. 模型产生工具块后，query.ts:1380选择StreamingToolExecutor的剩余结果或runTools；1396附近将结果标准化为API所需消息。1716行将messagesForQuery、assistantMessages、toolResults合成下一轮state；1705附近检查maxTurns。没有后续工具需求的正常路径返回completed，同时还存在Hook、预算、错误恢复等其他分支。

Herta对应：`cli.chat/run_turn → Agent.run → ContextEngine.prepare → Provider.complete → ToolExecutor.execute → MemoryTurn/Session → 下一步`。我们保留唯一循环、步数上限、调用/结果配对与错误反馈；当前CLI非流式、工具顺序执行，不搬入上游UI状态、并发/流式工具调度和复杂继续条件。TypeScript的`async function*`可以先理解为Python异步生成器：执行过程中逐项yield消息，而非一次返回整个任务结果。

## Tool与Permission：工具描述、调度与允许执行分开

| 真实文件/关键符号 | 已读片段确认的职责 |
|---|---|
| [`Tool.ts:Tool/findToolByName`，362/358行](https://github.com/Hyper66666/claude-code-sourcemap/blob/554bc4514ebaf83ef54d95bc44f4add7272d4f46/restored-src/src/Tool.ts#L358) | 工具契约含inputSchema、call、checkPermissions、isConcurrencySafe等；按名称查找实例。类型定义本身不会执行工具 |
| [`services/tools/toolOrchestration.ts:runTools/partitionToolCalls`，19/91行](https://github.com/Hyper66666/claude-code-sourcemap/blob/554bc4514ebaf83ef54d95bc44f4add7272d4f46/restored-src/src/services/tools/toolOrchestration.ts#L19) | 按isConcurrencySafe分组，安全批次并发，其余串行；两条路径都到runToolUse，并不等于所有工具统一并行 |
| [`services/tools/toolExecution.ts:runToolUse`，337行](https://github.com/Hyper66666/claude-code-sourcemap/blob/554bc4514ebaf83ef54d95bc44f4add7272d4f46/restored-src/src/services/tools/toolExecution.ts#L337) | 查找工具、检查取消；streamedCheckPermissionsAndCallTool(492)委托checkPermissionsAndCallTool(599)，处理参数、权限、调用及结果；未知工具返回带调用ID的错误结果 |
| [`services/tools/toolHooks.ts:resolveHookPermissionDecision`，332行](https://github.com/Hyper66666/claude-code-sourcemap/blob/554bc4514ebaf83ef54d95bc44f4add7272d4f46/restored-src/src/services/tools/toolHooks.ts#L332) | 调和Hook决定与普通权限。无Hook决定的正常分支在423行调用传入的canUseTool；不能简写成“任何Hook允许都直接执行” |
| [`hooks/useCanUseTool.tsx:useCanUseTool`，28行](https://github.com/Hyper66666/claude-code-sourcemap/blob/554bc4514ebaf83ef54d95bc44f4add7272d4f46/restored-src/src/hooks/useCanUseTool.tsx#L28) | 已读交互式权限回调路径在37行调用hasPermissionsToUseTool（除显式forceDecision情况），之后处理允许/交互等结果。不同入口可以注入不同canUseTool，不能把此Hook硬连为QueryEngine全部场景的固定实现 |
| [`utils/permissions/permissions.ts:hasPermissionsToUseTool/hasPermissionsToUseToolInner`，473/1158行](https://github.com/Hyper66666/claude-code-sourcemap/blob/554bc4514ebaf83ef54d95bc44f4add7272d4f46/restored-src/src/utils/permissions/permissions.ts#L1158) | 综合deny/ask规则、tool.checkPermissions与运行模式，返回allow/deny/ask；外层还有dontAsk及feature门控的其他处理，不是操作系统隔离 |
| [`services/tools/StreamingToolExecutor.ts:executeTool`，265行](https://github.com/Hyper66666/claude-code-sourcemap/blob/554bc4514ebaf83ef54d95bc44f4add7272d4f46/restored-src/src/services/tools/StreamingToolExecutor.ts#L265) | 320行仍委托runToolUse；流式调度入口不会因此跳过统一执行检查 |

普通无Hook决策路径可概括为：`runTools → runToolUse → streamedCheckPermissionsAndCallTool → checkPermissionsAndCallTool → schema/值校验 → resolveHookPermissionDecision → 注入的canUseTool → 权限决定 → tool.call`。toolExecution.ts:995在非allow时返回错误结果，1207行才调用tool.call；拒绝不是让模型自己遵守一句提示。

Herta对应：ToolSpec的Pydantic参数模型/handler对应工具契约，Registry生成Schema；Executor按本次参数校验并调用TerminalApproval，确认后才运行handler。保留Read指纹、真实预览、逐次确认和结构化错误；简化为read_only/side_effect，不照搬上游多权限模式、Hooks、并发工具执行或字符串命令黑名单。已有目录校验约束内置工具；Python测试进程仍拥有当前用户权限，不称沙箱。

## Context：控制本次请求，保留任务继续所需的信息

直觉：历史档案和本次摆上工作台的材料可以不同；压缩还要留下当前任务、关键决定及工具协议的连续性。

本轮确认的调用关系：

1. `query.ts:365`调用[`utils/messages.ts:getMessagesAfterCompactBoundary`，4643行](https://github.com/Hyper66666/claude-code-sourcemap/blob/554bc4514ebaf83ef54d95bc44f4add7272d4f46/restored-src/src/utils/messages.ts#L4643)选择最后压缩边界后的视图；还有按feature启用的snip视图。
2. query.ts:414/454依次调用deps.microcompact/deps.autocompact。productionDeps分别接到microcompactMessages/autoCompactIfNeeded；microCompact内部实现本轮未展开，不凭函数名宣称已完整理解其缓存策略。
3. [`services/compact/autoCompact.ts:autoCompactIfNeeded`，241行](https://github.com/Hyper66666/claude-code-sourcemap/blob/554bc4514ebaf83ef54d95bc44f4add7272d4f46/restored-src/src/services/compact/autoCompact.ts#L241)先检查禁用、连续失败熔断及shouldAutoCompact，再尝试session-memory路径，之后可调用compactConversation。阈值分支见shouldAutoCompact(160)；不能把所有分支写成必定执行。
4. [`services/compact/compact.ts:compactConversation`，387行](https://github.com/Hyper66666/claude-code-sourcemap/blob/554bc4514ebaf83ef54d95bc44f4add7272d4f46/restored-src/src/services/compact/compact.ts#L387)准备摘要请求并调用streamCompactSummary(1136)。后者含runForkedAgent共享缓存路径及queryModelWithStreaming回退路径(1292)，不是简单截取旧文字。
5. [`buildPostCompactMessages`，330行](https://github.com/Hyper66666/claude-code-sourcemap/blob/554bc4514ebaf83ef54d95bc44f4add7272d4f46/restored-src/src/services/compact/compact.ts#L330)组合边界、摘要、保留消息、附件与Hook结果；query.ts:528采用该结果继续。`utils/messages.ts:normalizeMessagesForAPI`(1989)承担API消息整理，本轮仅查阅相关入口与配对/边界片段，没有逐分支审计整个193KB文件。

Herta对应：ContextSettings与ContextEngine.prepare按本机词面估算预算，保留完整用户轮次和工具配对；_summary为extractive-v1程序摘取。Session原文不删除，当前必需内容过大则ContextError。这是明确的小范围实现，不是上游语义压缩、上下文溢出自动恢复或精确Token计费。v1先验证边界，不为源码功能数量增加模型摘要调用。

## Python学习实现如何辅助，而不替代上游

- [`s01_agent_loop/code.py:agent_loop`，96行](https://github.com/shareAI-lab/learn-claude-code/blob/ce8f9f186058939da54c9d6fead78dfb5d0fd6c3/s01_agent_loop/code.py#L96)：反复调用模型、提取tool_use、执行并回填tool_result。用于理解循环，不能替代Herta已有取消、步数、参数和Session契约。
- [`s03_permission/code.py:check_permission/agent_loop`，201/217行](https://github.com/shareAI-lab/learn-claude-code/blob/ce8f9f186058939da54c9d6fead78dfb5d0fd6c3/s03_permission/code.py#L201)：通过拒绝列表、规则与用户交互演示权限层。不将字符串黑名单当作操作系统保护，也不将其默认允许策略替换Herta当前逐次副作用确认。
- [`s08_context_compact/code.py:ContextCompactor/prepare/compact_history`，254/516/498行](https://github.com/shareAI-lab/learn-claude-code/blob/ce8f9f186058939da54c9d6fead78dfb5d0fd6c3/s08_context_compact/code.py#L498)：展示工具结果持久化、节录、模型摘要和超限重试。仅作概念对照，本轮没有运行、复制或移植。

本轮未追踪所有UI入口、所有权限模式、内部服务端行为或全部编译门控。已查阅文件与函数不代表实际启用了这些能力。面试资料沿上面三个主题讲清“真实上游路径 → Herta对应代码 → 为什么简化 → 实际验证”，而非声称读完全部源码。
