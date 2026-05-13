# 主题 4: Long-running Stateful Agent Metrics

## 概述

追踪**长生命周期有状态智能体**的持久化和恢复能力。

对应主题 4：检查点持久化 + 会话恢复 + 长时间运行。

## 采集指标

### 检查点指标

| 指标 | 描述 | 目标 | 单位 |
|------|------|------|------|
| `checkpoint_save_count` | 检查点保存次数 | - | 次 |
| `checkpoint_save_duration` | 检查点保存时长 | <100ms | 毫秒 |
| `checkpoint_save_error_rate` | 检查点保存错误率 | <1% | % |
| `checkpoint_restore_count` | 检查点恢复次数 | - | 次 |
| `checkpoint_restore_error_rate` | 检查点恢复错误率 | <5% | % |
| `checkpoint_size_avg` | 平均检查点大小 | <1MB | bytes |

### 会话指标

| 指标 | 描述 | 目标 | 单位 |
|------|------|------|------|
| `session_active_count` | 活跃会话数 | - | 个 |
| `session_avg_duration` | 平均会话时长 | - | 秒 |
| `session_max_duration` | 最大会话时长 | >1h | 秒 |
| `session_isolation_rate` | 会话隔离完整率 | 100% | % |
| `session_revival_count` | 会话恢复次数 | - | 次 |

### 故障恢复指标

| 指标 | 描述 | 目标 | 单位 |
|------|------|------|------|
| `failure_recovery_rate` | 故障自动恢复率 | >70% | % |
| `failure_detection_time` | 故障检测时间 | <30s | 秒 |
| `data_loss_rate` | 数据丢失率 | 0% | % |
| `state_recovery_latency` | 状态恢复延迟 | <5s | 秒 |

### 资源指标

| 指标 | 描述 | 目标 | 单位 |
|------|------|------|------|
| `memory_usage_per_session` | 每会话内存使用 | <500MB | MB |
| `redis_memory_usage` | Redis 内存使用 | <2GB | GB |
| `postgres_checkpoints` | PostgreSQL 检查点 | - | 个 |

## 采集方法

通过 PostgresSaver 和 Redis 监控采集。

## 使用示例

```python
from metrics.stateful_agent.collector import StatefulAgentMetricsCollector

collector = StatefulAgentMetricsCollector()
collector.record_checkpoint_save(session_id="...", size_bytes=...)
collector.record_failure_recovery(session_id="...", recovered=True)

metrics = collector.get_metrics()
collector.export_json("metrics/stateful_agent/data.jsonl")
```
