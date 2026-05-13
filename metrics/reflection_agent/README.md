# 主题 5: Self-Reflection & Verification Metrics

## 概述

追踪**自校验与验证**的质量和效率。

对应主题 5：反思循环 + 证据校验 + 质量门控。

## 采集指标

### 校验质量指标

| 指标 | 描述 | 目标 | 单位 |
|------|------|------|------|
| `reflection_success_rate` | 反思校验成功率 | >85% | % |
| `hallucination_rate` | 幻觉率 | <5% | % |
| `hallucination_detection_rate` | 幻觉检出率 | >80% | % |
| `confidence_accuracy` | 置信度准确性 | >0.7 | 相关系数 |
| `false_positive_rate` | 误报率 | <10% | % |
| `false_negative_rate` | 漏报率 | <15% | % |

### 校验维度指标

| 指标 | 描述 | 目标 | 单位 |
|------|------|------|------|
| `factuality_score` | 事实性评分 | >0.85 | 分 |
| `consistency_score` | 一致性评分 | >0.80 | 分 |
| `completeness_score` | 完整性评分 | >0.75 | 分 |
| `citation_coverage` | 引用覆盖率 | >95% | % |
| `overall_confidence` | 整体置信度 | >0.80 | 分 |

### 重规划效率指标

| 指标 | 描述 | 目标 | 单位 |
|------|------|------|------|
| `revision_count` | 重规划次数 | ≤3 | 次 |
| `revision_success_rate` | 重规划后成功率 | >70% | % |
| `revision_convergence_rate` | 重规划收敛率 | >80% | % |
| `avg_revisions_to_pass` | 平均通过次数 | <2 | 次 |

### 声明级指标

| 指标 | 描述 | 目标 | 单位 |
|------|------|------|------|
| `total_claims` | 总声明数 | - | 个 |
| `verified_claims` | 已验证声明数 | - | 个 |
| `hallucinated_claims` | 幻觉声明数 | - | 个 |
| `conflicting_claims` | 冲突声明数 | - | 个 |

## 采集方法

通过 `app/agents/reflection.py` 中的 `ReflectionResult` 采集。

## 使用示例

```python
from metrics.reflection.collector import ReflectionMetricsCollector

collector = ReflectionMetricsCollector()
collector.record_reflection(
    session_id="...",
    verification=VerificationResult(...),
)
collector.record_revision(session_id="...", success=True)

metrics = collector.get_metrics()
collector.export_json("metrics/reflection/data.jsonl")
```
