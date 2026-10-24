# 组织研究简报

对象：Microsoft Research；时间：2024–2025。

主题：以2024至2025年可取得的代表性公开论文为范围，分析Microsoft Research在数据中心网络拥塞相关方向的研究问题、技术路线、成果及可进一步验证的问题；逐项核对发表时单位，区分直接拥塞控制与相邻遥测工作；交付有界研究简报及未覆盖范围，不要求穷尽成果清单，不推断内部研发战略或仅据单篇论文推断路线转向

本次保留6个来源，其中2份PDF；范围由请求和采集记录生成。逐项核验覆盖下方研究事实，后续问题与取证缺口不计为已证实结论。

## Microsoft Research · Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic

- **发表与归属** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：该论文发表于NSDI '24（2024年4月），Wei Bai在发表时的单位标注为Microsoft Research，其余作者分别来自TU Berlin与Princeton University。 [citation:2][citation:5]

- **研究问题** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：研究问题是：交换机缓冲区要在无损RDMA与有损TCP两类流量间共享，如何既实现隔离又最大化突发吸收。 [citation:1][citation:5]

- **研究问题** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：作者分析指出两项根因：缓冲区共享依赖入口与出口两套独立且常冲突的视角，且对瞬态拥塞下的占用变化过度反应。 [citation:1][citation:5]

- **技术方法** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：Reverie采用统一入口与出口的联合接纳控制，并基于低通滤波分配缓冲，使突发队列长度在瞬态拥塞下落入缓冲上限内。 [citation:1][citation:5]

- **成果及条件** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：评估显示Reverie可同时改善RDMA与TCP的流完成时间，最高达33%。 [citation:1][citation:5]

- **成果及条件** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：在NS-3的leaf-spine仿真中，Reverie相比DT将TCP短流的99分位完成时间平均改善42.7%。 [citation:2]

- **论文中的限制** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：论文评估基于NS3仿真（256主机、25Gbps链路的leaf-spine拓扑），未报告真实硬件部署结果。 [citation:2]

- **论文中的限制** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：作者指出，针对给定交换机寻找最优参数γ仍是一个开放问题。 [citation:2]

## Microsoft Research · Enabling Silent Telemetry Data Transmission with InvisiFlow

- **发表与归属** Enabling Silent Telemetry Data Transmission with InvisiFlow：该论文发表于NSDI '25（2025年4月），Liangcheng Yu在发表时的单位同时标注University of Pennsylvania与Microsoft Research。 [citation:3][citation:4]

- **研究问题** Enabling Silent Telemetry Data Transmission with InvisiFlow：现有的遥测数据传输方法在网络重载时会显著扰动用户流量，或造成遥测数据丢失。 [citation:3][citation:6]

- **技术方法** Enabling Silent Telemetry Data Transmission with InvisiFlow：InvisiFlow不再让遥测报文总沿最短路径推送，而是利用机会式发送和拥塞梯度动态寻找空闲容量。 [citation:3][citation:6]

- **成果及条件** Enabling Silent Telemetry Data Transmission with InvisiFlow：在FatTree拓扑的高负载场景下，InvisiFlow的遥测丢包率接近零，相比Everflow、Planck等方法使用的传输方式约降低33.8倍。 [citation:3][citation:6]

- **论文中的限制** Enabling Silent Telemetry Data Transmission with InvisiFlow：论文评估由测试床实验和ns-3大规模仿真组成，未报告在真实生产数据中心部署的结果。 [citation:4]


## 后续验证建议（非已验证事实）

- Reverie的缓冲共享与低通滤波设计，能否在真实可编程交换机的硬件限制下实现，并与仿真结果一致？
- 在混合RDMA/TCP生产负载中，Reverie对PFC暂停和尾延迟的影响是否会随负载与参数γ变化而显著偏离仿真结论？
- InvisiFlow的机会式遥测发送在真实Tofino级交换机上的资源开销与对用户流量的实际影响是否与仿真一致？
- 在拥塞控制与遥测这两个方向上，Microsoft Research后续是否有2025年之后可公开获取的直接拥塞控制论文，以确认研究路线延续或转向？

## 本次取证缺口（模型说明）

- 本次收集仅覆盖2024至2025年两篇以Microsoft Research为合著单位的NSDI论文，未覆盖其他会议、期刊或arXiv来源。
- 未收集Microsoft Research在该方向上的作者团队构成、项目页面或实验室介绍等官方背景材料。
- 未获取Reverie与InvisiFlow在真实硬件或生产环境下的验证报告。
- 未系统检索2024至2025年间Microsoft Research其他拥塞控制或数据中心网络论文，因此覆盖面有界。

## 核验结果

自动来源支持：13/13 项；人工复核：未复核。模型置信度不代表人工确认。
支持状态来自模型语义判断与原文引语校验，不能保证结论为真。


## References

[1] https://www.usenix.org/conference/nsdi24/presentation/addanki-reverie — https://www.usenix.org/conference/nsdi24/presentation/addanki-reverie (paper_or_proceedings)
[2] https://www.usenix.org/conference/nsdi24/presentation/addanki-reverie (PDF) — https://www.usenix.org/system/files/nsdi24-addanki-reverie.pdf (paper_or_proceedings)
[3] https://www.usenix.org/conference/nsdi25/presentation/zhang-yinda — https://www.usenix.org/conference/nsdi25/presentation/zhang-yinda (paper_or_proceedings)
[4] https://www.usenix.org/conference/nsdi25/presentation/zhang-yinda (PDF) — https://www.usenix.org/system/files/nsdi25-zhang-yinda.pdf (paper_or_proceedings)
[5] https://www.microsoft.com/en-us/research/publication/reverie-low-pass-filter-based-switch-buffer-sharing-for-datacenters-with-rdma-and-tcp-traffic/ — https://www.microsoft.com/en-us/research/publication/reverie-low-pass-filter-based-switch-buffer-sharing-for-datacenters-with-rdma-and-tcp-traffic/ (official_document_check_entity_and_claim)
[6] https://www.microsoft.com/en-us/research/publication/enabling-silent-telemetry-data-transmission-with-invisiflow/ — https://www.microsoft.com/en-us/research/publication/enabling-silent-telemetry-data-transmission-with-invisiflow/ (official_document_check_entity_and_claim)