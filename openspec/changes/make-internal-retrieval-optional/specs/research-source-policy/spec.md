# Spec Delta

## Purpose

为研究任务提供明确、一致的资料来源策略：公开研究默认通过联网获取证据，用户可以补充检索自己的内部资料；内部资料的返回数量不能代替研究覆盖度判断，也不能控制联网是否执行。

## ADDED Requirements

### Requirement: Public research by default
系统 SHALL 默认联网研究且关闭内部资料检索，规划、模型失败回退和重规划均须遵守请求的来源选择及现有工具许可。

#### Scenario: Default research
- **WHEN** 用户未启用内部资料，规划器提出包含内部检索的计划
- **THEN** 系统仅执行获许可的公开信息取证，内部检索不得执行或阻塞搜索和浏览

#### Scenario: Fallback and revision
- **WHEN** 规划模型输出无效内容或研究需要重规划
- **THEN** 系统继续采用默认联网及当前内部资料选择，不得恢复旧的内部优先策略

### Requirement: Explicit internal document retrieval
系统 SHALL 接受默认 false 的 `use_internal_docs` 选项；启用后检索当前用户的资料，可用 `rag_group` 限定范围，且不得赋予技能许可之外的工具权限。

#### Scenario: Supplementary documents
- **WHEN** 用户启用内部资料并指定分组
- **THEN** 系统可同时调度联网与该用户该分组的内部检索，分析接收两类证据

#### Scenario: Disabled document access
- **WHEN** 选项关闭而模型、技能或旧任务状态包含内部检索节点
- **THEN** 系统不得执行内部检索，分组值不得隐式启用它

### Requirement: Web research independent of retrieval hits
系统 SHALL 继续执行计划中的获许可联网节点，无论内部检索命中、返回空结果或不可用；调用和时间预算仍可终止研究。

#### Scenario: Hit followed by web collection
- **WHEN** 内部检索返回资料，旧字段 `allow_web_after_rag_hit` 为 false
- **THEN** 搜索和浏览仍可执行，研究保留内部与公开证据

#### Scenario: Empty or unavailable documents
- **WHEN** 内部检索无结果或检索能力不可用
- **THEN** 联网取证继续，不要求内部资料作为前置条件

### Requirement: User controls and compatibility
系统 SHALL 在研究界面默认关闭内部资料开关，仅在启用时允许编辑并提交分组；旧联网开关字段须被忽略，恢复时缺少新选项默认关闭内部检索。

#### Scenario: Toggle and submit
- **WHEN** 用户启用资料、填写分组后再关闭并提交研究
- **THEN** 请求关闭内部检索且不提交有效分组，所选公开渠道保持有效

#### Scenario: Legacy request or pending state
- **WHEN** 旧客户端或待执行状态只包含旧联网开关和内部优先策略
- **THEN** 这些字段不得决定新执行的联网行为或授予内部资料读取权限
