# 主题 1: Autonomous Research Workflow Metrics

## 概述

追踪**自主研究工作流**的端到端执行性能和正确性。

对应主题 1：用户输入 → 全自动端到端研究，无需人工干预。

## 采集指标

### 工作流执行指标

| 指标 | 描述 | 目标 | 单位 |
|------|------|------|------|
| `workflow_success_rate` | 成功完成的工作流占比 | ≥85% | % |
| `workflow_avg_duration` | 平均端到端时长 | - | 秒 |
| `workflow_p95_duration` | P95 时长 | <10min | 秒 |
| `workflow_p99_duration` | P99 时长 | <20min | 秒 |
| `workflow_completion_rate` | 工作流完成率（含失败） | ≥90% | % |

### 节点级指标

| 指标 | 描述 | 目标 | 单位 |
|------|------|------|------|
| `node_execution_count` | 各节点执行次数 | - | 次 |
| `node_avg_duration` | 各节点平均执行时长 | <5min | 毫秒 |
| `node_error_rate` | 各节点错误率 | <5% | % |
| `node_timeout_rate` | 各节点超时率 | <2% | % |

### 工作流状态指标

| 指标 | 描述 | 目标 | 单位 |
|------|------|------|------|
| `revision_count` | 重规划迭代次数 | ≤3 | 次 |
| `subagent_parallelism` | 平均并行子 Agent 数 | >2 | 个 |
| `state_update_count` | 每工作流状态更新次数 | - | 次 |
| `checkpoint_frequency` | 每工作流检查点保存次数 | - | 次 |

### 转换指标

| 指标 | 描述 | 目标 | 单位 |
|------|------|------|------|
| `edge_transition_count` | 总节点转换次数 | - | 次 |
| `conditional_branch_count` | 条件边评估次数 | - | 次 |
| `fan_out_count` | 并行扇出次数 | - | 次 |

## 采集方法

通过 LangGraph 检查点数据和 `app/graph/compiler.py` 中的嵌入式仪表采集。

## 使用示例

```python
from metrics.langgraph_workflow.collector import LangGraphMetricsCollector

collector = LangGraphMetricsCollector()
collector.record_workflow_start(session_id="...", query="...")
# ... 执行工作流 ...
collector.record_workflow_end(session_id="...", status="completed")

metrics = collector.get_metrics()
collector.export_json("metrics/langgraph_workflow/data.jsonl")
```
