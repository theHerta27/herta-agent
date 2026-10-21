# 当前教学分支：Python CLI 单元03

当前目标是理解并构建一个独立的 Python CLI Coding Agent。当前可读取、字面搜索，并在逐次确认差异后替换已有文件中的一处唯一文本，复用同一个Agent Loop；尚不能运行命令。下面原有桌面版章节保留为历史说明，不代表当前教学分支的产品入口。

在本分支的仓库根目录，使用已有 Python 环境运行：

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'backend')
python -m herta_agent --repo examples/cli-read --demo-read-file notes/demo.md --message '请读取这份笔记，展示内容。'
```

`--demo-read-file` 是固定工具调用演示：不调用模型、不读取 API Key；实际文件读取、校验和结果回填仍由真实 Harness 执行。省略 `--message` 进入交互模式，`/exit` 退出。会话仅存于当前进程。`--provider openai` 注册`read_file`、`grep_code`和`edit_file`，CLI对每次编辑显示完整差异，只有输入`yes`才确认。模型适配器可以替换；目前只通过本地模拟 HTTP 验证，真实模型选工具和回答质量未确认。

搜索→读取的本地学习夹具：

```powershell
python examples/cli-search/demo.py
```

该夹具使用相同`create_agent/chat/Agent.run`，固定搜索`def add_tax`，将真实命中的路径交给Read，显示`steps=3`；不增加生产CLI参数或第二套Loop。搜索区分大小写、按字面匹配，返回路径、行号与预览；遇到预算截断或无法读取的文件，会通过`truncated/skipped_files`说明。详见[单元02](docs/learning/unit-02-search-read.md)。

读取→确认编辑→回读的本地学习夹具：

```powershell
python examples/cli-edit/demo.py
```

只操作本次创建的临时文件。输入`yes`后实际修改并回读，显示`steps=4`；输入`no`、直接回车、EOF或确认时Ctrl+C会拒绝此次编辑。每次运行均重建演示文件，不触及已有资料。实际修改限已有普通UTF-8文件中的一处唯一文本；内容指纹过期、重复匹配、链接、硬链接或只读文件均拒绝，不提供文件创建/删除或多文件补丁。详见[单元03](docs/learning/unit-03-confirmed-edit.md)。

路径检查约束 `read_file` 对选定项目目录的访问，排除 `.env`、`.git` 等内部路径，不是操作系统沙箱。仅接受不超过1 MiB的UTF-8文本，每次最多400行，并按结果字节数保守截断；更大的文件明确报错，不返回不完整行。具体限制、真实调用链、验证与练习见 [单元01学习总结](docs/learning/unit-01-cli-read.md)。旧桌面启动脚本不是这个 CLI 的入口。

---

# 旧版桌面说明（历史）

Windows 个人 AI 桌面助手，保留大黑塔人格、持续会话与知识检索，提供语音、提醒、可管理记忆和受控文件工作台。Electron 管理本机 Python 服务；Agent Loop、工具执行、上下文预算与 SQLite 历史均由 Herta 自己实现。工程机制主要参考项目中的 Hermes 源码，Cyrene 用于产品功能思路。

## 现在就用

本机依赖和桌面构建已准备好。在项目目录双击：

- **`启动离线演示.cmd`**：完全离线，验证聊天界面、会话、停止与历史恢复；回答是明确标注的演示回显。
- **`启动Herta.cmd`**：使用已配置的聊天服务。默认 `https://api.deepseek.com`、`deepseek-flash`；DeepSeek域名优先读取 `DEEPSEEK_API_KEY`，否则读取 `HERTA_API_KEY`；其他聊天地址仅使用 `HERTA_API_KEY`。启动器会补读 Windows 用户级环境变量，无 Key 时在本机窗口中遮蔽输入，仅用于本次启动。

切换演示/真实模式时先从系统托盘右键选择“退出 Herta”。当前交付按用户要求只进行本地验收。使用真实聊天入口并发送消息会调用配置的服务；本次最终回归使用离线 Provider，没有继续真实问答或真实效果评测。

更新版本后也需要从托盘“退出 Herta”再启动；窗口右上角×只会隐藏旧进程。启动器检测到早于当前构建的驻留实例会明确提示退出，避免再次唤起旧界面。新版右上角包含“文件、学习、个性、日常、附加、快捷、扩展、设置”，没有音乐界面。

启动后可新建/切换会话、发送消息、查看流式回答，点击停止取消当前运行。展开工具活动可查看检索片段与原始来源；展开上下文活动可查看预算、保留消息、摘要与证据引用。关闭窗口后留在系统托盘，提醒继续运行；双击托盘或按 Ctrl+Shift+H 唤出窗口。托盘“退出 Herta”才清理自管后端，重开后恢复已完成的历史。

右上角设置可修改聊天地址/模型、Embedding 模式、上下文窗口、输出预留与旧历史摘要。保存会重启自管服务；有运行时拒绝修改，失败会恢复此前设置。设置页面不接收或显示 API Key。

## 从聊天整理一份笔记

在输入框上方点击“选择资料目录”，选择项目以外的普通资料文件夹，在原生提示中允许聊天读取。可准备两份短 UTF-8 Markdown，发送：“读取 asyncio.md 和 task.md，整理成一份复习提纲，保留文件名和行号来源，保存到复习/asyncio提纲.md，先给我预览确认。”

Agent 使用现有工具读取资料并提出新 Markdown。聊天会展示与后端暂存内容一致的预览；点击“确认保存笔记”，在原生对话框确认后才写入。保存后会读取实际目标、核对内容，并在原会话请求 Agent 查询执行状态和文件内容。未发送草稿保留；核对请求失败时可点击“让 Herta 核对结果”。打开历史只恢复任务状态，不自动调用模型。

这条任务复用现有 Agent Loop、目录授权、文档暂存、文件执行器和原生审批，没有新增依赖或第二套服务。文本预览最多400行/10,000字符，生成笔记最多10,000字符；已有文件不覆盖，工程目录及敏感文件仍受保护。预览有效期10分钟，过期或目录授权变化后需重新生成。完整本机流程使用确定性模型协议桩验证，**真实 DeepSeek 选工具和整理质量尚未验收**。操作与验证边界见 [笔记任务说明](docs/NOTE_TASK.md)。

## 日常陪伴

点击右上角“日常”：

- **提醒与专注**：添加一次、每天或每周的北京时间提醒；到期后可以“知道了”或延后10分钟。45分钟专注会创建休息提醒。完全退出期间不执行，重开时补一条错过的提醒，重复计划继续按原时间运行。免打扰保留未读提醒并推迟系统通知；Windows 通知是否展示取决于系统设置。
- **本地语音**：点击“录音”，结束后在消息框编辑识别文字，再发送。每次最长60秒；每条回答可朗读、停止，也可开启自动朗读新回答。录音会停止旧朗读；停止和切换会话会取消旧请求及播放。当前机器的模型与依赖已准备好，识别和合成全程在本机执行。
- **偏好与记忆**：编辑称呼、自动朗读、日常工具开关和免打扰；可以重置偏好。新增记忆先待确认，点击保存后才进入以后每轮上下文，可随时删除。

聊天共享原有 Agent Loop，提供4个日常工具：创建/查询/取消提醒和提出待确认记忆。可在偏好中关闭日常工具；只读 MCP 的原有权限门禁继续有效。离线演示只验证界面和确定性功能，不会理解自然语言并选择工具；同一执行循环中的工具调用已用离线夹具验证，真实模型的自然语言路由暂未验收。

在新环境启用语音，双击 **`准备本地语音.cmd`**：按锁文件安装可选依赖，再下载公共 Whisper/Piper 模型到 `.local/voice`。日常运行不会自动下载模型，缺失时显示不可用。模型来源、版本、文件哈希和现有验收见 [陪伴版报告](docs/COMPANION_ACCEPTANCE.md)。

## 文件与空间分析

点击右上角“文件”，通过系统目录选择器添加本机目录：

- 浏览文件夹、按名称搜索，识别工程、缓存和快捷方式；快捷方式不解析目标。
- 预览 1 MiB 内的常见 UTF-8 文本；预览最多400行/10,000字符，截断会明确提示。可加入聊天草稿，编辑后自行发送。
- 点击“分析空间”查看磁盘可用空间、目录逻辑大小、大文件和目录排行。可选择检查有界的重复内容候选；支持停止与历史报告。
- 默认仅本地查看。开启“允许聊天读取此目录”需要原生确认：模型可以调用5个只读文件工具，内容可能发送给你配置的服务。关闭共享或撤销授权会阻止后续工具读取，已进入会话的内容仍保留在历史中。

勾选普通文件后，可预览复制、移动、改名或按类型整理方案。具体方案经过原生确认才执行，不覆盖现有目标；聊天中的 `propose_file_plan` 只生成待审阅方案。预览绑定文件内容与目录授权，有效期10分钟，最多100动作、256 MiB单文件、1 GiB总量。执行可停止，逐项保存收据；撤销需重新预览确认，拒绝被后续修改的文件或含新增内容的文件夹。退出停止自有任务，重开保留中断记录并提示核查，不自动重试。

敏感配置、系统目录、链接与重解析点受保护；缓存仅统计大小；修改还保护工程、硬链接和启动脚本。分析最多20,000项/16层/30秒，搜索最多5,000项/8层，受限制或无法读取的结果有提示。逻辑大小不能当作实际可释放空间，重复内容不能当作删除授权。运行期间拒绝设置重启。

授权与报告单独保存在 `workspace.sqlite3`，不迁移或清空原有会话、提醒和记忆。更多验证见 [只读工作台报告](docs/READONLY_WORKBENCH_ACCEPTANCE.md)。

## 文档与个人资料

在文件工作台勾选PDF、DOCX、TXT或Markdown，点击“阅读选中文档”查看带页码、段落或表格行引用的正文。抽取最多32 MiB单文件、200页PDF、200000正文字符；扫描件、加密文档和截断会明确提示。可加入聊天草稿请求整理学习笔记；发送前可以编辑。

“建立资料索引”默认只使用已有本地BGE，模型不可用时保留文字检索并提示。每批最多20份资料/500片段、每目录2000片段；可以查看和移除索引。检索保留原来源，文件修改后排除旧片段，重新索引即可。目录默认本地查看，明确共享后同一Agent可调用文档阅读和个人知识工具。

展开“PDF操作与DOCX转换”可合并、提取页面、旋转、图片转PDF及DOCX转PDF。生成文件和Markdown笔记都复用具体方案、原生确认、收据和撤销；目标已存在时拒绝覆盖。可绑定一个普通Obsidian资料目录作为笔记Vault，编辑结构化摘录草稿或粘贴聊天成果后预览保存，不修改已有笔记或内部配置。

本机LibreOffice转换引擎已校验并提取到项目本地目录。在新环境双击 **`准备文档处理.cmd`** 准备官方转换引擎；不安装系统应用、不上传文档。可通过 `HERTA_LIBREOFFICE` 指向已有的 `soffice.com`。缺少引擎时明确报错，其他文档功能仍可用。

## 学习、个性化与快捷共享

“学习”管理一次/每天/每周任务、长期目标、提醒关联、完成/延期/重开和历史；记录资料进度与复习，选择老师/面试官/背诵/复盘角色。复述先编辑语音转写，再对照原文的文字遗漏；不是模型语义评分。资料可关联已授权文档。

“个性”编辑人格补充、恢复默认、选择Piper或你的大黑塔GPT-SoVITS音色及参考语气；语音可暂停、继续、重播、停止。大黑塔声音在后台准备并复用模型，空闲5分钟释放；首次启动仍需等待准备。已修复短开头后正文丢失，准备后的本机短句合成约1.1秒，见[语音修复报告](docs/VOICE_PLAYBACK_FIX.md)。新环境用`准备大黑塔语音.cmd`准备独立推理环境；用户权重与录音不上传Git。

记忆可查看来源、修改、审核、启用或停用。Skills可从有完成记录的任务生成候选，或手写/由同一Agent提议，再编辑和审核；修改会重新待审核。只有审核启用的Skills进入统一上下文预算，不会训练模型、执行脚本或增加工具权限。

“快捷”或Ctrl+Shift+Space打开轻量面板，共享主窗口的当前会话。过期会话/草稿会拒绝提交，防止覆盖和发错位置。“附加”读取你主动复制的文字，或选择窗口/屏幕截图预览，在本机Windows OCR识别；核对后加入当前草稿，仍需自行发送。超过6000字明确截取，不后台监控剪贴板或屏幕。

“扩展”配置最多3个本机stdio MCP程序，指定绝对路径和工具白名单，原生确认后重启连接。只接入声明只读的工具，失败恢复此前配置；程序以当前用户权限运行，注解不提供系统隔离。配置不接收环境变量或密钥字段。

本机发行目录位于`release/Herta-20261012-portable`，完整目录约12GB，包含独立运行环境和现有模型。移动后仍可启动；通过`制作本机发行包.cmd`可以新建同类目录，`scripts/Package-Herta.ps1 -Lite`省去大黑塔推理资源。发行包按白名单排除个人数据库、密钥及导入音频。原项目入口保留已有数据；发行包默认新数据，可用HERTA_DESKTOP_DATA_DIR显式沿用旧数据。详细用法见[发行版说明](docs/PORTABLE_README.md)。

## 本机知识模型

项目内没有发现完整的千问模型。找到并接入的是 **BAAI/bge-large-zh**，位于：

```text
C:\Users\Administrator\.cache\huggingface\hub\models--BAAI--bge-large-zh\snapshots\b5d9f5c027e87b6f0b6fa4b614f8f9cdc45ce0e8
```

`auto` 默认发现本地模型；当前索引已用这个模型建立，20 个片段、1024 维。权重仅在本机加载，不自动下载；首次检索需要加载模型，之后复用。历史远端索引保留为独立版本。若权重移走，可用 `HERTA_LOCAL_EMBEDDING_MODEL` 指定完整模型目录。

显式配置非空 `HERTA_EMBEDDING_BASE_URL` 与 `HERTA_EMBEDDING_MODEL` 时，`auto` 选择远端服务。设置选择 `local` 可强制本地；`remote` 还需要独立的 `HERTA_EMBEDDING_API_KEY`。远端建库会发送知识片段，查询会发送问题。离线启动入口禁止远端建库。

启动器检查并复用配置匹配的索引；缺失时建立新版本。地址/模型改变后索引可能不匹配，需关闭应用再从启动器重开；索引不可用时界面明确提示，普通聊天仍能运行。人格文件加载失败或必需上下文超过预算会停止该轮。

## 数据与配置

| 内容 | 位置 |
| --- | --- |
| 桌面会话数据库 | `.local/desktop/sessions.sqlite3` |
| 日常偏好 / 提醒 / 记忆 | `.local/desktop/companionship.sqlite3` |
| 目录授权 / 空间分析历史 | `.local/desktop/workspace.sqlite3` |
| 本地语音权重和哈希清单 | `.local/voice/manifest.json` |
| 大黑塔角色音色资源（尚未接入推理） | `models/voice/the-herta/v2proplus/manifest.json` |
| 非敏感设置 | `.local/desktop/settings.json` |
| 版本化知识索引 | `.local/rag/` |
| 启动检查报告 | `.local/desktop/startup-report.json` |
| 人格 / 角色知识 | `persona/soul.md` / `knowledge/` |

Key 仅存在于主进程/后端环境，不进入 renderer、公共设置、索引或诊断。摘要作为有来源范围、哈希和算法版本的派生记录单独存储，不覆盖原始消息。Token 使用可替换的词法估算器，不能当作精确计费或保证实际模型窗口不溢出的依据。

## 可选只读 MCP

官方 MCP SDK 的 stdio 适配器将白名单工具加入同一个 Registry/Executor。当前支持最多3个显式配置的本机 Server，在“扩展”面板审阅并原生确认；要求绝对可执行路径、工具白名单及只读声明，副作用工具直接拒绝，失败恢复旧配置。示例见 [MCP 示例](examples/mcp/README.md)。可选扩展启动失败或通信损坏不会关闭普通聊天服务。

## 本地验收

V2.2–V2.6已实现文件执行、文档/知识、任务、人格/记忆/Skills、语音及共享等组件，但部分能力仍依赖面板，不能视为从聊天完成任务的完整Agent。当前优先补少量任务闭环，场景清单不再作为必须全部实现的要求，见[能力收敛审查](docs/AGENT_CAPABILITY_AUDIT.md)。既有本地回归仅证明各自覆盖的接口与流程；真实模型任务路由尚未确认。[历史组件报告](docs/PRODUCT_COMPLETION_REPORT.md)与[语音修复报告](docs/VOICE_PLAYBACK_FIX.md)保留原验收边界。旧SQLite与音频保留；私人便携目录为`release/Herta-20261012-portable`，继续原会话请使用项目根目录启动入口。

清理版基线为247项后端、49项前端单元和14项Electron E2E，见[清理验收报告](docs/MUSIC_REMOVAL_ACCEPTANCE.md)。E2E 使用真实 Electron/Python/HTTP/SQLite 和离线模型夹具，不冒充真实回答质量。

2026-10-09 旧首版基线为223项后端、35项前端单元和11项Electron E2E；当前计数以陪伴版报告为准。

本地 BGE 在既有 28 题检索集上覆盖了全部 21 个指定证据单元，4 个跨段问题都覆盖了所需片段。摘要对照验证了预算和文字保留行为；模型理解、工具路由、答案正确率、实际 Token 和费用仍未验收。详见 [评测报告](docs/HARNESS_EVAL_REPORT.md) 和 [实施状态](docs/IMPLEMENTATION_STATUS.md)。

```powershell
Set-Location -LiteralPath 'D:\Desktop\herta-agent'
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\.venv\Scripts\ruff.exe check backend evals/harness
.\.venv\Scripts\ruff.exe format --check backend evals/harness
.\.venv\Scripts\python.exe evals/harness/run_offline.py
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run test:e2e
```

本地检索复现（强制使用本地，禁止误选远端）：

```powershell
$env:HERTA_EMBEDDING_PROVIDER = 'local'
.\.venv\Scripts\python.exe -m herta_agent.rag eval --mode retrieval --split all --output .local/rag/reports/local-bge-validation.json
```

## 重建开发环境

当前机器可直接启动。需要重新安装时，使用 uv 和 Node.js：

```powershell
Set-Location -LiteralPath 'D:\Desktop\herta-agent'
$env:UV_PYTHON_INSTALL_DIR = Join-Path (Get-Location) '.local\python'
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.local\uv-cache'
$env:UV_PROJECT_ENVIRONMENT = Join-Path (Get-Location) '.venv'
uv sync --project backend --extra dev --extra local --python 3.12 --locked
npm --prefix frontend ci
npm --prefix frontend run build
```

Python 3.12.13，Node 22.16.0，锁文件为 `backend/uv.lock` 和 `frontend/package-lock.json`。本地模型权重不包含在 Git 或安装依赖中；需保留上面的缓存目录。

原 CLI 与服务入口仍可使用：

```powershell
.\.venv\Scripts\python.exe -m herta_agent --demo-tools --message '你好，黑塔'
.\.venv\Scripts\python.exe -m herta_agent.service --provider demo
```

CLI 默认离线；持久服务默认监听 `127.0.0.1:8765`，数据库与桌面入口分开。独立服务配置见 [Phase 5 教程](docs/phase-5-walkthrough.md)。

## 设计与学习

- [Harness 设计](docs/HERTA_HARNESS_DESIGN.md)、[源码映射](docs/HERMES_SOURCE_MAP.md)、[首版执行计划](docs/V1_IMPLEMENTATION_PLAN.md)。
- [桌面设计](docs/phase-6-ui-design.md)、[RAG 教程](docs/phase-4-walkthrough.md)、[Hermes 分析](docs/hermes-analysis.md)。

服务单机单用户。任务、文档、可审核Skills、可切换音色、主动共享/OCR及最多3个只读MCP服务已接通。此版本不提供任意Shell、默认全盘修改、复杂GUI自动化或自动训练模型。音乐业务已永久取消；Live2D和代码协作不进入当前方向。真实聊天与模型效果验收按用户要求暂缓。
