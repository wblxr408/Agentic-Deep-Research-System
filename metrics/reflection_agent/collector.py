"""
主题 5: Self-Reflection & Verification Metrics Collector.

采集自校验与验证的质量和效率指标。
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ReflectionMetrics:
    """单次反思操作指标"""
    session_id: str
    total_claims: int
    verified_claims: int
    hallucinated_claims: int
    conflicts: int
    factuality_score: float = 0.0
    consistency_score: float = 0.0
    completeness_score: float = 0.0
    citation_coverage: float = 0.0
    overall_confidence: float = 0.0
    needs_revision: bool = False
    revision_count: int = 0
    evaluated_at: str | None = None


@dataclass
class HallucinationDetail:
    """幻觉声明详情"""
    session_id: str
    claim: str
    severity: str = "medium"
    reason: str = ""
    suggested_action: str = ""
    evaluated_at: str | None = None


@dataclass
class RevisionRecord:
    """重规划记录"""
    session_id: str
    revision_number: int
    triggered_by: str  # "hallucination", "inconsistency", "incompleteness"
    success: bool = False
    new_confidence: float = 0.0
    attempts: int = 1


class ReflectionMetricsCollector:
    """
    主题 5: 自校验与验证指标采集器。

    采集：
    - 幻觉率、置信度准确性、误报率、漏报率
    - 各校验维度评分（事实性、一致性、完整性、引用覆盖率）
    - 重规划次数、收敛率、通过率
    - 声明级指标（总声明、已验证、幻觉、冲突）
    """

    def __init__(self, storage_path: str = "metrics/reflection_agent/data"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._reflections: list[ReflectionMetrics] = []
        self._hallucinations: list[HallucinationDetail] = []
        self._revisions: list[RevisionRecord] = []

    def record_reflection(
        self,
        session_id: str,
        total_claims: int,
        verified_claims: int,
        hallucinated_claims: int,
        conflicts: int,
        factuality_score: float = 0.0,
        consistency_score: float = 0.0,
        completeness_score: float = 0.0,
        citation_coverage: float = 0.0,
        overall_confidence: float = 0.0,
        needs_revision: bool = False,
        revision_count: int = 0,
        hallucination_details: list[dict] | None = None,
    ) -> None:
        """记录反思操作"""
        metrics = ReflectionMetrics(
            session_id=session_id,
            total_claims=total_claims,
            verified_claims=verified_claims,
            hallucinated_claims=hallucinated_claims,
            conflicts=conflicts,
            factuality_score=factuality_score,
            consistency_score=consistency_score,
            completeness_score=completeness_score,
            citation_coverage=citation_coverage,
            overall_confidence=overall_confidence,
            needs_revision=needs_revision,
            revision_count=revision_count,
            evaluated_at=datetime.utcnow().isoformat(),
        )
        self._reflections.append(metrics)
        self._persist_reflection(metrics)

        if hallucination_details:
            for h in hallucination_details:
                self._hallucinations.append(HallucinationDetail(
                    session_id=session_id,
                    claim=h.get("claim", ""),
                    severity=h.get("severity", "medium"),
                    reason=h.get("reason", ""),
                    suggested_action=h.get("suggested_action", ""),
                    evaluated_at=datetime.utcnow().isoformat(),
                ))

        logger.info(
            f"[Metrics] Reflection recorded: {total_claims} claims, "
            f"{hallucinated_claims} hallucinated, confidence={overall_confidence:.2f}"
        )

    def record_revision(
        self,
        session_id: str,
        revision_number: int,
        triggered_by: str,
        success: bool = False,
        new_confidence: float = 0.0,
    ) -> None:
        """记录重规划"""
        record = RevisionRecord(
            session_id=session_id,
            revision_number=revision_number,
            triggered_by=triggered_by,
            success=success,
            new_confidence=new_confidence,
        )
        self._revisions.append(record)
        logger.info(
            f"[Metrics] Revision recorded: session={session_id}, "
            f"rev={revision_number}, success={success}"
        )

    def _persist_reflection(self, metrics: ReflectionMetrics) -> None:
        """持久化反思指标"""
        date = datetime.utcnow().strftime("%Y-%m-%d")
        filepath = self.storage_path / f"reflections_{date}.jsonl"
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(metrics), ensure_ascii=False) + "\n")

    def get_metrics(self) -> dict[str, Any]:
        """获取聚合指标"""
        if not self._reflections:
            return {"summary": {}}

        total = len(self._reflections)
        total_claims = sum(r.total_claims for r in self._reflections)
        total_hallucinated = sum(r.hallucinated_claims for r in self._reflections)
        total_verified = sum(r.verified_claims for r in self._reflections)
        total_conflicts = sum(r.conflicts for r in self._reflections)
        revision_triggers = sum(1 for r in self._reflections if r.needs_revision)

        all_confidences = [r.overall_confidence for r in self._reflections]
        all_citation_coverages = [r.citation_coverage for r in self._reflections]
        all_factuality = [r.factuality_score for r in self._reflections if r.factuality_score > 0]
        all_consistency = [r.consistency_score for r in self._reflections if r.consistency_score > 0]
        all_completeness = [r.completeness_score for r in self._reflections if r.completeness_score > 0]
        all_revisions = [r.revision_count for r in self._reflections]

        # 重规划统计
        total_revisions = len(self._revisions)
        successful_revisions = sum(1 for r in self._revisions if r.success)

        # 幻觉按严重程度分类
        severity_counts = {"high": 0, "medium": 0, "low": 0}
        for h in self._hallucinations:
            if h.severity in severity_counts:
                severity_counts[h.severity] += 1

        return {
            "reflections": [asdict(r) for r in self._reflections[-100:]],
            "revisions": [asdict(r) for r in self._revisions[-100:]],
            "summary": {
                "total_reflections": total,
                "total_claims_analyzed": total_claims,
                "verified_claims": total_verified,
                "hallucinated_claims": total_hallucinated,
                "hallucination_rate": total_hallucinated / total_claims if total_claims > 0 else 0,
                "conflicts_detected": total_conflicts,
                "revision_trigger_rate": revision_triggers / total if total > 0 else 0,
                "avg_revisions_per_workflow": (
                    sum(all_revisions) / len(all_revisions) if all_revisions else 0
                ),
                # 校验维度评分
                "factuality_score_avg": sum(all_factuality) / len(all_factuality) if all_factuality else 0,
                "consistency_score_avg": sum(all_consistency) / len(all_consistency) if all_consistency else 0,
                "completeness_score_avg": (
                    sum(all_completeness) / len(all_completeness) if all_completeness else 0
                ),
                "citation_coverage_avg": (
                    sum(all_citation_coverages) / len(all_citation_coverages)
                    if all_citation_coverages else 0
                ),
                "overall_confidence_avg": (
                    sum(all_confidences) / len(all_confidences) if all_confidences else 0
                ),
                "confidence_p95": (
                    sorted(all_confidences)[int(len(all_confidences) * 0.95)]
                    if all_confidences else 0
                ),
                # 重规划指标
                "total_revisions": total_revisions,
                "successful_revisions": successful_revisions,
                "revision_success_rate": (
                    successful_revisions / total_revisions if total_revisions > 0 else 0
                ),
            },
            "hallucination_by_severity": severity_counts,
            "hallucination_details": [asdict(h) for h in self._hallucinations[-100:]],
        }

    def export_json(self, filepath: str | Path) -> None:
        """导出指标到 JSONL 文件"""
        metrics = self.get_metrics()
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(metrics, ensure_ascii=False) + "\n")
        logger.info(f"[Metrics] Exported to {filepath}")
