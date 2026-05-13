"""
主题 2: Research DAG Generation Metrics Collector.

采集研究 DAG 生成的质量和执行效率指标。
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
class DAGRecord:
    """单个 DAG 生成记录"""
    dag_id: str
    dag_name: str
    generated_at: str
    node_count: int = 0
    edge_count: int = 0
    depth: int = 0
    node_types: dict[str, int] = field(default_factory=dict)
    execution_order: list[list[str]] = field(default_factory=list)
    parallel_batches: int = 0
    status: str = "generated"  # generated, executing, completed, failed
    execution_records: list[dict] = field(default_factory=list)
    plan_coverage_score: float = 0.0


@dataclass
class NodeExecutionRecord:
    """DAG 中单个节点执行记录"""
    node_id: str
    node_type: str
    started_at: str
    ended_at: str | None = None
    duration_ms: int | None = None
    status: str = "pending"
    confidence: float = 0.0
    error: str | None = None


class DAGMetricsCollector:
    """
    主题 2: 研究 DAG 生成指标采集器。

    采集：
    - DAG 生成成功率、节点数、深度
    - 并行度因子、批次执行次数
    - 各类型节点执行成功率
    - 计划覆盖度评分
    """

    def __init__(self, output_dir: str | Path = "metrics/research_dag/data"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._dags: dict[str, DAGRecord] = {}

    def record_dag_generated(
        self,
        dag_id: str | None = None,
        dag_name: str = "",
        nodes: list[dict] | None = None,
        edges: list[dict] | None = None,
        execution_order: list[list[str]] | None = None,
    ) -> str:
        """记录 DAG 生成"""
        dag_id = dag_id or f"dag-{uuid.uuid4().hex[:8]}"
        nodes = nodes or []
        edges = edges or []

        # 计算深度
        depth = self._calculate_depth(nodes, edges)

        # 统计节点类型
        node_types: dict[str, int] = {}
        for node in nodes:
            node_type = node.get("node_type", "unknown")
            node_types[node_type] = node_types.get(node_type, 0) + 1

        record = DAGRecord(
            dag_id=dag_id,
            dag_name=dag_name,
            generated_at=datetime.utcnow().isoformat(),
            node_count=len(nodes),
            edge_count=len(edges),
            depth=depth,
            node_types=node_types,
            execution_order=execution_order or [],
            parallel_batches=len(execution_order) if execution_order else 0,
        )

        self._dags[dag_id] = record
        logger.info(f"[Metrics] DAG generated: {dag_id}, nodes={len(nodes)}, depth={depth}")
        return dag_id

    def record_node_execution(
        self,
        dag_id: str,
        node_id: str,
        node_type: str,
        status: str = "success",
        duration_ms: int | None = None,
        confidence: float = 0.0,
        error: str | None = None,
    ) -> None:
        """记录 DAG 节点执行"""
        if dag_id not in self._dags:
            logger.warning(f"[Metrics] Unknown DAG: {dag_id}")
            return

        ended_at = datetime.utcnow().isoformat()
        record = NodeExecutionRecord(
            node_id=node_id,
            node_type=node_type,
            started_at=ended_at,  # simplified
            ended_at=ended_at,
            duration_ms=duration_ms,
            status=status,
            confidence=confidence,
            error=error,
        )
        self._dags[dag_id].execution_records.append(asdict(record))

    def record_dag_completed(
        self,
        dag_id: str,
        status: str = "completed",
        plan_coverage_score: float = 0.0,
    ) -> None:
        """记录 DAG 完成"""
        if dag_id not in self._dags:
            return

        self._dags[dag_id].status = status
        self._dags[dag_id].plan_coverage_score = plan_coverage_score
        self._persist_record(self._dags[dag_id])

        logger.info(
            f"[Metrics] DAG completed: {dag_id}, status={status}, "
            f"coverage={plan_coverage_score:.2%}"
        )

    def _calculate_depth(self, nodes: list[dict], edges: list[dict]) -> int:
        """计算 DAG 深度（拓扑排序）"""
        if not nodes:
            return 0

        # 构建邻接表
        adj: dict[str, list[str]] = {n.get("node_id", f"n{i}"): [] for i, n in enumerate(nodes)}
        in_degree: dict[str, int] = {n.get("node_id", f"n{i}"): 0 for i, n in enumerate(nodes)}

        for edge in edges:
            from_node = edge.get("from_node", "")
            to_node = edge.get("to_node", "")
            if from_node in adj and to_node in adj:
                adj[from_node].append(to_node)
                in_degree[to_node] += 1

        # BFS 计算深度
        max_depth = 0
        queue = [(nid, 1) for nid, deg in in_degree.items() if deg == 0]
        visited = set()

        while queue:
            node_id, depth = queue.pop(0)
            if node_id in visited:
                continue
            visited.add(node_id)
            max_depth = max(max_depth, depth)

            for neighbor in adj[node_id]:
                if neighbor not in visited:
                    queue.append((neighbor, depth + 1))

        return max_depth

    def get_metrics(self) -> dict[str, Any]:
        """获取聚合指标"""
        if not self._dags:
            return {}

        completed = [d for d in self._dags.values() if d.status in ("completed", "failed")]

        if not completed:
            # 仍在生成中
            return {
                "dags": {k: asdict(v) for k, v in self._dags.items()},
                "summary": {},
            }

        # 节点数统计
        node_counts = [d.node_count for d in completed]
        edge_counts = [d.edge_count for d in completed]
        depths = [d.depth for d in completed]
        batch_counts = [d.parallel_batches for d in completed]

        # 节点类型分布
        all_node_types: dict[str, int] = {}
        for d in completed:
            for nt, count in d.node_types.items():
                all_node_types[nt] = all_node_types.get(nt, 0) + count

        # 各类型节点成功率
        node_success_by_type: dict[str, dict] = {}
        for d in completed:
            for record in d.execution_records:
                node_type = record.get("node_type", "unknown")
                if node_type not in node_success_by_type:
                    node_success_by_type[node_type] = {"total": 0, "success": 0}
                node_success_by_type[node_type]["total"] += 1
                if record.get("status") == "success":
                    node_success_by_type[node_type]["success"] += 1

        for node_type in node_success_by_type:
            total = node_success_by_type[node_type]["total"]
            success = node_success_by_type[node_type]["success"]
            node_success_by_type[node_type]["success_rate"] = (
                success / total if total > 0 else 0
            )

        # 并行度因子
        total_nodes = sum(node_counts)
        total_batches = sum(batch_counts)
        parallelism_factor = total_nodes / total_batches if total_batches > 0 else 1.0

        # 覆盖度
        coverage_scores = [d.plan_coverage_score for d in completed if d.plan_coverage_score > 0]

        return {
            "dags": {k: asdict(v) for k, v in self._dags.items()},
            "summary": {
                "total_dags": len(self._dags),
                "completed_dags": len(completed),
                "avg_node_count": sum(node_counts) / len(node_counts) if node_counts else 0,
                "avg_edge_count": sum(edge_counts) / len(edge_counts) if edge_counts else 0,
                "avg_depth": sum(depths) / len(depths) if depths else 0,
                "avg_parallel_batches": sum(batch_counts) / len(batch_counts) if batch_counts else 0,
                "parallelism_factor": parallelism_factor,
                "node_type_distribution": all_node_types,
                "node_success_by_type": node_success_by_type,
                "avg_plan_coverage": (
                    sum(coverage_scores) / len(coverage_scores) if coverage_scores else 0
                ),
            },
        }

    def export_json(self, filepath: str | Path) -> None:
        """导出指标到 JSONL 文件"""
        metrics = self.get_metrics()
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(metrics, ensure_ascii=False) + "\n")
        logger.info(f"[Metrics] Exported to {filepath}")

    def _persist_record(self, record: DAGRecord) -> None:
        """持久化单条记录"""
        filepath = self.output_dir / f"{record.dag_id}.jsonl"
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
