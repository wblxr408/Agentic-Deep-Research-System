# Spec Delta

## Purpose

为跨学科的企业、高校和实验室研究提供可追溯的成果评价背景，区分收录索引、载体目录、期刊指标和论文级引用表现，使用户能够选择适用体系，同时识别缺失数据、版本差异及不可比较的情况。

## ADDED Requirements

### Requirement: Support distinct evaluation families
系统 SHALL 适配 CCF、ICORE、WoS 的 SCIE／SSCI／AHCI／ESCI 及 Scopus 收录、JCR 的 JIF／分区／JCI、期刊分区表（中科院分区）、CiteScore 及百分位、SJR、SNIP、ABDC、AJG、论文引用百分位、CNCI 和 FWCI。收录、目录等级、期刊指标与论文级指标分别保存，不合并为无来源的通用等级。

#### Scenario: Multiple labels for one publication
- **WHEN** 一项成果的发表载体适用多个体系
- **THEN** 系统分别呈现各体系的原始记录，不把 CCF-A、JCR Q1 和中科院一区互换

### Requirement: Determine applicability by discipline and output type
系统 SHALL 按学科、成果类型及目录实际覆盖范围判断体系适用性；同一成果可有多个学科类别。计算机成果可启用 CCF／ICORE，其他领域不自动套用；所有适用学科均可保留期刊与引用指标。

#### Scenario: Material-science journal and computing conference
- **WHEN** 分析同时包含材料期刊文章与计算机会议论文
- **THEN** 分别展示其适用体系；会议附属轨道不自动继承主会等级，期刊分区不自动用于会议

#### Scenario: Business research
- **WHEN** 成果属于商科相关领域且命中 ABDC 或 AJG 的相应目录
- **THEN** 系统按目录版本展示其等级，同时保留其他适用收录与指标

### Requirement: Track edition category and evidence
系统 SHALL 为每条评价记录保留体系、发布版本／年份、指标数据年份、学科类别、原始值、来源、获取时间及匹配依据，并以 ISSN／载体身份等核定对应关系。用户可采用发表时口径或指定年度快照，报告须显示该选择。

#### Scenario: Multiple subject quartiles
- **WHEN** 同一期刊在不同类别中具有不同 JCR 分区
- **THEN** 系统保留各类别值，并明确参与当前匹配的类别，不静默取最高分区

#### Scenario: Historical evaluation
- **WHEN** 用户分析过去年度成果并选择当年口径
- **THEN** 系统使用可核实的对应历史记录；无法取得时标记缺失，不用当前等级冒充历史等级

### Requirement: Distinguish unavailable and inapplicable data
系统 SHALL 区分已核实、未收录、不适用、数据缺失、来源不可用及证据冲突；缺失不等于最低等级。未授权或不可取得的来源可补充用户已授权数据，并保留来源与获取状态。

#### Scenario: Unavailable metric source
- **WHEN** 指标需授权且当前无权限，或来源临时不可用
- **THEN** 系统标记对应状态及缺失原因，继续可完成的研究，不推测数值或伪称完成适配数据采集

### Requirement: Preserve metric level and comparison context
系统 SHALL 区分期刊级与论文级指标，并按学科、年份及成果类型声明比较背景。论文引用表现可使用适用的引用百分位、CNCI／FWCI；期刊等级不得直接作为单篇成果真实质量或未来技术价值的证明。

#### Scenario: Organization comparison across disciplines
- **WHEN** 两个对象的成果来自引用习惯不同的学科
- **THEN** 系统呈现可比较的分组或归一化依据，同时保留原始值，不直接按影响因子相加产生机构优劣结论
