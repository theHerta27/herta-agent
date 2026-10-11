# Herta Agent

Windows 本地桌面陪伴助手，保留大黑塔人格、持续会话与知识检索，新增本地音乐、语音、提醒和可管理记忆。Electron 管理本机 Python 服务；Agent Loop、工具执行、上下文预算与 SQLite 历史均由 Herta 自己实现。工程机制主要参考项目中的 Hermes 源码，Cyrene 用于产品功能思路。

## 现在就用

本机依赖和桌面构建已准备好。在项目目录双击：

- **`启动离线演示.cmd`**：完全离线，验证聊天界面、会话、停止与历史恢复；回答是明确标注的演示回显。
- **`启动Herta.cmd`**：使用已配置的聊天服务。默认 `https://api.deepseek.com`、`deepseek-flash`；优先采用显式 `HERTA_API_KEY`，否则读取 `DEEPSEEK_API_KEY`。启动器会补读 Windows 用户级环境变量，无 Key 时在本机窗口中遮蔽输入，仅用于本次启动。

切换演示/真实模式时先从系统托盘右键选择“退出 Herta”。当前交付按用户要求只进行本地验收。使用真实聊天入口并发送消息会调用配置的服务；本次最终回归使用离线 Provider，没有继续真实问答或真实效果评测。

启动后可新建/切换会话、发送消息、查看流式回答，点击停止取消当前运行。展开工具活动可查看检索片段与原始来源；展开上下文活动可查看预算、保留消息、摘要与证据引用。关闭窗口后留在系统托盘，音乐和提醒继续运行；双击托盘或按 Ctrl+Shift+H 唤出窗口。托盘“退出 Herta”才清理自管后端，重开后恢复已完成的历史。

右上角设置可修改聊天地址/模型、Embedding 模式、上下文窗口、输出预留与旧历史摘要。保存会重启自管服务；有运行时拒绝修改，失败会恢复此前设置。设置页面不接收或显示 API Key。

## 日常陪伴

点击右上角“日常”：

- **本地音乐**：导入音频文件，播放/暂停、上一首/下一首和调节音量。歌曲仍位于你选择的位置，移动后需重新导入。音乐状态显示实际播放结果。
- **提醒与专注**：添加一次、每天或每周的北京时间提醒；到期后可以“知道了”或延后10分钟。45分钟专注会创建休息提醒，有音乐时继续播放。完全退出期间不执行，重开时补一条错过的提醒，重复计划继续按原时间运行。免打扰保留未读提醒并推迟系统通知；Windows 通知是否展示取决于系统设置。
- **本地语音**：点击“录音”，结束后在消息框编辑识别文字，再发送。每次最长60秒；每条回答可朗读、停止，也可开启自动朗读新回答。录音和朗读压低音乐音量，结束后恢复。当前机器的模型与依赖已准备好，识别和合成全程在本机执行。
- **偏好与记忆**：编辑称呼、音量、自动朗读、日常工具开关和免打扰；可以重置偏好。新增记忆先待确认，点击保存后才进入以后每轮上下文，可随时删除。

聊天共享原有 Agent Loop，新增7个日常工具：创建/查询/取消提醒、搜索本地音乐、播放控制、查询实际播放状态和提出待确认记忆。可在偏好中关闭日常工具；只读 MCP 的原有权限门禁继续有效。离线演示只验证界面和确定性功能，不会理解自然语言并选择工具；同一执行循环中的工具调用已用离线夹具验证，真实模型的自然语言路由暂未验收。

在新环境启用语音，双击 **`准备本地语音.cmd`**：按锁文件安装可选依赖，再下载公共 Whisper/Piper 模型到 `.local/voice`。日常运行不会自动下载模型，缺失时显示不可用。模型来源、版本、文件哈希和现有验收见 [陪伴版报告](docs/COMPANION_ACCEPTANCE.md)。

## 本机知识检索

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
| 日常偏好 / 提醒 / 记忆 / 音乐索引 | `.local/desktop/companionship.sqlite3` |
| 本地语音权重和哈希清单 | `.local/voice/manifest.json` |
| 非敏感设置 | `.local/desktop/settings.json` |
| 版本化知识索引 | `.local/rag/` |
| 启动检查报告 | `.local/desktop/startup-report.json` |
| 人格 / 角色知识 | `persona/soul.md` / `knowledge/` |

Key 仅存在于主进程/后端环境，不进入 renderer、公共设置、索引或诊断。摘要作为有来源范围、哈希和算法版本的派生记录单独存储，不覆盖原始消息。Token 使用可替换的词法估算器，不能当作精确计费或保证实际模型窗口不溢出的依据。

## 可选只读 MCP

官方 MCP SDK 的 stdio 适配器将白名单工具加入同一个 Registry/Executor。首版仅支持一个显式配置的本机 Server，要求绝对可执行路径、工具白名单及只读声明；副作用工具直接拒绝。示例和配置步骤见 [MCP 示例](examples/mcp/README.md)。可选扩展启动失败或通信损坏不会关闭普通聊天服务。

## 本地验收

2026-10-12 陪伴版回归：**243项后端、46项前端单元、14项Electron E2E全部通过**；Ruff、TypeScript、ESLint和桌面构建通过。详见 [陪伴版报告](docs/COMPANION_ACCEPTANCE.md)，包含本地语音、提醒、音乐和最终独立审查修复。E2E 使用真实 Electron/Python/HTTP/SQLite 和离线模型夹具，不冒充真实回答质量。

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

服务单机单用户。当前记忆只保存用户确认的短文本；自动经验提炼与可复用 Skills、个人资料导入、网页操作、多 Server、任意 Shell/文件写入、独立安装发行包仍为后续范围。Live2D 和代码协作不进入当前产品方向。完整真实模型效果验收按用户要求暂缓。
