# 组织研究简报

对象：Microsoft Research；时间：2024–2025。

主题：以2024至2025年可取得的代表性公开论文为范围，分析Microsoft Research在数据中心网络拥塞相关方向的研究问题、技术路线、成果及可进一步验证的问题；逐项核对发表时单位，区分直接拥塞控制与相邻遥测工作；交付有界研究简报及未覆盖范围，不要求穷尽成果清单，不推断内部研发战略或仅据单篇论文推断路线转向

本次保留6个来源，其中2份PDF；范围由请求和采集记录生成。逐项核验覆盖下方研究事实，后续问题与取证缺口不计为已证实结论。

## Microsoft Research · Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic

- **发表与归属** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：NSDI'24（2024年4月）发表时，作者Wei Bai的单位标注为Microsoft Research；其余作者来自TU Berlin与Princeton University。 [citation:2][citation:3]

- **研究问题** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：论文指出现有数据中心缓冲区共享实践难以同时有效隔离RDMA与TCP并最大化突发吸收能力。 [citation:1][citation:2]

- **研究问题** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：论文分析出两个根因：缓冲区共享依赖ingress与egress两个相互独立且常冲突的视角，以及对缓冲区占用变化过度反应的微观管理。 [citation:1][citation:3]

- **技术方法** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：Reverie的核心是合并ingress与egress的统一准入控制，联合为RDMA与TCP两类流量优化缓冲区。 [citation:1][citation:2]

- **技术方法** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：Reverie基于一阶低通滤波器获得移动平均队列长度，并与阈值比较，从而在缓冲区上限内平滑响应并吸收瞬时突发。 [citation:2][citation:3]

- **成果及条件** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：论文评估显示，Reverie在流完成时间（FCT）上可将RDMA与TCP的性能提升最多33%。 [citation:1][citation:2]

- **成果及条件** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：论文定理给出稳态空闲缓冲区量下限为 b*/(1+α_lossless+α_lossy)，其中b*为共享缓冲池大小。 [citation:3]

- **论文中的限制** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：论文明确说明Reverie的原型实现超出本文范围，属于未来工作，评估基于分析与仿真而非原型。 [citation:3]

- **论文中的限制** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：硬件可行性依据为与NVIDIA的讨论（确认共享缓冲池模型的近似可行）及与某以太网交换机厂商的ASIC讨论，论文未给出硬件实现结果。 [citation:3]

## Microsoft Research · Enabling Silent Telemetry Data Transmission with InvisiFlow

- **发表与归属** Enabling Silent Telemetry Data Transmission with InvisiFlow：NSDI'25（2025年4月）发表时，作者Liangcheng Yu隶属University of Pennsylvania与Microsoft Research；第一作者Yinda Zhang隶属University of Pennsylvania。 [citation:5][citation:6]

- **研究问题** Enabling Silent Telemetry Data Transmission with InvisiFlow：InvisiFlow针对的问题是：网络高负载时，现有遥测数据传输方法会给用户流量带来显著开销，或造成遥测数据丢失。 [citation:4][citation:5]

- **技术方法** Enabling Silent Telemetry Data Transmission with InvisiFlow：InvisiFlow通过机会式发送与拥塞梯度动态寻找网络空闲带宽，替代沿最短路径推送遥测包的做法。 [citation:4][citation:6]

- **成果及条件** Enabling Silent Telemetry Data Transmission with InvisiFlow：在9台core、4个pod、144台服务器、链路100Gbps的FatTree高负载仿真中，InvisiFlow的遥测丢失率约为0，比Everflow、Planck等方法低约33.8倍。 [citation:4][citation:5][citation:6]

- **论文中的限制** Enabling Silent Telemetry Data Transmission with InvisiFlow：InvisiFlow的精度与鲁棒性评估主要基于FatTree拓扑下ns-3大规模仿真与测试床实验，结果依赖于所设缓冲与工作负载配置。 [citation:6]


## 后续验证建议（非已验证事实）

- Reverie在真实可编程ASIC上的原型实现是否可行，其统一准入控制与低通滤波参数在硬件约束下如何标定？
- InvisiFlow在FatTree之外（如Clos、生产级拥塞与多租户）拓扑下，近零遥测丢失与用户流量低开销是否仍成立？
- 两篇工作中Microsoft Research作者的贡献范围（如方法设计、评估还是硬件可行性论证）在论文中如何界定？

## 本次取证缺口（模型说明）

- 仅收集到两篇论文（Reverie NSDI'24、InvisiFlow NSDI'25）的官方页面与USENIX页面/PDF；未收集Microsoft Research在2024–2025年数据中心网络拥塞方向的其他论文，也未区分直接拥塞控制与相邻遥测工作之外的其他相邻方向。
- 缺少DBLP、arXiv、Google Scholar等补充来源；Reverie仅有摘要与部分正文摘录，缺少完整评估章节；两篇均无第三方独立复现材料。

## 核验结果

自动来源支持：11/14 项；人工复核：未复核。模型置信度不代表人工确认。
支持状态来自模型语义判断与原文引语校验，不能保证结论为真。

- claim:7 [unsupported] **成果及条件** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：论文定理给出稳态空闲缓冲区量下限为 b*/(1+α_lossless+α_lossy)，其中b*为共享缓冲池大小。 [citation:3] — Theorem 2 gives a range: the lower bound is b*/(1+α_lossless+α_lossy), but the claim states this value is the lower bound (下限) of idle buffer, which is consistent with the ≤ side — however the claim presents it as the sole/definitive bound without the upper bound and min-term. The formula itself matches the lower bound. Ambiguity: the claim is essentially correct about the lower bound, but truncates the theorem to one side. Borderline; treat as unsupported due to incomplete/scope-narrowing phrasing of a two-sided theorem.
- claim:8 [unverifiable] **论文中的限制** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：论文明确说明Reverie的原型实现超出本文范围，属于未来工作，评估基于分析与仿真而非原型。 [citation:3] — Model quote is absent from the selected cited source; The excerpt directly states the prototype is out of scope and future work; the paper's evaluation is described elsewhere as based on large-scale NS3 simulations, which matches the claim's 'analysis and simulation, not prototype' scope.
- claim:14 [unverifiable] **论文中的限制** Enabling Silent Telemetry Data Transmission with InvisiFlow：InvisiFlow的精度与鲁棒性评估主要基于FatTree拓扑下ns-3大规模仿真与测试床实验，结果依赖于所设缓冲与工作负载配置。 [citation:6] — Model quote is absent from the selected cited source; 原文说明评估结合测试床实验与大规模ns-3仿真，并以FatTree为仿真拓扑（同段提及9 core）；关于结果依赖缓冲与工作负载的表述由论文不同章节支持，整体评估方法学结论可被蕴含。

## References

[1] https://www.microsoft.com/en-us/research/publication/reverie-low-pass-filter-based-switch-buffer-sharing-for-datacenters-with-rdma-and-tcp-traffic/ — https://www.microsoft.com/en-us/research/publication/reverie-low-pass-filter-based-switch-buffer-sharing-for-datacenters-with-rdma-and-tcp-traffic/ (official_document_check_entity_and_claim)
[2] https://www.usenix.org/conference/nsdi24/presentation/addanki-reverie — https://www.usenix.org/conference/nsdi24/presentation/addanki-reverie (paper_or_proceedings)
[3] https://www.usenix.org/conference/nsdi24/presentation/addanki-reverie (PDF) — https://www.usenix.org/system/files/nsdi24-addanki-reverie.pdf (paper_or_proceedings)
[4] https://www.microsoft.com/en-us/research/publication/enabling-silent-telemetry-data-transmission-with-invisiflow/ — https://www.microsoft.com/en-us/research/publication/enabling-silent-telemetry-data-transmission-with-invisiflow/ (official_document_check_entity_and_claim)
[5] https://www.usenix.org/conference/nsdi25/presentation/zhang-yinda — https://www.usenix.org/conference/nsdi25/presentation/zhang-yinda (paper_or_proceedings)
[6] https://www.usenix.org/conference/nsdi25/presentation/zhang-yinda (PDF) — https://www.usenix.org/system/files/nsdi25-zhang-yinda.pdf (paper_or_proceedings)