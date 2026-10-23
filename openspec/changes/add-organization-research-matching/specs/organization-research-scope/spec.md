# Spec Delta

## Purpose

为组织研究发展分析提供明确的对象、学科、主题和时间边界，让高校、科研实验室与企业能够独立或组合研究，并在比较、汇总和报告中保持实体归属、证据范围及成果统计的一致性。

## ADDED Requirements

### Requirement: Select organization types
系统 SHALL 在组织研究模式中支持高校、科研实验室、企业三种对象类型的任意非空组合，单选、多选及全选均有效；类型之间按并集筛选。初次进入此模式默认选择三类，明确清空后不得自动恢复全选。

#### Scenario: University-only research
- **WHEN** 用户只选择高校并提交合法研究请求
- **THEN** 研究仅纳入符合条件的高校对象，不要求其具有企业合作关系

#### Scenario: Mixed organization types
- **WHEN** 用户选择高校和科研实验室，或选择全部三类
- **THEN** 研究覆盖选中类型的并集，并在结果中标明每个对象的类型

#### Scenario: Empty type selection
- **WHEN** 用户清空所有类型后提交组织研究
- **THEN** 界面提示至少选择一类，直接 API 请求也被拒绝，不静默扩大范围

### Requirement: Select one or multiple entities
系统 SHALL 允许用户研究一个或多个具体对象，或在选定类型和研究条件中发现候选对象。已指定对象必须有可辨识名称、类型和来源；同名未消歧对象保持待确认。指定对象与类型不相容时请求必须拒绝，不自动改变类型。

#### Scenario: One standalone laboratory
- **WHEN** 用户选择科研实验室并指定一个实验室
- **THEN** 系统独立分析该实验室，不要求另选企业或高校作为主对象

#### Scenario: Multiple named organizations
- **WHEN** 用户指定两所高校与一家企业，且相应类型均被选择
- **THEN** 系统分别给出各对象的分析与同口径比较，不把多选解释为对象必须存在合作

#### Scenario: Ambiguous or incompatible entity
- **WHEN** 同名对象的归属无法核实，或用户指定企业但只选择高校类型
- **THEN** 前者呈现待确认且不强行合并，后者拒绝提交并说明冲突字段

### Requirement: Select disciplinary and temporal scope
系统 SHALL 支持一个或多个学科、明确主题和合法时间区间；在计划、筛选及报告中保留学科与年份依据。对象类型、学科和时间等硬条件必须先于加权排序执行。

#### Scenario: Cross-disciplinary comparison
- **WHEN** 用户选择计算机与材料两个学科并设置时间范围
- **THEN** 结果保留每项成果的学科及发表时间，按各学科适用口径分析，并说明跨学科可比范围

#### Scenario: Invalid time range
- **WHEN** 起始时间晚于结束时间
- **THEN** 请求被拒绝并提供可修正错误，不启动取证

### Requirement: Preserve parent and historical affiliation
系统 SHALL 区分机构、院系和实验室实体，保存有来源与时间依据的隶属关系及发表署名。父机构和子实验室同时选中不等于两项独立成果；作者当前任职不覆盖历史署名。

#### Scenario: Parent and laboratory selected together
- **WHEN** 同一成果关联被选中的高校及其下属实验室
- **THEN** 各对象视图可呈现该成果，合并汇总只计一次并说明归属关系

### Requirement: Distinguish publication and research-family counts
系统 SHALL 分别保存发表记录和研究家族，预印本与正式版通过证据关联；共著、资助和仅存在引用关系分别标注。多对象共有成果在汇总中去重，比较视图明确全计数或分数计数口径。

#### Scenario: Conference and journal extension
- **WHEN** 一项研究有会议版、期刊扩展版及关联预印本
- **THEN** 系统分别展示发表记录与研究家族数，并保留版本关联依据，不由标题近似直接宣布同一研究

### Requirement: Optional organization mode
系统 SHALL 仅在用户启用组织研究模式时应用这些选择要求，保留通用研究请求；新增选择不得扩大原有内部资料权限、联网许可或预算。

#### Scenario: Existing general research request
- **WHEN** 旧请求不携带组织研究配置
- **THEN** 系统继续执行原通用研究流程，不要求补填对象类型

### Requirement: Select research purpose independently
系统 SHALL 支持布局与演进分析、合作资源发现、综合研究三类目的，未提供时沿用研究发展；目的、权重、报告模板和绘图方案分别表达。各目的适用于选定的高校、实验室、企业及其组合，不固定要求企业或产品分析。

#### Scenario: Standalone academic development
- **WHEN** 用户选择一所高校或实验室，仅要求研究发展分析
- **THEN** 系统组织学术问题、方法与成果演进，不要求生成企业产品页、合作候选或对外联系信息

#### Scenario: Combined analysis
- **WHEN** 用户选择综合研究并给出合作需求
- **THEN** 系统结合布局、成果深读和合作依据组织分析，保留与权重及页面配置相互独立的目的快照

### Requirement: Declare corpus and coverage
系统 SHALL 保存来源、检索式、对象别名、时间和截止日、纳入／排除、候选流转与全文取得状态，并按学科和任务声明成果类型。完整性只相对于已声明且实际覆盖的范围解释，缺口不得表述为现实全集。

#### Scenario: Limited source coverage
- **WHEN** 用户限定部分论文源或部分成果只能取得元数据
- **THEN** 结果显示实际覆盖、排除和全文缺口，技术判断不冒充已读全文结论，且不自行扩展来源

### Requirement: Version disciplinary research mapping
系统 SHALL 按适用学科配置问题、方法与应用层次，支持核心／关联方向、多标签和未知分类，保留版本及分类证据。会议或期刊偏好不得替代主题发现；用户显式载体硬条件仍须执行并说明覆盖边界。

#### Scenario: Non-computing classification
- **WHEN** 研究对象属于非计算机学科且存在多个相关方向
- **THEN** 系统采用适用的学科分类并保留交叉标签，不强制使用网络分层、CCF 或某些计算机会议列表

#### Scenario: Classification changes over time
- **WHEN** 同一批证据使用新分类规则分析
- **THEN** 系统保存新版本并展示重分类依据，不将分类变化宣称为组织研究投入或数量增长

### Requirement: Preserve relationship semantics and geography
系统 SHALL 分开保存共著、资助、正式项目、联合实验室及交流的类型、来源、时间和核实状态；合作频次、持续性、地域和角色分别解释，历史归属不覆盖当前状态。

#### Scenario: Coauthorship and location
- **WHEN** 仅取得一篇与异地高校共同署名的论文
- **THEN** 系统仅确认有依据的共著与署名所在地，不推出战略协议、主导关系或企业在该地设有研发中心

### Requirement: Deliver mechanism-level analysis and bounded inference
系统 SHALL 为选定代表成果保留问题、已有局限、机制／方法、创新、实验设置与基线、结果边界和原文定位；缺项保持未知。研究演进须区分数量、来源覆盖与路线变化，并记录支持、反证／替代解释及待验证信号。投入、内部战略、成熟度、部署或未来方向不得仅由成果数量推出。

#### Scenario: Abstract-only result
- **WHEN** 某代表成果只有摘要，机制和实验条件无法取得
- **THEN** 系统呈现摘要可支持的内容及深读缺口，不补造方法细节、数值或论文原图

#### Scenario: Related patent or product
- **WHEN** 存在相关专利或适用产品材料，但没有成果部署的直接证据
- **THEN** 系统区分相关线索与已部署结论；未来方向以带时间、依据及待验证条件的情景表达

### Requirement: Reproduce quantitative analysis across outputs
系统 SHALL 使用确定性计算产生计数、比例、变化率和评分，保留分子、分母、去重单位、多标签、缺失及规则版本；图表、文字和导出引用同一数据快照。发现冲突时说明并修正，生成模型不得自行改写统计结果。

#### Scenario: Percentage and overlapping categories
- **WHEN** 已核样本中某项为 9 个、总量为 54 个，且技术类别允许多标签
- **THEN** 系统按声明精度计算该占比约为 16.67%，各类别说明分母和重复规则，不要求多标签占比强行合计 100%

#### Scenario: Missing annual observations
- **WHEN** 部分年度来源未覆盖或记录未知
- **THEN** 趋势图与报告标出缺失，不自动补零并据此宣称增长或衰退
