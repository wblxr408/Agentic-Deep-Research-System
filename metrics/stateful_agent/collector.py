"""
主题 4: Long-running Stateful Agent Metrics Collector.

采集长生命周期有状态智能体的持久化和恢复能力指标。
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
class CheckpointRecord:
    """检查点记录"""
    checkpoint_id: str
    session_id: str
    created_at: str
    size_bytes: int = 0
    duration_ms: int | None = None
    status: str = "success"
    error: str | None = None


@dataclass
class SessionRecord:
    """会话记录"""
    session_id: str
    user_query: str
    created_at: str
    ended_at: str | None = None
    status: str = "active"
    checkpoint_count: int = 0
    revival_count: int = 0
    error_count: int = 0
    data_loss: bool = False


@dataclass
class FailureRecoveryRecord:
    """故障恢复记录"""
    failure_id: str
    session_id: str
    failure_type: str  # crash, timeout, network, manual
    detected_at: str
    recovered_at: str | None = None
    recovered: bool = False
    data_loss: bool = False
    recovery_duration_ms: int | None = None


class StatefulAgentMetricsCollector:
    """
    主题 4: 长生命周期有状态智能体指标采集器。

    采集：
    - 检查点保存/恢复次数、时长、错误率
    - 会话活跃数、时长、隔离率
    - 故障恢复率、数据丢失率
    - 资源使用（内存、Redis）
    """

    def __init__(self, output_dir: str | Path = "metrics/stateful_agent/data"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._checkpoints: dict[str, CheckpointRecord] = {}
        self._sessions: dict[str, SessionRecord] = {}
        self._failures: list[FailureRecoveryRecord] = []

    def record_checkpoint_save(
        self,
        session_id: str,
        checkpoint_id: str | None = None,
        size_bytes: int = 0,
        duration_ms: int | None = None,
        status: str = "success",
        error: str | None = None,
    ) -> str:
        """记录检查点保存"""
        checkpoint_id = checkpoint_id or f"ckpt-{uuid.uuid4().hex[:8]}"
        record = CheckpointRecord(
            checkpoint_id=checkpoint_id,
            session_id=session_id,
            created_at=datetime.utcnow().isoformat(),
            size_bytes=size_bytes,
            duration_ms=duration_ms,
            status=status,
            error=error,
        )
        self._checkpoints[checkpoint_id] = record

        # 更新会话检查点计数
        if session_id in self._sessions:
            self._sessions[session_id].checkpoint_count += 1

        logger.info(
            f"[Metrics] Checkpoint saved: {checkpoint_id}, "
            f"session={session_id}, size={size_bytes}B, duration={duration_ms}ms"
        )
        return checkpoint_id

    def record_checkpoint_restore(
        self,
        checkpoint_id: str,
        session_id: str,
        recovered: bool = True,
        error: str | None = None,
    ) -> None:
        """记录检查点恢复"""
        record = CheckpointRecord(
            checkpoint_id=checkpoint_id,
            session_id=session_id,
            created_at=datetime.utcnow().isoformat(),
            status="restored" if recovered else "failed",
            error=error,
        )
        self._checkpoints[checkpoint_id] = record
        logger.info(f"[Metrics] Checkpoint restore: {checkpoint_id}, recovered={recovered}")

    def record_session_start(
        self,
        session_id: str,
        user_query: str,
    ) -> None:
        """记录会话开始"""
        record = SessionRecord(
            session_id=session_id,
            user_query=user_query,
            created_at=datetime.utcnow().isoformat(),
            status="active",
        )
        self._sessions[session_id] = record
        logger.info(f"[Metrics] Session started: {session_id}")

    def record_session_end(
        self,
        session_id: str,
        status: str = "completed",
    ) -> None:
        """记录会话结束"""
        if session_id not in self._sessions:
            logger.warning(f"[Metrics] Unknown session: {session_id}")
            return

        session = self._sessions[session_id]
        session.ended_at = datetime.utcnow().isoformat()
        session.status = status
        self._persist_session(session)

        logger.info(
            f"[Metrics] Session ended: {session_id}, status={status}, "
            f"checkpoints={session.checkpoint_count}, revivals={session.revival_count}"
        )

    def record_failure_recovery(
        self,
        session_id: str,
        failure_type: str,
        recovered: bool = True,
        recovery_duration_ms: int | None = None,
        data_loss: bool = False,
    ) -> str:
        """记录故障恢复"""
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        record = FailureRecoveryRecord(
            failure_id=failure_id,
            session_id=session_id,
            failure_type=failure_type,
            detected_at=datetime.utcnow().isoformat(),
            recovered_at=datetime.utcnow().isoformat() if recovered else None,
            recovered=recovered,
            data_loss=data_loss,
            recovery_duration_ms=recovery_duration_ms,
        )
        self._failures.append(record)

        # 更新会话
        if session_id in self._sessions:
            self._sessions[session_id].revival_count += 1
            if data_loss:
                self._sessions[session_id].data_loss = True
            if not recovered:
                self._sessions[session_id].error_count += 1

        logger.info(
            f"[Metrics] Failure recovery: {failure_id}, "
            f"session={session_id}, type={failure_type}, recovered={recovered}"
        )
        return failure_id

    def record_data_loss(self, session_id: str) -> None:
        """记录数据丢失"""
        if session_id in self._sessions:
            self._sessions[session_id].data_loss = True
        logger.warning(f"[Metrics] Data loss detected: {session_id}")

    def get_metrics(self) -> dict[str, Any]:
        """获取聚合指标"""
        # 检查点指标
        total_checkpoints = len(self._checkpoints)
        checkpoint_saves = [
            c for c in self._checkpoints.values()
            if c.status in ("success", "failed")
        ]
        checkpoint_durations = [
            c.duration_ms for c in self._checkpoints.values()
            if c.duration_ms is not None
        ]
        checkpoint_sizes = [
            c.size_bytes for c in self._checkpoints.values()
            if c.size_bytes > 0
        ]
        checkpoint_errors = sum(
            1 for c in self._checkpoints.values()
            if c.status in ("failed", "error")
        )

        # 会话指标
        active_sessions = [
            s for s in self._sessions.values()
            if s.status == "active"
        ]
        completed_sessions = [
            s for s in self._sessions.values()
            if s.status in ("completed", "failed")
        ]

        session_durations = []
        for s in completed_sessions:
            if s.ended_at:
                start = datetime.fromisoformat(s.created_at)
                end = datetime.fromisoformat(s.ended_at)
                session_durations.append(int((end - start).total_seconds()))

        sessions_with_data_loss = sum(1 for s in self._sessions.values() if s.data_loss)

        # 故障恢复指标
        total_failures = len(self._failures)
        recovered_failures = sum(1 for f in self._failures if f.recovered)
        failures_with_data_loss = sum(1 for f in self._failures if f.data_loss)
        recovery_durations = [
            f.recovery_duration_ms for f in self._failures
            if f.recovery_duration_ms is not None
        ]

        return {
            "checkpoints": {k: asdict(v) for k, v in self._checkpoints.items()},
            "sessions": {k: asdict(v) for k, v in self._sessions.items()},
            "failures": [asdict(f) for f in self._failures],
            "summary": {
                # 检查点指标
                "total_checkpoints": total_checkpoints,
                "checkpoint_save_count": len(checkpoint_saves),
                "checkpoint_save_error_rate": (
                    checkpoint_errors / total_checkpoints
                    if total_checkpoints > 0 else 0
                ),
                "avg_checkpoint_duration_ms": (
                    sum(checkpoint_durations) / len(checkpoint_durations)
                    if checkpoint_durations else 0
                ),
                "avg_checkpoint_size_bytes": (
                    sum(checkpoint_sizes) / len(checkpoint_sizes)
                    if checkpoint_sizes else 0
                ),
                # 会话指标
                "active_sessions": len(active_sessions),
                "total_sessions": len(self._sessions),
                "avg_session_duration_s": (
                    sum(session_durations) / len(session_durations)
                    if session_durations else 0
                ),
                "max_session_duration_s": max(session_durations) if session_durations else 0,
                "session_isolation_rate": (
                    (len(self._sessions) - sessions_with_data_loss) / len(self._sessions)
                    if self._sessions else 1.0
                ),
                # 故障恢复指标
                "total_failures": total_failures,
                "failure_recovery_rate": (
                    recovered_failures / total_failures
                    if total_failures > 0 else 0
                ),
                "data_loss_rate": (
                    failures_with_data_loss / total_failures
                    if total_failures > 0 else 0
                ),
                "avg_recovery_duration_ms": (
                    sum(recovery_durations) / len(recovery_durations)
                    if recovery_durations else 0
                ),
            },
        }

    def export_json(self, filepath: str | Path) -> None:
        """导出指标到 JSONL 文件"""
        metrics = self.get_metrics()
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(metrics, ensure_ascii=False) + "\n")
        logger.info(f"[Metrics] Exported to {filepath}")

    def _persist_session(self, session: SessionRecord) -> None:
        """持久化会话记录"""
        filepath = self.output_dir / f"session_{session.session_id}.jsonl"
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(session), ensure_ascii=False) + "\n")
