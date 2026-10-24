# 北大系统团队全文调研与报告交付

日期：2026-10-22。范围沿用[研究简报](../PKU_RESEARCH_BRIEF.md)：金鑫、刘譞哲相关系统研究网络，2024—2026年大模型服务与云系统，回答研究布局、机制演进和具体合作课题。

## 实际材料与产物

重点全文：DistServe、dLoRA、LoongServe、RLHFuse、Aegaeon、HydraServe、ServeGen，另读RAGCache的2024预印本v2。补读TokenLake v1、Heddle v1、ExpertPlex v2三项前沿预印本，分别核对版本日期和机构署名。FastServe的2023预印本/2026会议记录用于校正演进时间；不把它算成本次额外深读论文。RAGCache 2026期刊书目与2024所读全文分开，不混用作者和实验。JITServe与HARP不作为本次北大成果。

资料保存于`outputs/pku-systems-20261022/papers/`。七份PDF已保存并用pypdf提取全部页的原生文本，无空文本页；Aegaeon作者站的直接下载超时，改用Firecrawl取得公开PDF全文Markdown，并与USENIX/作者PDF网页读取内容核对关键正文。三项前沿全文也保存为Markdown。Firecrawl生成的曲线表格没有当作数据使用；唯一数值图按Aegaeon正文1192与213重绘。

现有结构化解析器对部分论文标记`partial_text/truncated`，尽管页数齐全。实际深读补用了完整逐页文本，模型按问题接收选定方法/实验段落；全文已获取不等于每个模型请求已读全文。原始结构化解析状态保持原样。

交付：

- [可交互主报告](../../outputs/pku-systems-20261022/report.html)、[主报告PDF](../../outputs/pku-systems-20261022/report.pdf)、[Markdown](../../outputs/pku-systems-20261022/report.md)。
- [技术附录](../../outputs/pku-systems-20261022/technical-appendix.html)及[附录PDF](../../outputs/pku-systems-20261022/technical-appendix.pdf)：8篇机制/实验条件表及5项合作课题完整说明。
- [研究数据](../../outputs/pku-systems-20261022/report-data.json)、[用量](../../outputs/pku-systems-20261022/research-budget.json)、[关键数值复核](../../outputs/pku-systems-20261022/key-results-review.json)、[首次语义复核](../../outputs/pku-systems-20261022/claim-review.json)。

报告包含研究能力图、路线时间图、阶段隔离/弹性并行机制图、团队协作网络、具有实际生产环境的GPU配置对照，共5幅图；参考资料列出可点击原文。合作课题逐项给出资源、必要条件、首个成果和验收指标。公开学术邮箱只作为读者联系入口，没有发送任何消息。

## 真实自动流程与人工续作

真实ADRS任务为`97b4ccc3-aa8d-4dc7-a8b2-bfbdba8fb8a6`，通过既有登录、查询解释与研究API启动。14个声明来源取得13个，Aegaeon作者站失败并计入实际调用。分析调用原生用量28,874，输出达到8192上限；报告请求因保守输入预占不足未外发。随后暂停结果持久化因PostgreSQL参数类型推断冲突成为failed，`completed_at`为空。

这条失败记录没有被修改为成功，也没有重置额度。继续研究使用同一120,000总量的剩余91,126额度，复用既有`ModelTokenBudget/BudgetedClient`对11篇选定全文段落进行真实DeepSeek阅读，再对24项论文主张和12项关键数字做语义来源核对。合计24次真实模型请求、原生104,569/120,000 tokens；未知模型价格保持unknown，不能报告账单为0。逐篇笔记中5项输出达到长度上限，作为部分笔记保留，不直接发布为完整结构化成果。

首次24项复核有若干partial及一项unsupported，原因包括选段未覆盖全部复合主张和复核模型要求了主张未表达的细节，原结果未覆盖。随后以原文明确段落核对12个关键实验/数值：11项自动支持，HydraServe一项因果解释判partial。报告使用“无NVLink，评估模型可放单GPU”的较窄事实，人工对照§8.1确认；不把它记成自动通过，不宣称整篇报告全部机器审核通过。合作建议与研判由证据推导，不冒充论文事实。

最终HTML/PDF为研究辅助、来源复核后人工整编的交付稿，**不是该失败任务自动生成并持久化的最终报告**。临时续作与编排脚本位于`.codex-homework/pku-deep-20261022/`，不能据此宣布通用自动报告具备同等深度。

## 本次必要修复与实际验证

按用户要求继续优化时，先观察两项当前消费者失败，再修复：

1. `app/api/research.py`最终结果SQL显式统一`$1::varchar`与`$14::timestamp`，避免同一参数在状态赋值/CASE及时间赋值/CASE中被推断为不兼容类型。真实PostgreSQL临时表执行生产语句，验证paused、原稿和用量落库且完成时间为空；不修改历史研究行。
2. `app/agents/analyst.py`遇到`finish_reason=length`保存原生用量、片段和提取状态，抛出已有暂停异常；阻止截断JSON继续作为报告输入。

仅运行`tests/current_change/test_deep_report_completion.py`两项当前变更检查：最初2项失败；SQL状态修复后发现时间参数也有冲突；修复两处类型后2项通过。没有运行现有回归、冒烟、启动/导入/hash/文件存在或文字正则检查。未为证明新修复而再发起整份收费研究；新完整自动流程仍未完成。

按既有预算边界复用 **A2AB-10《委派环路检测与全链预算》/ 基线v1.0 / 工程解决方案1、3，验收办法T3的预算分支**，索引及完整方案已读；出处为Basic Memory `main/engineering/security/a2abreak/solutions/a2-ab-10-委派环路检测与全链预算`。控制点是服务端根额度、分析截断暂停与可信事务持久化；续作只用剩余额度，无新增根身份续命。没有新增委派/权限/租约功能，其他01—11沿用既有适用评估；本次证据不代表全部A2A安全验证。

## 读者质量与未完成范围

详见[本次质量审阅](pku-report-quality-20261022.md)。主报告按问题比较，技术细节进入附录；实际打开离线HTML、展开附录、按研究方向筛选，保存桌面与手机预览，并导出主文/附录PDF。最终页数以`render-record.json`实际导出结果为准；不是预设页数目标。PDF另渲染为页面缩略图检查换页、裁切和文字。

仍需实现的通用能力：按子问题分配全文阅读份额、处理结构化提取截断、给报告阶段装配可容纳且有充分依据的上下文、自动主文/附录组织、让复核器针对未支持的具体主张取回恰当段落，以及新的完整自动研究验证。高级算法、专业绘图执行器和全部ORG/OPT范围没有因此完成。
