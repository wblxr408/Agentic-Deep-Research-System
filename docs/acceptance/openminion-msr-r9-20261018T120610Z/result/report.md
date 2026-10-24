## Microsoft Research 数据中心网络拥塞相关研究简报（2024–2025）

### 一、范围与方法说明

本简报仅基于本次检索到并已核对来源的公开材料，覆盖 2024–2025 年两篇代表性论文：Reverie（NSDI '24）与 InvisiFlow（NSDI '25）。两篇论文均可在 Microsoft Research 官方出版物页面与 USENIX 会议页面双向核对。[citation:1][citation:2][citation:4][citation:5]

### 二、逐项核对发表时单位

Reverie 作者为 Vamsi Addanki（TU Berlin）、Wei Bai（Microsoft Research）、Stefan Schmid（TU Berlin）、Maria Apostolaki（Princeton University）。即微软方面仅 Wei Bai 一人署名 Microsoft Research。[citation:2][citation:3]

InvisiFlow 作者为 Yinda Zhang（UPenn）、Liangcheng Yu（UPenn 与 Microsoft Research 双署名）、Gianni Antichi（Politecnico di Milano / QMUL）、Ran Ben Basat（UCL）、Vincent Liu（UPenn）。微软方面仅 Liangcheng Yu 以双署名身份参与。[citation:5][citation:6]

两篇均为多机构合作成果，微软为参与方之一，并非全部由微软内部完成；这一区分对判断“微软研发主体性”至关重要。[citation:2][citation:5]

### 三、直接拥塞控制方向：Reverie

Reverie 针对的问题层次是交换机缓冲区共享（buffer sharing），而非端到端传输协议本身。论文指出，数据中心交换机缓冲区被容忍丢包的 TCP/DCTCP 类流量与要求无损的 RDMA（RoCE）类流量共同使用，而现有共享实践在“隔离 RDMA 与 TCP”与“最大化突发吸收”之间存在根本性冲突。[citation:1][citation:2]

论文归纳出两个根因：其一，RDMA 与 TCP 的缓冲区共享依赖入口与出口两个独立且常相互冲突的缓冲区视角；其二，共享方案对缓冲区占用变化过度微管理，在瞬态拥塞时反应过度。[citation:1][citation:3]

技术路线是统一（consolidated ingress/egress）接纳控制，联合优化两类流量的缓冲区分配，并基于低通滤波器分配缓冲区，使平均队列长度较瞬时队列长度更晚触达阈值，从而在缓冲上限内吸收瞬态突发。[citation:1][citation:2]

关于分配行为，Reverie 按 1/(1+α) 比例分配共享缓冲区，类别单独使用时获得更多缓冲；定理 2 表明稳态下会保留少量空闲缓冲区，作者明确这是为吸收瞬态突发所需的设计取舍。[citation:3]

成果方面，作者报告 RDMA 与 TCP 的流完成时间最多改善 33%。需要说明的是，该百分比出自作者自述评估，本次材料未包含完整实验设置，数值应视为论文宣称值。[citation:1][citation:2]

关于可进一步验证的问题：论文明确原型实现“超出本文范围、属于未来工作”，仅称与 NVIDIA 的讨论确认共享缓冲池模型的近似可在硬件实现，并正与一家主要以太网交换机厂商讨论在其可编程接纳控制 ASIC 上实现。因此硬件可实现性属于厂商沟通层面的推断，尚无公开原型证据。[citation:3]

### 四、相邻遥测工作：InvisiFlow（非直接拥塞控制）

InvisiFlow 定位为“遥测数据传输基座”，目标是让网络遥测数据收集对用户流量近乎“隐形”，属于相邻方向而非拥塞控制算法本身。其问题陈述是：现有遥测传输方法在高负载下会给用户流量带来显著开销和/或造成遥测数据丢失。[citation:4][citation:5]

技术路线区别于始终按最短路径推送遥测包的既有系统：InvisiFlow 利用机会式发送与拥塞梯度动态寻找空闲带宽，同时降低遥测丢包率与对用户流量的开销。[citation:4][citation:5]

成果方面，作者报告在 FatTree 拓扑下高负载场景中仍可达近零丢包率，较 Everflow、Planck 等方法所用技术约低 33.8 倍；在 70% 负载下，全流相对误差较多路复用基线降低约 2.4 倍、较拉取式基线降低约 4.8 倍；负载不均衡场景下 80% 负载仍保持零遥测丢包，而基线丢包率上升；70% 负载下缺失路径比例为 0，对比值为 33.2（原文在此处截断，后续数值未取得）。以上均为作者自述评估结果。[citation:6]

工程实现方面，原型相对于低优先级 UDP 方案仅增加 2.08% 网关与 0.78% VLIW 动作，且不在出口管线重循环遥测包。评估结合测试床实验与大规模 ns-3 仿真。[citation:6]

### 五、结论与未覆盖范围

就可核对材料看，2024–2025 年微软在该方向上呈现“一条直接缓冲区拥塞管理线（Reverie）+ 一条相邻遥测传输线（InvisiFlow）”的格局，两者机构署名均为多方合作。[citation:2][citation:5]

未覆盖范围包括：完整实验方法与数据集细节、Reverie 的原型实现与厂商落地进展、微软在该方向的专利/内部文档、以及其他可能存在于 dblp、arXiv、Google Scholar 的成果。本简报不据此推断微软内部研发战略或路线转向。[citation:3][citation:6]

## 核验结果

自动来源支持：9/16 项；人工复核：未复核。模型置信度不代表人工确认。
支持状态来自模型语义判断与原文引语校验，不能保证结论为真。

- claim:5 [unverifiable] Reverie 针对的问题层次是交换机缓冲区共享（buffer sharing），而非端到端传输协议本身。论文指出，数据中心交换机缓冲区被容忍丢包的 TCP/DCTCP 类流量与要求无损的 RDMA（RoCE）类流量共同使用，而现有共享实践在“隔离 RDMA 与 TCP”与“最大化突发吸收”之间存在根本性冲突。[citation:1][citation:2] — Model quote is absent from the selected cited source; Excerpt explicitly describes switch buffer sharing as the problem layer, mixed loss-tolerant TCP/DCTCP vs lossless RDMA/RoCE traffic, and the fundamental tension between isolating RDMA and TCP and maximizing burst absorption.
- claim:8 [unsupported] 关于分配行为，Reverie 按 1/(1+α) 比例分配共享缓冲区，类别单独使用时获得更多缓冲；定理 2 表明稳态下会保留少量空闲缓冲区，作者明确这是为吸收瞬态突发所需的设计取舍。[citation:3] — The excerpt does not mention the 1/(1+α) sharing ratio, the behavior of a single class alone, Theorem 2, or keeping idle buffers at steady state as an explicit design trade-off. It only discusses the shared allocation concept and burst absorption in general. These specific claims are not entailed by the supplied excerpt.
- claim:10 [unsupported] 关于可进一步验证的问题：论文明确原型实现“超出本文范围、属于未来工作”，仅称与 NVIDIA 的讨论确认共享缓冲池模型的近似可在硬件实现，并正与一家主要以太网交换机厂商讨论在其可编程接纳控制 ASIC 上实现。因此硬件可实现性属于厂商沟通层面的推断，尚无公开原型证据。[citation:3] — The excerpt confirms that ASIC implementation is left to future work with a switch ASIC vendor. However, it does not say that a prototype is 'out of scope' of this paper, does not mention approval of the shared-buffer model's approximation by NVIDIA, and does not mention any specific 'major Ethernet switch vendor.' The Acknowledgement mentions NVIDIA discussions but only in the acknowledgements text, and the excerpt is cut off there. Several specific details in the claim go beyond what the supplied excerpt supports.
- claim:13 [unsupported] 成果方面，作者报告在 FatTree 拓扑下高负载场景中仍可达近零丢包率，较 Everflow、Planck 等方法所用技术约低 33.8 倍；在 70% 负载下，全流相对误差较多路复用基线降低约 2.4 倍、较拉取式基线降低约 4.8 倍；负载不均衡场景下 80% 负载仍保持零遥测丢包，而基线丢包率上升；70% 负载下缺失路径比例为 0，对比值为 33.2（原文在此处截断，后续数值未取得）。以上均为作者自述评估结果。[citation:6] — The excerpt only supports the single sub-claim that InvisiFlow keeps zero telemetry packet loss at 80% load under load imbalance while baseline loss rose. It does not mention FatTree, 33.8×, Everflow/Planck, 2.4× at 70%, 4.8× versus pull-based, or the 33.2 missing-path figure. Numbers and scope cannot be verified from the excerpt.
- claim:14 [unsupported] 工程实现方面，原型相对于低优先级 UDP 方案仅增加 2.08% 网关与 0.78% VLIW 动作，且不在出口管线重循环遥测包。评估结合测试床实验与大规模 ns-3 仿真。[citation:6] — Table 2 does support the 2.08% gateway and 0.78% VLIW marginal increase versus the low-priority UDP baseline. But the excerpt does not show 'no recirculation of telemetry packets in the egress pipeline' or mention testbed experiments or large-scale ns-3 simulation, so the claim as a whole is broader than this evidence and cannot be supported.
- claim:15 [unsupported] 就可核对材料看，2024–2025 年微软在该方向上呈现“一条直接缓冲区拥塞管理线（Reverie）+ 一条相邻遥测传输线（InvisiFlow）”的格局，两者机构署名均为多方合作。[citation:2][citation:5] — Excerpts confirm Reverie (NSDI '24) is buffer sharing and InvisiFlow (NSDI '25) is telemetry transmission, both with multi-author affiliations. But the excerpt does not establish a Microsoft 2024–2025 programmatic 'two-line' connection linking them, so the '格局' framing is the authors' synthetic interpretation, not something these sources show.
- claim:16 [unverifiable] 未覆盖范围包括：完整实验方法与数据集细节、Reverie 的原型实现与厂商落地进展、微软在该方向的专利/内部文档、以及其他可能存在于 dblp、arXiv、Google Scholar 的成果。本简报不据此推断微软内部研发战略或路线转向。[citation:3][citation:6] — Missing or duplicate model verdict

## References

[1] https://www.microsoft.com/en-us/research/publication/reverie-low-pass-filter-based-switch-buffer-sharing-for-datacenters-with-rdma-and-tcp-traffic/ — https://www.microsoft.com/en-us/research/publication/reverie-low-pass-filter-based-switch-buffer-sharing-for-datacenters-with-rdma-and-tcp-traffic/ (official_document_check_entity_and_claim)
[2] https://www.usenix.org/conference/nsdi24/presentation/addanki-reverie — https://www.usenix.org/conference/nsdi24/presentation/addanki-reverie (paper_or_proceedings)
[3] https://www.usenix.org/conference/nsdi24/presentation/addanki-reverie (PDF) — https://www.usenix.org/system/files/nsdi24-addanki-reverie.pdf (paper_or_proceedings)
[4] https://www.microsoft.com/en-us/research/publication/enabling-silent-telemetry-data-transmission-with-invisiflow/ — https://www.microsoft.com/en-us/research/publication/enabling-silent-telemetry-data-transmission-with-invisiflow/ (official_document_check_entity_and_claim)
[5] https://www.usenix.org/conference/nsdi25/presentation/zhang-yinda — https://www.usenix.org/conference/nsdi25/presentation/zhang-yinda (paper_or_proceedings)
[6] https://www.usenix.org/conference/nsdi25/presentation/zhang-yinda (PDF) — https://www.usenix.org/system/files/nsdi25-zhang-yinda.pdf (paper_or_proceedings)