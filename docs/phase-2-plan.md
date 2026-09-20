# Phase 2 实施计划

范围与消息协议见 phase-2-design.md。原地保留用户学习注释和现有独立环境；不更改语料、Hermes 或系统 Python。

1. 新建 tools/registry.py、executor.py、echo.py 与 tools/__init__.py。先测试重复注册、schema、严格参数、未知工具、超时/取消，再实现。统一 JSON 结果为 ok/data/error；参数基类禁止额外字段及非有限值。
2. 扩展 runtime/messages.py、session.py、agent.py 与 llm/base.py。先覆盖两步闭环、多个调用、预算耗尽及取消闭合，再实现不可变 ToolCall、角色编码、待处理 id、顺序 Executor 与模型请求预算。
3. 扩展 llm/openai_compatible.py 并更新 demo.py。HTTP 测试覆盖工具 schema 与回填、损坏/重复 id、旧 function_call 拒绝；普通聊天请求保持兼容。
4. 改造 __main__.py：Runner 重复运行单轮任务，--demo-tools/--demo-delay/--tool-timeout 复现成功、超时和取消。真实客户端在同一 Runner 中关闭。测试 Windows SIGINT 取消后继续输入，保留 Phase 1 CLI 回归。
5. 运行完整 unittest、Ruff check/format 和 PowerShell 手动命令；更新 README、架构状态、Phase 2 复现教程与任务记录。真实模型未联调则明确说明。完成后停在 Phase 2。

每个实现步骤均先运行新增测试观察预期失败，再实现并验证；不新增依赖。
