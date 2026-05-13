"""
Browser Agent metrics collector.

Collects and aggregates metrics for web browsing and content extraction.
"""

from __future__ import annotations

import json
import time
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExtractionMetrics:
    """Metrics for a single page extraction."""
    session_id: str
    url: str
    page_type: str
    extraction_level: str  # snippet, skim, deep
    status: str  # success, failed, timeout
    started_at: str
    completed_at: str | None = None
    duration_ms: int | None = None

    # Content metrics
    original_tokens: int = 0
    extracted_tokens: int = 0
    compression_ratio: float = 0.0

    # Error details
    error_type: str | None = None
    error_message: str | None = None

    # HTTP details
    status_code: int | None = None

    # ===== Browser Use 5-Capability Metrics =====
    # Step 1: OPEN
    open_step_duration_ms: int | None = None
    open_retry_count: int = 0

    # Step 2: SEARCH / SCROLL
    scroll_count: int = 0
    scroll_reached_bottom: bool = False
    scroll_loaded_more: bool = False
    scroll_step_duration_ms: int | None = None

    # Step 3: EXTRACT
    extract_method: str = "skim"  # meta, paragraphs, full
    structured_data_count: int = 0  # tables, lists, json-ld items extracted

    # Step 4: ANALYZE
    analyze_step_duration_ms: int | None = None
    analyze_confidence: float = 0.0
    analyze_page_type_predicted: str | None = None

    # Step 5: NAVIGATE
    next_page_count: int = 0  # how many sub-links were followed


@dataclass
class BrowserUseStepMetrics:
    """Metrics for each step of the Browser Use pipeline."""
    session_id: str
    url: str
    step: str  # open, scroll, extract, analyze
    started_at: str
    duration_ms: int | None = None
    success: bool = True
    details: dict = field(default_factory=dict)


class BrowserAgentMetricsCollector:
    """
    Collects metrics for Browser Agent operations.

    Tracks the full Browser Use 5-capability pipeline:
    1. OPEN     - URL navigation with retry
    2. SCROLL   - Smart scrolling for dynamic content
    3. EXTRACT  - Structured data extraction
    4. ANALYZE - AI-powered page content analysis
    5. NAVIGATE - Multi-step page navigation

    Usage:
        collector = BrowserAgentMetricsCollector()

        # Record each step
        collector.record_open_start(session_id, url)
        collector.record_open_end(session_id, url, success=True, duration_ms=500, retries=0)

        collector.record_scroll_start(session_id, url)
        collector.record_scroll_end(session_id, url, scrolls=5, reached_bottom=True)

        collector.record_extraction_start(session_id, url)
        collector.record_extraction_end(session_id, url, status="success",
                                       extraction_level="deep", structured_data_count=3)

        collector.record_analysis_end(session_id, url, confidence=0.85, predicted_type="news")

        metrics = collector.get_metrics()
    """

    def __init__(self, storage_path: str = "metrics/browser_agent/data"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._extractions: dict[str, ExtractionMetrics] = {}
        self._pool_stats = {
            "total_launches": 0,
            "total_crashes": 0,
            "concurrent_current": 0,
            "concurrent_peak": 0,
        }
        # Per-step aggregations
        self._step_stats = {
            "open": {"attempts": 0, "success": 0, "total_duration_ms": 0},
            "scroll": {"attempts": 0, "success": 0, "total_scrolls": 0},
            "extract": {"attempts": 0, "success": 0, "total_duration_ms": 0},
            "analyze": {"attempts": 0, "success": 0, "total_confidence": 0.0},
        }

    # ==============================================================
    # Step 1: OPEN Metrics
    # ==============================================================

    def record_open_start(self, session_id: str, url: str) -> str:
        """Record the start of URL navigation (OPEN step)."""
        key = f"{session_id}:{url}"
        if key not in self._extractions:
            self._extractions[key] = ExtractionMetrics(
                session_id=session_id,
                url=url,
                page_type="unknown",
                extraction_level="skim",
                status="running",
                started_at=datetime.utcnow().isoformat(),
            )
        self._step_stats["open"]["attempts"] += 1
        self._pool_stats["concurrent_current"] += 1
        self._pool_stats["concurrent_peak"] = max(
            self._pool_stats["concurrent_peak"],
            self._pool_stats["concurrent_current"],
        )
        self._pool_stats["total_launches"] += 1
        return key

    def record_open_end(
        self,
        session_id: str,
        url: str,
        success: bool,
        duration_ms: int = 0,
        retries: int = 0,
        status_code: int | None = None,
    ) -> None:
        """Record the end of URL navigation (OPEN step)."""
        key = f"{session_id}:{url}"
        if key in self._extractions:
            self._extractions[key].open_step_duration_ms = duration_ms
            self._extractions[key].open_retry_count = retries
            if status_code:
                self._extractions[key].status_code = status_code
        self._step_stats["open"]["success"] += 1 if success else 0
        self._step_stats["open"]["total_duration_ms"] += duration_ms
        logger.debug(f"[BrowserMetrics] OPEN: {url}, success={success}, duration={duration_ms}ms")

    # ==============================================================
    # Step 2: SCROLL Metrics
    # ==============================================================

    def record_scroll_start(self, session_id: str, url: str) -> None:
        """Record the start of smart scrolling (SCROLL step)."""
        key = f"{session_id}:{url}"
        if key not in self._extractions:
            self._extractions[key] = ExtractionMetrics(
                session_id=session_id,
                url=url,
                page_type="unknown",
                extraction_level="skim",
                status="running",
                started_at=datetime.utcnow().isoformat(),
            )
        self._step_stats["scroll"]["attempts"] += 1

    def record_scroll_end(
        self,
        session_id: str,
        url: str,
        scrolls: int = 0,
        reached_bottom: bool = False,
        loaded_more: bool = False,
        duration_ms: int = 0,
    ) -> None:
        """Record the end of smart scrolling (SCROLL step)."""
        key = f"{session_id}:{url}"
        if key in self._extractions:
            self._extractions[key].scroll_count = scrolls
            self._extractions[key].scroll_reached_bottom = reached_bottom
            self._extractions[key].scroll_loaded_more = loaded_more
            self._extractions[key].scroll_step_duration_ms = duration_ms
        self._step_stats["scroll"]["success"] += 1
        self._step_stats["scroll"]["total_scrolls"] += scrolls
        logger.debug(f"[BrowserMetrics] SCROLL: {url}, scrolls={scrolls}, bottom={reached_bottom}")

    # ==============================================================
    # Step 3: EXTRACT Metrics
    # ==============================================================

    def record_extraction_start(
        self,
        session_id: str,
        url: str,
        page_type: str = "general",
    ) -> str:
        """Record the start of content extraction (EXTRACT step)."""
        extraction_id = f"{session_id}:{url}"
        if extraction_id not in self._extractions:
            self._extractions[extraction_id] = ExtractionMetrics(
                session_id=session_id,
                url=url,
                page_type=page_type,
                extraction_level="skim",
                status="running",
                started_at=datetime.utcnow().isoformat(),
            )
        self._step_stats["extract"]["attempts"] += 1
        return extraction_id

    def record_extraction_end(
        self,
        session_id: str,
        url: str,
        status: str,
        extraction_level: str = "skim",
        original_tokens: int = 0,
        extracted_tokens: int = 0,
        status_code: int | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        structured_data_count: int = 0,
    ) -> None:
        """Record the end of content extraction (EXTRACT step)."""
        extraction_id = f"{session_id}:{url}"
        if extraction_id not in self._extractions:
            logger.warning(f"[BrowserMetrics] Unknown extraction: {extraction_id}")
            return

        ext = self._extractions[extraction_id]
        ext.status = status
        ext.extraction_level = extraction_level
        ext.completed_at = datetime.utcnow().isoformat()
        ext.original_tokens = original_tokens
        ext.extracted_tokens = extracted_tokens
        ext.status_code = status_code
        ext.error_type = error_type
        ext.error_message = error_message
        ext.structured_data_count = structured_data_count

        if ext.started_at:
            start = datetime.fromisoformat(ext.started_at)
            end = datetime.fromisoformat(ext.completed_at)
            ext.duration_ms = int((end - start).total_seconds() * 1000)

        if extracted_tokens > 0 and original_tokens > 0:
            ext.compression_ratio = extracted_tokens / original_tokens

        self._pool_stats["concurrent_current"] = max(0, self._pool_stats["concurrent_current"] - 1)
        self._step_stats["extract"]["success"] += 1 if status == "success" else 0

        self._persist_extraction(ext)
        logger.info(
            f"[BrowserMetrics] EXTRACT: {url}, status={status}, "
            f"duration={ext.duration_ms}ms, compression={ext.compression_ratio:.2f}"
        )

    def record_analysis_end(
        self,
        session_id: str,
        url: str,
        confidence: float = 0.0,
        predicted_type: str | None = None,
        duration_ms: int = 0,
    ) -> None:
        """Record the end of AI page analysis (ANALYZE step)."""
        key = f"{session_id}:{url}"
        if key in self._extractions:
            self._extractions[key].analyze_confidence = confidence
            self._extractions[key].analyze_page_type_predicted = predicted_type
            self._extractions[key].analyze_step_duration_ms = duration_ms
        self._step_stats["analyze"]["attempts"] += 1
        self._step_stats["analyze"]["success"] += 1 if confidence > 0.5 else 0
        self._step_stats["analyze"]["total_confidence"] += confidence
        logger.debug(f"[BrowserMetrics] ANALYZE: {url}, confidence={confidence:.2f}")

    def record_browser_crash(self) -> None:
        """Record a browser crash."""
        self._pool_stats["total_crashes"] += 1
        logger.warning("[BrowserMetrics] Browser crash recorded")

    def _persist_extraction(self, ext: ExtractionMetrics) -> None:
        """Persist extraction metrics to storage."""
        date = datetime.utcnow().strftime("%Y-%m-%d")
        filepath = self.storage_path / f"{date}.jsonl"
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(ext), ensure_ascii=False) + "\n")

    def get_metrics(self) -> dict[str, Any]:
        """Get aggregated metrics including Browser Use 5-step breakdown."""
        if not self._extractions:
            return {
                "summary": {},
                "browser_use_steps": self._build_step_summary(),
                "by_page_type": {},
                "by_extraction_level": {},
                "pool_stats": self._pool_stats,
            }

        total = len(self._extractions)
        successful = sum(1 for e in self._extractions.values() if e.status == "success")
        failed = sum(1 for e in self._extractions.values() if e.status == "failed")

        durations = [e.duration_ms for e in self._extractions.values() if e.duration_ms]
        durations.sort()

        compression_ratios = [
            e.compression_ratio for e in self._extractions.values()
            if e.compression_ratio > 0
        ]

        # By page type
        by_page_type: dict[str, dict] = {}
        for ext in self._extractions.values():
            if ext.page_type not in by_page_type:
                by_page_type[ext.page_type] = {
                    "count": 0, "success": 0, "failed": 0,
                    "durations": [], "compression": [],
                }
            stats = by_page_type[ext.page_type]
            stats["count"] += 1
            if ext.status == "success":
                stats["success"] += 1
            else:
                stats["failed"] += 1
            if ext.duration_ms:
                stats["durations"].append(ext.duration_ms)
            if ext.compression_ratio > 0:
                stats["compression"].append(ext.compression_ratio)

        for pt_stats in by_page_type.values():
            if pt_stats["durations"]:
                pt_stats["avg_duration_ms"] = sum(pt_stats["durations"]) / len(pt_stats["durations"])
            if pt_stats["compression"]:
                pt_stats["avg_compression"] = sum(pt_stats["compression"]) / len(pt_stats["compression"])
            del pt_stats["durations"]
            del pt_stats["compression"]

        # By extraction level
        by_level: dict[str, dict] = {}
        for ext in self._extractions.values():
            if ext.extraction_level not in by_level:
                by_level[ext.extraction_level] = {"count": 0, "success": 0}
            by_level[ext.extraction_level]["count"] += 1
            if ext.status == "success":
                by_level[ext.extraction_level]["success"] += 1

        return {
            "summary": {
                "total_extractions": total,
                "successful": successful,
                "failed": failed,
                "success_rate": successful / total if total > 0 else 0,
                "avg_duration_ms": sum(durations) / len(durations) if durations else 0,
                "p95_duration_ms": (
                    durations[int(len(durations) * 0.95)] if durations and len(durations) > 1 else 0
                ),
                "avg_compression_ratio": (
                    sum(compression_ratios) / len(compression_ratios) if compression_ratios else 0
                ),
            },
            "browser_use_steps": self._build_step_summary(),
            "by_page_type": by_page_type,
            "by_extraction_level": by_level,
            "pool_stats": self._pool_stats,
        }

    def _build_step_summary(self) -> dict[str, Any]:
        """Build step-level summary for Browser Use 5-capability pipeline."""
        summary = {}
        for step, stats in self._step_stats.items():
            attempts = stats.get("attempts", 0)
            success = stats.get("success", 0)
            summary[step] = {
                "attempts": attempts,
                "success": success,
                "success_rate": success / attempts if attempts > 0 else 0,
            }
            if step in ("open", "extract") and "total_duration_ms" in stats:
                summary[step]["avg_duration_ms"] = (
                    stats["total_duration_ms"] / attempts if attempts > 0 else 0
                )
            if step == "scroll" and "total_scrolls" in stats:
                summary[step]["avg_scrolls"] = (
                    stats["total_scrolls"] / attempts if attempts > 0 else 0
                )
            if step == "analyze" and "total_confidence" in stats:
                summary[step]["avg_confidence"] = (
                    stats["total_confidence"] / attempts if attempts > 0 else 0
                )
        return summary

    def export_json(self, filepath: str) -> None:
        """Export metrics to JSON file."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.get_metrics(), f, ensure_ascii=False, indent=2)
