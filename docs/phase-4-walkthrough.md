# Phase 4：从证据文本到可解释的 RAG

本阶段实现已落在本地 `phase-4-rag`，没有提交、推送或合并。工程测试覆盖完整链路；本机未配置聊天或 Embedding 环境变量，**真实服务合约、语义检索质量、模型路由和据证回答仍待验证**。下文命令用于补齐这些验收，不把固定向量测试当作效果成绩。

## 先理解执行链

建库由人显式执行：

```text
knowledge/herta.md + sources.json
→ load_corpus：20个证据单元、确定性切分、原始来源/规范化偏移
→ embed_documents：标题 + 正文 → 独立远程服务
→ float32归一化矩阵 + chunks.jsonl + manifest.json
→ 验证后原子替换 current.json
```

正式聊天由模型决定是否查资料：

```text
PersonaContextBuilder → 稳定 system + Session历史 → 聊天模型
→ search_knowledge({query}) → embed_query → 精确余弦排序
→ 阈值、重叠、k、正文预算过滤 → 带来源的 tool message
→ 原有 Agent Loop 再请求聊天模型 → 回答及 [chunk_id] 引用
```

Agent Loop 没有新增 RAG 分支。Persona 仍每轮重新加载、同轮保持完整快照；检索正文不会升为 system。Tool 描述要求把正文作为资料而非指令，但这不是安全隔离或模型一定遵从的保证，实际回答仍需评测。

## 新增文件与边界

| 文件 | 作用 |
| --- | --- |
| `knowledge/herta.md` / `sources.json` | 固定20个角色证据单元和原文定位；仅正文被编码 |
| `evals/rag/questions.jsonl` | 28题：13可回答、4跨段、7资料不足、4无需检索；dev17/check11 |
| `rag/models.py` / `ingest.py` | 验证证据、600字符段落切分、长段80字符重叠 |
| `rag/embeddings.py` | 独立配置、文档/查询接口、唯一远程适配器、响应顺序与数值验证 |
| `rag/store.py` | 不可变版本、校验和、配置指纹、禁止pickle、Windows指针发布 |
| `rag/retriever.py` | 全矩阵点积、稳定排序、过滤、可解释候选列表 |
| `rag/service.py` / `rag/__main__.py` | 入口装配以及 build、inspect、eval |
| `rag/evaluate.py` | 分开统计直接检索、正式聊天，保留人工语义判断 |
| `tools/search_knowledge.py` | 只接收query、错误映射、默认20秒总期限 |

工具执行器增加可选的单工具期限和预期错误映射；echo 仍沿用原全局期限。配置中的 Key 从序列化和 repr 中排除。聊天入口也改为只读环境 Key，不再提示输入后作为应用配置保存。

## Windows 配置与运行

在本项目根目录的 PowerShell 中运行。聊天与 Embedding 地址、模型和 Key 分开设置；地址是服务根地址，通常带 `/v1`，不要把 `/embeddings` 或 `/chat/completions` 拼入 Base URL。占位地址/模型必须换成实际服务支持的值。

```powershell
Set-Location -LiteralPath 'D:\Desktop\herta-agent'
$env:HERTA_EMBEDDING_BASE_URL = 'https://你的Embedding服务/v1'
$env:HERTA_EMBEDDING_MODEL = '你的Embedding模型'
$env:HERTA_BASE_URL = 'https://你的聊天服务/v1'
$env:HERTA_MODEL = '你的聊天模型'
```

Key 由你在本地终端设置，不发送到对话、不放入配置文件。PowerShell 可用以下方式避免把值写进命令历史（环境变量仍属于当前进程的秘密）：

```powershell
$embeddingSecret = Read-Host 'Embedding Key' -AsSecureString
$env:HERTA_EMBEDDING_API_KEY = [System.Net.NetworkCredential]::new('', $embeddingSecret).Password
Remove-Variable embeddingSecret
$chatSecret = Read-Host 'Chat Key' -AsSecureString
$env:HERTA_API_KEY = [System.Net.NetworkCredential]::new('', $chatSecret).Password
Remove-Variable chatSecret
```

应用不加载 `.env`，不隐式复用聊天 Key，不重试或自动切换模型。文档片段在 build 时、query 在查询时会发送到对应 Embedding 服务；检索证据随后会随 tool message 发给聊天服务。

可选环境项：

| 名称（前缀均为 `HERTA_EMBEDDING_`） | 默认值与含义 |
| --- | --- |
| `DOCUMENT_PREFIX` / `QUERY_PREFIX` | 空串；需要特定指令前缀的模型按其实际约定填写 |
| `MAX_INPUT_CHARS` | 16000；包括前缀、标题和正文，超出直接报错，不截断 |
| `BATCH_SIZE` | 32；按批请求，响应按 index 恢复顺序 |
| `TIMEOUT` | 60秒；每批HTTP总期限，查询还受工具默认20秒期限限制 |

字符上限不等于服务 token 上限；实际模型支持、维度、中文效果和限流仍需实测。索引指纹包括地址、模型、前缀及输入上限；换 Key 不要求重建，换编码配置要求重建。

```powershell
# 20个当前短单元通常形成20个chunk；命令会报告实际数目和维度。
.\.venv\Scripts\python.exe -m herta_agent.rag build
.\.venv\Scripts\python.exe -m herta_agent.rag inspect '黑塔为什么恭喜阮梅实验失败？'
.\.venv\Scripts\python.exe -m herta_agent --provider openai --message '故事四里出现的究竟是谁？请给出证据。'
```

默认路径相对项目资源定位，与启动 cwd 无关。RAG 命令的全局选项放在子命令前，例如 `--index 'D:\中文 目录\索引' --k 4 --min-score 0.0 inspect '问题'`；正式聊天对应 `--rag-index`、`--rag-k`、`--rag-min-score` 和 `--rag-timeout`。两种入口必须使用同一套实验设置。

CLI 启动时加载固定索引快照；建库完成后重启聊天才能使用新版本。索引缺失、损坏、正文/来源或编码配置改变时明确报错；不在聊天中自动建库。普通聊天可继续，知识工具会返回失败。Persona 的失败仍停止当前轮。交互模式 Ctrl+C 取消当前轮，保留 Session。

## 用 inspect 理解检索

每条证据包含 `id`、`unit_id`、标题、正文、规范化文档hash、字符半开区间 `[start,end)`、整理文本行号、原始来源行号及URL。字符偏移基于去BOM、换行转LF后的正文，不能直接当原始UTF-8字节偏移。

归一化后分数为 `document_vector · query_vector`。分数表示向量空间里的相似程度，**不是事实正确率或资料包含答案的概率**。默认 k=4、正文预算2400字符、阈值0.0；这个阈值只是未校准起点。

`candidates` 保留全库排序，`reason` 分别为 selected、below_threshold、overlap、limit、budget。`search` 工具只返回选中内容，不把全库诊断塞给模型。同一单元的重叠窗口只取较高分片段；完整片段超预算则跳过，不在返回阶段截成半句。

余弦最高也可能无答案。例如“完整返老还童公式”可以命中K16，但该段明确没有公式；不能把“检索相关”评成“问题可回答”。故事四还需要K19与K20共同保留反转，不能只引用前半段就认定真正博识尊出现。

## 真实评测顺序

```powershell
# 先用dev校准，只调整有证据支持的切分/前缀/k/阈值。
.\.venv\Scripts\python.exe -m herta_agent.rag eval --mode retrieval --split dev
# 冻结设置后跑check；失败也要保留，不改题目预期来提高分数。
.\.venv\Scripts\python.exe -m herta_agent.rag eval --mode retrieval --split check
# 正式模型主动调用工具，单独检查路由、引用和回答。
.\.venv\Scripts\python.exe -m herta_agent.rag eval --mode chat --split all
```

报告默认保存在 `.local/rag/reports`，已被 Git 忽略；`--output` 可指定文件。记录索引manifest、无Key的编码配置、题集hash、时间、查询、候选/过滤结果，以及聊天的模型、Run设置、Persona hash、实际工具结果、引用和回答。服务端默认采样参数未由本阶段控制，不能保证真实模型逐字复现。

直接检索只对需要检索的24题调用Retriever；17道有答案题按预期单元去重计算证据召回，另外统计4道跨段题是否全命中。无答案题的召回为null，不混入分母，也不要求必须空命中。4道无需检索题在此模式跳过，工具触发只能在正式聊天模式测。

正式聊天每题新建Session，保留本题实际query和成功返回的chunk。自动检查路由、引用是否来自本题结果、是否缺引用；有引用但语义不支持仍可能答错。`groundedness`、`unknown_handling`、`expected_judgment` 固定标为 pending_manual_review，需结合每题expected/forbidden核对。报告不会自动宣称语义全部通过。

## 五个精读函数

1. `ingest.load_corpus`：从证据清单到chunk，理解为什么来源定位必须在切分时保存。
2. `RemoteEmbeddings._request`：请求边界、响应重排、数值校验及取消，理解向量不是任意数字数组。
3. `store.publish_index`：先写新版本并自检，再换指针，理解可再生索引与Windows文件生命周期。
4. `Retriever.inspect`：一次精确排序如何变成有限证据，逐项看过滤原因。
5. `evaluate_chat`：沿实际Session消息追踪工具与引用，理解检索质量、模型路由和答案质量是不同问题。

建议先手算 `[3,4]` 归一化为 `[0.6,0.8]`，再看 `test_retriever.py` 的已知向量排名。无共享词面的fixture只验证“按向量检索而非关键词匹配”的工程行为，不能证明远程模型已经具备足够中文语义能力。

## 验证结果与未完成验收

93项离线测试通过，包括既有52项回归。Ruff check/format通过；原始两份语料hash未改变。独立审查发现并修复：NPZ伪装成NPY导致未捕获异常、bool数组被当向量、来源行号隐式类型转换。完整HTTP边界模拟验证了不同聊天/Embedding服务与Key、真实适配器→本地索引→Tool→模型链路、索引失败发布、Persona稳定、取消和Session恢复。

**未执行真实API调用或真实语义评测；尚未通过最终RAG效果验收。** 当前进程没有任何HERTA环境配置。下一项是用户在本地配置后按上述顺序运行、保留失败案例并校准；工程完成不等于真实效果已达标。没有实现词面baseline、向量数据库、本机Embedding、RAG以外功能或Phase 5。
