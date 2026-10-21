# 单元01：让CLI通过工具读取真实文件

## 背景问题

原CLI能够回显和演示echo，但强制加载人格，真实模型分支还组装RAG。Coding CLI首先需要一个更小的完整任务：指定项目目录，执行一次真实只读操作，将结果交回同一个Agent Loop，再输出回答。

本单元在`phase-6-ui@9ab9796`上建立隔离分支`learning/unit-01-cli-read`，没有合并旧coding分支，也没有提交、推送或改变原桌面入口。原主目录的未提交文件仍保留。本单元已经获得开始确认；结束后等待用户理解并确认下一单元。

## 核心原理

把模型看作提出操作建议的人，把Harness看作执行台。模型说“用read_file读取这个路径”，执行台根据已登记的工具说明检查参数、实际读盘，然后递回收据。模型不能只靠写一句“我读过了”就让程序认为操作成功。

正式名称分别是Provider、ToolCall、ToolRegistry、ToolExecutor和ToolResult。一次用户请求是一个Run；每次向Provider请求响应算一个Step。本例需要两步：第一步提出工具调用，第二步读取工具结果并形成最终回答。`Session`保存这次交流，当前只存在于进程内；Context Engine准备每一步的输入，不负责访问磁盘。

本轮使用的`ReadDemoProvider`是固定脚本：工具路径来自`--demo-read-file`，不是它理解了自然语言。真实模型适配器保留，并用本地`MockTransport`测试HTTP数据流；没有远程模型验收。

## 真实源码和调用链

| 状态 | 文件和函数 | 本单元职责 |
|---|---|---|
| 修改 | [__main__.py](../../backend/herta_agent/__main__.py) | 只转到`cli.main`；原控制台脚本仍可复用 |
| 新增 | [cli.py](../../backend/herta_agent/cli.py)，`main/run_cli/create_agent/chat/run_turn/print_result` | 解析参数、组装组件、终端输入输出；保留原Windows取消处理 |
| 保留 | [Agent.run](../../backend/herta_agent/runtime/agent.py)、[ContextEngine.prepare](../../backend/herta_agent/runtime/context_engine.py) | 唯一循环与上下文预算，没有另造一套 |
| 保留 | [ToolRegistry](../../backend/herta_agent/tools/registry.py)、[ToolExecutor.execute](../../backend/herta_agent/tools/executor.py)、[Session](../../backend/herta_agent/runtime/session.py)、[MemoryTurn](../../backend/herta_agent/runtime/turn.py) | 工具Schema、参数校验、期限、错误封装、调用与结果配对 |
| 选择性移植 | [Repository.path](../../backend/herta_agent/tools/coding/paths.py) | 解析规范路径，检查根目录边界和排除项 |
| 选择性移植并适配 | [ReadParameters/read_file/_read_file](../../backend/herta_agent/tools/coding/read_file.py) | 参数模型、工具说明及真实有界读取 |
| 新增演示类 | [ReadDemoProvider](../../backend/herta_agent/llm/demo.py) | 先返回固定调用，再展示实际工具反馈 |

入口迁移涉及的关键Diff是：原`__main__.py`的终端组装移到`cli.py`，删除入口中的人格/RAG强制加载；新增`registry.register(read_file(repository))`；Read工具明确声明`permission="read_only"`；真实读取使用`await asyncio.to_thread(_read_file, repo, parameters)`。完整可审阅补丁见[关键Diff](verification/unit-01/key-diff.patch)，包含新建文件，不只统计Git已跟踪文件。

本轮实际运行的输入是：

```powershell
python -m herta_agent --repo examples/cli-read --demo-read-file notes/demo.md --message '请读取这份笔记，展示内容。'
```

真实文件为[演示笔记](../../examples/cli-read/notes/demo.md)，没有使用私人文件。执行路径为：

1. `__main__ → cli.main → run_cli`：解析项目目录、创建`RunSettings`和`Repository`，选用离线`ReadDemoProvider`。
2. `create_agent`：只登记`read_file(repository)`，使用`StaticContextBuilder(CODING_SYSTEM)`，实例化已有`Agent`。
3. `chat → run_turn → Agent.run`：建立Session，`MemoryTurn.begin → Session.begin_turn`记下用户消息。
4. `ToolRegistry.definitions → ContextEngine.prepare → Agent._request → ReadDemoProvider.complete`：第一步得到`read_file`调用，其`arguments`字符串是`{"path":"notes/demo.md"}`。
5. `MemoryTurn.append → Session.record_calls`记下调用ID；`ToolExecutor.execute`通过`ReadParameters.model_validate_json`校验参数。
6. `ToolSpec.handler`即`read_file`内的异步`read`，通过`asyncio.to_thread(_read_file, repo, parameters)`运行同步读操作；`Repository.path`检查路径，`_read_file`打开文件、严格解码并返回行号和正文。
7. Executor封装为`ToolResult`；`MemoryTurn.append → Session.record_result`用`tool_call_id`把收据对应到原调用。
8. Loop再次准备上下文并请求Provider。脚本展示实际收据，`MemoryTurn.complete → Session.complete_turn`保存回答，最终`print_result`显示`steps=2`。

实际输出包括以下数据；完整输出保存在执行日志中：

```json
{"path":"notes/demo.md","lines":[{"line":1,"text":"# 单元01演示"},{"line":2,"text":"这是新建的非私人演示文件。"},{"line":3,"text":"目标：让工具读取真实内容，再交回 Agent Loop。"}],"truncated":false,"next_line":null}
```

几个关键名称：`spec`是工具说明书，`handler`是执行函数；`parameters`是校验后的参数对象；`arguments`是模型发来的JSON字符串；`repo`是当前选定目录的边界对象。`read_file(repo)`是一个工厂函数：它返回ToolSpec，并让内部handler记住这个repo，这种“函数记住创建环境”的机制称为闭包。

## 关键设计取舍

- **入口和核心分开**：CLI负责组装，不把参数解析塞进Loop。Provider可以替换，不使用Claude Agent SDK，也不复制源码镜像。CLI不再强制人格/RAG；相关旧组件及服务源码保留，测试改为显式组装原组件，保留内容、哈希、恢复和证据断言。
- **按真实来源小范围移植**：来源是本仓旧`coding-agent@e121d8207f74af98e22f2c100348b05160a0560b`的`tools/coding/paths.py`、`read_file.py`。只移植读取所需的路径逻辑，没有复制遍历、Search、Patch或Docker。适配点包括显式`read_only`、字节预算、严格解码、大文件拒绝及线程读取。文件哈希见执行证据；无新增第三方依赖，`asyncio`来自标准库，Pydantic和httpx沿用已有实现。包依赖清单本轮未裁剪。
- **先约束输入大小**：文件超过1MiB返回`file_too_large`，不将前缀的半行伪装成完整行。支持UTF-8文本，每页最多400行且行数据约24KB，给主线64KB结果上限和下一步上下文留余量。单行本身超出结果预算则明确报错。`truncated/next_line`表示结果分页，不能假装已经读完整份文件；400/401行连续性有真实文件测试。
- **取消等待与终止I/O不同**：线程读取让事件循环能处理超时或取消，但无法强杀已经开始的底层读取。Runner退出时会等待执行器收尾，因此单次进程退出时间不能当作硬超时保证。测试保留真实异步handler和Executor，只在同步读取辅助函数中制造可控等待，并验证工作线程最终结束；原CLI模型/工具Ctrl+C及会话续接测试继续保留。
- **目录限制不是沙箱**：只约束这个Read工具，拒绝根目录外、排除路径和解析后越界的链接。不提供任意脚本、写操作或操作系统隔离，也不声称能抵御其他进程恶意并发替换文件路径。

## 测试验证

新增10项测试位于[test_cli_read.py](../../backend/tests/test_cli_read.py)。针对CLI、Read、人格与RAG适配的回归实际运行23项通过；最终完整后端运行357项，354通过、3项真实GPU语音验收按原条件跳过。覆盖真实读盘及行号、中文结果限制、缺失/排除/越界/二进制路径、链接与Windows别名、严格参数、分页、大文件拒绝、真实handler取消等待和HTTP结果回填。旧CLI的Ctrl+C、超时、会话续接仍运行。

关键命令为`python -m unittest test_cli test_cli_read test_persona_integration test_rag_integration -v`和仓库原有的`python -m unittest discover -s backend/tests -v`。详细环境、完整命令、全量结果与原始失败分别保存于[执行记录](verification/unit-01/verification.md)，不把日志混进教程。全库`ruff check backend evals/harness`通过；改动的11个Python文件格式检查通过；全库格式检查仍报告原有`test_desktop_start_guard.py`一处换行未格式化，该文件未修改。

保留的真实失败包括：旧CLI不认识新参数；初次结果预算导致下一步上下文超限；移植代码忽略无效UTF-8；原同步Read无法取消等待；旧人格/RAG的CLI绑定不再成立。均按实际原因处理。初始Windows句柄测试受沙箱限制，旧文档测试在隔离目录缺少LibreOffice路径；服务测试还多次撞到空就绪文件的时序错误，最终只调整`backend/tests/service_probe.py`夹具，先写临时文件再原子替换，不改服务代码。原失败日志仍在，没有改成“全部一次通过”。

这些检查证明本地程序的已覆盖数据流和执行行为，不证明真实模型会选择Read、会理解文件、会正确回答，也不证明整个Coding Agent已经完成。本轮没有运行真实模型、真实GPU语音验收、前端或Electron验收，没有访问已有私人数据库。

## 动手练习

单元01结束时曾留一个`start_line=0`测试练习。随后用户要求直接回答并继续，现已补入[test_cli_read.py](../../backend/tests/test_cli_read.py)的`test_zero_start_line_is_rejected_before_disk_lookup`，不再等待用户手写。

目标：输入无效行号时，结果为`ok=False`、错误码`invalid_arguments`，并且不会调用`Repository.path`查找磁盘文件。提示：沿用`self.execute`，参考已有严格参数测试中`patch.object(self.repo, "path", ...)`的做法。先写出预期，再运行该测试，最后解释错误为什么出现在Executor参数校验层，而不是读文件函数。

答案：`ReadParameters.start_line`用`ge=1`规定至少为1；`ToolExecutor.execute`先调用`model_validate_json`，遇到0时捕获ValidationError并返回`invalid_arguments`。handler尚未执行，因此没有路径查找或文件读取。测试把`Repository.path`临时换成“调用就报错”的警报，再断言错误码及警报调用次数为0，验证的正是这个顺序。

验证命令：`python -m unittest discover -s backend/tests -p test_cli_read.py -v`。原单元01记录仍保留当时的结果；后续新增测试与单元02记录见[单元02总结](unit-02-search-read.md)。
