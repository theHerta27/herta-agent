# Herta V2 剩余里程碑持续实施计划

> 执行者使用 executing-plans 在现有会话内逐任务实现；用户已明确要求持续推进直至完成，只有必要问题才询问。

**Goal:** 完成产品规划 V2.2–V2.6，形成可直接使用的 Windows 个人助手。

**Architecture:** 复用当前单一 Agent、Context Engine、RAG、SQLite、窄 Electron 桥与语音协调。确定性事务由本地服务承担；模型只读取授权资料、提出待确认方案/记忆/Skills。第三方语音推理独立进程与环境。

**Spec:** `docs/herta-agent-plan.md`；V2.2另依据 `docs/superpowers/specs/2026-10-12-file-workbench-design.md`。

## 全局约束

- 用户最新授权为连续实施，不逐批请求设计批准或询问是否继续；文件执行的原生确认是产品功能，开发测试只操作独立夹具。
- 仅本地验收，禁止真实 DeepSeek/远程 Embedding 请求；允许准备公开依赖和本机模型。密钥不显示。
- 音乐已永久取消；不新增 Live2D、代码协作或任意 shell 执行。
- 保留已有数据和能力；每批增量迁移，兼容旧 SQLite。
- 已有 Windows 目录句柄与拥有式线程 IO 是文件能力的基础，不能退回普通路径快照。
- 每项行为先写并观察失败测试，再实现；任务定向验证，关键阶段全量回归，最终一次独立审查。
- 各里程碑保存本地提交，不自动推送或合并；原两份未跟踪用户文档不变。

## Review Focus

1. 授权变化、并发确认、文件被编辑/替换、锁定文件及崩溃窗口不得覆盖后续用户工作；重点检查保留目录句柄时目标父目录被FSCTL_SET_REPARSE_POINT原位改变的情况，以及mkdir是否与叶子文件一样绑定目录对象。
2. 大文档/扫描件/损坏附件、抽取截断、引用和模型共享范围应准确；缺依赖时不得假称成功。
3. 重复任务、时区、重开与进度修订不应丢失提醒、历史或用户设置。
4. Skills/人格/文件资料不能扩展工具权限；学习经验只有审核后成为未来上下文。
5. 语音 Provider 切换、取消、暂停/重播、快捷面板/截图取消与退出必须清理自有资源。

## Task 1：V2.2受控文件操作

文件：新增 `workspace/file_plans.py`、`workspace/file_jobs.py`、严格模型、测试 `test_file_plans.py`；更新既有 router/service/tools 与 Electron/工作台。

接口：`propose(root_id, operations)` 返回不可变 plan/digest/source snapshots；`confirm(plan_id,digest,request_id)` 幂等返回 owned job；`cancel`、`jobs`、`preview_undo` 与再次原生确认。读取授权根ID与同一工作台SQLite；只允许普通文件 copy/move/rename/mkdir，拒绝覆盖、工程内部与硬链接，100动作/256MiB单文件/1GiB总量、10分钟有效。

- [x] RED：预览不修改、源变化/冲突/撤销拒绝、执行/收据/幂等、取消/崩溃/条件撤销。
- [x] GREEN：先持久intent，句柄保护下独占目标/分块复制，真实收据；退出拥有并等待任务。
- [x] Electron：勾选文件、手工/按类型预览、完整原生确认、任务与撤销；同Loop仅可提出方案。
- [x] 验证 unittest定向、前端定向/Electron文件回归与静态检查，提交。

## Task 2：V2.3文档与个人知识

文件：新 `documents/` 抽取/转换/个人索引服务、路由与工具；前端文档与知识工作区。

接口：沿用授权root+相对路径，只读PDF/DOCX/TXT/MD，page/paragraph引用、有界抽取；PDF合并/拆分/旋转/图片转换与DOCX→PDF输出新文件，复用Task1审批/收据；授权Vault中保存笔记，个人资料默认本地，明确共享后可检索进入同Loop。复用本地Embedding，不远程建库。

- [x] RED/GREEN：实际生成PDF/DOCX夹具、损坏/截断/范围拒绝、转换与笔记审批、检索与来源/撤销。
- [x] 验证依赖可用，补完整阅读→检索/总结草稿→保存闭环、Electron与定向检查，提交。

## Task 3：V2.4学习与任务

文件：新 `productivity/` store/router/tools/context、桌面学习与任务面板。

接口：短期任务/长期目标/重复规则、日期时区、完成/延期、既有提醒关联；学习材料链接和进度、复习建议、老师/面试/背诵/复盘角色共用Agent。ASR先填可编辑转写，按原文对照遗漏，不冒充模型评分。

- [x] RED/GREEN：持久任务/提醒同步、重复完成下一次、修订与重开、角色与进度/复习、语音文本纠错。
- [x] Electron端到端创建→完成/延期→复习流程，定向与全量回归，提交。

## Task 4：V2.5人格、语音、记忆与Skills

文件：扩展persona/companion context/store、Skills服务与面板；本机TTS Provider适配与独立GPT-SoVITS环境/启动脚本。

接口：可编辑人格/称呼/任务角色；记忆修改/来源/停用；Skill草案、审核、保存、加载/停用，依据任务历史生成候选，共用上下文预算且不更改权限。Piper和大黑塔Provider可切换，角色推理采用拥有式stdio独立进程、原音色资产校验后使用；暂停/重播/停止/切换取消。

- [ ] RED/GREEN：人格与Skill生命周期、来源/范围、注入不扩大权限；两Provider与取消/错误、暂停/重播。
- [ ] 准备独立GPT-SoVITS公开依赖/基础模型，真实本机生成大黑塔语音，记录兼容性与哈希，不改用户权重字节、不使用无限制反序列化。
- [ ] Electron语音与个性化闭环，定向/全量，提交。

## Task 5：V2.6随处唤起与发行

文件：Electron快捷面板与主动共享/截图OCR、扩展设置、启动/构建/发行脚本及使用说明。

接口：托盘快捷键保留，轻量输入面板直接共享同一聊天状态；用户主动附加选中文字或截图，显示预览和发送确认；本地OCR或配置的视觉能力按需处理；只读MCP增加可配置已审列表而不放开副作用。

- [ ] RED/GREEN：快捷面板/主窗口会话一致、共享取消/截断/截图OCR、桥与CSP保护、MCP设置验证、退出与重开。
- [ ] 完成可直接启动/打包的Windows版本、完整本地后端/前端/Electron回归、文档与实际能力对照。
- [ ] 一次全变更只读独立审查，重要问题一轮RED→GREEN修复，再完整回归、最终本地提交。

## 接口预检

Task1→2：新输出与笔记使用同样具体方案/确认/收据，文本与文档读取继续root守卫。
Task2→3：学习材料引用root+相对路径+正文来源，不引入第二Loop。
Task3→4：任务角色与长期上下文统一预算；Skill不能自动授予文件执行。
Task4→5：快捷面板共享已有语音generation/会话状态；新增桌面窗的IPC必须逐窗鉴权。
