# 从个人书架导入研究方法

2026-10-26，从[用户 Skill 书架](https://bo-skill-bookshelf.vercel.app/)的166个目录条目中筛入45项，已通过当前登录账号的原“导入文件”入口保存。来源固定为网站指向的仓库提交 `db8ce71a00e9957030a4a19b1c1a474dfb16aa2e`，发布为2026-10-22.5。发布包元数据标为165项，与当前目录条目数量分别保留。

## 使用

这45项现在作为仓库随附的默认方法。正常配置数据库并启动应用后，账号首次读取方法集合或开始匹配时，会在本人注册表中自动初始化；无需下载书架或逐个上传。后端Docker镜像也包含同一套资源。

初始化事务按账号串行，已有同slug方法及停用／删除状态保留。新建的默认方法各自拥有独立账号ID；用户可修改、停用或删除，不影响别人。20.1源码记录本人默认来源基线与个人修订：可确认内容相同的既有副本纳入来源，无法确认的同名方法不自动关联；旧默认副本的初始内容若与当前包不同则标记基线待确认。普通编辑在事务中追加新修订，界面提交所看到的版本，过期修改返回冲突，不改写历史。方法详情接入默认更新、个人差异和历史回退；上述新增源码尚未端到端验证。

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

## 默认更新与个人版本

方法详情中的“版本与更新”区分账号的当前修订与仓库随附版本，显示本人内容相对基线的变化、默认内容相对基线的变化，并可查看完整默认原文。当仓库更新方法包后，用户按需选择更新；对基线、个人内容和新默认内容做三方文本合并，重叠区域保留个人内容并标明位置，非重叠的默认变化可进入新修订。当前启停状态始终保留；历史修订只追加，不改写已被研究引用的内容。个人修改或默认变化超过4000行、合并后结构无效、方法标识变化时，不执行自动合并，用户可对照原文手动编辑。

既有方法若只有相同标识但无法确认来源，可先对照当前随附内容，再自行关联为未来更新的基线；关联不改写个人指令。当前版本不再提供某默认方法时保留个人方法与历史，不显示可用更新。用户可以浏览本人历史内容并选择回退；回退生成新修订并保留当前启停状态，恢复相应的默认来源基线。原有实现时期可能已经丢失的历史内容无法凭现有记录还原。

**ACI：** `GET /api/v1/skills/{id}/default-update` 返回当前修订、来源状态、默认版本、两组有界差异及合并冲突；`GET /{id}/default-source` 返回当前包内对应默认原文。`POST /{id}/default-association` 显式关联来源，`POST /{id}/default-update` 以期望个人修订、基线和目标身份检查后执行合并。`GET /{id}/versions` 分页列出本人修订，`GET /{id}/versions/{version}` 读取历史内容，`POST /{id}/versions/{version}/restore` 要求期望当前修订并追加回退版本。请求均以当前主体定位方法，不接收其他账号的来源；已删除方法不可通过这些入口复活。包内容、变更及目标身份来自随附仓库资源，不从网页自动下载或执行脚本。

个人编辑、启停、升级、回退和删除更新本人注册表代次；运行目录在读取时对照数据库代次，跨进程变更后重新装载。新版本继续通过原方法解析、阶段选择与任务工具授权交集，不因默认来源自行获得新工具或数据权限。已启动研究仍使用原冻结引用。对应源码控制点为 `app/skills/{defaults,service,versioning,registry}.py` 与 `app/api/skills.py`。

设计按 A2ABreak 基线 v1.0：A2AB-01《技能声明验证与委派准入》工程解决方案1、3、4，维持注册、阶段及执行结果边界；A2AB-03《上下文归属与跨租户隔离》工程解决方案1—3，方法、基线和历史都按主体过滤；A2AB-06《并发状态版本与审批绑定》工程解决方案1、3，当前修订、来源及目标身份在事务中检查；A2AB-08《结构化授权请求与权限不放大》工程解决方案1—4，方法文字和升级不单独扩大授权。原文位于 Basic Memory main `main/engineering/security/a2abreak/solutions/a2-ab-01-技能声明验证与委派准入`、`.../a2-ab-03-上下文归属与跨租户隔离`、`.../a2-ab-06-并发状态版本与审批绑定`、`.../a2-ab-08-结构化授权请求与权限不放大`。本次不新增远端Agent、委派、事件流、Webhook或分块产物，其余条目沿用已有适用性评估。上述为源码控制点，功能与安全均待最终统一端到端验证。

## 阶段上下文共享与研究评审职责（2026-11-03）

### 同次规划的问题级方法选择

原注册表的自动匹配按触发词／词项和优先级选候选；阶段编译再按阶段／学科／模板和授权筛选，尚不等于AI按问题选择。现在仅在已有Planner模型调用中，可附带analyst／reflection／report的冻结方法目录元数据，要求同次返回可选method_choices（阶段、已有ID和问题相关理由）。目录不能与完整原请求、4096输出及当前声明窗口／根份额共同容纳时不发送；固定流程、指定RAG目录／seed及简单事实等原本不调用Planner模型的路径不因此新增调用。

有效选择以`adrs-question-method-plan-v1`保存到原plan_manifest并参与原计划版本，绑定原stage_compilation ID及问题／冻结合同。只允许实际目录中的阶段和ID；冲突阶段、非法或缺失选择独立回退原包，不派修复模型，也不阻塞有效研究计划。未给某阶段决定就保留原方法；明确空ID只停止该阶段自动方法指导，不删除手动选择。重规划可同次调整，原发现扩展继承该清单，旧无选择的检查点沿原包。

三个阶段的模型提示、hint和请求收据消费同一投影：手动方法保留全部已冻结阶段内容／引用，自动未选方法保留原constraints，其他方法／阶段提示、hint和overview不重复装入。相同shared section引用继续有效，只保留实际需要的shared内容；hint只从同ID／版本／身份的冻结引用中归属且必须已在原包，无法可靠归属或解析时回退完整原包。原注册表、冻结stage_compilation、权限交集、required_tools、dispatch_tools及用户禁用约束均不改，不加载新文件、路径或方法版本；绘图手选及工具阶段保持原行为。

收据的content_scope区分selected_method、frozen_constraints_only及fallback_frozen_method，既有方法usage投影保留这些已知范围；混有旧未记录范围时明确legacy_content_scope_unknown，不能把仅约束送达说成完整方法执行或遵循。选择理由在原计划清单／trace中，选择不批准科学内容、来源或完成状态。

最小待运行目标：同次Planner可缩三个阶段自动方法且无额外选择请求；手选内容／引用、所有原constraints和服务端授权保留；未知ID、重复阶段、目录超容量／未发送或响应不完整均回退相应原包；非冲突阶段不被牵连；共享引用／hint归属与收据实际提示一致；任务或冻结编译改变不使用旧选择；固定RAG路径不新增Planner调用。仅源码／调用链审阅，无模型、测试或实际Token／费用数据。固定路径借后续既有分析响应择法、阶段内更细按需加载、工具／绘图及实际选择质量继续原4.5，整项未验收。

源码对照发现，随附academic-pipeline、deep-research、agent-crosscheck、paper-audit、grilling和systematic-literature-review的Stage:reflection含同一逐项核对指令，通用Constraints也重复。原stage profiles已经只发送一次agent_hints，但多个方法同时选中时，各自章节仍重复序列化；本次没有读取或改写账号个人方法，也不据随附内容推断某次真实任务已经选择全部六项。

新编译格式`adrs-stage-skills-v2-shared-sections`只在同一阶段共享章节名及文字完全相同的内容：shared_sections保存文字，各Skill的sections保留shared_section_id及所属身份／版本。模型包说明引用仍适用于各自Skill，不合并语义相近但不同的研究方法。只有序列化字节更少时采用共享表示，短文反而变大则保留内联；相同hint去重，试装与最终包使用相同表示计算资源占用。原阶段／学科／模板筛选、手选优先、权限交集、required_tools、引用加载、冲突及真实收据继续按各Skill维护。额外空间可能容纳原有自动候选，实际请求仍受原上下文和根预算约束，不能据此承诺固定Token降幅。

旧冻结`adrs-stage-skills-v1`可由原stage_profile读取，旧任务不重编；新包继续由原请求冻结、图执行、research_method_context及方法usage投影消费，无新选择模型、注册库或缓存服务。准备度Reflection将原READINESS_PROMPT置于方法／hints之后，明确当前阶段判断继续取证／分析的价值；方法提供相关研究视角，最终实际报告仍独立核来源、读者和图文。显式研究要求与原权限保持；无准备度政策的旧入口保留原提示路径。

| 消费者 | 独有职责 | 本次处置 |
|---|---|---|
| Reflection | 根据问题、关键矛盾／缺口和新增信息价值决定是否再研究 | 保留同次判断，阶段职责最后明确；不让通用“逐项数字”变成默认重复整稿审核 |
| 最终事实审核 | 实际成稿主张、来源、条件和推断依据 | 保留；不能由研究准备度或方法选择替代 |
| 读者／图文审核 | 当前稿覆盖／实质阅读影响和实际图文内容 | 保留独有范围；相同事实复用及新视觉推断仍归原审核合同 |
| Skill编译／执行 | 提供阶段方法、版本、限制和真实使用记录 | 同文共享，仍逐项处理权限和归属；不增加独立评审 |

最小观察目标待授权：多个同文方法共享后仍各有来源／限制；不同条件不折叠；短文无需共享；手选冲突不因共享而消失；v1旧冻结可读取；准备度不会因默认方法重复要求自动新增逐句审核。仅源码／调用链审阅，未运行编译、模型、数据库、测试或真实研究，用户方法组合、模型理解及实际费用仍待原4.4—4.5／Q3接受。

## 实际操作

前序45次原接口导入均成功。已回读 OpenAlex 的方法、阶段和来源，写作／绘图筛选正常。临时同源窗口选择 OpenAlex、多库论文检索和科研绘图，采用图文简报并手选科研绘图后，原确定性计划预览返回“Can start”。未点击开始研究。

默认分发另以当前新增行为的单一用例连接既有PostgreSQL：先观察新账号返回0项的失败断言，实施后同一用例通过，覆盖首次／并发获取45项、个人调整与删除保留、不同账号独立内容。未运行既有回归或构建／探针，未构建Docker镜像。现有本机API进程本轮未重启；该行为在加载新代码的服务进程中生效。详见[默认分发交付](acceptance/default-methods-20261026.md)。

详细过程和界面见[实际导入记录](acceptance/bookshelf-20261026.md)。
