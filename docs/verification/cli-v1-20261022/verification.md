# CLI v1验收记录

日期：2026-10-22。分支`learning/unit-01-cli-read`，基线`683b38a78b30ff01cd68bc6cb850db3decb4b5fa`及本地未提交修改。用户明确授权持续交付与真实模型验收；未自动提交、推送或发布，未打开旧用户数据库。

## 真实模型与业务结果

服务`https://api.deepseek.com`，模型`deepseek-flash`，实际OpenAICompatibleProvider/httpx HTTP请求，非流式。只使用新建的average演示项目及本次任务/项目约定/工具说明，没有固定脚本规定调用顺序。密钥优先从进程再从Windows用户环境补读，未打印、不入库。

| 运行 | 实际过程和结果 |
|---|---|
| 现有开发环境首跑 | 6次模型请求：Search×2 → Read×2 → Edit → Read → Test → 最终回答。两次副作用预览由操作助手核对后输入yes，范围仅用户授权的演示文件和unittest。3个原测试与独立行为检查通过，测试字节未变 |
| 独立wheel安装版 | 新建第二份有Bug副本；6次模型请求：第1步Search+Read，第2步Read×2，第3步确认Edit，第4步回读，第5步确认Test，第6步解释结果。3测试通过，独立4组输入行为核查通过 |
| 安装版跨进程恢复 | 恢复同一session的14条历史；1次真实请求正确解释上轮文件与除零原因，未再调用工具；最终保存16条消息、两个completed Run |

本轮共13次真实模型请求，无自动HTTP重试。每次修复上限8请求，恢复上限2请求，均未耗尽。适配器当前不保留服务返回usage，不能给出精确计费Token或金额；`--trace`显示的Token为本机估算。没有评测通过率指标。

安装版的原始持久记录导出在[live-session.json](live-session.json)，含模型产生的7个tool_calls、配对结果、两个Run配置与7步上下文诊断；只替换了绝对演示/解释器路径前缀，没有鉴权头。代码差异在[live-change.diff](live-change.diff)，原测试SHA256在JSON中。源码包中不包含演示数据库。确认输入由本次执行助手在逐次审阅后完成，不声称用户亲自在终端输入过yes。

独立核查命令：`python examples/coding-task/check.py 本次演示目录`；[实际结果](cli-live-check.log)为`passed=true`，3测试通过、独立行为检查通过；checker本身不调用模型、不修改文件。恢复输出见[实际恢复记录](cli-live-resume.log)。首跑受限进程的checker因替换文件ACL无法读取，使用有权限的进程重跑通过；没有把环境权限失败冒充产品失败或删去记录。

## 独立安装

`uv build --project backend --wheel --out-dir .local/cli-v1-dist`成功；新建`.venv-cli`后安装本地wheel成功，基础12个发行包（含Herta及间接依赖）。源码声明仅httpx/pydantic两项直接依赖；安装从site-packages加载，清除PYTHONPATH后验证，非复用旧可编辑环境。

[导入证据](cli-installed-import.log)确认FastAPI、NumPy、MCP、Torch、Piper、Uvicorn均未安装；[help](cli-installed-help.log)、[固定Read本地演示](cli-installed-demo.log)、[新启动器离线退出](cli-launcher.log)通过。安装记录见[build](cli-build.log)、[install](cli-install.log)、[lock](cli-lock.log)。本机CLI Python为3.12.13，httpx0.28.1、pydantic2.14.1；原开发环境pydantic2.13.5。没有发布PyPI包。

整理格式后重新[构建](cli-build-final.log)、[安装](cli-install-final.log)，[核对](cli-release-check.log)97个包内Python文件与当前源码字节一致，并核对安装包未含数据库/密钥/参考快照、核心依赖只有2项；新安装版Read→保存→列会话[冒烟通过](cli-installed-final-smoke.log)。这次重新构建只含格式变化，没有新增付费调用。

## 本地自动化验证

| 实际命令 | 结果与证明范围 |
|---|---|
| `python -m unittest discover -s backend/tests -p 'test_cli*.py' -v` | 96项通过，35.239秒；最终格式整理后再次96项通过40.121秒。工具实际临时文件、确认/拒绝、冲突、测试失败分类、取消、上下文、保存/恢复与项目隔离；固定Provider/Mock HTTP均不是模型智能验收，见[最终日志](cli-v1-tests-release.log) |
| `python -m unittest discover -s backend/tests -v` | 447项，444通过、3可选语音跳过，152.855秒；包括旧服务/共享持久化回归。执行时设置HERTA_LIBREOFFICE指向主目录已存在的本机引擎，见[最终日志](backend-v1-full-final.log) |

保留的失败：新保存参数测试先6失败；增加取消接纳测试暴露created遗留，修复后可继续；默认路径测试暴露无用户目录环境错误，修复；基础安装契约先失败后拆分依赖。首次CLI全组6错误来自旧Mock测试清空所有环境后仍使用默认保存路径，已让这些测试显式`--no-save`，保存行为由专用临时目录测试覆盖。首次完整后端447项中旧DOCX转换失败1项（工作区缺本地引擎路径）、3跳过，指定已有引擎重跑后通过。原始红灯和失败日志留在本目录。

早期6项存储测试的2个清理错误来自测试自身sqlite连接上下文只提交事务而未关闭连接；改为closing后消除，并保留cli-history-green.log实际失败记录。全backend Ruff lint通过，10个修改/新增Python文件格式通过；全仓格式检查发现未改动的旧`test_desktop_start_guard.py`一处排版问题，已与HEAD字节核对为原有问题，未为此改旧桌面测试。对应日志[lint](cli-v1-ruff.log)、[变更格式](cli-v1-format-changed.log)、[原全局格式失败](cli-v1-format.log)、[diff检查](cli-v1-diff-check.log)。

只修改CLI、共享持久化适配、包装元数据和文档；前端/Electron业务没有改动，本轮未重新运行前端/Electron和真实语音。完整后端通过不等于已复验桌面交互与真实供应商全部效果。

## v1能力与限制

已完成本次小范围交付目标：独立安装、真实小编码闭环、人工确认、结果核查、会话保存/恢复、核心机制与源码对照文档。界面默认demo明确标注；真实模式须显式选择。历史教学资料保留，不再连续新增教学单元。

仍明确限制Windows unittest、有界UTF-8和字面搜索、单处编辑/已有目录新建；没有通用Shell、pytest、自动安装依赖、OS沙箱、跨文件事务、多Agent或完整模型语义压缩。内置路径检查不能限制测试脚本的系统访问。运行或提交边界被打断后，已经发生的文件修改不回滚，未知结果不重试。默认CLI数据是明文，由用户管理。

本次验收仅证明两次同类小修复及一次会话恢复；不宣称任意真实项目可自动完成，也未新增未经验证的能力。

最终[独立审查](review.md)未发现Critical/Important阻塞项；审查者另在精简环境补跑46项相关测试及取消/写入失败/跨进程锁探针，不与上表重复累计数量。v1按本次收敛标准完成本地交付，源码、安装包、运行环境与资料留在当前隔离工作区；未自动提交推送。

独立审查发现的非阻塞小限制：从Herta仓库根搜索可能命中`.venv-cli`中的安装副本，消耗有界搜索预算；内置排除集未包含该环境名。暂缓调整，操作时以`backend`缩小范围。本次真实演示目标目录不含虚拟环境，不受影响。
