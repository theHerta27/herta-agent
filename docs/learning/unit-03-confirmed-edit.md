# 单元03：看清差异，确认后编辑

## 背景问题

前两单元能找代码、读代码，现在补一条完整的小任务：读文件 → 提出一处替换 → 显示差异 → 人确认 → 写入 → 回读。本单元已获用户明确开始授权；不等待前面练习完成，也不进入单元04。沿用当前隔离目录，不调用真实模型或读取已有私人资料。

## 核心原理

像修改一份校样：先拿到原稿，圈出替换文字，让作者看修改前后，再落笔。如果等待确认时原稿已被别人改过，就重新取稿，不能拿旧方案覆盖新内容。

`sha256`是文件字节内容的指纹，不是密钥或授权。Read返回指纹，Edit用`expected_sha256`说明“我针对的是这个版本”。`old_text`必须精确且唯一，`new_text`是替换内容；真正的执行许可来自终端确认，不能靠模型自己说“已确认”。

## 真实源码和调用链

| 文件与关键符号 | 作用 |
|---|---|
| [read_file.py](../../backend/herta_agent/tools/coding/read_file.py) `_read_file` | 保留行号和分页，新增全文件原始字节的`sha256` |
| [edit_file.py](../../backend/herta_agent/tools/coding/edit_file.py) `EditParameters/prepare_edit` | 校验路径、指纹和唯一匹配；在内存中生成替换结果与差异，不写盘 |
| 同上 `commit_edit/edit_file` | 再核对原文，通过临时文件和`os.replace`替换一个目标，返回写入收据 |
| [permissions.py](../../backend/herta_agent/tools/permissions.py) `TerminalApproval/terminal_text` | 展示完整差异并转义控制字符；仅`yes`批准这一次，回车、EOF、Ctrl+C均拒绝 |
| [executor.py](../../backend/herta_agent/tools/executor.py) `ToolExecutor.execute` | 参数校验后调用`authorize(spec, parameters)`；获准才进入handler；不给模型绕开确认的入口 |
| [cli.py](../../backend/herta_agent/cli.py) `create_agent/run_cli`；[agent.py](../../backend/herta_agent/runtime/agent.py) `Agent.__init__` | 注册Edit，传入确认回调；Agent只增加转发参数，循环主体不变 |
| [演示](../../examples/cli-edit/demo.py)；[测试](../../backend/tests/test_cli_edit.py) | 固定Provider、实际临时文件与模拟HTTP，不是自然语言模型验收 |

本轮实际演示输入：“把value从1改成2，先确认差异，再读取核对。”`EditFixture.complete`固定提出工具请求，原Harness真实执行：

1. 第1次请求返回Read；`Agent.run → ToolExecutor.execute → read_file`，取得`value = 1`及指纹。
2. 第2次请求返回Edit；Executor校验JSON，`TerminalApproval → prepare_edit`给出`-value = 1 / +value = 2`。
3. 输入`yes`；handler重新备稿并核对指纹，`commit_edit`写入，收据含`written/path/before_sha256/after_sha256`。拒绝则返回`permission_denied`，不进入写入函数。
4. 第3次请求返回Read，实际得到`value = 2`；第4次请求才输出回答，因此`steps=4`。本轮收据的after指纹与回读指纹相同。固定脚本拒绝路径不继续编辑，`steps=3`。

运行方式（每次使用新建临时文件，结束后清理）：

```powershell
Set-Location -LiteralPath 'D:\Desktop\herta-agent\.local\worktrees\unit-01-cli-read'
$env:PYTHONPATH = (Join-Path (Get-Location) 'backend')
& 'D:\Desktop\herta-agent\.venv\Scripts\python.exe' -B -X utf8 examples/cli-edit/demo.py
```

## 关键设计取舍

- **小范围复用**：Read/Search的Repository和有界读取继续使用；唯一Loop、Session和Context保留。旧`tool_policy`仍兼容桌面服务，新CLI只选参数级`authorize`，两种入口互斥，不串联第二套审批服务。未配置审批时Edit默认拒绝。
- **输入契约先简化**：已读本仓旧`coding-agent@e121d8207f74af98e22f2c100348b05160a0560b`的185行`apply_patch.py`。它包括多文件解析/回滚，本单元不移植。选择标准库字符串定位、`difflib`展示、`hashlib`指纹、`tempfile/os.replace`单文件提交，无新依赖；不把展示用diff拿去自行解析。Git apply适用于统一补丁输入，本单元未运行它，不声明兼容该格式。
- **架构参考有出处**：沿用2026-10-19已读取的[Claude Code Edit说明](https://code.claude.com/docs/en/tools-reference#edit-tool-behavior)及[权限文档](https://code.claude.com/docs/en/permissions)本地快照，学习精确文本替换和执行前确认。我们的字段、严格全文件指纹和逐次确认是自己的小范围契约，不声称逐项复刻官方行为；未复制非官方还原源码。具体快照、旧源文件哈希和依赖版本见执行记录中的来源清单。
- **先完整展示再确认**：只改已有普通UTF-8文件，单文件仍限1MiB；新旧文本各最多32000字符，差异最多16000字节，过大就拒绝，不截短后批准。链接、硬链接、只读文件及原排除路径拒绝；不创建/删除/重命名文件。未命中、多处命中、内容过期或无变化均拒绝。CR等控制字符可见转义，避免隐藏换行变化或执行终端控制序列。
- **取消与写入分开**：备稿在线程中只读，可取消等待，之后不会迟到写入；真正提交没有`await`，尽量避免写到一半被异步取消。确认期间主线程等待用户，不设人工思考超时；`tool_timeout`用于获准后的handler。第一次Ctrl+C拒绝确认，结束恢复原信号处理。底层I/O仍没有硬超时保证，目录检查不是OS沙箱，也不承诺抵御恶意进程在最后检查与替换之间抢改路径。

## 测试验证

先观察新增Read指纹和Edit调用失败，再实现。另用子进程先复现首次SIGINT不能结束确认等待，修复后通过；CR预览和只读文件也有先失败再通过记录。临时文件测试覆盖确认/拒绝/空输入/EOF、过期与重复匹配、路径和链接、写入失败清理、等待期间外部修改、取消后无迟到写入，以及同一Loop中的实际回读。

最终完整后端385项中382通过、3项可选语音测试跳过；编辑和权限局部21项通过，代码规则与涉及12个Python文件格式检查通过。独立静态审查未发现需修复的重要问题。实际命令、失败与跳过记录见[执行记录](verification/unit-03/verification.md)；[本单元Diff](verification/unit-03/key-diff.patch)与单元02结束快照比较，不把前两单元的未提交代码混入本轮。完整回归仍包含旧组件，数量不能证明真实模型选工具或答案质量。前端、Electron、真实模型和私人数据库本轮均未验收，没有提交或推送。

## 动手练习

约5分钟，只做观察：运行上面的演示两次，第一次输入`no`，第二次输入`yes`。比较差异、最终实际文件、工具错误/收据和`steps`。两次各用新临时文件，第一次拒绝不会影响第二次。读完后尝试用自己的话解释：文件指纹为什么不能代替你的确认？不要求现在写函数，也不影响本单元交付。单元03完成后暂停，不自动进入下一单元。

用户已实际完成两次运行，要求直接讲解，答案如下：

| 输出 | 怎么理解 |
|---|---|
| `--- a/note.py` / `+++ b/note.py` | 同一文件的修改前/修改后版本；不表示真的存在a、b目录 |
| `@@ -1,2 +1,2 @@` | 展示旧版本从第1行起的2行，以及新版本从第1行起的2行 |
| `-value = 1` / `+value = 2` | 准备移除的旧行/准备写入的新行，此时还没写文件 |
| ` untouched = True` | 上下文行，没有改变；这与能被执行的Python语句是不同概念 |
| `permission_denied` | 用户拒绝本次编辑的正常结果，文件仍是value=1，不是程序坏了 |
| `written: true` | 实际写入完成；before/after指纹对应修改前后的内容，回读指纹与after相同说明读到对应结果 |

`steps`是Provider请求次数，不是代码行数，也不是工具次数。拒绝：请求Read→请求Edit被拒绝→请求最终回答，共3次；同意：请求Read→请求Edit→请求Read核对→请求最终回答，共4次。这里的Provider是固定脚本，不是收费模型。

`context_sha256`只标识本轮系统上下文快照，不是文件指纹或账单；两次相同因为系统上下文相同。每次演示都会重新创建value=1的临时文件。文件指纹只能检测版本变化，不能表达人的执行许可，所以仍需你确认。
