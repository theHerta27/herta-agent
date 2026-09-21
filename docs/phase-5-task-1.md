# Phase 5 Task 1：SQLite记录与原子消息提交

> 本文保留Task 1交付时的记录；其中“尚未实现”的Task 2、3现已完成，见[后续记录](phase-5-task-2-3.md)。

本轮只完成Task 1。分支从phase-4-rag的ae72541创建为phase-5-service；未提交、push或merge。

## 新增的东西

- `backend/herta_agent/storage/models.py`：不可变Session、Run、Message记录及Admission；只允许保存模型标识和RunSettings的RunConfig；安全StoreError。
- `backend/herta_agent/storage/sqlite.py`：SQLiteSessionStore，管理sessions/runs/messages三张表和版本号，提供显式事务、分页、消息校验与成功终态提交。
- `backend/herta_agent/storage/__init__.py`：独立存储包入口。
- `backend/tests/test_session_store.py`：Task 1行为测试；数据库建在临时中文/空格路径，测试结束删除。

现有Agent Loop、Session内存实现、Persona、RAG与依赖没有修改。

## 数据现在从哪里写进去

**只有调用SQLiteSessionStore的代码才会写库，目前调用者是新测试。原CLI/Agent尚未接上数据库。** 构造Store时必须显式给出数据库路径，不自动创建正式会话库。

```text
测试构造Message和RunConfig
  → admit_run：同一事务创建Run + user消息
  → start_run / set_context：记录运行状态与人格hash
  → append_message：完整assistant工具调用 / tool结果
  → finish_run：同一事务写最终assistant + completed状态
  → close / open / load_history：重开后取回正式记录
```

存储层校验Message结构与工具配对，最终文本只能经finish_run提交；它没有模型网络响应，无法判断一段自然语言是否来自已完成的供应商协议。完整协议校验仍是Provider及后续Runtime提交边界的责任，不能把本任务声称为已经接好了真实流式。

## 本任务解决的问题

Run创建到一半或最终提交到一半发生错误时，SQLite回滚整次事务，不留下“Run存在但user丢了”或“消息保存了却没有completed”的半份结果。

消息顺序以Session序号保存。工具ID只在对应assistant调用批次中配对，另一个Step/Session可以使用相同ID；错误、重复或错Step的tool结果拒绝。全局message_id和Session内序号由数据库约束保护。

只保存正式消息，没有partial或事件表。system、delta字典及普通append中的纯文本assistant都拒绝；最终完整assistant须与running Run、Session、序号和Step对应。存储错误不向调用者暴露SQL、参数或底层错误正文。

## 建议精读的三个函数

1. `SQLiteSessionStore.admit_run`：看Run与user怎样在同一事务创建。
2. `SQLiteSessionStore.finish_run`：看消息校验、最后回答与终态怎样一起提交。
3. `SQLiteSessionStore._transaction`：看提交点、回滚与安全异常转换。

测试中的SQLite触发器会真的在INSERT/UPDATE执行中抛错，不是把方法的返回值伪造成失败。可以先读两个fault测试，再回头看事务函数。

## 明确尚未实现

- Task 2：失败/取消终态的pending自动闭合、中断恢复；重开后running仍是running。本任务只支持成功完成，其他终态提交明确拒绝。
- Task 3：专用线程、异步数据库I/O、取消与在途事务协调。当前保留async接口，但方法内执行短同步SQL，仅用于这一存储层阶段，尚不能接入并发服务。
- Runtime提交/事件接口、RunManager全局容量与取消、Provider真流式、FastAPI和SSE。
- 持久消息自动进入当前CLI/Agent历史、任何真实模型或Embedding API验证。

Phase 4真实RAG效果与阈值仍待后续真实服务配置，Task 1不会改变该状态。后续任务只能在再次授权后继续。

## 实际验证结果

- 实现前：原93项离线回归通过；新增测试因storage模块不存在而预期失败。
- 实现后：Task 1定向13项通过；完整unittest 106项通过（10.788秒）。
- Ruff check通过；format --check通过（50个Python文件）。
- 独立只读代码审查未发现Task 1范围内具体缺陷。没有调用真实模型或Embedding服务。
