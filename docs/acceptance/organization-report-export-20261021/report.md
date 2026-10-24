# DistServe 论文的发表日期、Peking University 署名、研究问题与方法

> Generated: 2026-10-21 | Research Depth: Comprehensive（有界单样本）

## Executive Summary
基于 USENIX 的 OSDI '24 DistServe 展示页这一项有界公开样本，可确证该论文发表于 **2024 年 7 月**（BibTeX `year=2024, month=jul`，页码 193–210），但**精确到日的发表日期未知** [citation:1]。8 位作者中 **5 位标注 Peking University**，属多机构合作成果 [citation:1]。论文针对 LLM 服务中 prefill 与 decoding 共置导致的干扰与资源耦合问题，提出将两阶段拆分到不同 GPU 并协同优化资源分配与并行策略的方法 [citation:1]。

## 1. Background and Context
本研究仅分析 USENIX 出版商页面（OSDI '24 的 DistServe 展示页）这一有界公开样本，不对 DistServe 的完整发表史、资助或部署情况外推 [citation:1]。范围限定为计算机学科、2024 年、主题 DistServe；页面出现机构名称本身不证明成果归属，抓取时间也不证明发表时间。

## 2. Key Findings

### 2.1 发表日期：年份与月份可确证，具体日期未知
页面 BibTeX 记录：标题为 “DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving”，收录于 18th USENIX Symposium on Operating Systems Design and Implementation (OSDI 24)，`year = 2024`、`month = jul`，页码 193–210，出版方 USENIX Association，会议地点 Santa Clara, CA [citation:1]。`citation_publication_date` 亦为 2024 [citation:1]。

因此可确证**发表年份 2024、月份 7 月**（置信度：年份 HIGH，月份 MEDIUM——仅来自 BibTeX month 字段）；**精确到日的发表日期未知**，页面未给出，不应臆造。会议技术议程页显示 OSDI '24 会期自 2024 年 7 月 10 日开始 [citation:2]，这可作为会议时间背景，但不等于该论文的单独发表日期。

### 2.2 Peking University 署名：8 位作者中 5 位标注
页面作者列表为：Yinmin Zhong、Shengyu Liu（Peking University）；Junda Chen（UC San Diego）；Jianbo Hu（Peking University）；Yibo Zhu（StepFun）；Xuanzhe Liu、Xin Jin（Peking University）；Hao Zhang（UC San Diego）[citation:1]。即 **8 位作者中 5 位标注 Peking University**（Zhong、Liu S.、Hu、Liu X.、Jin），Peking University 为第一署名单位之一 [citation:1]。该署名来自论文作者列表本身，而非个人简介或现任职信息（置信度：HIGH）。

### 2.3 研究问题
现有 LLM 服务系统将 prefill 与 decoding 两阶段共置，并对所有用户与请求统一批处理，导致强烈的 prefill-decoding 干扰，同时把两阶段的资源分配与并行策略耦合在一起 [citation:1]。而应用常分别强调每阶段延迟——prefill 的首 token 时间（TTFT）与 decoding 的每输出 token 时间（TPOT）；在严格延迟约束下，现有系统只能优先其一或过度配置算力 [citation:1]。

### 2.4 方法
DistServe 将 prefill 与 decoding 计算分配到不同 GPU，消除两阶段干扰；依据应用的 TTFT 与 TPOT 要求，为每个阶段协同优化资源分配与并行策略；并按服务集群带宽放置两阶段，以最小化 disaggregation 带来的通信开销 [citation:1]。

## 3. Data and Statistics

| 项目 | 内容 | 来源 | 置信度 |
|---|---|---|---|
| 发表年份 | 2024 | BibTeX `year` [citation:1] | HIGH |
| 发表月份 | 7 月 | BibTeX `month=jul` [citation:1] | MEDIUM |
| 精确日期 | 未知 | 页面未提供 [citation:1] | — |
| 页码 | 193–210 | BibTeX [citation:1] | HIGH |
| 作者数 / PKU 署名数 | 8 / 5 | 作者列表 [citation:1] | HIGH |
| 页面自述性能 | 7.4× 更多请求或 12.6× 更紧 SLO，>90% 请求满足延迟约束 | 摘要 [citation:1] | MEDIUM（作者自述，未独立复现） |

## 4. Expert Perspectives
本样本为出版商页面，未包含第三方专家评论或独立评测。页面自述的 7.4×/12.6× 指标系论文作者在摘要中的表述，非独立复现，应视为作者主张而非已验证结论 [citation:1]。页面显示的会议赞助方 KAUST 属会议赞助，**不构成论文资助证据** [citation:1]。

## 5. Conclusions and Recommendations
- **可确证**：DistServe 发表于 OSDI '24，年份 2024、月份 7 月，页码 193–210；8 位作者中 5 位标注 Peking University；研究问题与方法如上 [citation:1]。
- **明确未知（待核）**：精确发表日期、论文资助来源、正式合作协议、独立评价指标、作者当前任职、实际部署情况——本页面均无直接证据 [citation:1]。
- **建议**：后续核实会议日程中的具体报告日期、论文致谢中的资助信息，以及 7.4×/12.6× 指标的独立复现（置信度：建议性，需人工复核）。
- **不外推**：本结论仅限该单一有界样本，不代表 DistServe 完整发表史或 Peking University 全部成果。

## References
[citation:1] USENIX, "DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving," OSDI '24 presentation page. https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin
[citation:2] USENIX, "OSDI '24 Technical Sessions." https://www.usenix.org/conference/osdi24/technical-sessions

## 核验结果

自动来源支持：0/19 项；人工复核：未复核。模型置信度不代表人工确认。
支持状态来自模型语义判断与原文引语校验，不能保证结论为真。

- claim:1 [missing_citation] Generated: 2026-10-21 | Research Depth: Comprehensive（有界单样本） — Awaiting source support judgement
- claim:2 [not_checked] 基于 USENIX 的 OSDI '24 DistServe 展示页这一项有界公开样本，可确证该论文发表于 **2024 年 7 月**（BibTeX `year=2024, month=jul`，页码 193–210），但**精确到日的发表日期未知** [citation:1]。8 位作者中 **5 位标注 Peking University**，属多机构合作成果 [citation:1]。论文针对 LLM 服务中 prefill 与 decoding 共置导致的干扰与资源耦合问题，提出将两阶段拆分到不同 GPU 并协同优化资源分配与并行策略的方法 [citation:1]。 — Verification token/time budget exhausted
- claim:3 [not_checked] 本研究仅分析 USENIX 出版商页面（OSDI '24 的 DistServe 展示页）这一有界公开样本，不对 DistServe 的完整发表史、资助或部署情况外推 [citation:1]。范围限定为计算机学科、2024 年、主题 DistServe；页面出现机构名称本身不证明成果归属，抓取时间也不证明发表时间。 — Verification token/time budget exhausted
- claim:4 [not_checked] 页面 BibTeX 记录：标题为 “DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving”，收录于 18th USENIX Symposium on Operating Systems Design and Implementation (OSDI 24)，`year = 2024`、`month = jul`，页码 193–210，出版方 USENIX Association，会议地点 Santa Clara, CA [citation:1]。`citation_publication_date` 亦为 2024 [citation:1]。 — Verification token/time budget exhausted
- claim:5 [not_checked] 因此可确证**发表年份 2024、月份 7 月**（置信度：年份 HIGH，月份 MEDIUM——仅来自 BibTeX month 字段）；**精确到日的发表日期未知**，页面未给出，不应臆造。会议技术议程页显示 OSDI '24 会期自 2024 年 7 月 10 日开始 [citation:2]，这可作为会议时间背景，但不等于该论文的单独发表日期。 — Verification token/time budget exhausted
- claim:6 [not_checked] 页面作者列表为：Yinmin Zhong、Shengyu Liu（Peking University）；Junda Chen（UC San Diego）；Jianbo Hu（Peking University）；Yibo Zhu（StepFun）；Xuanzhe Liu、Xin Jin（Peking University）；Hao Zhang（UC San Diego）[citation:1]。即 **8 位作者中 5 位标注 Peking University**（Zhong、Liu S.、Hu、Liu X.、Jin），Peking University 为第一署名单位之一 [citation:1]。该署名来自论文作者列表本身，而非个人简介或现任职信息（置信度：HIGH）。 — Verification token/time budget exhausted
- claim:7 [not_checked] 现有 LLM 服务系统将 prefill 与 decoding 两阶段共置，并对所有用户与请求统一批处理，导致强烈的 prefill-decoding 干扰，同时把两阶段的资源分配与并行策略耦合在一起 [citation:1]。而应用常分别强调每阶段延迟——prefill 的首 token 时间（TTFT）与 decoding 的每输出 token 时间（TPOT）；在严格延迟约束下，现有系统只能优先其一或过度配置算力 [citation:1]。 — Verification token/time budget exhausted
- claim:8 [not_checked] DistServe 将 prefill 与 decoding 计算分配到不同 GPU，消除两阶段干扰；依据应用的 TTFT 与 TPOT 要求，为每个阶段协同优化资源分配与并行策略；并按服务集群带宽放置两阶段，以最小化 disaggregation 带来的通信开销 [citation:1]。 — Verification token/time budget exhausted
- claim:9 [not_checked] | 发表年份 | 2024 | BibTeX `year` [citation:1] | HIGH | — Verification token/time budget exhausted
- claim:10 [not_checked] | 发表月份 | 7 月 | BibTeX `month=jul` [citation:1] | MEDIUM | — Verification token/time budget exhausted
- claim:11 [not_checked] | 精确日期 | 未知 | 页面未提供 [citation:1] | — | — Verification token/time budget exhausted
- claim:12 [not_checked] | 页码 | 193–210 | BibTeX [citation:1] | HIGH | — Verification token/time budget exhausted
- claim:13 [not_checked] | 作者数 / PKU 署名数 | 8 / 5 | 作者列表 [citation:1] | HIGH | — Verification token/time budget exhausted
- claim:14 [not_checked] | 页面自述性能 | 7.4× 更多请求或 12.6× 更紧 SLO，>90% 请求满足延迟约束 | 摘要 [citation:1] | MEDIUM（作者自述，未独立复现） | — Verification token/time budget exhausted
- claim:15 [not_checked] 本样本为出版商页面，未包含第三方专家评论或独立评测。页面自述的 7.4×/12.6× 指标系论文作者在摘要中的表述，非独立复现，应视为作者主张而非已验证结论 [citation:1]。页面显示的会议赞助方 KAUST 属会议赞助，**不构成论文资助证据** [citation:1]。 — Verification token/time budget exhausted
- claim:16 [not_checked] **可确证**：DistServe 发表于 OSDI '24，年份 2024、月份 7 月，页码 193–210；8 位作者中 5 位标注 Peking University；研究问题与方法如上 [citation:1]。 — Verification token/time budget exhausted
- claim:17 [not_checked] **明确未知（待核）**：精确发表日期、论文资助来源、正式合作协议、独立评价指标、作者当前任职、实际部署情况——本页面均无直接证据 [citation:1]。 — Verification token/time budget exhausted
- claim:18 [missing_citation] **建议**：后续核实会议日程中的具体报告日期、论文致谢中的资助信息，以及 7.4×/12.6× 指标的独立复现（置信度：建议性，需人工复核）。 — Awaiting source support judgement
- claim:19 [missing_citation] **不外推**：本结论仅限该单一有界样本，不代表 DistServe 完整发表史或 Peking University 全部成果。 — Awaiting source support judgement

## 研究对象、口径与冻结配置
主题：DistServe；学科：computer science；时间：2024-01-01 至 2024-12-31。
对象类型：university；请求冻结时间：2026-10-21T04:30:23.437044+00:00。实际采集时间逐来源保留。
范围规则：adrs-organization-scope-v2；配置版本：report-export-e2e-v1；权重规则：adrs-weight-rules-v1；预设版本：adrs-presets-v1。
分别保留发表记录与研究家族；同成果可归属多个对象，汇总取并集，未关联版本按独立发表计数。
偏好配置不等于已完成评分；结果页只读重排不改写本报告的配置、事实或证据。
### 对象与来源
- Peking University（university；pending）：<https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin>
### 原始与生效权重
| 维度 | 原始权重 | 开启 | 生效权重 |
| --- | ---: | --- | ---: |
| 主题相关性 | 6.0 | 是 | 60.00% |
| 证据完整度 | 4.0 | 是 | 40.00% |
| 时效性 | 0.0 | 是 | 0.00% |
| 研究路线契合 | 0.0 | 是 | 0.00% |
| 成果表现 | 0.0 | 是 | 0.00% |
| 合作互补性 | 0.0 | 是 | 0.00% |
### 成果表现组内权重
| 项目 | 原始权重 | 开启 | 组内生效权重 |
| --- | ---: | --- | ---: |
| venue | 1.0 | 是 | 0.00% |
| paper | 1.0 | 是 | 0.00% |
### 指标组内权重
| 项目 | 原始权重 | 开启 | 组内生效权重 |
| --- | ---: | --- | ---: |
| 未显式配置 | — | — | — |
### 有序偏好映射（产品偏好，非官方等价）
- ccf／adrs-preference-map-v1：A=1.0；B=0.6666666666666667；C=0.33333333333333337
- icore／adrs-preference-map-v1：A*=1.0；A=0.75；B=0.5；C=0.25
- abdc／adrs-preference-map-v1：A*=1.0；A=0.75；B=0.5；C=0.25
- ajg／adrs-preference-map-v1：4*=1.0；4=0.8；3=0.6；2=0.4；1=0.19999999999999996
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
- ev-66854e32：DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving \| USENIX；<https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin>；采集 2026-10-21T04:30:54.155918。
- ev-b317edea：OSDI '24 Technical Sessions \| USENIX；<https://www.usenix.org/conference/osdi24/technical-sessions>；采集 2026-10-21T04:30:52.502654。
### 缺失与解释边界
- 证据索引不等于机构成果全集或已核实合作关系。
- 仅覆盖本次取得的样本；空样本不代表现实中零成果，来源未覆盖年份不补零。
- 学科比较组使用请求标签，尚未逐篇核定学科；不输出跨学科或载体的统一质量榜。
- 原文位置与引用检查不等于独立语义复核；模型推断、建议和未来情景仍须复核。
- 评价目录为冻结的部分样本及授权要求，未自动应用到本次成果；缺失指标不作零分或最低等级。
- coauthorship 关系尚无已纳入的直接依据；不表示该关系不存在。
- funding 关系尚无已纳入的直接依据；不表示该关系不存在。
- citation 关系尚无已纳入的直接依据；不表示该关系不存在。


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
待核记录 0 项；未确立的关系：coauthorship、funding、citation。未取得证据不表示关系不存在。
机构署名按所选名称／别名与发表来源对照；不推出当前任职、正式协议、内部研发投入或科研质量优劣。跨载体／年份不汇成统一质量榜。
### 后续评估建议（模型判断，待复核）
- 建议后续核实精确发表日期（会议日程中的具体报告日期）、论文致谢中的资助信息，以及 7.4×/12.6× 指标的独立复现；这些在本页面均无直接证据。 [citation:1] [citation:1]
