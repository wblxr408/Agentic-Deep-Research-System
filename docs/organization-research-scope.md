# 组织研究范围预览 API

2026-10-19：交付 `add-organization-research-matching` 任务 1.1–1.4。入口为 `POST /api/v1/research/scope/preview`，使用研究路由现有的登录认证。实现位于 `app/research_scope.py`，由普通函数进行校验与归属计算；家族扩展后的响应 `schema_version` 为 `2`。

该接口消费请求中的记录，返回范围和成果归属预览。请求不会创建研究任务、保存证据、调用模型、抓取来源或开展联网候选发现。正式 `ResearchRequest`、研究状态和前端仍按任务 4、5 接入。

## 最小请求

```json
{
  "scope": {
    "organization_types": ["university", "laboratory"],
    "disciplines": ["materials"],
    "topic": "材料制备方法的研究演进",
    "start_date": "2020-01-01",
    "end_date": "2026-12-31"
  },
  "candidate_entities": [
    {
      "entity_id": "lab-a",
      "name": "先进材料实验室",
      "type": "laboratory",
      "source_urls": ["https://example.org/laboratory"]
    }
  ]
}
```

示例为替代输入；域名不构成真实机构的取证证明。请求带现有登录会话。成功返回 200，非法输入返回 FastAPI 的 422 `detail`，包含字段位置与拒绝原因；修正请求后可重试。

## 输入契约

| 字段 | 规则与含义 |
| --- | --- |
| `scope.organization_types` | `university`、`laboratory`、`company` 任意非空组合；省略时默认三类，显式空列表、未知类型和重复类型均拒绝。多类是并集，不要求有合作关系。 |
| `scope.entities` | 0–200 个明确选中的实体。非空时进入 `named_entities` 模式，准确保留选择及顺序，不自动补入其他候选；空或省略时进入 `candidate_discovery` 模式。实体类型必须在所选类型内。 |
| `scope.disciplines`、`topic` | 1–20 个非空学科及非空主题；主题最长 2000 字符。学科字符串是查询条件，尚不代表评价体系已适配。 |
| `scope.start_date`、`end_date` | 必填有效日期，开始不晚于结束，成果筛选包含两个端点。 |
| `candidate_entities` | 最多 200 个候选或关系上下文实体。发现模式按类型筛选这些已提供记录，同时返回保留学科、主题、时间的 `discovery_query`，供后续发现工具消费；此处不判断候选是否真实符合学科与主题。 |
| `relationships` | 最多 500 条 `part_of` 隶属边，包含 `parent_id`、`child_id`、`source_urls` 和可选有效期 `valid_from`／`valid_to`。引用的两端必须已提供。禁止自指、环和倒置日期；为保持输入可解释性，即使有效期不同也拒绝结构成环。 |
| `outputs` | 最多 1000 条成果。每条提供唯一 `output_id`、`title`、`published_on`、来源和 1–50 条发表时署名 `affiliations`。同一 ID 重复输入拒绝。 |
| `current_affiliations` | 最多 1000 条当前任职记录，独立保留，不参与历史成果归属计算。 |
| `research_families` | 最多 1000 个研究家族，每项提供 `family_id`、非空 `output_ids`、关联依据 `source_urls`。一个发表记录只属于一个家族；重复成员、冲突家族或未知成果拒绝。 |
| `output_relations` | 最多 2000 条 `coauthorship`／`funding`／`citation` 关系，包含 `output_id`、`entity_ids`、`source_urls`。引用成果和实体必须已提供；组织共著关系至少两方。关系不自动产生署名归属或战略合作。 |

每个实体提供 `entity_id`、`name`、`type`、非空 HTTP(S) `source_urls`，可附别名和 `resolution_status: pending/confirmed`（默认 `pending`）。高校院系使用 `type: university` 和 `unit_kind: department`；院系与实验室、学校分别拥有 ID。所有模型拒绝未知字段。名称最多 300 字符、ID 最多 160 字符，实体别名最多 30 个，每条来源最多 20 个。

实体 ID 是调用方提供的身份句柄：同名、不同 ID 的两个实验室始终分别保留；同一 ID 的冲突资料拒绝，不能以名称相似就覆盖。实体选择列表中不允许重复 ID。机构隶属必须通过关系边表达，名称中的学校名不自动建立关系。

署名记录包含 `author_id`、`entity_id`、`raw_affiliation`、`source_urls`。原始署名保留原文，全部空白时拒绝；引用实体必须在已选实体或候选目录中。发表时署名是按论文记录提供的事实线索，当前任职只能作为另一条线索保留。

## 归属与响应

对研究日期范围内的每条成果，按 `published_on` 选择当时有效的隶属边，再向父机构传播归属。有效期包含端点；已知开始且结束为空表示从该日持续有效，开始未知时不推断历史有效，并计入 `undated_relationship_count`。例如学校 → 院系 → 实验室两条边均在 2022 年有效时，实验室的 2022 年署名成果也进入学校视图；2023 年终止的边不能传播 2024 年成果。

主要响应字段：

| 字段 | 消费方式 |
| --- | --- |
| `schema_version`、`scope` | 当前版本 `2` 和校验后的范围，默认值显式展开。 |
| `selection_mode`、`discovery_query` | 具体对象模式不返回发现查询；发现模式保留完整输入条件，没有候选也可生成查询。 |
| `selected_entities`、`pending_entity_ids` | 所选对象及待消歧列表。`confirmed` 是调用方声明，本接口不会替它核实身份。 |
| `excluded_candidates` | 记录 `type_out_of_scope` 或 `not_selected`，不静默扩大明确选择。关系上下文可被保留但不成为所选分析对象。 |
| `views` | 每个所选实体独立输出 `direct_output_ids`、`inherited_output_ids`、合并后的 `output_ids` 和 `output_count`。同时直接署名且经父子链得到同一成果时，归入直接列表一次。 |
| `summary` | 所选视图的成果 ID 并集。父子机构各显示同一成果，汇总只计一次；各机构计数不能直接相加。`output_count` 保留发表记录口径，新增家族计数见下文。 |
| `outputs`、`relationships`、`current_affiliations` | 返回日期范围内原始成果及输入关系／当前署名，保留来源以便复核。`outputs` 也可能包含未归属所选对象的请求记录，应以 `summary.output_ids` 消费汇总样本。 |
| `verification` | 固定 `source_status: provided_records_only`、`external_sources_checked: false`。预览计数包括待消歧输入的条件归属，不得包装成已核验结论。 |

### 发表记录、家族与关系统计

各对象视图及 `summary` 同时提供 `publication_count`、`research_family_ids`、`research_family_count`、`unlinked_publication_count` 和 `counting_method: full`。两个发表记录经有来源的家族关联可计为两条发表、一项研究；未关联的记录各作为独立研究单元，标识为 `publication:<output_id>`，不因标题相同就合并。明确家族标识为 `family:<family_id>`，两类前缀避免碰撞。家族视图按研究日期内有归属的成员计入，时间外记录不会增加计数。

例如会议版和期刊扩展版分别为 `conference`、`journal`，显式输入：

```json
{"research_families": [{"family_id": "study", "output_ids": ["conference", "journal"], "source_urls": ["https://example.org/extension-evidence"]}]}
```

同一研究被两个对象共同署名时，各对象按全计数显示一项研究，汇总家族并集计一次。`relation_counts` 按关系种类、成果 ID 与无序实体集合去重；同一关系的多个证据记录仍保留，资助方仅有资助边不会进入署名视图。`output_relations` 只输出汇总样本内的关系。当前不提供分数计数。

## ACI 边界与后续接入

该操作是登录用户对自己提供的记录进行同步、无持久副作用的计算，不加载其他任务或用户证据。来源 URL 仅作为数据保存和返回，既不访问也不执行；无需额外模型或外部采集预算，受上述批次数量和字符串限制。接口未新增外部重试或工具超时设置，沿用应用 HTTP 生命周期；数据不足时返回空视图或待消歧／无日期提示，不自动补证。

后续任务 4.1–4.4 将生效范围、证据快照及这些视图接入研究执行、持久化和报告；5.1 再接用户选择界面。学科评价和权重配置预览见[适配与 ACI 说明](research-evaluation-and-weights.md)，其余关系分析和全流程业务实跑按未完成任务推进。验收分别见 [1.1–1.3 记录](acceptance/organization-scope-20261019.md)和[1.4–3.1 记录](acceptance/organization-evaluation-20261019.md)。
