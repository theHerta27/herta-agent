# 移除音乐业务实施计划

> **For agentic workers:** Use superpowers:executing-plans inline, task by task. 用户已明确要求完成代码清理、不重新设计产品；按本次确定范围执行，不再请求方向或计划批准。末尾仅一次独立只读审查。

**Goal:** 彻底撤销音乐业务并保留语音、提醒、专注、记忆、设置及旧数据。
**Architecture:** 删除音乐工具/API/IPC/协议和UI；AudioCoordinator保留为纯语音模块；CompanionStore仅在读取旧偏好时忽略废弃字段，既有数据库和音频文件不删除。
**Tech Stack:** 既有Python、SQLite、FastAPI、Electron、React/TypeScript；不新增依赖。
**Spec:** 用户2026-10-12本次移除清单、保留清单及数据兼容要求；docs/herta-agent-plan.md按本次决定修订。

## Global Constraints
- 不重设产品，不增加替代播放器/音乐Agent/MCP控制。
- Piper/faster-whisper、朗读/录音/停止/取消/会话切换/错误提示保留。
- 旧数据库不清空，旧曲库表/播放记录不再读取或创建；旧偏好volume不改作语音音量。
- 提醒、45分钟专注、记忆、用户其他偏好及会话保留；原音频文件不删除。
- 验收仅本地，不调用真实聊天/Embedding服务；不推送/合并。

## Review Focus
- 旧偏好带volume、旧desired=playing：启动不报错、不自动播音频，其他偏好不变。
- 改偏好/重开：提醒、候选和确认记忆、交付记录、会话数据库与原音频内容不受影响。
- 纯语音协调仍防止迟到合成、停止后晚启动、跨会话转录与继续播下一段。
- 后端重启不会恢复废弃播放或丢失语音订阅；专注只创建45分钟提醒。
- 运行源码/编译产物无音乐入口；只在旧数据兼容夹具与退役记录出现必要旧字段名。

### Task 1: 后端移除与旧数据兼容
**Files:** companion/models.py、store.py、router.py、tools.py、context.py；tests/test_companion.py、test_companion_api.py、test_music_retirement.py；service/app.py错误提示。
**Interfaces:** snapshot只含preferences/reminders/deliveries/memories；Preferences移除volume；剩余4个日常工具，未知音乐工具返回unknown_tool；旧音乐HTTP路由404。
- [x] 加入旧SQLite快照/文件保留、偏好更新/重开、全音乐路由失效与工具不可调用测试；观察失败。
- [x] 删除音乐models/schema创建/handlers；仅_read preferences丢弃旧volume，不触碰旧表或播放记录。
- [x] 移除过时音乐正向测试，保留提醒/身份授权等覆盖；定向测试通过。

### Task 2: 纯语音协调与桌面清理
**Files:** shared/contracts.ts；electron/companion.ts、main.ts、preload.ts；index.html；audio/coordinator.ts；state/companion-runtime.ts；CompanionPanel/App/CSS；unit/audio/companion/runtime；e2e/companion.spec.ts。
**Interfaces:** AudioCoordinator(bridge,createAudio)；无music/apply/report，只在朗读时创建Audio；focus仅create_reminder；桥接保留日常/voice接口。
- [x] 增加拒绝旧action/volume、专注不播放、不因快照创建Audio及纯语音行为测试，观察失败。
- [x] 删除播放器/音量偏好/音乐IPC/协议/CSP及音乐类名，保留音频blob与麦克风权限。
- [x] 更新真实Electron：从旧数据库启动、偏好/提醒/记忆/专注保持；没有旧IPC/protocol；现有语音3类场景不退化。
- [x] 单元/typecheck/lint/build及定向桌面测试通过。

### Task 3: 文档、全量回归与交付
**Files:** 用户docs/herta-agent-plan.md；README、PERSONAL_ASSISTANT_ROADMAP、COMPANION_ACCEPTANCE、IMPLEMENTATION_STATUS、companion设计/旧计划/Hermes映射及规划笔记；新docs/MUSIC_REMOVAL_ACCEPTANCE.md。
- [x] 删除产品规划音乐章节、其他音乐建议与过时使用描述；保留语音播放器措辞和语音未来设置。
- [x] 给出后续任务顺序：只读桌面/磁盘→受控文件执行→文档与个人知识→学习/待办→语音/记忆/Skills→按需桌面扩展；本轮只清理音乐。
- [x] 全量后端、前端单元、Electron及Ruff/TS/ESLint/build；检查源码与构建产物残留，记录真实计数。
- [x] 一次独立只读审查，重要发现一次修复并失败→通过验证；保存报告、本地提交，不推送。
