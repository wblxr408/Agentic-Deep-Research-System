# DistServe 出版商页面中 Peking University 的署名、发表年月与研究主题

> Generated: 2026-10-20 | Research Depth: Comprehensive

## Executive Summary
在 USENIX OSDI '24 的 DistServe 论文出版商页面上，**Peking University** 以单位标注形式出现在 **5 位作者**名下（Yinmin Zhong、Shengyu Liu、Jianbo Hu、Xuanzhe Liu、Xin Jin）[citation:1]。发表时间可确认为 **2024 年 7 月**（BibTeX `year=2024, month=jul`），但**具体日期未知**；研究主题为 LLM 推理服务中 prefill 与 decoding 的解耦及 goodput 优化[citation:1]。本次仅有一个已选对象，无法进行跨对象比较。

## 1. 背景与范围
本研究仅核查 DistServe 的 USENIX OSDI '24 出版商页面（及技术议程页）中 Peking University 的署名、发表年月与研究主题，时间窗为 2024-01-01 至 2024-12-31，学科限定为计算机科学。需注意：页面出现机构名称仅证明作者列表中的单位标注，不等同于机构层面的正式协议、资助关系或历史任职。

## 2. 关键发现

### 2.1 署名（置信度：HIGH）
出版商页面作者列表原文为：“Yinmin Zhong and Shengyu Liu, Peking University; Junda Chen, UC San Diego; Jianbo Hu, Peking University; Yibo Zhu, StepFun; Xuanzhe Liu and Xin Jin, Peking University; Hao Zhang, UC San Diego”[citation:1]。

| 作者 | 页面单位标注 |
|---|---|
| Yinmin Zhong | Peking University |
| Shengyu Liu | Peking University |
| Jianbo Hu | Peking University |
| Xuanzhe Liu | Peking University |
| Xin Jin | Peking University |

即 Peking University 在该论文作者列表中有 **5 位署名作者**[citation:1]。此为论文作者列表中的单位标注，**不证明**机构资助或正式合作协议。

### 2.2 发表年月（置信度：MEDIUM）
BibTeX 记录 `year = {2024}`、`month = jul`，会议为 18th USENIX OSDI 24，地点 Santa Clara, CA，页码 193–210[citation:1]。页面元数据 `citation_publication_date: 2024` 仅给出年份[citation:1]。技术议程页显示 OSDI '24 会期自 2024 年 7 月 10 日开始，论文自 2024-07-10 起对公众开放[citation:2]。故可确认**年份 2024、月份 7 月**；**具体日期（日）在出版商页面未给出，列为未知**。议程页的 `article:published_time: 2024-05-09` 是网页发布时间，不能当作论文发表日期[citation:2]。

### 2.3 研究主题（置信度：HIGH）
DistServe 通过将 LLM 推理的 prefill 与 decoding 阶段解耦到不同 GPU，消除 prefill-decoding 干扰，并针对 TTFT 与 TPOT 延迟约束协同优化资源分配与并行策略；评估显示可服务 **7.4×** 更多请求或 **12.6×** 更紧 SLO，**>90%** 请求满足延迟约束[citation:1]。学科归属为计算机科学（系统/LLM 服务），与契约学科一致。

### 2.4 共同主题与差异
仅一个已选对象，**无法进行跨对象比较**；共同主题/差异维度记为不适用（N/A）。

## 3. 数据与统计
- 署名作者数（Peking University 标注）：**5**[citation:1]
- 发表年份：**2024**；月份：**7 月**；日：**未知**[citation:1][citation:2]
- 会议：18th USENIX OSDI 24，Santa Clara, CA，页码 193–210[citation:1]
- 性能数据：7.4× 更多请求 / 12.6× 更紧 SLO，>90% 请求满足延迟约束[citation:1]

## 4. 专家视角
本次检索文档未包含独立专家评论或第三方分析，故不提供专家观点。页面摘要本身即为作者方对研究贡献的陈述[citation:1]。

## 5. 结论与建议
1. **署名**：Peking University 在 DistServe 作者列表中有 5 位署名作者，属单位标注，非机构协议证据[citation:1]。
2. **发表年月**：可确认 2024 年 7 月，日级日期未知[citation:1][citation:2]。
3. **研究主题**：LLM 推理服务 prefill/decoding 解耦与 goodput 优化[citation:1]。
4. **待核项**：论文具体发表日；Peking University 在该成果中的资助与正式合作协议（页面未提及）；作者院系细分归属（页面仅写 Peking University）。建议核对 USENIX 论文 PDF 首页与 proceedings 目录以确认日级日期及院系归属。

## References
[citation:1] USENIX, "DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving," OSDI '24 出版商页面. https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin
[citation:2] USENIX, "OSDI '24 Technical Sessions." https://www.usenix.org/conference/osdi24/technical-sessions

## 核验结果

自动来源支持：0/22 项；人工复核：未复核。模型置信度不代表人工确认。
支持状态来自模型语义判断与原文引语校验，不能保证结论为真。

- claim:1 [missing_citation] Generated: 2026-10-20 | Research Depth: Comprehensive — Awaiting source support judgement
- claim:2 [not_checked] 在 USENIX OSDI '24 的 DistServe 论文出版商页面上，**Peking University** 以单位标注形式出现在 **5 位作者**名下（Yinmin Zhong、Shengyu Liu、Jianbo Hu、Xuanzhe Liu、Xin Jin）[citation:1]。发表时间可确认为 **2024 年 7 月**（BibTeX `year=2024, month=jul`），但**具体日期未知**；研究主题为 LLM 推理服务中 prefill 与 decoding 的解耦及 goodput 优化[citation:1]。本次仅有一个已选对象，无法进行跨对象比较。 — Verification token/time budget exhausted
- claim:3 [missing_citation] 本研究仅核查 DistServe 的 USENIX OSDI '24 出版商页面（及技术议程页）中 Peking University 的署名、发表年月与研究主题，时间窗为 2024-01-01 至 2024-12-31，学科限定为计算机科学。需注意：页面出现机构名称仅证明作者列表中的单位标注，不等同于机构层面的正式协议、资助关系或历史任职。 — Awaiting source support judgement
- claim:4 [not_checked] 出版商页面作者列表原文为：“Yinmin Zhong and Shengyu Liu, Peking University; Junda Chen, UC San Diego; Jianbo Hu, Peking University; Yibo Zhu, StepFun; Xuanzhe Liu and Xin Jin, Peking University; Hao Zhang, UC San Diego”[citation:1]。 — Verification token/time budget exhausted
- claim:5 [missing_citation] | Yinmin Zhong | Peking University | — Awaiting source support judgement
- claim:6 [missing_citation] | Shengyu Liu | Peking University | — Awaiting source support judgement
- claim:7 [missing_citation] | Jianbo Hu | Peking University | — Awaiting source support judgement
- claim:8 [missing_citation] | Xuanzhe Liu | Peking University | — Awaiting source support judgement
- claim:9 [missing_citation] | Xin Jin | Peking University | — Awaiting source support judgement
- claim:10 [not_checked] 即 Peking University 在该论文作者列表中有 **5 位署名作者**[citation:1]。此为论文作者列表中的单位标注，**不证明**机构资助或正式合作协议。 — Verification token/time budget exhausted
- claim:11 [not_checked] BibTeX 记录 `year = {2024}`、`month = jul`，会议为 18th USENIX OSDI 24，地点 Santa Clara, CA，页码 193–210[citation:1]。页面元数据 `citation_publication_date: 2024` 仅给出年份[citation:1]。技术议程页显示 OSDI '24 会期自 2024 年 7 月 10 日开始，论文自 2024-07-10 起对公众开放[citation:2]。故可确认**年份 2024、月份 7 月**；**具体日期（日）在出版商页面未给出，列为未知**。议程页的 `article:published_time: 2024-05-09` 是网页发布时间，不能当作论文发表日期[citation:2]。 — Verification token/time budget exhausted
- claim:12 [not_checked] DistServe 通过将 LLM 推理的 prefill 与 decoding 阶段解耦到不同 GPU，消除 prefill-decoding 干扰，并针对 TTFT 与 TPOT 延迟约束协同优化资源分配与并行策略；评估显示可服务 **7.4×** 更多请求或 **12.6×** 更紧 SLO，**>90%** 请求满足延迟约束[citation:1]。学科归属为计算机科学（系统/LLM 服务），与契约学科一致。 — Verification token/time budget exhausted
- claim:13 [missing_citation] 仅一个已选对象，**无法进行跨对象比较**；共同主题/差异维度记为不适用（N/A）。 — Awaiting source support judgement
- claim:14 [not_checked] 署名作者数（Peking University 标注）：**5**[citation:1] — Verification token/time budget exhausted
- claim:15 [not_checked] 发表年份：**2024**；月份：**7 月**；日：**未知**[citation:1][citation:2] — Verification token/time budget exhausted
- claim:16 [not_checked] 会议：18th USENIX OSDI 24，Santa Clara, CA，页码 193–210[citation:1] — Verification token/time budget exhausted
- claim:17 [not_checked] 性能数据：7.4× 更多请求 / 12.6× 更紧 SLO，>90% 请求满足延迟约束[citation:1] — Verification token/time budget exhausted
- claim:18 [not_checked] 本次检索文档未包含独立专家评论或第三方分析，故不提供专家观点。页面摘要本身即为作者方对研究贡献的陈述[citation:1]。 — Verification token/time budget exhausted
- claim:19 [not_checked] **署名**：Peking University 在 DistServe 作者列表中有 5 位署名作者，属单位标注，非机构协议证据[citation:1]。 — Verification token/time budget exhausted
- claim:20 [not_checked] **发表年月**：可确认 2024 年 7 月，日级日期未知[citation:1][citation:2]。 — Verification token/time budget exhausted
- claim:21 [not_checked] **研究主题**：LLM 推理服务 prefill/decoding 解耦与 goodput 优化[citation:1]。 — Verification token/time budget exhausted
- claim:22 [missing_citation] **待核项**：论文具体发表日；Peking University 在该成果中的资助与正式合作协议（页面未提及）；作者院系细分归属（页面仅写 Peking University）。建议核对 USENIX 论文 PDF 首页与 proceedings 目录以确认日级日期及院系归属。 — Awaiting source support judgement

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
- Peking University 在 DistServe（OSDI '24）作者列表中署名 5 位作者，研究主题为 LLM 推理服务的 prefill/decoding 解耦与 goodput 优化；发表年月为 2024 年 7 月，具体日期未知。建议下一步核对 USENIX 论文 PDF 首页与 proceedings 目录以确认日级日期及院系归属。 [citation:1] [citation:1]
