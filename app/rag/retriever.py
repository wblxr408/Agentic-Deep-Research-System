"""
Hybrid Retriever: combines vector search + BM25 + RRF fusion.

Implements the complete hybrid retrieval pipeline.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)


class HybridRetriever:
    """
    Hybrid retrieval combining pgvector ANN + PostgreSQL BM25 + RRF fusion.

    The RRF (Reciprocal Rank Fusion) formula:
        RRF(d) = Σ 1 / (k + rank(d))
    where k is a constant (default 60) and rank(d) is the rank of document d
    in each individual result list.
    """

    def __init__(self):
        settings = get_settings()
        self.rag_cfg = settings.rag

    @staticmethod
    def reciprocal_rank_fusion(
        result_lists: list[list[tuple[str, float]]],
        k: int = 60,
    ) -> list[tuple[str, float]]:
        """
        Fuse multiple ranked result lists using RRF.

        Args:
            result_lists: List of (doc_id, score) lists from different rankers
            k: RRF constant (higher = more weight to lower ranks)

        Returns:
            Fused list of (doc_id, rrf_score), sorted descending
        """
        scores: dict[str, float] = {}

        for result_list in result_lists:
            for rank, (doc_id, score) in enumerate(result_list, 1):
                if doc_id not in scores:
                    scores[doc_id] = 0.0
                scores[doc_id] += 1.0 / (k + rank)

        return sorted(scores.items(), key=lambda x: x[1], reverse=True)

    @staticmethod
    def normalize_scores(
        results: list[tuple[str, Any]],
        score_key: str = "score",
    ) -> list[tuple[str, float]]:
        """Normalize scores to [0, 1] range."""
        if not results:
            return []

        max_score = max(r[1].get(score_key, 0) if isinstance(r[1], dict) else getattr(r[1], score_key, 0) for r in results)
        min_score = min(r[1].get(score_key, 0) if isinstance(r[1], dict) else getattr(r[1], score_key, 0) for r in results)

        if max_score == min_score:
            return [(r[0], 1.0) for r in results]

        normalized = []
        for doc_id, result in results:
            score = result.get(score_key, 0) if isinstance(result, dict) else getattr(result, score_key, 0)
            normalized_score = (score - min_score) / (max_score - min_score)
            normalized.append((doc_id, normalized_score))

        return normalized
