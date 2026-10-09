# Herta Harness 本地评测报告

日期：2026-10-09。基线：`81a1d740f7b92a6124dc0f29773b417af6b606f6`；本轮新增源码版本以本报告所在 Git Commit 为准。Python3.12.13 / Node22.16.0 / Windows。当前用户仅允许本地测试；真实模型效果评测暂缓。

## 测试与实验是不同证据

223项后端单测、35项前端单测和11项 Electron E2E 已通过。它们覆盖运行状态、工具结果、取消、存储、设置和诊断，但不能推断真实模型理解或答案正确。所有最终模型请求均为本地测试替身，MCP 为本机 stdio Server。

## C0 / C1 / C2 离线契约对照

数据集：`evals/harness/cases.json`（`herta-harness-local-v1`），SHA256 `cf978d6a3ca76c456953c4b5575c3ceacf1b5684d18678b578191d648a48bf83`。运行器：`evals/harness/run_offline.py`。题目首先约定项目名“星塔”，插入8轮较长闲聊，再追问项目名。

固定窗口8192，输出预留512，安全余量256，输入预算7424，摘要上限768。固定人格来自本机 `persona/soul.md`。FixtureReader 仅搜索“星塔”文字是否可见；它不是语言模型，也不模拟推理。

| 策略 | 估算输入 | 输入预算 | 省略旧消息 | 旧标记可见 | 估算预算内 | 原历史未改写 |
| --- | ---: | ---: | ---: | --- | --- | --- |
| C0 完整历史基线 | 20538 | 7424 | 0 | 是 | 否 | 是 |
| C1 预算选择，关闭摘要 | 5599 | 7424 | 16 | 否 | 是 | 是 |
| C2 预算选择＋抽取摘要 | 6290 | 7424 | 16 | 是 | 是 | 是 |

C0 故意保留旧行为作为测量基线，使用仅评测引擎允许发送全部文字，再报告真实配置预算；产品默认 ContextEngine 会先拒绝超预算。C1/C2 证明选择策略与派生摘要能够限制估算体积。这个单一用例也暴露了 C1 丢失旧约定的代价；C2 能保留此例文字，不证明对任意旧约定有效。

请求均在进程内完成，`network_requests=0`、`actual_model_quality=not_evaluated`、`actual_token_usage=null`。报告不计算真实正确率、成本节省或模型延迟；elapsed 仅是本地夹具运行时间。

报告：`.local/harness-offline-report.json`。复现：

```powershell
.\.venv\Scripts\python.exe evals/harness/run_offline.py
```

## 本地 BGE 检索观察

使用磁盘上完整的 BAAI/bge-large-zh 权重，CPU离线推理；不是固定向量替身。模型只读取本机权重，未请求远端 Embedding API。索引20片段1024维；索引 ID `4207b9f4cf1140f1b07964da98130260`，Embedding指纹 `d1f5af6b0543a819e32286c3033d44dcdc29b7d80e2da58010a826480c11b1e2`。

题集：`evals/rag/questions.jsonl`，SHA256 `3c71faa22b714f740210aace63249f118ae1ec1e3866f01d296ab4cad48d6616`。全部28题中4题明确无需检索，其他24题执行直接检索；不是让聊天模型自主决定路由。

| 观察 | 本地结果 |
| --- | --- |
| 指定必要证据单元覆盖 | 21/21，过滤后 recall=1.0 |
| 跨段问题证据完整 | 4/4 |
| 检索设置 | k=4，min_score=0.0，max_chars=2400 |
| 首次冷加载查询 | 约5.69秒 |
| 后续查询 | 约0.16–0.25秒，依本机负载变化 |
| 路由、回答正确性、引用是否支持答案 | 未测 |
| 无答案拒答、阈值校准 | 未完成 |

这里的1.0只表示固定题集指定的 evidence unit 出现在返回片段中，不代表问答100%正确。min_score=0 尚未校准，score不能解释成事实置信度。逐题返回/缺失片段与耗时保存在 `.local/rag/reports/local-bge-validation.json`，语义人工判断仍为 pending。

## 失败注入与修复

- 超大人格/当前轮：Context 在模型调用前明确拒绝；旧 tool ID 配对完整保留或整组省略。
- MCP非法参数、缺失工具、超时、取消、进程断开和非法UTF-8：执行器返回统一错误；SDK任务不取消 FastAPI 生命周期；集成测试证明下一轮聊天和SQLite仍正常。
- 设置重启失败：不保存候选设置，恢复旧配置与服务并展示明确失败；服务启动但缺配置显示配置未就绪。
- 摘要上限：分别检查64/128/256的硬边界；读取诊断失败后重试确实发请求。

实际日志：`.local/final-backend-tests.log`、`.local/final-desktop-e2e.log`。

## 尚未执行的真实验收

按最新用户指令，未完成真实DeepSeek固定题集、真实多轮 C0/C1/C2、实际Token/费用和语义评分。此前启动的真实系统评测已停止，没有完整报告；本报告不拿夹具结果替代它。后续只有用户明确允许后再执行。

工作区实现的逐文件SHA256与最终测试计数保存在 `.local/harness-delivery-manifest.json`，用于核对本轮本地验收时的源码快照；GitHub 版本以提交中的源码为准。此清单不记录密钥；仅基线Commit不足以复现本轮新增功能。
