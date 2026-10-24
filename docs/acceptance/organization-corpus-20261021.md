# 样本基线与流转的真实端到端交付

2026-10-21，OpenSpec 7.2。基于真实 USENIX 页面、本机 DeepSeek、API、PostgreSQL、Edge 和实际下载，验证声明来源、样本流转、截止时间、去重和全文缺口。[ACI](../organization-corpus.md)说明参数、权限、错误、预算及未验证分支；没有引入新 Agent 或另一条研究引擎。

## 新增请求的失败与实际修复

真实登录后提交包含 `organization_research.corpus` 的请求，旧 API 返回 extra_forbidden 422；[原响应](organization-corpus-20261021/baseline-response.txt)保留。实现后，从真实工作台填写来源、种子、检索式、成果类型和日期，发起新研究。

首轮 `725771bd-180f-4aa1-9f75-da07e29bd24b` 在报告阶段因新增 JSON 交接漏导入 `json` 失败，已修复。后续发现并行工具的 Send payload 漏传组织配置及已读材料，导致根状态有来源声明，但实际工具没有使用它；补齐当前运行配置，并仅向浏览节点传本网址已读材料。读取改用现有受控 HTTP，保留来源取得方式与元数据，原文证明和样本流转不再依赖模型自报。

中间研究 `c8fa4bbe-f65d-44d9-8696-9c69e074a7bd` 遇到本机运行环境中断：消费者、API、UI、Docker 进程均消失，数据库拒绝连接。使用已安装的恢复入口及原容器恢复服务后，读取到旧研究仍为 running 的持久快照；确认旧工作进程不存在且预算时限已过，保存原快照并通过原 RuntimePersistence／Harness 记录 worker_interrupted_budget_expired。没有重置预算、把旧研究记为完成，或仅因轮询超时重启它。

检索首轮 `e784b177-a641-4f8d-aa30-94627081939b` 中，空受限检索被当作可重试错误，等待回退反复调度，触发 GraphRecursionError。改为在保留渠道原始 empty_content／过滤记录的同时，把没有范围内线索作为本次发现的有界结果；不自动扩域、不增加图递归上限掩盖问题。认证、速率、配置和网络等明确错误仍保留原失败处理。

日期边界的实际 RED `1933500f-1647-4518-bb6a-8ee0ef81fa60`：DistServe 只有 2024 年 7 月，研究要求 7 月 16–31 日时被误判为已排除。修复为区间三分：确定在范围外才排除，完整在内才纳入，交叠而精度不足保持待核。单个主记录且标题一致的出版 BibTeX 元数据保留原文偏移和月精度，不让模型把月初补成具体发表日。上述[失败与中断摘要](organization-corpus-20261021/failed-attempts.json)及本机原状态均保留。

## 最终真实场景

共同来源为 [DistServe／OSDI 24](https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin)及 [Harp／NSDI 26](https://www.usenix.org/conference/nsdi26/presentation/hu-jiayu)。选择 Peking University、计算机学科、会议论文；这些请求标签不等于已经完成独立学科分类。

| 场景与研究 ID | 实际结果 | 原始交付 |
| --- | --- | --- |
| 只读种子 `c2d7de95-9615-4b83-b9e7-051df16a488e` | 2024 年范围，三条原始种子含 DistServe 的片段重复，合并为两条；DistServe 采纳 1 发表／1 家族，Harp 按 2026 年 5 月出版区间排除。2 条来源，6 次工具履历中 2 次实际读取、4 次复用任务证据，没有新增重复证据。采纳样本未取得全文。 | [数据](organization-corpus-20261021/seeds.json)、[页面](organization-corpus-20261021/seeds.png) |
| 检索＋种子 `ca9ae733-92ec-4c44-a29a-bc595a393c99` | 实际查询及范围过滤进入结果。21 个来源候选，采纳 1、排除 19、待核 1；19 包括范围外线索及 Harp 日期排除，不等于 19 篇已读论文。10 条来源证据含片段和已读正文，取得证据的来源均在 usenix.org 范围内；搜索片段不能作为主要成果原文证明。 | [数据／执行式／工具与节点结果](organization-corpus-20261021/search.json)、[页面](organization-corpus-20261021/search.png) |
| 月精度交叠 `ea1cdb8b-dd0b-4933-a210-a5049d38dcd6` | 请求 2024-07-16 至 2024-07-31，只读 DistServe；出版区间为 2024-07-01 至 2024-07-31、精度 month。最终 1 个候选待核、0 采纳、0 排除，原因 date_precision_overlaps_scope。没有把区间下界当成真实发表日，也没有以 0 采纳推断现实零成果。 | [数据](organization-corpus-20261021/date-overlap.json)、[页面](organization-corpus-20261021/date-overlap.png) |

消费者 [`organization_corpus_e2e.py`](../../scripts/organization_corpus_e2e.py) 检查真实结果、PostgreSQL 保存正文及 corpus、一致的冻结时刻、UI 中对应具体来源行、实际 JSON 下载。只读场景由真实配置页面提交；检索和交叠场景用同一登录身份调用实际创建接口后消费页面和下载。检索页面有多个“已排除”行，首个观察器因定位不唯一停止；改为按 Harp 来源行定位后，使用同一完成 session 回访通过，没有重新取证。

```powershell
.venv/Scripts/python.exe scripts/organization_corpus_e2e.py --ui
.venv/Scripts/python.exe scripts/organization_corpus_e2e.py --search
.venv/Scripts/python.exe scripts/organization_corpus_e2e.py --search --session ca9ae733-92ec-4c44-a29a-bc595a393c99
.venv/Scripts/python.exe scripts/organization_corpus_e2e.py --overlap
```

最终三条场景消费者均退出 0。范围外种子和不支持的平台渠道由真实创建入口返回 422，见[拒绝记录](organization-corpus-20261021/rejected-inputs.json)。没有用健康、启动、导入、文件存在性、hash 或文字探针代替上述业务路径；未执行回归、单元、冒烟或类型／构建／lint 等非端到端门禁。

## 保留的限制

本项通过的是来源和样本契约，三篇报告最终审计仍 needs_review、人工未审核。只读／检索报告分别为 4 项主张中检查 2 项、0 项获支持，以及 5 项中检查 2 项、0 项获支持；交叠报告 6 项检查、3 项获支持。完整审核明细在各数据包，不能把结构化计数一致或 completed 当作正文科学结论已核实。

检索中仍有补证节点因预算跳过，保留节点结果及 budget_exceeded，不冒称所有发现均已读取。该样本只有一条纳入发表；引用、作者单位、语义审核和研究深度仍受覆盖限制。重定向／DNS 攻击全集、其他出版商格式、显式 PDF 全文、全部五类来源及所有跨 owner／旧版本分支没有在本项重新执行；代码支持不等于已有运行证明。

先前请求与快照不回填新声明。采纳是有来源样本检查，学科／主题仍需 7.3，关系／深读／趋势／行动／跨图文统计仍按 7.4–7.8；完整 TODO 及最终统一端到端能力验证未完成。
