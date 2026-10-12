# 受控文件执行本地验收

2026-10-12，基于 phase-6-ui 的只读工作台增量实现 V2.2。

支持普通资料文件复制、移动、改名和按类型整理。用户在工作台审阅完整相对路径列表，原生确认使用后端保存的方案、目录路径和 SHA-256 摘要；模型工具只能生成预览。有效期10分钟、100动作、单文件256 MiB、总量1 GiB，不覆盖目标、不执行任意删除或 Shell。

Windows IO 使用目录句柄绑定叶子文件，祖先不共享删除权限，普通文件不共享写入/删除。独占临时副本校验后发布；每个动作先写 intent，再保存真实完成收据。取消只停止未完成部分，进程重开标记中断而不盲目重试。复制/移动可条件撤销，拒绝用户后续编辑或新文件；仅删除该任务创建且仍为空的目录。

测试涵盖预览无修改、摘要/授权失效、来源变化、大小写冲突、重复移动、硬链接/工程保护、目录相对句柄、取消副本、崩溃收据、幂等、条件撤销以及同一 Agent Loop 提案与共享撤销。Electron 使用独立临时资料目录，完成取消确认→复制→收据→撤销闭环。所有聊天使用离线 Provider，无远端聊天/Embedding 验收。

后端全量279项通过；新增同Loop边界验证后文件定向14项通过。前端55项单元、TypeScript、ESLint及构建通过；文件工作台3项Electron通过。全量桌面结果随持续产品开发报告更新。

SQLite 只增量建表和目录授权版本列。原提醒、记忆、会话及用户音频不删除。音乐业务仍保持移除状态。

文件/文档集成后的完整Electron18项已通过；后端全量292项通过，文档新增引用案例另有定向12项通过。后续版本继续在此基线上增量实现。

原生 API 依据：[CreateFileW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)、[OBJECT_ATTRIBUTES](https://learn.microsoft.com/en-us/windows/win32/api/ntdef/ns-ntdef-_object_attributes)、[NtSetInformationFile](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/nf-ntifs-ntsetinformationfile)。
