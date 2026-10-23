# Spec Delta

## Purpose

将取得的网页、用户资料及论文转换为可定位、有结构且明确缺口的正文、表格与图像记录，为后续分块、引用和报告提供同一解析版本。原始抽取文字、清洗变换、质量与人工审核分别保存，避免把解析成功当事实核验通过。

## ADDED Requirements

### Requirement: Bounded structured parsing
系统 SHALL 为已支持的TXT、MD、JSON、DOCX、PDF和已取得HTML保存正文、块、来源位置及解析版本，受字符、页数、表格／图像数量和进程时间上限约束。页数未知或布局不可用不得伪造。

#### Scenario: Document exceeds retained character limit
- **WHEN** 有效文档正文超过保留上限
- **THEN** 返回明确截断及未覆盖状态，已有块与字符位置保持有效，不能宣称完整全文

### Requirement: Native text and explicit local OCR
系统 SHALL 原生文字优先；无文本PDF页可由用户显式启用且服务端允许的本机OCR处理。未启用、程序／语言包不可用或预算不足时显示缺口，OCR识别置信度不得显示成事实可信度。

#### Scenario: Scanned page without configured OCR
- **WHEN** 扫描页无原生文本且OCR不可用
- **THEN** 页码和缺口保留，不把该页当空白事实，不自动将图片发送给模型

### Requirement: Traceable table cells
系统 SHALL 将可恢复表格的单元格、行列及原位置分别保存，明确合并单元格的已知跨度或未知；表格文字用于检索时仍能回到表格依据。

#### Scenario: Merged DOCX table
- **WHEN** 来源表格有合并单元格
- **THEN** 保留显式合并关系及源位置，不把合并单元格当多条独立事实重复计数

### Requirement: Image and caption provenance
系统 SHALL 保存实际出现的图像指针、原位置、原始alt描述和可定位图注，不因识别出图像或图号就生成图内数值或已读图结论。未实际取图和未运行图像理解须明确区分。

#### Scenario: HTML external image
- **WHEN** 已读页面含外部图片链接与图注
- **THEN** 保存页面原指针和图注关系，不自动跟随URL或生成图片理解结果

### Requirement: Explain normalization and duplication
系统 SHALL 保留原始抽取文字与清洗转换，不能静默忽略乱码。精确重复可复用但保留出处；近似或语义相似只作待核候选，不自动合并成果或删除原文。

#### Scenario: Similar passages from different sources
- **WHEN** 两段文字相似但来源不同
- **THEN** 显示候选依据并保留两份来源，不能声称语义相同或同一研究家族

### Requirement: Separate quality and human review
系统 SHALL 展示截断、无文本页、乱码、表格／布局限制、OCR状态及人工审核状态。人工标记绑定本人具体解析版本，不反写原文或自动确立事实。

#### Scenario: Owner flags a parsing problem
- **WHEN** 拥有者对某解析版本登记问题
- **THEN** 保存独立审核记录；另一主体不可写入，该标记不改变已保存正文或原报告
