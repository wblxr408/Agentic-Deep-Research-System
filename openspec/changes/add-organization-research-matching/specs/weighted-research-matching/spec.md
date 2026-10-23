# Spec Delta

## Purpose

让用户通过可修改、可追溯的匹配偏好，从指定学科与对象范围内发现或比较研究方向、成果和组织；解释每个分项及其证据，并将硬性筛选、学术表现和信息完整性区分，避免未知数据被展示为确定排名。

## ADDED Requirements

### Requirement: Configure matching dimensions and metric weights
系统 SHALL 支持主题相关性、研究路线契合、成果表现、证据完整度、时效性和合作互补性等维度的预设与自定义权重，并支持成果表现内部各适用评价体系的权重。用户可关闭某项、恢复预设及查看实际生效配置；独立研究不要求启用合作互补性。

#### Scenario: Adjust user preferences
- **WHEN** 用户提高主题相关性并关闭合作互补性
- **THEN** 新匹配按调整后的有效权重计算，并显示变化及其影响；零权重项不贡献分数

### Requirement: Validate and normalize weights
系统 SHALL 拒绝负数、非有限数、未知维度及同一有效层级全零的权重。非负有效权重在对应层级归一化为总和 100%，保存原始输入及生效值；可编辑的分档映射必须版本化并保持各体系自身的等级顺序。

#### Scenario: Normalize proportional weights
- **WHEN** 用户只启用主题相关性和证据完整度，分别输入 6 和 4
- **THEN** 系统显示并使用 60% 和 40%，不把原始值误解释为仅合计 10% 的贡献

#### Scenario: Invalid weight set
- **WHEN** 有效维度全为零或任一输入为负数或非有限数
- **THEN** 请求被拒绝并提示具体问题，不静默恢复默认配置

### Requirement: Apply hard constraints before scoring
系统 SHALL 先应用对象类型、学科、时间及用户显式设置的关系／指标硬条件，再进行软匹配排序。未知事实不满足需要已核实证据的硬条件，须说明待核原因；评分不能产生或改写共著、资助与合作事实。

#### Scenario: High score outside selected type
- **WHEN** 只选择高校而企业候选的主题相关性最高
- **THEN** 企业仍被排除，调整权重不能覆盖对象范围

### Requirement: Explain comparable scores
系统 SHALL 在共同适用口径内展示分项值、归一化权重、贡献、依据及评分规则版本。相关的载体指标须共享成果表现维度的权重上限；跨学科或载体不可比时分组展示，不建立 CCF／JCR／中科院分区的官方等价关系。匹配分表达当前偏好下的契合度，不是质量定论或成功概率。

#### Scenario: Correlated venue indicators
- **WHEN** 同时启用 JIF、JCR 分区及其他载体指标
- **THEN** 它们仅在成果表现维度的既定预算内分配权重，不因指标数量增加而突破该维度上限

### Requirement: Expose missing-data uncertainty
系统 SHALL 预先固定同组候选的适用维度；对未知分项给出有效权重覆盖率及可能分数区间，不按零分或逐候选重新归一化制造确定总分。缺失与低表现分别显示；区间重叠的候选不得宣布确定优劣。

#### Scenario: Incomplete evidence overlaps complete result
- **WHEN** 两项权重为 60%／40%，候选甲第一项为 0.9、第二项未知，候选乙分别为 0.8／0.7
- **THEN** 甲显示覆盖率 60%、区间 54–94，乙显示完整匹配分 76；甲的已知贡献 54 不显示为最终总分，也不宣称甲确定高于或低于乙

### Requirement: Preview and preserve matching snapshots
系统 SHALL 支持在固定证据快照上修改权重并预览重排，明确区分重算与重新取证。已提交会话保存对象、学科、原始与有效权重、规则及评价版本、证据截止时间；后续修改形成新配置版本，不改变历史结果或暂停恢复的原配置。

#### Scenario: Reweight existing evidence
- **WHEN** 用户在结果页改变权重并预览
- **THEN** 系统使用同一候选与证据快照重算，展示变化且不自动触发外部采集

#### Scenario: Resume a historical session
- **WHEN** 默认配置或目录更新后恢复暂停研究
- **THEN** 继续使用该会话原配置与预算，报告可追溯其版本；升级配置通过新的显式研究请求执行

### Requirement: Deliver analysis with provenance
系统 SHALL 在结果、报告和导出中保留对象归属、学科、评价口径、匹配解释和未解决问题，区分事实、分析建议与预测；关键来源不足时交付受限结果，不声称完成精准匹配或掌握机构完整研发战略。

#### Scenario: Partial-source result
- **WHEN** 部分指标来源不可用但仍有可核实研究证据
- **THEN** 结果说明已覆盖范围与缺口，保留可用证据及受限匹配，不把缺失填成已证实结论

### Requirement: Provide purpose-specific actionable results
系统 SHALL 按研究目的交付后续研究问题／验证路线，或候选组织及关联团队／学者、需求契合、已核关系、互补点、待验证议题、优先级及下一步。优先级复用硬条件、分项、有效权重及缺失区间；缺需求、关系或可行性证据时必须显示条件和待补项，不把公开共著、学术声望或计数解释为合作成功概率。

#### Scenario: Missing collaboration demand
- **WHEN** 用户选择合作发现但未提供足够的己方研究需求
- **THEN** 系统展示候选方向与需补充的匹配条件，不宣称完成精准合作匹配或制造确定推荐总分

#### Scenario: Development-only purpose
- **WHEN** 用户仅研究某高校或实验室的学术演进
- **THEN** 系统可输出后续研究问题和验证路线，无需合作候选；报告生成不触发对外联系
