# 6.2 独立、混合与非计算机案例

2026-10-21，真实 Edge、认证 API、已有 PostgreSQL 和保存的原文证据。复用两条已完成的仓库真实研究，并新建材料学研究；没有将人工构造的成果、替代模型或既有 Codex 报告当作本次外部数据。

## 三个真实场景

| 场景 | 实际研究 | 对象及成果口径 |
| --- | --- | --- |
| 独立高校 | `2c8d4301-4cba-4adc-b692-c4da7e6add04` | Peking University 独立研究；真实出版商 DistServe 会议论文，1 条发表／1 家族。复用 5.4 的实际研究，本轮新增消费其重排变化。 |
| 混合对象 | `6533d261-19b7-47bc-9031-5c9237c1bf36` | PKU、UC San Diego 两所高校与 StepFun 企业；同一 DistServe 共同成果各对象均为 1，联合并集仍为 1。复用 4.4 实际研究，本轮新增消费混合类型的证据快照与重排。 |
| 非计算机 | `09d2337c-ebc5-47e8-a217-86a6435c7557` | King Faisal University，materials science，钙钛矿太阳能电池的真实期刊论文，1 条发表／1 家族。来自本轮新模型／工具研究。 |

前两项原始研究过程分别见 [5.4](organization-report-export-20261021.md)和[4.4](organization-findings-20261020.md)。非计算机种子为 PLOS 的[论文原文](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0351439)，保存了论文标题、发表署名及来源位置。研究请求要求保留页面更正线索，不将更正通知或参考文献另计为研究；本项不讨论未经独立核清的效率数值。

## 真实失败和改造

初始新研究 `12a0450a-0bdd-4bb7-acc9-576da7bf675e` 取得出版商原文后，日期校验拒绝 `2026-07-10`：原文明确标 `Published: July 10, 2026`，现有解析仅支持部分 ISO／BibTeX 写法，成果没有被纳入。消费者按预期失败，没有把期望改成零篇或替换为计算机成果。

`app/organization_findings.py` 补充出版商明确标注的英文发表日期及 ISO 斜线分隔日期。区分 Received、Accepted、Published；英文路径只考虑首个明确发表标签，不在后续日期中寻找碰巧匹配模型的条目；保持原始字段位置和声明精度，不做模糊日期猜测。

更新服务后启动新的实际研究 `09d2337c-ebc5-47e8-a217-86a6435c7557`，原失败结果保留。最终发表日期为 **2026-07-10**，不是收到日期或接受日期。并不据此宣称覆盖所有语言和所有出版商日期格式。

## 实际权重变化和学科适配

同一消费者对三个场景分别从本人完成结果准备不可变快照，在真实界面输入主题／证据权重 6／4，再改成 10／0。两次预览使用同一证据快照、独立配置版本，来源及成果归属未改。

每个对象在 60% 主题＋40% 未取得的证据完整度分项下，显示 **60–100、覆盖率 60%**；改为 100% 标题词面主题偏好后，显示 **100、覆盖率 100%**。这里的词面特征在三个样本中均命中，不是完整语义评估或科研质量分。混合对象共用同一论文，最后同分且没有确定优劣关系；没有为了演示而制造机构排名。

材料案例的实际结果类型是 `journal_article`。界面选择该真实类型后，CCF／ICORE 不适用，JCR JIF 适用但需授权导入；计算机会议样本的 CCF 则适用。保存的是适用性结果与缺失原因，没有给本篇材料论文伪造 JIF、分区或论文影响指标。

三个场景重排前后，PostgreSQL 保存的原报告、review 快照、token 记账和工具审计行数完全相同；新增行为只是原证据上的偏好计算。用户不必另选企业才能研究高校；混合类型也不要求存在正式合作协议。

## 最终消费及产物

`scripts/organization_cross_domain_e2e.py` 最终退出 0，三项 UI 重排、学科状态与原研究保持均通过。非计算机样本是这次真实外部读取与模型抽取，独立／混合样本是此前真实仓库研究；没有替代输入，复用的范围明确说明。

[材料请求](organization-cross-domain-20261021/materials-request.json)、[新研究结果](organization-cross-domain-20261021/materials-source-result.json)；三个子目录各保留 `source.json`、`snapshot.json`、`before.json`、`after.json`、`applicability.json` 和真实界面截图：

- [独立高校](organization-cross-domain-20261021/independent-university/after.json)。
- [混合对象](organization-cross-domain-20261021/mixed-organizations/after.json)。
- [非计算机材料学](organization-cross-domain-20261021/materials-science/after.json)。

这些是有界样本及当前偏好消费，不证明候选发现准确率、独立语义复核、完整评价连通、所有学科或全部报告事实。正文审计及来源噪声等仍按后续 TODO 处理。未运行回归、单元、冒烟、健康、类型／构建／lint 或其他非端到端检查；统一全系统能力验证仍未完成。
