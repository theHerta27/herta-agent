# Phase 5 Task 8–9

Task 8实现模型服务返回的SSE流解析：网络块先按SSE边界组帧，再解码UTF-8和JSON；支持LF、CRLF、CR及多行data。文本增量可以立即向上传递，工具名称/参数按index累计，合法finish_reason、[DONE]及流结束全部校验后才产生唯一完整回复。重复终结、截断、旧function_call、冲突工具ID/类型等明确失败。单帧上限256KiB、累计响应4MiB（含忽略的元数据/注释）；HTTP异常不暴露body/URL，不自动重试。

工具参数保持既有边界：Provider负责片段组装与Message/ToolCall结构校验，原始arguments仍由Executor进行JSON/schema验证并反馈工具错误。未改动RAG算法或工具循环。

Task 9在Agent原请求位置增加显式streaming=True选择；默认False保持CLI与complete兼容。流式入口不存在就明确报错。整个流消费与关闭受同一次请求期限约束；llm.delta只进入observer，完整校验后的ModelReply继续走原有提交/工具/终止分支，没有第二份Loop。

这里解析的是上游模型的SSE，不是已经完成给UI使用的FastAPI/SSE服务。Task 10–12尚未开始。

离线验证：Provider定向8项、Runtime定向7项；完整157项unittest通过，Ruff check/format --check通过（65文件）。字节级MockTransport验证真实适配器，另有可控假增量验证取消、超时、协议失败、提交失败后数据库及下一轮上下文不含partial。组合测试覆盖知识Tool回填及同Run人格文件变更不影响已取得的快照。

上述是协议和工程验证，没有真实模型或Embedding调用，不能视为供应商流式表现或Phase 4 RAG效果已验收。

独立审查发现普通AsyncIterator不一定提供aclose；补充测试先复现失败后修复为可选关闭，HTTP异步生成器仍显式关闭。
