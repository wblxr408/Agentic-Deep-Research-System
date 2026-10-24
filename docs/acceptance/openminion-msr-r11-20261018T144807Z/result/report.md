# 组织研究简报

对象：Microsoft Research；时间：2024–2025。

主题：以2024至2025年可取得的代表性公开论文为范围，分析Microsoft Research在数据中心网络拥塞相关方向的研究问题、技术路线、成果及可进一步验证的问题；逐项核对发表时单位，区分直接拥塞控制与相邻遥测工作；交付有界研究简报及未覆盖范围，不要求穷尽成果清单，不推断内部研发战略或仅据单篇论文推断路线转向

本次保留6个来源，其中2份PDF；范围由请求和采集记录生成。逐项核验覆盖下方研究事实，后续问题与取证缺口不计为已证实结论。

## Microsoft Research · Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic

- **发表与归属** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：Reverie 作者为 TU Berlin 的 Vamsi Addanki 与 Stefan Schmid、Microsoft Research 的 Wei Bai、Princeton University 的 Maria Apostolaki；微软仅为四位作者之一。 [citation:1][citation:2]

- **研究问题** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：Reverie 针对数据中心交换机缓冲区在无损耗 RDMA（RoCE）与有损耗 TCP/DCTCP 之间的共享：现行实践难以同时实现两类流量隔离与最大化突发吸收。 [citation:1][citation:2]

- **研究问题** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：Reverie 将根因归为两点：RDMA 与 TCP 共享依赖入口与出口两套独立且常冲突的缓冲区视角；共享方案对占用变化过度反应、微观管理。 [citation:1][citation:2][citation:3]

- **技术方法** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：Reverie 的核心是统一入口与出口的准入控制，为 RDMA 与 TCP 联合优化缓冲区，并以低通滤波器分配缓冲、在瞬时拥塞下吸收突发队列。 [citation:1][citation:2][citation:3]

- **成果及条件** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：按论文评估，以流完成时间为指标，Reverie 可同时把 RDMA 与 TCP 的性能提升最多 33%。 [citation:1][citation:2]

- **论文中的限制** Reverie: Low Pass Filter-Based Switch Buffer Sharing for Datacenters with RDMA and TCP Traffic：Reverie 尚未提供原型实现并列为未来工作；定理表明其在稳态会保留少量空闲缓冲；与交换机 ASIC 厂商合作落地尚属未来工作。 [citation:3]

## Microsoft Research · Enabling Silent Telemetry Data Transmission with InvisiFlow

- **发表与归属** Enabling Silent Telemetry Data Transmission with InvisiFlow：InvisiFlow 作者来自 University of Pennsylvania（Yinda Zhang、Vincent Liu）、宾大与 Microsoft Research 双属的 Liangcheng Yu、Politecnico di Milano 与 Queen Mary（Gianni Antichi）、UCL（Ran Ben Basat）。 [citation:5][citation:6]

- **研究问题** Enabling Silent Telemetry Data Transmission with InvisiFlow：InvisiFlow 针对遥测数据回传：既有传输方法对用户流量造成显著开销，或在网络重载时丢失遥测数据，影响流量工程、路径追踪等应用。 [citation:4][citation:5]

- **技术方法** Enabling Silent Telemetry Data Transmission with InvisiFlow：InvisiFlow 是一种静默采集遥测的通信基底，区别于始终沿最短路径推送遥测包，它借助机会式发送与拥塞梯度动态寻找空闲网络容量。 [citation:4][citation:5]

- **成果及条件** Enabling Silent Telemetry Data Transmission with InvisiFlow：在 FatTree 高负载场景下，InvisiFlow 遥测丢失率接近零，相比 Everflow、Planck 所用先进传输方式约低 33.8 倍。 [citation:4][citation:5]

- **成果及条件** Enabling Silent Telemetry Data Transmission with InvisiFlow：在可编程交换机原型上，InvisiFlow 额外资源开销约为 2.08% 额外网关与 0.78% 额外 VLIW 动作，评测结合测试床实验与大规模 ns-3 仿真。 [citation:6]


## 后续验证建议（非已验证事实）

- Reverie 的 33% FCT 提升是在何种拓扑、负载与缓冲区规模下测得，是否覆盖混合 RDMA/TCP 的实际生产缓存配置？
- InvisiFlow 的拥塞梯度利用是否与 DCTCP 等并发用户流量产生反馈耦合，在超高负载或非 FatTree 拓扑下是否仍近零丢失？
- 两篇论文中 Microsoft Research 参与的具体贡献边界（作者分工）未有公开材料说明，难以判断微软的实际技术投入。

## 本次取证缺口（模型说明）

- 仅覆盖两篇代表性论文（NSDI'24 Reverie、NSDI'25 InvisiFlow），未检索 2024–2025 年微软在拥塞控制（如传输层 CC、PFC/ECN 调优）方向的其它公开成果。
- 未获取 DBLP、Google Scholar 等来源做作者单位与发表年份的交叉核对。
- InvisiFlow 属遥测传输的相邻工作，并非直接的拥塞控制协议；本简报未补充其拥塞梯度机制细节。
- 未覆盖非 USENIX 出版渠道（如 ACM SIGCOMM、IEEE）中微软相关论文。
- 未评估论文限制的可验证性方案与复现实验条件。
- 缺少对 2024–2025 年微软数据中心拥塞方向成果的系统性检索（DBLP/Google Scholar 未使用）。
- 缺少更广泛论文集合的作者单位逐项核对记录。
- 无法推断微软内部研发战略或路线走向，任务未要求亦未提供依据。

## 核验结果

自动来源支持：10/11 项；人工复核：未复核。模型置信度不代表人工确认。
支持状态来自模型语义判断与原文引语校验，不能保证结论为真。

- claim:11 [unverifiable] **成果及条件** Enabling Silent Telemetry Data Transmission with InvisiFlow：在可编程交换机原型上，InvisiFlow 额外资源开销约为 2.08% 额外网关与 0.78% 额外 VLIW 动作，评测结合测试床实验与大规模 ns-3 仿真。 [citation:6] — Model quote is absent from the selected cited source; The excerpt gives exactly 2.08% additional gateways and 0.78% additional VLIW actions for the hardware prototype, and states evaluation combines testbed experiments and large-scale ns-3 simulations. All figures and conditions are entailed.

## References

[1] https://www.microsoft.com/en-us/research/publication/reverie-low-pass-filter-based-switch-buffer-sharing-for-datacenters-with-rdma-and-tcp-traffic/ — https://www.microsoft.com/en-us/research/publication/reverie-low-pass-filter-based-switch-buffer-sharing-for-datacenters-with-rdma-and-tcp-traffic/ (official_document_check_entity_and_claim)
[2] https://www.usenix.org/conference/nsdi24/presentation/addanki-reverie — https://www.usenix.org/conference/nsdi24/presentation/addanki-reverie (paper_or_proceedings)
[3] https://www.usenix.org/conference/nsdi24/presentation/addanki-reverie (PDF) — https://www.usenix.org/system/files/nsdi24-addanki-reverie.pdf (paper_or_proceedings)
[4] https://www.microsoft.com/en-us/research/publication/enabling-silent-telemetry-data-transmission-with-invisiflow/ — https://www.microsoft.com/en-us/research/publication/enabling-silent-telemetry-data-transmission-with-invisiflow/ (official_document_check_entity_and_claim)
[5] https://www.usenix.org/conference/nsdi25/presentation/zhang-yinda — https://www.usenix.org/conference/nsdi25/presentation/zhang-yinda (paper_or_proceedings)
[6] https://www.usenix.org/conference/nsdi25/presentation/zhang-yinda (PDF) — https://www.usenix.org/system/files/nsdi25-zhang-yinda.pdf (paper_or_proceedings)