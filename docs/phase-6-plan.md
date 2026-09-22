# Phase 6 实施计划：7个可见交付阶段

> 设计与计划已确认。2026-09-22 获授权实施阶段1，现已完成并停止；阶段2–7未开始。实施使用 `superpowers:executing-plans`，每阶段先用关键行为测试确认预期失败，再最小实现与验收。提交/push/merge仍单独按用户授权。

**目标：** 用Electron/React把Phase 5变成可日常聊天、看工具、取消和恢复会话的Windows应用。

**架构：** Main管理一个本机Python子进程并桥接HTTP/SSE，Renderer只维护视图与意图。Python仍是唯一Agent Runtime，SQLite仍是正式消息唯一来源。

**技术：** Electron / React / TypeScript / Vite，CSS Tokens；小型Markdown/图标库按需选；Vitest + React Testing Library做关键行为测试，Playwright做Electron集成。实施时锁定兼容版本，不在规划期安装或生成工程。

**设计依据：** [phase-6-ui-design.md](D:/Desktop/herta-agent/docs/phase-6-ui-design.md)。所有尺寸、状态含义、Settings决策以该文档为准。

## 全局约束与入口

- 完整Phase 5基线已固定为6679dfeda6535d4e33d8e24e7d042d0b5f6f7b84，含Task 10–12。保留用户8张素材，不重生成、不改变最终位置。阶段1直接建立最少工程，不覆盖现有frontend素材。
- 只在用户确认设计/计划并授权实施后建UI分支、安装依赖或编写代码。未来目录使用现有frontend，避免另建apps/desktop造成两套入口。
- 不改Agent Loop、Persona/RAG算法或Store语义；不加Settings热更新/Run重放/队列/鉴权/多用户/第二套后端。
- Main单实例、自管一份loopback单worker后端；开发桌面DB固定为`.local/desktop/sessions.sqlite3`。不会自动搬入旧`.local/sessions.sqlite3`，避免两个服务拥有同一库。
- 只有完整后端消息进入正式UI历史；partial只存在内存。切会话保留连接，断流不自动重发；完成与取消以持久结果为准。
- 用户已确认：可改非敏感Base URL/模型；Key仅读本地环境；无活跃Run时重启自管服务生效。不做密钥输入/保存/日志，也不复制环境到Renderer。
- 本轮不测试真实API。实施自动测试也用显式fixture；真实服务手工验收需用户配置并明确发起。Phase 4真实RAG效果仍待验收。
- 每阶段结束能在Electron窗口亲手验证新增成果；不要求每个CSS值配单测，不重建既有后端178项测试。关键交互/协议/生命周期有行为测试，最终运行全部后端回归。

实施后的统一命令契约（当前尚不存在，阶段1建立）：

```powershell
npm --prefix frontend run dev          # Electron窗口 + Vite + 自管后端
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run test         # 一次性单测，不启动watch
npm --prefix frontend run build        # 构建前端/Main，不制作安装包
npm --prefix frontend run test:e2e     # 明确的离线Electron夹具环境
```

## 关键接口约定（只供将来实现）

`shared/contracts.ts`映射现有SessionRecord/MessageRecord/RunRecord/ServiceEvent，另外单独定义桌面状态，不能混写后端schema。

- 只读/命令桥：`getBackendStatus()`、`listSessions(afterId?, limit?)`、`createSession()`、`getSession(sessionId, afterSeq?, limit?)`、`getRun(runId)`。
- 流意图：`startRun({clientRequestId, sessionId, text})`发起一次请求；`cancelRequest(clientRequestId)`在run_id已知时调用cancel，否则终止本地请求。`onRunEvents(handler)`在App层订阅一次，返回unsubscribe；不暴露任意IPC通道。
- Main把HTTP拒绝、ServiceEvent批次、transportClosed分开通知，带clientRequestId；HTTP成功接纳不能由“本地startRun调用返回”推断。后端POST正文仍只有text。
- 流批次交付后Preload内部回执；Main只保留有界待交付批次，可合并相邻同message_id delta；超量/超时取消相应连接。回执只是传输确认，不是持久化消息确认。
- 设置桥：`getSettings()`只返非敏感生效/草稿值与keyPresent；`applySettings(nonSecretSettings)`在Main串行的空闲/重启临界区中执行，不能和新startRun交叉。`restartBackend()`只作用自管进程。
- Renderer使用App级`chat-store`、纯`run-reducer`及`history-view`；不引入通用事件总线、插件或多层状态框架。组件按props/动作与store交互。

## 阶段1：桌面能启动、连接、退出

**亲手可见：** 一个名为Herta的真实Windows窗口；“正在启动 → 服务就绪/配置未就绪”；关闭后无遗留自管Python，再打开仍能正常连接。先显示最小Welcome文字与禁用输入，不等待全套视觉完成。

**主要文件：** 新建`frontend/package.json`、锁文件、Vite/TS配置、`index.html`、`src/main.tsx`、`src/App.tsx`、`shared/contracts.ts`、`electron/main.ts`、`preload.ts`、`backend-process.ts`、`backend-client.ts`、`desktop/backend_host.py`；测试`tests/unit/backend-process.test.ts`、`tests/e2e/desktop-startup.spec.ts`。

**工作：**

- [x] 先写启动/退出测试：子进程尚未ready不能接纳；缺解释器显示安全错误；收到就绪后health确认；重复启动只激活已有窗口；进程退出不能继续显示就绪。确认缺实现时失败。
- [x] 建立最少工程和安全Preload，开发脚本启动可见Electron，不让用户分别启动两个终端；native title bar，窗口默认1200×800、最小800×600。
- [x] 薄Python host复用现有create_app/ServiceSettings，只增加私有stdio ready/shutdown协议；child绑定port=0后报告实际端口/PID；Main保留真实子进程所有权，shell=false、windowsHide=true、绝对路径。
- [x] 开发DB与资源路径按设计解析；缺聊天配置保持只读就绪状态，不伪装demo。测试选择离线模式使用专属环境/临时DB，不污染用户数据。
- [x] stdin shutdown/EOF请求现有Manager完成清理后停止服务器；Windows启动器与实际进程均纳入退出等待。生命周期错误只显示固定摘要，不输出原环境/启动配置。

**验收：** typecheck/lint、启动定向测试；在中文空格路径、目录外启动和连续启动/关闭3次中实际操作。关闭后检测自己的子进程退出与DB可重新打开；其他Python进程不受影响。此时不修改后端业务代码、不创建新的health/settings API。

## 阶段2：静态布局与小型Design System

**亲手可见：** Welcome半身图、克制Sidebar、对齐的正文与输入区、可切深浅色；正常聊天示例里Hero消失。示例仅在测试/设计预览入口展示，不混入真实历史。

**主要文件：** 新建`src/styles/tokens.css`、`base.css`，`components/AppShell.tsx`、`WelcomeView.tsx`、`ConversationSidebar.tsx`、`ChatHeader.tsx`、`MessageList.tsx`、`Composer.tsx`；修改App；测试`tests/unit/composer.test.tsx`、`tests/e2e/layout.spec.ts`。

**工作：**

- [ ] 先写关键交互断言：组字中的Enter不发送，Shift+Enter换行；停止按钮不因输入禁用而消失；折叠Sidebar后焦点可达。样式用实际视觉验收，不写镜像CSS测试。
- [ ] 按设计Token与780内容宽度布局；只用Hero/avatar/rag-reading三张，Hero留在Welcome，输入区在正常布局中不遮挡消息。
- [ ] 正文16px/1.7；用户轻背景、assistant无外框；本地字体、图标按钮可访问名称；可见focus、减少动画；低窗口高度收缩Hero。
- [ ] Composer自动增长至180，超过后内部滚动；加入字数限制提示；无附件/语音按钮、无假功能入口。

**验收：** 1200×800、1000×700、800×600和Windows125%/150%缩放；长中文/长代码不撑破页面，输入/停止始终可见。Tab遍历、主题切换、图片缺失回退；对照两张截图检查留白和层级，不做像素复制。

## 阶段3：真实Session与History

**亲手可见：** 选择新对话草稿、切换已有会话，Sidebar看到真实历史；退出重开桌面后数据仍在；只读历史不需要模型Key。新对话未发送时不产生空库记录。

**主要文件：** 扩展`electron/backend-client.ts`与桥接类型；新增`src/state/chat-store.ts`、`history-view.ts`、`components/ChatView.tsx`；更新Sidebar/MessageList；测试`tests/unit/history-view.test.ts`、`session-navigation.test.tsx`、`tests/e2e/history.spec.ts`。

**工作：**

- [ ] 先写分页/切换失败测试：>100消息、>50会话、相同文本不同message_id、A请求迟到但已切B；不得丢页、混会话或把加载中当空Session。
- [ ] 按后端真实ID游标取元数据，再按updated_at排序；可见项读取首user作为摘要，最多4并发；暂无摘要用时间/短ID，不加标题API。
- [ ] History按after_seq分页直到末页，消息按ID去重/seq排序，先加载完整再开放发送。用持久run_id读取各轮状态，不从缺少最终assistant猜cancelled。
- [ ] 普通user/assistant进入正文，工具声明/结果先保留结构并显示简洁活动占位，阶段5完善交互。SQLite写入仍只通过现有API完成。
- [ ] 草稿/滚动保存在App级内存；读取失败局部重试，不能让空白页覆盖原历史。保留“新对话”轻量草稿，首次发送才创建Session。

**验收：** 离线fixture通过现有API造两会话与分页历史，切换及重启后逐条核对ID/顺序；用户可以阅读和选择会话。测试数据位于临时桌面DB，不向`.local/desktop`写测试历史。此阶段不承诺模型聊天已接通。

## 阶段4：Chat与真实POST流式传输

**亲手可见：** 发送问题后文字逐步出现，完整回答落入历史；切到另一个Session再切回不会取消；同时两会话执行互不串内容。提供基本停止与断连处理，不能交付无法取消的流式阶段。

**主要文件：** 扩展`backend-client.ts`；新增`src/api/sse-parser.ts`、`state/run-reducer.ts`、`components/AssistantMessage.tsx`、`RunStatus.tsx`；更新store/Composer；测试`tests/unit/sse-parser.test.ts`、`run-reducer.test.ts`、`tests/e2e/chat-stream.spec.ts`及`tests/fixtures/service.py`。

**工作：**

- [ ] 先写真实字节fixture：中文跨UTF-8块、跨帧、注释心跳、重复seq、seq间隔、非200JSON、提前EOF。首段显示时fixture仍被屏障阻塞未结束；拒绝完整文本切字的假流式。
- [ ] Main在已订阅后发一次POST，clientRequestId贯穿首事件前状态；同一次点击/Enter即使React StrictMode也只提交一次。HTTP拒绝恢复草稿，无自动重试POST。
- [ ] partial按run_id/message_id独立，llm.completed用完整消息替换；根据tool_calls区分中间响应。终态GET Run与History校正；pending user按run_id对应正式user，只显示一次。
- [ ] App级事件处理与选中Session分开；切会话不unsubscribe/abort。UI草稿、事实、partial分开，失败/取消/崩溃不会把partial写localStorage或作为下一轮请求字段。
- [ ] 首事件前Stop终止提交，有run_id后调用cancel并等终态；断流进入核对而非成功，不重发POST。超过核对期限仍未知则明确显示，不能提前放行重复发送。
- [ ] Main→Renderer有界批次/回执；delta合并不改变其余事件顺序，退出/销毁清理连接。渲染节流与网络读取分离；上翻不强制跟随，提供回到最新。

**验收：** Unicode流式、两Session、早停/晚停、HTTP409/429/503、断流已提交和未提交两种结果、Renderer重载；普通demo可能一次返回，不把demo称为真实流式模型。阶段末已能聊天和基本取消，阶段5补工具呈现与状态细节。

## 阶段5：Tool/RAG活动与完整Run交互

**亲手可见：** “正在检索角色资料…”→“已检索角色资料”，默认收起；展开后有工具名、Step、query、简化结果和来源。取消/失败/中断各有明确文案，工具失败后模型仍可继续。

**主要文件：** 新建`components/RunActivity.tsx`、`ToolActivity.tsx`、`RunGroup.tsx`；完善RunStatus/MessageList/history-view/run-reducer；测试`tests/unit/tool-activity.test.tsx`、`tests/e2e/tools-cancel.spec.ts`。

**工作：**

- [ ] 先写tool_call_id跨Step重用、tool.failed无started、先已提交结果再取消、completed与cancel竞争、service.error/persisted=false等测试；不得串活动或假称保存成功。
- [ ] 用`run_id + step + tool_call_id`关联声明、参数、结果，参数来自llm.completed的tool_calls；历史从tool消息重建同样摘要，不依赖丢失的事件日志。
- [ ] search_knowledge把rag.retrieved合并到现有活动；真实字段是chunks/source/score等，不读取旧roadmap的sources/count/duration_ms。空结果与失败区分，相关度不是置信度。
- [ ] 一轮仅一行活动汇总，展开才看详情；普通工具通用摘要，不硬编码只有RAG能显示。没有隐藏推理数据就不添加“思维链”面板。
- [ ] 收到取消请求显示“正在取消”；持久终态到来才结束。未提交partial移出正文，已提交工具记录保留；取消后的迟到delta丢弃。
- [ ] 中间assistant内容归入活动说明，最终回答独立；不会把tool JSON直接当聊天正文，不虚构完整工具持续时间。

**验收：** 离线fixture覆盖工具成功/失败/多Step/取消修复，并通过实际HTTP写入临时SQLite；桌面重开后活动摘要依然可展开，partial不回来。RAG fixture只证明展示与配对，不证明真实检索质量。

## 阶段6：最小Settings与统一错误状态

**亲手可见：** 设置里修改Provider模式、聊天Base URL/模型，独立查看/修改Embedding非敏感配置；Key只显示是否来自启动环境。空闲时“应用并重启服务”，设置生效；运行中明确禁止应用。历史不会丢失。

**主要文件：** 新建`electron/settings.ts`、`components/SettingsDialog.tsx`、`BackendBanner.tsx`；更新main/bridge/process管理；测试`tests/unit/settings.test.ts`、`error-states.test.tsx`、`tests/e2e/settings-restart.spec.ts`。

**工作：**

- [ ] 先写配置与启动意图竞争：startRun正在接纳、Run正在取消、核对不明时都拒绝应用；重启临界区拒绝新提交。保存失败、启动失败不能显示“已生效”。
- [ ] 设置文件仅保存允许字段；本地覆盖优先，恢复环境值移除覆盖。URL/model校验匹配后端；Key无字段、无IPC值、无localStorage/日志，测试只用动态假凭据。
- [ ] 主进程复查所有请求状态与health.active_runs=0，锁住新意图后停旧实例再启新实例；桌面DB路径不变。不能依靠React按钮禁用来保证竞态正确。
- [ ] 实现backend unavailable、输入错误、busy、capacity、运行失败、存储失败统一样式；不同恢复动作明确，草稿保留。Provider错误原因拿不到时如实显示通用错误，不猜认证/余额。
- [ ] Key是否提供与health可用性分开；更新系统环境后提示完全重启Electron。无自动远程“测试连接”，无模型枚举、自动建库或热切换。
- [ ] 设置Esc关闭/焦点归还；主题只影响Renderer，不触发后端重启。

**验收：** 假服务捕获环境，证明两套Provider配置独立且Renderer/日志/设置文件无Key；配置修改后旧Run历史的model不变；更改Embedding配置导致索引不匹配时显示RAG不可用，普通聊天仍可用。

## 阶段7：Windows完整可用闭环与交付

**亲手可见：** 从桌面开发入口打开→选择历史/新聊→逐步回答→观察工具→取消→退出→重开恢复；异常有明确反馈。无需手工先启动Python，不交付安装包。

**主要文件：** `tests/e2e/windows-lifecycle.spec.ts`、`daily-use.spec.ts`；完善desktop host/进程测试；新增`docs/phase-6-walkthrough.md`；更新README和architecture当前状态、planning记录，保留早期设计作为历史而不混为实际接口。

**工作：**

- [ ] 真实Electron + 真实loopback HTTP + 实际SQLite，测试明确注入的离线Provider；不以纯React mock替代进程/断连验收。夹具由测试入口注入，不给正式Settings新增“测试Provider”。
- [ ] 验证正常关窗取消清理、无Run直接关窗、后端骤停、Renderer崩溃、端口动态分配、连续启动、中文空格路径和目录外启动；检查只处理自管进程，父进程EOF不留孤儿服务。
- [ ] 强制故障后重启同一临时DB：已有完整消息保留，pending配对修复为interrupted，不重放工具，partial不恢复；未知通知不能被标成成功。
- [ ] 验证Sidebar分页/滚动、100+历史、两个并行会话、409/429、长Markdown与代码、滚动锁定、IME、键盘焦点、DPI/缩放和低窗口高度；脚本/危险链接不能执行。
- [ ] 运行前端typecheck/lint/unit/build/e2e，以及原后端完整unittest、Ruff和diff检查；记录实际数量与环境，不预写“通过”。Python host也纳入Python检查。
- [ ] 交付PowerShell运行/关闭/配置/离线验证步骤、数据路径与重启恢复说明；用一次执行链解释HTTP/SSE、UI暂态/DB事实、三层职责与本机进程所有权。真实API手工验证另记，不混入自动验收。

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\.venv\Scripts\ruff.exe check backend frontend/desktop
.\.venv\Scripts\ruff.exe format --check backend frontend/desktop
git -c safe.directory=D:/Desktop/herta-agent diff --check
```

**验收结束：** Phase 6可用闭环完成后停止；不进入Phase 7安装包/Python分发，也不自行动工未获批准的后端错误契约改进。

## 五个重点审查场景

| 场景 | 归属与证据 |
| --- | --- |
| 切会话卸载组件意外断开SSE | 阶段3/4：A持续运行，B可聊，回A状态正确，只有显式取消/断连终止 |
| 首事件丢失但user已提交，或终态丢失但已completed | 阶段4/5：GET校对，不能重POST、重复user或改写成功 |
| Windows只杀venv启动器、换显示器或目录后启动 | 阶段1/7：真实解释器退出，窗口可见，绝对路径与DB持续正确 |
| 空闲检测后设置重启与新Run同时到达 | 阶段6：Main串行锁住接纳，旧/新配置没有混合运行 |
| 多Step同名调用ID、失败却没有started、流式Markdown尚不完整 | 阶段4/5：按复合键配对，安全文本回退，终态靠DB而非UI猜测 |

## 文档自检与当前交付

七阶段均有可操作成果，没有只搭底座却看不到效果的长阶段。首批阶段1先证明桌面自管后端，再阶段2稳定视觉，不需要先扩展Agent业务。接口映射、Settings用户选择、素材取舍、未知状态与错误诊断限制均已纳入设计与验收。

当前已完成阶段1–5。按用户本轮收敛要求，测试覆盖关键闭环，不扩展原计划的全部边界矩阵；上方阶段2–5清单保留原始验收范围，不代表所有边界已逐项验收。实际交付包括布局素材、分页历史、应用级会话状态、固定 IPC/HTTP/SSE、流式回答、Stop、工具/RAG摘要与重启恢复。组件按最小实现合并，未机械创建每个规划文件。

2026-09-23：前端 typecheck、lint、21项单元测试、7项真实 Electron e2e（含 build）通过；后端178项 unittest、Ruff check/format、diff check通过。真实窗口测试采用离线 Provider 和临时 SQLite；没有调用真实模型或 Embedding API，不证明真实 RAG 质量。启动与验收见 `docs/phase-6-chat.md`。停在阶段5，阶段6/7未开始。
