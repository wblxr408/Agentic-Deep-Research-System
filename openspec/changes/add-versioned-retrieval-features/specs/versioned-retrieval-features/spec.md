# Spec Delta

## Purpose

让每个保留来源及小块的词汇、稠密、实体、模态和时间特征有明确的生成依据、范围和版本，供后续检索索引消费。用户能够选择表示成本并查看缺口，未采用的候选模型和未知身份／日期不被表达为已验证能力。

## ADDED Requirements

### Requirement: Source anchored lexical views
系统 SHALL 保留有界词项、实际原文位置、词频及明确计数范围的文档统计；规范词项与原文字面分别表达，截断和未知不能冒充零频。

#### Scenario: Mixed language document
- **WHEN** 中文、英文和技术标识混合的来源被接入
- **THEN** 生成版本化词项及可核对的原文位置；词汇统计说明是否含重叠片段及截断，不当作成果统计

### Requirement: Explicit dense cost and identity
系统 SHALL 允许接入时选择稠密表示，默认无需模型的词汇表示。稠密启用时保存实际编码身份、维度、归一化和已知截断边界，失败不得提交为完整表示。查询不得将不兼容／未知版本向量当作同模型空间。

#### Scenario: Dense disabled
- **WHEN** 用户关闭稠密特征后接入资料或采用词汇查询
- **THEN** 不加载嵌入模型，来源仍可保存／按词汇检索，特征记录明确稠密未启用

#### Scenario: Encoder dimension mismatch
- **WHEN** 已选择的编码输出维度不符合当前存储配置
- **THEN** 拒绝该次接入并保留可解释错误，不截断／填补向量或写入部分来源

### Requirement: Evidence grounded entity and time features
系统 SHALL 区分词典提及、已消歧实体、已确认关系及日期角色；只有明确的来源日期才生成带依据和时点的时间窗口／衰减，未知或未来日期不伪造时效分。

#### Scenario: Date appears inside a paragraph
- **WHEN** 来源仅有字面日期或机构共现
- **THEN** 记录原位置及角色未知，不据此确定发表年份、任职、合作或来源新鲜度

### Requirement: Honest modality and candidate state
系统 SHALL 为学习稀疏、细粒度语义、行为语义、BSR和多模态候选记录选型条件及当前状态。图像指针／图注不等于图像特征；行为模型没有适当授权数据时不得训练或隐式收集点击。

系统 SHALL 在用户显式选择时派生独立英文词形视图，保存数据库实际文本检索配置、版本和覆盖；不得替换原始词项或伪造原文位置。BSR SHALL 指Beam Search Retrieval，其搜索实际接线须遵循来源权限与有限资源，保留来源路径，不能把提及当成已确认关系。

#### Scenario: Image pointer without image bytes
- **WHEN** 解析只保留图像指针和文字图注
- **THEN** 特征视图标明未编码图像且不跟随资源出站，文字特征继续关联原位置

### Requirement: Owned versioned feature inspection
系统 SHALL 允许本人查看／下载已有特征和生成规则，旧记录缺特征时明确未知。只读查看不得触发模型、网络、训练或重建；普通metadata编辑不能篡改服务器生成的特征版本。

#### Scenario: Known source ID belongs to another owner
- **WHEN** 调用者尝试读取他人的特征
- **THEN** 在正文或特征被返回之前拒绝，不能通过特征详情旁路资料权限

### Requirement: Explicit learned sparse representations
系统 SHALL 允许本人选择实际的固定版本本地学习稀疏模型，为源片段生成带词表身份、非负权重和输入覆盖的稀疏表示；模型不可用或输入被截断时不得伪称完整。词面统计保留为独立路径。

### Requirement: Actual multivector and image representations
系统 SHALL 仅在明确选择和实际编码后保存token级多向量、图像或图文表示，绑定来源、模型空间、输入版本和权限；未取得原图、未配置兼容模型或空间不匹配时不得标为可比较。

### Requirement: User-declared source-anchored identity links
系统 SHALL 允许本人为实际原文中已定位的实体候选声明和撤销稳定身份标识，绑定账号、资料版本、片段和原文位置；重复提交不得重复修改。身份声明必须区别于独立核验，只有本人选择的候选及仍有效链接才可进入后续研究。
