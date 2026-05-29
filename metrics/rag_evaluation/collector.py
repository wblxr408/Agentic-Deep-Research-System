"""
Offline RAG evaluation metrics collector.

Separates retrieval-layer evaluation from generation-layer evaluation:
- Retrieval: Hit@K / MRR
- Generation: faithfulness / answer relevancy / context recall / context precision
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class RetrievalEvalRecord:
    """Single retrieval-layer evaluation record."""

    question_id: str
    query: str
    top_k: int
    expected_chunk_ids: list[str]
    retrieved_chunk_ids: list[str]
    hit: float
    recall_at_k: float
    reciprocal_rank: float
    first_relevant_rank: int | None
    recorded_at: str
    query_type: str = "unlabeled"


@dataclass
class GenerationEvalRecord:
    """Single generation-layer evaluation record."""

    question_id: str
    query: str
    answer: str
    faithfulness: float
    answer_relevancy: float
    ground_truth_answer: str | None = None
    context_recall: float | None = None
    context_precision: float | None = None
    judge_model: str | None = None
    recorded_at: str | None = None


class RAGEvaluationCollector:
    """Collector for layered offline RAG evaluation metrics."""

    def __init__(self, storage_path: str = "metrics/rag_evaluation/data"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._retrieval_records: list[RetrievalEvalRecord] = []
        self._generation_records: list[GenerationEvalRecord] = []

    def record_retrieval_eval(
        self,
        *,
        question_id: str,
        query: str,
        expected_chunk_ids: list[str],
        retrieved_chunk_ids: list[str],
        top_k: int = 5,
        query_type: str = "unlabeled",
    ) -> None:
        """Record one retrieval evaluation example."""
        expected_set = set(expected_chunk_ids)
        ranked = retrieved_chunk_ids[:top_k]

        first_rank: int | None = None
        for idx, chunk_id in enumerate(ranked, start=1):
            if chunk_id in expected_set:
                first_rank = idx
                break

        # Hit@K answers "did the gold doc appear at all"; recall@K answers
        # "what fraction of the gold docs were retrieved" (matters for multi-answer queries).
        recall_hits = sum(1 for chunk_id in ranked if chunk_id in expected_set)
        recall_at_k = (recall_hits / len(expected_set)) if expected_set else 0.0

        record = RetrievalEvalRecord(
            question_id=question_id,
            query=query,
            top_k=top_k,
            expected_chunk_ids=expected_chunk_ids,
            retrieved_chunk_ids=retrieved_chunk_ids,
            hit=1.0 if first_rank is not None else 0.0,
            recall_at_k=recall_at_k,
            reciprocal_rank=(1.0 / first_rank) if first_rank is not None else 0.0,
            first_relevant_rank=first_rank,
            recorded_at=datetime.utcnow().isoformat(),
            query_type=query_type,
        )
        self._retrieval_records.append(record)
        self._persist_record("retrieval", asdict(record))

    def record_generation_eval(
        self,
        *,
        question_id: str,
        query: str,
        answer: str,
        ground_truth_answer: str | None = None,
        faithfulness: float,
        answer_relevancy: float,
        context_recall: float | None = None,
        context_precision: float | None = None,
        judge_model: str | None = None,
    ) -> None:
        """Record one generation evaluation example."""
        record = GenerationEvalRecord(
            question_id=question_id,
            query=query,
            answer=answer,
            ground_truth_answer=ground_truth_answer,
            faithfulness=faithfulness,
            answer_relevancy=answer_relevancy,
            context_recall=context_recall,
            context_precision=context_precision,
            judge_model=judge_model,
            recorded_at=datetime.utcnow().isoformat(),
        )
        self._generation_records.append(record)
        self._persist_record("generation", asdict(record))

    def get_metrics(self) -> dict[str, Any]:
        """Return combined layered evaluation metrics."""
        return {
            "retrieval": self._build_retrieval_summary(),
            "generation": self._build_generation_summary(),
        }

    def _build_retrieval_summary(self) -> dict[str, Any]:
        if not self._retrieval_records:
            return {"records": [], "summary": {}, "by_query_type": {}, "failures": []}

        records = self._retrieval_records
        return {
            "records": [asdict(r) for r in records[-100:]],
            "summary": self._aggregate_retrieval(records),
            "by_query_type": self._retrieval_by_query_type(records),
            "failures": self._failure_trace(records),
        }

    @staticmethod
    def _aggregate_retrieval(records: list[RetrievalEvalRecord]) -> dict[str, Any]:
        """Aggregate Hit@K / Recall@K / MRR over a set of retrieval records."""
        total = len(records)
        if total == 0:
            return {}
        hits = sum(r.hit for r in records)
        recalls = [r.recall_at_k for r in records]
        reciprocal_ranks = [r.reciprocal_rank for r in records]
        first_ranks = [r.first_relevant_rank for r in records if r.first_relevant_rank is not None]

        return {
            "total_queries": total,
            "hit_rate": hits / total,
            "recall_at_k": sum(recalls) / total,
            "mrr": sum(reciprocal_ranks) / total,
            "avg_first_relevant_rank": (sum(first_ranks) / len(first_ranks)) if first_ranks else None,
        }

    def _retrieval_by_query_type(self, records: list[RetrievalEvalRecord]) -> dict[str, Any]:
        """Group retrieval records by query type so weak categories stand out.

        This is the article's core idea: an average score hides which kind of
        query is failing. Aggregating per type (同义 / 缩写 / 跨语言 / 数字代码 / 长query)
        turns one opaque number into an actionable diagnosis table.
        """
        buckets: dict[str, list[RetrievalEvalRecord]] = {}
        for record in records:
            buckets.setdefault(record.query_type, []).append(record)
        return {
            query_type: self._aggregate_retrieval(bucket)
            for query_type, bucket in sorted(buckets.items())
        }

    @staticmethod
    def _failure_trace(records: list[RetrievalEvalRecord]) -> list[dict[str, Any]]:
        """Surface the queries that missed entirely (hit == 0).

        A failure trace is more useful than the mean score for deciding what to
        fix: it shows exactly which queries (and types) the gold doc never made
        the Top-K for.
        """
        return [
            {
                "question_id": r.question_id,
                "query": r.query,
                "query_type": r.query_type,
                "top_k": r.top_k,
                "expected_chunk_ids": r.expected_chunk_ids,
                "retrieved_chunk_ids": r.retrieved_chunk_ids[: r.top_k],
            }
            for r in records
            if r.hit == 0.0
        ]

    def _build_generation_summary(self) -> dict[str, Any]:
        if not self._generation_records:
            return {"records": [], "summary": {}}

        total = len(self._generation_records)
        faithfulness_scores = [r.faithfulness for r in self._generation_records]
        answer_relevancy_scores = [r.answer_relevancy for r in self._generation_records]
        context_recalls = [r.context_recall for r in self._generation_records if r.context_recall is not None]
        context_precisions = [r.context_precision for r in self._generation_records if r.context_precision is not None]

        return {
            "records": [asdict(r) for r in self._generation_records[-100:]],
            "summary": {
                "total_answers": total,
                "faithfulness_avg": sum(faithfulness_scores) / total,
                "answer_relevancy_avg": sum(answer_relevancy_scores) / total,
                "context_recall_avg": (
                    sum(context_recalls) / len(context_recalls) if context_recalls else None
                ),
                "context_precision_avg": (
                    sum(context_precisions) / len(context_precisions) if context_precisions else None
                ),
            },
        }

    def _persist_record(self, record_type: str, payload: dict[str, Any]) -> None:
        filepath = self.storage_path / f"{record_type}_{datetime.utcnow().date().isoformat()}.jsonl"
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        logger.info("[Metrics] RAG %s evaluation recorded for question=%s", record_type, payload.get("question_id"))
