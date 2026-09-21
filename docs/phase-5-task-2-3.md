# Phase 5 Task 2–3

Task 2让遗留的created/running Run在重启后明确结束为interrupted。恢复读取已保存的消息，只补齐未返回的工具调用，并说明结果未知，不重跑工具。修复与终态在同一事务中保存；再次恢复不重复写入。失败/取消同样原子闭合pending。open不隐式恢复，启动装配必须显式调用recover_interrupted后才接纳新Run。

Task 3用一个专用线程创建、操作、关闭SQLite连接。async接口不再阻塞事件循环；取消会等待线程工作真正结束再传播，close排在已接收工作之后并拒绝新操作。SQLite锁等待上限起点为1秒。存储执行/提交故障使writable变为false，不自动重试，需关闭重开并恢复；普通输入校验或唯一键冲突不视为存储损坏。错误正文不暴露底层异常，finish_run的error参数由调用者提供安全文本。

主要变更：storage/sqlite.py、test_store_recovery.py、test_store_cancellation.py。Task 1测试保留事务回滚断言，故障后重试改为关闭重开与恢复，以符合Task 3的故障停止写入语义。没有新依赖、通用执行框架或额外调度器。

对应知识点：事务原子性、状态机、崩溃恢复和幂等；事件循环、线程归属、Future、协作式取消和资源生命周期。外部工具副作用与SQLite不在同一事务中，硬退出仍只能在下次启动修复历史。

目前仅测试调用存储层，CLI/Agent仍未接入。Task 4–7将连接单一Agent Loop的提交/事件边界与RunManager，让持久历史、并发接纳、取消和终态形成执行闭环；本轮没有开始这些任务。Phase 4真实RAG效果仍未验收。

验证：恢复6项、线程/取消6项、完整unittest 118项通过（包含原93项）；最终Ruff及独立审查结果记于progress.md。所有测试离线。
