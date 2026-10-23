# Spec Delta

## Purpose

让检索块、父级上下文和报告依据始终关联到具体来源版本与规范原文区间，支持结构化分块和有据元数据，同时保留未知与历史引用。索引切法改变不能覆盖过去报告的原文依据。

## ADDED Requirements

### Requirement: Select bounded chunk policy
系统 SHALL 提供固定、滑动、递归及利用原结构的分块选择，保存实际参数及版本，拒绝无效长度／重叠。不能将未运行的语义模型分块声称已采用。

#### Scenario: Long table or code block
- **WHEN** 表格／代码超过目标块长度
- **THEN** 生成有界小块并保留其原结构父级、块内区间及必要缺口，不丢失原文或伪造恢复结果

### Requirement: Preserve hierarchy and metadata provenance
系统 SHALL 保存来源／解析／分块版本、父子ID、标题路径、字符区间、可用页码及字段质量；只索引必要小块，父级引用不得要求重复嵌入整文。标题和背景摘录必须可与原文区分。

#### Scenario: Source heading inherited
- **WHEN** 某正文片段继承章节标题
- **THEN** 原片段文字和偏移保持不变，继承标题另作有来源的上下文元数据

### Requirement: Controlled parent context
系统 SHALL 在同owner、原资料分组、可访问来源和有限字符预算内允许小块扩展到父级，明确实际返回区间。无法核对版本或旧片段无位置时不得猜父级。

#### Scenario: Parent source is archived or unrelated
- **WHEN** 命中片段的父来源已不可用或属于另一主体／分组
- **THEN** 不返回该父级，不能依赖片段ID扩大读取范围

### Requirement: Distinguish mentions from confirmed facts
系统 SHALL 将字面实体、日期与引用标识连同原位置保存，标明词面／字典依据和未知关系；可配置跨学科问题／方法／应用、核心／关联和多标签版本，不能从文字共现确立合作或任职。

#### Scenario: Two institutions in one paragraph
- **WHEN** 同一片段出现两个机构名称但没有已核合作记录
- **THEN** 仅保留有定位的提及，不创建已确认合作边或地理研发中心

### Requirement: Stable report and claim locators
系统 SHALL 将任务内证据标识、来源版本、片段和原文区间传到引用及主张审计，允许本人查看保留原文。重切／新解析或后来索引变化不得改写原任务依据。

#### Scenario: Index is rebuilt after report
- **WHEN** 新分块配置产生独立索引表示
- **THEN** 旧报告仍能读取其任务保留的旧证据和引用区间，不重新检索当前索引代替原依据

### Requirement: Explicit legacy gaps
系统 SHALL 为缺原区间或结构的历史片段标记未知；只有实际文字和版本可核对时才生成稳定定位，不以标题／前缀猜测原文唯一位置。

#### Scenario: Legacy chunk lacks offsets
- **WHEN** 旧片段没有原文偏移
- **THEN** 可保留其片段原文，但父级／原文件位置显示不可用，不能追认不存在的页码
