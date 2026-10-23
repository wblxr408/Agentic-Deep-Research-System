# Spec Delta

## Purpose

将研究结论对应到真实来源正文的位置与原文片段，在最终报告生成后检查引用是否支持相应主张，明确自动核验的范围、模型置信度与人工复核状态，避免用引用存在替代事实支持。

## ADDED Requirements

### Requirement: Select evidence for each claim
系统 SHALL 按待核验主张在全部已收集证据正文中选择片段，保留证据标识、来源、位置和原文，不以固定前若干条的开头摘要代替主张取证。超出核验预算的主张必须标记未检查。

#### Scenario: Relevant sentence late in later source
- **WHEN** 相关限制或数字位于第16条之后证据的正文后部
- **THEN** 核验仍能选出该片段并保留位置与上下文

### Requirement: Audit final report citations
系统 SHALL 对最终报告正文的主张检查引用存在性、引用与来源对应关系、引语是否确实来自对应原文及语义支持判定；无引文、错误引用、伪引语、矛盾或无法判定分别标注。引用存在或原文包含引语本身不等于语义支持。

模型 MAY 选择本条主张已提供的原文片段编号，由可信代码附上原文及偏移；未知或属于其他来源的编号 SHALL 被拒绝，不得回退到附带引语绕过。兼容旧式引语输出时继续检查其原文匹配。SDK核验格式异常仅可在根预算内重试一次，原失败保留，再次失败不得通过。

#### Scenario: Citation points to contradictory evidence
- **WHEN** 最终报告主张有有效引用标识但来源只支持相反结论
- **THEN** 自动核验将其标记矛盾或不支持并呈现对应片段，不计为已支持

#### Scenario: Technical comparisons and report metadata
- **WHEN** 报告含vs.比较、带引用的表格数据行、Markdown表头及引用说明块
- **THEN** 保留完整技术比较和数据行用于核验，表头和引用说明元信息不作为事实主张

#### Scenario: PDF line wrapping in a source quote
- **WHEN** 模型引语与所引原文仅有空白或换行差异
- **THEN** 可进行空白归一化匹配并保留原文偏移与切片，明确匹配种类；更改词、数字、单位或标点不能因此通过

### Requirement: Separate model and human verification
系统 SHALL 独立保存模型置信度、自动支持判定、确定性引语校验以及人工复核状态。未收到人工记录时必须标记未复核，核验服务失败不得返回全通过。

#### Scenario: Model claims high confidence without human review
- **WHEN** 模型给出高置信度且没有人工复核记录
- **THEN** 结果仍显示人工未复核；自动核验失败或漏检主张保持待核

### Requirement: Retrieve cross-language and separated conditions
系统 SHALL 为跨语言待核主张在预算内形成检索词，并在已引来源全文选择多个相关窗口，保留每个窗口偏移；检索词不作为事实证据。结果条件与主数字分处不同段落时不能只检查一个片段。查询或核验失败仍显式待核，不自动扩大来源或取消预算。

#### Scenario: Chinese claim with an English deployment limitation
- **WHEN** 中文主张中的实验／部署限制位于英文论文后部
- **THEN** 核验能检索到对应英文限制并保留位置，不以无关开头替代

### Requirement: Audit the corrected final report
SDK流程 SHALL 在初审不支持或待核时至多执行一次无工具修订，保留原报告／初审和调整原因，并对修订后的最终文本重新核验；不得通过缩小原任务或忽略不支持项宣称完成。

#### Scenario: Draft overstates commercial deployment
- **WHEN** 初审发现草稿把实验室结果写成商业部署
- **THEN** 修订依据原文纠正范围，最终审计检查纠正后的主张，并保留初审矛盾记录
