# Spec Delta

## Purpose
复用可信注册表为当前研究阶段提供必要技能内容、参考资料和明确成本，同时使能力需求与权限限制分开；固定实际版本，阻止网页或模型自报指令扩大授权或无界占用上下文。

## ADDED Requirements

### Requirement: Progressive stage context
系统 SHALL 按阶段、领域和显式选择编译已注册技能，先使用元信息，再加载需要的指令/角色提示和可信内联参考；记录版本、生效/跳过原因、冲突和上下文预算。自动选择 MUST NOT 静默覆盖用户手选绘图或模板方案。
#### Scenario: Only relevant stage instructions
- **WHEN** 进入取证或报告阶段
- **THEN** 只取得该阶段适用的冻结内容，非相关完整会话/技能不会广播；必要内容超出预算时明确受阻，不能截断硬约束后假装已生效。

### Requirement: Requirements do not grant permissions
技能能力需求 SHALL 与工具权限限制分开，需求不足返回明确缺口；多项限制按交集执行，显式空许可保持拒绝。网页正文、任意路径、未授权外链或模型结果 MUST NOT 成为新的技能加载来源。
#### Scenario: Conflicting skills
- **WHEN** 一个技能需要的工具被任务或另一个生效限制禁止
- **THEN** 展示冲突及可修改项，在可信执行点保持禁止，不使用技能声明扩大许可。
