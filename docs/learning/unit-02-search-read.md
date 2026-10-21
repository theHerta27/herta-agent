# 单元02：先找到代码，再读取正文

## 背景问题

单元01的Read需要先知道路径。现在让Agent在选定项目中搜索关键词，拿到真实路径和行号，再调用Read。用户本轮要求直接回答上一练习并继续，因此先补`start_line=0`测试，再推进这一项小能力；结束后再次等待反馈。

## 核心原理

像先查书的索引，再翻到对应页：`grep_code`负责定位，`read_file`负责展开上下文。本版搜索是区分大小写的字面匹配，不需要向量模型或索引，`[0]`也当普通字符搜索。

Harness没有增加“必须先搜索再读取”的流程分支。它仍然重复：问Provider → 执行返回的工具调用 → 回填结果 → 再问Provider。改变的是Registry多登记了一个ToolSpec，模型接口因此能看到两份工具说明。演示Provider按固定脚本选择顺序，不是已经验证真实模型的决策。

## 真实源码和调用链

| 文件 | 本单元变化 |
|---|---|
| [cli.py](../../backend/herta_agent/cli.py) `create_agent` | 增加`registry.register(grep_code(repository))`，复用原Loop/Executor |
| [grep_code.py](../../backend/herta_agent/tools/coding/grep_code.py) | `GrepParameters`校验关键词、范围和数量；`_search`返回命中；异步handler在线程运行并处理取消信号 |
| [paths.py](../../backend/herta_agent/tools/coding/paths.py) `Repository.files` | 遍历普通文件，沿用路径边界，排除内部目录、链接和特殊文件 |
| [read_file.py](../../backend/herta_agent/tools/coding/read_file.py) | 提取已有`read_bounded_bytes/decode_utf8`供Read和Search共用，保留Read原契约 |
| [test_cli_search.py](../../backend/tests/test_cli_search.py) | 真实文件边界和三步HTTP夹具；不访问模型服务 |
| [demo.py](../../examples/cli-search/demo.py) | 使用同一`create_agent/chat`的离线学习夹具，不另建循环 |

在当前隔离目录运行以下命令（只访问新建的演示文件，不调用模型）。搜索范围为演示仓库的`shop`目录，输入关键词`def add_tax`。

```powershell
Set-Location -LiteralPath 'D:\Desktop\herta-agent\.local\worktrees\unit-01-cli-read'
$env:PYTHONPATH = (Join-Path (Get-Location) 'backend')
& 'D:\Desktop\herta-agent\.venv\Scripts\python.exe' -B -X utf8 examples/cli-search/demo.py
```

1. `SearchReadFixture.complete`返回`grep_code({"query":"def add_tax","path":"shop","limit":1})`。
2. `Agent.run → ToolExecutor.execute → GrepParameters校验 → grep_code.handler → _search`。`Repository.path/files`给出候选文件，共用的读取函数严格解码。
3. 工具实际返回`shop/billing.py`第1行：`def add_tax(price):`。Session记录工具结果后，原Loop再次请求Provider。
4. 夹具从这个真实结果取`path/line`，提出`read_file`调用；第三步请求再收到读取结果，显示：

```text
1: def add_tax(price):
2:     return price * 1.1
[steps=3]
```

这里的billing.py是明确标注的演示文件，不是Herta内部业务。`query`是待找文本，`matches`是命中条目，`limit`是最多返回多少条；`truncated=True`表示没搜索完整，`skipped_files`表示候选普通文件中有无法检索的文件。排除目录、链接及特殊文件不属于候选集。

## 关键设计取舍

- **复用来源**：本仓旧`coding-agent@e121d8207f74af98e22f2c100348b05160a0560b`的`tools/coding/grep_code.py`和`paths.py::Repository.files`。保留字面匹配及遍历方式，适配主线只读权限、共享读取、结果字节预算与线程取消。无新增第三方依赖。当前小范围搜索直接复用已有标准库实现；采用ripgrep还需引入外部可执行文件、进程生命周期与打包约定，本单元暂不引入。
- **结果不是越多越好**：最多检查2000个候选文件、读取约16MiB（允许一个探测字节），最多100条结果，并将结果行数据限制在约8KB；每行预览最多1000字符，截短会标记。遍历超过2000个目录会明确报错，请缩小path。较大、二进制和无效UTF-8文件跳过并计数。空matches在截断或存在跳过时不能证明代码不存在。
- **共享读取而非另建服务**：Read与Search共用同一目录对象和字节/解码函数。单个文件仍限制1MiB，Search不会绕过Read去读取更大的文件。Runtime、审批和存储接口没有修改。
- **取消边界**：停止等待后设置Event，工作线程在文件/行之间检查信号，不再继续后面的读取；已经开始的底层I/O不能强杀。测试等整个搜索函数退出后再检查实际读取记录。Windows用受控文件类型信息验证特殊文件过滤，未实测POSIX FIFO。

## 测试验证

先运行单元01相关23项作为基线。新工具未登记时观察到真实失败；普通文件过滤审查后也先观察到失败，再修正。Read与Search局部20项通过，含本轮补的零行号测试；最终后端367项中364项通过、3项可选语音测试跳过。代码规则检查与本单元涉及的9个Python文件格式检查通过；上一单元记录的旧桌面测试格式问题未改动，本轮未重跑全库格式检查。实际命令和失败记录见[执行记录](verification/unit-02/verification.md)。[本单元Diff](verification/unit-02/key-diff.patch)与上一单元结束快照比较，不把尚未提交的单元01代码冒充新写。

测试覆盖真实路径/行号、字面/大小写、排除项、无法解码文件计数、结果/读取预算、链接越界、受控特殊文件过滤、取消及搜索结果驱动的Read。另做两次进程内变异验证：故意去掉普通文件过滤或让取消信号失效，对应测试会失败；产品源码未被变异修改。

这些检查证明本地工具接线和已覆盖行为，不证明真实模型理解或答案质量。没有调用远程模型、读取私人资料、修改数据库或运行前端/Electron；没有提交、合并或推送。本机未实测POSIX FIFO。

## 动手练习

这次只做一个约5分钟的观察练习，不要求写函数：打开[演示夹具](../../examples/cli-search/demo.py)，找到`QUERY = "def add_tax"`，先猜如果改为`"DEF ADD_TAX"`会得到什么，再改这一行并运行演示。

观察“工具执行成功”和“找到匹配”是否相同，再解释为什么没命中时不需要继续Read。你不想动手也可以直接提问；助手不会提前改成大写。单元02到此停止，等待你理解并确认后再讨论下一单元。
