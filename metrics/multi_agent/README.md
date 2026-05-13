# 主题 3: Tool-driven Multi-Agent Collaboration Metrics

## 概述

追踪**工具驱动多智能体协作**的效率和可靠性。

对应主题 3：多个专业 Agent 通过工具调用协作，非角色扮演。

## 采集指标

### 工具调用指标

| 指标 | 描述 | 目标 | 单位 |
|------|------|------|------|
| `tool_call_total` | 工具调用总次数 | - | 次 |
| `tool_call_success_rate` | 工具调用成功率 | >90% | % |
| `tool_call_error_rate` | 工具调用错误率 | <5% | % |
| `tool_call_timeout_rate` | 工具调用超时率 | <2% | % |
| `tool_call_avg_duration` | 平均调用时长 | <2s | 毫秒 |
| `tool_call_efficiency` | 有效调用率 | >80% | % |

### Agent 级指标

| 指标 | 描述 | 目标 | 单位 |
|------|------|------|------|
| `agent_call_count` | 各 Agent 调用次数 | - | 次 |
| `agent_success_count` | 各 Agent 成功次数 | - | 次 |
| `agent_error_count` | 各 Agent 错误次数 | - | 次 |
| `agent_efficiency` | 各 Agent 效率 | >80% | % |
| `agent_avg_duration` | 各 Agent 平均时长 | - | 毫秒 |

### 协作指标

| 指标 | 描述 | 目标 | 单位 |
|------|------|------|------|
| `parallel_calls` | 并行调用次数 | - | 次 |
| `sequential_calls` | 顺序调用次数 | - | 次 |
| `fan_out_count` | 扇出次数 | - | 次 |
| `fan_in_count` | 扇入次数 | - | 次 |
| `handover_count` | 交接次数 | - | 次 |

### 成本指标

| 指标 | 描述 | 目标 | 单位 |
|------|------|------|------|
| `total_cost_usd` | 总成本 | - | USD |
| `cost_per_call` | 每次调用成本 | - | USD |
| `tokens_per_call` | 每次调用 Token | - | Token |

## 采集方法

通过 `app/graph/state.py` 中的 `ToolCallRecord` 和 `ToolInvocationHistory` 采集。

## 使用示例

```python
from metrics.multi_agent.collector import MultiAgentMetricsCollector

collector = MultiAgentMetricsCollector()
collector.record_tool_call(agent="search", tool="duckduckgo_search", ...)
collector.record_agent_collaboration(agent="browser", parallel_calls=[...])

metrics = collector.get_metrics()
collector.export_json("metrics/multi_agent/data.jsonl")
```
