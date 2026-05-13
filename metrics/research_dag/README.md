# 主题 2: Research DAG Generation Metrics

## 概述

追踪**研究 DAG 生成**的质量和执行效率。

对应主题 2：动态生成研究计划 DAG，支持并行与条件分支。

## 采集指标

### DAG 生成质量指标

| 指标 | 描述 | 目标 | 单位 |
|------|------|------|------|
| `dag_generation_success_rate` | DAG 生成成功率 | ≥90% | % |
| `dag_node_count` | 每个 DAG 的节点数 | 3-10 | 个 |
| `dag_edge_count` | 每个 DAG 的边数 | 0-10 | 条 |
| `dag_depth` | DAG 最大深度 | 2-5 | 层 |
| `dag_plan_coverage` | 计划覆盖维度 | >90% | % |

### DAG 执行效率指标

| 指标 | 描述 | 目标 | 单位 |
|------|------|------|------|
| `parallelism_factor` | 并行度因子 | >2x | 倍 |
| `estimated_vs_actual_duration` | 预估 vs 实际时长比 | 0.8-1.2 | 比值 |
| `batch_execution_count` | 批次执行次数 | - | 次 |
| `nodes_per_batch` | 每批节点数 | 1-5 | 个 |

### 节点级指标

| 指标 | 描述 | 目标 | 单位 |
|------|------|------|------|
| `node_type_distribution` | 节点类型分布 | 均衡 | % |
| `dependency_accuracy` | 依赖关系准确率 | >85% | % |
| `node_success_rate_by_type` | 各类型节点成功率 | >80% | % |

## 采集方法

通过 Planner Agent 输出和 DAG 执行监控采集。

## 使用示例

```python
from metrics.research_dag.collector import DAGMetricsCollector

collector = DAGMetricsCollector()
collector.record_dag_generated(dag_id="...", nodes=[...], edges=[...])
collector.record_dag_execution(dag_id="...", batch_execution=[...])

metrics = collector.get_metrics()
collector.export_json("metrics/research_dag/data.jsonl")
```
