# Phase 6 阶段1：打开与关闭 Herta

本阶段已实现真实 Electron 窗口、自启 Python/FastAPI、状态展示、关闭清理和重复启动。还没有聊天、历史列表、设置面板或阶段2视觉布局。原 Agent Loop、Persona、RAG 和 Store 代码没有修改。

## 亲手验证

在 PowerShell 运行：

```powershell
Set-Location -LiteralPath 'D:\Desktop\herta-agent'
npm --prefix frontend run dev
```

窗口立即打开，显示“正在启动”，随后显示“服务就绪”或“配置未就绪”。缺聊天配置也能启动本机服务，不会偷偷切到 demo。此处“服务就绪”只表示本机 health 确认可用，不代表远程凭据或模型效果已验证。当前输入框始终禁用。

要完全离线看到“服务就绪”，可以在本次 PowerShell 中明确选择 demo：

```powershell
$env:HERTA_SERVICE_PROVIDER = 'demo'
npm --prefix frontend run dev
# 关窗后恢复默认选择：
Remove-Item Env:HERTA_SERVICE_PROVIDER
```

关窗后等待终端命令结束，再运行同一命令。重复启动会激活已有窗口，不另外启动后端。也可以最小化窗口再运行启动命令，检查已有窗口恢复。关闭时先走正常清理；仅在20秒超时后对仍由自己持有的 Windows 启动器进程树执行强制终止，不按进程名批量杀 Python。

Main 不依赖当前工作目录，使用绝对路径定位 `.venv/Scripts/python.exe`、薄 host 与资源。开发数据库是 `.local/desktop/sessions.sqlite3`，不会自动搬入旧服务数据库。测试使用临时目录，不向这个开发数据库添加历史。

开发脚本与 Electron 通过 Node IPC 通知退出，因为 Windows GUI Electron 的 stdin 不可靠。Electron 与 Python 则使用独立的 stdin/stdout：Python 在 FastAPI 完成 startup 后报告动态端口和真实 PID，Main 再检查 health；收到 shutdown 或父进程管道 EOF 后，Python 调用现有 Manager 清理并退出。开发脚本意外结束也会断开 IPC，让 Electron 清理后端。

## 三层职责

- Electron Main：拥有原生窗口和 Python 子进程，管理启动/退出，读取本机 health，并通过窄 IPC 返回状态。
- React Renderer：展示状态与最小 Welcome，不能访问 Node、凭据或任意 HTTP/文件接口。
- Python Backend：沿用现有 Runtime、SessionStore、RunManager 与 FastAPI。薄 host 只适配桌面进程生命周期。

应用自己拥有子进程，才能做到一条命令打开、动态端口连接、只清理自己的服务，以及关窗后不遗留后台 Python。单纯连接一个由用户另外打开的服务无法保证这些行为。

## 环境与复现

当前验证环境为 Windows 10、Node 22.16.0、Python 3.12.13，依赖由 package-lock.json 固定。Vite 6.4.3 与现有 Node 版本兼容。新环境先按 README 建立 Python `.venv`，再安装前端：

```powershell
Set-Location -LiteralPath 'D:\Desktop\herta-agent\frontend'
npm ci
npx install-electron --no
```

Electron 安装需下载官方 Windows 二进制。本次下载经本机代理完成，按 Electron 包提供的 SHA256 校验；代理配置没有写入项目。Key 仍只从启动环境读取，不写入前端配置或日志。

```powershell
Set-Location -LiteralPath 'D:\Desktop\herta-agent'
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend test
npm --prefix frontend run test:e2e
.\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
.\.venv\Scripts\ruff.exe check backend frontend/desktop
.\.venv\Scripts\ruff.exe format --check backend frontend/desktop
git diff --check
```

实际结果：9项 Vitest 测试、6项 Playwright Electron 测试、178项后端测试通过；typecheck、lint、build、Ruff check/format check、diff check 通过。Electron 用真实 Windows 桌面权限运行，包含三次启停、中文空格路径、目录外启动、缺配置、缺解释器、单实例激活、后端骤停及开发入口；EOF 测试验证真实解释器退出、SQLite可重开且其他 Python 进程仍存活。受限执行环境会导致 Electron 渲染子进程失败，不能把这种环境下的失败计作通过。

独立审查发现停机失败会永久缓存失败 Promise，已先用失败测试复现，再修复为允许下一次关闭重试。阶段1结束后停止；没有调用真实模型或 Embedding API，Phase 4 真实 RAG 效果仍待验收。
