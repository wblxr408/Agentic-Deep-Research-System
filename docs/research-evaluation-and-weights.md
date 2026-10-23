# 学科评价适配与权重配置

2026-10-19，OpenSpec 任务 2.1–2.6、3.1 的基础模块及预览 API。实现为 `app/research_evaluation.py`、`app/research_matching.py` 普通函数，复用研究路由登录认证。3.2–3.5 的实际评分、区间和重排见[证据快照与匹配预览](research-matching-preview.md)；正式研究链路、个人持久预设及前端仍按后续任务实施。

## ACI：入口、输入输出与执行边界

| 操作 | 输入／用途 | 返回／失败后动作 |
| --- | --- | --- |
| `POST /api/v1/research/evaluation/preview` | 学科、成果类型、载体 `target_id`、可选论文 `work_id`、发表年、指标年、可选指定 `editions` 与来源批次 | 20 项体系分别返回适用性、状态、原始记录、版本和来源接入表；缺失时保留原因，可授权导入或改变明确的快照条件。 |
| `POST /api/v1/research/evaluation/openalex/normalize` | 已取得的 OpenAlex `work` 原始 JSON、`retrieved_on`、明确的 `citation_cutoff` | 输出 OpenAlex 提供方的 FWCI／引用百分位来源批次；空值仍为空，不生成 CNCI，不把引用次数换算为专有指标。 |
| `POST /api/v1/research/weights/preview` | 预设、自定义或覆盖权重、启停、成果表现分组、指标权重与等级映射版本 | 原始展开配置、各层生效权重、映射、规则／预设／配置版本；仅生成偏好配置，不为候选评分。 |

三个接口同步计算，均无持久副作用、不访问来源 URL、不调用外部服务或模型，也不读取其他用户会话资料。返回 `external_sources_checked: false` 的数据预览不代表外部采集或事实核验。使用内置快照时仅从固定的 `config/evaluation/public-snapshots.json` 读取公开记录；调用方无法指定本地路径。

合法请求返回 200。参数非法返回 422 `detail`，包括位置与拒绝原因；修正后可重试。来源不可用、未覆盖及证据冲突是单项业务状态，研究其他部分可以继续，不暗中改用当前年份、其他提供方或范围外来源。本地计算无外部工具重试或网络超时，沿用应用 HTTP 生命周期，新增模型／外部请求预算为零。真实采集仍由现有授权渠道与预算控制，不因导入标签而新增权限。

评价请求最多 100 个来源批次，每批最多 10000 条记录、最多 20 个学科和 20 个指定体系版本；预览为单个精确身份。权重最多 6 个维度、20 个指标和 10 个等级映射，每个映射最多 10 档。应按目标、年份和来源切分导入批次，避免把整个资料库放进一次预览。

## 评价请求示例

```json
{
  "disciplines": ["computing"],
  "output_type": "conference_paper",
  "target_id": "dblp:conf/nsdi",
  "publication_year": 2022,
  "metric_year": 2022,
  "editions": {"ccf": "2022"}
}
```

`output_type` 支持 `journal_article`、`conference_paper`、`preprint`、`book`、`software`、`dataset`。`publication_year` 表示成果发表背景，`metric_year` 明确选择评价快照年份；二者可以不同，返回记录保留原值，不自动将当前目录用于历史评价。`editions` 进一步限定体系版本，找不到指定历史记录则标缺失。会议 `track` 默认为 `main`，可为 `workshop`，不会继承主会等级；期刊及论文级匹配分别使用 `journal`、`work` 轨道。

对象身份使用调用方核定的规范 ID，例如 `dblp:conf/sigcomm`、`issn:0047-2506`、`openalex:W1951724000`、`doi:10.1000/example`。匹配为**身份＋轨道精确相等**，不按标题或简称模糊套等级。期刊和论文同时查询时，`target_id` 放载体身份，`work_id` 放论文身份；本模块不自动核实输入身份。

初始学科分派识别 `computing`／`computer science`／计算机、`materials`、`business`／`economics`／`management`／商科等名称：CCF／ICORE 限计算机，ABDC／AJG 限商科相关期刊，期刊分区与期刊指标不用于会议；通用期刊／引用体系仍需具体来源证明覆盖。未知学科不会自动套用计算机或商科目录，复杂学科分类继续由后续任务细化。

### 来源与导入契约

`sources` 数组中的每项包含 `source_id`、`scheme_id`、`edition`、`metric_year`、`provider`、`source_url`、`retrieved_on`、`access`、`coverage` 和 `records`。来源 URL 必须为 HTTP(S)。`access: authorized_import` 必须显式 `authorized: true`；这是调用方的授权声明，并非系统验证了许可证。`public` 输入也不会自动获得已核实标志。

每条记录包含 `target_id`、`track`、`category`、`raw_value` 和可选 `status`（`available`、`not_indexed`、`data_missing`）。有数据时保留原始值；后两种状态必须为空值。每项评价记录返回来源 ID／URL、获取时间、提供方、版本、年份、类别和 `match_basis: exact_identifier_and_track`。调用方记录标 `evidence_status: caller_provided`，随版本发布的公开快照标 `public_source_snapshot`；两者都不等于完成运行时外部核验。

分区／目录只接受体系自己的等级，数值指标拒绝负值、非有限值，收录字段使用布尔值。JCR 分区与中科院分区分别保留，多个类别、多个提供方和年份不合并；不默认取最好分区。当前没有类别自动选择或评分。

`availability` 区分 `available`、`not_indexed`、`not_applicable`、`data_missing`、`source_unavailable`、`conflict`。部分样本没有命中只能返回 `data_missing`；明确完整版本的不存在或显式未收录记录才能表示 `not_indexed`，完整性依赖所声明来源。相同提供方、类别、版本、引用截止日下数值冲突返回 `conflict` 并保留记录；不同提供方的指标独立保留。收录布尔值 `false` 仍是一个可用的否定记录，不被填成最低等级。

## 逐来源接入状态（2026-10-19）

以下是当前仓库实际数据状态；授权导入行为用替代输入验证，不代表已取得商业数据。

| 体系／来源 | 当前适配与实得记录 | 未覆盖部分／后续动作 |
| --- | --- | --- |
| CCF | 精确目录适配；已读取 CCF 原始 2012、2022 PDF 的公开镜像，保存 NSDI／SIGCOMM 记录及来源 | 官网本次返回验证页；镜像原文版本如实记录，未取得 2026 完整官方目录。2012 NSDI B、2022 A 不代表每个中间年份的生效日。 |
| ICORE／CORE | 官方门户读取 SIGCOMM 的 CORE2023、ICORE2026 记录，分别保留版本 | 仅已取得的会议样本，不是完整目录；不替代 CCF。 |
| WoS SCIE／SSCI／AHCI／ESCI | 四类独立收录记录适配，授权导入 | 未取得当前用户授权名录／覆盖年份；无数据时来源不可用。 |
| Scopus 收录 | 独立收录与年份适配，授权导入 | 未连接用户授权的数据服务。 |
| JCR JIF／Q1–Q4／JCI | 三项独立适配，保留多类别与多年度授权导入 | 未取得真实 JCR 数据；不从网页碎片或期刊相似名称推测。 |
| 期刊分区表（中科院分区） | 独立分区及版本适配，授权导入 | 未取得已授权目录；不由 JCR 分区换算。 |
| CiteScore／百分位 | 独立数值适配，百分位保留 0–100 标度 | 未连接真实数据，支持授权来源记录。 |
| SJR | 独立提供方、类别与年份适配 | 未采集真实 SJR 数值；可授权导入并保持来源。 |
| SNIP | 独立数值适配 | 未连接真实数据，不能用 SJR／JIF 近似替代。 |
| ABDC | 读取官方 2025 工作簿中 2010／2013／2016／2019／2022／2025 工作表，保存 JIBS 的印刷／在线 ISSN 样本 | 样本覆盖仅一家期刊，其他期刊缺失不等于未收录。 |
| AJG | 自身等级与版本适配、授权导入；官方入口提供 AJG2024 登录／注册 | 当前没有登录授权，未保存真实等级数据；与 ABDC 分别呈现。 |
| 论文引用百分位 | OpenAlex 原始字段适配，保留 0–1 标度及标准化背景；已取得一篇真实论文 | 不与仅按年份的百分位或 CiteScore 百分位混用，不宣称全库覆盖。 |
| CNCI | 仅允许带 `Clarivate InCites` 提供方与完整背景的授权导入 | 未获得真实 InCites 数据，不能用自算平均引用比冒名。 |
| FWCI | 已取得 OpenAlex 的真实提供值并适配；允许明确标为 `Elsevier SciVal` 的授权导入 | OpenAlex 与 SciVal 输入数据和分类不同，不互换为同一官方数值。 |

原始 OpenAlex 响应、公开目录样本及实际预览输出见 [来源证据目录](acceptance/evaluation-sources-20261019/)，复现上下文见 [交付记录](acceptance/organization-evaluation-20261019.md)。内置数据是固定的部分覆盖快照，预览不会自动刷新；`use_public_snapshots: false` 可仅使用当前请求的数据。

### 论文级引用背景

可用记录须提供发表年、文献类型、学科类别和引用截止日。CNCI 强制命名提供方 `Clarivate InCites`，FWCI 强制区分 `OpenAlex`／`Elsevier SciVal`。这些字段用于追溯，不由接口推测授权或核实来源。

OpenAlex 归一化入口保留原提供方数值、子领域 ID／名称、`updated_date`、发表年与文献类型。请求显式指定引用截止日且不得晚于取得日期、早于发表年；归一化不会代替调用方核实截止口径。本次真实 2015 年样本采用公开说明中的发表年及后三年窗口，截止 2018-12-31，快照年份 2026，提供方更新时间另存。OpenAlex 的说明解释了其引用窗口和与其他数据库输入的差别，不能仅因指标同名就合并：[OpenAlex 引用与 FWCI 说明](https://help.openalex.org/data/works/citations/)。

## 权重与等级映射

```json
{
  "preset": "custom",
  "config_version": "my-config-v2",
  "weights": {"topic_relevance": 6, "evidence_completeness": 4, "cooperation_complementarity": 0}
}
```

上例生效 60%、40%、0。维度标识为 `topic_relevance`、`research_alignment`、`output_performance`、`evidence_completeness`、`recency`、`cooperation_complementarity`。

`research_development` 预设为 35／20／20／15／10／0，`cooperation_discovery` 为 30／15／15／15／10／15。预设支持局部覆盖；`custom` 只采用显式提供的维度。值可为数字，或 `{"weight": 6, "enabled": false}`；关闭时保留原值，生效为零。恢复预设可重新发送仅含预设名的请求。个人方案已通过[个人预设 API](personal-research-presets.md)保存和版本化，5.2 的[编辑器](organization-weight-editor.md)已接入真实选择、编辑、恢复及保存研究。

成果表现内部由 `performance_groups` 配置 `venue`／`paper` 组（初始各 1），`metric_weights` 配置各体系相对权重。先组内分别归一化，组权重另行归一化；缺省指标列表为空，表示尚未配置指标，不能视为已经对候选完成评分。关闭父维度后，子层生效值为零，允许保留全零子层；活动层全零则拒绝。负值、非有限数、布尔值和未知键拒绝，归一化采用先缩放再求和以避免大有限值溢出。

输出包括展开的 `raw_config`、`effective_weights`、`effective_groups`、组内 `effective_metric_weights`、`config_version`、`adrs-weight-rules-v1`、`adrs-presets-v1` 和等级映射。生效指标权重是组内比例，不能与父维度权重混读为全局贡献；实际特征匹配、同源上限计算与贡献解释分别属于 3.2、3.3。

`mappings` 每项提供 `scheme_id`、非空 `version`、`scores`。必须完整覆盖体系自身的有序档位，分值为 0–1 且保持档位顺序：CCF A/B/C、ICORE A*/A/B/C、ABDC A*/A/B/C、AJG 4*/4/3/2/1、JCR Q1–Q4、中科院 1–4。ICORE 地区专用等级和 Unranked 可保留原目录值，当前不自动加入通用有序分值。

未提供映射时使用 `adrs-preference-map-v1` 初始等间距偏好，明确为尚未业务标定的产品规则，不建立不同体系间的官方等价。每次返回都是该请求的配置快照；匹配区间和同证据重排已由[3.2–3.5](research-matching-preview.md)实现，主研究配置冻结及暂停恢复见[运行 ACI](organization-research-runtime.md)，完整评价与匹配仍待后续任务。
