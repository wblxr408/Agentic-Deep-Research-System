# 6.1 腾讯网络研究：公开有界运行案例

2026-10-21。此案例包记录本仓库新产生的实际研究、模型／工具步骤、来源、版本、失败和受限结果。未复用之前 Codex 生成的腾讯报告作为运行证明；全部来源来自公开网页，未启用内部资料。可分享的是这个带审计与限制的运行案例，生成正文仍是待复核稿，不能当作已通过学术或商业决策审核的报告。

## 范围和种子

研究任务 **`5b56e7b4-b594-4fd5-bc66-bf088b35a2f5`**，对象仅 Tencent（企业），别名含 Tencent Cloud／腾讯／腾讯云；学科 computer science，主题 VPC network failure detection and recovery，范围 2026-01-01 至 2026-10-21。

以 USENIX 的 [Harp 出版商页面](https://www.usenix.org/conference/nsdi26/presentation/hu-jiayu)为种子，关注该单项公开成果的署名、时间、摘要可支持的机制、作者自述及待验证问题，不代表腾讯 2020—2026 论文全集、内部战略或完整合作网络。该页面有 Tencent 和 Fudan University 的发表署名，BibTeX 明示 2026 年 5 月；本次结构化输出保留 **2026-05-01 至 2026-05-31 的月精度区间**，没有虚构具体日期。机构视图只有被选中的 Tencent，外部署名不等于自动新增已选高校。

## 实际调用和版本

使用现有 LangGraph 主应用，经过 Planner、搜索／浏览、Analyst、Reflection、Report，并由确定性函数生成成果比较和冻结报告附录。实际保存的模型用量条目为 `deepseek-chat`（Analyst／Reflection／Report）；凭据不进入案例包。源查询、事件和结果保存在本次运行与原工具审计中。

配置 `tencent-network-case-20261021-v1`，预设 `adrs-presets-v1`，权重规则 `adrs-weight-rules-v1`，范围规则 `adrs-organization-scope-v2`，报告摘要 `adrs-organization-report-v1`。冻结的目录／适配器及来源版本在下载 JSON 中保留，`applied_to_evidence=false`，未把目录样本冒充此论文已取得的指标。

实际工具审计 9 项：2 次浏览成功、3 次搜索成功、2 次 `budget_exceeded`、2 次 `schema_validation`。原运行预算记录工具计数达到 12 的上限；审计行数与预算计数不是同一口径。参数校验失败的浏览步骤提供的是说明文字而非 URL，没有伪称取得全文。模型来源上下文也含搜索线索，不能把 32 条引用当作 32 篇已读论文。

应用保存总 token 估计 **50,799**；`estimated=true`。费用字段保存为 0，**不表示模型服务免费或实际账单为零**。本案例仅报告应用记账值，不将其作为提供方计费凭证。

## 失败、修复和消费证据

新研究本身已完成，但首次消费 `GET /api/v1/research/{id}/tool-calls` 返回 500：asyncpg 返回的 `args_json`／`safety_json` 是 JSON 字符串，而响应模型要求字典。修复该读取点，复用同文件 `_json_object`；没有绕过接口去拼造工具轨迹或重复取证。

更新服务后，`scripts/organization_tencent_case_e2e.py --session 5b56e7b4-b594-4fd5-bc66-bf088b35a2f5` 从**同一已完成任务**继续消费，退出 0：工具轨迹成功返回、字典字段可读取；PostgreSQL 正文及组织结果与 API 完整一致；实际页面回访及 Markdown／JSON／HTML 下载完成；JSON 与保存结果一致。原研究只有这一条，新读取没有重新调用研究模型。

结果为 1 条发表、1 个未关联版本的独立研究家族；保留 Tencent 作者和外部署名来源、月精度日期及 7 条解释边界。报告 22,251 字符、32 条引用。署名和原文位置通过程序校验，不代表独立语义复核；作者关于部署／生产改善的陈述仍是来源自述。

## 质量限制必须随结果一起交付

检索混入了国家空间数据基础设施、竖琴、医疗项目等同名噪声；完整公开来源列表未被删除来美化效果。该问题不计作检索相关性或任务不跑偏已经通过，继续由 OPT-08／09／14 及后续样本覆盖工作处理。两项无效浏览和预算耗尽同样原样记录。

最终正文审计 `needs_review=true`，64 项主张中实际检查 21 项、支持 8 项，来源支持率字段为 0.125；这不是一份全面核实的成品研究报告。更多主张未完成核查，不能因报告状态为 completed 或元数据／下载一致，就称其事实正确。正文审计和引用错配继续由 OPT-15 处理。

本项证明“以公开原文启动并交付一条可复核、带真实失败和受限结论的机构运行案例”；不代替第 7 组深读、关系、趋势和行动能力，不据此勾选 ORG 整体或全部业务质量验收。

## 案例包

- [原请求](tencent-network-case-20261021/request.json)、[报告 Markdown 待复核稿](tencent-network-case-20261021/tencent-report.md)、[HTML 待复核稿](tencent-network-case-20261021/tencent-report.html)、[完整研究 JSON](tencent-network-case-20261021/tencent-report.json)。
- [实际工具调用](tencent-network-case-20261021/tool-calls.json)、[预算与正文审核](tencent-network-case-20261021/verification.json)、[交付计数](tencent-network-case-20261021/delivery.json)、[实际读取失败](tencent-network-case-20261021/audit-read-failure.txt)、[应用截图](tencent-network-case-20261021/application.png)。

未运行单元、回归、冒烟、健康、类型／构建／lint 或其他门禁；这些结果不被用作本项证据。整体统一端到端能力验证尚未执行，完整 TODO 仍进行中。
