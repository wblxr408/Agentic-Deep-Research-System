# ADRS：面向研发团队的组织研究简报

## 要解决的任务

研发人员需要了解一家企业、一所高校或一个实验室在某个主题上研究了什么，采用哪些技术路线，实验结果依赖什么条件，以及哪些问题值得继续验证。论文索引、机构归属和合作关系容易混淆；摘要中的数字也可能缺少正文里的条件。

本演示聚焦一件事：**输入组织、主题、时间和来源范围，产出能回到原文核对的研究发展简报。** 首个案例是Microsoft Research在2024–2025年数据中心网络拥塞相关方向的代表性公开工作，明确区分缓冲共享与相邻的遥测传输，不推断内部战略，也不把两篇论文当作机构全部成果。

## SDK的实际作用

入口为[scripts/openminion_research.py](../scripts/openminion_research.py)，实现为[app/openminion_research.py](../app/openminion_research.py)，依赖固定OpenMinion0.1.7。

1. OpenMinion Agent实际调用两个登记的只读工具：搜索机构论文线索、读取原文。工具复用已有SearchAgent和HttpReader；论文页面可以补读首个合规PDF，各自保留证据与引用标识。
2. 同一SDK执行一次无工具的证据综合，从实际来源建立引文；采集草稿只作待核材料，不是证据。该阶段用于解决真实运行中工具草稿缺引文、上下文终止等问题，采集和综合的run标识／统计分别保存。
3. 最终报告再经SDK模型做逐项来源支持判定；可信代码核对引用编号、原文引语及偏移。模型置信度、自动支持状态、人工未复核分别保存。

CLI是明确的参赛入口；主应用原有LangGraph链路仍存在，Reflection和Report也使用共享的主张取证／最终审计模块。没有用导入SDK代替真实模型与工具运行，也没有为了演示增加委派框架。

## 如何复现和查看

配置本机LLM_*后，在仓库根目录执行；密钥不写入请求或交付产物。

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-openminion.txt
.venv/Scripts/python.exe -X utf8 scripts/openminion_research.py --request examples/organization-research.json --output data/research-runs/demo-01
```

必须使用新结果目录。先看report.md，再看result.json中的scope、plan、trace、evidence、documents、gaps和audit。SDK执行结束不等于研究完成；任务状态、原文支持情况与未覆盖范围要一起阅读。运行中展示工具参数、状态及关联PDF的结果。

可先查看[最新完整真实运行报告](acceptance/openminion-msr-r16-20261019T030501Z/result/report.md)和[交付证据](acceptance/openminion-delivery-20261018.md)：r16重新采集6来源及两篇完整PDF，约194秒、11次工具、13/13事实自动支持，任务completed，人工仍未复核。原r13的14/14后续复核及多次失败分别保存，不与新采集混为一谈。

来源可单选或多选：出版商／会议论文集、DBLP、arXiv、Google Scholar、官网。官网域名显式配置；Scholar只作发现，DBLP作元数据，arXiv需核对版本。选择范围在搜索过滤、原文请求和每次跳转前由代码执行。完整ACI、预算和错误恢复见[运行说明](openminion-research.md)。

## Cortensor生态结合

本实现保留日常模型和Cortensor provider配置入口。当前更合适的结合点是：日常模型负责带工具取证，Cortensor对固定公开材料做文字综合或独立核验；来源清单和主张片段可以作为不同推理后端的共同输入。

[Portal官方说明](https://docs-v2.cortensor.network/products/portal-and-api-gateway/)列出了托管文字接口和工具调用限制。独立Cortensor访问凭据尚未提供，网络推理未实测；替代HTTP用例不代表Cortensor网络证据。该边界与[SDK采用反馈](openminion-findings.md)一并提供，不以接入配置冒称实际网络运行。

## 本轮范围

交付是可运行的组织研究工作流及来源核验。跨学科评价指标、可调权重、网页来源多选面板及主应用会话联动仍按[组织实现计划](RESEARCH_DEVELOPMENT_PLAN.md)推进；不能把CLI成果当作这些功能已经上线。
