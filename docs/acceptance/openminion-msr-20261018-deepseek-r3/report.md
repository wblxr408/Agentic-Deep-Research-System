# 2024–2025 年数据中心网络拥塞控制：Microsoft Research 相关公开研究（基于部分证据的评估）

**证据充分性说明：** 本次检索仅获取到 3 份可用的一手/官方页面内容（Reverie 论文页、Microsoft NDSI 2024 博客、Microsoft Networking & Infrastructure Group 出版物列表），其中出版物列表页面内容被截断且主要显示 2017–2018 年条目，未能覆盖 2024–2025 年完整清单。因此下文仅能就**已核实**的公开成果展开，其余部分明确标注为“公开证据不足”。不涉及、也不推断任何内部研发战略。

## 1. 已核实的 2024–2025 年公开成果

**Reverie：面向 RDMA 与 TCP 混合流量的低通滤波式交换机缓冲区共享（NSDI '24，2024 年 4 月）**

- **作者与来源：** Vamsi Addanki（TU Berlin）、Wei Bai（Microsoft Research）、Stefan Schmid（TU Berlin）、Maria Apostolaki（Princeton University）[citation:1][citation:4]。
- **研究问题：** 数据中心交换机缓冲区需要同时承载两类流量——传统应用使用容忍丢包的传输协议（如 DCTCP），而较新应用使用 RDMA 等对丢包/拥塞信号反应截然不同的协议。多类流量共享同一缓冲区时，现有共享方案难以兼顾不同丢包容忍度与拥塞信号响应特性，导致隔离性与利用率难以两全 [citation:1][citation:4]。
- **技术路线：** 采用**基于低通滤波（low-pass filter）的缓冲区共享**机制来分配/调度共享缓冲区，以在异构传输（RDMA vs. TCP/DCTCP）共存时提供更合适的拥塞信号与缓冲区使用行为 [citation:1]。
- **成果形式：** 经 NSDI '24 同行评审录用并发表（2024 年 4 月）[citation:1][citation:4]。

**Microsoft at NDSI 2024（官方博客）**

- 博客汇总了 Microsoft 在 networked systems 方向的“发现与实现”，涉及资源管理与服务保障类工作，例如面向 Kubernetes 的 CPU 节省与 SLO 违规减少的方案，以及 5G RAN 切片中的应用级服务保障（Zipper）[citation:2]。
- **与拥塞控制的关联限度：** 这些条目属于更广义的网络系统/资源管理范畴，**并非直接的数据中心拥塞控制算法研究**。将其视为拥塞控制成果属于过度延伸，故此处仅作为同期研究背景记录，不纳入拥塞控制技术路线归纳。

## 2. 技术路线归纳（仅限已核实内容）

在已核实范围内，Microsoft Research 参与的 2024 年公开工作体现的路线是：**从“端到端拥塞控制算法”转向“交换机缓冲区管理与拥塞信号设计”**——即在网络设备侧处理异构传输共存问题（RDMA 与 TCP/DCTCP 混跑），用信号处理手段（低通滤波）改善共享缓冲区下的拥塞反馈质量 [citation:1][citation:4]。这与纯端侧算法（如 DCQCN 类）形成互补视角。

## 3. 尚未解决的问题（基于公开材料可识别的方向）

- **异构传输共存的公平性与隔离性：** RDMA 与 TCP 对丢包/ECN 的反应差异，使得在同一缓冲区中同时满足低延迟、高吞吐与公平性仍是开放问题（Reverie 正是针对该矛盾提出）[citation:1][citation:4]。
- **缓冲区共享策略在不同拥塞信号机制下的通用性：** 公开摘要未给出跨场景（不同交换机、不同负载）的普适性结论，属待验证/待解决问题。
- **证据层面的缺口：** 出版物列表页仅显示至 2018 年条目，**无法据此确认 Microsoft Research 在 2024–2025 年是否还有其它拥塞控制相关论文**，因此“完整成果清单”与“系统性未解决问题”在本次证据下无法给出。

## 4. 结论与局限

- **可确证：** Microsoft Research（Wei Bai）参与了 NSDI '24 的 Reverie 工作，聚焦 RDMA/TCP 混合流量下的交换机缓冲区共享与拥塞信号设计（2024 年 4 月发表）[citation:1][citation:4]。
- **不可确证：** 2024–2025 年 Microsoft Research 在数据中心拥塞控制方向的完整论文清单、系统性技术路线图与已明确的未解决问题集合；现有官方页面证据被截断且时效不足。
- **未做推断：** 本文未对 Microsoft 内部研发战略、路线优先级或未公开项目作任何推断。

<citation_notes>
[citation:1] Microsoft Research 出版物页 — Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic（NSDI'24, April 2024），URL 见 seed_urls 第 1 项。
[citation:2] Microsoft Research 博客 — Microsoft at NDSI 2024: Discoveries and Implementations in Networked Systems（含 CPU 节省/SLO、Zipper 5G RAN 切片等条目）。
[citation:3] Microsoft Research Networking & Infrastructure Group 出版物列表页（内容截断，主要显示 2017–2018 年条目，未覆盖 2024–2025）。
[citation:4] USENIX NSDI '24 会议论文页 — Reverie（作者：Vamsi Addanki, TU Berlin; Wei Bai, Microsoft Research; Stefan Schmid, TU Berlin; Maria Apostolaki, Princeton University）。
</citation_notes>

## 核验结果

自动来源支持：3/23 项；人工复核：未复核。模型置信度不代表人工确认。
支持状态来自模型语义判断与原文引语校验，不能保证结论为真。

- claim:1 [missing_citation] **证据充分性说明：** 本次检索仅获取到 3 份可用的一手/官方页面内容（Reverie 论文页、Microsoft NDSI 2024 博客、Microsoft Networking & Infrastructure Group 出版物列表），其中出版物列表页面内容被截断且主要显示 2017–2018 年条目，未能覆盖 2024–2025 年完整清单。因此下文仅能就**已核实**的公开成果展开，其余部分明确标注为“公开证据不足”。不涉及、也不推断任何内部研发战略。 — Awaiting source support judgement
- claim:2 [missing_citation] **Reverie：面向 RDMA 与 TCP 混合流量的低通滤波式交换机缓冲区共享（NSDI '24，2024 年 4 月）** — Awaiting source support judgement
- claim:4 [unverifiable] **研究问题：** 数据中心交换机缓冲区需要同时承载两类流量——传统应用使用容忍丢包的传输协议（如 DCTCP），而较新应用使用 RDMA 等对丢包/拥塞信号反应截然不同的协议。多类流量共享同一缓冲区时，现有共享方案难以兼顾不同丢包容忍度与拥塞信号响应特性，导致隔离性与利用率难以两全 [citation:1][citation:4]。 — Model quote is absent from the selected cited source; The excerpt states the coexistence of DCTCP (loss-tolerant) and RDMA (lossless) traffic classes and that current buffer-sharing practices fundamentally limit both isolation and burst absorption maximization, which matches the claim's problem framing. The word 'utilization' is a loose paraphrase of 'maximizing burst absorption', but the core tension (isolation vs. buffer efficiency) is entailed.
- claim:5 [missing_citation] **技术路线：** 采用**基于低通滤波（low-pass filter）的缓冲区共享**机制来分配/调度共享缓冲区，以在异构传输（RDMA vs. — Awaiting source support judgement
- claim:6 [unsupported] TCP/DCTCP）共存时提供更合适的拥塞信号与缓冲区使用行为 [citation:1]。 — The excerpt describes the coexistence of TCP/DCTCP and RDMA and the limitations of current buffer sharing, but it does not state that any approach provides 'more appropriate congestion signals and buffer usage behavior' for TCP/DCTCP coexistence. A related topic is not enough to entail the claim.
- claim:8 [missing_citation] **Microsoft at NDSI 2024（官方博客）** — Awaiting source support judgement
- claim:9 [unsupported] 博客汇总了 Microsoft 在 networked systems 方向的“发现与实现”，涉及资源管理与服务保障类工作，例如面向 Kubernetes 的 CPU 节省与 SLO 违规减少的方案，以及 5G RAN 切片中的应用级服务保障（Zipper）[citation:2]。 — The excerpt supports the CPU-savings/SLO-violation and Zipper/5G RAN slicing components, but it does not show that the blog is a Microsoft 'discoveries and implementations in networked systems' roundup covering resource management and service assurance as a theme. The overarching framing is not entailed by this single excerpt (the title appears only in the source title, not the quote).
- claim:10 [missing_citation] **与拥塞控制的关联限度：** 这些条目属于更广义的网络系统/资源管理范畴，**并非直接的数据中心拥塞控制算法研究**。将其视为拥塞控制成果属于过度延伸，故此处仅作为同期研究背景记录，不纳入拥塞控制技术路线归纳。 — Awaiting source support judgement
- claim:11 [unsupported] 在已核实范围内，Microsoft Research 参与的 2024 年公开工作体现的路线是：**从“端到端拥塞控制算法”转向“交换机缓冲区管理与拥塞信号设计”**——即在网络设备侧处理异构传输共存问题（RDMA 与 TCP/DCTCP 混跑），用信号处理手段（低通滤波）改善共享缓冲区下的拥塞反馈质量 [citation:1][citation:4]。这与纯端侧算法（如 DCQCN 类）形成互补视角。 — The excerpts establish that this 2024 MSR-affiliated paper works on switch buffer sharing and low-pass-filter-based buffer allocation for mixed RDMA/TCP traffic — the device-side, signal-processing part checks out. But the claim's core assertion of a shift 'from end-to-end congestion control algorithms to switch buffer management' (a directional/trend statement) is nowhere entailed by the sources; they describe one paper, not a programmatic redirection. The 'complementary to DCQCN-style end-side algorithms' framing is also the author's synthesis, absent from the text.
- claim:12 [unverifiable] **异构传输共存的公平性与隔离性：** RDMA 与 TCP 对丢包/ECN 的反应差异，使得在同一缓冲区中同时满足低延迟、高吞吐与公平性仍是开放问题（Reverie 正是针对该矛盾提出）[citation:1][citation:4]。 — Model quote is absent from the selected cited source; The excerpt does state that RDMA and TCP have differing loss tolerance and reaction to congestion signals, that isolating them while maximizing burst absorption is fundamentally hard under current practice, and that Reverie targets this conflict (providing isolation plus burst absorption). Caveat: the specific triad 'low latency, high throughput, fairness' is not verbatim in the source — it is the claim's paraphrase of isolation/absorption — and 'open problem' is an inference, so support is strong on substance but not word-for-word on every term.
- claim:13 [missing_citation] **缓冲区共享策略在不同拥塞信号机制下的通用性：** 公开摘要未给出跨场景（不同交换机、不同负载）的普适性结论，属待验证/待解决问题。 — Awaiting source support judgement
- claim:14 [missing_citation] **证据层面的缺口：** 出版物列表页仅显示至 2018 年条目，**无法据此确认 Microsoft Research 在 2024–2025 年是否还有其它拥塞控制相关论文**，因此“完整成果清单”与“系统性未解决问题”在本次证据下无法给出。 — Awaiting source support judgement
- claim:15 [unverifiable] **可确证：** Microsoft Research（Wei Bai）参与了 NSDI '24 的 Reverie 工作，聚焦 RDMA/TCP 混合流量下的交换机缓冲区共享与拥塞信号设计（2024 年 4 月发表）[citation:1][citation:4]。 — Model quote is absent from the selected cited source; Affiliation listing confirms Wei Bai of Microsoft Research as a co-author; source:1 confirms NSDI'24, April 2024, and the title confirms RDMA/TCP mixed-traffic switch buffer sharing and low-pass-filter congestion signaling. All asserted elements (participant, venue, topic, date) are entailed.
- claim:16 [missing_citation] **不可确证：** 2024–2025 年 Microsoft Research 在数据中心拥塞控制方向的完整论文清单、系统性技术路线图与已明确的未解决问题集合；现有官方页面证据被截断且时效不足。 — Awaiting source support judgement
- claim:17 [missing_citation] **未做推断：** 本文未对 Microsoft 内部研发战略、路线优先级或未公开项目作任何推断。 — Awaiting source support judgement
- claim:18 [missing_citation] <citation_notes> — Awaiting source support judgement
- claim:20 [unsupported] [citation:2] Microsoft Research 博客 — Microsoft at NDSI 2024: Discoveries and Implementations in Networked Systems（含 CPU 节省/SLO、Zipper 5G RAN 切片等条目）。 — The excerpt confirms only that this is an MSR blog about Microsoft at NSDI'24 (the blog title itself spells 'NDSI', matching the claim's odd spelling). It does not contain the specific items the claim attributes — CPU savings/SLO, Zipper 5G RAN slicing — since the quote cuts off before any paper list. The parenthetical content list is unverified by the supplied excerpt.
- claim:21 [not_checked] [citation:3] Microsoft Research Networking & Infrastructure Group 出版物列表页（内容截断，主要显示 2017–2018 年条目，未覆盖 2024–2025）。 — Not checked
- claim:22 [not_checked] [citation:4] USENIX NSDI '24 会议论文页 — Reverie（作者：Vamsi Addanki, TU Berlin; Wei Bai, Microsoft Research; Stefan Schmid, TU Berlin; Maria Apostolaki, Princeton University）。 — Not checked
- claim:23 [not_checked] </citation_notes> — Not checked

## References

[1] https://www.microsoft.com/en-us/research/publication/reverie-low-pass-filter-based-switch-buffer-sharing-for-datacenters-with-rdma-and-tcp-traffic/ — https://www.microsoft.com/en-us/research/publication/reverie-low-pass-filter-based-switch-buffer-sharing-for-datacenters-with-rdma-and-tcp-traffic/
[2] https://www.microsoft.com/en-us/research/blog/microsoft-at-ndsi-2024-discoveries-and-implementations-in-networked-systems/ — https://www.microsoft.com/en-us/research/blog/microsoft-at-ndsi-2024-discoveries-and-implementations-in-networked-systems/
[3] https://www.microsoft.com/en-us/research/group/networking-infrastructure-group/publications/ — https://www.microsoft.com/en-us/research/group/networking-infrastructure-group/publications/
[4] https://www.usenix.org/conference/nsdi24/presentation/addanki-reverie — https://www.usenix.org/conference/nsdi24/presentation/addanki-reverie