# Phase 0 工作记录

## Phase 1 最终交付与验证
- 已完成最小 Python Runtime、内存历史、Provider 接口、Demo/HTTP Provider、CLI、配置与清晰异常。
- Phase 1 的正常 Run 只有一次模型调用。工具循环、预算耗尽路径、Persona、RAG、API、SSE 和桌面尚未实现。
- 最终运行 `python -m unittest discover -s backend/tests`：26 项全部通过（包含 Windows 中文管道修复后的回归）。
- `ruff check backend` 通过；`ruff format --check backend` 通过，15 个 Python 文件排版一致。
- 默认离线中文单轮启动成功；交互两轮与退出由 CLI 子进程测试验证。
- 安装后的模块及 herta-agent 命令能从 D:\Desktop 运行；隔离模式 sys.path 没有 Hermes 路径。
- `uv sync --project backend --extra dev --python 3.12 --locked --offline` 成功，锁文件与安装一致。
- README 和 Phase 1 教程的链接/函数行号已核验；后续阶段业务目录未创建。
- 真实供应商联调未执行：没有使用任何真实模型 Key，也没有发真实模型请求。HTTP 契约测试使用 MockTransport。
- 完成 docs/phase-1-walkthrough.md、README；更新架构状态和复用记录，无 Hermes 业务代码移植。
- 本阶段已停止，等待用户确认 Phase 2。

## Phase 1 开始
- 用户“下一步”授权进入 Phase 1；读取已有计划、发现、架构与工作记录。
- py 启动器未发现已注册 Python，继续检查 PATH 上的解释器；不修改现有 Hermes 环境。
- 沙箱首次下载 Python 被网络权限阻止；通过工具自动审批的联网权限在项目内继续下载。
- uv 默认全局缓存不可写；后续所有 uv 命令显式指定项目 .local/uv-cache。
- 已建立 Phase 1 消息/会话/Provider/循环骨架与 CLI，准备依赖安装和离线测试。
- 独立环境：Python 3.12.13；uv 生成 backend/uv.lock 并将项目 editable 安装到根目录 .venv。
- 首轮 26 项 unittest 全部通过；Ruff 发现测试闭包绑定、排版及 CLI input 的异步检查提示。
- 修正测试循环闭包绑定并统一排版。教学 CLI 的输入阶段无后台任务，保留同步 input 并作精确单行豁免，避免使用不可取消的 stdin 工作线程。
- 增加 timeout 布尔值拒绝和 API Key 换行校验；Ruff check 已通过。正在编写教程与运行说明。
- 最后从项目目录外实测发现 Windows 管道编码造成中文显示乱码；修复 CLI 重定向标准流为 UTF-8，并将交互测试改为中文且不依赖 PYTHONIOENCODING 环境变量。

## 2026-09-18
- 读取完整用户需求并检查项目目录。
- 使用 planning-with-files-zh 技能建立三份进度记录。
- 开始检查参考源码和许可证。
- 已记录压缩包哈希，并校验 ZIP 路径不会越出 references；正在解压到独立参考目录。
- 首次工具调用工作目录不存在，未执行；已修正。
- 完成解压和根 MIT 许可证核查；定位实际循环、工具注册/派发和 Persona 入口。
- Windows 下 rg 路径通配符未展开；后续改用目录检索或 rg -g。
- 已追踪循环、持久化、超时与中断；开始编写三份正式文档和 Phase 0 手动复现说明。
- 部分大段工具输出被截断，改为读取关键函数附近的小段并定位精确行号。
- 完成三份正式文档及 phase-0-walkthrough.md：包含目录职责、执行链、精读函数、PowerShell 复现步骤和自测问题。
- 新增 .gitignore；根 LICENSE 原样复制到 LICENSES/Hermes-MIT.txt。
- 静态阅读 registry 与 sequential timeout 的测试文件，未执行其测试或导入 Hermes。
- 开始核验文档行号、参考源码与 ZIP 一致性、原文件哈希和 Phase 0 范围。

## 最终静态核验（已通过）
- 4 份 docs 文件存在且非空，Markdown 代码围栏成对。
- 文档里的显式 .py/.toml 行号引用路径存在且没有越界，共涉及 24 个不同源码文件。
- 这 24 个源码文件逐项与 ZIP 内对应文件做 SHA256 比较，全部一致。
- ZIP 内 13,888 个文件均能在 references 中找到；该项检查完整解压存在性，不声称逐个审计全部代码。
- 3 份原始输入 SHA256 与开始记录一致，未改动原文件。
- LICENSES/Hermes-MIT.txt 与参考根 LICENSE 哈希一致。
- backend、apps、persona、knowledge、.venv、.local 均未创建，范围仍为 Phase 0。
- 手工对照核心分支：循环 1520/1555、工具结果 1074/1075、system 注入 1155、取消 109、许可证原文。
- 新增源码快捷链接指向前述已验证的 5 个函数。

## 验证边界与交付状态
- 未运行 Hermes、未导入其模块、未安装项目依赖、未调用真实模型。
- 本阶段不含业务代码，未运行 pytest；上述是文档与来源静态检查，不是 Runtime 功能测试。
- 三份正式分析文档及手动复现教程已交付。Phase 0 完成，停在这里等待用户确认，未进入 Phase 1。
