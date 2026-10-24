## Microsoft Research · Reverie

- **发表与归属** Reverie：Reverie 发表于 NSDI 2024，共同作者 Wei Bai 在论文发表时的单位标注为 Microsoft Research，其余作者分别来自 TU Berlin 与 Princeton University。 [citation:1][citation:2][citation:4]

- **研究问题** Reverie：Reverie 研究数据中心交换机缓冲区在 RDMA 无损流量与 TCP/DCTCP 有损流量混合场景下的共享问题，指出现有做法难以同时做到业务隔离与最大化突发吸收。 [citation:1][citation:2][citation:4]

- **技术方法** Reverie：Reverie 的核心是统一入口与出口视角的准入控制，按低通滤波方式分配缓冲区，以在缓冲上限内吸收瞬态拥塞造成的突发队列长度。 [citation:1][citation:2][citation:4]

- **成果及条件** Reverie：Reverie 的评估显示，按流完成时间计，RDMA 与 TCP 的性能最高可提升 33%。 [citation:1][citation:4]

- **成果及条件** Reverie：在 NS-3 仿真的 incast 场景下，Reverie 相较 DT 使 TCP incast 性能最高提升 46.8%。 [citation:2]

- **成果及条件** Reverie：在 20%–80% 背景负载、leaf-spine 256 主机拓扑的仿真中，Reverie 相较 DT 平均降低短流 TCP 的 99 分位流完成时间 42.7%。 [citation:2]

- **论文中的限制** Reverie：Reverie 的评估基于 NS-3 仿真，尚未见真实硬件部署证据；参数 γ 的最优取值在该文中仍是未解问题。 [citation:2]

## Microsoft Research · InvisiFlow

- **发表与归属** InvisiFlow：InvisiFlow 发表于 NSDI 2025，共同作者 Liangcheng Yu 在论文发表时的单位标注为 University of Pennsylvania 与 Microsoft Research 双聘。 [citation:3][citation:5]

- **研究问题** InvisiFlow：InvisiFlow 指出既有遥测数据传输方法在网络高负载时会给用户流量带来显著开销，或导致遥测数据丢失。 [citation:3][citation:5]

- **技术方法** InvisiFlow：InvisiFlow 通过机会式发送与拥塞梯度动态寻找网络空闲容量，而非沿最短路径固定推送遥测包。 [citation:3][citation:5]

- **成果及条件** InvisiFlow：在 FatTree 拓扑的高负载场景下，InvisiFlow 的遥测丢包率相对 Everflow、Planck 等方法降低约 33.8 倍。 [citation:3][citation:5]

- **论文中的限制** InvisiFlow：InvisiFlow 属于面向遥测传输的相邻工作，并非直接拥塞控制机制；其公开摘要仅给出 FatTree 仿真条件下的评估结果。 [citation:3][citation:5]
