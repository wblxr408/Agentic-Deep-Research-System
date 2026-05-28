from __future__ import annotations

import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from metrics.browser_agent.collector import BrowserAgentMetricsCollector
from metrics.langgraph_workflow.collector import LangGraphMetricsCollector
from metrics.multi_agent.collector import MultiAgentMetricsCollector
from metrics.observability.collector import ObservabilityMetricsCollector
from metrics.reflection_agent.collector import ReflectionMetricsCollector
from metrics.research_dag.collector import DAGMetricsCollector
from metrics.research_quality.collector import ResearchQualityCollector
from metrics.stateful_agent.collector import StatefulAgentMetricsCollector


BASE_OUTPUT_ROOT = ROOT / "metrics" / "experiments"
OUTPUT_ROOT = BASE_OUTPUT_ROOT


def _ensure_clean_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _pause(seconds: float = 0.01) -> None:
    time.sleep(seconds)


def run_langgraph_workflow_experiment() -> dict:
    collector = LangGraphMetricsCollector(
        storage_path=_ensure_clean_dir(OUTPUT_ROOT / "langgraph_workflow" / "data")
    )

    wf1 = collector.record_workflow_start("wf-session-1", "Compare LLM browser agents")
    collector.record_node_start(wf1, "planner")
    _pause()
    collector.record_node_end(wf1, "planner", status="success")
    collector.record_fan_out(wf1, parallel_count=3)
    collector.record_node_start(wf1, "search")
    _pause()
    collector.record_node_end(wf1, "search", status="success")
    collector.record_node_start(wf1, "browser")
    _pause()
    collector.record_node_end(wf1, "browser", status="success")
    collector.record_node_start(wf1, "rag")
    _pause()
    collector.record_node_end(wf1, "rag", status="success")
    collector.record_conditional_branch(wf1)
    collector.record_checkpoint(wf1)
    collector.record_revision(wf1)
    collector.record_node_start(wf1, "analyst")
    _pause()
    collector.record_node_end(wf1, "analyst", status="success")
    _pause()
    collector.record_workflow_end(wf1, status="completed")

    wf2 = collector.record_workflow_start("wf-session-2", "Investigate MCP tool risks")
    collector.record_node_start(wf2, "planner")
    _pause()
    collector.record_node_end(wf2, "planner", status="success")
    collector.record_node_start(wf2, "search")
    _pause()
    collector.record_node_end(wf2, "search", status="error", error="upstream timeout")
    collector.record_conditional_branch(wf2)
    collector.record_checkpoint(wf2)
    _pause()
    collector.record_workflow_end(wf2, status="failed", error_message="search timeout")

    result = collector.get_metrics()
    collector.export_json(OUTPUT_ROOT / "langgraph_workflow" / "summary.jsonl")
    return result


def run_research_dag_experiment() -> dict:
    collector = DAGMetricsCollector(output_dir=_ensure_clean_dir(OUTPUT_ROOT / "research_dag" / "data"))

    nodes = [
        {"node_id": "n1", "node_type": "planner"},
        {"node_id": "n2", "node_type": "rag"},
        {"node_id": "n3", "node_type": "search"},
        {"node_id": "n4", "node_type": "browser"},
        {"node_id": "n5", "node_type": "analyst"},
    ]
    edges = [
        {"from_node": "n1", "to_node": "n2"},
        {"from_node": "n1", "to_node": "n3"},
        {"from_node": "n3", "to_node": "n4"},
        {"from_node": "n2", "to_node": "n5"},
        {"from_node": "n4", "to_node": "n5"},
    ]
    order = [["n1"], ["n2", "n3"], ["n4"], ["n5"]]

    dag1 = collector.record_dag_generated(
        dag_id="dag-exp-1",
        dag_name="research-comparison",
        nodes=nodes,
        edges=edges,
        execution_order=order,
    )
    collector.record_node_execution(dag1, "n1", "planner", status="success", duration_ms=120, confidence=0.9)
    collector.record_node_execution(dag1, "n2", "rag", status="success", duration_ms=80, confidence=0.85)
    collector.record_node_execution(dag1, "n3", "search", status="success", duration_ms=200, confidence=0.8)
    collector.record_node_execution(dag1, "n4", "browser", status="success", duration_ms=320, confidence=0.75)
    collector.record_node_execution(dag1, "n5", "analyst", status="success", duration_ms=140, confidence=0.88)
    collector.record_dag_completed(dag1, status="completed", plan_coverage_score=0.92)

    dag2 = collector.record_dag_generated(
        dag_id="dag-exp-2",
        dag_name="mcp-safety-check",
        nodes=nodes[:4],
        edges=edges[:3],
        execution_order=[["n1"], ["n2", "n3"], ["n4"]],
    )
    collector.record_node_execution(dag2, "n1", "planner", status="success", duration_ms=100, confidence=0.87)
    collector.record_node_execution(dag2, "n2", "rag", status="success", duration_ms=70, confidence=0.82)
    collector.record_node_execution(dag2, "n3", "search", status="success", duration_ms=180, confidence=0.79)
    collector.record_node_execution(dag2, "n4", "browser", status="error", duration_ms=350, confidence=0.4, error="navigation timeout")
    collector.record_dag_completed(dag2, status="failed", plan_coverage_score=0.61)

    result = collector.get_metrics()
    collector.export_json(OUTPUT_ROOT / "research_dag" / "summary.jsonl")
    return result


def run_multi_agent_experiment() -> dict:
    collector = MultiAgentMetricsCollector(output_dir=_ensure_clean_dir(OUTPUT_ROOT / "multi_agent" / "data"))

    c1 = collector.record_tool_call_start(call_id="call-1", agent_type="search", tool_name="duckduckgo_search")
    _pause()
    collector.record_tool_call_end(c1, status="success", result_summary="3 urls", cost_usd=0.001, tokens_used=120)
    c2 = collector.record_tool_call_start(call_id="call-2", agent_type="browser", tool_name="open_page")
    _pause()
    collector.record_tool_call_end(c2, status="timeout", error="navigation timeout", cost_usd=0.003, tokens_used=0)
    c3 = collector.record_tool_call_start(call_id="call-3", agent_type="rag", tool_name="retrieve_chunks")
    _pause()
    collector.record_tool_call_end(c3, status="success", result_summary="6 chunks", cost_usd=0.0005, tokens_used=80)
    c4 = collector.record_tool_call_start(call_id="call-4", agent_type="analyst", tool_name="synthesize")
    _pause()
    collector.record_tool_call_end(c4, status="error", error="schema mismatch", cost_usd=0.002, tokens_used=240)

    collector.record_agent_stats("session-1", "search", calls=1, successes=1, failures=0, total_duration_ms=110)
    collector.record_agent_stats("session-1", "browser", calls=1, successes=0, failures=1, total_duration_ms=400)
    collector.record_agent_stats("session-1", "rag", calls=1, successes=1, failures=0, total_duration_ms=70)
    collector.record_agent_stats("session-1", "analyst", calls=1, successes=0, failures=1, total_duration_ms=150)
    collector.record_collaboration("parallel", ["search", "rag"], duration_ms=210, success=True)
    collector.record_collaboration("fan_out", ["planner", "search", "browser", "rag"], duration_ms=250, success=True)
    collector.record_collaboration("fan_in", ["search", "browser", "rag", "analyst"], duration_ms=130, success=False)

    result = collector.get_metrics()
    collector.export_json(OUTPUT_ROOT / "multi_agent" / "summary.jsonl")
    return result


def run_stateful_agent_experiment() -> dict:
    collector = StatefulAgentMetricsCollector(output_dir=_ensure_clean_dir(OUTPUT_ROOT / "stateful_agent" / "data"))

    collector.record_session_start("session-state-1", "Long running budgeted research")
    ckpt1 = collector.record_checkpoint_save("session-state-1", checkpoint_id="ckpt-1", size_bytes=2048, duration_ms=18)
    ckpt2 = collector.record_checkpoint_save("session-state-1", checkpoint_id="ckpt-2", size_bytes=3072, duration_ms=24)
    collector.record_checkpoint_restore(ckpt2, "session-state-1", recovered=True)
    collector.record_failure_recovery("session-state-1", "crash", recovered=True, recovery_duration_ms=420, data_loss=False)
    _pause()
    collector.record_session_end("session-state-1", status="completed")

    collector.record_session_start("session-state-2", "Approval gated workflow recovery")
    collector.record_checkpoint_save("session-state-2", checkpoint_id="ckpt-3", size_bytes=1024, duration_ms=12)
    collector.record_failure_recovery("session-state-2", "timeout", recovered=False, recovery_duration_ms=900, data_loss=True)
    collector.record_data_loss("session-state-2")
    _pause()
    collector.record_session_end("session-state-2", status="failed")

    result = collector.get_metrics()
    collector.export_json(OUTPUT_ROOT / "stateful_agent" / "summary.jsonl")
    return result


def run_reflection_experiment() -> dict:
    collector = ReflectionMetricsCollector(storage_path=_ensure_clean_dir(OUTPUT_ROOT / "reflection_agent" / "data"))

    collector.record_reflection(
        session_id="reflect-1",
        total_claims=12,
        verified_claims=10,
        hallucinated_claims=1,
        conflicts=1,
        factuality_score=0.88,
        consistency_score=0.82,
        completeness_score=0.79,
        citation_coverage=0.83,
        overall_confidence=0.84,
        needs_revision=True,
        revision_count=1,
        hallucination_details=[
            {"claim": "provider always returns usage", "severity": "medium", "reason": "not always true", "suggested_action": "mark estimated"},
        ],
    )
    collector.record_revision("reflect-1", revision_number=1, triggered_by="hallucination", success=True, new_confidence=0.9)

    collector.record_reflection(
        session_id="reflect-2",
        total_claims=8,
        verified_claims=8,
        hallucinated_claims=0,
        conflicts=0,
        factuality_score=0.94,
        consistency_score=0.9,
        completeness_score=0.86,
        citation_coverage=0.91,
        overall_confidence=0.92,
        needs_revision=False,
        revision_count=0,
    )

    result = collector.get_metrics()
    collector.export_json(OUTPUT_ROOT / "reflection_agent" / "summary.jsonl")
    return result


def run_observability_experiment() -> dict:
    collector = ObservabilityMetricsCollector(storage_path=_ensure_clean_dir(OUTPUT_ROOT / "observability" / "data"))

    collector.record_connection_start("obs-1")
    collector.record_event_publish("obs-1", "thought", 120)
    collector.record_event_publish("obs-1", "tool_call", 220)
    collector.record_event_publish("obs-1", "approval", 80)
    _pause()
    collector.record_connection_end("obs-1", events_sent=3, bytes_sent=420)

    collector.record_connection_start("obs-2")
    collector.record_event_publish("obs-2", "trace", 90)
    _pause()
    collector.record_connection_end("obs-2", events_sent=1, bytes_sent=90)

    return collector.get_metrics()


def run_research_quality_experiment() -> dict:
    collector = ResearchQualityCollector(storage_path=_ensure_clean_dir(OUTPUT_ROOT / "research_quality" / "data"))

    collector.record_report_quality(
        session_id="quality-1",
        query="Compare harness and langgraph",
        total_claims=15,
        verified_claims=13,
        hallucinated_claims=1,
        citation_count=11,
        plan_coverage=0.87,
        avg_confidence=0.84,
    )
    collector.record_report_quality(
        session_id="quality-2",
        query="MCP governance review",
        total_claims=10,
        verified_claims=8,
        hallucinated_claims=1,
        citation_count=7,
        plan_coverage=0.74,
        avg_confidence=0.79,
    )

    return collector.get_metrics()


def run_browser_agent_experiment() -> dict:
    collector = BrowserAgentMetricsCollector(storage_path=_ensure_clean_dir(OUTPUT_ROOT / "browser_agent" / "data"))

    collector.record_open_start("browser-1", "https://example.com/article")
    collector.record_open_end("browser-1", "https://example.com/article", success=True, duration_ms=420, retries=0, status_code=200)
    collector.record_scroll_start("browser-1", "https://example.com/article")
    collector.record_scroll_end("browser-1", "https://example.com/article", scrolls=4, reached_bottom=True, loaded_more=False, duration_ms=160)
    collector.record_extraction_start("browser-1", "https://example.com/article", page_type="article")
    _pause()
    collector.record_extraction_end(
        "browser-1",
        "https://example.com/article",
        status="success",
        extraction_level="deep",
        original_tokens=4000,
        extracted_tokens=900,
        status_code=200,
        structured_data_count=2,
    )
    collector.record_analysis_end("browser-1", "https://example.com/article", confidence=0.88, predicted_type="article", duration_ms=90)

    collector.record_open_start("browser-2", "https://example.com/pricing")
    collector.record_open_end("browser-2", "https://example.com/pricing", success=False, duration_ms=900, retries=2, status_code=504)
    collector.record_scroll_start("browser-2", "https://example.com/pricing")
    collector.record_scroll_end("browser-2", "https://example.com/pricing", scrolls=1, reached_bottom=False, loaded_more=False, duration_ms=50)
    collector.record_extraction_start("browser-2", "https://example.com/pricing", page_type="landing")
    _pause()
    collector.record_extraction_end(
        "browser-2",
        "https://example.com/pricing",
        status="failed",
        extraction_level="skim",
        original_tokens=1500,
        extracted_tokens=0,
        status_code=504,
        error_type="timeout",
        error_message="gateway timeout",
        structured_data_count=0,
    )
    collector.record_analysis_end("browser-2", "https://example.com/pricing", confidence=0.32, predicted_type="landing", duration_ms=40)
    collector.record_browser_crash()

    result = collector.get_metrics()
    collector.export_json(str(OUTPUT_ROOT / "browser_agent" / "summary.json"))
    return result


def _run_browser_agent_scaled_case(sample_count: int) -> dict:
    collector = BrowserAgentMetricsCollector(
        storage_path=_ensure_clean_dir(OUTPUT_ROOT / "browser_agent_scale" / f"data_{sample_count}")
    )

    success_target = int(sample_count * 0.8)
    for i in range(sample_count):
        session_id = f"browser-scale-{sample_count}-{i}"
        if i < success_target:
            url = f"https://example.com/article/{i}"
            collector.record_open_start(session_id, url)
            collector.record_open_end(session_id, url, success=True, duration_ms=320 + (i % 7) * 15, retries=i % 2, status_code=200)
            collector.record_scroll_start(session_id, url)
            collector.record_scroll_end(session_id, url, scrolls=3 + (i % 4), reached_bottom=True, loaded_more=(i % 3 == 0), duration_ms=120 + (i % 5) * 10)
            collector.record_extraction_start(session_id, url, page_type="article")
            _pause()
            collector.record_extraction_end(
                session_id,
                url,
                status="success",
                extraction_level="deep" if i % 2 == 0 else "skim",
                original_tokens=3200 + i * 5,
                extracted_tokens=720 + (i % 6) * 30,
                status_code=200,
                structured_data_count=1 + (i % 3),
            )
            collector.record_analysis_end(
                session_id,
                url,
                confidence=0.82 + (i % 5) * 0.025,
                predicted_type="article",
                duration_ms=70 + (i % 4) * 10,
            )
        else:
            url = f"https://example.com/landing/{i}"
            collector.record_open_start(session_id, url)
            collector.record_open_end(session_id, url, success=False, duration_ms=700 + (i % 5) * 40, retries=1 + (i % 2), status_code=504)
            collector.record_scroll_start(session_id, url)
            collector.record_scroll_end(session_id, url, scrolls=1 + (i % 2), reached_bottom=False, loaded_more=False, duration_ms=40 + (i % 3) * 10)
            collector.record_extraction_start(session_id, url, page_type="landing")
            _pause()
            collector.record_extraction_end(
                session_id,
                url,
                status="failed",
                extraction_level="skim",
                original_tokens=1600 + i * 3,
                extracted_tokens=0,
                status_code=504,
                error_type="timeout" if i % 2 == 0 else "blocked",
                error_message="gateway timeout" if i % 2 == 0 else "anti bot blocked",
                structured_data_count=0,
            )
            collector.record_analysis_end(
                session_id,
                url,
                confidence=0.28 + (i % 4) * 0.04,
                predicted_type="landing",
                duration_ms=30 + (i % 2) * 10,
            )
            if i % 3 == 0:
                collector.record_browser_crash()

    result = collector.get_metrics()
    result["sample_count"] = sample_count
    collector.export_json(str(OUTPUT_ROOT / "browser_agent_scale" / f"summary_{sample_count}.json"))
    return result


def run_browser_agent_scale_experiments() -> dict:
    return {
        "20": _run_browser_agent_scaled_case(20),
        "50": _run_browser_agent_scaled_case(50),
        "100": _run_browser_agent_scaled_case(100),
    }


def main() -> None:
    global OUTPUT_ROOT
    run_id = time.strftime("%Y%m%d-%H%M%S")
    OUTPUT_ROOT = BASE_OUTPUT_ROOT / run_id
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    results = {
        "langgraph_workflow": run_langgraph_workflow_experiment(),
        "research_dag": run_research_dag_experiment(),
        "multi_agent": run_multi_agent_experiment(),
        "stateful_agent": run_stateful_agent_experiment(),
        "reflection_agent": run_reflection_experiment(),
        "observability": run_observability_experiment(),
        "research_quality": run_research_quality_experiment(),
        "browser_agent": run_browser_agent_experiment(),
        "browser_agent_scale": run_browser_agent_scale_experiments(),
    }

    output_file = OUTPUT_ROOT / "summary.json"
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
