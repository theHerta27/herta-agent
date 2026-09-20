# Phase 3 实施计划

依据 phase-3-design.md 和用户已确认的 A 策略实施；在 phase-3-context 分支继续 Phase 2，main 与 phase-2-tools 不移动。

1. 写 Context/Persona 测试：全文/BOM/CRLF、失败不请求、修复可复用、单 Run 固定快照、下轮更新、历史和工具配对不变。运行观察缺失接口失败。
2. 新增 runtime/context.py 与 persona.py，实现小型 Builder 协议、冻结快照、显式文件加载。修改 Agent 只委托快照，不包含人格文件操作；Session/RunResult 记录哈希。运行测试。
3. 整理 data/derived/persona_evidence.jsonl、来源说明与 persona/soul.md；原始文件不变。检查原文定位和输入哈希。人格约束与原文观察区分。
4. CLI 增加 --soul（默认项目资源路径），两种 Provider 都必须装配文件 Builder。测试项目目录外启动、路径带中文空格、缺文件停止、交互修复继续，以及 HTTP 全文注入。继续保留 Phase 2 行为。
5. 执行完整 unittest/Ruff、独立审查，更新架构/README/复现教程和进度。真实模型未联调则明确记录，停在 Phase 3。

无需新依赖，不实现 RAG、Memory、Skills、MCP、UI；不自动提交或推送本轮成果。
