# Microsoft Research 数据中心网络拥塞研究简报（2024–2025 代表性公开论文）

## 1. 范围与方法
- **范围**：2024–2025 年可公开获取的代表性论文；不要求穷尽成果清单。
- **单位**：逐项核对**发表时**的作者单位。
- **分类**：区分「直接拥塞/缓冲管理」与「相邻的遥测传输」两类工作。
- **判断边界**：只描述论文本身陈述的问题与技术路线；不推断微软内部研发战略，也不据单篇论文推断方向转向。

## 2. Reverie（NSDI '24，pp. 651–668）——直接相关：交换机缓冲共享
**作者与发表时单位**
- Vamsi Addanki — TU Berlin
- Wei Bai — **Microsoft Research**
- Stefan Schmid — TU Berlin
- Maria Apostolaki — Princeton University

**研究问题**：数据中心交换机缓冲区由不同丢包容忍度的流量类共享——传统应用用有损传输（如 DCTCP），新应用需无损传输（如 RoCE/RDMA）。论文分析认为现有缓冲共享做法存在根本限制，难以同时做到「隔离 RDMA 与 TCP」与「最大化突发吸收」，并给出两个根因：
1. RDMA/TCP 的缓冲共享依赖入口（ingress）与出口（egress）两套相互独立、时常冲突的缓冲视图；
2. 共享方案对缓冲区占用做「微观管理」，在瞬态拥塞时反应过度。

**技术路线**
- 统一的（入口+出口合并）准入控制，联合为两类流量优化缓冲分配；
- 基于**低通滤波**的缓冲分配，使瞬态拥塞下的突发队列长度在缓冲上限内被自然吸收。

**成果（论文自述）**：流完成时间（FCT）上，RDMA 与 TCP 性能均可提升最多 **33%**；同时适用于无损与有损流量类。

## 3. InvisiFlow（NSDI '25，pp. 71–86）——相邻工作：遥测数据传输
**作者与发表时单位**
- Yinda Zhang — University of Pennsylvania
- Liangcheng Yu — University of Pennsylvania **and Microsoft Research**
- Gianni Antichi — Politecnico di Milano and Queen Mary University of London
- Ran Ben Basat — University College London
- Vincent Liu — University of Pennsylvania

**研究问题**：流量工程、路径追踪等应用需从网络设备向采集器发送细粒度遥测数据；既有方法在重负载下会对用户流量造成显著开销，和/或丢失遥测数据。

**技术路线**：不再总是按最短路把遥测包推给采集器，而是利用**机会式发送**与**拥塞梯度**动态寻找空闲容量，同时最小化遥测丢失与对用户流量的开销。

**成果（论文自述）**：FatTree 拓扑、高负载场景下接近零丢失；相比 Everflow、Planck 等系统所用先进传输方法，丢失约低 **33.8 倍**。

**分类说明**：该文本身是「遥测数据传输基座」，不是拥塞控制算法；「拥塞梯度/机会式发送」属相邻机制复用。若作为「微软拥塞控制路线」的证据会属过度外推——它只体现「规避拥塞信号」的思想相近。

## 4. 单位核对要点（易误判处）
| 论文 | 微软署名作者 | 其发表时单位 | 注意 |
|---|---|---|---|
| Reverie | Wei Bai | Microsoft Research | 唯一微软单位作者；第一作者 Addanki 属 TU Berlin |
| InvisiFlow | Liangcheng Yu | UPenn **兼** MSR | 双单位兼职署名；第一作者 Zhang 属 UPenn |

因此两篇均**不能**简单标为「Microsoft Research 论文」，只能标为「含微软研究人员参与」。

## 5. 可进一步验证的问题
1. **Reverie 低通滤波的参数敏感性**：截止频率/时间常数如何权衡突发吸收与隔离度？摘要未给定量曲线，需查正文与工件。
2. **Reverie 的可部署性**：合并准入控制是否需交换机硬件改动（如可编程 ASIC）？对在役芯片的可行性未验证。
3. **33% 与 33.8× 的基准可比性**：两数分别来自不同拓扑、负载与对比对象，不宜横向比较「提升幅度」。
4. **是否有其他直接拥塞控制工作**：2024–2025 年微软是否还有主机侧 CC、INT 反馈闭环等论文——本轮检索未覆盖，下结论前需补查 DBLP/arXiv 作者主页。
5. **双单位署名的含义**：Yu 的双单位是否意味着该工作部分在 MSR 完成？需查致谢/资助信息。

## 6. 明确未覆盖的范围
- 未做 DBLP/arXiv/Google Scholar 的系统性检索，**不代表微软 2024–2025 年拥塞方向的完整成果集**；
- 技术细节主要据官方摘要，未逐段核对论文正文（如 InvisiFlow 正文提取未成功）；
- 未覆盖微软以外的工业界工作（Google、Meta、阿里等）作对照；
- 通用检索式（「Microsoft Research + congestion」）返回结果无效，故**未获得**除种子论文外的其他线索。

**证据强度提示**：以上结论均以微软官方出版物页与 USENIX 会议页/摘要为依据；具体数字属论文自述，未经独立复现。

## 核验结果

自动来源支持：0/39 项；人工复核：未复核。模型置信度不代表人工确认。
支持状态来自模型语义判断与原文引语校验，不能保证结论为真。

- claim:1 [missing_citation] **范围**：2024–2025 年可公开获取的代表性论文；不要求穷尽成果清单。 — Awaiting source support judgement
- claim:2 [missing_citation] **单位**：逐项核对**发表时**的作者单位。 — Awaiting source support judgement
- claim:3 [missing_citation] **分类**：区分「直接拥塞/缓冲管理」与「相邻的遥测传输」两类工作。 — Awaiting source support judgement
- claim:4 [missing_citation] **判断边界**：只描述论文本身陈述的问题与技术路线；不推断微软内部研发战略，也不据单篇论文推断方向转向。 — Awaiting source support judgement
- claim:5 [missing_citation] **作者与发表时单位** — Awaiting source support judgement
- claim:6 [missing_citation] Vamsi Addanki — TU Berlin — Awaiting source support judgement
- claim:7 [missing_citation] Wei Bai — **Microsoft Research** — Awaiting source support judgement
- claim:8 [missing_citation] Stefan Schmid — TU Berlin — Awaiting source support judgement
- claim:9 [missing_citation] Maria Apostolaki — Princeton University — Awaiting source support judgement
- claim:10 [missing_citation] **研究问题**：数据中心交换机缓冲区由不同丢包容忍度的流量类共享——传统应用用有损传输（如 DCTCP），新应用需无损传输（如 RoCE/RDMA）。论文分析认为现有缓冲共享做法存在根本限制，难以同时做到「隔离 RDMA 与 TCP」与「最大化突发吸收」，并给出两个根因： — Awaiting source support judgement
- claim:11 [missing_citation] RDMA/TCP 的缓冲共享依赖入口（ingress）与出口（egress）两套相互独立、时常冲突的缓冲视图； — Awaiting source support judgement
- claim:12 [missing_citation] 共享方案对缓冲区占用做「微观管理」，在瞬态拥塞时反应过度。 — Awaiting source support judgement
- claim:13 [missing_citation] **技术路线** — Awaiting source support judgement
- claim:14 [missing_citation] 统一的（入口+出口合并）准入控制，联合为两类流量优化缓冲分配； — Awaiting source support judgement
- claim:15 [missing_citation] 基于**低通滤波**的缓冲分配，使瞬态拥塞下的突发队列长度在缓冲上限内被自然吸收。 — Awaiting source support judgement
- claim:16 [missing_citation] **成果（论文自述）**：流完成时间（FCT）上，RDMA 与 TCP 性能均可提升最多 **33%**；同时适用于无损与有损流量类。 — Awaiting source support judgement
- claim:17 [missing_citation] **作者与发表时单位** — Awaiting source support judgement
- claim:18 [missing_citation] Yinda Zhang — University of Pennsylvania — Awaiting source support judgement
- claim:19 [missing_citation] Liangcheng Yu — University of Pennsylvania **and Microsoft Research** — Awaiting source support judgement
- claim:20 [missing_citation] Gianni Antichi — Politecnico di Milano and Queen Mary University of London — Awaiting source support judgement
- claim:21 [not_checked] Ran Ben Basat — University College London — Not checked
- claim:22 [not_checked] Vincent Liu — University of Pennsylvania — Not checked
- claim:23 [not_checked] **研究问题**：流量工程、路径追踪等应用需从网络设备向采集器发送细粒度遥测数据；既有方法在重负载下会对用户流量造成显著开销，和/或丢失遥测数据。 — Not checked
- claim:24 [not_checked] **技术路线**：不再总是按最短路把遥测包推给采集器，而是利用**机会式发送**与**拥塞梯度**动态寻找空闲容量，同时最小化遥测丢失与对用户流量的开销。 — Not checked
- claim:25 [not_checked] **成果（论文自述）**：FatTree 拓扑、高负载场景下接近零丢失；相比 Everflow、Planck 等系统所用先进传输方法，丢失约低 **33.8 倍**。 — Not checked
- claim:26 [not_checked] **分类说明**：该文本身是「遥测数据传输基座」，不是拥塞控制算法；「拥塞梯度/机会式发送」属相邻机制复用。若作为「微软拥塞控制路线」的证据会属过度外推——它只体现「规避拥塞信号」的思想相近。 — Not checked
- claim:27 [not_checked] | Reverie | Wei Bai | Microsoft Research | 唯一微软单位作者；第一作者 Addanki 属 TU Berlin | — Not checked
- claim:28 [not_checked] | InvisiFlow | Liangcheng Yu | UPenn **兼** MSR | 双单位兼职署名；第一作者 Zhang 属 UPenn | — Not checked
- claim:29 [not_checked] 因此两篇均**不能**简单标为「Microsoft Research 论文」，只能标为「含微软研究人员参与」。 — Not checked
- claim:30 [not_checked] **Reverie 低通滤波的参数敏感性**：截止频率/时间常数如何权衡突发吸收与隔离度？摘要未给定量曲线，需查正文与工件。 — Not checked
- claim:31 [not_checked] **Reverie 的可部署性**：合并准入控制是否需交换机硬件改动（如可编程 ASIC）？对在役芯片的可行性未验证。 — Not checked
- claim:32 [not_checked] **33% 与 33.8× 的基准可比性**：两数分别来自不同拓扑、负载与对比对象，不宜横向比较「提升幅度」。 — Not checked
- claim:33 [not_checked] **是否有其他直接拥塞控制工作**：2024–2025 年微软是否还有主机侧 CC、INT 反馈闭环等论文——本轮检索未覆盖，下结论前需补查 DBLP/arXiv 作者主页。 — Not checked
- claim:34 [not_checked] **双单位署名的含义**：Yu 的双单位是否意味着该工作部分在 MSR 完成？需查致谢/资助信息。 — Not checked
- claim:35 [not_checked] 未做 DBLP/arXiv/Google Scholar 的系统性检索，**不代表微软 2024–2025 年拥塞方向的完整成果集**； — Not checked
- claim:36 [not_checked] 技术细节主要据官方摘要，未逐段核对论文正文（如 InvisiFlow 正文提取未成功）； — Not checked
- claim:37 [not_checked] 未覆盖微软以外的工业界工作（Google、Meta、阿里等）作对照； — Not checked
- claim:38 [not_checked] 通用检索式（「Microsoft Research + congestion」）返回结果无效，故**未获得**除种子论文外的其他线索。 — Not checked
- claim:39 [not_checked] **证据强度提示**：以上结论均以微软官方出版物页与 USENIX 会议页/摘要为依据；具体数字属论文自述，未经独立复现。 — Not checked

## References

[1] https://www.usenix.org/conference/nsdi24/presentation/addanki-reverie — https://www.usenix.org/conference/nsdi24/presentation/addanki-reverie (paper_or_proceedings)
[2] https://www.microsoft.com/en-us/research/publication/reverie-low-pass-filter-based-switch-buffer-sharing-for-datacenters-with-rdma-and-tcp-traffic/ — https://www.microsoft.com/en-us/research/publication/reverie-low-pass-filter-based-switch-buffer-sharing-for-datacenters-with-rdma-and-tcp-traffic/ (official_document_check_entity_and_claim)
[3] https://www.microsoft.com/en-us/research/publication/enabling-silent-telemetry-data-transmission-with-invisiflow/ — https://www.microsoft.com/en-us/research/publication/enabling-silent-telemetry-data-transmission-with-invisiflow/ (official_document_check_entity_and_claim)
[4] https://www.usenix.org/conference/nsdi25/presentation/zhang-yinda — https://www.usenix.org/conference/nsdi25/presentation/zhang-yinda (paper_or_proceedings)
[5] https://www.usenix.org/system/files/nsdi24-addanki-reverie.pdf — https://www.usenix.org/system/files/nsdi24-addanki-reverie.pdf (paper_or_proceedings)