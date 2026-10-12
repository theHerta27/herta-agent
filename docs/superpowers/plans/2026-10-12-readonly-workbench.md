# V2.1：只读文件工作台与大黑塔音色资源

依据：`docs/herta-agent-plan.md`，用户于 2026-10-12 明确要求开始实施；本批次完成 V2.1，并整理后续 V2.5 所需音色资源。实现者在当前 `phase-6-ui` 内联执行。

## 全局约束

- 仅本地验收，不调用 DeepSeek 或远程 Embedding。继续使用单一 Agent Loop。
- 不写入、搬移或删除工作台选择目录中的任何文件；用户单独授权的音色资源规范化除外。
- 原有 SQLite、语音、提醒、专注、记忆、设置和人格保持兼容。音乐方向已取消。
- 授权目录由 Electron 原生选择器产生；主进程独有随机令牌保护目录授权 API。聊天共享默认关闭，开启前明确提示内容可能发送给所配置模型。
- 禁止路径穿越、设备/网络路径、符号链接与重解析点；读取文本时保护敏感目录及工程内部依赖。快捷方式只识别，不解析目标。
- 有界分析、可取消、记录历史、重启后标记中断；实际磁盘空间与扫描的逻辑文件大小分别显示。
- 不把角色权重提交到 Git，不改权重字节，不使用无限制 pickle 加载。Piper 继续可用。

## Task 1：目录授权、读取与工具

接口：WorkspaceService 持久化 root id/path/identity/shared/active；list/search/read 接受不透明 root id 与相对路径；工具只看到明确共享的 root。

先写失败测试：越界/敏感文件/链接、授权撤销、持久化、只读原文件哈希、默认禁止 Agent 读取。实现路径检查、独立 workspace.sqlite3、保护路由与工具，并接入既有 Agent 与生命周期。

验证：`.venv/Scripts/python.exe -m unittest discover -s backend/tests -p test_workspace.py`。Expected: 新行为测试从 RED 变 GREEN。

## Task 2：有界磁盘分析

接口：start(root, duplicates)、jobs、cancel；报告提供文件与目录排行、项目/缓存提示、重复候选、扫描限制、跳过计数和 total/used/free。

先写失败测试：相同内容候选、项目识别、敏感/链接跳过、限制与取消、重启中断。实现单个活动分析，后台线程协作取消；退出等待自有线程结束；每次 IO 重新验证根身份和授权。

验证：同 Task 1 全测试。Expected: 报告正确且原文件 SHA 不变。

## Task 3：Electron 与文件工作台

接口：DesktopBridge.workspace 固定方法；主进程固定 API 客户端带令牌；选择器不接受 renderer 指定路径。React 对话框浏览/搜索/文本预览/加入草稿/共享/撤销/分析与历史。

先写失败单元测试及 Electron 场景；保持现有设计和语音停止机制。分析中禁止设置重启，原生共享确认说明远程发送边界。

验证：frontend 单测、TypeScript、lint、build、Electron 全回归。Expected: 新场景和既有语音/提醒全部通过。

## Task 4：音色资源规范化

将用户授权的 7 个文件整理到忽略目录 `models/voice/the-herta/v2proplus`，记录原名、SHA256、音频参数和参考文本来源。保留原 ZIP，移动前后比对每个 SHA256。

核对 GPT-SoVITS 官方 v2ProPlus 特殊头与配置类；只用受限加载，内存适配文件头，原文件不改。资源就绪与真实推理就绪分别记录；本批不安装未经验证的 GPT-SoVITS 运行环境。

验证：全部 SHA 一致、资源清单可复验、原 ZIP 保留。Expected: 两组权重受限读取结果或明确具体限制，不能宣称已生成大黑塔音色。

## Task 5：交付

更新 README/产品计划/验收报告；运行后端、前端和 Electron 回归及格式检查。一次全变更独立审查，重要问题一轮修复并复验，次要项登记。保存本地提交，不自动推送。

## 接口预检

- Task 1 → 2：根身份/撤销与读取统一检查；报告仅记录相对路径。
- Task 1/2 → 3：固定桥方法，不向 renderer 暴露授权令牌；settings active count 包含分析。
- Task 4 → 5：模型文件在忽略目录，清单摘要与集成状态进入文档。
