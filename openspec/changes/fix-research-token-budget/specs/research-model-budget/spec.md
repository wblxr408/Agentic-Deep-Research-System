# Spec Delta

## Purpose

将研究模型请求纳入根任务可执行配额，使规划、综合、反思、报告和最终语义审核共享真实有限资源，来源审核获得专用份额，并保留可解释的用量和预算暂停状态，避免事后记账掩盖超支。

## ADDED Requirements

### Requirement: Manual limits with headroom recommendations
系统 SHALL 根据当前对象、模块、研究深度和交付形式给出初步复杂度、预计用量、冗余比例及建议上限，不增加模型调用或自动加额。用户 SHALL 可手动设置Token、工具次数和从原创建时间计的总执行时长，预览及实际执行 MUST 使用同一有效配置。

#### Scenario: A deep multi-module research request
- **WHEN** 用户选择深入研究与多个模块
- **THEN** 建议为重试、补证及完整审核预留35%—75%冗余，显示估算与总额的区别；采用建议是明确用户操作

### Requirement: Owner-authorized paused budget revisions
系统 SHALL 允许本人在任务暂停且无在途请求时，按当前execution、budget_revision及幂等request_id修订上限。系统 MUST 保留累计用量、未知收据、原创建时间和恢复次数，保存旧／新配置与授权时间；建议或自动恢复不能自行修订额度。

#### Scenario: An owner raises a paused task's limit
- **WHEN** 本人提交有效新上限且状态、execution及revision仍匹配
- **THEN** 原事务更新根快照和数值视图，累计用量不变、原期限起点不变；不自动启动模型，后续继续原恢复与来源校验

#### Scenario: Another user or stale revision edits limits
- **WHEN** 任务不属于当前用户、状态仍运行、存在在途请求或revision过期
- **THEN** 变更不生效，不重置已发生用量；相同请求参数重放只产生一次预算修订

### Requirement: Pre-request token admission
系统 SHALL 在每次实际模型请求前预占输入及最大输出，并调整输出上限或拒绝请求；备用尝试 SHALL 重新准入。未知失败用量 MUST NOT 自动当作零消费。

#### Scenario: Insufficient report input allowance
- **WHEN** 报告输入已经超过其可用配额
- **THEN** 不调用供应商，保留研究状态并报告预算不足

### Requirement: Reserved final audit
系统 SHALL 为报告与最终语义审核保留Token和时间，前序阶段及可选检索不能耗尽这些份额。审核不完整时 SHALL 保留not_checked而不作为已完成审核交付。

#### Scenario: Large batch cannot fit
- **WHEN** 审核批次整体装不进额度但单条主张能够审核
- **THEN** 缩小批次执行可完成判断，其余项明确未核

### Requirement: Lossless shared audit passages
审核 SHALL 保留每项显式引用的全部来源范围及原有选段，不用默认三来源上限裁掉复合主张依据。重叠原文可按来源边界拆成共享片段，但每项局部passage MUST 由有序片段完整恢复，不加入其他主张才可用的文字。系统 SHALL 保留全部主张及原预算／期限，载荷仍超限的项目保持未核，不以裁掉事实获得通过。

#### Scenario: Compound claim across several papers
- **WHEN** 一项主张引用四篇或更多论文，且比较中的多个事实需要不同原文
- **THEN** 所有被引来源都参与选段，模型可返回多个本项局部passage_numbers，服务器逐个核对编号及精确原文；任何非法锚点不能记为支持

#### Scenario: Overlapping passages in separated report sections
- **WHEN** 报告不同位置的主张使用重叠选段
- **THEN** 可按实际共享量同批核对且重叠文字只发一次，每项仍只能使用其自身passage列出的片段；结果保持原报告顺序，旧契约判定不跨版本复用

#### Scenario: Content correction batch cannot fit
- **WHEN** 唯一内容修订轮的段落原文符合批次上界，但包含问题和许可原文的完整消息超过剩余写作准入
- **THEN** 先拆分尚未派发的批次再请求，不重试已处理段落；单段仍装不下或任一必要修订失败时保留原稿及已收到响应，不发布部分修订，不动用额外额度

### Requirement: Account actual usage and recompute limits
系统 SHALL 接收流式及非流式供应商usage，合并所有模型尝试与工具用量，更新后重算预算状态；未知价格 SHALL 单独标识。

#### Scenario: Final stage crosses the limit
- **WHEN** 新返回的实际usage达到或超过根上限
- **THEN** 保存实际用量和停止原因，停止后续请求，不通过截断计数维持表面合法

### Requirement: Bounded report continuation
系统 SHALL 允许已完成分析的同一根任务对结构无效或流中断的报告最多进行一次显式续作。续作 MUST 复核owner、冻结输入、产物绑定、当前资料、原创建时间、累计用量与原期限，以事务execution及checkpoint裁决并发，直接进入报告阶段而非重新取证。旧失败、原始响应和报告历史 MUST 保留。

#### Scenario: Continue after report contract failure
- **WHEN** 本人任务的分析已完整保存、报告校验失败，原期限和可用额度仍足以准入
- **THEN** 同根开始一次新的报告执行，完整审核后才可发布，累计用量和截止时间不重置

#### Scenario: Repeated or expired report continuation
- **WHEN** 报告续作次数已满、状态变化、输入或来源变化、额度或原期限不足
- **THEN** 拒绝新的模型调用，保留当前资料、失败与用量
