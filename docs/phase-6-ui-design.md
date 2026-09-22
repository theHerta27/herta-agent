# Phase 6：Windows 桌面 UI 设计

状态：2026-09-22，设计提案，未开始编码。目标是每天能打开、聊天、观察工具、取消、切换和恢复历史的 Herta；技术栈固定 Electron / React / TypeScript / Vite + 现有 Python 后端。

## 1. 基线与范围

以 `phase-5-service` **实际工作区**为准：HEAD 为 `33f10e2`，Task 10–12 仍在未提交改动中；`frontend/` 目前只有用户准备的8张图片。后续建分支不能只从旧HEAD取代码而漏掉这些改动。本轮不提交、搬移或覆盖它们。

已核对 architecture、Phase 5 design/plan/walkthrough、service/app/events/sse/runs/turn、Runtime事件与提交、SQLite记录/恢复和服务测试。Phase 5 已完成服务闭环，现有记录为178项离线测试通过；本轮只做阅读和文档核查，没有重跑工程测试。旧文档开头的“只到Task 9”、architecture里计划中的Settings API/事件字段，不能作为实际能力。

V1只有：会话侧栏、Welcome、消息区、Composer、Run/Tool活动、最小设置。无Memory/MCP/Skills、多Agent、Cron、语音、Live2D、插件、知识库管理器、开发者控制台、附件上传或执行代码功能。Phase 6负责开发环境桌面可用闭环，最终exe、Python分发和安装升级留给Phase 7。真实供应商流式兼容性和Phase 4真实RAG效果仍待真实服务验收。

## 2. 主界面与比例

**一张安静的聊天工作台，不做卡片仪表盘。** 默认暗色，设置可切浅色/跟随系统；内容优先，少量低饱和紫色只用于强调与焦点。

```text
┌──────────── Windows 原生标题栏：Herta ────────────────────────┐
│ Herta             │ 会话标题                  模型 / 本机状态 │
│ ＋ 新对话         │                                          │
│                   │        用户问题（轻背景短块）              │
│ 历史会话          │        Herta 正文（无外框）                │
│   问题摘要        │        ▸ 已检索角色资料 · 1项活动           │
│   问题摘要 · 运行 │        Herta 最终回答                      │
│                   │                                          │
│                   │        本轮状态 / 局部错误                │
│ 设置              │        [ 输入问题……              发送/停止 ]│
└───────────────────┴──────────────────────────────────────────┘
```

- 默认窗口1200×800 DIP，最小800×600；原生窗口边框与最小化/最大化/关闭按钮，不自写无边框拖动系统。窗口位置恢复须落在当前显示器可见范围。
- Sidebar宽248，内边距12；行高36–40，文字14。顶部只放品牌和新对话，底部设置；中间独立滚动。无Projects、PR、Work/Code/Learn等入口。
- 主区顶部48高；正文与Composer共用最大780宽，左右至少24，段落行高1.7。1280以上居中留白，不随窗口无限拉宽。
- 小于1000宽时Sidebar可折叠为44宽栏，点开临时会话面板；主区左右16。低窗口高度优先保留输入区，缩小/隐藏Hero。代码块和表格内部横向滚动，页面不横向溢出。
- Composer占正常布局底部，不覆盖消息；高度随输入增长，上限180后内部滚动。Enter发送，Shift+Enter换行，中文输入法组字中的Enter不发送。运行中允许编辑下一条草稿，按钮变“停止”，不自动排队；取消中禁用重复停止，不禁用查看历史。
- 自动跟随仅在用户接近底部时发生；上翻阅读后显示“回到最新”，不抢滚动。按Session保留本次应用内的草稿与滚动位置，草稿不作为历史、不要求重启恢复。

## 3. 角色素材与Welcome

Welcome在新对话草稿/真正空Session显示，历史加载中不闪现Welcome。主区中上部放半身图，下面是“Herta”和一句“把你的问题带来。”，再放与正文等宽的Composer。最多两条可填入输入框的示例问题，不自动发送，不生成营销式功能卡。

| 实际素材 | V1用途 |
| --- | --- |
| `welcome/herta-welcome-bust.png`，900×764 | Welcome唯一Hero，约300–340宽、最大280高，contain、不铺背景；发送后移除 |
| `avatar/herta-avatar.png`，1490×1490 | assistant组标题28–32圆形头像；不对每个delta/工具重复绘制，不叠头像框 |
| `status/herta-rag-reading.png`，1024×1024 | 知识工具运行时活动行旁可用28–32小图；文字状态始终存在，不作全局加载动画 |
| fullbody / avatar-frame / success / error / empty | 保留原文件，V1不使用，避免视觉噪音与首次加载成本 |

素材均位于 `frontend/src/assets/herta/`，本轮已逐张查看，不重新抠图、不改原文件。半身图包含原图自带文字标识，不能拿它充当应用Logo；应用名始终为Herta。正常聊天完全没有大型Hero、漂浮贴纸或背景人物。图片加载失败保留布局与文本，头像以“H”回退；装饰图空alt，身份名由文字提供。只导入实际使用的3张，避免将全部status打入首屏。

## 4. 参考取舍与Design Tokens

**Codex：** 本地 `references/ui/codex/screenshots/codex.jpg` 为1603×915浅色聊天截图。侧栏约占21%，主区正文与底部输入同轴，次要操作靠边，执行内容可折叠，靠留白而非大量边框划层级。借鉴这些比例、密度和渐进展示；不复制品牌、图标、资产、PR/项目导航。截图没有展示Welcome或暗色，不能声称观察到它们的具体设计。

**Cyrene：** `references/ui/cyrene/screenshots/cyrene-work.png` 是Work页面，不是Herta功能清单。源码中ChatPage负责页面装配；ChatComposer有centered/docked切换和可增长输入；ChatMessageList把正文、活动与工具分开并处理回到底部；ConversationSidebar独立滚动；RunStageIndicator用文字和状态标记；theme/tokens/base区分原始值与主题覆盖。这些职责值得借鉴。

不采用Cyrene的多模式、庞大ChatPage业务、Ant Design X整套依赖、TTS/Reasoning/任务面板/权限流；不采用StatusFloat的随机漂浮、头像常驻动画、粉色发光或透明桌面背景；不沿用其缺失终态时默认completed的逻辑。只参考方法，独立实现，不复制角色资源和大段代码；其根LICENSE已读，代码为MIT，不因此把角色资产视为可移植。

**ui-ux-pro-max：** 已读并搜索布局/排版/暗色/可访问性/交互。采用可见焦点、文字对比度、减少动画、稳定布局和一致间距。搜索器给出的营销单列、活泼色块、Lora/Raleway远程字体不适合本项目，明确不采用；不为套用Skill加入Tailwind或移动端站点工程。

建议语义Token（提案值，阶段2按实际窗口再微调）：

| Token | 暗色 | 浅色 |
| --- | --- | --- |
| background | #17181C | #FAFAF9 |
| surface | #1F2126 | #F1F1F0 |
| surface-hover | #2A2D34 | #E9E9E8 |
| border | #343842 | #DADCDF |
| text-primary | #EDEDF1 | #212229 |
| text-secondary | #ACB1BE | #5C626D |
| accent / focus | #B7A4EE | #69529B |
| text-on-accent | #1A1622 | #FFFFFF |
| danger | #FF9898 | #B23B3B |
| success | #8BD1AC | #256645 |

Spacing：4/8/12/16/24/32/48；radius：6（按钮）、10（小块）、16（Composer）；font-size：12状态辅助、13工具、14导航、16正文/输入、24欢迎标题；content-width：780；sidebar-width：248。字体用本机 `Segoe UI Variable / Segoe UI / Microsoft YaHei UI / sans-serif`，代码用Consolas；不依赖网络字体。

关键文字组合已按相对亮度计算：暗色正文15.19:1、次级7.51:1；浅色正文15.17:1、次级5.43:1；强调按钮文字均超过6:1。分隔线只作装饰，不作为输入边界/状态唯一线索。focus-visible提供2px强调描边；状态兼有图标和文字。图标按钮至少36×36，Send/Stop为40×40；键盘全程可达，Settings返回焦点到触发按钮。只对颜色/透明度做120–180ms过渡，尊重reduced-motion；屏幕阅读器只播报阶段变化，不逐token播报。

## 5. 三层职责与桌面启动

| 层 | 负责 |
| --- | --- |
| Electron Main + 窄Preload | 窗口、自管Python进程、绝对资源路径、非敏感配置；HTTP/SSE传输桥接、连接关闭、外链白名单 |
| React Renderer | 会话选择、输入、消息/活动呈现、暂态状态与错误；发送用户意图，不接触Key/SQL，不调用模型 |
| Python/FastAPI | 现有SessionStore、RunManager、唯一Loop、Persona、Provider/工具/RAG、终态裁决 |

Electron把Chromium渲染页面与桌面窗口/进程能力组合起来，Main管理宿主、Renderer使用React。进程和Preload边界依据[Electron进程模型](https://www.electronjs.org/docs/latest/tutorial/process-model)及[contextBridge](https://www.electronjs.org/docs/latest/api/context-bridge)。React没有必要重复实现模型/工具循环：否则取消、历史、预算会出现两个决策者。

传输方案比较：

| 方案 | 取舍 |
| --- | --- |
| **推荐：Main代理固定HTTP接口及SSE，Preload暴露类型化意图** | 多一层薄桥接，但无须给现有服务加CORS；Main持有连接，切换视图不误取消，Renderer不取得凭据 |
| Renderer直接fetch本机端口 | 贴近Web，但开发/打包来源均需明确CORS或代理，流易随页面组件销毁；当前后端没有CORS，不关闭webSecurity来绕过 |
| 手动启动/附加外部服务 | 调试方便，但不满足打开桌面即可用，配置和进程归属模糊；不作为V1正常路径 |

Main只调用固定路由；Preload不暴露任意URL、shell、文件读写或原始ipcRenderer。`contextIsolation=true`、`nodeIntegration=false`、sandbox保持开启；Markdown不执行原始HTML/脚本、远程图片不自动加载，外链仅用户点击后经校验打开http/https，禁止file/javascript等协议。参考[Electron安全建议](https://www.electronjs.org/docs/latest/tutorial/security)。不增加账户/鉴权系统；旧roadmap的本机token未在Phase 5实现，本提案不把loopback/CORS或私有端口称为完整身份验证。

**生命周期是桌面适配，不是扩展Agent能力：**

1. Main单实例启动，先显示Welcome框架与“正在启动服务”；从项目绝对位置找到`.venv/Scripts/python.exe`，不使用PATH里的其他Python，不弹终端。
2. 建议新增薄的 `frontend/desktop/backend_host.py`：只调用现有`ServiceSettings`和`create_app`，以Uvicorn绑定127.0.0.1:0；就绪后经私有stdout发送port/实际PID/协议版本。Main核对自管子进程仍存活，再GET health；不解析Uvicorn人类日志猜端口。无新业务HTTP路由、无新Loop。
3. 桌面开发用固定`.local/desktop/sessions.sqlite3`，与CLI服务默认DB分开，避免两个服务同时拥有同一运行库；首次不自动迁移旧库。重启仍用该路径，UI明确“桌面会话”。Persona/knowledge/index继续指向现有绝对路径；为Phase 7预留userData路径解析，不现在打包Python。
4. Main退出先停止接纳桌面新意图、取消自管请求并等待持久终态；host通过stdin的shutdown/EOF请求现有Manager清理并让Uvicorn退出。建议20秒总等待，超时只对仍持有身份的自管进程做Windows终止兜底，不能按进程名批杀或把只杀venv启动器当成功。下次启动使用已有interrupted恢复。
5. 有活跃Run时关闭窗口提示“取消运行并退出/返回”；最小化不关闭连接，不做托盘驻留。后端意外退出显示离线，可手动重启，不重发原POST。Renderer崩溃/重载时Main关闭其流，随后GET恢复事实，无事件续传。

当前CLI没有机器就绪/优雅停机控制通道，所以该host是桌面闭环必需的**新适配工作**，不能声称已有；它不修改Python Runtime或Store语义。若实现中发现必须改业务接口，先另列缺口讨论。

## 6. Session、历史与事实来源

- 应用启动先加载持久Session清单；默认选“新对话”Welcome，历史始终在Sidebar。新对话先是本地草稿，首次发送时POST /sessions，避免每点一次就创建永久空会话。
- 列表按ID游标顺序读取全部轻量元数据后按updated_at降序显示，读取期间标“正在加载会话”；不能把后端第一页误称最近50条。标题先用时间+短ID；可见行最多20个、并发上限4读取`limit=1`的首条user，派生前24字摘要并缓存。无模型生成标题、不新增标题数据库/重命名/删除/置顶接口。
- 打开会话用after_seq递增、每页100条读取至不足100；按message_id去重、seq排序。加载期间展示骨架和进度，未加载完整时不允许发送，避免把早期消息误当最新历史。历史加载失败可重试GET，草稿保留；旧请求迟到只更新所属Session，不能覆盖新选择。
- 每个Run的user/assistant正文属于Message List；assistant.tool_calls、tool消息投影成Run Activity，按`run_id + step + tool_call_id`配对。不同Step复用调用ID不合并。历史终态按消息中唯一run_id懒加载GET /runs/{id}，最多并发4；不是只依赖current_run推测所有旧轮状态。
- History是SQLite的正式事实；UI另有pending input、当前Run/Step partial、活动展示和草稿。持久消息不复制到localStorage/IndexedDB。刷新时按ID与后端对齐，不用文本相等去重，也不把同样问题的两轮误合并。
- 切换A→B只换选中视图；Main仍消费A的SSE，App级状态仍按Session接收，Sidebar标“运行中”。B可启动自己的Run，遵守后端全局容量；同Session仍禁重复发送。不是断开连接后让后端继续跑。

## 7. 流式、Tool与取消

Main用POST fetch读取UTF-8 SSE，解析跨块文字/空行/id/event/data/心跳，不能用原生EventSource提交JSON；SSE协议参考[MDN](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)。事件保持schema_version=1与原关联ID；本地clientRequestId只用于首事件前的意图归属，不塞进后端只接受text的正文。

| 后端真实事件 | UI处理 |
| --- | --- |
| run.started | 绑定run_id；从“正在提交”转为执行；核对已入库user |
| llm.started | 新step/message_id，显示“等待回答”；不称为读取思维链 |
| llm.delta | 只追加到这个message_id的暂态文本，约每帧批量渲染，不给每段建气泡 |
| llm.completed | payload.message已提交；用完整内容替换该partial，按message_id对齐；有tool_calls则归入活动，不能视为Run结束 |
| tool.started | 显示“正在检索角色资料…”或“正在执行 echo…”；参数来自此前已提交tool_calls |
| tool.completed / failed | payload.result标记工具结果；默认一行摘要，可展开工具名、Step、简化参数、结果/错误；失败不自动等于整轮失败 |
| rag.retrieved | 更新同一知识工具活动，显示query、index_id、chunks来源/分数；不重复插一条聊天消息 |
| run.completed / failed / cancelled | 结束本轮，GET Run与增量History核对；清空未提交partial；保留已提交消息 |
| service.error | “存储未能确认本轮结果”；persisted=false不能渲染成已保存failed，停止新发送并提供重启/核对 |

每轮默认只显示一行活动摘要（如“已检索角色资料 · 2项活动”），失败用文字与图标强调，详情仍由用户展开。活动里可以展示已提交的中间assistant说明，但不把多个Step文本拼成最终答案。RAG空chunks显示“本次未返回证据”，不推论“问题没有答案”；score注明相似度，不做置信度进度条。原始完整JSON不默认铺出，也不新增开发控制台。

历史可从完整tool消息重新投影上述摘要，但没有精确事件开始时间/持续时间，不补造耗时。tool.failed可以没有tool.started（参数无效），取消修复的tool结果也可以没有对应SSE完成事件；终态后History校正处理。

**停止：** 有run_id时POST cancel，保留流等终态；按钮显示“正在取消”，accepted仅表示请求已接受。尚未有run_id时取消本地提交连接，之后查询当前Session/新出现的Run核对。保存提交前的最近run_id和最大seq，不能把上一轮已完成Run误认作这次结果。接纳结果暂不明时阻止盲目重发，保留草稿并提供“核对状态”。

取消/失败后未提交文字从正常正文移除，显示简短状态；完整已提交的工具调用/结果不删除。点击取消与最终提交竞争时，GET若是completed就展示完整成功回答，不强行改成cancelled。

**断流：** EOF不是成功；没有终态时进入“连接中断，正在核对”，GET状态与历史（每秒一次，最多10秒），仍不明则保持明确未知状态并提供手动核对，不自动重发POST或Last-Event-ID续传。存储不可写直接显示故障，避免无限轮询旧running。

Main→Renderer也应有限缓冲：可合并连续同message_id的delta，保持其余事件顺序；最多128项/2MiB待交付、有限等待。UI未订阅/渲染端销毁或持续不消费则关闭流并取消，不能把后端背压转移成无限IPC队列。只保留当前状态，不保存全量事件日志；重复seq忽略，seq有间隔触发事实校正、不自动补发，不能要求取消后seq连续。

## 8. 状态语言与Settings

| 场景 | 展示与操作 |
| --- | --- |
| 空Session | Welcome + 可输入Composer；不显示假示例聊天 |
| 有历史 / 历史加载中 | 消息或骨架；加载失败可重试GET，保留选择与草稿 |
| Streaming / Tool Call | 单一Run状态行 + partial或活动；停止可用 |
| Tool Success / Failure | 简短成功/失败标记，必要时展开；等待后续模型动作 |
| Cancelled / Interrupted | “本轮已取消”/“上次运行中断”；已提交历史保留，可新发一轮，不提供断点续跑 |
| Backend unavailable | 顶部持久提示，主内容保留，禁发送；重试启动/重连 |
| Provider/Persona执行错误 | “本轮未完成”及GET返回的安全错误；可打开设置或修复后新发；不虚构401/余额不足等诊断 |
| 409 session_busy | “此会话正在运行”，刷新该Run，保留草稿；不排队 |
| 429 capacity | “同时运行数量已满”，其他会话正常，手动稍后发送 |
| 422 / 503 | 输入附近显示验证错误；能力缺失或存储故障明确说明，不丢草稿 |

**已获用户确认的最小Settings：** 一个简单面板；Provider模式（兼容API/明确离线demo）、聊天Base URL、模型名可编辑。Embedding保持独立，在同面板折叠区域展示/编辑自己的非敏感Base URL和模型，提示改变编码配置可能需要用现有CLI重建索引。没有模型列表API，不做自动列模型、测试请求或知识库管理。

Key只显示“启动环境已提供/未提供”，没有输入框、不回传原值、不显示部分字符；Main只把存在性布尔值给Renderer。实际有效性以health/执行结果为准，存在不等于验证通过。环境变量更新后须完全退出并从更新后的环境重新启动Electron，不能声称已运行进程自动读到系统新值。

非敏感配置由Main保存至桌面设置文件（开发`.local/desktop/settings.json`，将来userData），明确“本地覆盖优先于继承环境，恢复环境值则移除覆盖”。保存与生效分开：有任意活跃/正在接纳/核对不明的Run时禁止应用；空闲时锁住新提交，确认health.active_runs=0后重启自管后端。成功后显示当前生效值；失败明确仍未生效，可修正或恢复原配置，不暗中切demo。Base URL禁止userinfo/query/fragment，杜绝把Key放URL；不记录配置提交正文或环境快照。

其余仅有主题选项和只读后端/RAG可用状态；不做大型设置中心，不改Session中历史Run的模型记录。

## 9. 组件与目录提案

已有素材在frontend，建议直接以它作为桌面前端根目录，替代早期roadmap的apps/desktop占位；无需两套目录或移动素材。

```text
DesktopApp
├─ AppShell / BackendBanner
├─ ConversationSidebar
├─ ChatView
│  ├─ ChatHeader
│  ├─ WelcomeView 或 MessageList
│  │  └─ RunGroup → UserMessage / AssistantMessage / RunActivity → ToolActivity
│  ├─ RunStatus
│  └─ Composer
└─ SettingsDialog
```

```text
frontend/
  package.json / package-lock.json / vite.config.ts / tsconfig*.json
  electron/
    main.ts                窗口、单实例与退出
    preload.ts             白名单意图与事件订阅
    backend-process.ts     Python启动、就绪、停止与绝对路径
    backend-client.ts      固定HTTP、POST SSE与取消
    settings.ts            非敏感配置与安全摘要
  desktop/backend_host.py  薄进程适配，调用现有create_app
  shared/contracts.ts      UI与Main桥接类型；区分后端schema和本地状态
  src/
    main.tsx / App.tsx
    assets/herta/          现有素材原位保留
    styles/tokens.css / base.css
    components/            上述可见组件，按职责拆小文件
    state/chat-store.ts / run-reducer.ts / history-view.ts
    api/sse-parser.ts      纯解析器供Main使用与单测，不在React组件里解析
  tests/unit/ / tests/e2e/ / tests/fixtures/
```

不先引入Redux、路由框架、通用插件层或整套Chat组件库。App级状态保存各Session视图，连接由Main持有；组件不在挂载effect里发起Run，避免StrictMode双提交。Markdown渲染和图标可选小型成熟库，版本在获准实施时选择并锁定。

## 10. Phase 5接口是否够用

| 已核实能力 / 缺口 | 结论 |
| --- | --- |
| Session创建、列表、历史；Run读取、取消、POST SSE | 足够支撑核心闭环，保留现有语义 |
| 列表默认50/最大100，ID升序，无标题 | UI按游标读取后排序，首条user派生摘要；现有walkthrough的默认100不作为契约 |
| History升序after_seq，current_run可能为终态 | 分页到末尾才显示“历史已加载”；逐Run状态另外GET；不存在倒序/Run列表API |
| tool.started无arguments，tool结果无duration_ms | 从llm.completed与历史关联参数，不展示虚构耗时 |
| run.started payload为空；终态仅persisted/steps | 不读取旧roadmap里的max_steps/final_message_id/code/message；错误从GET Run读取 |
| Provider/Persona多种失败归为run_aborted | **阻塞精确原因诊断，不阻塞失败状态与聊天**。V1如实展示通用安全错误；若要区分认证/超时/Persona须另行批准后端错误契约改动 |
| 无Settings/CORS/就绪与停机控制 | Settings已选Main保存+空闲重启；Main HTTP桥接避免CORS改动；薄host补桌面生命周期。均不增加Agent业务能力 |
| 无事件重放、无Run断点续跑 | UI不提供这些功能，断线GET核对，符合现有边界 |
| 普通demo无增量/工具调用 | demo只能验证普通聊天；流式/Tool用明确离线fixture验收，真实服务另行手工验证 |

**结论：没有必须先扩展Agent业务后端才能开始UI的阻塞。** 不能把“精确Provider诊断、结构化启动停机”说成Phase 5已经具备；后者作为桌面适配纳入计划，前者保留限制。当前尚有Phase 5未提交工作区，开始实施前必须保留完整基线，不在本轮擅自提交。

## 11. 学习与验收重点

用一次真实操作解释分层：React发意图 → Preload/Main传输 → FastAPI/Runtime决定与提交 → SSE实时投影 → GET校正持久事实。HTTP处理命令和查询；SSE是这次POST响应上的单向事件流。Tool Activity是执行记录的视图，不是发给模型的新聊天角色。

验收按下一文档7阶段推进，每阶段都有可见成果。最终要亲手验证：跨会话并行和切换、中文流式、长Markdown/代码、取消竞争、工具失败后继续、断线未知状态、关窗与后端崩溃、重启恢复。第一版没有漂亮界面掩盖假的完成状态，也不把离线fixture称为真实RAG质量验收。
