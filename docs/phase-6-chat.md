# Phase 6 阶段2–5：桌面聊天

已实现 Sidebar、Welcome、Composer、角色素材、明暗主题、新会话、分页历史、流式回答、Tool/RAG 活动、Stop 和重开恢复。只在首次发送时创建新会话。SQLite 是正式历史来源，半截回答只在内存里展示，取消或失败不会带进下一轮上下文。

## 启动与真实模型

先关闭旧桌面窗口，在 PowerShell 设置配置并启动：

```powershell
Set-Location -LiteralPath 'D:\Desktop\herta-agent'
$env:HERTA_SERVICE_PROVIDER = 'openai'
$env:HERTA_BASE_URL = 'https://你的服务地址/v1'
$env:HERTA_MODEL = '你的模型名'
$chatSecret = Read-Host 'Chat API Key' -AsSecureString
$env:HERTA_API_KEY = [System.Net.NetworkCredential]::new('', $chatSecret).Password
Remove-Variable chatSecret
npm --prefix frontend run dev
```

服务需要兼容流式 Chat Completions 和工具调用；Base URL 不含 `/chat/completions`。Key 仅从启动环境继承，不写入配置或 Renderer。更新环境后要完全关闭并重新启动应用。依赖安装见 [阶段1说明](phase-6-stage-1.md)。无需手工启动 Python 服务。

完全离线的简单回显可将 `HERTA_SERVICE_PROVIDER` 设为 `demo`，但它不能代替真实模型 Streaming/Tool/RAG 验收。

## 亲手验证

1. 发送问候，检查回答逐步出现；Enter 发送，Shift+Enter 换行，中文组字时 Enter 不应发送。
2. 点击新对话再发送一条消息；在侧栏切换会话，确认各自历史、草稿和运行状态互不混淆。
3. 请模型调用 `echo` 工具，展开活动查看参数与结果。是否实际调用由模型决定。
4. RAG 需要独立的 `HERTA_EMBEDDING_BASE_URL`、`HERTA_EMBEDDING_MODEL`、`HERTA_EMBEDDING_API_KEY` 和已构建索引。按 [Phase 4 教程](phase-4-walkthrough.md) 配置并运行 `.\.venv\Scripts\python.exe -m herta_agent.rag build`，再重启桌面。问“请检索黑塔与螺丝咕姆的关系并给出来源”，展开 search_knowledge 查看来源、片段和相关度；相关度不是事实置信度。建库和查询会访问你配置的 Embedding 服务。
5. 请求较长回答，生成中点击 Stop；等待已取消状态，再发下一条。半截文本应消失，已提交工具记录仍保留。
6. 关闭窗口，重新运行启动命令，选择旧会话。消息、工具结果和终态应恢复；partial 不恢复。桌面数据库在 `.local/desktop/sessions.sqlite3`。

## 验证与边界

2026-09-23：typecheck、lint、21项前端单元测试、7项真实 Electron e2e（含 build）、178项后端 unittest、Ruff check/format 和 diff check通过。e2e 覆盖中文输入、实际流式分段、跨会话并行、工具/RAG 展示、取消、重启历史恢复和小窗口布局。夹具走实际后端与临时 SQLite，不调用真实 API；真实供应商兼容性和真实 RAG 效果仍待验证。

Main 管理窗口、Python 子进程和固定请求通道；Renderer 管理展示与暂态；Python 继续负责唯一 Agent Loop 和持久提交。切换会话不切断执行，应用退出才清理自管进程。

断连后会核对持久状态，绝不自动重发 POST。若提前取消且无法确定是否接纳，界面保留未知状态并阻止重复发送，可手动核对；不会仅凭暂时查不到记录假称未执行。Markdown 链接当前只显示文字，远程图片和原始 HTML 不渲染。

本批未实施阶段6 Settings、阶段7完整故障验收矩阵或安装包。Provider 继续使用环境变量；没有修改 Agent Loop、Persona、RAG 算法或 Store 语义。
