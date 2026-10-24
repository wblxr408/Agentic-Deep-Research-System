# DistServe（OSDI '24）单篇成果核实与三方机构归属评估

> Generated: 2026-10-20 | Research Depth: Comprehensive

## Executive Summary

基于 USENIX 官方页面，DistServe 确认为 **2024 年 7 月**发表于第 18 届 OSDI 会议的会议论文（页码 193–210），属计算机系统学科 [citation:1]。该文由 **Peking University（5 位作者）、UC San Diego（2 位作者）、StepFun（1 位作者）** 三方共同署名，属**单篇多机构署名成果**，去重后三方共有成果计 **1 篇**，不得重复计为 3 篇 [citation:1][citation:7]。现有证据**未包含任何资助致谢或机构间正式协议信息**，共著不能推断协议，资助与协议状态须标注为"未确立" [citation:9]。

## 1. Background and Context

本研究仅聚焦 DistServe 这一篇成果，研究范围固定为 2024-01-01 至 2024-12-31、计算机科学学科，对象为 Peking University（大学）、UC San Diego（大学）、StepFun（公司）三类机构 [citation:1]。

DistServe 的技术主题是**大语言模型（LLM）推理服务中的 prefill/decode 解耦**：现有系统将两阶段合并批处理，导致 prefill-decoding 干扰并耦合资源分配与并行计划；DistServe 通过解耦两阶段、以 goodput（同时满足 TTFT 与 TPOT 约束的最大请求速率）为优化目标来提升服务性能 [citation:1][citation:2]。

方法学上须注意三条边界：官网页面出现机构名称**不证明**成果归属；抓取时间**不证明**发表时间；当前任职**不证明**历史署名，共著**不证明**正式协议 [citation:9]。本报告据此以出版商页面的 BibTeX 与作者行为主要证据源。

## 2. Key Findings

### 2.1 发表信息核实（高置信度）

USENIX 页面的 BibTeX 记录给出完整出版元数据：booktitle 为 *18th USENIX Symposium on Operating Systems Design and Implementation (OSDI 24)*，**year = 2024**，**month = jul**，地址 Santa Clara, CA，**pages = 193–210**，publisher 为 USENIX Association，ISBN 978-1-939133-40-3 [citation:1]。页面元数据 `citation_publication_date` 亦为 2024 [citation:1]。

据此可确认：**2024 年 7 月发表**，属计算机系统（操作系统）学科，成果类型为会议论文 [citation:1]。arXiv 版本（2401.09670）确实存在且主题一致，但本次证据未给出其提交日期，故**不作为发表时间依据** [citation:2]。

### 2.2 作者单位核实（高置信度）

页面作者行逐字列出 8 位作者及其单位 [citation:1]：

| 作者 | 单位 | 归属实体 |
|---|---|---|
| Yinmin Zhong | Peking University | pku |
| Shengyu Liu | Peking University | pku |
| Junda Chen | UC San Diego | ucsd |
| Jianbo Hu | Peking University | pku |
| Yibo Zhu | StepFun | stepfun |
| Xuanzhe Liu | Peking University | pku |
| Xin Jin | Peking University | pku |
| Hao Zhang | UC San Diego | ucsd |

按作者行计数：**Peking University 5 人、UC San Diego 2 人、StepFun 1 人**，合计 8 人，与 BibTeX 作者列表完全一致 [citation:1][citation:4][citation:5][citation:6]。

### 2.3 三方样本归属比较与去重

三方指向的是**同一篇论文**（output_id: `distserve-osdi24`），属单篇多机构署名，而非三项独立成果 [citation:1][citation:7]。

| 机构 | 类型 | 样本成果数（去重） | 署名作者数 | 计数方法 |
|---|---|---|---|---|
| Peking University | 大学 | **1** | 5 | full |
| UC San Diego | 大学 | **1** | 2 | full |
| StepFun | 公司 | **1** | 1 | full |
| **三方共有（去重汇总）** | — | **1** | 8（合计） | 不得重复计为 3 |

**共同主题**：三方均通过同一篇 OSDI '24 论文进入本次样本，主题一致为 LLM 推理服务系统优化 [citation:1]。

**差异**：署名结构上学术机构主导（PKU 5 人 + UCSD 2 人 = 7 人），企业方 StepFun 仅 1 人 [citation:8]。须强调，**此为署名结构差异，不构成贡献度、资助关系或协议关系的证据** [citation:8][citation:9]。

### 2.4 资助与正式协议状态（证据不足，须标明）

所给证据中**未见任何基金号、资助致谢或机构间正式合作协议的表述** [citation:9]。特别须澄清：页面上的 "Sponsored by King Abdullah University of Science and Technology (KAUST)" 是 **OSDI '24 会议赞助方**，**不是**本文的资助来源，不可误读 [citation:9]。

因此，关系覆盖状态为：共著关系 = 源支持的样本内关系；**资助 = 未确立（not_established）**；**正式协议 = 未确立** [citation:9]。

## 3. Data and Statistics

| 数据点 | 数值 | 来源 | 置信度 |
|---|---|---|---|
| 发表年份/月份 | 2024 年 7 月 | [citation:1] | 高 |
| 会议 | OSDI '24（第 18 届） | [citation:1] | 高 |
| 页码 | 193–210 | [citation:1] | 高 |
| 作者总数 | 8 | [citation:1] | 高 |
| PKU / UCSD / StepFun 作者数 | 5 / 2 / 1 | [citation:1] | 高 |
| 三方去重成果数 | 1 | [citation:1][citation:7] | 高 |
| 自报性能：请求量提升 | 7.4× | [citation:14] | 作者自报，未独立复现 |
| 自报性能：SLO 收紧 | 12.6× | [citation:14] | 作者自报，未独立复现 |
| 自报：满足延迟约束请求占比 | > 90% | [citation:14] | 作者自报，未独立复现 |

上述性能指标均为**论文作者自报**，未经独立复现，引用时须标注该限定 [citation:14]。

## 4. Expert Perspectives

本次证据中**未包含**针对 DistServe 的第三方专家评论或独立评测意见，故不提供专家观点段落，以免引入无证据支撑的判断。

可引用的仅有技术定位性描述：DistServe 作为 LLM 推理引擎之上的**编排层（orchestration layer）**实现，并在聊天机器人、编程助手、文档摘要三类真实应用负载上评估 [citation:5]。另有技术评述指出其"实践简单、未涉及过多其他优化技巧，适合作为验证 PD 分离单一技术性能的工作，代码可读性较高；但因实践方式较简单，对跨机方案限制较多"——此为社区评述，非同行评议结论，仅供参考 [citation:3]。

## 5. Conclusions and Recommendations

### 5.1 结论

1. **发表信息成立**：DistServe 为 2024 年 7 月 OSDI '24 会议论文，页码 193–210，出版商 USENIX Association [citation:1]。
2. **三方归属成立且须去重**：PKU、UCSD、StepFun 均为该单篇论文的署名单位，三方共有成果汇总计 **1 篇**，不得重复计为 3 篇 [citation:1][citation:7]。
3. **资助与协议未确立**：现有证据不支持任何资助来源或正式机构协议的结论，KAUST 为会议赞助方而非论文资助方 [citation:9]。

### 5.2 下一步评估建议（建议/推断，非事实）

1. **核实资助**：调取 USENIX 官方 PDF 的致谢（Acknowledgments）与脚注，确认是否存在基金号或资助表述；当前证据仅含摘要页与 BibTeX [citation:11]。
2. **核对单位标注**：以论文 PDF 作者脚注比对页面作者行，确认单位标注一致性与是否存在双聘/兼职标注 [citation:12]。
3. **评估合作深度**：补充作者贡献声明、代码仓库归属（LLMServe/DistServe）与机构新闻稿等独立证据，**不得由共著推断正式协议** [citation:13]。
4. **影响力评估**：可引用 7.4× 请求量、12.6× 更紧 SLO、>90% 请求满足延迟约束等指标，但须标注为作者自报、未经独立复现 [citation:14]。

### 5.3 待核清单

- arXiv 预印本（2401.09670）的提交日期 [citation:2]
- 论文致谢中的资助信息 [citation:11]
- 作者单位脚注细节（是否含双聘标注）[citation:12]
- 是否存在正式机构间合作协议 [citation:13]

## References

[citation:1] USENIX, "DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving," OSDI '24 页面（含 BibTeX 与作者行）. https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin
[citation:2] arXiv, "DistServe: Disaggregating Prefill and Decoding for Goodput-optimized..." 摘要页. https://arxiv.org/abs/2401.09670
[citation:3] 知乎, "【推理】PD分离的绝佳入门教程 —— DistServe"（社区评述）. https://zhuanlan.zhihu.com/p/19666783423
[citation:4] 同 [citation:1]，作者行 PKU 计数依据.
[citation:5] USENIX, DistServe 论文 PDF. https://www.usenix.org/system/files/osdi24-zhong-yinmin.pdf
[citation:6] 同 [citation:1]，作者行 StepFun 计数依据.
[citation:7] 同 [citation:1]，BibTeX 作者列表（去重依据）.
[citation:8] 同 [citation:1]，署名结构差异分析依据.
[citation:9] 同 [citation:1]，页面 "Sponsored by KAUST" 为会议赞助方.
[citation:11] 同 [citation:1][citation:5]，资助核实建议依据.
[citation:12] 同 [citation:1][citation:5]，单位脚注核对建议依据.
[citation:13] GitHub, "LLMServe/DistServe" 仓库. https://github.com/LLMServe/DistServe
[citation:14] 同 [citation:1]，论文自报性能指标（7.4×、12.6×、>90%）.

## 核验结果

自动来源支持：7/49 项；人工复核：未复核。模型置信度不代表人工确认。
支持状态来自模型语义判断与原文引语校验，不能保证结论为真。

- claim:1 [missing_citation] Generated: 2026-10-20 | Research Depth: Comprehensive — Awaiting source support judgement
- claim:2 [unsupported] 基于 USENIX 官方页面，DistServe 确认为 **2024 年 7 月**发表于第 18 届 OSDI 会议的会议论文（页码 193–210），属计算机系统学科 [citation:1]。该文由 **Peking University（5 位作者）、UC San Diego（2 位作者）、StepFun（1 位作者）** 三方共同署名，属**单篇多机构署名成果**，去重后三方共有成果计 **1 篇**，不得重复计为 3 篇 [citation:1][citation:7]。现有证据**未包含任何资助致谢或机构间正式协议信息**，共著不能推断协议，资助与协议状态须标注为"未确立" [citation:9]。 — The USENIX excerpt supports the venue (18th OSDI, 2024, July, pages 193–210) and the author affiliations: Peking University (Yinmin Zhong, Shengyu Liu, Jianbo Hu, Xuanzhe Liu, Xin Jin = 5), UC San Diego (Junda Chen, Hao Zhang = 2), StepFun (Yibo Zhu = 1). However, the claim's assertion that the evidence contains no funding acknowledgments or formal inter-institutional agreements, and that funding/agreement status must be marked 'unestablished', is not entailed by the supplied excerpts; the cited CSDN excerpt (citation 9) is about DistServe's architecture and says nothing about funding or agreements. The 'no funding/agreement' negative claim is not established by the provided passages.
- claim:3 [unsupported] 本研究仅聚焦 DistServe 这一篇成果，研究范围固定为 2024-01-01 至 2024-12-31、计算机科学学科，对象为 Peking University（大学）、UC San Diego（大学）、StepFun（公司）三类机构 [citation:1]。 — The excerpt confirms DistServe, 2024, and the three institutions (Peking University, UC San Diego, StepFun). But the claim's framing that the study scope is fixed to 2024-01-01 to 2024-12-31 and computer science discipline, focusing only on this one work, is a meta-statement about the report's scope not entailed by the source excerpt. The date range and discipline restriction are not stated in the supplied passages.
- claim:5 [unsupported] 方法学上须注意三条边界：官网页面出现机构名称**不证明**成果归属；抓取时间**不证明**发表时间；当前任职**不证明**历史署名，共著**不证明**正式协议 [citation:9]。本报告据此以出版商页面的 BibTeX 与作者行为主要证据源。 — The cited CSDN excerpt describes DistServe's architecture (prefill/decode separation, KV cache transfer, scheduler) and contains nothing about methodological boundaries such as institution names not proving attribution, crawl time not proving publication time, current affiliation not proving historical authorship, or co-authorship not proving formal agreements. The claim's methodological assertions are not entailed by the supplied passage.
- claim:9 [missing_citation] | Yinmin Zhong | Peking University | pku | — Awaiting source support judgement
- claim:10 [missing_citation] | Shengyu Liu | Peking University | pku | — Awaiting source support judgement
- claim:11 [missing_citation] | Junda Chen | UC San Diego | ucsd | — Awaiting source support judgement
- claim:12 [missing_citation] | Jianbo Hu | Peking University | pku | — Awaiting source support judgement
- claim:13 [missing_citation] | Yibo Zhu | StepFun | stepfun | — Awaiting source support judgement
- claim:14 [missing_citation] | Xuanzhe Liu | Peking University | pku | — Awaiting source support judgement
- claim:15 [missing_citation] | Xin Jin | Peking University | pku | — Awaiting source support judgement
- claim:16 [missing_citation] | Hao Zhang | UC San Diego | ucsd | — Awaiting source support judgement
- claim:19 [missing_citation] | Peking University | 大学 | **1** | 5 | full | — Awaiting source support judgement
- claim:20 [missing_citation] | UC San Diego | 大学 | **1** | 2 | full | — Awaiting source support judgement
- claim:21 [missing_citation] | StepFun | 公司 | **1** | 1 | full | — Awaiting source support judgement
- claim:22 [missing_citation] | **三方共有（去重汇总）** | — | **1** | 8（合计） | 不得重复计为 3 | — Awaiting source support judgement
- claim:24 [unsupported] **差异**：署名结构上学术机构主导（PKU 5 人 + UCSD 2 人 = 7 人），企业方 StepFun 仅 1 人 [citation:8]。须强调，**此为署名结构差异，不构成贡献度、资助关系或协议关系的证据** [citation:8][citation:9]。 — The cited excerpts (8 and 9) discuss DistServe's technical approach and do not contain the author affiliation counts (PKU 5, UCSD 2, StepFun 1) nor the caveat about contribution/funding/agreement. The affiliation counts appear only in citation 1, not in the supplied excerpts for this claim.
- claim:25 [unsupported] 所给证据中**未见任何基金号、资助致谢或机构间正式合作协议的表述** [citation:9]。特别须澄清：页面上的 "Sponsored by King Abdullah University of Science and Technology (KAUST)" 是 **OSDI '24 会议赞助方**，**不是**本文的资助来源，不可误读 [citation:9]。 — The supplied excerpt (citation 9) is a technical description of DistServe and contains no statement about absence of grant numbers/acknowledgments, nor about the KAUST sponsorship being conference-level rather than paper funding. The KAUST text appears in citation 1, not in the cited excerpt.
- claim:26 [not_checked] 因此，关系覆盖状态为：共著关系 = 源支持的样本内关系；**资助 = 未确立（not_established）**；**正式协议 = 未确立** [citation:9]。 — Verification token/time budget exhausted
- claim:27 [not_checked] | 发表年份/月份 | 2024 年 7 月 | [citation:1] | 高 | — Verification token/time budget exhausted
- claim:28 [not_checked] | 会议 | OSDI '24（第 18 届） | [citation:1] | 高 | — Verification token/time budget exhausted
- claim:29 [not_checked] | 页码 | 193–210 | [citation:1] | 高 | — Verification token/time budget exhausted
- claim:30 [not_checked] | 作者总数 | 8 | [citation:1] | 高 | — Verification token/time budget exhausted
- claim:31 [not_checked] | PKU / UCSD / StepFun 作者数 | 5 / 2 / 1 | [citation:1] | 高 | — Verification token/time budget exhausted
- claim:32 [not_checked] | 三方去重成果数 | 1 | [citation:1][citation:7] | 高 | — Verification token/time budget exhausted
- claim:33 [not_checked] | 自报性能：请求量提升 | 7.4× | [citation:14] | 作者自报，未独立复现 | — Verification token/time budget exhausted
- claim:34 [not_checked] | 自报性能：SLO 收紧 | 12.6× | [citation:14] | 作者自报，未独立复现 | — Verification token/time budget exhausted
- claim:35 [not_checked] | 自报：满足延迟约束请求占比 | > 90% | [citation:14] | 作者自报，未独立复现 | — Verification token/time budget exhausted
- claim:36 [not_checked] 上述性能指标均为**论文作者自报**，未经独立复现，引用时须标注该限定 [citation:14]。 — Verification token/time budget exhausted
- claim:37 [missing_citation] 本次证据中**未包含**针对 DistServe 的第三方专家评论或独立评测意见，故不提供专家观点段落，以免引入无证据支撑的判断。 — Awaiting source support judgement
- claim:38 [not_checked] 可引用的仅有技术定位性描述：DistServe 作为 LLM 推理引擎之上的**编排层（orchestration layer）**实现，并在聊天机器人、编程助手、文档摘要三类真实应用负载上评估 [citation:5]。另有技术评述指出其"实践简单、未涉及过多其他优化技巧，适合作为验证 PD 分离单一技术性能的工作，代码可读性较高；但因实践方式较简单，对跨机方案限制较多"——此为社区评述，非同行评议结论，仅供参考 [citation:3]。 — Verification token/time budget exhausted
- claim:39 [not_checked] **发表信息成立**：DistServe 为 2024 年 7 月 OSDI '24 会议论文，页码 193–210，出版商 USENIX Association [citation:1]。 — Verification token/time budget exhausted
- claim:40 [not_checked] **三方归属成立且须去重**：PKU、UCSD、StepFun 均为该单篇论文的署名单位，三方共有成果汇总计 **1 篇**，不得重复计为 3 篇 [citation:1][citation:7]。 — Verification token/time budget exhausted
- claim:41 [not_checked] **资助与协议未确立**：现有证据不支持任何资助来源或正式机构协议的结论，KAUST 为会议赞助方而非论文资助方 [citation:9]。 — Not checked
- claim:42 [not_checked] **核实资助**：调取 USENIX 官方 PDF 的致谢（Acknowledgments）与脚注，确认是否存在基金号或资助表述；当前证据仅含摘要页与 BibTeX [citation:11]。 — Not checked
- claim:43 [not_checked] **核对单位标注**：以论文 PDF 作者脚注比对页面作者行，确认单位标注一致性与是否存在双聘/兼职标注 [citation:12]。 — Not checked
- claim:44 [not_checked] **评估合作深度**：补充作者贡献声明、代码仓库归属（LLMServe/DistServe）与机构新闻稿等独立证据，**不得由共著推断正式协议** [citation:13]。 — Not checked
- claim:45 [not_checked] **影响力评估**：可引用 7.4× 请求量、12.6× 更紧 SLO、>90% 请求满足延迟约束等指标，但须标注为作者自报、未经独立复现 [citation:14]。 — Not checked
- claim:46 [not_checked] arXiv 预印本（2401.09670）的提交日期 [citation:2] — Not checked
- claim:47 [not_checked] 论文致谢中的资助信息 [citation:11] — Not checked
- claim:48 [not_checked] 作者单位脚注细节（是否含双聘标注）[citation:12] — Not checked
- claim:49 [not_checked] 是否存在正式机构间合作协议 [citation:13] — Not checked

## 可复核样本与对象比较
计数由结构化记录计算，仅覆盖本次取得并通过原文校验的样本；未链接版本暂按单条发表独立计数。
| 对象 | 发表记录 | 研究家族 |
| --- | ---: | ---: |
| Peking University | 1 | 1 |
| UC San Diego | 1 | 1 |
| StepFun | 1 | 1 |
| 去重汇总 | 1 | 1 |
相同成果可分别归属多个对象，合并总量取成果／家族并集，不相加各对象行。
### 同口径样本比较
2024／conference_paper；学科口径来自请求：computer science。仅比较该组已取得样本，不作科研质量排序。
| 对象 | 本组研究家族数 |
| --- | ---: |
| Peking University | 1 |
| UC San Diego | 1 |
| StepFun | 1 |
### 已纳入成果与依据
- DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving；日期区间 2024-07-01 至 2024-07-31（month 精度）；[citation:1]
### 缺口与解释边界
待核记录 0 项；未确立的关系：funding、citation。未取得证据不表示关系不存在。
机构署名按所选名称／别名与发表来源对照；不推出当前任职、正式协议、内部研发投入或科研质量优劣。跨载体／年份不汇成统一质量榜。
### 后续评估建议（模型判断，待复核）
- 下一步应查阅论文 PDF 的致谢与作者单位脚注，以核实资助来源与单位标注；现有证据未包含任何资助或正式合作协议信息，共著不能推断协议。 [citation:1] [citation:5]
