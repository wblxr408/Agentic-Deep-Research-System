# Peking University 公开系统研究：DistServe（OSDI '24）单样本分析

> 按本次所选研究模块组织；来源摘述和分析仍需阅读审核状态。

## 研究全景

**来源摘述（待审核）**：本次研究仅覆盖一个发表样本：DistServe: Disaggregating Prefill and Decoding for Goodput\-optimized Large Language Model Serving，收录于 18th USENIX Symposium on Operating Systems Design and Implementation（OSDI 24），页码 193–210，2024 年 7 月于 Santa Clara, CA 发表，作者列表含 Peking University 署名。 [citation:1]

**来源摘述（待审核）**：该样本公开的研究方向限于 LLM 服务系统（LLM serving），核心思路是将 prefill 与 decoding 两个阶段解耦，以在时延约束下优化 goodput。按研究契约，样本数为 1，不能把这篇论文解释为 Peking University 系统研究的投入或产出总量，也不构成机构层面的统计。 [citation:1]

**证据缺口**：机构层面的系统研究布局、其他论文样本与投入规模均未取得材料，保留未知。 

## 研究演进

**来源摘述（待审核）**：当前只有一个年度观测（2024）。arXiv 预印本日期为 2024/01/18，OSDI '24 正式发表月份为 2024 年 7 月，二者属同一工作的版本关系，不构成跨年变化。 [citation:12] [citation:1]

**证据缺口**：由于只有一个年度样本，无法确立多年演进趋势；任何跨年度的方向变化或产出变化均缺证，不能以版本先后推断研究演进。 

## 关系分析

**来源摘述（待审核）**：署名与共著：作者为 Yinmin Zhong、Shengyu Liu（Peking University）、Junda Chen（UC San Diego）、Jianbo Hu（Peking University）、Yibo Zhu（StepFun）、Xuanzhe Liu、Xin Jin（Peking University）、Hao Zhang（UC San Diego）。这是论文署名事实，不等于正式机构协议、合作备忘录或产品部署。 [citation:1]

**来源摘述（待审核）**：资助：页面仅显示 OSDI '24 Open Access 由 King Abdullah University of Science and Technology（KAUST）赞助，这是会议层面的开放获取赞助，并非论文研究资助；论文本身的资助来源未知。 [citation:1]

**证据缺口**：正式协议、项目合作、产品部署与可联系性均无证据，保留未知；共著关系不能外推为机构间正式合作安排。 

## 成果深读

**来源摘述（待审核）**：DistServe 将 prefill 与 decoding 计算分配到不同 GPU，消除两阶段相互干扰；在给定 TTFT（首 token 时延）与 TPOT（每输出 token 时延）约束下联合优化资源分配与并行策略，并按集群带宽放置两阶段以减少解耦带来的通信开销。 [citation:1]

**来源摘述（待审核）**：评估摘要称，在多种主流 LLM、应用与延迟要求下，DistServe 相比当时最先进系统可服务 7\.4 倍更多请求，或在同等请求量下支持 12\.6 倍更紧的 SLO，同时使超过 90% 的请求满足时延约束。 [citation:1]

**证据缺口**：论文全文未取得，具体方法细节、实验硬件与负载条件、图表数据无法核清，相关结论保留缺口，不据摘要外推。 

## 交叉验证

**来源摘述（待审核）**：支持性材料：USENIX 会议页面与 arXiv 页面在论文标题上一致，可相互印证该工作的存在与题目。 [citation:1] [citation:12]

**来源摘述（待审核）**：未发现实质冲突；arXiv 日期（2024\-01\-18）早于会议发表月份（2024\-07），属预印本与正式版的版本差异，而非矛盾。 [citation:12] [citation:1]

**证据缺口**：未取得论文全文、资助声明、代码仓库与部署证据；检索中出现的无关新闻站点条目不采用，也不作为任何结论依据。相关线索不能当作部署证明。 

## 后续行动

**分析判断（待复核）**：研究验证问题：一是获取论文全文，核清方法细节、实验条件与图表数据；二是核实论文的资助与项目来源；三是若需判断 Peking University 系统研究的机构布局，需补充同机构其他系统方向论文样本，当前仅 1 篇，不能外推。 [citation:1]

**证据缺口**：合作目的方面缺少明确需求与条件，不擅自联系任何作者或机构；如需推进，应先补齐合作目标、范围与授权条件。 


## 核验结果

自动来源支持：9/17 项；人工复核：未复核。模型置信度不代表人工确认。
支持状态来自模型语义判断与原文引语校验，不能保证结论为真。

- claim:1 [missing_citation] 按本次所选研究模块组织；来源摘述和分析仍需阅读审核状态。 — Awaiting source support judgement
- claim:4 [missing_citation] **证据缺口**：机构层面的系统研究布局、其他论文样本与投入规模均未取得材料，保留未知。 — Awaiting source support judgement
- claim:6 [missing_citation] **证据缺口**：由于只有一个年度样本，无法确立多年演进趋势；任何跨年度的方向变化或产出变化均缺证，不能以版本先后推断研究演进。 — Awaiting source support judgement
- claim:9 [missing_citation] **证据缺口**：正式协议、项目合作、产品部署与可联系性均无证据，保留未知；共著关系不能外推为机构间正式合作安排。 — Awaiting source support judgement
- claim:12 [missing_citation] **证据缺口**：论文全文未取得，具体方法细节、实验硬件与负载条件、图表数据无法核清，相关结论保留缺口，不据摘要外推。 — Awaiting source support judgement
- claim:15 [missing_citation] **证据缺口**：未取得论文全文、资助声明、代码仓库与部署证据；检索中出现的无关新闻站点条目不采用，也不作为任何结论依据。相关线索不能当作部署证明。 — Awaiting source support judgement
- claim:16 [unsupported] **分析判断（待复核）**：研究验证问题：一是获取论文全文，核清方法细节、实验条件与图表数据；二是核实论文的资助与项目来源；三是若需判断 Peking University 系统研究的机构布局，需补充同机构其他系统方向论文样本，当前仅 1 篇，不能外推。 [citation:1] — The claim is a set of proposed verification tasks and a caution about not extrapolating from a single paper. The excerpts show only one DistServe paper and its affiliations (Peking University among others), but they do not establish that only 1 paper exists, nor address funding/project sources or full-text details. The methodological caution is not entailed by the supplied passages.
- claim:17 [missing_citation] **证据缺口**：合作目的方面缺少明确需求与条件，不擅自联系任何作者或机构；如需推进，应先补齐合作目标、范围与授权条件。 — Awaiting source support judgement

---

## References

[1] **DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving | USENIX** - https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin
[2] **USA TODAY - Breaking News and Latest News Today** - https://www.usatoday.com/
[3] **USA TODAY: Latest World and US News - USATODAY.com** - https://www.usatoday.com/network/
[4] **Crossword Puzzles | USA TODAY** - https://puzzles.usatoday.com/
[5] **Sports News, Scores, Predictions and Analysis - USA TODAY** - https://www.usatoday.com/sports/
[6] **U.S. and National News - USA TODAY** - https://www.usatoday.com/news/nation/
[7] **The Latest US and World News - USATODAY.com** - https://www.usatoday.com/news/mobile/
[8] **Free Online Games | USA TODAY** - https://games.usatoday.com/all-games
[9] **Help Center - USA TODAY** - https://help.usatoday.com/subscription-services
[10] **USA Today** - https://www.usa-today.org/
[11] **Play Mahjongg Solitaire | USA TODAY** - https://games.usatoday.com/games/mahjongg-solitaire
[12] **[2401.09670] DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving** - https://arxiv.org/abs/2401.09670

## 研究对象、口径与冻结配置
主题：基于 https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin 研究 Peking University 的公开系统研究。只覆盖这篇 DistServe 发表样本；按选择的研究目的和模块交付。只有一个年度观测时明确不能确立多年趋势。署名或共著不等于正式协议、产品部署或可联系性；缺证保留未知，不把机构成果量当作内部研发投入。；学科：computer science；时间：2024-01-01 至 2024-12-31。
对象类型：university；请求冻结时间：2026-10-21T05:35:08.808397+00:00。实际采集时间逐来源保留。
范围规则：adrs-organization-scope-v2；配置版本：user-config-v1；权重规则：adrs-weight-rules-v1；预设版本：adrs-presets-v1。
分别保留发表记录与研究家族；同成果可归属多个对象，汇总取并集，未关联版本按独立发表计数。
偏好配置不等于已完成评分；结果页只读重排不改写本报告的配置、事实或证据。
研究目的：综合研究；研究模块：研究全景、研究演进、关系分析、成果深读、交叉验证、后续行动；模块规则：adrs-analysis-modules-v1。目的、模块与权重分别保存。
### 对象与来源
- Peking University（university；pending）：<https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin>
### 原始与生效权重
| 维度 | 原始权重 | 开启 | 生效权重 |
| --- | ---: | --- | ---: |
| 主题相关性 | 30.0 | 是 | 30.00% |
| 研究路线契合 | 15.0 | 是 | 15.00% |
| 成果表现 | 15.0 | 是 | 15.00% |
| 证据完整度 | 15.0 | 是 | 15.00% |
| 时效性 | 10.0 | 是 | 10.00% |
| 合作互补性 | 15.0 | 是 | 15.00% |
### 成果表现组内权重
| 项目 | 原始权重 | 开启 | 组内生效权重 |
| --- | ---: | --- | ---: |
| venue | 1.0 | 是 | 50.00% |
| paper | 1.0 | 是 | 50.00% |
### 指标组内权重
| 项目 | 原始权重 | 开启 | 组内生效权重 |
| --- | ---: | --- | ---: |
| 未显式配置 | — | — | — |
### 有序偏好映射（产品偏好，非官方等价）
- ccf／adrs-preference-map-v1：A=1.0；B=0.6666666666666667；C=0.33333333333333337
- icore／adrs-preference-map-v1：A*=1.0；A=0.75；B=0.5；C=0.25
- abdc／adrs-preference-map-v1：A*=1.0；A=0.75；B=0.5；C=0.25
- ajg／adrs-preference-map-v1：1=0.19999999999999996；2=0.4；3=0.6；4=0.8；4*=1.0
- jcr_quartile／adrs-preference-map-v1：Q1=1.0；Q2=0.75；Q3=0.5；Q4=0.25
- cas_partition／adrs-preference-map-v1：1=1.0；2=0.75；3=0.5；4=0.25
### 评价口径及可用性
目录版本：adrs-evaluation-catalog-v1；适配规则：adrs-evaluation-adapters-v1。目录样本不代表本次成果已核定评价。
- ccf：部分公开样本；<https://www.ccf.org.cn/Academic_Evaluation/By_category/>；尚未核定本次成果。
- icore：部分公开样本；<https://portal.core.edu.au/conf-ranks/>；尚未核定本次成果。
- wos_scie：需授权导入／尚无公开样本；<https://mjl.clarivate.com/>；尚未核定本次成果。
- wos_ssci：需授权导入／尚无公开样本；<https://mjl.clarivate.com/>；尚未核定本次成果。
- wos_ahci：需授权导入／尚无公开样本；<https://mjl.clarivate.com/>；尚未核定本次成果。
- wos_esci：需授权导入／尚无公开样本；<https://mjl.clarivate.com/>；尚未核定本次成果。
- scopus：需授权导入／尚无公开样本；<https://www.scopus.com/sources>；尚未核定本次成果。
- jcr_jif：需授权导入／尚无公开样本；<https://jcr.clarivate.com/>；尚未核定本次成果。
- jcr_quartile：需授权导入／尚无公开样本；<https://jcr.clarivate.com/>；尚未核定本次成果。
- jcr_jci：需授权导入／尚无公开样本；<https://jcr.clarivate.com/>；尚未核定本次成果。
- cas_partition：需授权导入／尚无公开样本；<https://www.fenqubiao.com/>；尚未核定本次成果。
- citescore：需授权导入／尚无公开样本；<https://www.scopus.com/sources>；尚未核定本次成果。
- citescore_percentile：需授权导入／尚无公开样本；<https://www.scopus.com/sources>；尚未核定本次成果。
- sjr：需授权导入／尚无公开样本；<https://www.scimagojr.com/>；尚未核定本次成果。
- snip：需授权导入／尚无公开样本；<https://www.scopus.com/sources>；尚未核定本次成果。
- abdc：部分公开样本；<https://abdc.edu.au/abdc-journal-quality-list/>；尚未核定本次成果。
- ajg：需授权导入／尚无公开样本；<https://charteredabs.org/academic-journal-guide>；尚未核定本次成果。
- citation_percentile：部分公开样本；<https://help.openalex.org/data/works/citations/>；尚未核定本次成果。
- cnci：需授权导入／尚无公开样本；<https://incites.help.clarivate.com/Content/Indicators-Handbook/ih-normalized-citation-impact.htm>；尚未核定本次成果。
- fwci：部分公开样本；<https://help.openalex.org/data/works/citations/>；尚未核定本次成果。
- ccf／2012／指标年 2012：public，partial；<https://risame.github.io/sun/ccf.pdf>
- ccf／2022／指标年 2022：public，partial；<https://scdm-shu.github.io/ccf/2022-CCF-Ranking.pdf>
- icore／CORE2023／指标年 2023：public，partial；<https://portal.core.edu.au/conf-ranks/?search=SIGCOMM&by=all&source=CORE2023&sort=atitle&page=1>
- icore／ICORE2026／指标年 2026：public，partial；<https://portal.core.edu.au/conf-ranks/?search=SIGCOMM&by=all&source=ICORE2026&sort=atitle&page=1>
- abdc／2010／指标年 2010：public，partial；<https://abdc.edu.au/wp-content/uploads/2026/09/ABDC-JQL-2025-v3-210926.xlsx>
- abdc／2013／指标年 2013：public，partial；<https://abdc.edu.au/wp-content/uploads/2026/09/ABDC-JQL-2025-v3-210926.xlsx>
- abdc／2016／指标年 2016：public，partial；<https://abdc.edu.au/wp-content/uploads/2026/09/ABDC-JQL-2025-v3-210926.xlsx>
- abdc／2019／指标年 2019：public，partial；<https://abdc.edu.au/wp-content/uploads/2026/09/ABDC-JQL-2025-v3-210926.xlsx>
- abdc／2022／指标年 2022：public，partial；<https://abdc.edu.au/wp-content/uploads/2026/09/ABDC-JQL-2025-v3-210926.xlsx>
- abdc／2025／指标年 2025：public，partial；<https://abdc.edu.au/wp-content/uploads/2026/09/ABDC-JQL-2025-v3-210926.xlsx>
- fwci／OpenAlex snapshot 2026-10-19／指标年 2026：public，partial；<https://api.openalex.org/works/W1951724000>
- citation_percentile／OpenAlex snapshot 2026-10-19／指标年 2026：public，partial；<https://api.openalex.org/works/W1951724000>
### 实际取证来源
- ev-c2800eb8：DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving \| USENIX；<https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin>；采集 2026-10-21T05:35:37.444253。
- ev-2d23ce6e：USA TODAY - Breaking News and Latest News Today；<https://www.usatoday.com/>；采集 2026-10-21T05:35:17.677195+00:00。
- ev-20dc30fd：USA TODAY: Latest World and US News - USATODAY.com；<https://www.usatoday.com/network/>；采集 2026-10-21T05:35:17.677195+00:00。
- ev-50d45c7e：Crossword Puzzles \| USA TODAY；<https://puzzles.usatoday.com/>；采集 2026-10-21T05:35:17.677195+00:00。
- ev-bce0c116：Sports News, Scores, Predictions and Analysis - USA TODAY；<https://www.usatoday.com/sports/>；采集 2026-10-21T05:35:17.677195+00:00。
- ev-dd8920ec：U.S. and National News - USA TODAY；<https://www.usatoday.com/news/nation/>；采集 2026-10-21T05:35:17.677195+00:00。
- ev-0d2e65ed：The Latest US and World News - USATODAY.com；<https://www.usatoday.com/news/mobile/>；采集 2026-10-21T05:35:17.677195+00:00。
- ev-60c094ab：Free Online Games \| USA TODAY；<https://games.usatoday.com/all-games>；采集 2026-10-21T05:35:17.677195+00:00。
- ev-8e12f8a9：Help Center - USA TODAY；<https://help.usatoday.com/subscription-services>；采集 2026-10-21T05:35:17.677195+00:00。
- ev-b9f536cd：USA Today；<https://www.usa-today.org/>；采集 2026-10-21T05:35:17.677195+00:00。
- ev-d1650eee：Play Mahjongg Solitaire \| USA TODAY；<https://games.usatoday.com/games/mahjongg-solitaire>；采集 2026-10-21T05:35:17.677195+00:00。
- ev-70d7c527：\[2401.09670\] DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving；<https://arxiv.org/abs/2401.09670>；采集 2026-10-21T05:35:59.229993。
### 缺失与解释边界
- 证据索引不等于机构成果全集或已核实合作关系。
- 仅覆盖本次取得的样本；空样本不代表现实中零成果，来源未覆盖年份不补零。
- 学科比较组使用请求标签，尚未逐篇核定学科；不输出跨学科或载体的统一质量榜。
- 原文位置与引用检查不等于独立语义复核；模型推断、建议和未来情景仍须复核。
- 评价目录为冻结的部分样本及授权要求，未自动应用到本次成果；缺失指标不作零分或最低等级。
- coauthorship 关系尚无已纳入的直接依据；不表示该关系不存在。
- funding 关系尚无已纳入的直接依据；不表示该关系不存在。
- citation 关系尚无已纳入的直接依据；不表示该关系不存在。
- 待核 research_families：1 validation error for FamilyClaim output_ids   Tuple should have at least 2 items after validation, not 1 \[type=too_short, input_value=\['out-distserve-osdi24'\], input_type=list\]     For further information visit https://errors.pydantic.dev/2.10/v/too_short


## 可复核样本与对象比较
计数由结构化记录计算，仅覆盖本次取得并通过原文校验的样本；未链接版本暂按单条发表独立计数。
| 对象 | 发表记录 | 研究家族 |
| --- | ---: | ---: |
| Peking University | 1 | 1 |
| 去重汇总 | 1 | 1 |
相同成果可分别归属多个对象，合并总量取成果／家族并集，不相加各对象行。
### 同口径样本比较
2024／conference_paper；学科口径来自请求：computer science。仅比较该组已取得样本，不作科研质量排序。
| 对象 | 本组研究家族数 |
| --- | ---: |
| Peking University | 1 |
### 已纳入成果与依据
- DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving；日期区间 2024-07-01 至 2024-07-31（month 精度）；[citation:1]
### 缺口与解释边界
待核记录 1 项；未确立的关系：coauthorship、funding、citation。未取得证据不表示关系不存在。
机构署名按所选名称／别名与发表来源对照；不推出当前任职、正式协议、内部研发投入或科研质量优劣。跨载体／年份不汇成统一质量榜。
- 待核：research_families：1 validation error for FamilyClaim output_ids   Tuple should have at least 2 items after validation, not 1 [type=too_short, input_value=['out-distserve-osdi24'], input_type=list]     For further information visit https://errors.pydantic.dev/2.10/v/too_short
### 后续评估建议（模型判断，待复核）
- 后续应获取论文全文与资助声明，以核清方法、实验条件及资助来源；当前仅有摘要级信息。 [citation:1]
