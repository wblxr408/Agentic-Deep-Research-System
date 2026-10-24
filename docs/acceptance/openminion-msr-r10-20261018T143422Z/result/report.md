## Microsoft Research 数据中心网络拥塞方向研究简报（2024–2025）

### 范围与方法
本简报以 2024–2025 年可取得的代表性公开论文为限，聚焦 Microsoft Research 参与的数据中心网络拥塞相关工作，逐项核对发表时作者单位，并区分直接拥塞控制类成果与相邻的遥测传输类成果。全部结论仅依据已采集的四份材料（两篇论文的官方页面与两篇会议论文正文），不穷尽成果清单，不推断内部研发战略或路线转向。[citation:1][citation:2][citation:4][citation:5]

### 成果一：Reverie——交换机缓冲共享（直接拥塞相关）
**发表信息与单位核对。** Reverie 发表于 NSDI'24（2024 年 4 月），作者为 Vamsi Addanki（TU Berlin）、Wei Bai（Microsoft Research）、Stefan Schmid（TU Berlin）、Maria Apostolaki（Princeton University）；会议正式记录与 Microsoft 官方页面一致，其中仅 Wei Bai 署名 Microsoft Research。[citation:1][citation:2][citation:3]

**研究问题。** 数据中心交换缓冲区由容损流量（如 DCTCP）与无损流量（如 RoCE 上的 RDMA）共享，现有共享方案难以在有效隔离 RDMA 与 TCP 的同时最大化突发吸收；根因有二：一是 RDMA 与 TCP 的缓冲共享依赖 ingress 与 egress 两个独立且常相互冲突的视图，二是共享方案对缓冲区过度细粒度地管理、对瞬时拥塞下占用变化反应过度。[citation:1][citation:2]

**技术路线。** Reverie 提出统一（合并 ingress 与 egress）的接纳控制，按流量类参数动态分配共享缓冲，并基于平均队列长度（低通滤波）而非瞬时长度作判定，使突发队列在瞬时拥塞下被自然吸收；论文同时给出稳态缓冲浪费的上界分析，指出保留的少量空闲缓冲正是突发吸收能力的来源。[citation:1][citation:3]

**成果与验证状态。** 论文报告 Reverie 可将 RDMA 与 TCP 的流完成时间性能提升最高约 33%。[citation:1] 需注意，论文明确说明原型实现超出本文范围、属后续工作，仅表示与 NVIDIA 的讨论确认其共享缓冲池模型的近似在硬件上可行，并正与某以太网交换机厂商讨论在其可编程接纳控制 ASIC 上实现——故该结果目前属仿真/分析结论，尚缺公开的硬件原型佐证。[citation:3]

### 成果二：InvisiFlow——静默遥测数据传输（相邻工作）
**发表信息与单位核对。** InvisiFlow 发表于 NSDI'25（2025 年 4 月，第 71–86 页），作者为 Yinda Zhang（UPenn）、Liangcheng Yu（UPenn 与 Microsoft Research）、Gianni Antichi（Politecnico di Milano 与 QMUL）、Ran Ben Basat（UCL）、Vincent Liu（UPenn）；按发表时单位，Microsoft Research 仅对应 Liangcheng Yu 一人。[citation:4][citation:5][citation:6]

**研究问题与定位。** 该工作解决细粒度遥测数据从网络设备传往采集器时的传输问题：既有方法在网络高负载下会给用户流量带来显著开销，和/或造成遥测数据丢失。它处理的是遥测数据自身的传输路径与发送时机，而非用户流量的拥塞控制机制，故在本简报中归为与拥塞相邻的遥测工作，不宜与 Reverie 混同。[citation:4][citation:5]

**技术路线。** InvisiFlow 不再始终沿最短路径推送遥测包，而是利用机会式发送与拥塞梯度动态寻找空闲网络容量，以同时压低遥测丢失率和对用户流量的开销；原型在 egress 管道寄存器中暂存遥测数据后立即丢弃对应包，避免重循环开销，相对低优先级 UDP 方案仅增加约 2.08% 网关与 0.78% VLIW 动作资源。[citation:4][citation:6]

**成果。** 在 FatTree 拓扑下，InvisiFlow 即便在高负载场景也能接近零丢失率，相比 Everflow、Planck 等方法所使用的先进传输方案丢失率约低 33.8 倍。[citation:4][citation:5]

### 可进一步验证的问题
1. Reverie 缺少公开硬件原型：论文中「NVIDIA 可行性确认」与「与交换机厂商洽谈 ASIC 实现」均为文字表述，其 33% 性能提升尚无真实 ASIC 或独立复现证据。[citation:3]
2. InvisiFlow 的评估为测试床实验叠加 ns-3 大规模仿真（FatTree，9 核心交换机、4 pod、144 服务器、100 Gbps 链路、4:1 超订比，缓冲按 Tofino 比例设置），结论依赖仿真参数设定，尚需独立复现核对。[citation:6]
3. 两篇论文的「拥塞」语义需逐一区分：Reverie 直接涉及交换机缓冲分配与拥塞隔离，InvisiFlow 处理的是遥测传输对用户流量的干扰与自身丢失，二者不应合并为同一技术路线。[citation:1][citation:4]

### 未覆盖范围
本简报仅覆盖四份已采集材料（两篇论文各自的官方页面与会议正文），未穷尽 Microsoft Research 在 2024–2025 年数据中心网络拥塞方向的全部公开成果；其他相关论文、arXiv/DBLP/Google Scholar 等索引中的其他条目、以及未列入种子范围的工作均未纳入核对。作者单位仅按发表时署名认定，不推断个人后续任职或内部组织归属；亦不推断研究战略或路线转向。[citation:1][citation:2][citation:4][citation:5]

## 核验结果

自动来源支持：7/13 项；人工复核：未复核。模型置信度不代表人工确认。
支持状态来自模型语义判断与原文引语校验，不能保证结论为真。

- claim:1 [unverifiable] 本简报以 2024–2025 年可取得的代表性公开论文为限，聚焦 Microsoft Research 参与的数据中心网络拥塞相关工作，逐项核对发表时作者单位，并区分直接拥塞控制类成果与相邻的遥测传输类成果。全部结论仅依据已采集的四份材料（两篇论文的官方页面与两篇会议论文正文），不穷尽成果清单，不推断内部研发战略或路线转向。[citation:1][citation:2][citation:4][citation:5] — 该断言主要描述本简报自身的范围与方法论（2024–2025 年限、仅依据四份材料、不推断内部战略等），这类元陈述无法由材料内容本身所蕴含。所引段落只能证实两篇论文涉及 Microsoft Research 参与及相关主题，不足以验证“仅依据四份材料”“不穷尽清单”等自限性表述。
- claim:4 [unverifiable] **技术路线。** Reverie 提出统一（合并 ingress 与 egress）的接纳控制，按流量类参数动态分配共享缓冲，并基于平均队列长度（低通滤波）而非瞬时长度作判定，使突发队列在瞬时拥塞下被自然吸收；论文同时给出稳态缓冲浪费的上界分析，指出保留的少量空闲缓冲正是突发吸收能力的来源。[citation:1][citation:3] — Model quote is absent from the selected cited source; The unified consolidated admission control, single shared pool with per-packet accounting, and average-queue-length (low-pass filter) decision rule are all entailed by cited excerpts. The 'upper bound on steady-state buffer waste' and 'retained idle buffer as source of burst absorption' portions are only loosely implied by the buffers/headroom discussion and are not directly entailed; lacking a specific excerpt for that sub-claim, I mark it unsupported in part, though the core technical route is supported. Overall: partially supported; the claimed formal waste-bound analysis is not evidenced.
- claim:7 [unverifiable] **研究问题与定位。** 该工作解决细粒度遥测数据从网络设备传往采集器时的传输问题：既有方法在网络高负载下会给用户流量带来显著开销，和/或造成遥测数据丢失。它处理的是遥测数据自身的传输路径与发送时机，而非用户流量的拥塞控制机制，故在本简报中归为与拥塞相邻的遥测工作，不宜与 Reverie 混同。[citation:4][citation:5] — Verification unavailable: AgentOutputValidationError
- claim:8 [unverifiable] **技术路线。** InvisiFlow 不再始终沿最短路径推送遥测包，而是利用机会式发送与拥塞梯度动态寻找空闲网络容量，以同时压低遥测丢失率和对用户流量的开销；原型在 egress 管道寄存器中暂存遥测数据后立即丢弃对应包，避免重循环开销，相对低优先级 UDP 方案仅增加约 2.08% 网关与 0.78% VLIW 动作资源。[citation:4][citation:6] — Verification unavailable: AgentOutputValidationError
- claim:9 [unverifiable] **成果。** 在 FatTree 拓扑下，InvisiFlow 即便在高负载场景也能接近零丢失率，相比 Everflow、Planck 等方法所使用的先进传输方案丢失率约低 33.8 倍。[citation:4][citation:5] — Verification unavailable: AgentOutputValidationError
- claim:13 [unverifiable] 本简报仅覆盖四份已采集材料（两篇论文各自的官方页面与会议正文），未穷尽 Microsoft Research 在 2024–2025 年数据中心网络拥塞方向的全部公开成果；其他相关论文、arXiv/DBLP/Google Scholar 等索引中的其他条目、以及未列入种子范围的工作均未纳入核对。作者单位仅按发表时署名认定，不推断个人后续任职或内部组织归属；亦不推断研究战略或路线转向。[citation:1][citation:2][citation:4][citation:5] — The claim is a methodological scope statement about the brief itself—what was and was not collected, that other papers/indexes were excluded, and that no career or strategy inferences are made. The excerpts are the four source pages themselves and their bibliography entries; they can confirm the two papers and their affiliations at publication (e.g., Wei Bai, Microsoft Research; Liangcheng Yu, University of Pennsylvania and Microsoft Research), but no excerpt enumerates the brief's seed corpus or asserts the absence of other Microsoft Research work. A statement of what the brief omitted cannot be entailed by a subset of the surveyed pages, so the claim is a scoping declaration rather than a factual assertion checkable against these excerpts.

## References

[1] https://www.microsoft.com/en-us/research/publication/reverie-low-pass-filter-based-switch-buffer-sharing-for-datacenters-with-rdma-and-tcp-traffic/ — https://www.microsoft.com/en-us/research/publication/reverie-low-pass-filter-based-switch-buffer-sharing-for-datacenters-with-rdma-and-tcp-traffic/ (official_document_check_entity_and_claim)
[2] https://www.usenix.org/conference/nsdi24/presentation/addanki-reverie — https://www.usenix.org/conference/nsdi24/presentation/addanki-reverie (paper_or_proceedings)
[3] https://www.usenix.org/conference/nsdi24/presentation/addanki-reverie (PDF) — https://www.usenix.org/system/files/nsdi24-addanki-reverie.pdf (paper_or_proceedings)
[4] https://www.microsoft.com/en-us/research/publication/enabling-silent-telemetry-data-transmission-with-invisiflow/ — https://www.microsoft.com/en-us/research/publication/enabling-silent-telemetry-data-transmission-with-invisiflow/ (official_document_check_entity_and_claim)
[5] https://www.usenix.org/conference/nsdi25/presentation/zhang-yinda — https://www.usenix.org/conference/nsdi25/presentation/zhang-yinda (paper_or_proceedings)
[6] https://www.usenix.org/conference/nsdi25/presentation/zhang-yinda (PDF) — https://www.usenix.org/system/files/nsdi25-zhang-yinda.pdf (paper_or_proceedings)