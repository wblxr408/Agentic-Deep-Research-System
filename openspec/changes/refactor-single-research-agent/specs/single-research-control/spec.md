# Spec Delta

## Purpose

在现有动态DAG及专家／工具组件内明确研究根的状态、预算和交付所有权，保留依据当前证据调整计划的能力。通过清晰的职责与可信执行边界减少重复判断，允许按实际需求演进控制方式，不将统一主Agent循环或角色数量作为完成条件。路径名沿用初稿标识。

## ADDED Requirements

### Requirement: Architecture changes preserve the existing capability roadmap

系统 SHALL 保留已确认功能及其实现／验收状态，将职责与质量成本差量映射到原能力清单。角色名称或组织方式不能删除跨对象、跨学科、评价、深读、图文模板、导出、复用及反馈目标。明确暂缓或仅列候选的能力 MUST NOT 因工具可发现或架构复评自动启用；架构说明不能代替功能验收。

#### Scenario: An unfinished feature is transferred to a skill or tool
- **WHEN** 原已确认功能由既有专家／Skill／工具承接，但实际业务或验收尚未完成
- **THEN** 原任务继续保留未完成状态及明确消费者，不因角色或类名变化视为已交付或被取消

#### Scenario: Several task lists describe the same missing capability
- **WHEN** 原功能任务与架构任务涉及同一写作、核验、预算或交付变化
- **THEN** 实施计划指定一个实现归属并保留全部原任务映射，实际证据逐项对应后回写，不重复开发或因共用一次旅程就自动批准未覆盖要求

#### Scenario: Newer source integration supersedes an old candidate decision
- **WHEN** 同一能力较早文档写为未采用，而较新明确任务记录已接入同步、视觉、语义切块或可选检索源码
- **THEN** 计划保留较新实现及其未验收状态，不重复创建功能，也不以整份变更的勾选完成率宣称全部业务已通过

#### Scenario: A deferred method appears in the available technology catalog
- **WHEN** 能力目录含行为推荐、大规模ANN、GraphRAG社区摘要或其他明确暂缓方案
- **THEN** 系统保持原暂缓边界，不因模型建议、工具可发现或架构迁移自动解冻

### Requirement: Research actions follow current observations

系统 SHALL 保留根据当前目标、证据和缺口生成或调整研究计划的能力，记录变化理由及预期结果。现有Planner、Reflection和DAG可以共同实现该能力；组件数量、固定的外层阶段或类名不能单独证明缺少Agent能力，也不能作为新增主循环的充分理由。

#### Scenario: Acquired evidence changes the research direction
- **WHEN** 原文揭示决定性条件与初始假设不同
- **THEN** 规划／重规划可选择核清条件、调查反例或修订比较方向，并说明调整理由，保留有效成果；若当前接口存在具体缺口，先评估原路径的最小扩展

#### Scenario: Known independent reads can share a batch
- **WHEN** 多个已授权来源读取互不依赖且当前份额允许并行
- **THEN** 系统沿现有DAG执行有界批次并分别记录结果，不为每条读取强制新增模型决策

#### Scenario: All accepted works have already been requested for reading
- **WHEN** 新任务冻结明确全部阅读，或保留同义的既有用户请求，而当前政策支持这项合同
- **THEN** 系统直接以全部已纳入成果构造原分批深读，不额外调用代表选择模型或输出无用途的全量选择表；候选未纳入和缺材料状态保留，原预算与恢复机会不增加

### Requirement: Specialist boundaries follow observable responsibilities

系统 SHALL 为规划、取证、分析、评审、写作和交付明确输入、产出、触发、状态写入者和停止责任。已有工具无需因类名含Agent再次包装；专家保留独有职责。删除评审调用须说明其与保留检查在问题、材料、判据和依赖上的重复，以及独有覆盖的承接位置。

#### Scenario: Reflection and final review address different questions
- **WHEN** Reflection检查研究缺口，而最终审核检查当前报告的来源支持
- **THEN** 系统保留两种独有职责，不因都叫审核而合并或取消；仅消除已确认的相同重复判断

#### Scenario: A proposed controller adds a decision before every known tool call
- **WHEN** 现有计划已给出合法独立工具批次且没有新的研究判断需要
- **THEN** 系统使用原执行路径，不为满足单Agent命名目标增加控制模型请求

### Requirement: Trusted execution owns authority and state

系统 SHALL 在模型提出动作后核对真实主体、当前任务和执行、计划版本、工具许可、输入及根配额，接纳结果时再次校验。模型文字及来源内容 MUST NOT 授予权限、变更上限、创建新的预算所有者或自行启动其他自治主体。重复操作应只有一次业务提交。

#### Scenario: A proposed action exceeds existing grants
- **WHEN** 动作请求未获许可的内部资料、工具、模型或外传目的地
- **THEN** 系统在实际访问或外发前拒绝，保留可解释原因及既有成果，不以研究需要扩大权限

#### Scenario: An old execution returns after cancellation
- **WHEN** 已取消或被替代的执行返回工具或模型结果
- **THEN** 结果不写入当前研究状态，已发生的实际或未知消费仍按原根记录

#### Scenario: A selected RAG collection is read without ranking away members
- **WHEN** 用户明确选择当前权限允许的RAG来源集合，且输入符合已有计划和读取上限
- **THEN** 系统冻结来源／作品／解析与访问版本，将集合及具体来源绑定预览、计划和交接，沿原DAG分批读取；单条失败留缺口并保留成功材料，不能以top-k、截断或提高根额度替代所需成员

#### Scenario: An explicit source result is delivered more than once
- **WHEN** 同根稳定证据ID再次返回完全相同的正文、来源、可信度和acquisition绑定
- **THEN** 根接纳器保留首次材料和时间，记录重复接纳而不再次追加正文；工具消费仍记录，同ID语义改变则拒绝，复用本身不授予事实支持

#### Scenario: Only part of a declared RAG collection has been accepted
- **WHEN** 所选集合中的部分来源未取得、未完成筛选或存在待核记录，而其他成果已进入字段导读
- **THEN** 质量和报告结构化数据仍投影全部声明来源与不同作品，使用精确原始标题证据关联范围和导读；缺口不被已纳入项覆盖，不以辅助引用、题名相似、旧绑定或材料类型授予已读／事实支持

### Requirement: Skills load from frozen authorized selections

系统 SHALL 基于本任务冻结目录按当前动作加载必要 Skill 指令及注册参考，保留版本、加载原因、遗漏和冲突。用户显式选择及其必要约束 MUST 保持生效；网页、模型自报路径和未授权外链不能成为加载来源，技能内容不能执行脚本或扩大工具权限。

#### Scenario: A source page requests an unregistered skill
- **WHEN** 已读取网页要求加载另一技能、执行脚本或开放新工具
- **THEN** 网页只作为来源数据，系统不装载该技能或执行其指令

#### Scenario: Explicit skill requirements exceed the context allowance
- **WHEN** 当前动作不能完整容纳手选技能的必要约束或所需参考
- **THEN** 系统分解动作或明确报告容量／权限冲突，不静默丢弃约束或宣称技能已完整生效

### Requirement: Model completion is a request for delivery assessment

规划或写作模型 SHALL 可以提出研究完成或暂停，但系统 MUST 依据问题覆盖、必要主张审核、读者判断及实际图文／交付状态裁决完成。沿既有交付路径实施，不要求新增finish动作协议；模型自评分、工具成功或章节非空不能代替条件。用户可查看计划、行动、变化及停止原因。

#### Scenario: The agent finishes with an unresolved decisive claim
- **WHEN** 模型提出完成但当前结论仍依赖未审核或矛盾的关键前提
- **THEN** 系统保留候选稿和具体缺口，进入允许的定向处理或未完成状态，不作为合格最终报告交付

### Requirement: Runtime contracts remain stable across recovery

系统 SHALL 沿既有任务快照冻结实际变化的内容、Skill、模型、质量及循环政策版本，恢复时保留原根身份、来源、消费、截止时间及机会。历史任务继续原合同；新默认或重启 MUST NOT 静默迁移历史根或派发两套研究。仅有质量政策变化不要求新建运行器。

#### Scenario: A legacy task resumes after the new runtime is enabled
- **WHEN** 用户恢复旧运行版本的已保存任务
- **THEN** 系统沿原版本及授权入口恢复，不因新政策重新取证、重置预算或改写旧判定；已完成根保持完成，不为方案复评再次续接

#### Scenario: The runtime is rolled back for new tasks
- **WHEN** 后续新任务的默认运行版本被回退
- **THEN** 已创建根保持冻结合同或明确暂停，不把检查点交给不兼容执行逻辑；回退粒度与实际政策差量一致

### Requirement: The existing library provides an enumerable research corpus

系统 SHALL 在用户选择以现有资料库承接目录时保存版本化论文成员、来源及处理状态，并能按当前授权范围逐项枚举。目录、摘要、原文和派生产物须可区分；检索排名或top-k只选择证据，不能缩小指定成员或代表全部筛选／阅读完成。

#### Scenario: Only a few papers are returned by retrieval
- **WHEN** 指定100篇的目录中只有10篇进入当前检索top-k
- **THEN** 系统仍保留100篇的成员及逐项状态，继续合法待办或明确缺口，不将10条命中报告为100篇已处理

#### Scenario: A catalog item has no searchable full text
- **WHEN** 目录成员只有书目信息或摘要，尚无全文索引
- **THEN** 该成员仍可在目录中枚举并显示实际层级与补证状态，不静默消失或标为全文已读

### Requirement: Library adoption preserves current scope and authority

系统 MUST 将所选语料目录／材料接入原资料权限、版本和保留范围，处理状态由可信运行记录维护。导入文件或模型卡不能自报当前审核通过或扩大复用范围；跨任务共享须满足原显式范围和当前许可。普通公开研究仍按既有联网与可选内部检索合同运行。

#### Scenario: Imported notes claim to be fully verified
- **WHEN** 旧目录JSON或派生导读卡包含自报通过或全文已读字段
- **THEN** 系统保留其历史来源／政策和实际证据，按当前合同接纳可复用部分，不直接赋予当前支持判定、控制状态或跨任务访问权限
