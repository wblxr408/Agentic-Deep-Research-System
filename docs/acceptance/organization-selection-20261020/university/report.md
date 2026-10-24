# 只以 DistServe 出版商页面核实北京大学署名与研究主题

> Generated: 2026-10-20 | Research Depth: Comprehensive（受限于单一来源，实际为单页核实）

## Executive Summary
仅依据 USENIX 的 DistServe 论文页面，可高置信度确认：该文发表于 **OSDI '24（2024 年 7 月）**，8 位作者中 **5 位标注 Peking University**，含第一作者 Yinmin Zhong；研究主题为**大语言模型服务系统的 prefill/decoding 分离与 goodput 优化** [citation:1]。但该页面只提供“作者署名单位”层面的证据，**不构成**机构隶属、资助或合作协议证据，且日期仅精确到月、样本仅 1 篇 [citation:1]。

## 1. Background and Context
本研究契约限定：仅以 DistServe 的出版商（USENIX）页面为来源，核实北京大学在该成果中的署名与研究主题，并说明来源样本与缺口；学科限定 computer_science，时间窗 2024-01-01 至 2024-12-31 [citation:1]。USENIX 为总部位于美国的非营利专业协会，主办 OSDI 等系统领域会议 [citation:2][citation:5]。需强调：页面出现机构名称只证明作者署名标注，不证明机构层面归属或正式合作。

## 2. Key Findings

### 2.1 成果识别（高置信度）
页面 BibTeX 与 citation_* 元数据一致给出：标题《DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving》，收录于 18th USENIX Symposium on Operating Systems Design and Implementation (OSDI 24)，2024 年 7 月，Santa Clara, CA，页码 193–210，出版方 USENIX Association [citation:1]。标题、年份、会议名三项互相印证 [citation:1]。

### 2.2 北京大学署名（高置信度，仅限作者列表层面）
页面作者行列出：Yinmin Zhong、Shengyu Liu（Peking University）；Junda Chen（UC San Diego）；Jianbo Hu（Peking University）；Yibo Zhu（StepFun）；Xuanzhe Liu、Xin Jin（Peking University）；Hao Zhang（UC San Diego）[citation:1]。即 **8 位作者中 5 位标注 Peking University**，覆盖第一作者 [citation:1]。

| 作者 | 页面标注单位 |
|---|---|
| Yinmin Zhong（第一作者） | Peking University |
| Shengyu Liu | Peking University |
| Jianbo Hu | Peking University |
| Xuanzhe Liu | Peking University |
| Xin Jin | Peking University |
| Junda Chen | UC San Diego |
| Hao Zhang | UC San Diego |
| Yibo Zhu | StepFun |

来源：[citation:1]。此表为“署名单位”证据，**非**机构隶属、资助或合作协议证据。

### 2.3 研究主题（高置信度）
页面摘要说明：DistServe 将 prefill 与 decoding 计算分离到不同 GPU，消除两阶段干扰，并按应用 TTFT/TPOT 时延要求协同优化资源分配与并行策略，同时依据集群带宽放置两阶段以减少通信开销 [citation:1]。评估显示相比 SOTA 系统可服务 **7.4× 更多请求**或 **12.6× 更紧 SLO**，同时 **>90% 请求**满足时延约束 [citation:1]。主题属计算机系统 / LLM 服务系统方向，落在契约学科与 2024 时间窗内 [citation:1]。

## 3. Data and Statistics

| 指标 | 数值 | 来源 |
|---|---|---|
| 有效样本（出版商页面） | 1 | [citation:1] |
| 有效成果（会议论文） | 1（OSDI '24） | [citation:1] |
| 作者总数 / 标注北大者 | 8 / 5 | [citation:1] |
| 发表时间精度 | 月（2024-07） | [citation:1] |
| 性能提升 | 7.4× 请求量 或 12.6× 更紧 SLO | [citation:1] |

## 4. Expert Perspectives
> 说明：本节无独立专家访谈来源，以下为基于页面证据的分析判断（标注为分析，非事实）。

- **分析（中置信度）**：5/8 作者含第一作者标注北大，说明北大在该成果中承担显著署名角色；但署名比例不等于贡献份额，页面未提供贡献声明 [citation:1]。
- **分析（高置信度）**：单一出版商页面不能代表北大在该方向的成果全集，也不能作为“零篇/全集”判断依据 [citation:1]。

## 5. Conclusions and Recommendations
1. **可确认**：DistServe 为 OSDI '24 论文，2024 年 7 月发表；5 位作者标注 Peking University，含第一作者；主题为 LLM 服务系统 prefill/decoding 分离与 goodput 优化 [citation:1]。
2. **不可确认（缺口）**：
   - 页面仅有作者单位行，**无院系、实验室、资助致谢或机构协议**，无法推断北大与 UC San Diego、StepFun 的正式合作安排 [citation:1]。
   - 日期仅精确到**月**，无精确发表日 [citation:1]。
   - 样本仅 1 篇，不能代表成果全集 [citation:1]。
   - 其余检索证据（USENIX 主页、USENIX Security '27、百科、博客）与 DistServe 无关，不构成补充证据 [citation:2][citation:3][citation:4][citation:5][citation:6]。
3. **建议**：获取论文 PDF 首页/致谢与 OSDI '24 程序册，以核实院系归属与资助信息；在此之前，仅可表述为“5 位作者在出版商页面标注 Peking University”，selected-1 的 resolution_status 应保持 **pending** [citation:1]。

## References
1. [citation:1] USENIX, "DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving," OSDI '24. https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin
2. [citation:2] USENIX Home. https://www.usenix.org/
3. [citation:3] USENIX Security '27. https://www.usenix.org/conference/usenixsecurity27
4. [citation:4] USENIX_百度百科. https://baike.baidu.com/item/USENIX/16660019
5. [citation:5] USENIX - 维基百科. https://zh.wikipedia.org/zh-cn/USENIX
6. [citation:6] USENIX Security 2026 录用论文深度解读（博客）. https://yaoyue123.github.io/2026/08/13/usenix-security-2026-accepted-papers-deep-dive/index.html

> 置信度说明：署名与主题结论为**高置信度**（直接引自出版商页面）；机构层面合作、精确日期、成果全集为**未核实缺口**。

## 核验结果

自动来源支持：0/30 项；人工复核：未复核。模型置信度不代表人工确认。
支持状态来自模型语义判断与原文引语校验，不能保证结论为真。

- claim:1 [missing_citation] Generated: 2026-10-20 | Research Depth: Comprehensive（受限于单一来源，实际为单页核实） — Awaiting source support judgement
- claim:2 [not_checked] 仅依据 USENIX 的 DistServe 论文页面，可高置信度确认：该文发表于 **OSDI '24（2024 年 7 月）**，8 位作者中 **5 位标注 Peking University**，含第一作者 Yinmin Zhong；研究主题为**大语言模型服务系统的 prefill/decoding 分离与 goodput 优化** [citation:1]。但该页面只提供“作者署名单位”层面的证据，**不构成**机构隶属、资助或合作协议证据，且日期仅精确到月、样本仅 1 篇 [citation:1]。 — Verification token/time budget exhausted
- claim:3 [not_checked] 本研究契约限定：仅以 DistServe 的出版商（USENIX）页面为来源，核实北京大学在该成果中的署名与研究主题，并说明来源样本与缺口；学科限定 computer_science，时间窗 2024-01-01 至 2024-12-31 [citation:1]。USENIX 为总部位于美国的非营利专业协会，主办 OSDI 等系统领域会议 [citation:2][citation:5]。需强调：页面出现机构名称只证明作者署名标注，不证明机构层面归属或正式合作。 — Verification token/time budget exhausted
- claim:4 [not_checked] 页面 BibTeX 与 citation_* 元数据一致给出：标题《DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving》，收录于 18th USENIX Symposium on Operating Systems Design and Implementation (OSDI 24)，2024 年 7 月，Santa Clara, CA，页码 193–210，出版方 USENIX Association [citation:1]。标题、年份、会议名三项互相印证 [citation:1]。 — Verification token/time budget exhausted
- claim:5 [not_checked] 页面作者行列出：Yinmin Zhong、Shengyu Liu（Peking University）；Junda Chen（UC San Diego）；Jianbo Hu（Peking University）；Yibo Zhu（StepFun）；Xuanzhe Liu、Xin Jin（Peking University）；Hao Zhang（UC San Diego）[citation:1]。即 **8 位作者中 5 位标注 Peking University**，覆盖第一作者 [citation:1]。 — Verification token/time budget exhausted
- claim:6 [missing_citation] | Yinmin Zhong（第一作者） | Peking University | — Awaiting source support judgement
- claim:7 [missing_citation] | Shengyu Liu | Peking University | — Awaiting source support judgement
- claim:8 [missing_citation] | Jianbo Hu | Peking University | — Awaiting source support judgement
- claim:9 [missing_citation] | Xuanzhe Liu | Peking University | — Awaiting source support judgement
- claim:10 [missing_citation] | Xin Jin | Peking University | — Awaiting source support judgement
- claim:11 [missing_citation] | Junda Chen | UC San Diego | — Awaiting source support judgement
- claim:12 [missing_citation] | Hao Zhang | UC San Diego | — Awaiting source support judgement
- claim:13 [missing_citation] | Yibo Zhu | StepFun | — Awaiting source support judgement
- claim:14 [not_checked] 来源：[citation:1]。此表为“署名单位”证据，**非**机构隶属、资助或合作协议证据。 — Verification token/time budget exhausted
- claim:15 [not_checked] 页面摘要说明：DistServe 将 prefill 与 decoding 计算分离到不同 GPU，消除两阶段干扰，并按应用 TTFT/TPOT 时延要求协同优化资源分配与并行策略，同时依据集群带宽放置两阶段以减少通信开销 [citation:1]。评估显示相比 SOTA 系统可服务 **7.4× 更多请求**或 **12.6× 更紧 SLO**，同时 **>90% 请求**满足时延约束 [citation:1]。主题属计算机系统 / LLM 服务系统方向，落在契约学科与 2024 时间窗内 [citation:1]。 — Verification token/time budget exhausted
- claim:16 [not_checked] | 有效样本（出版商页面） | 1 | [citation:1] | — Verification token/time budget exhausted
- claim:17 [not_checked] | 有效成果（会议论文） | 1（OSDI '24） | [citation:1] | — Verification token/time budget exhausted
- claim:18 [not_checked] | 作者总数 / 标注北大者 | 8 / 5 | [citation:1] | — Verification token/time budget exhausted
- claim:19 [not_checked] | 发表时间精度 | 月（2024-07） | [citation:1] | — Verification token/time budget exhausted
- claim:20 [not_checked] | 性能提升 | 7.4× 请求量 或 12.6× 更紧 SLO | [citation:1] | — Verification token/time budget exhausted
- claim:21 [missing_citation] 说明：本节无独立专家访谈来源，以下为基于页面证据的分析判断（标注为分析，非事实）。 — Awaiting source support judgement
- claim:22 [not_checked] **分析（中置信度）**：5/8 作者含第一作者标注北大，说明北大在该成果中承担显著署名角色；但署名比例不等于贡献份额，页面未提供贡献声明 [citation:1]。 — Verification token/time budget exhausted
- claim:23 [not_checked] **分析（高置信度）**：单一出版商页面不能代表北大在该方向的成果全集，也不能作为“零篇/全集”判断依据 [citation:1]。 — Verification token/time budget exhausted
- claim:24 [not_checked] **可确认**：DistServe 为 OSDI '24 论文，2024 年 7 月发表；5 位作者标注 Peking University，含第一作者；主题为 LLM 服务系统 prefill/decoding 分离与 goodput 优化 [citation:1]。 — Verification token/time budget exhausted
- claim:25 [missing_citation] **不可确认（缺口）**： — Awaiting source support judgement
- claim:26 [not_checked] 页面仅有作者单位行，**无院系、实验室、资助致谢或机构协议**，无法推断北大与 UC San Diego、StepFun 的正式合作安排 [citation:1]。 — Verification token/time budget exhausted
- claim:27 [not_checked] 日期仅精确到**月**，无精确发表日 [citation:1]。 — Verification token/time budget exhausted
- claim:28 [not_checked] 样本仅 1 篇，不能代表成果全集 [citation:1]。 — Verification token/time budget exhausted
- claim:29 [not_checked] 其余检索证据（USENIX 主页、USENIX Security '27、百科、博客）与 DistServe 无关，不构成补充证据 [citation:2][citation:3][citation:4][citation:5][citation:6]。 — Verification token/time budget exhausted
- claim:30 [not_checked] **建议**：获取论文 PDF 首页/致谢与 OSDI '24 程序册，以核实院系归属与资助信息；在此之前，仅可表述为“5 位作者在出版商页面标注 Peking University”，selected-1 的 resolution_status 应保持 **pending** [citation:1]。 — Verification token/time budget exhausted

## 可复核样本与对象比较
计数由结构化记录计算，仅覆盖本次取得并通过原文校验的样本；未链接版本暂按单条发表独立计数。
| 对象 | 发表记录 | 研究家族 |
| --- | ---: | ---: |
| Peking University | 1 | 1 |
| 去重汇总 | 1 | 1 |
相同成果可分别归属多个对象，合并总量取成果／家族并集，不相加各对象行。
### 同口径样本比较
2024／conference_paper；学科口径来自请求：computer_science。仅比较该组已取得样本，不作科研质量排序。
| 对象 | 本组研究家族数 |
| --- | ---: |
| Peking University | 1 |
### 已纳入成果与依据
- DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving；日期区间 2024-07-01 至 2024-07-31（month 精度）；[citation:1]
### 缺口与解释边界
待核记录 0 项；未确立的关系：coauthorship、funding、citation。未取得证据不表示关系不存在。
机构署名按所选名称／别名与发表来源对照；不推出当前任职、正式协议、内部研发投入或科研质量优劣。跨载体／年份不汇成统一质量榜。
### 后续评估建议（模型判断，待复核）
- 建议下一步获取论文 PDF 首页与致谢、OSDI '24 程序册，以核实北京大学的院系/实验室归属与资助信息；在获得这些材料前，selected-1 的 resolution_status 应保持 pending。 [citation:1]
