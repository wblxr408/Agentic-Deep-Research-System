# 必要源码路径与尚未完成范围（2026-10-24）

本页回答原全部ORG／OPT-01—18／FLOW是否还有明确未接入的必要源码前置条件。依据是模块输入、实际主应用消费者和保存／读取路径的人工源码审阅，不是运行验收、测试结果或逐行无缺陷保证。审阅没有执行单元／回归／冒烟、构建／类型／lint／schema、导入／启动／文件／hash／文字探针或改名诊断；没有提前取证、模型请求、付费根、部署或新观察器。

本轮确认并修复了两处主链缺口，而非只整理既有规划：

| 普通推送提交 | 实际源码改动 | 仍未证明 |
| --- | --- | --- |
| `7f73aff1fecfa136a559d69b54d458e70a41cec4` | Analyst深读不再按局部种子字节上限删除指定成果；署名原证明留根，问题种子保留／遗漏进入阶段context，新契约阻止旧阶段混用或尝试数清空 | 实际完整深读、跨段条件语义与成本 |
| `e75c9cd20d2302f6a498fc7c5c9bc1eda80f2460` | 公开原文归档operation绑定实际正文，当前访问快照核对owner／source_id／正文版本，可信RAG据此保留来源public；普通上传／新正文／未知旧归档不降级 | 完整U2／U4及撤权／到期实际效果 |

此前迁入、审核／修订载荷、凭据URL、批次恢复、深读到写作和重试根限额的提交继续保留，见[接续记录](acceptance/cloud-continuation-20261024.md)及Git历史。所有提交在`codex/adrs-todo-20261023`，含`[skip ci]`，未强推或向main推送。

## ORG的实际路径

| 条目 | 已接入的选定路径及消费者 | 未完成／未采用范围 |
| --- | --- | --- |
| ORG.1 对象与范围 | `app/research_scope.py:preview_organization_scope`处理单／多高校、实验室、企业、实体／隶属、成果家族；`app/organization_runtime.py`冻结请求并供根图取证／综合；`OrganizationResearchPanel`提供实际请求输入 | 混合对象的本轮完整自动交付待U1／U3，不以界面字段存在证明真实身份正确 |
| ORG.2 学科评价 | `app/research_evaluation.py:preview_evaluation`及目录／适配规则保留体系、版本与可用性，`organization_taxonomy.py`冻结分类并接成果与统计 | 授权JCR等数据没有真实输入时保持缺项；不自动获取商业目录，不从载体等级推出论文技术质量 |
| ORG.3 权重与匹配 | `research_matching.py`的硬筛选、分层权重、缺失区间和贡献；`research_matching_bridge.py:snapshot_from_research`只从本人保存来源／定位创建快照，既有API／权重编辑器接入 | 未有权取得的特征不补零，真实排序价值及用户判断待U3；不用学习排序替代当前有据分项 |
| ORG.4 主应用及历史 | 原请求／query preview、根快照、Report、`organization_report.py`及JSON／Markdown／HTML交付共用冻结配置，`ResearchDashboard`、重排／导出入口已接入 | 本轮页面、SQL、下载、重开及并发仍未执行；历史证据不扩充为本轮验收 |
| ORG.5 跨案例证据 | 对应消费者路径已具备，历史企业／独立对象／跨学科记录保留 | 本项主要欠缺新的完整业务证据，不是可由额外源码或新规划代替的任务；历史29/34不改写 |
| ORG.6及7.4—7.8 | `organization_findings.py`接关系／技术卡／趋势；`organization_actions.py:build_action_view`、`organization_statistics.py:build_statistics`经根Report消费，事实／推断／情景／行动与统计单位分开 | 关系真实含义、全文条件、反证、合作可行性与全量主张支持仍待完整旅程，复合7.4—7.8保持未勾选 |

## 18模块逐项对应

下表“已接入”只指本轮选定的必要实现和消费者；每个`.b`及原细分复合项继续未验收。候选的“不采用”不等于算法已经实现，也不意味着原完整目标已通过。

| 模块 | 源码输入→实际消费者 | 当前边界及欠缺 |
| --- | --- | --- |
| OPT-01 接入 | `api/documents.py`上传／文本接入、`DocumentBatchIntake`→原来源事务／`evidence_ingestion.py:reconcile_evidence_ledger`→运行快照和`IngestionPanel` | 显式有界文件批次、逐项恢复和完整配置绑定已接；不做服务端任意目录扫描、CDC／Webhook／定时消费者。真实部分失败／重放等待完整旅程 |
| OPT-02 解析 | `research_documents.py:read_document`→`document_structure.py`、`document_pdf.py`、`document_html.py`→上传与浏览原文／解析详情 | 原生、受限本机OCR、布局／单元格／图像指针和缺口已接；不自动运行视觉语义模型或把图像指针称为已识图。真实扫描件／OCR／布局仍待取证 |
| OPT-03 分块 | `evidence_chunks.py:build_chunk_plan`→来源版本、`source_chunk_metadata`、直接定位／RAG父级上下文及引用 | 固定／滑动／递归／结构和父子定位已接；无收益证据时不加语义边界模型。旧引用不因新切片覆盖，实际跨版本／长结构待旅程 |
| OPT-04 特征 | `retrieval_features.py:build_feature_plan`→上传／版本保存→词面、时间与可选dense查询profile | 词汇／字面实体、结构、已声明时间和固定编码profile已接；SPLADE、多向量、行为及图文编码未采用，未知BSR不虚构含义。实际编码／关闭／不兼容待旅程 |
| OPT-05 索引 | `db/retrieval_indexes.py:publish_source_index/apply_index_action/scoped_bm25`→原源／head事务与RAG；`SourceIndexPanel` | 版本化词项、direct、显式回滚及同版本完整性已接；不新建HNSW／IVF／PQ／DiskANN。真实重建／失效／回滚及范围统计待U2／U4 |
| OPT-06 生命周期 | `source_lifecycle.py`的策略、变更／发布／`current_access`→检索、上下文扩展及`current_synthesis_state`；`SourceLifecyclePanel` | 原文不可变、当前版本／有效期、显式墓碑／清理和公开归档正文绑定已接；无后台purge／重训。撤销、并发及旧引用实际效果待U2／U4 |
| OPT-07 理解 | `query_understanding.py`解释／冻结→预览身份→创建与根配置；`QueryUnderstandingPanel` | 显式槽位、上下文归属、歧义和交付偏好已接；没有额外意图模型或Agent。真实编辑／澄清／预览过期待旅程 |
| OPT-08 规划 | `planning_control.py:compile_plan/condition_decision/iteration_decision`、`tool_handoff.py`→根DAG／实际工具／结果接纳 | 单根依赖、条件、并发、交接、渐进Skill和有界补证已接，根重试保留显式零；无新自治调度器。旧执行／重复／审批及恢复仍待U4 |
| OPT-09 路由 | `query_rewriting.py:search_route`→外网真实查询；`model_routing.py`→阶段主备／有界能力升级与`BudgetedClient` | 原词、明确别称、份额、能力与资料交集已接；不加独立改写／路由模型。实际主备、拒绝、费用及升级边界待旅程 |
| OPT-10 过滤 | `retrieval_filters.py:compile_filter`→RAG各通道、选择器、统计及最终复核 | 业务OR与可信owner／范围AND预过滤已接，缺失／短缺如实返回；不做未授权补量、自适应ANN或Bitmap新服务。真实过滤与撤权待U2／U4 |
| OPT-11 召回 | `retrieval_candidates.py:literal_candidates`、`RAGAgent`的BM25／FTS／可选dense与结构通道→融合／重排／当前范围复核 | 真实可用通道与不可用原因已接；字面entity不是消歧，结构边不是科研合作。未选GraphRAG社区摘要、多向量或行为通道；实际内容质量待U2／U3 |
| OPT-12 外网 | Search／Browser、原受控HTTP／DOM／文档worker→`external_evidence.py`新鲜度／同任务复用→根账本与显式归档API | 跳转、来源范围、时间、原文版本和有限资源已接；不登录外部平台、不复制本地会话。实际联网／原文／资源／缓存待U1—U4 |
| OPT-13 融合 | `candidate_fusion.py:fuse_candidates`→Search／RAG返回顺序及候选依据→现有精排 | RRF、Borda、分数归一化、词面近重复／多样性和份额已接；不把镜像当独立证据，不训练LTR。贡献与支持、实际质量／成本待旅程 |
| OPT-14 上下文 | `evidence_selection.py`、`research_context.py`→分阶段Analyst／Report，`reading_source_spans`承接技术卡原文定位 | 当前问题／来源／条件窗口、完整记录、原引用与遗漏已接，本轮修复指定深读对象丢失；相关性、选段和语义支持仍区分。跨段条件完整性待U1／U3 |
| OPT-15 交付 | `report_planning.py`→Report／`claim_verification.py`／`report_revision.py`→`research_delivery.py`／`research_figures.py`／报告历史、模板及导出组件 | 全部主张、一轮修订、主文／附录、声明式页／图和文本历史已接；未支持稿暂停。未提供任意语义画布／PPTX原生适配，图表PDF不冒充整份原生PDF；真实图文和阅读仍未通过 |
| OPT-16 治理 | `data_governance.py`及当前来源快照→实际模型／网络／MCP，`disclosure.py`→完整发布、SSE／日志／历史／导出 | owner保存权限与公开来源分开，凭据／高类别只能收紧；启用内部检索的冻结initial_class仍至少internal，来源public不降根限制。未加SSO／KMS或宣称完整语义DLP，安全效果待U2／U4 |
| OPT-17 反馈 | `research_quality.py`→本人quality／compare入口，`db/research_quality.py:save_feedback`→`ResearchQuality` | 真实候选标签、显式反馈、绑定／幂等、独立算术及已存任务比较已接；无完整标注时指标未知，无自动A/B、训练或代填人类评价。真实用户反馈待交付后取得 |
| OPT-18 运行 | `llm_budget.py`、`runtime_accounting.py`、`execution_control.py`及DB事务→根派发、取消、恢复、收据、Harness镜像和工作区 | 原根预算／期限、未知费用、迟到收据、受限绘图复用、失败保存及重试上限已接；无新观察器／队列／后台实验，未宣称实测SLA。真实竞态、取消和全账本待U4 |

## FLOW与完整交付还欠什么

| 原范围 | 必要源码路径／本轮结论 | 当前未完成的实际结果 |
| --- | --- | --- |
| FLOW.1 | 原tool_handoff、根结果绑定和幂等接纳已接入 | 异常路径仍受FLOW.5完整范围约束 |
| FLOW.3 | 全部主张及任务方法／来源事实、局部多锚点、完整输出后发布及唯一修订轮已接入 | 新实质报告的全量科学支持仍未通过，不降低必核或把位置有效当语义正确 |
| FLOW.4 | 模型／工具统一准入结算、审核剩余预留、绘图衔接和原根重试上限已接入 | 240000等历史上限与费用保留；实际端到端成本、未知收据和原期限需再取证，不再简单加预算 |
| FLOW.5 | owner／execution／plan、访问当前性、取消／恢复及事务边界已接入 | 双主体、撤权、迟到、重复、未知回执和回滚仍待完整U4，禁止拆成接口探针 |
| FLOW.10及10.4b2 | 前置身份分批、逐问题深读、缺字段有界补读、原文到写作、种子／上下文绑定和阶段持久化已接入 | 指定成果没有丢失不等于完整条件已读；真实中断／恢复／跨段条件与研究深度仍待U1／U3／U4 |
| FLOW.11及11.2c2 | 预设／自定义页、主文／附录、数据比较图、默认／逐图注册Skill及固定受信渲染已接入 | 所选Skill必须实际在云端注册且引用内容可用；不能声称本机个人Skill已迁入或执行。真实成图、视觉／交互／离线阅读待完整旅程 |
| FLOW.12 | 模型核对、作者自审、实际人类试读的记录路径不混同 | 新全自动报告及真实读者反馈都未取得，不能用人工整编或旧失败覆盖为通过 |
| FLOW.2／6／7／8／9 | 保留原日期的真实交付／形式／阻断修复记录 | 不将其历史勾选提升为当前新代码或其他ORG／OPT完整通过 |

原OpenSpec的`add-complete-research-delivery`4.5、5.5、6.5、7.3、9.3，`fix-research-token-budget`2.2、3.3、4.3、5.2、5.9，`add-bounded-research-planning`的统一旅程与3.3b、4.4、5.5、6.4、7.5、8.4、9.3，以及其余接入／解析／分块／特征／索引／生命周期／理解的最终2.1，仍按原范围未勾选。它们包含实际内容和边界结果，不能用源码审阅代替。

## 下一阶段的最小条件

本次按选定的最小实现路径，没有再确认一个需要为了等待配置而新增算法、Agent或框架的源码前置项；这不保证不存在将由真实旅程暴露的缺陷。后续新缺陷按实际结果修复并保留失败，不改写既有验收。

1. **真实模型配置**：安全配置provider、API base、model和实际凭据，资料类别许可与冻结任务限制相容；不从聊天／仓库提取先前本地秘密。当前用户仍要求暂留空，因此本轮不能实际跑模型。
2. **浏览器与真实外网能力**：先使已保存的下载出站设置实际生效，完成Chromium依赖安装，再作为整个业务旅程使用；旧403和草稿保存不是已下载／已发布／已就绪证明。实际论文来源仍经过原出站／范围／预算，不提前取证观察。
3. **真实隔离验收状态**：云端PostgreSQL／pgvector与Redis已有安装／集群初始化记录，但服务、业务库／应用DDL和两个实际测试主体尚未执行；将其作为完整旅程必要准备，不另做启动／SQL门禁。U4使用隔离主体／资源，不需迁入用户本机全库。
4. **U2真实原文**：按用户澄清，可在新完整旅程真实取得公开DistServe／dLoRA原文，再由当前owner显式归档→版本／发布→检索→引用→报告→导出。来源public与启用内部检索后任务initial_class至少internal分别记录；不造企业密件、不用生成文本替代论文、不冒称旧U2恢复。仅明文要求旧owner历史数据的个别项另列缺口。
5. **U1／U3图文与人类评价**：完整有据研究、指定对象／学科／权重／模板和实际所选Skill的可用版本，随后实际阅读、导出和重开；人类反馈只能在真实产物可读后取得。不能让模型或静态产物脚本代填。

上述条件未满足前，不建付费根观察进度，不把全部未勾选项泛化为“缺原私有数据库”，也不为占满工作量制造无依据优化。源端本地继续停写，当前任务分支仍由云端单一写入。没有合并／部署或环境草稿发布行为。
