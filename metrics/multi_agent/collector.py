"""
主题 3: Tool-driven Multi-Agent Collaboration Metrics Collector.

采集工具驱动多智能体协作的效率和可靠性指标。
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRecord:
    """单次工具调用记录"""
    call_id: str
    agent_type: str
    tool_name: str
    started_at: str
    ended_at: str | None = None
    duration_ms: int | None = None
    status: str = "pending"
    result_summary: str | None = None
    error: str | None = None
    cost_usd: float = 0.0
    tokens_used: int = 0


@dataclass
class AgentCollaborationRecord:
    """Agent 协作记录"""
    collaboration_id: str
    collaboration_type: str  # parallel, sequential, fan_out, fan_in
    agents: list[str]
    started_at: str
    ended_at: str | None = None
    duration_ms: int | None = None
    success: bool = True


@dataclass
class SessionMetrics:
    """会话级指标"""
    session_id: str
    total_tool_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    agent_stats: dict[str, dict] = field(default_factory=dict)


class MultiAgentMetricsCollector:
    """
    主题 3: 工具驱动多 Agent 协作指标采集器。

    采集：
    - 工具调用成功率、错误率、超时率
    - 各 Agent 调用次数、效率
    - 并行/顺序调用统计
    - 成本和 Token 消耗
    """

    def __init__(self, output_dir: str | Path = "metrics/multi_agent/data"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._tool_calls: dict[str, ToolCallRecord] = {}
        self._collaborations: list[AgentCollaborationRecord] = []
        self._sessions: dict[str, SessionMetrics] = {}

    def record_tool_call_start(
        self,
        call_id: str | None = None,
        agent_type: str = "",
        tool_name: str = "",
    ) -> str:
        """记录工具调用开始"""
        call_id = call_id or f"call-{uuid.uuid4().hex[:8]}"
        record = ToolCallRecord(
            call_id=call_id,
            agent_type=agent_type,
            tool_name=tool_name,
            started_at=datetime.utcnow().isoformat(),
        )
        self._tool_calls[call_id] = record
        return call_id

    def record_tool_call_end(
        self,
        call_id: str,
        status: str = "success",
        result_summary: str | None = None,
        error: str | None = None,
        cost_usd: float = 0.0,
        tokens_used: int = 0,
    ) -> None:
        """记录工具调用结束"""
        if call_id not in self._tool_calls:
            logger.warning(f"[Metrics] Unknown tool call: {call_id}")
            return

        record = self._tool_calls[call_id]
        record.ended_at = datetime.utcnow().isoformat()
        record.status = status
        record.result_summary = result_summary
        record.error = error
        record.cost_usd = cost_usd
        record.tokens_used = tokens_used

        # 计算时长
        if record.ended_at and record.started_at:
            start_dt = datetime.fromisoformat(record.started_at)
            end_dt = datetime.fromisoformat(record.ended_at)
            record.duration_ms = int((end_dt - start_dt).total_seconds() * 1000)

    def record_agent_stats(
        self,
        session_id: str,
        agent_type: str,
        calls: int,
        successes: int,
        failures: int,
        total_duration_ms: int = 0,
    ) -> None:
        """记录 Agent 级统计"""
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionMetrics(session_id=session_id)

        session = self._sessions[session_id]
        session.agent_stats[agent_type] = {
            "calls": calls,
            "successes": successes,
            "failures": failures,
            "total_duration_ms": total_duration_ms,
            "avg_duration_ms": total_duration_ms / calls if calls > 0 else 0,
            "success_rate": successes / calls if calls > 0 else 0,
        }

    def record_collaboration(
        self,
        collaboration_type: str,
        agents: list[str],
        duration_ms: int | None = None,
        success: bool = True,
    ) -> str:
        """记录 Agent 协作"""
        collab_id = f"collab-{uuid.uuid4().hex[:8]}"
        record = AgentCollaborationRecord(
            collaboration_id=collab_id,
            collaboration_type=collaboration_type,
            agents=agents,
            started_at=datetime.utcnow().isoformat(),
            ended_at=datetime.utcnow().isoformat(),
            duration_ms=duration_ms,
            success=success,
        )
        self._collaborations.append(record)
        return collab_id

    def get_metrics(self) -> dict[str, Any]:
        """获取聚合指标"""
        if not self._tool_calls:
            return {}

        # 工具调用聚合
        total_calls = len(self._tool_calls)
        successful_calls = sum(1 for c in self._tool_calls.values() if c.status == "success")
        failed_calls = sum(1 for c in self._tool_calls.values() if c.status == "error")
        timeout_calls = sum(1 for c in self._tool_calls.values() if c.status == "timeout")

        durations = [c.duration_ms for c in self._tool_calls.values() if c.duration_ms]
        costs = [c.cost_usd for c in self._tool_calls.values() if c.cost_usd]
        tokens = [c.tokens_used for c in self._tool_calls.values() if c.tokens_used]

        # 按 Agent 分组
        agent_stats: dict[str, dict] = {}
        for call in self._tool_calls.values():
            agent = call.agent_type
            if agent not in agent_stats:
                agent_stats[agent] = {
                    "total": 0, "success": 0, "error": 0, "timeout": 0,
                    "total_duration_ms": 0, "total_cost": 0.0, "total_tokens": 0,
                }
            agent_stats[agent]["total"] += 1
            if call.status == "success":
                agent_stats[agent]["success"] += 1
            elif call.status == "error":
                agent_stats[agent]["error"] += 1
            elif call.status == "timeout":
                agent_stats[agent]["timeout"] += 1
            agent_stats[agent]["total_duration_ms"] += call.duration_ms or 0
            agent_stats[agent]["total_cost"] += call.cost_usd
            agent_stats[agent]["total_tokens"] += call.tokens_used

        for agent in agent_stats:
            stats = agent_stats[agent]
            if stats["total"] > 0:
                stats["success_rate"] = stats["success"] / stats["total"]
                stats["avg_duration_ms"] = stats["total_duration_ms"] / stats["total"]
            else:
                stats["success_rate"] = 0.0
                stats["avg_duration_ms"] = 0.0

        # 协作聚合
        collab_types: dict[str, int] = {}
        for collab in self._collaborations:
            collab_types[collab.collaboration_type] = collab_types.get(collab.collaboration_type, 0) + 1

        return {
            "tool_calls": {k: asdict(v) for k, v in self._tool_calls.items()},
            "collaborations": [asdict(c) for c in self._collaborations],
            "sessions": {k: asdict(v) for k, v in self._sessions.items()},
            "summary": {
                "total_tool_calls": total_calls,
                "success_count": successful_calls,
                "error_count": failed_calls,
                "timeout_count": timeout_calls,
                "success_rate": successful_calls / total_calls if total_calls > 0 else 0,
                "error_rate": failed_calls / total_calls if total_calls > 0 else 0,
                "timeout_rate": timeout_calls / total_calls if total_calls > 0 else 0,
                "avg_duration_ms": sum(durations) / len(durations) if durations else 0,
                "p95_duration_ms": sorted(durations)[int(len(durations) * 0.95)] if durations else 0,
                "total_cost_usd": sum(costs),
                "total_tokens": sum(tokens),
                "agent_stats": agent_stats,
                "collaboration_types": collab_types,
            },
        }

    def export_json(self, filepath: str | Path) -> None:
        """导出指标到 JSONL 文件"""
        metrics = self.get_metrics()
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(metrics, ensure_ascii=False) + "\n")
        logger.info(f"[Metrics] Exported to {filepath}")

    def clear(self) -> None:
        """清空当前指标（用于测试或重置）"""
        self._tool_calls.clear()
        self._collaborations.clear()
        self._sessions.clear()
