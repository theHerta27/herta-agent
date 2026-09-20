# Phase 3 最小设计：Context Builder 与稳定人格

状态：已实现并验证，52 项测试通过。用户选择 A：soul.md 是 CLI 必需运行条件，失败停止当前轮，保留会话供修复后重试。

## 目标与已有约定

从 Phase 2 的 Agent.run 抽出上下文构建，用可注入组件把稳定 system context 与有序历史组合。CLI 装配 persona/soul.md，每次模型请求都包含其全文。Runtime 不硬编码角色名、人格规则、文件路径或角色判断。

既有 architecture.md 第 7 节已规定每个 Run 重新读取 soul.md、记录哈希、同一 Run 的全部 Step 使用同一份内容。不逐 Step 重新读文件、不截断 Persona、不将其加入 Session 历史或向量检索。

保留 Phase 2 工具闭环、预算、取消后配对与继续聊天。当前不引入 RAG、长期 Memory、Skills、MCP、UI、通用模板引擎或自动人格评估平台。

## 三种实现取舍

1. **推荐：独立 Builder + 每 Run 不可变快照**。Builder 负责加载，快照负责 system + history 组合；Agent 只调用小接口。既能保证一轮稳定，也能下轮读取手动编辑后的 soul。
2. 启动时固定全文。代码更少，但必须重启才能更新，偏离已有每 Run 读取约定。
3. 每 Step 读文件。容易在工具执行前后产生不同人格，破坏同一轮可复现性，不采用。

## 组件边界

| 文件/产物 | 职责 |
| --- | --- |
| backend/herta_agent/runtime/context.py | Context Builder 接口、不可变快照、system 与 history 组合；普通静态上下文实现用于通用 Runtime 与测试 |
| backend/herta_agent/persona.py | 从显式 Path 读取完整 UTF-8 soul，验证非空，生成快照；不读取原始材料或 evidence |
| backend/herta_agent/runtime/agent.py | 注入 Builder；Run 开始获得快照，每 Step 请求快照构建消息；不拼接 Persona 文本 |
| backend/herta_agent/__main__.py | 默认装配项目 persona/soul.md，支持 --soul 显式路径；不依赖终端当前工作目录寻找默认文件 |
| persona/soul.md | 从证据提炼的行为规则、边界与少量原创示例 |
| data/derived/persona_evidence.jsonl | 人工整理的 dimension / observation / behavior_rule / confidence / source，可定位至原文件行号、章节与原链接 |
| docs/phase-3-walkthrough.md | 新增文件、运行路径、精读函数、PowerShell 复现步骤、测试证据与真实模型验证边界 |

普通静态 Context Builder 是通用 Python Runtime 的默认实现，维持直接 Agent(provider) 调用兼容；用户 CLI 显式装配文件 Persona，两者不混淆。测试可注入固定内容，不需要从磁盘读取生产人格。

## 内容与来源

原始两份 Markdown 保留原位，不修改、不复制进 Runtime。只根据用户提供的原文做归纳，不新增未经核实的角色经历。证据文档引用文件、行号/故事章节和原链接，并记录输入哈希。

soul 使用已约定九节：Identity、Core Personality、Intellectual Attitude、Values、Social Behavior、Speaking Style、Behavioral Rules、Boundaries、Style Examples。以行为规则为主，不复制长台词或整段故事，不创建人物关系知识库。

原文观察与产品适配区分：研究导向、自信与幽默是角色证据；完整解释技术问题、不假装工具成功、不过度贬低用户、承认真实未知等是让角色适合协作助手的明确约束，不能冒称为逐字原作结论。

## 快照、消息与路径

- 一个 Run 一份快照，全 Step 复用；下一 Run 才观察文件变化。
- system message 在每次请求最前方出现一次，历史不被改写；工具调用与结果保持原顺序和 id。
- 哈希基于实际注入的 UTF-8 文本，明确处理 BOM/Windows 换行的规则并测试；不把时间或路径拼入 system，避免无意义变化。
- 哈希作为运行诊断信息展示/记录，不塞进用户或工具消息；不引入完整持久化 Run 系统。
- 默认路径基于源码项目位置解析，显式 --soul 路径支持 Windows 空格与中文；安装/打包资源分发留到后续阶段，不能默默寻找 Hermes 的 SOUL。

## 已确认的加载失败策略

当文件缺失、为空、不可读或不是有效 UTF-8：

- 用户选择 A：报出可理解的 Context/Persona 错误，不发模型请求；交互模式保留会话，修复后下一轮可重试。不存在自动降级或沿用上次缓存的路径。

加载契约：UTF-8（可带 BOM），移除文件开头 BOM，保留正文与 CRLF，不 strip/模板替换/截断。Markdown 作为完整文本使用，不引入 Markdown AST 或 YAML front matter 解析器；解析失败指无效 UTF-8 或包含 NUL 的非文本内容。缺失、目录路径、权限错误和纯空白均为明确错误。

遵循 Phase 2 失败历史规则：保留该轮已提交的 user 消息，不伪造 assistant；释放忙碌标记。Session.context_hash 记录最近一次 Run 成功加载的快照哈希；新 Run 开始先清空，加载失败保持 None，避免误报上轮哈希。RunResult 携带 context_hash，CLI 显示诊断行。哈希只针对注入正文。

## 验证计划

覆盖完整 Unicode/Markdown 原文注入、BOM/CRLF、空白/缺失/损坏文件、每 Run 加载一次、工具中间改文件不影响当前 Run、下一轮生效、一个 system 且历史不污染、替换 Builder 后 Agent 仍可工作、取消/失败后复用、HTTP 请求确实携带 soul 全文、不同工作目录启动及显式路径。

继续运行所有 Phase 2 测试。离线演示仍明确标为固定逻辑，不能把上下文注入测试等同于“真实模型人格表现已验证”。Persona 风格通过教程中的人工场景检查，当前没有真实模型配置时如实保留此边界。
