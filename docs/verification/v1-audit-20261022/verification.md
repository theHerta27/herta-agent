# CLI v1只读审计验证记录

日期：2026-10-22。工作区`D:\Desktop\herta-agent\.local\worktrees\unit-01-cli-read`，HEAD683b38a78b30ff01cd68bc6cb850db3decb4b5fa，加上此前未提交的单元08成果；保留全部原改动。本轮只写审计、来源证据、规划与协作约定。

## 实际本地检查

Python可执行文件为`D:\Desktop\herta-agent\.venv\Scripts\python.exe`。测试前PYTHONPATH指向当前worktree的backend/backend/tests，并设置UTF-8和PYTHONDONTWRITEBYTECODE；从进程环境移除HERTA_*与DEEPSEEK_API_KEY，没有输出Key。

```powershell
python -B -X utf8 -m unittest discover -s backend/tests -p 'test_cli*.py' -v
python -B -X utf8 -m unittest test_runtime test_runtime_commits test_runtime_events test_runtime_streaming test_tool_loop test_tool_permissions test_tool_provider test_tools test_context test_context_engine test_project_context test_provider test_provider_env test_provider_streaming test_session_store -v
```

| 组 | 结果 | 日志 |
|---|---|---|
| CLI所有现有test_cli*.py | 84项全部通过，27.825秒，无跳过，退出0 | [cli-tests.log](cli-tests.log) |
| Loop/工具/Provider/上下文/Session Store | 103项全部通过，6.508秒，无跳过，退出0 | [core-tests.log](core-tests.log) |

两组测试方法不重叠，共187项，使用固定Provider或MockTransport，不调用真实模型；文件/SQLite/Windows测试进程则是真实临时夹具。CLI组按原有边界在沙箱外运行，以覆盖Windows子进程和取消行为；仅运行仓库代码及自己创建的临时资料。

本轮没有重跑2026-10-21完整435项回归、前端、Electron、GPU/语音，也没有执行新环境安装，因此不把历史报告或静态依赖图当作本轮产品验收。

## 上游只读获取与校验

GitHub GET固定镜像提交554bc4514ebaf83ef54d95bc44f4add7272d4f46和学习实现ce8f9f186058939da54c9d6fead78dfb5d0fd6c3，之后全部文件按SHA读取。24份缓存分别核对Git blob SHA、SHA256和固定文件树匹配；[source-evidence.json](source-evidence.json)保存具体路径、指纹、永久链接及阅读范围。源文件缓存只在.local，未复制到产品或本证据目录；此处只保留来源元数据。

普通终端网络GET最初被沙箱拦截，随后经授权只读网络调用成功。useCanUseTool.ts初次404，完整树显示为.tsx，按实际路径获取成功；保留此记录，不称快照缺文件。不运行上游代码，不复现其内部构建，不把镜像字节匹配扩大为npm原始归档完整性证明。

实际机制研究见[源码对照](../../architecture/claude-code-2.1.88-audit.md)，审计及交付判断见[v1审计](../../CLI_V1_AUDIT.md)。官方文档为2026-10-22滚动网页，没有冒填Git SHA或2.1.88版本标签。

## 变更与最终静态核验

- 业务快照覆盖当前工作区260个backend/前端源码/脚本/配置文件，审计前后哈希相同；原有08代码仍是原来的未提交改动，不因git diff中出现cli.py而冒称本轮修改。
- 现有核心函数、模型/文件数据、依赖、Lock文件均未变；主目录业务与原有资料未修改。
- 本轮新增2份审计文档和本目录元数据/日志，同步AGENTS.md、task_plan.md、findings.md、progress.md。不安装依赖、不调用付费API、不提交/推送、不启动下一交付阶段。
- 源码/文档空白、链接、固定SHA引用与前后哈希检查结果见[final-static-check.log](final-static-check.log)；业务初始哈希见[business-before.json](business-before.json)。

没有为只读文档重跑全量测试；上述两组是本轮新鲜结果，不能证明真实模型任务成功。
