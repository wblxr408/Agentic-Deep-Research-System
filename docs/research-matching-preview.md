# 证据快照与可解释匹配预览

2026-10-19：OpenSpec 3.2–3.5。计算位于 `app/research_matching.py`，快照读写位于 `app/db/matching.py`，入口复用研究路由认证。权重配置沿用[3.1 契约](research-evaluation-and-weights.md)，对象与家族沿用[范围契约](organization-research-scope.md)。

2026-10-21：5.3 已从本人已完成研究接入保存成果／原文来源转换、真实 PostgreSQL、结果页重排和独立新研究动作；见[会话重排 ACI](research-reranking.md)与[端到端记录](acceptance/organization-rerank-20261021.md)。当前自动分项是标题词面与有界时效，完整评价／特征仍有缺口。分值表达声明口径及偏好，不是科研质量定论或合作成功概率。

## 使用顺序与 ACI

| 接口 | 用途、输入 | 输出与副作用 |
| --- | --- | --- |
| `POST /api/v1/research/matching/snapshots` | 显式提交已整理的范围、证据、比较组、候选研究家族、特征／评价记录及硬条件；可绑定当前用户已有 `session_id` | 201 返回 `snapshot_id`、证据截止日、`matching-evidence-v1`。仅在现有 PostgreSQL 中新增不可覆盖的快照，不启动研究、不取证。重复创建形成新 ID。 |
| `POST /api/v1/research/matching/preview` | `snapshot_id`＋`configuration`（3.1 权重契约） | 200 返回生效配置、比较组、完整结果／待补证、区间／覆盖率、贡献、依据和排除原因。数据库只读，不修改原快照、历史结果或事实，不新增模型／采集请求。 |
| `POST /api/v1/research/{session_id}/matching/snapshot` | 本人已完成会话，无来源覆盖输入 | 按原执行与转换版本复用／创建快照，返回原冻结偏好和来源说明；不取证。客户端不能自报服务端转换标记。 |

两项均要求现有登录会话或已授权 API 身份。服务端从认证主体写入 owner，不接收调用方指定 owner。保存时若绑定会话，单条参数化 SQL 先检查会话归属再插入；每次读取同时检查快照 owner 和所绑定会话当前归属。不存在及其他用户的 ID 均返回 404，不能靠更换 ID 访问。当前无快照更新、共享或覆盖接口。

预览请求示例：

```json
{
  "snapshot_id": "创建接口返回的 UUID",
  "configuration": {
    "preset": "custom",
    "config_version": "preference-v2",
    "weights": {"topic_relevance": 6, "evidence_completeness": 4}
  }
}
```

预览只接受 ID 与配置，附带 `candidates`、范围或来源 URL 等覆盖字段会返回 422。非法数值、未知证据引用、重复家族、比较口径冲突等也返回 422，修正输入后重新创建快照；已有快照保持原样。证据不足返回受限业务结果，不自动发起补证。

来源 URL 仅作为元数据保存，不下载、不执行。计算不需要模型或采集预算；数据库操作沿用应用连接和超时配置，没有新增外部重试。CPU 计算在工作线程执行，避免占用异步 HTTP 事件循环。若需新证据，应通过明确的新研究／取证操作准备材料后创建新快照。

## 快照数据契约

| 字段 | 结构与规则 |
| --- | --- |
| `scope` | 已有 `OrganizationResearchScope`：对象类型、可选具体实体、学科、主题、日期。具体选择必须与候选实体记录一致；超出所选类型的其他候选可以保留，预览明确排除。 |
| `evidence_cutoff`、`evaluation_versions` | 显式证据截止日和评价版本清单；证据／指标的获取日期不得晚于截止日。版本清单是快照声明，实际评价记录及比较组仍独立保留其版本。 |
| `evidence` | `evidence_id`、`source_url`、`retrieved_on`、`verification_status`（`confirmed`／`unreviewed`）。最多 10000 条，ID 唯一。确认状态是当前 owner 对输入材料的声明，不是接口独立完成了来源核验。 |
| `groups` | 最多 50 个比较组：唯一 `group_id`、`discipline`、`output_type`、`metric_year`、`category`、`feature_rules` 与 `metric_rules`。每组固定适用维度和规则，对所有候选采用同一口径，不跨组建立统一榜。 |
| `candidates` | 最多 200 个对象，每项为 `entity`、`observations`、可选 `facts`；同名对象不凭名称合并。总观察数不超过 5000，每对象最多 1000 个。 |
| `observations` | 一条代表某对象在某比较组中的一项研究家族：`family_id`、`group_id`、可选 `published_on`、`title`、可选 `abstract`、非空 `evidence_ids`、`features` 与 `metrics`。同对象／同组／同家族重复拒绝，扩展版须先按 1.4 合成家族。 |
| `facts`、`required_relations` | 关系为 `funding`、`coauthorship`、`project`、`joint_lab`；事实提供 `value`、`verification_status`（`confirmed`／`unknown`／`contradicted`）与证据 ID。硬条件只接受值为 true、事实已确认且引用证据均已确认的记录。 |
| `required_metrics` | 每项含 `scheme_id`，再选择 `allowed_values` 或非负 `minimum` 中的一种。按原始值及确认依据过滤观察，不能拿匹配分满足收录、等级或资助条件。 |
| `session_id` | 可选的已有会话 UUID；服务端检查归属。省略时建立属于当前用户的独立证据快照，供整理材料后的预览使用。 |

所有证据 ID 必须存在。每项特征／指标最多引用 50 条证据；标题、说明及版本标识使用有长度上限的字段，摘要最长 12000 字符。元数据和调用方的“确认”声明不会授予资料访问或联网权限，响应明确标记 `verification: frozen_owner_provided_evidence`。

### 特征与比较口径

`feature_rules` 按维度选择如下版本化规则；`output_performance` 必须由指标计算，不能直接填一个绕过父级上限的值。

| 规则 | 适用维度及计算 | 依据 |
| --- | --- | --- |
| `provided_v1` | 明确的人工／上游量表值 0–1，或未知 null | `features` 提供 `value`、`reason`、`evidence_ids`，非空值必须有证据；不宣称模型已经自动判断了相关性或互补性。 |
| `token_overlap_v1` | 主题相关性＝主题中不同词项被标题／摘要覆盖的比例 | 英文按小写词项，中文按二元片段；透明的词项覆盖启发式，不代表语义精度。 |
| `linear_recency_v1` | 时效性＝发表日在研究时间段中的位置，单日区间为 1 | 使用通过日期硬筛选的发表时间及冻结范围。 |
| `confirmed_sources_v1` | 证据完整度＝该观察明确列出的证据中，owner 已确认来源的比例 | 是相对输入证据清单的完整度，不能推导为现实证据全集已覆盖。 |

来源、理由及规则版本进入分项贡献。量表值不可超出 0–1，未知仍为 null；跨研究家族聚合采用等权平均，并保留家族数量、ID 及已知覆盖比例。未知家族的取值区间保留为 0–1，不能从分母中移除。

`metric_rules` 每项固定 `provider`、`edition`、`normalization_version` 和适用的 `citation_cutoff`。观察中的 `metrics` 按体系键提供 2.1–2.5 的完整 `record`、可选 `normalized_value`、证据 ID 与理由。提供方、版本、年份、类别及引用截止日必须与组一致；论文级记录还须与发表年一致。

原始等级／数值在快照入口再次复用评价适配器校验；材料期刊不能声明适用 CCF，会议不能套期刊分区。JCR 等多类别必须先明确当前组的类别，不自动取最高分区。目录等级由当前配置的有序映射转换；其他数值使用有声明版本和理由的归一化量表，缺失归一化值仍未知，不能直接把 JIF 或 FWCI 加到总分。

## 硬筛选、分层贡献与不确定性

先排除范围外类型、未选实体及不满足已确认关系条件的对象，再筛选日期、学科和明确指标条件下的家族；无合格观察的对象不进入评分。所有排除保留理由；权重再高也不能覆盖硬条件。评分读取事实，原始事实随结果呈现，不由评分生成或改写。

每个比较组先一次性确定适用维度并归一化，再对候选采用同一集合。指标权重在适用的载体／论文组内分配，指标之间再分配组预算，最终受 `output_performance` 父维度上限约束。例如根权重主题 80%、成果表现 20%，增加 JIF、JCR 分区或 JCI 时，三项合计最多贡献 20 分，不会变成各贡献 20 分。

组不适用的配置项统一排除；某候选缺项时保留对应预算，不临时补权重。过滤后只有零权重指标时，成果表现按未知区间保留；没有任何适用维度时，组返回 `comparison_status: no_applicable_dimensions`，分数和区间均为空，避免显示虚假零分。

`lower_bound` 是贡献下界，`upper_bound` 加上未知部分及日期精度的可能贡献，`coverage` 是按有效权重计算的已知比例。只有全部生效分项已知且贡献区间退化为点时，才返回 `score` 并进入组内 `complete` 降序列表；其他进入 `pending_evidence`，按实体 ID 稳定展示，不按区间中点强排。已知零值仍计为已覆盖，100% 覆盖不代表有精确发表日或确定总分。

标准案例：主题与证据权重 60%／40%，甲的主题为 0.9、证据未知，则下界 54、上界 94、覆盖率 60%、最终分数为空；乙为 0.8／0.7，则完整分数为 76。两者区间重叠，`definitely_better` 为空。只有同组一方下界严格高于另一方上界，才返回确定更匹配关系；不同组不产生该关系。

响应同时保留每个维度和指标的权重、上下界贡献、来源 ID、解释、规则版本、组上下文、家族规模、评价版本、证据截止日及原始／生效配置。`external_requests` 固定为 0；预览没有调用搜索、浏览、评价数据采集或模型的代码路径。

## 存储、迁移与验证边界

新增 `research_matching_snapshots` 表：UUID、owner、可选会话、完整 JSONB 证据载荷、创建时间；以 owner 建索引。沿用项目 PostgreSQL，没有新增数据库服务、Agent 或编排器。独立快照表用于保留多个不可覆盖的证据版本，避免重排改写可变的运行状态或原始研究请求。普通初始化和迁移入口均接入同一 DDL；现有会话不改写、不回填，绑定会话删除时其快照级联删除。

2026-10-19 的历史交付有 22 个新增 HTTP 行为用例，使用 SQLite 适配 asyncpg 调用形状；当时 Docker PostgreSQL 不可用，凭据主体也用替代输入。这些历史证据只证明原消费契约，不能代替真实实例与登录业务。

3.2–3.5 的历史 RED／GREEN 和边界见[原验收](acceptance/matching-preview-20261019.md)，其 SQLite／替代主体证据不用于扩大 PostgreSQL 结论。5.3 的[真实业务链路](acceptance/organization-rerank-20261021.md)已另行完成实例 UUID／归属／NULL 会话及结果页验证；原历史限制不再作为当前未接入的描述。
