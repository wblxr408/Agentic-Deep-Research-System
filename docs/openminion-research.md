# OpenMinion 组织研究运行说明

此入口为本地公开资料研究：由 OpenMinion 0.1.7 实际驱动模型选择搜索／读取工具，再产出组织研究报告和原文支持核验。面向研发团队了解机构的研究问题、技术路线与研究缺口。高校、科研实验室、企业可通过请求中的多个带类型对象表达；跨学科指标和可调匹配面板仍按[组织实现计划](RESEARCH_DEVELOPMENT_PLAN.md)推进。

## 安装与运行

使用 Python 3.11+，在仓库根目录安装应用依赖，再安装可选 SDK：

```powershell
.venv/Scripts/python.exe -m pip install -r requirements-openminion.txt
.venv/Scripts/python.exe -X utf8 scripts/openminion_research.py --request examples/organization-research.json --output data/research-runs/msr-01
```

模型读取本地 `.env` 的 `LLM_PROVIDER`、`LLM_MODEL`、`LLM_API_KEY`、`LLM_API_BASE`，也遵循已有运行配置优先级。OpenAI兼容提供方映射到SDK的OpenAI provider；Anthropic单独映射。配置及密钥不写入结果，临时SDK状态按运行隔离。每次使用新输出目录，已有目录拒绝覆盖。

示例请求包含人工选取的公开原始来源入口；它们只作为线索，SDK仍须实际读取。原文不由外部预先生成的报告代替。可以编辑组织数组、主题、年份和来源入口。`seed_urls` 不必提供；来源选择失败时输出缺口，而不能引用模型记忆。最多8个组织、8个入口、24次工具调用、900秒；示例为18次／600秒。任务为代表性公开成果简报，资料不足时显式交付缺口，不能把它宣传为机构成果全量盘点。

运行中打印计划与工具状态，结束保存：

| 文件／字段 | 作用 |
| --- | --- |
| `result.json.scope/plan` | 原始研究范围与计划 |
| `trace` | 实际工具参数、完成／空／失败／拒绝、渠道尝试及证据标识 |
| `evidence` | 实际保留的原文、来源、获取时间及稳定标识 |
| `report.md` | Markdown结果、核验摘要与来源表 |
| `audit.claims` | 每项主张的引用、相关片段、原文偏移、模型判定与引语校验 |
| `coverage_status/coverage_missing/gaps` | 必需组织与研究维度的覆盖判定、缺项及模型说明的取证缺口；旧形态另存model_task_status |
| `structured_brief` | 每条研究事实的组织、工作、维度、正文与来源编号；另有建议问题和模型申明的缺项 |
| `sdk_run_state` | SDK运行状态，与研究任务是否完成分开 |
| `source_policy`、`source_uses` | 版本化的实际来源范围、域名及每条证据的用途 |
| `documents` | 原文格式、PDF页数／页码偏移、保留范围与截断状态 |
| `draft_report/raw_synthesis_report/invalid_output/stage` | 采集草稿、模型原始综合、不可消费输出及执行／失败阶段 |
| `initial_report/initial_audit/revision/plan_adjustments` | 初审失败时至多一次证据修订、原因和前后结果；audit始终对应最终正文 |

退出码0表示任务交付完成，2表示部分结果、取消或失败。SDK运行结束不等于研究完成；范围缺失、没有真实取证或任何必要研究事实未通过终审时保持partial。采集后固定执行一次无工具的SDK证据综合，输入有界原文清单、主张片段、原始草稿及采集失败，再对实际综合文本核验；草稿本身不是证据。保留采集draft/run/stats与synthesis_run_id/synthesis_stats，根预算耗尽、SDK工具错误或最终缺证不能靠格式转换变为成功。即使completed，仍须阅读gaps和audit；它不表示人工确认或机构完整研发策略已经被掌握。

最新[真实完整运行](acceptance/openminion-msr-r16-20261019T030501Z/result/report.md)及[交付证据](acceptance/openminion-delivery-20261018.md)：2026-10-19重新采集两篇全文，13/13事实自动支持，约194秒，人工未复核。

## 来源范围配置

`source_scope.groups`支持单选／多选。默认选择`publishers`、`dblp`、`arxiv`、`google_scholar`；官网需显式选择`official`并提供域名，不能由模型凭机构名称自行扩大范围。示例已加入微软官网。过去依赖任意公开网站的请求需要补充相应来源配置；没有配置时现在采用上述学术范围。

| 选项 | 用途和边界 |
| --- | --- |
| publishers | 出版商、会议论文集及评审平台的起始域名清单，可通过publisher_domains显式替换／扩充；清单不代表覆盖全部学科 |
| dblp | 论文发现、作者／载体／年份等元数据；不能仅凭索引页证明技术效果或机构路线 |
| arxiv | 预印本正文入口，需核对版本和同行评审状态；准入不代表已发表 |
| google_scholar | 仅发现线索；当前不自动抓取Scholar正文，不分配其正文引用 |
| official | 企业、高校、研究机构官网文档；通过official_domains指定，仍须核对实体、发布日期及每项主张 |

例如只研究官网与论文集：

```json
"source_scope": {
  "groups": ["publishers", "official"],
  "official_domains": ["microsoft.com", "cs.princeton.edu"]
}
```

`publisher_domains`省略时使用`app/research_sources.py`的可见起始清单；提供时替换该清单，可复制默认列表后补充目标出版商。仅接受具体域名，允许其子域，拒绝URL、通配符和常见公共后缀；当前不是完整公共后缀解析服务。机构官网域名由发起者确认配置，系统不声称自动验证域名所有权。不能用`official_domains`把Scholar等已知索引来源升级为原始论文证据。source_policy保存实际清单和版本，历史结果不随新默认清单改变。

搜索请求附加域名条件，并由可信代码过滤结果；搜索服务本身仍使用已有web渠道。初始原文请求、种子和重定向逐跳判定来源范围，跳转目标在DNS解析／连接前被拒绝。Scholar线索指向的论文需其出版商或arXiv来源组也被选中，才能继续读取。范围外记录`source_out_of_scope`，Scholar正文记录`discovery_only`；零条合规结果显示empty及被拒线索，不自动放宽范围。登录、验证码、付费墙或不支持的格式仍形成取证缺口。PDF支持文字提取，不包含OCR；扫描件、加密或损坏文件明确失败，选择来源并不保证所有文档可读。

这项配置已接入本地SDK命令行；网页的来源多选面板尚待接入，见[实现计划](RESEARCH_DEVELOPMENT_PLAN.md)。来源用途传给采集模型并保存在产物中，其是否足以支持主张仍依赖原文核验和人工判断，不是按站点自动判真。

## 工具 ACI

`search_organizations(query)`：公开网页检索线索，输入1–1000字符，返回最多4个合规URL／标题／摘要及来源用途。沿用现有SearchAgent及web渠道；每次最多3次底层尝试，限定剩余时长。轨迹保留实际查询、被过滤来源及原因。空结果与渠道失败在轨迹中可区分；搜索摘要不分配引用标识，需继续读取。不会由查询前缀授权切换到私人社交渠道。

`read_source(url, focus="")`：公开HTTPS原文读取，复用HttpReader的公共地址判定、DNS锁定与逐跳重定向检查；拒绝文件、内部地址和非只读请求。单次下载32MiB、此读取工具累计64MiB、每来源最多保留160000字符；失败读取按预留上界保守计费。该预算用于容纳本案例约26MB的正式论文，并不取消其他上限。搜索渠道另有每次最多3次底层调用。HTML优先main/article，移除导航、脚本和页脚，返回最多6条范围内链接并优先PDF；同时至多读取首个范围内非slides PDF，作为独立paper证据返回，linked_paper轨迹注明成功／失败。一次工具操作最多读取页面和这一个关联文档，各自遵循原有跳转及总字节预算。

focus按问题选择至多3200字符的原文窗口并返回start/end；有嵌套paper时父页面片段至多1800字符。模型仅接收当前片段涉及的页码，完整页码和保留正文仍在documents/evidence。英文论文宜使用英文技术词。同次运行重复URL复用正文，证据标识稳定，仍计工具次数；同页关联PDF失败不自动无限重试，模型可在预算内显式选择其他合规原文。

PDF沿用已有pypdf依赖，通过既有CommandRunner在子进程提取，最多15秒／80页；进程沿用超时和后代回收边界，解析器诊断不进入结果通道。保存每页number/start/end、total_pages、retained_pages和truncated；页码以下载PDF文件页序为准，可能包括会议封面。读取时返回的偏移与结果原文一致，不能用其证明未保留的内容。扫描无文字、加密、损坏、解析超时等返回`pdf_no_extractable_text`、`encrypted_pdf`、`invalid_pdf`或`timeout`，不生成成功证据。

工具次数和时间为可信代码控制；模型不能重置。SDK还限制循环步数及每轮工具次数。核验只接收已有片段，不授予更多工具。截止时间触发cancel，finally关闭runtime；临时状态与输出不连接应用内部资料，也不支持跨用户恢复。SDK0.1.7部分artifact工厂从进程环境选路径，因此本地入口串行运行并临时绑定OPENMINION_HOME／DATA_ROOT，结束恢复；此入口不能作为共享多租户服务直接部署。

## 原文核验的含义

Reflection按主张从全部已收集证据的正文选择片段。Report生成后重新核对实际最终主张，结果保存于既有`review_status.final_report_audit`并追加到报告；流式内容在完成前属于草稿。

核验保留三层结果：模型语义判定及置信度；可信代码核对引语是否存在于所引来源及其偏移；人工复核状态，默认`not_reviewed`。引用存在、引语存在均不能单独证明支持。模型判定缺失、错误引用、伪引语、矛盾、缺引用和超预算分别显示。SDK任务最多核验20项，应用Report最多40项；未覆盖项明确`not_checked`。应用核验遵循剩余token／时间预算，使用量并入报告阶段统计。

当前模型优先选择本条主张已提供的`excerpt_id`，程序取对应原文切片和偏移，`quote_match=selected_excerpt`。编号必须属于该主张所引来源和实际片段；未知编号、跨来源编号即使附有效旧式引语也拒绝。它减少PDF转写换行／断词的错误，不改变模型须核对完整语义的要求；选择了片段也不能单独证明支持。`model_quote`保留模型额外提供的文本，原文以`source_quote`为准。

引语先精确匹配；若仅有PDF换行或连续空白差异，可按空白归一化匹配，并把位置映射回原文。`quote_match`区分两者，`source_quote`保存原文切片；不更改数字、单位、词或标点。模型的quote和原文切片均可查看，不能用格式容错掩盖语义差异。

当前算法保守地把正文句子／表格数据行作为待核单元，标题、参考文献、Markdown表头、代码块和citation_notes元信息不计入，并保护vs.等常见英文缩写；其覆盖率并非经标定的事实正确率。多条件主张需要模型整体判断；一个有效引语仍可能不足以覆盖全部细节。人工核对结果不由模型生成。

核验同时识别[1]和[citation:1]，按真实证据序号绑定；SDK展示规范化为后者，保留模型原文。中文待核主张在预算内生成英文检索词，再到已引来源选择最多3个相关窗口，保留retrieval_query和偏移；查询不是事实。失败仍回退并记录错误，不能自动判支持。

窗口排序对来源内反复出现的词降权，减少长论文标题遮蔽后部限制的情况。模型选择原文片段编号，语义仍根据全部选中上下文判断，不要求一个锚点复述所有条件。旧式quote输出继续进行精确／仅空白归一化检查，不去除断词或改写标点。词面检索仍可能遗漏内容，不能视为完整语义检索保证。

多窗口优先补未覆盖的查询条件，每个片段可额外保留最多400字符后文，避免数字紧随命中点却被截掉；审计批次的总字符预算继续生效。核验契约同时明确传入SDK调用消息，避免只靠返回后的typed校验发现字段形状错误。

初审有待核项时至多一次无工具修订，保留初审和计划调整原因，再审计最终正文。修订不能缩小原任务以求通过；仍缺必要证据则partial，不无限循环。具体真实失败和新行为证据见[综合修复记录](acceptance/sdk-synthesis-recovery-20261018.md)。

综合或证据修订若返回不满足typed schema的JSON，在同一根时限内可各执行至多一次无工具格式修复；`format_recoveries`保存失败原文、恢复状态及成功run标识。它与事实修订不同，不补新来源或添加事实；修复结果仍须通过覆盖检查和最终核验。二次格式失败直接保留失败，SDK异常未提供的失败调用统计记为未知。

事实修订只重传prior_findings、来源编号和最多12000字符审计问题，每项至多3个片段，遗漏片段数与问题标识明示；不再重复整份综合来源包。预算仍可能不足，遗漏不能默认为已修复，最终正文必须重新审计。

每次SDK核验如发生typed格式异常且根预算足够，至多重试一次无工具JSON输出；`audit_invalid_outputs`和`audit_format_recoveries`保留失败正文及恢复状态。二次失败保持待核，不按模型散文中的“支持”直接通过。

综合现在返回逐条findings，由程序生成报告，每项工作覆盖发表归属、问题、方法和成果条件；questions单独作为后续验证建议。coverage_missing检查请求组织、每项工作的必需维度和引用范围，不把未要求的全量成果普查或独立复现实验变成完成条件。completed还要求所有研究事实终审通过、真实采集成功且根预算未耗尽；仅有少量支持项不能完成。范围文字由真实请求、来源数及PDF数生成，建议与取证缺口明确不计作已证实结论；audit.scope注明research_findings_only，人工状态仍为未复核。

模型自行提出的缺项保留在`model_missing_requirements`及原始结构化输出中，供复核时参考；它们不自动变成请求范围或验收要求。请求覆盖检查与模型语义支持核验分别保存。

## Cortensor结合方式

用户选择同时保留日常模型和Cortensor。当前入口可分别选择配置的日常模型及SDK原生Cortensor provider，同一个JSON请求可以保存到不同结果目录。

```powershell
.venv/Scripts/python.exe scripts/openminion_research.py --request examples/organization-research.json --output data/research-runs/cortensor-01 --provider cortensor
```

`CORTENSOR_API_URL`、`CORTENSOR_API_KEY`、`CORTENSOR_MODEL`、`CORTENSOR_SESSION_ID`、`CORTENSOR_API_MODE`从`.env`或环境读取。直接Router的completion路径需要实际session；Portal的`/v1`路径由网关管理session，使用被授权的模型别名，例如官方示例的`oss-20b`。不能把日常DeepSeek密钥用于Cortensor。

**现阶段适配建议：日常模型负责带工具的取证，Cortensor优先用于已有材料的文字综合或独立复核。** [Portal官方说明](https://docs-v2.cortensor.network/products/portal-and-api-gateway/)当前明确不开放托管接口的tool/function calling；SDK原生Cortensor另有hybrid／文本工具协议，是否可用须对获配端点实际验证。替代HTTP提供方用例仅证明SDK适配链路，不能证明Cortensor网络已实跑，也不能据此保证Portal工具支持。

[Hackathon #5官方要求](https://docs-v2.cortensor.network/ecosystem/hackathon-5/)要求SDK有实际运行作用和真实模型演示；Portal为可选且访问受限。没有Cortensor凭据时仍可完成SDK研究任务，并在材料中如实记录接入边界。2026-10-18核对。

## 安全与验证范围

设计的完整11项适用性评估见[OpenSpec设计](../openspec/changes/add-openminion-research-workflow/design.md)。采用A2ABreak v1.0：03上下文归属与跨租户隔离、07Webhook归属验证与受控出站（本入口只采用出站部分）、08结构化授权请求与权限不放大、10委派环路检测与全链预算（无委派，仅预算部分）、11中断任务租约与有界资源回收（期限与回收部分）。引用其“工程解决方案／验收办法”章节；这些是本地实验方案，不是官方修复认证。

本次新增行为用例包含真实SDK对替代HTTP模型的搜索→读取→审计、取消前不采集、后部证据选取、最终矛盾引文和伪引语／错误引用。未执行旧能力或安全回归；真实外网运行与失败另见验收产物和[SDK反馈](openminion-findings.md)。
