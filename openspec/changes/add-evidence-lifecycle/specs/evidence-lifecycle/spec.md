# Spec Delta

## Purpose

让研究资料的新增、修订、替换、停止使用和删除有明确的版本及保存范围。用户能够知道哪个版本参与后续检索，访问变化在查询时生效，同时旧报告保留其原有证据和修订关联，不把新索引当作历史报告依据。

## ADDED Requirements

### Requirement: Public archival provenance remains distinct from access scope
系统 SHALL 区分本人保存权限与公开原文的数据级别。只有服务端确认的公开归档事件与当前owner、来源ID及实际正文版本一致时，当前访问快照才 SHALL 为RAG分级携带公开来源依据；可编辑metadata或公网URL MUST NOT 单独证明public。更高限制、当前访问条件及模型类别上限仍有效。

#### Scenario: Reuse an explicitly archived public paper
- **WHEN** 当前owner显式归档真实取得的公开原文，之后发布索引并在许可范围检索同一正文版本
- **THEN** 该来源可保留public依据，仍执行owner／任务／组／有效期及版本检查，不因资料公开而向其他owner开放

#### Scenario: Revised text or legacy unbound archive
- **WHEN** 正文生成新来源版本，或历史归档事件缺少可验证正文绑定
- **THEN** 不沿用旧公开证明，按现有保守规则及实际限制信号分级，不猜测旧来源公开或复制旧权限

### Requirement: Immutable source revisions
系统 SHALL 通过独立来源版本保存正文修订，支持全文替换和绑定旧版本原位范围的局部修订；同一版本族只允许一个当前版本。新版本失败不得替换当前版本，旧报告依据不得被覆盖。

#### Scenario: Correct a passage
- **WHEN** 本人提交旧版本、原位范围及替换文字并明确修订原因
- **THEN** 系统生成新版本并保留前驱关联；旧任务引用不改写，受影响报告可从修订记录查到

### Requirement: Explicit reuse and validity
系统 SHALL 默认限制新资料在绑定任务内使用；分组沿用和本人跨任务检索必须显式选择。查询必须复核当前owner、实际任务、分组、当前版本、生效期与删除状态；模型不得提供可信任务身份。

#### Scenario: Task source used elsewhere
- **WHEN** 另一任务或没有可信任务身份的调用检索任务级资料
- **THEN** 所有召回通道、统计及上下文扩展均不包含该资料；未绑定资料仍可由本人直接定位

### Requirement: Recoverable and physical removal
系统 SHALL 支持Tombstone、恢复及显式永久清理；过期／已删除／非当前版本不参与新检索。清理必须绑定当前状态并限制数量，不能删除当前生效版本或默认启动无人值守清理。

#### Scenario: Delete then restore
- **WHEN** 本人删除来源后再恢复
- **THEN** 删除期间查询不可见，恢复时保留原文；同族已有当前版本时恢复不会悄悄替换它

### Requirement: Atomic version publication
系统 SHALL 为新增和增量索引复用原事务边界，允许有界多版本发布原子切换。动作必须有幂等ID及预期状态；重复请求只有一次业务效果，过期或跨owner请求被拒绝。

#### Scenario: Batch contains stale member
- **WHEN** 一批发布的任一成员版本已变化
- **THEN** 整批不切换，原当前版本及索引仍有效

### Requirement: Traceable invalidation and maintenance
系统 SHALL 保存带修订原因的变更记录和访问版本，后续查询复核当前状态，缓存不可跨访问版本复用。文字／样式／权重修改不得自动重建证据；索引维护采用明确选择并呈现实际效果和未采用候选理由。

#### Scenario: Recalculate weights
- **WHEN** 用户只修改报告版式或匹配权重
- **THEN** 来源原文及检索代际不改变；事实纠正另建修订并关联其受影响报告
