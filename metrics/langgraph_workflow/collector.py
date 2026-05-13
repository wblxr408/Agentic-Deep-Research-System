"""
主题 1: Autonomous Research Workflow Metrics Collector.

采集自主研究工作流的端到端执行性能和正确性指标。
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WorkflowRecord:
    """单个工作流执行记录"""
    workflow_id: str
    session_id: str
    user_query: str
    started_at: str
    ended_at: str | None = None
    duration_ms: int | None = None
    status: str = "running"  # running, completed, failed, paused
    revision_count: int = 0
    node_executions: dict[str, dict] = field(default_factory=dict)
    state_updates: int = 0
    checkpoint_count: int = 0
    edge_transitions: int = 0
    conditional_branches: int = 0
    fan_outs: int = 0
    error_message: str | None = None


@dataclass
class NodeExecution:
    """单个节点执行记录"""
    node_name: str
    started_at: str
    ended_at: str | None = None
    duration_ms: int | None = None
    status: str = "pending"
    error: str | None = None


class LangGraphMetricsCollector:
    """
    主题 1: 自主研究工作流指标采集器。

    采集：
    - 工作流成功率、时长分布
    - 节点执行次数、错误率、超时率
    - 重规划次数、并行度
    - 状态更新次数、检查点频率
    - 边转换次数、条件分支次数
    """

    def __init__(self, output_dir: str | Path = "metrics/langgraph_workflow/data"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 内存中的指标
        self._workflows: dict[str, WorkflowRecord] = {}
        self._node_executions: list[NodeExecution] = []

    def record_workflow_start(
        self,
        session_id: str,
        query: str,
        workflow_id: str | None = None,
    ) -> str:
        """记录工作流开始"""
        wf_id = workflow_id or f"wf-{uuid.uuid4().hex[:8]}"
        record = WorkflowRecord(
            workflow_id=wf_id,
            session_id=session_id,
            user_query=query,
            started_at=datetime.utcnow().isoformat(),
        )
        self._workflows[wf_id] = record
        logger.info(f"[Metrics] Workflow started: {wf_id}")
        return wf_id

    def record_node_start(
        self,
        workflow_id: str,
        node_name: str,
    ) -> None:
        """记录节点开始执行"""
        if workflow_id not in self._workflows:
            logger.warning(f"[Metrics] Unknown workflow: {workflow_id}")
            return

        self._workflows[workflow_id].node_executions[node_name] = {
            "started_at": datetime.utcnow().isoformat(),
            "status": "running",
        }

    def record_node_end(
        self,
        workflow_id: str,
        node_name: str,
        status: str = "success",
        error: str | None = None,
    ) -> None:
        """记录节点执行结束"""
        if workflow_id not in self._workflows:
            return

        wf = self._workflows[workflow_id]
        if node_name not in wf.node_executions:
            logger.warning(f"[Metrics] Unknown node: {node_name}")
            return

        started = wf.node_executions[node_name]["started_at"]
        start_dt = datetime.fromisoformat(started)
        duration_ms = int((datetime.utcnow() - start_dt).total_seconds() * 1000)

        wf.node_executions[node_name].update({
            "ended_at": datetime.utcnow().isoformat(),
            "duration_ms": duration_ms,
            "status": status,
            "error": error,
        })

        self._workflows[workflow_id].state_updates += 1
        self._workflows[workflow_id].edge_transitions += 1

    def record_workflow_end(
        self,
        workflow_id: str,
        status: str = "completed",
        error_message: str | None = None,
    ) -> None:
        """记录工作流结束"""
        if workflow_id not in self._workflows:
            logger.warning(f"[Metrics] Unknown workflow: {workflow_id}")
            return

        wf = self._workflows[workflow_id]
        wf.ended_at = datetime.utcnow().isoformat()

        start_dt = datetime.fromisoformat(wf.started_at)
        end_dt = datetime.fromisoformat(wf.ended_at)
        wf.duration_ms = int((end_dt - start_dt).total_seconds() * 1000)

        wf.status = status
        wf.error_message = error_message

        # 持久化
        self._persist_record(wf)
        logger.info(
            f"[Metrics] Workflow ended: {wf_id}, status={status}, "
            f"duration={wf.duration_ms}ms, revisions={wf.revision_count}"
        )

    def record_revision(self, workflow_id: str) -> None:
        """记录重规划"""
        if workflow_id in self._workflows:
            self._workflows[workflow_id].revision_count += 1

    def record_fan_out(self, workflow_id: str, parallel_count: int) -> None:
        """记录并行扇出"""
        if workflow_id in self._workflows:
            self._workflows[workflow_id].fan_outs += 1

    def record_conditional_branch(self, workflow_id: str) -> None:
        """记录条件分支评估"""
        if workflow_id in self._workflows:
            self._workflows[workflow_id].conditional_branches += 1

    def record_checkpoint(self, workflow_id: str) -> None:
        """记录检查点保存"""
        if workflow_id in self._workflows:
            self._workflows[workflow_id].checkpoint_count += 1

    def get_metrics(self) -> dict[str, Any]:
        """获取聚合指标"""
        if not self._workflows:
            return {}

        completed = [w for w in self._workflows.values() if w.status in ("completed", "failed")]
        if not completed:
            return {"workflows": {}, "summary": {}}

        durations = [w.duration_ms for w in completed if w.duration_ms]
        revision_counts = [w.revision_count for w in completed]
        state_updates = [w.state_updates for w in completed]
        fan_outs = [w.fan_outs for w in completed]

        # 节点聚合
        node_stats: dict[str, dict] = {}
        for wf in completed:
            for node_name, node_data in wf.node_executions.items():
                if node_name not in node_stats:
                    node_stats[node_name] = {
                        "count": 0,
                        "errors": 0,
                        "total_duration_ms": 0,
                    }
                node_stats[node_name]["count"] += 1
                if node_data.get("status") == "error":
                    node_stats[node_name]["errors"] += 1
                node_stats[node_name]["total_duration_ms"] += node_data.get("duration_ms", 0)

        for node_name in node_stats:
            count = node_stats[node_name]["count"]
            if count > 0:
                node_stats[node_name]["avg_duration_ms"] = (
                    node_stats[node_name]["total_duration_ms"] / count
                )
                node_stats[node_name]["error_rate"] = (
                    node_stats[node_name]["errors"] / count
                )

        return {
            "workflows": {
                wf_id: asdict(wf) for wf_id, wf in self._workflows.items()
            },
            "summary": {
                "total_workflows": len(self._workflows),
                "completed_workflows": len([w for w in completed if w.status == "completed"]),
                "failed_workflows": len([w for w in completed if w.status == "failed"]),
                "success_rate": (
                    len([w for w in completed if w.status == "completed"]) / len(completed)
                    if completed else 0
                ),
                "avg_duration_ms": sum(durations) / len(durations) if durations else 0,
                "p95_duration_ms": sorted(durations)[int(len(durations) * 0.95)] if durations else 0,
                "p99_duration_ms": sorted(durations)[int(len(durations) * 0.99)] if durations else 0,
                "avg_revision_count": sum(revision_counts) / len(revision_counts) if revision_counts else 0,
                "avg_state_updates": sum(state_updates) / len(state_updates) if state_updates else 0,
                "avg_fan_outs": sum(fan_outs) / len(fan_outs) if fan_outs else 0,
                "node_stats": node_stats,
            },
        }

    def export_json(self, filepath: str | Path) -> None:
        """导出指标到 JSONL 文件"""
        metrics = self.get_metrics()
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(metrics, ensure_ascii=False) + "\n")
        logger.info(f"[Metrics] Exported to {filepath}")

    def _persist_record(self, record: WorkflowRecord) -> None:
        """持久化单条记录"""
        filepath = self.output_dir / f"{record.workflow_id}.jsonl"
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
