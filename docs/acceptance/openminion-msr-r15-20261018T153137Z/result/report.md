# 组织研究简报

对象：Microsoft Research；时间：2024–2025。

主题：以2024至2025年可取得的代表性公开论文为范围，分析Microsoft Research在数据中心网络拥塞相关方向的研究问题、技术路线、成果及可进一步验证的问题；逐项核对发表时单位，区分直接拥塞控制与相邻遥测工作；交付有界研究简报及未覆盖范围，不要求穷尽成果清单，不推断内部研发战略或仅据单篇论文推断路线转向

本次保留6个来源，其中2份PDF；范围由请求和采集记录生成。逐项核验覆盖下方研究事实，后续问题与取证缺口不计为已证实结论。

## Microsoft Research · Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic

- **发表与归属** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：该论文发表于NSDI 2024（2024年4月16–18日，Santa Clara），作者中仅有Wei Bai标注发表时单位为Microsoft Research，其余作者分别隶属TU Berlin与Princeton University。 [citation:1][citation:2]

- **研究问题** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：论文指出，在RDMA与TCP混合流量下，现有交换机缓冲区共享做法无法同时实现RDMA与TCP的有效隔离和突发吸收最大化。 [citation:1][citation:2]

- **研究问题** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：作者将上述冲突归因于两点：RDMA与TCP的缓冲区共享依赖入口与出口两套相互独立且常冲突的缓冲视图；共享方案对缓冲占用变化过度反应。 [citation:2]

- **技术方法** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：Reverie的核心是统一入口与出口的准入控制，联合优化RDMA与TCP两类流量的缓冲区分配，并据低通滤波分配缓冲以在缓冲上限内吸收瞬时拥塞的突发队列。 [citation:1][citation:2]

- **成果及条件** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：论文报告，Reverie可在流完成时间上将RDMA与TCP的性能提升最高约33%（作者自报评估结果）。 [citation:1][citation:5]

- **成果及条件** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：在NS-3仿真（256主机leaf-spine、25Gbps链路、websearch背景流量与incast流量）中，Reverie相对DT最多将TCP incast性能提升约46.8%，相对ABM最多约2.1%。 [citation:2]

- **论文中的限制** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：论文报告，γ=0.999时incast流平均FCT随γ增大持续下降，而γ=0.999999（接近1）时平均FCT反升9%，说明极端γ取值会损害性能。 [citation:2]

- **论文中的限制** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：作者指出，只要避开容易被识别的极端γ取值，就无需为Reverie寻找最优γ值，未将其列为开放性待解问题。 [citation:2]

## Microsoft Research · Enabling Silent Telemetry Data Transmission with InvisiFlow

- **发表与归属** Enabling Silent Telemetry Data Transmission with InvisiFlow：该论文发表于NSDI 2025（2025年4月28–30日，Philadelphia），作者中仅有Liangcheng Yu标注University of Pennsylvania与Microsoft Research双隶属，其余作者隶属UPenn、Politecnico di Milano、QMUL与UCL。 [citation:3][citation:4]

- **研究问题** Enabling Silent Telemetry Data Transmission with InvisiFlow：论文验证，网络高负载时现有遥测数据传输方法会给用户流量带来显著开销，并造成遥测数据丢失；这属于与拥塞控制相邻的遥测传输问题。 [citation:3][citation:4]

- **技术方法** Enabling Silent Telemetry Data Transmission with InvisiFlow：InvisiFlow不再像既有系统那样沿最短路径推送遥测包；它借助机会式发送与拥塞梯度动态寻找空闲网络容量，以同时降低遥测丢失率与对用户流量的开销。 [citation:3][citation:4]

- **成果及条件** Enabling Silent Telemetry Data Transmission with InvisiFlow：在FatTree拓扑、70%负载下，InvisiFlow缺失路径比例比低优先级UDP与拉取式基线分别低约33.8倍与36.3倍。 [citation:4]

- **成果及条件** Enabling Silent Telemetry Data Transmission with InvisiFlow：在负载不均衡场景下，InvisiFlow即使负载达80%仍保持零遥测丢失率，而低优先级UDP与拉取式方法的丢失率随之上升。 [citation:4]

- **论文中的限制** Enabling Silent Telemetry Data Transmission with InvisiFlow：原型中每个遥测数据包需保持较小（约小于160B）以适应流水线寄存器限制，较大消息需逐跳分片；交付保证与目的地数量扩展被作者列为未来工作。 [citation:4]


## 后续验证建议（非已验证事实）

- Reverie报告的性能提升主要来自NS-3仿真（leaf-spine、websearch与incast流量）；是否有可获得的硬件或生产网络评估证据，以核实这些增益的适用范围？
- 论文摘要称InvisiFlow较Everflow与Planck等方法约33.8倍更低丢失，正文报告70%负载下相对低优先级UDP与拉取式基线分别为33.8倍和36.3倍；Everflow/Planck对应的具体基线与负载条件应如何逐项核对？
- Reverie默认交换机支持PFC的部署条件在真实多租户数据中心中的可行性如何（含PFC死锁与公平性风险），公开材料是否给出相应评估？
- InvisiFlow的小包限制（约小于160B、逐跳分片）在真实可编程交换机与多目的地遥测场景下的可扩展性如何，是否存在公开的原型验证？

## 本次取证缺口（模型说明）

- 采集源集中在USENIX官方论文页/USENIX会议论文与Microsoft Research官方页面，缺少DBLP、arXiv、Google Scholar等来源的独立元数据核对。
- 仅覆盖两篇代表性论文（NSDI 2024、NSDI 2025），未覆盖2024–2025年Microsoft Research在拥塞控制方向的其它公开工作。
- 未取得硬件测试床或生产部署评估的原文证据，结果均来自论文自报的仿真/原型评估。
- 未收集作者以外的机构归属、资助与数据集/代码公开情况，无法据此判断协作与可复现条件。

## 核验结果

自动来源支持：11/14 项；人工复核：未复核。模型置信度不代表人工确认。
支持状态来自模型语义判断与原文引语校验，不能保证结论为真。

- claim:1 [unverifiable] **发表与归属** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：该论文发表于NSDI 2024（2024年4月16–18日，Santa Clara），作者中仅有Wei Bai标注发表时单位为Microsoft Research，其余作者分别隶属TU Berlin与Princeton University。 [citation:1][citation:2] — Verification unavailable: AgentOutputValidationError
- claim:2 [unverifiable] **研究问题** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：论文指出，在RDMA与TCP混合流量下，现有交换机缓冲区共享做法无法同时实现RDMA与TCP的有效隔离和突发吸收最大化。 [citation:1][citation:2] — Verification unavailable: AgentOutputValidationError
- claim:10 [unverifiable] **研究问题** Enabling Silent Telemetry Data Transmission with InvisiFlow：论文验证，网络高负载时现有遥测数据传输方法会给用户流量带来显著开销，并造成遥测数据丢失；这属于与拥塞控制相邻的遥测传输问题。 [citation:3][citation:4] — Model quote is absent from the selected cited source; The abstract states prior work observed and the authors validate that existing telemetry transmission methods can cause significant user-traffic overhead and/or telemetry loss, especially under heavy network load. The paper frames this as transmission for telemetry data coexisting with user traffic/congestion, supporting the 'adjacent to congestion control' characterization as a reasonable scope description.

## References

[1] https://www.usenix.org/conference/nsdi24/presentation/addanki-reverie — https://www.usenix.org/conference/nsdi24/presentation/addanki-reverie (paper_or_proceedings)
[2] https://www.usenix.org/conference/nsdi24/presentation/addanki-reverie (PDF) — https://www.usenix.org/system/files/nsdi24-addanki-reverie.pdf (paper_or_proceedings)
[3] https://www.usenix.org/conference/nsdi25/presentation/zhang-yinda — https://www.usenix.org/conference/nsdi25/presentation/zhang-yinda (paper_or_proceedings)
[4] https://www.usenix.org/conference/nsdi25/presentation/zhang-yinda (PDF) — https://www.usenix.org/system/files/nsdi25-zhang-yinda.pdf (paper_or_proceedings)
[5] https://www.microsoft.com/en-us/research/publication/reverie-low-pass-filter-based-switch-buffer-sharing-for-datacenters-with-rdma-and-tcp-traffic/ — https://www.microsoft.com/en-us/research/publication/reverie-low-pass-filter-based-switch-buffer-sharing-for-datacenters-with-rdma-and-tcp-traffic/ (official_document_check_entity_and_claim)
[6] https://www.microsoft.com/en-us/research/publication/enabling-silent-telemetry-data-transmission-with-invisiflow/ — https://www.microsoft.com/en-us/research/publication/enabling-silent-telemetry-data-transmission-with-invisiflow/ (official_document_check_entity_and_claim)