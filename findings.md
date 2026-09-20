# Phase 0 发现

## Phase 1 决策
- Phase 1 已完成，26 项离线测试与 Ruff 检查通过。教学说明见 docs/phase-1-walkthrough.md；真实模型联调尚未执行。
- 默认 Python 是 Hermes 的 3.11.9，改用 uv 在项目 .local/python 内安装 3.12，再建立根目录 .venv；不在 Hermes 环境安装依赖。
- 原生异步 HTTPX 实现最小 Chat Completions 适配器，避免引入供应商 SDK；Pydantic 验证内部消息、配置和响应结构。
- 默认 DemoProvider 完全离线且明确标注为固定回显；真实模型使用 --provider openai 显式开启。
- Phase 1 每次正常 run 只调用一次模型。for 循环和 max_steps 是 Phase 2 的结构边界；不制造无意义多次请求来演示循环，不声称已经测试工具预算耗尽。
- 会话失败/取消保留用户消息，不追加假 assistant 回复；finally 释放会话占用。

- 输入文件：hermes-agent-main.zip、大黑塔原始语料.md、大黑塔原始语料的整理思路.md。
- 当前目录没有业务代码，未发现适用的 AGENTS.md。
- 用户要求每次只做一个阶段，本次交付仅为 Phase 0。
- ZIP SHA256：3F5F65CE7BDBE33B59463CBDF20E73CEA5930FBA5B2B9C4515663F5EB2CD72D3；不把 main 文件名当作确定的 Git commit。
- 压缩包含独立桌面应用、分拆后的 agent 模块及多个子目录许可证，需追踪实际调用链，不能按旧版 Hermes 的文件布局推断。
- 角色输入包含台词/角色故事与整理建议；本阶段只检查目录和内容类型，不生成衍生材料。
- 根 LICENSE 实测为 MIT，Copyright (c) 2025 Nous Research；已保留解压源码原许可证，子目录许可证需逐项判断。
- 入口声明 pyproject.toml:413 → hermes_cli.main:main；AIAgent 位于 run_agent.py:229，经 TurnFacadeMixin 转发到 agent/conversation_loop.py。
- tools/registry.py 的 register 接收现成 schema 字典，get_definitions 包装为 function schema；dispatch 做名称查找与结果/异常统一，并非统一 Pydantic 参数验证器。
- Hermes 的 SOUL 由 prompt_builder.load_soul_md 从 HERMES_HOME 读取，可能扫描/截断；Herta 需要另行实现整份稳定注入。
- 真实循环在 conversation_loop._run_conversation_turn:1429；1520 行检查 max_iterations 与 iteration_budget，另有 grace call，不能将其说成绝无额外调用的简单 for 循环。
- turn_context.build_api_messages:1155 在每次 API 请求前添加 system message；system_prompt 将 stable/context/volatile 三段拼接，含许多 V1 不需要的能力。
- 工具结果通过 tool_executor.py:1074 配对 tool_call_id，先持久化再发 tool.completed。
- SessionDB 使用 SQLite，默认 HERMES_HOME/state.db；JSONL 有故障转存等用途，并非主会话存储。
- 工具 timeout 是等待截止时间与工作线程中断信号组合；放弃等待不能保证强制终止非协作线程。Herta 拟采用 asyncio 原生异步工具和有限网络 deadline。
- 参考官方 Python 3.12 asyncio、Pydantic JSON Schema、MDN SSE、Electron security 文档核验方案；没有用线上 Hermes 替代本地快照。
- 最终决策：本阶段仅复用 LICENSE 文本，无业务代码 reuse/adapt；核心机制参考后重写。V1 采用独立异步 Runtime、SSE、本地 SQLite 历史及简单 NumPy 向量存储方案。
- 三份原始输入哈希复核未变；24 个被行号引用的源码文件与 ZIP 哈希一致，13,888 个压缩包文件均已解压存在。
# Phase 2 补充：Windows 工具闭环

- 用户确认 Ctrl+C 取消当前轮、保留 Session。同步输入循环外持有 Runner，每轮只运行一个可取消任务；不用 stdin 线程、loop.add_signal_handler 或 Linux 进程信号写法。
- 工具调用记录与结果必须配对。取消时只为 pending id 回填 cancelled，已完成结果保持不变；max_steps 最后一轮仍要求工具时不执行，而回填预算耗尽结果。
- Registry 的同一参数模型既生成 schema，也供 Executor 严格验证 JSON；失败以 ok/data/error 回填，不把底层异常正文发给模型。
- Windows 子进程内定时触发 SIGINT 已验证模型等待、工具等待、后续轮继续及单条消息退出 130；本地取消不保证远端模型停止计费。
- 本阶段未引入新依赖或复制 Hermes 业务代码，原始语料仍留待 Phase 3。
