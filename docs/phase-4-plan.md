# Phase 4 最终实施计划

目标：在现有 Windows Agent 上接入有来源、可独立检查和评测的角色事实 RAG。

依据：[最小设计](D:/Desktop/herta-agent/docs/phase-4-design.md)。用户现已授权编码，独立配置远程兼容API；采用TDD按任务逐项验证。Embedding适配器与本地索引可按明确接口分工实现，最终统一集成审查。

技术边界：Python 3.12、Pydantic、asyncio、HTTPX；只新增NumPy用于矩阵检索。仅一个远程Embedding适配器，Key仅来自环境且不序列化；不实现本机模型。词面baseline不在必做清单内。

## 实施状态

| 工作 | 结果 |
| --- | --- |
| Task 1–5：切分、适配器、索引、检索、Tool | 工程实现完成，93项总回归通过 |
| Task 6：评测代码与固定题集 | 完成，直接检索与正式聊天分开报告 |
| Task 6：实际服务合约、dev校准、check与聊天效果 | **未执行**：当前本地进程缺少服务配置；不以mock成绩替代 |
| Task 7：文档、静态检查、审查 | 完成；见phase-4-walkthrough.md，真实服务相关手动路径待验收 |
| 分支与阶段 | 本地phase-4-rag；未提交、推送或合并，停在Phase 4 |

以下任务保留最初实施顺序和检查目的；实际完成状态以上表及教程验证记录为准。

## 已完成的准备

- [x] 收敛范围：现有角色事实/人物关系/故事事件，不扩充语料。
- [x] 整理 knowledge/herta.md 的20个证据单元及 sources.json。
- [x] 整理28个带预期证据与行为的评测题，区分 dev/check。
- [x] 写清 Tool 主动触发、向量精确检索、来源与工程/语义评测边界。
- [x] 确定独立远程兼容API，补齐设计第9节；实际服务/模型输入约束留待本地配置验证。
- [x] 用户授权后已从Phase 3建立phase-4-rag；main/已有远端分支未移动。

## 全局约束

- 保留52项 Phase 1–3 回归；不改 soul.md 必需加载、快照及取消行为。
- 正文只索引 knowledge/herta.md；禁止把评测题/答案、Persona 和README混入。
- 原始快照不变，K01–K20来源可核对；不伪造遮蔽信息或抓取新语料。
- Agent Loop 不实现检索算法、路径选择或关键词路由。
- Windows 原生路径/异步方式；无 bash、fork、Unix信号或常驻数据库。
- 不静默换 Embedding、不词面降级、不在聊天请求内建库。
- 下列模块和命令已落地，具体CLI参数见教程。

## Task 1：模型、输入与确定性切分

计划新增 rag/__init__.py、rag/models.py、rag/ingest.py、tests/test_rag_ingest.py。

- [ ] 先写失败测试：白名单、未知/重复K编号、missing source、BOM/CRLF、中文路径、短段完整、长段按句界切分与80字符重叠、偏移映射、清洗后稳定hash、空库。
- [ ] 实现 source manifest/Chunk 验证类型；拒绝不在指定知识目录内的正文路径，不扫描整个仓库。
- [ ] 实现600字符上限的确定性切分，保留标题和K单元；标题作为编码上下文计入编码器长度预算，引用位置不包含合成标题。
- [ ] 运行针对性测试，inspect 输入产物；验证所有原始来源位置，原文件hash不变。

## Task 2：Embedding 单一适配器

新增rag/embeddings.py、tests/test_embeddings.py，修改config.py；远程运行方式已确认。

- [ ] 明确文档/查询编码模式、模型名、服务标识、维度与最大输入；所有值由同一配置指纹记录。不要假设聊天API Key或模型可直接用于Embedding。
- [x] 先写失败测试：批响应数量/顺序、错误索引、空/零/非有限向量、不同维度、HTTP错误/超时、取消与凭据脱敏。仅远程方案，用MockTransport。
- [ ] 只实现选定后端，保持 embed_documents/embed_query 小接口；没有隐式重试或模型切换。
- [ ] 验证测试通过；用户本地配置后再做小规模真实服务合约验证。mock不能替代这一项。

## Task 3：本地索引与发布

计划新增 rag/store.py、tests/test_rag_store.py，按已定执行方式更新 pyproject.toml 与 uv.lock。

- [ ] 先写失败测试：向量/metadata行数错位、manifest缺字段、模型/编码指纹不符、正文改动、文件破损、发布中断、旧版本仍可读取。
- [ ] 实现版本目录、数组/chunks/manifest写入，禁用pickle；先验证完整产物再替换current指针。
- [ ] Windows用真实临时目录验证发布；不覆盖在用矩阵文件，不自动删除旧版本。
- [ ] 验证CLI进程持有固定索引快照；重建不影响正在使用的快照，重启后加载新版本。

## Task 4：精确检索与可解释检查入口

计划新增 rag/retriever.py、rag/__main__.py、tests/test_retriever.py、tests/test_rag_cli.py。

- [ ] 先用手工可计算向量写排序、归一化、同分稳定性、k、过滤阈值、重叠去重、2400字符预算、无命中与取消测试。
- [ ] 实现全量向量点积，不引入ANN/数据库；返回原query、index_id、score与完整来源。
- [ ] 增加 build/inspect 开发命令；默认路径相对项目资源，显式路径支持中文/空格和目录外启动。
- [ ] 验证inspect能指出每个候选为何被返回或丢弃；明确分数不是正确率。

## Task 5：作为 Tool 接入既有 Agent

计划新增 tools/search_knowledge.py、tests/test_rag_tool.py；修改 tools/registry.py、tools/executor.py、runtime/errors.py、__main__.py。

- [ ] 先写失败测试：query空白/超长、工具注册、默认echo期限保持不变、检索20秒覆盖整个查询、已知错误外层ok=false、未知异常脱敏。
- [ ] ToolSpec 增加经验证的可选timeout；Executor仍使用协作式取消，补充ToolExecutionError安全映射。
- [ ] 入口装配Retriever；索引不可用明确提示，工具调用返回具体错误，不在后台建库。
- [ ] 接通模型 → search_knowledge → 带来源工具结果 → 模型；测试取消配对、失败后Session复用、soul全文与本轮hash不变。
- [ ] 工具描述写清适用范围、何时查、仅引用实际结果；不改Agent Loop为自动检索。

## Task 6：真实检索、路由与回答评测

计划新增 rag/evaluate.py、tests/test_rag_evaluate.py，扩展 rag/__main__.py eval 子命令；使用已提交候选题集，不生成题目混入语料。

- [ ] 先测试题集schema、K引用、单元级去重、跨段全部命中、分母区分、报告可复现性以及引用id解析。
- [ ] 用选定真实Embedding全量建库，在dev上校准切分/k/阈值，记录每次配置与失败案例；不为优化成绩改写检查题预期。
- [ ] 冻结配置，跑11个check场景，逐题报告直接检索的证据命中；保留原始候选和过滤后结果。
- [ ] 配置实际聊天模型，单独跑28题的Tool触发与据证回答检查；记录模型、查询、返回证据、引用与人工判断。未经配置不能声称端到端通过。
- [ ] 增加隔离的工程测试fixture：含类似system指令的文档、查询无共享词但语义相近、知识正文不随评测答案改变；这些不混入正式corpus、不作为真实效果成绩。
- [ ] 词面baseline如需要再作为独立离线对照实验，先不增加多检索后端框架。

## Task 7：交付核验与教学文档

计划新增 docs/phase-4-walkthrough.md、更新README/架构/复用记录；评测报告默认写.local/rag/reports，必要时整理去凭据的摘要进docs。

- [ ] 运行完整unittest、Ruff check/format，独立代码审查；已有52项回归保持通过。
- [ ] 手动走Windows建库、直接检查、正式聊天、无命中、坏索引、重建、取消路径；记录真实服务验证边界。
- [ ] 文档解释新增文件、执行路径、2–5个精读函数、命令、实际质量报告及未通过项。
- [ ] 停在Phase 4，未经明确要求不合并、推送或进入下一阶段。

## 实施前重点审查

题集绝不被索引；Q15的两个事实不能因重复抄写而变成单段即可回答；故事四的前半段不能脱离身份反转当成事实结论；命中相关片段不等于其中有答案；索引不匹配不能报成空结果；API故障不能被外层ok=true掩盖。以上分别由Task 1/4/5/6测试和人工资料核对负责。
