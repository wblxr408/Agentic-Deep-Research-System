# 从个人书架导入研究方法

2026-10-26，从[用户 Skill 书架](https://bo-skill-bookshelf.vercel.app/)的166个目录条目中筛入45项，已通过当前登录账号的原“导入文件”入口保存。来源固定为网站指向的仓库提交 `db8ce71a00e9957030a4a19b1c1a474dfb16aa2e`，发布为2026-10-22.5。发布包元数据标为165项，与当前目录条目数量分别保留。

## 使用

这45项现在作为仓库随附的默认方法。正常配置数据库并启动应用后，账号首次读取方法集合或开始匹配时，会在本人注册表中自动初始化；无需下载书架或逐个上传。后端Docker镜像也包含同一套资源。

初始化事务按账号串行，已有同slug方法及停用／删除状态保留。新建的默认方法各自拥有独立账号ID；用户可修改、停用或删除，不影响别人。20.1.1源码开始记录本人默认来源基线与个人修订：可确认内容相同的既有副本纳入来源，无法确认的同名方法不自动关联；旧默认副本的初始内容若与当前包不同则标记基线待确认。普通编辑在事务中追加新修订，界面提交所看到的版本，过期修改返回冲突，不改写历史。版本差异、升级与回退界面仍在20.1.2实现；上述新增源码尚未端到端验证。

在 Skills 中按名称搜索、按阶段筛选、阅读或启停；在研究选项的“资料与方法”中选择自动匹配或本次使用。绘图中可选择统一科研绘图、复杂网络分析、引用网络构建和研究脉络与争议图谱四项。写作阶段筛选可见25项。

方法包括19项研究与文献、3项学术写作与审查、9项研究输入／绘图／交付／质量方法，以及14项报告结构方法。各条的来源、版本、许可及全部166项纳入／排除理由见[完整清单](../resources/research-skills/bookshelf/manifest.json)。目录中文名为“研究现状”的 State of Art 原文实际属于艺术与创意展示，已据原文排除。

## 方法目录

| 用途 | 已加载的源 Skill |
| --- | --- |
| 文献与研究 | academic-pipeline、academic-research-graph、bib-search-citation、bibliometrix-guide、citation-network-builder、dblp-cli、deep-research、literature-search-openalex、orcid-api、paper-search、research-gap、systematic-literature-review |
| 企业与市场 | company-intel、competitive-analysis、intelligence-collection-disciplines、market-researcher-agent |
| 数据与图谱 | geopandas、knowledge-graph-construction、networkx |
| 写作与审查 | academic-paper、paper-audit、cover-letter |
| 研究输入与交付 | scientific-data-visualization、pdf、documents、presentations、spreadsheets、agent-crosscheck、grilling、task-contract、browser |
| 报告结构 | artifact-template-analytics-dashboard、annual-impact-report、business-review、design-report、experiment-analysis、growth-strategy、investment-committee-memo、legal-memorandum、market-trends-report、product-strategy、strategy-memorandum、system-design、three-statement-forecast、weekly-business-review（后13项同为 artifact-template- 前缀） |

## 接入

[方法文件](../resources/research-skills/bookshelf/)使用原 Markdown 注册表格式。Prompt 和 Stage 段提供 ADRS 阶段方法；元数据声明具体触发词。全部入库后，运行仍按查询、top-k、阶段和字符预算选取。

来源、署名及原依赖随文件保留，原主要 SKILL 文本在长度允许时嵌入个人导入副本作为归档引用；归档原文未声明为阶段加载引用。原始 ZIP 和配套资源位于本机 `.codex-homework/bookshelf/packages/`，个人导入副本位于 `.codex-homework/bookshelf/importable/`。仓库分发本项目适配方法和固定来源链接。

复合流水线和多视角方法分配给原有阶段。原脚本、R／GeoPandas 等计算环境及宿主插件不会因文本入库自动接入。文档模板在本系统接入报告结构，二进制导出沿用现有契约；绘图使用已有受控渲染适配器。

## 实际操作

前序45次原接口导入均成功。已回读 OpenAlex 的方法、阶段和来源，写作／绘图筛选正常。临时同源窗口选择 OpenAlex、多库论文检索和科研绘图，采用图文简报并手选科研绘图后，原确定性计划预览返回“Can start”。未点击开始研究。

默认分发另以当前新增行为的单一用例连接既有PostgreSQL：先观察新账号返回0项的失败断言，实施后同一用例通过，覆盖首次／并发获取45项、个人调整与删除保留、不同账号独立内容。未运行既有回归或构建／探针，未构建Docker镜像。现有本机API进程本轮未重启；该行为在加载新代码的服务进程中生效。详见[默认分发交付](acceptance/default-methods-20261026.md)。

详细过程和界面见[实际导入记录](acceptance/bookshelf-20261026.md)。
