# Phase 5 Task 4–7

本批只完成计划中的Task 4–7，不改变12个任务和Phase排布。

- Task 4：Agent通过TurnIO提交消息，默认MemoryTurn保持原CLI；Session.restore验证闭合历史。提交失败停止推进，不把未提交结果写进内存。
- Task 5：RuntimeEvent/EventSink不依赖SSE；完成事件在提交后发出，参数无效不发工具开始事件。Executor回调的基础设施错误直接传播，不混入handler错误。
- Task 6：RunManager在await之前预占Session及全局名额，满额立即拒绝。PersistentTurn将已落库user映射到内存一次，后续Store先提交再更新内存。ServiceSettings默认并发4、范围1–32，通过HERTA_MAX_ACTIVE_RUNS读取，模型标识可显式传入，配置不保存Key。
- Task 7：Manager拥有接纳过程及工作Task；取消接纳者也不会丢失已提交Run。终态提交由同一入口裁决，先接受取消就不能再执行新工具或提交成功回答，先进入最终提交则等待结果。重复取消不打断清理。shutdown默认10秒协作等待（grace_seconds可指定），超时明确报错且继续持有清理任务；数据库关闭在全部Run释放后执行。

事件通道有界（每Run 128项），清理不等待消费者。存储终态提交失败报告service.error / persisted=false；磁盘仍是running时不冒充failed。通知失败不会改写已提交completed。HTTP背压、断连与SSE编码仍属Task 11。

知识点：依赖倒置与接口隔离、事务提交与内存一致性、观察者模式、状态机、原子接纳、协作式取消、任务所有权和资源生命周期。

验证：Task 4定向3项，Task 5定向3项，Task 6定向5项，Task 7定向13项；完整142项离线测试通过，原93项保留；Ruff check及format --check通过（62个文件）。独立审查复现“适配器吞取消后仍执行工具”，新增失败测试后在提交/事件边界加入取消检查，验证模型与handler两种吞取消情况。

原CLI仍默认使用内存；持久执行入口是RunManager.submit，目前由测试调用。未开始Task 8–12：真实Provider流式、FastAPI/SSE装配与Windows HTTP集成仍待后续。未调用真实模型/Embedding API，Phase 4真实RAG效果仍未验收。
