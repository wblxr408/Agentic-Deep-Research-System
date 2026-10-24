# 腾讯云 VPC 网络故障检测与恢复：Harp（NSDI '26）有界案例研究

> Generated: 2026-10-21 | Research Depth: Comprehensive

## Executive Summary

以 USENIX NSDI '26 的 Harp 展示页为唯一种子，可核实腾讯在 2026 年有一项关于 VPC 网络故障检测与恢复的公开会议论文：*Harp: Improving VPC Network Availability via Efficient Failure Detection and Rerouting in Tencent Cloud*，BibTeX 标注 `year = {2026}`、`month = may`，故发表时间应保留为 **2026 年 5 月（月精度）** [citation:1]。论文由 **5 位腾讯作者与 1 位复旦大学作者**共著，摘要描述了不依赖特定硬件或传输协议的软件路径监测与故障绕行机制，并自述已在腾讯云部署两年多、生产环境中断时间降低 **78.71%–99.97%** [citation:1]。上述生产指标属**作者自述**，种子页面未提供独立验证；本案例仅覆盖一项成果，不代表腾讯 2020–2026 年网络研究全集，也不能以数量推断研发投入 [citation:1]。

## 1. 背景与研究范围

### 1.1 范围契约

本研究按组织研究契约锁定单一实体 **Tencent**（别名 Tencent Cloud、腾讯、腾讯云），学科限定为计算机科学，主题为 VPC 网络故障检测与恢复，时间窗为 2026-01-01 至 2026-10-21，证据截止 2026-10-21T04:39:19Z。实体解析状态为 `pending`，唯一来源 URL 为 Harp 展示页 [citation:1]。

### 1.2 方法边界

- **单一种子**：仅以出版商展示页为起点，未扩展检索腾讯其他网络论文，因此本案例是**有界样本**而非全集 [citation:1]。
- **页面出现名称不等于归属**：展示页同时出现 USENIX、KAUST 赞助方等名称，只有作者单位行与 BibTeX 作者字段被用于归属判定 [citation:1]。
- **抓取时间不等于发表时间**：发表时间以 BibTeX 的 `year`/`month` 字段为准，而非页面抓取时刻 [citation:1]。
- **共著不等于正式协议**：企业与高校同列作者仅构成学术合作线索，不构成机构级协议证据 [citation:1]。

## 2. 关键发现

### 2.1 论文题名、发表月份与出版信息

| 字段 | 内容 | 来源 |
|---|---|---|
| 题名 | Harp: Improving VPC Network Availability via Efficient Failure Detection and Rerouting in Tencent Cloud | [citation:1] |
| 会议 | 23rd USENIX Symposium on Networked Systems Design and Implementation (NSDI 26) | [citation:1] |
| 年份 | 2026 | [citation:1] |
| 月份 | may（5 月，月精度） | [citation:1] |
| 页码 | 1669–1684 | [citation:1] |
| 出版方 | USENIX Association | [citation:1] |
| 地点 | Renton, WA | [citation:1] |
| ISBN | 978-1-939133-54-0 | [citation:1] |

BibTeX 条目同时给出 `citation_publication_date: 2026` 与 `citation_conference_title`，与上述字段一致 [citation:1]。技术日程页显示会议自 **2026 年 5 月 4 日（周一）** 开始，与 5 月发表一致；但该页未直接列出 Harp 的具体场次，因此**不能据此确定论文的精确报告日**，发表时间应保持月精度 [citation:2]。

### 2.2 Tencent 署名与外部高校共著线索

作者单位行原文为：“Jiayu Hu, Feng Jin, and Xianping Zhou, Tencent; Kai Zhang, Fudan University; Zhen Shen and Yongkang Luo, Tencent” [citation:1]。据此：

| 作者 | 单位 | 归属 |
|---|---|---|
| Jiayu Hu | Tencent | 腾讯 |
| Feng Jin | Tencent | 腾讯 |
| Xianping Zhou | Tencent | 腾讯 |
| Kai Zhang | Fudan University | 外部高校 |
| Zhen Shen | Tencent | 腾讯 |
| Yongkang Luo | Tencent | 腾讯 |

即 **6 位作者中 5 位腾讯、1 位复旦**，构成企业与高校共著线索 [citation:1]。需强调：该线索仅证明学术层面的共同署名，**不构成腾讯与复旦大学之间的正式协议或机构级合作关系证明**；复旦作者的具体角色与贡献在种子页面未披露 [citation:1]。

### 2.3 摘要可支持的问题域与机制

摘要声明 Harp 是面向 VPC 网络的“高效且鲁棒”的故障检测与恢复机制 [citation:1]。可核实的机制要点有三：

1. **不依赖特定硬件特性或传输协议**——与既有方法形成对照，降低部署前提 [citation:1]。
2. **软件路径监测**——Harp 是轻量级软件实现，为每一对通信主机识别可行的物理路径并监测其健康状态 [citation:1]。
3. **故障绕行**——发生网络故障时，将受影响流从故障路径快速切换到健康路径 [citation:1]。

摘要未披露具体算法、探测频率、控制面架构、路径计算方式等细节，这些均属**全文缺口**，不应补造 [citation:1]。

### 2.4 作者自述部署／生产结果 vs. 独立验证

摘要自述：Harp 已在腾讯云部署**两年多**，并在处理网络故障方面“证明有效”；生产系统结果显示 VPC 网络中断时间降低 **78.71%–99.97%**，可在**亚秒级**绕过故障路径；作者还分享了部署中高效检测与处理故障的经验 [citation:1]。

| 结论类型 | 内容 | 证据性质 | 置信度 |
|---|---|---|---|
| 部署时长 | 两年多 | 作者自述 | 中 |
| 中断时间降幅 | 78.71%–99.97% | 作者自述生产结果 | 中 |
| 绕行时延 | 亚秒级 | 作者自述 | 中 |
| 独立复现/第三方评测 | 未提供 | — | 未知 |

种子页面未提供任何第三方独立复现、工件评估或外部评测证据，因此上述指标应标注为“**作者报告**”，而非独立验证 [citation:1]。全文 PDF 未取得，故不补造实验条件、对照组、统计方法与图表 [citation:1]。

## 3. 数据与统计

| 数据点 | 数值 | 来源 | 说明 |
|---|---|---|---|
| 样本内公开成果数 | 1 | [citation:1] | 单一种子，非全集 |
| 作者总数 | 6 | [citation:1] | — |
| 腾讯作者数 | 5 | [citation:1] | — |
| 外部高校作者数 | 1（复旦） | [citation:1] | — |
| 论文页数 | 16（1669–1684） | [citation:1] | 依页码推算 |
| 中断时间降幅 | 78.71%–99.97% | [citation:1] | 作者自述 |
| 部署时长 | >2 年 | [citation:1] | 作者自述 |

**计数口径说明**：上述“1 项成果”为确定性样本计数，采用 full 计数法，仅反映本次有界检索结果，**不是现实全集，也不是科研质量排名**，不得用于推断腾讯在该主题上的投入规模 [citation:1]。

## 4. 专家视角与证据分级

本案例无外部专家评论可引用，以下为基于证据的分级判断（分析师解读，非文档事实）：

- **高置信**：题名、作者与单位、发表年月（2026-05）、摘要机制描述——均直接引自出版商页面 [citation:1]。
- **中置信**：78.71%–99.97%、亚秒级、两年多部署——原文明确，但属作者自述、无独立验证 [citation:1]。
- **低/未知**：会议具体报告日、实验条件、基线对比、资助信息、内部战略与未来方向——种子页面无依据 [citation:1][citation:2]。

> 摘要原文：“Harp has been deployed in Tencent Cloud for more than two years and has proven its effectiveness in handling network failures.” [citation:1]

该引述本身即为作者自述，引用它不构成对其结论的独立背书。

## 5. 结论与建议

### 5.1 可分享的结论

1. 腾讯在 2026 年 5 月于 NSDI '26 发表了一项 VPC 网络故障检测与恢复研究，题名与出版信息如上表 [citation:1]。
2. 该成果为腾讯主导、复旦大学参与的企业—高校共著，5:1 的作者构成清晰 [citation:1]。
3. 技术路径为**软件化路径监测 + 快速绕行**，明确回避对特定硬件与传输协议的依赖 [citation:1]。
4. 生产指标为作者自述，尚缺独立验证，引用时应保留“作者报告”限定语 [citation:1]。

### 5.2 明确不成立的推断

- 不能以 1 项成果推断腾讯 2020–2026 年网络研究全集或研发投入 [citation:1]。
- 不能将腾讯—复旦共著表述为正式合作协议 [citation:1]。
- 不能将 BibTeX 的 `month = may` 细化为具体某日 [citation:1]。
- 不能补造实验条件、图表、资助信息或未来方向 [citation:1]。

### 5.3 待验证问题

1. 78.71%–99.97% 的**测量口径、样本期与故障类型**分别是什么？[citation:1]
2. “两年多”部署的**起始时间与覆盖区域**为何？[citation:1]
3. Harp 在 NSDI '26 是否有独立于作者的**工件评估（artifact evaluation）**记录？[citation:2]
4. 是否存在**后续版本或期刊扩展**？[citation:1]
5. 复旦作者（Kai Zhang）的**具体角色与贡献**为何？[citation:1]
6. 论文的**资助信息、内部战略与未来方向**——种子页面无依据，保留为缺口 [citation:1]。

**建议下一步**：获取 NSDI '26 全文 PDF 与可能的 artifact evaluation 记录，以核实实验条件、基线对比与独立验证情况 [citation:2]。

## References

[citation:1] Jiayu Hu, Feng Jin, Xianping Zhou, Kai Zhang, Zhen Shen, Yongkang Luo. "Harp: Improving VPC Network Availability via Efficient Failure Detection and Rerouting in Tencent Cloud." 23rd USENIX Symposium on Networked Systems Design and Implementation (NSDI 26), pp. 1669–1684, Renton, WA, USENIX Association, 2026 (month = may). https://www.usenix.org/conference/nsdi26/presentation/hu-jiayu

[citation:2] USENIX. "NSDI '26 Technical Sessions." https://www.usenix.org/conference/nsdi26/technical-sessions

## 核验结果

自动来源支持：8/64 项；人工复核：未复核。模型置信度不代表人工确认。
支持状态来自模型语义判断与原文引语校验，不能保证结论为真。

- claim:1 [missing_citation] Generated: 2026-10-21 | Research Depth: Comprehensive — Awaiting source support judgement
- claim:3 [unverifiable] 本研究按组织研究契约锁定单一实体 **Tencent**（别名 Tencent Cloud、腾讯、腾讯云），学科限定为计算机科学，主题为 VPC 网络故障检测与恢复，时间窗为 2026-01-01 至 2026-10-21，证据截止 2026-10-21T04:39:19Z。实体解析状态为 `pending`，唯一来源 URL 为 Harp 展示页 [citation:1]。 — The excerpts confirm the single source URL, the Tencent/腾讯云 entity, the VPC failure detection/recovery topic, and 2026 publication. However, the research-contract details (entity resolution status 'pending', discipline 'computer science', time window 2026-01-01 to 2026-10-21, evidence cutoff timestamp) are not stated in the supplied passages and cannot be verified from them.
- claim:4 [unverifiable] **单一种子**：仅以出版商展示页为起点，未扩展检索腾讯其他网络论文，因此本案例是**有界样本**而非全集 [citation:1]。 — The excerpts show a single publisher presentation page, but the claim about the research methodology (using only this seed, not expanding to other Tencent network papers, treating it as a bounded sample) is a process assertion not entailed by the source content itself.
- claim:9 [not_checked] | 会议 | 23rd USENIX Symposium on Networked Systems Design and Implementation (NSDI 26) | [citation:1] | — Verification token/time budget exhausted
- claim:10 [not_checked] | 年份 | 2026 | [citation:1] | — Verification token/time budget exhausted
- claim:11 [not_checked] | 月份 | may（5 月，月精度） | [citation:1] | — Verification token/time budget exhausted
- claim:12 [not_checked] | 页码 | 1669–1684 | [citation:1] | — Verification token/time budget exhausted
- claim:16 [not_checked] BibTeX 条目同时给出 `citation_publication_date: 2026` 与 `citation_conference_title`，与上述字段一致 [citation:1]。技术日程页显示会议自 **2026 年 5 月 4 日（周一）** 开始，与 5 月发表一致；但该页未直接列出 Harp 的具体场次，因此**不能据此确定论文的精确报告日**，发表时间应保持月精度 [citation:2]。 — Verification token/time budget exhausted
- claim:17 [not_checked] 作者单位行原文为：“Jiayu Hu, Feng Jin, and Xianping Zhou, Tencent; Kai Zhang, Fudan University; Zhen Shen and Yongkang Luo, Tencent” [citation:1]。据此： — Verification token/time budget exhausted
- claim:18 [missing_citation] | Jiayu Hu | Tencent | 腾讯 | — Awaiting source support judgement
- claim:19 [missing_citation] | Feng Jin | Tencent | 腾讯 | — Awaiting source support judgement
- claim:20 [missing_citation] | Xianping Zhou | Tencent | 腾讯 | — Awaiting source support judgement
- claim:21 [missing_citation] | Kai Zhang | Fudan University | 外部高校 | — Awaiting source support judgement
- claim:22 [missing_citation] | Zhen Shen | Tencent | 腾讯 | — Awaiting source support judgement
- claim:23 [missing_citation] | Yongkang Luo | Tencent | 腾讯 | — Awaiting source support judgement
- claim:24 [not_checked] 即 **6 位作者中 5 位腾讯、1 位复旦**，构成企业与高校共著线索 [citation:1]。需强调：该线索仅证明学术层面的共同署名，**不构成腾讯与复旦大学之间的正式协议或机构级合作关系证明**；复旦作者的具体角色与贡献在种子页面未披露 [citation:1]。 — Verification token/time budget exhausted
- claim:25 [not_checked] 摘要声明 Harp 是面向 VPC 网络的“高效且鲁棒”的故障检测与恢复机制 [citation:1]。可核实的机制要点有三： — Verification token/time budget exhausted
- claim:26 [not_checked] **不依赖特定硬件特性或传输协议**——与既有方法形成对照，降低部署前提 [citation:1]。 — Verification token/time budget exhausted
- claim:27 [not_checked] **软件路径监测**——Harp 是轻量级软件实现，为每一对通信主机识别可行的物理路径并监测其健康状态 [citation:1]。 — Verification token/time budget exhausted
- claim:28 [not_checked] **故障绕行**——发生网络故障时，将受影响流从故障路径快速切换到健康路径 [citation:1]。 — Verification token/time budget exhausted
- claim:29 [not_checked] 摘要未披露具体算法、探测频率、控制面架构、路径计算方式等细节，这些均属**全文缺口**，不应补造 [citation:1]。 — Verification token/time budget exhausted
- claim:30 [not_checked] 摘要自述：Harp 已在腾讯云部署**两年多**，并在处理网络故障方面“证明有效”；生产系统结果显示 VPC 网络中断时间降低 **78.71%–99.97%**，可在**亚秒级**绕过故障路径；作者还分享了部署中高效检测与处理故障的经验 [citation:1]。 — Verification token/time budget exhausted
- claim:31 [missing_citation] | 部署时长 | 两年多 | 作者自述 | 中 | — Awaiting source support judgement
- claim:32 [missing_citation] | 中断时间降幅 | 78.71%–99.97% | 作者自述生产结果 | 中 | — Awaiting source support judgement
- claim:33 [missing_citation] | 绕行时延 | 亚秒级 | 作者自述 | 中 | — Awaiting source support judgement
- claim:34 [missing_citation] | 独立复现/第三方评测 | 未提供 | — | 未知 | — Awaiting source support judgement
- claim:35 [not_checked] 种子页面未提供任何第三方独立复现、工件评估或外部评测证据，因此上述指标应标注为“**作者报告**”，而非独立验证 [citation:1]。全文 PDF 未取得，故不补造实验条件、对照组、统计方法与图表 [citation:1]。 — Verification token/time budget exhausted
- claim:36 [not_checked] | 样本内公开成果数 | 1 | [citation:1] | 单一种子，非全集 | — Verification token/time budget exhausted
- claim:37 [not_checked] | 作者总数 | 6 | [citation:1] | — | — Verification token/time budget exhausted
- claim:38 [not_checked] | 腾讯作者数 | 5 | [citation:1] | — | — Verification token/time budget exhausted
- claim:39 [not_checked] | 外部高校作者数 | 1（复旦） | [citation:1] | — | — Verification token/time budget exhausted
- claim:40 [not_checked] | 论文页数 | 16（1669–1684） | [citation:1] | 依页码推算 | — Verification token/time budget exhausted
- claim:41 [not_checked] | 中断时间降幅 | 78.71%–99.97% | [citation:1] | 作者自述 | — Not checked
- claim:42 [not_checked] | 部署时长 | >2 年 | [citation:1] | 作者自述 | — Not checked
- claim:43 [not_checked] **计数口径说明**：上述“1 项成果”为确定性样本计数，采用 full 计数法，仅反映本次有界检索结果，**不是现实全集，也不是科研质量排名**，不得用于推断腾讯在该主题上的投入规模 [citation:1]。 — Not checked
- claim:44 [not_checked] 本案例无外部专家评论可引用，以下为基于证据的分级判断（分析师解读，非文档事实）： — Not checked
- claim:45 [not_checked] **高置信**：题名、作者与单位、发表年月（2026-05）、摘要机制描述——均直接引自出版商页面 [citation:1]。 — Not checked
- claim:46 [not_checked] **中置信**：78.71%–99.97%、亚秒级、两年多部署——原文明确，但属作者自述、无独立验证 [citation:1]。 — Not checked
- claim:47 [not_checked] **低/未知**：会议具体报告日、实验条件、基线对比、资助信息、内部战略与未来方向——种子页面无依据 [citation:1][citation:2]。 — Not checked
- claim:48 [not_checked] 摘要原文：“Harp has been deployed in Tencent Cloud for more than two years and has proven its effectiveness in handling network failures.” [citation:1] — Not checked
- claim:49 [not_checked] 该引述本身即为作者自述，引用它不构成对其结论的独立背书。 — Not checked
- claim:50 [not_checked] 腾讯在 2026 年 5 月于 NSDI '26 发表了一项 VPC 网络故障检测与恢复研究，题名与出版信息如上表 [citation:1]。 — Not checked
- claim:51 [not_checked] 该成果为腾讯主导、复旦大学参与的企业—高校共著，5:1 的作者构成清晰 [citation:1]。 — Not checked
- claim:52 [not_checked] 技术路径为**软件化路径监测 + 快速绕行**，明确回避对特定硬件与传输协议的依赖 [citation:1]。 — Not checked
- claim:53 [not_checked] 生产指标为作者自述，尚缺独立验证，引用时应保留“作者报告”限定语 [citation:1]。 — Not checked
- claim:54 [not_checked] 不能以 1 项成果推断腾讯 2020–2026 年网络研究全集或研发投入 [citation:1]。 — Not checked
- claim:55 [not_checked] 不能将腾讯—复旦共著表述为正式合作协议 [citation:1]。 — Not checked
- claim:56 [not_checked] 不能将 BibTeX 的 `month = may` 细化为具体某日 [citation:1]。 — Not checked
- claim:57 [not_checked] 不能补造实验条件、图表、资助信息或未来方向 [citation:1]。 — Not checked
- claim:58 [not_checked] 78.71%–99.97% 的**测量口径、样本期与故障类型**分别是什么？[citation:1] — Not checked
- claim:59 [not_checked] “两年多”部署的**起始时间与覆盖区域**为何？[citation:1] — Not checked
- claim:60 [not_checked] Harp 在 NSDI '26 是否有独立于作者的**工件评估（artifact evaluation）**记录？[citation:2] — Not checked
- claim:61 [not_checked] 是否存在**后续版本或期刊扩展**？[citation:1] — Not checked
- claim:62 [not_checked] 复旦作者（Kai Zhang）的**具体角色与贡献**为何？[citation:1] — Not checked
- claim:63 [not_checked] 论文的**资助信息、内部战略与未来方向**——种子页面无依据，保留为缺口 [citation:1]。 — Not checked
- claim:64 [not_checked] **建议下一步**：获取 NSDI '26 全文 PDF 与可能的 artifact evaluation 记录，以核实实验条件、基线对比与独立验证情况 [citation:2]。 — Not checked

## 研究对象、口径与冻结配置
主题：VPC network failure detection and recovery；学科：computer science；时间：2026-01-01 至 2026-10-21。
对象类型：company；请求冻结时间：2026-10-21T04:39:19.742424+00:00。实际采集时间逐来源保留。
范围规则：adrs-organization-scope-v2；配置版本：tencent-network-case-20261021-v1；权重规则：adrs-weight-rules-v1；预设版本：adrs-presets-v1。
分别保留发表记录与研究家族；同成果可归属多个对象，汇总取并集，未关联版本按独立发表计数。
偏好配置不等于已完成评分；结果页只读重排不改写本报告的配置、事实或证据。
### 对象与来源
- Tencent（company；pending）：<https://www.usenix.org/conference/nsdi26/presentation/hu-jiayu>
### 原始与生效权重
| 维度 | 原始权重 | 开启 | 生效权重 |
| --- | ---: | --- | ---: |
| 主题相关性 | 35.0 | 是 | 35.00% |
| 研究路线契合 | 20.0 | 是 | 20.00% |
| 成果表现 | 20.0 | 是 | 20.00% |
| 证据完整度 | 15.0 | 是 | 15.00% |
| 时效性 | 10.0 | 是 | 10.00% |
| 合作互补性 | 0.0 | 是 | 0.00% |
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
- ev-249a9032：Harp: Improving VPC Network Availability via Efficient Failure Detection and Rerouting in Tencent Cloud \| USENIX；<https://www.usenix.org/conference/nsdi26/presentation/hu-jiayu>；采集 2026-10-21T04:39:46.906993。
- ev-7375e4f1：NSDI '26 Technical Sessions \| USENIX；<https://www.usenix.org/conference/nsdi26/technical-sessions>；采集 2026-10-21T04:39:49.686679。
- ev-f6b1631f：NSDI \| Overview — Federal Geographic Data Committee - FGDC；<https://www.fgdc.gov/nsdi/nsdi.html>；采集 2026-10-21T04:39:28.274812+00:00。
- ev-cbd057ff：NSDI '26 \| USENIX；<https://www.usenix.org/conference/nsdi26>；采集 2026-10-21T04:39:28.274812+00:00。
- ev-6863bbe3：NSDI '24 \| USENIX；<https://www.usenix.org/conference/nsdi24>；采集 2026-10-21T04:39:28.274812+00:00。
- ev-9fe5722d：NSDI \| Strategic Plan — Federal Geographic Data Committee；<https://www.fgdc.gov/nsdi-plan>；采集 2026-10-21T04:39:28.274812+00:00。
- ev-a937dff0：NSDI Conference - Home；<https://dl.acm.org/conference/nsdi>；采集 2026-10-21T04:39:28.274812+00:00。
- ev-85c8a45f：NSDI；<https://dl.acm.org/doi/proceedings/10.5555/3691825>；采集 2026-10-21T04:39:28.274812+00:00。
- ev-5f9577a5：Symposium on Networked Systems Design and Implementation；<https://en.wikipedia.org/wiki/Symposium_on_Networked_Systems_Design_and_Implementation>；采集 2026-10-21T04:39:28.274812+00:00。
- ev-b7f990e1：NSDI ’26 Fall；<https://nsdi26fall.usenix.hotcrp.com/>；采集 2026-10-21T04:39:28.274812+00:00。
- ev-904b3946：OGC NSDI Modernization Project \| Advancing U.S. Spatial Data；<https://www.ogc.org/initiatives/national-spatial-data-infrastructure-modernization-project/>；采集 2026-10-21T04:39:28.274812+00:00。
- ev-7fafe161：Microsoft at NSDI 2026: Advances in large-scale networked systems；<https://www.microsoft.com/en-us/research/blog/microsoft-at-nsdi-2026-advances-in-large-scale-networked-systems/>；采集 2026-10-21T04:39:28.274812+00:00。
- ev-3fa39308：HARP Login；<https://harp.cms.gov/>；采集 2026-10-21T04:39:28.270464+00:00。
- ev-89749cdd：Harp - Wikipedia；<https://en.wikipedia.org/wiki/Harp>；采集 2026-10-21T04:39:28.270464+00:00。
- ev-42b7e814：Health and Recovery Plans (HARPs)；<https://omh.ny.gov/omhweb/bho/harp.html>；采集 2026-10-21T04:39:28.270464+00:00。
- ev-ce948196：Health and Recovery Plan (HARP)/ Behavioral Health；<https://www.health.ny.gov/health_care/medicaid/program/medicaid_health_homes/harp_bh/index.htm>；采集 2026-10-21T04:39:28.270464+00:00。
- ev-01d613d5：12 Different Types of Harps - MusicalHow；<https://www.musicalhow.com/harp-types/>；采集 2026-10-21T04:39:28.270464+00:00。
- ev-c55a7368：Natalie Harp Bio, Age, Height, Husband, Family, Health & Net Worth；<https://thebiographybytes.com/natalie-harp/>；采集 2026-10-21T04:39:28.270464+00:00。
- ev-30902970：Harp \| Description, History, & Facts \| Britannica；<https://www.britannica.com/art/harp-musical-instrument>；采集 2026-10-21T04:39:28.270464+00:00。
- ev-05bf7aee：Harps \| Harp Sheet Music - Harp Parts & Accessories - Harp Strings \| Harp；<https://www.harp.com/>；采集 2026-10-21T04:39:28.270464+00:00。
- ev-c6491567：Rentals and Sales - The Harp Place；<https://theharpplace.com/harp-rentals/>；采集 2026-10-21T04:39:28.270464+00:00。
- ev-410ace9d：HARP Definition & Meaning - Merriam-Webster；<https://www.merriam-webster.com/dictionary/harp>；采集 2026-10-21T04:39:28.270464+00:00。
- ev-a69d0310：Home - Tencent；<https://www.tencent.com/>；采集 2026-10-21T04:39:28.276988+00:00。
- ev-26070100：Tencent - Wikipedia；<https://en.wikipedia.org/wiki/Tencent>；采集 2026-10-21T04:39:28.276988+00:00。
- ev-35762055：Home - Tencent；<https://www.tencent.com.cn/zh-hk/>；采集 2026-10-21T04:39:28.276988+00:00。
- ev-2c95fa60：下载中心-腾讯会议；<https://meeting.tencent.com/download/>；采集 2026-10-21T04:39:28.276988+00:00。
- ev-3c3e1bbd：腾讯网；<https://www.qq.com/>；采集 2026-10-21T04:39:28.276988+00:00。
- ev-45591054：Tencent \| Company, WeChat, Gaming, Controversy, & Facts \| Britannica Money；<https://www.britannica.com/money/Tencent>；采集 2026-10-21T04:39:28.276988+00:00。
- ev-b41535ac：腾讯会议官方——腾讯会议 会开会；<https://meeting.tencent.com/>；采集 2026-10-21T04:39:28.276988+00:00。
- ev-7de125a0：Home \| Tencent Careers；<https://careers.tencent.com/en-us/home.html>；采集 2026-10-21T04:39:28.276988+00:00。
- ev-cac3e8b4：Tencent Holdings Limited (TCEHY) Stock Price, News, Quote & History ...；<https://finance.yahoo.com/quote/TCEHY/>；采集 2026-10-21T04:39:28.276988+00:00。
- ev-7af1d0b9：Tencent Hy；<https://hy.tencent.ai/>；采集 2026-10-21T04:39:28.276988+00:00。
### 缺失与解释边界
- 证据索引不等于机构成果全集或已核实合作关系。
- 仅覆盖本次取得的样本；空样本不代表现实中零成果，来源未覆盖年份不补零。
- 学科比较组使用请求标签，尚未逐篇核定学科；不输出跨学科或载体的统一质量榜。
- 原文位置与引用检查不等于独立语义复核；模型推断、建议和未来情景仍须复核。
- 评价目录为冻结的部分样本及授权要求，未自动应用到本次成果；缺失指标不作零分或最低等级。
- funding 关系尚无已纳入的直接依据；不表示该关系不存在。
- citation 关系尚无已纳入的直接依据；不表示该关系不存在。


## 可复核样本与对象比较
计数由结构化记录计算，仅覆盖本次取得并通过原文校验的样本；未链接版本暂按单条发表独立计数。
| 对象 | 发表记录 | 研究家族 |
| --- | ---: | ---: |
| Tencent | 1 | 1 |
| 去重汇总 | 1 | 1 |
相同成果可分别归属多个对象，合并总量取成果／家族并集，不相加各对象行。
### 同口径样本比较
2026／conference_paper；学科口径来自请求：computer science。仅比较该组已取得样本，不作科研质量排序。
| 对象 | 本组研究家族数 |
| --- | ---: |
| Tencent | 1 |
### 已纳入成果与依据
- Harp: Improving VPC Network Availability via Efficient Failure Detection and Rerouting in Tencent Cloud；日期区间 2026-05-01 至 2026-05-31（month 精度）；[citation:1]
### 缺口与解释边界
待核记录 0 项；未确立的关系：funding、citation。未取得证据不表示关系不存在。
机构署名按所选名称／别名与发表来源对照；不推出当前任职、正式协议、内部研发投入或科研质量优劣。跨载体／年份不汇成统一质量榜。
### 后续评估建议（模型判断，待复核）
- 建议下一步获取 NSDI '26 全文 PDF 与可能的 artifact evaluation 记录，以核实实验条件、基线对比与独立验证情况。 [citation:1]
