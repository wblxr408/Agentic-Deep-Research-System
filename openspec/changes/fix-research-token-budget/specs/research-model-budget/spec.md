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
