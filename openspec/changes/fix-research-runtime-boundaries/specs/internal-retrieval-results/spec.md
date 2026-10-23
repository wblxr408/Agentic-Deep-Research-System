# Spec Delta

## Purpose

定义内部资料检索结果及引用对调用方的交付契约，保证用户启用内部资料后真实命中能够形成有效证据，并保留来源和资料块标识供报告引用使用。

## ADDED Requirements

### Requirement: Retrieval hit delivery
系统 SHALL 将真实检索命中作为带有结构化引用的结果交付，不能因生产者与结果类型不一致而静默丢弃。

#### Scenario: Internal document hit
- **WHEN** 授权范围内的资料被混合检索命中
- **THEN** 调用方收到资料正文、块标识、评分和可序列化的来源引用
