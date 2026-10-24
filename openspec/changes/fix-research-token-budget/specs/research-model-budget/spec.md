# Spec Delta

## Purpose

将研究模型请求纳入根任务可执行配额，使规划、综合、反思、报告和最终语义审核共享真实有限资源，来源审核获得专用份额，并保留可解释的用量和预算暂停状态，避免事后记账掩盖超支。

## ADDED Requirements

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
