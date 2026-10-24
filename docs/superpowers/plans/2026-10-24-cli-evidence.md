# CLI真实任务与工程证据实施计划

> 按用户2026-10-24“开始做、按优先级顺序来”的明确授权，使用Superpowers executing-plans在当前会话连续执行；保留guided-development源码讲解。任务内不重复请求常规确认；无自动Git提交或推送。

**目标：** 让现有CLI在小型真实项目中完成有独立证据的编码任务，再完善项目测试环境、上下文证据与面试入口。

**架构：** 保留唯一Agent/Registry/Executor/Approval/Provider/Session/SQLite。扩展已有examples/coding-task的准备和核查入口；目标项目是自建副本。生产变化只落在当前测试工具和Provider/事件的必要接线。

**范围依据：** 本轮用户批准的四项优先级；基线4821d53，已有CLI v1和终端验证记录。Python3.12+、Windows；不加入Shell、OS沙箱、多Agent、复杂Hooks或新业务面板。

**最新收敛：** 用户因面试临近，只实施P1与P4，跳过P2/P3。保留它们为原建议的历史记录，不作为本轮待交付项。无业务代码或依赖变更时，不为文档/示例打包重装不变的产品，也不重复耗时旧全套回归；运行相关CLI测试与静态检查，保留旧回归限制。

## 风险检查

- 核查器从模板计算原测试hash，不相信模型总结或目标目录内可改写的hash。
- 每个演示新建副本；私人目录、旧数据库、旧演示和运行中用户进程不操作。
- 模型工具由真实HTTP响应产生；故意有Bug的初始模板、拒绝和外部编辑注入均明确标记。
- 工具ok和测试passed分开；无测试、跳过、收集错误不能伪装任务通过。
- 当前Run失败保留结果；不足以形成通用成功率、性能或费用结论。

## P1：任务证据（先实施）

文件：扩展examples/coding-task/prepare.py、check.py；新增cases.py、case_checks.py和cases/{checkout,wordcount,approval}/模板；backend/tests/test_cli_coding_cases.py验证准备和独立核查。

- [x] 核查测试先失败再实现，默认average入口保持兼容；最终7项grader通过，包括skip先红后绿。
- [x] checkout6请求：初始3失败→2文件修复→7测试及独立输入通过，原测试未改。
- [x] wordcount13请求（5中断+8恢复）：JSON功能、5个新增测试；断言失败后修正，8测试及独立检查通过。
- [x] denial5/conflict4请求：no拒绝和外部编辑注入均有实际错误与文件核查，总请求28未超48上限。
- [x] 脱敏轨迹/差异/检查结果、失败和中断说明保存；CLI最终120项通过，独立审查通过。

## P2：项目测试环境

先阅读pytest官方接口，具体小范围方案沿用run_tests/test_command/TestParameters和TerminalApproval，不造第二执行器。用户指定解释器，模型只选固定runner；先测缺解释器、缺pytest、收集错误、断言失败、取消、路径和原unittest兼容，再接线和安装更新。

## P3：上下文证据

沿用ContextEngine.prepare，比较同一历史在两个窗口下的保留索引与工具配对。Provider中真实usage字段可选、缺失记unknown；耗时按真实事件计量。不根据缺失usage猜费用，不宣称未测提升。

## P4：展示与交付

更新CLI指南、README、INTERVIEW及架构/来源文档；提供新任务准备与独立检查命令、实际轨迹导览。重新打包本机CLI，定向及完整适用后端回归，失败按名记录；最后独立审查。录像只提供录制脚本，不假装已录制；不自动推送/公开仓库。

实际交付决定：生产包/依赖未变，不重复打包或安装；只跑全部CLI及脚本/格式检查。旧桌面完整回归未重跑，原问题不宣称修复。docs/DEMO.md、真实证据与问答已更新，独立复核无Critical/Important；无录像、提交或推送。
