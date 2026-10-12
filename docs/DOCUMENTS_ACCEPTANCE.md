# 文档与个人知识本地验收

2026-10-12，增量实现V2.3，沿用现有workspace.sqlite3及文件审批、执行队列、收据和条件撤销。

支持PDF、DOCX、UTF-8 TXT/Markdown正文抽取，PDF页、DOCX段落/表格行、文本行来源引用。单文件32 MiB、PDF200页、正文200000字符、最多2000抽取单元；扫描件显示无正文提示，DOCX提示未包含页眉/脚注/图片正文。拒绝损坏、加密、越界、链接和异常DOCX附件；解析在拥有式子进程中进行，Windows Job Object保证取消/超时关闭其子进程树。

PDF合并、按页提取、旋转、图片转PDF和DOCX→PDF输出新文件。官方LibreOffice26.8.1安装包SHA-256为c6298b10cfa1748bcbedad94c62ce771e240e5021bfd6d7a967cd571b04b5312，以静默管理解包方式准备在项目内；实际中文DOCX生成单页PDF并成功抽取中文正文。转换时隔离用户配置，来源快照在确认和发布时校验；禁止覆盖原文件。已完成成果释放暂存字节，收据和撤销仍保留。

个人索引使用既有本机BGE和有引用片段，禁止远端Embedding建库。每批20文档/500片段、每目录2000片段；文字检索作为显式模式和缺本地模型的提示回退。两份本机夹具语义检索将物理资料排在历史资料前（相关分数0.7233）。搜索前检查授权和源文件哈希，排除后续修改的旧片段；索引可以移除，源文件保留。共享目录后文档工具加入同一Agent Loop，模型仍不能执行保存。

Vault绑定普通资料目录；支持结构化摘录草稿、编辑Markdown、粘贴聊天整理成果，再预览/确认保存。该过程不冒充已完成真实模型总结质量验收。

后端292项全量测试通过（随后补充表格顺序/独立引用RED→GREEN）；文档定向11项通过，新增引用验证1项通过。前端55项单元和静态检查/构建通过，文件/文档Electron4项通过。完整桌面回归将在依赖准备停止后再次执行，最终计数以持续产品交付报告为准。全部使用生成夹具、离线Provider和本机模型，无真实DeepSeek请求。

最新文档定向12项及完整Electron18项通过；所有自有模型准备进程结束后完成稳定全量桌面回归。工具Schema只在共享目录可用时加入模型请求；每步上下文预算与实际请求使用同一份Schema快照。8192窗口的既有设置回归已修复并通过。

依赖来源：[LibreOffice官方包与SHA](https://download.documentfoundation.org/libreoffice/stable/26.8.1/win/x86_64/LibreOffice_26.8.1_Win_x86-64.msi.mirrorlist)、[PDF命令行导出](https://help.libreoffice.org/latest/en-US/text/shared/guide/pdf_params.html?DbPAR=SHARED3&System=WIN)。
