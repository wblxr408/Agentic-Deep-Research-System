# Spec Delta

## Purpose

让用户保留资料的直接定位、词汇检索及可选稠密查询有明确的索引选择、实际覆盖与来源版本，并允许本人在原文和特征不变时重建、关闭或回滚词汇索引。未发布或过期代际不能参与查询，索引改变不能覆盖原任务报告依据。

## ADDED Requirements

### Requirement: Traceable independent candidate channels
系统 SHALL 为精确／词汇／可选稠密／结构候选保留查询表示、原始排名与分数含义、候选标识、共同范围及配额。未配置的表示模型或索引 SHALL 显式跳过，不以词汇匹配冒充该能力。

#### Scenario: Independent channel failure
- **WHEN** FTS、BM25或其他请求通道部分失败
- **THEN** 记录失败和其他合法结果，各路原始排名可追溯；全部请求通道失败 SHALL 形成失败状态，不能宣称成功空检索

#### Scenario: Metadata-only mode
- **WHEN** 用户明确选择structured内部查询
- **THEN** 只按冻结筛选与入库／ID次序取得合法块，不编码或相关性重排，不将排序当价值判断

#### Scenario: Source structure auxiliary candidates
- **WHEN** 明确entity／chunk选择器取得合法种子
- **THEN** 最多5种子及一次同源当前解析／发布版本的父级兄弟块扩展，记录实际结构路径，词面提及不能成为已核身份或合作关系

### Requirement: Typed business conditions inside trusted scope
系统 SHALL 支持有界类型化业务AND／OR、存在与范围条件，并冻结请求策略及版本。可信owner、当前group、生命周期与已发布文档版本 SHALL 在业务OR外独立执行；字段与SQL表达式只由应用定义，值全部参数化。

#### Scenario: Same business filter across channels
- **WHEN** 查询使用FTS、BM25或精确向量
- **THEN** 三者候选以及BM25语料统计 SHALL 使用同一业务条件和可信范围；不以过滤前统计冒称过滤后语料，也不在模型消费后才过滤权限

#### Scenario: Missing field or unsupported condition
- **WHEN** 字段缺失、条件类型错误或请求了不可执行的策略
- **THEN** 比较排除缺失，显式missing／exists判断存在性；类型或策略错误在派发前拒绝，不静默忽略条件

#### Scenario: Revocation or changed published generation
- **WHEN** 候选取得后、进入重排或返回前，来源许可、业务条件或当前代际发生变化
- **THEN** 重新核对合法文档ID与原access revision，剔除失效候选并保留结果不足，不用旧缓存填满数量

#### Scenario: Bounded selectivity observation
- **WHEN** 本人合法块超过10001项
- **THEN** 记录观察上限及观察内保留比例，不推断全库选择率；正式候选检索继续使用完整合法范围

### Requirement: Explicit access choice
系统 SHALL 支持来源仅直接定位或加入词汇检索，选择记录到索引状态。直接定位模式不得通过其他召回通道被自动检索；开启检索不改变owner、来源范围或任务许可。

#### Scenario: Source kept for direct citation only
- **WHEN** 来源处于直接定位模式
- **THEN** 本人可按原位置读取，跨资料词汇／向量查询不返回它，直到本人明确启用

### Requirement: Atomic owned index publication
系统 SHALL 在完整生成已采用索引并保存实际覆盖后原子发布代际；未发布、失败或旧head的结果不能覆盖当前代际。生命周期动作必须绑定认证owner、来源／表示版本、预期head及幂等请求。

#### Scenario: Build fails or stale request arrives
- **WHEN** 新构建失败或请求预期head已经过期
- **THEN** 旧已发布索引继续有效，旧原文／报告不改写；重复已提交请求返回同一次结果，修改同请求参数拒绝

### Requirement: Scoped lexical statistics
系统 SHALL 在当前owner、分组、启用来源和已发布代际内计算倒排词频／文档频率和BM25，并标明实际特征覆盖。旧无词项代际可有全文回退，不能伪装为完整BM25语料。

#### Scenario: Source moved or archived
- **WHEN** 来源分组或状态发生变化
- **THEN** 新查询的候选、N／DF及结果按当前范围计算，旧缓存或倒排记录不能越过当前范围

### Requirement: Compatible exact dense access
系统 SHALL 只在相同实际编码身份和当前授权范围内比较向量。默认不因存在向量就创建近似索引，候选近似／量化方法需要有明确选择与适用依据。

#### Scenario: Existing approximate index belongs to old deployment
- **WHEN** 默认精确查询执行
- **THEN** 先固定可访问且编码兼容的候选范围再计算距离，不让旧全局近似索引影响本次完整范围语义，也不删除旧数据

### Requirement: Owned lifecycle visibility
系统 SHALL 允许本人查看当前选择／代际／覆盖并显式重建、关闭或回滚到同来源版本的已保留代际，动作不重新采集、解析或编码。旧无索引记录保持明确未知，不自动追认已构建。

#### Scenario: Rollback after rebuild
- **WHEN** 本人选择仍保留且版本一致的旧代际并提交当前预期head
- **THEN** 后续查询使用被选代际；原文、特征及旧报告引用保持原版本，其他owner不能执行该动作
### Requirement: Bounded source-preserving candidate fusion
The system SHALL freeze the fusion policy and forward its identity through the existing owner-bound tool handoff. Each route SHALL retain original rank, raw score meaning, direction and source identity. Fusion SHALL organize internal chunks and external discovery independently without creating factual support or widening access.

#### Scenario: A requested intersection route produces no candidates
- **WHEN** a requested route is empty, failed or unexecuted
- **THEN** intersection does not silently omit that route to produce a larger result
- **AND** the missing route status remains visible

#### Scenario: Scores cannot be compared within a route
- **WHEN** score normalization is selected but the route lacks usable finite scores
- **THEN** that route uses an explicitly recorded rank-based method
- **AND** synthetic search relevance is not treated as calibrated score evidence

#### Scenario: Similar bodies appear in different sources
- **WHEN** bounded lexical overlap groups near-duplicate candidates
- **THEN** original candidate IDs, source identities and route memberships remain available
- **AND** overlap or route agreement does not count as independent corroboration

