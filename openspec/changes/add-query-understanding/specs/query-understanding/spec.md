# Spec Delta

## Purpose
在任何取证或模型成本发生前，把用户查询解释为可见、可修订且有边界的研究契约；以显式上下文、必要澄清和冻结配置保证规划、恢复和交付使用同一研究目标。

## ADDED Requirements

### Requirement: Bounded query interpretation
系统 SHALL 返回事实、聚合、比较、多跳、探索式分类、实际命中规则、实体原文位置及候选链接、语义槽位、时间模式、复杂度与成本未知项，允许用户修正；模型自报置信度 MUST NOT 代替事实与归属验证。
#### Scenario: Explicit comparison
- **WHEN** 用户明确选择两个对象并请求比较
- **THEN** 解释保留两个对象及分类依据，指出可能独立研究的子问题和预算上限，不额外发起分类模型调用。

### Requirement: Explicit context and clarification
系统 SHALL 仅从当前主体可访问且显式指定的历史会话读取有界对象状态；未解指代、同名冲突和互相矛盾的时间 SHALL 在创建或计费前形成可修改的澄清项。
#### Scenario: Ambiguous reference
- **WHEN** 查询“它的研究趋势”而当前与显式上下文存在多个候选
- **THEN** 用户可选对象或改写问题，未解决时不创建研究，不默认采用最近一条会话。
#### Scenario: Foreign context
- **WHEN** 指定其他owner会话
- **THEN** 返回统一不存在，不泄露候选对象、证据、权限或预算。

### Requirement: Frozen task and delivery
系统 SHALL 在创建时复算解释，将问题、对象/学科/时间/来源、目的/模块/权重、交付模板/主题/页面/绘图描述和实际技能版本固定并供恢复及结果读取；预览过期 SHALL 返回更新解释。声明式交付描述 MUST NOT 扩大授权。
#### Scenario: Preview changes
- **WHEN** 预览后对象、范围、配置或所选上下文版本改变
- **THEN** 创建拒绝旧解释标识并返回当前预览；用户可重读后提交，不静默沿用。
#### Scenario: Resume a run
- **WHEN** 恢复同一研究
- **THEN** 沿用已冻结解释与交付，不重新读取当前历史会话或重算“今年”，旧会话无解释时明确标记legacy。
