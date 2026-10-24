# OpenMinion组织研究交付证据

核对环境：2026-10-18至19日，Windows、Python3.11.7、OpenMinion0.1.7、DeepSeek。密钥仅在本机配置，不包含在请求及产物。

## 可查看的结果

**最新完整运行r16为completed**：[研究简报](openminion-msr-r16-20261019T030501Z/result/report.md)、[完整结果](openminion-msr-r16-20261019T030501Z/result/result.json)、[执行日志](openminion-msr-r16-20261019T030501Z/console.log)。它重新进行了真实采集、综合与终审，193.797秒、11次实际工具调用、6来源、两份全文PDF（19页／17页，均未截断），读取计费28011540字节，根预算未耗尽，研究及核验errors均为空。

最终13/13项事实自动支持，13项原文片段锚点有效、coverage_missing为空，未触发修订或格式恢复。模型置信度0.8–0.97、人工状态全部not_reviewed。采集SDK run为fd491cf29f784d78a30e05c8fc3cbc64，综合为a007d9564a0f4cc49ba95198603e33f4；SDK自身stats的口径与应用实际trace分列，不能把它的4次tool_calls冒称全流程只有4次调用。这个单次成功案例不证明跨任务稳定性或模型判定的事实准确率。

[完整事实复核后的研究简报](openminion-msr-r13-reaudit-d-20261018/report.md)与[逐项审计](openminion-msr-r13-reaudit-d-20261018/audit.json)保留14/14自动支持、14个有效原文引语位置、独立模型置信度和人工not_reviewed；核验错误为空。它沿用[r13真实SDK任务](openminion-msr-r13-20261018T150637Z/result/result.json)的报告事实和原文，没有新采集，也没有把原partial记录改成成功。

r13实际采集14次工具、6来源和两份全文PDF，313.8秒；Reverie保留19页／86150字符，InvisiFlow保留17页／83637字符，两者均未截断。其原初审／修订／终审仍在原产物，原终审11/14。新整篇复核使用SDK执行9次返回的调用，包括检索词和各批判定；每次run标识和SDK统计可在复核JSON查看，不冒称失败调用的成本也已完整计入。

r15为partial（11/14），r16为新采集完整成功；两者分别保留，未把旧产物改成成功。

## 需求与实现对应

| 用户目标 | 实现与证据 | 实际边界 |
| --- | --- | --- |
| SDK实际驱动模型与搜索／读取 | app/openminion_research.py、scripts/openminion_research.py；r13的scope/plan/trace/evidence/documents与采集、综合、修订ID | 本地公开资料CLI；不是共享多租户HTTP服务 |
| 有用且专注的组织研究场景 | 2024–2025 Microsoft Research数据中心网络代表作；两篇工作各有发表归属、研究问题、方法、成果及限制和后续建议 | 有界代表作简报，不能据两篇论文推断内部战略或路线转向 |
| 区分工作主题 | Reverie的问题／方法是交换机缓冲共享；InvisiFlow是遥测数据传输，属于拥塞相关的相邻工作 | 这是按论文问题所作的场景归类，不把遥测效果改称拥塞控制效果 |
| 结论对应原文 | 全保留正文检索、双语词、同源多窗口、位置及引语核对，最终正文重新审计 | 自动支持是模型语义判定；原文匹配不是事实真值保证 |
| 模型置信度与人工状态分别呈现 | audit.claims中的model_verdict/model_confidence/source_checks/human_review_status | 未收到人工记录，全部仍not_reviewed |
| 学术和官网导航范围可选 | source_scope的五类单多选、显式官网域名、版本化出版商清单；搜索过滤及每跳连接前准入 | Scholar只发现，DBLP是元数据，arXiv需核版本；网页选择面板另按组织规划实现 |
| Cortensor结合评估 | docs/openminion-research.md、docs/openminion-findings.md | 原生provider配置已保留；缺独立凭据，网络推理未实测。Portal托管工具调用限制见官方文档 |

## 真实失败与修复

r8综合上下文超限；r11引语换行差异和模型扩张范围；r12结构数组超上限；r13长标题及跨窗口条件遗漏；r14网络失败消耗读取预算、修订上下文超限。失败原文与partial/failed状态均保留，详见[修复记录](sdk-synthesis-recovery-20261018.md)。

整篇复核A／B因返回results而非verdicts等schema问题为0/14，不作为成功证据；显式携带核验契约后C为12/14。窗口按来源内逆频率和新条件覆盖选取，并补最多400字符后文后，D为14/14。所有四次产物分开保留；这是本案例的逐步修复结果，未测重复稳定性。

修订上下文目标A仍超限；进一步去掉重复报告与完整来源包，只保留prior_findings、来源编号和最多12000字符审计问题后，B实际SDK返回有效简报，coverage_missing为空，1次模型、0工具、5957输入tokens／1117输出tokens。见[目标B产物](openminion-revision-context-target-b-20261018.json)。它验证当前上下文失败的修复，不当作新采集或另一轮完整研究。

## 本次检查

| 当前新增消费目标 | 实际结果 |
| --- | --- |
| PDF空白差异、错误单位、模型不得扩大验收范围 | 先2failed1passed，再3passed1.36秒 |
| 格式修复保留事实、二次失败停止 | 先2failed，再2passed4.39秒 |
| 重复长标题下仍能选后部限制 | 正确fixture的预期片段缺失RED后，1passed0.66秒；fixture字段错误不算行为RED |
| 冻结真实InvisiFlow结果及拓扑条件 | 先缺144服务器所在窗口的RED，再1passed0.78秒 |
| 真实模型核验当前三项失败 | 3/3支持，见openminion-audit-target-20261018.json，仅该目标 |
| 整篇SDK模型终审 | D的14/14支持，原文位置有效，errors为空；人工未复核 |
| 片段编号及引用消费 | 先3RED，再3passed1.14秒；有效片段自动附原文，未知／跨来源编号拒绝，不能用正确旧式引语绕过 |
| SDK核验格式恢复 | 先2RED，再2passed7.13秒；只重试一次，再失败停止，原失败保留 |
| 新采集完整任务 | r16：13/13自动支持，完整覆盖、两全文、0研究／核验错误，completed |

未创建、修改或运行旧回归、smoke、启动／导入、存在性或hash探针。类型／规范检查与实际结果分别记录；上面的替代响应消费用例不冒称外网证据。前期论文读取、来源准入、结构化facts及一次修订的当前变更证据见各验收记录，未重复运行旧套件。

最新修改模块py_compile通过；OpenSpec严格检查通过。代理已审阅报告范围、两篇工作的四个必需维度、13项机器状态／片段位置、页码及真实轨迹；这不计为人工事实复核。报告中“未报告生产部署”这类否定判断仍依赖模型对所给评估描述的推断，不能由没有检索到部署材料证明全世界不存在部署；如用于研发决策，应回看全文和作者说明。报告的模型取证缺口也不等于系统未保留全文。

## ACI与安全适用范围

采用本地A2ABreak v1.0“工程解决方案／验收办法”章节：A2AB-03上下文归属与跨租户隔离（新目录／session和本地CLI串行环境）；A2AB-07 Webhook归属验证与受控出站（仅使用只读公开HTTPS、DNS锁定和每跳域名准入部分）；A2AB-08结构化授权请求与权限不放大（两工具固定登记、配置范围固定）；A2AB-10委派环路检测与全链预算（无委派，仅全链预算）；A2AB-11中断任务租约与有界资源回收（根期限、取消、受控PDF子进程及finally）。这些是本地源文核对后的实验方案，不是官方修复认证或完整安全保证。

全部11项适用性、非适用理由、执行点及验证边界见[OpenSpec设计](../../openspec/changes/add-openminion-research-workflow/design.md)。当前新增边界用例及真实运行只证明其实际覆盖范围，不扩张为旧能力安全回归。

## 复现与后续范围

按[运行说明](../openminion-research.md)配置本机LLM_*，使用examples/organization-research.json及新目录运行CLI。公共搜索、下载和模型输出会变，不能保证重复得到同样论文或全部事实自动支持；失败时保留范围、轨迹、证据、缺口及审计。

跨学科评价、权重、组织网页多选和主应用会话联动继续由另一份[26项实现计划](../RESEARCH_DEVELOPMENT_PLAN.md)拥有。未提交、推送、发布、报名或录制参赛视频。Cortensor实际接入需获配独立端点与凭据。
