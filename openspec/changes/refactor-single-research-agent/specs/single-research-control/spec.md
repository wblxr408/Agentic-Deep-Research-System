# Spec Delta

## Purpose

为开放研究提供一个依据当前证据和缺口选择下一步的主决策主体，同时保持可信执行流程对权限、预算、状态、恢复与最终交付的控制。让用户能够理解研究行动及计划调整，既有任务继续遵循原冻结合同。

## ADDED Requirements

### Requirement: Architecture changes preserve the existing capability roadmap

系统 SHALL 保留已确认功能及其实现／验收状态，将主Agent改造映射到原能力清单。角色合并不能删除跨对象、跨学科、评价与权重、深读关系、图文模板、导出、复用及反馈目标。明确暂缓或仅列候选的能力 MUST NOT 因按需工具机制自动启用；架构完成不能代替原功能验收。

#### Scenario: An unfinished feature is transferred to a skill or tool
- **WHEN** 原已确认功能改由主Agent调用的Skill／工具承接，但实际业务或验收尚未完成
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

系统 SHALL 由一个主研究 Agent 根据当前目标、证据、已完成判断及未解决问题提出下一动作，记录理由和预期结果。不同观察能够产生不同后续动作；不能仅将固定七阶段顺序重命名为主 Agent。独立取证动作可在当前并发限制内成批执行。

#### Scenario: Acquired evidence changes the research direction
- **WHEN** 原文揭示决定性条件与初始假设不同
- **THEN** 主 Agent 能选择核清该条件、调查反例或修订比较方向，并向用户说明调整理由，保留此前有效成果

#### Scenario: Known independent reads can share a batch
- **WHEN** 多个已授权来源读取互不依赖且当前份额允许并行
- **THEN** 系统可执行一个有界批次，分别记录结果，不为每条读取强制增加一次主 Agent 决策

### Requirement: Trusted execution owns authority and state

系统 SHALL 在模型提出动作后核对真实主体、当前任务和执行、计划版本、工具许可、输入及根配额，接纳结果时再次校验。模型文字及来源内容 MUST NOT 授予权限、变更上限、创建新的预算所有者或自行启动其他自治主体。重复操作应只有一次业务提交。

#### Scenario: A proposed action exceeds existing grants
- **WHEN** 动作请求未获许可的内部资料、工具、模型或外传目的地
- **THEN** 系统在实际访问或外发前拒绝，保留可解释原因及既有成果，不以研究需要扩大权限

#### Scenario: An old execution returns after cancellation
- **WHEN** 已取消或被替代的执行返回工具或模型结果
- **THEN** 结果不写入当前研究状态，已发生的实际或未知消费仍按原根记录

### Requirement: Skills load from frozen authorized selections

系统 SHALL 基于本任务冻结目录按当前动作加载必要 Skill 指令及注册参考，保留版本、加载原因、遗漏和冲突。用户显式选择及其必要约束 MUST 保持生效；网页、模型自报路径和未授权外链不能成为加载来源，技能内容不能执行脚本或扩大工具权限。

#### Scenario: A source page requests an unregistered skill
- **WHEN** 已读取网页要求加载另一技能、执行脚本或开放新工具
- **THEN** 网页只作为来源数据，系统不装载该技能或执行其指令

#### Scenario: Explicit skill requirements exceed the context allowance
- **WHEN** 当前动作不能完整容纳手选技能的必要约束或所需参考
- **THEN** 系统分解动作或明确报告容量／权限冲突，不静默丢弃约束或宣称技能已完整生效

### Requirement: Model completion is a request for delivery assessment

主 Agent SHALL 可以提出研究完成或暂停，但系统 MUST 根据当前问题覆盖、必要主张审核、读者判断及图文／交付状态裁决实际完成。模型自评分、工具成功或章节非空不能代替这些条件。用户应能查看当前计划、实际动作、变化及停止原因。

#### Scenario: The agent finishes with an unresolved decisive claim
- **WHEN** 模型提出完成但当前结论仍依赖未审核或矛盾的关键前提
- **THEN** 系统保留候选稿和具体缺口，进入允许的定向处理或未完成状态，不作为合格最终报告交付

### Requirement: Runtime contracts remain stable across recovery

系统 SHALL 为新任务冻结主控制、Skill、模型、质量及循环政策版本，恢复时保留原根身份、来源、消费、截止时间及已消费机会。历史任务继续原运行合同；新默认设置或部署重启 MUST NOT 静默迁移历史根或同时派发新旧两套研究。

#### Scenario: A legacy task resumes after the new runtime is enabled
- **WHEN** 用户恢复旧运行版本的已保存任务
- **THEN** 系统沿原版本及授权入口恢复，不因新架构重新规划、重新取证、重置预算或改写旧质量判定

#### Scenario: The runtime is rolled back for new tasks
- **WHEN** 后续新任务的默认运行版本被回退
- **THEN** 已创建的新版本根保持其冻结合同或明确暂停，不把其检查点交给不兼容的旧执行器
