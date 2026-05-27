"""
Research API endpoints: SSE streaming and research session management.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.config import get_settings
from app.guardrails import (
    build_guardrail_decision,
    build_review_status,
    compose_guardrail_prompt,
    get_research_budget,
    normalize_research_length,
)
from app.graph.compiler import compile_research_graph
from app.graph.state import create_initial_state, ResearchState, RuntimeStatus, TaskStatus
from app.observability.sse_manager import get_sse_manager
from app.db.connection import get_db_pool
from app.db.json import dumps_json

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/research", tags=["research"])
ACCUMULATING_STATE_KEYS = {
    "agent_trace",
    "tool_histories",
    "collected_evidence",
    "search_results",
    "browser_results",
    "rag_results",
    "aggregated_evidence",
    "node_outcomes",
    "pending_approvals",
}

KNOWN_STATE_KEYS = {
    "task_id",
    "user_query",
    "created_at",
    "status",
    "session",
    "dag",
    "current_executing_nodes",
    "completed_nodes",
    "node_outcomes",
    "tool_histories",
    "collected_evidence",
    "search_results",
    "browser_results",
    "rag_results",
    "aggregated_evidence",
    "verification",
    "revision_needed",
    "revision_count",
    "analysis",
    "final_report",
    "citations",
    "guardrail_decision",
    "evidence_status",
    "review_status",
    "user_confirmed",
    "allow_web_after_rag_hit",
    "rag_group",
    "retrieval_policy",
    "runtime_status",
    "budget_state",
    "pending_approvals",
    "agent_trace",
    "guardrail_trace",
    "errors",
}


def _iter_state_updates(chunk: dict[str, Any]):
    """Yield state update mappings from raw LangGraph stream chunks."""
    if any(key in KNOWN_STATE_KEYS for key in chunk):
        yield chunk
        return

    for value in chunk.values():
        if isinstance(value, dict):
            yield value


def _normalize_citations(value: Any) -> list[dict[str, Any]]:
    """Return citations as a list of dicts regardless of stored shape."""
    if isinstance(value, list):
        normalized: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                normalized.append(item)
            else:
                normalized.append({"value": item})
        return normalized
    if isinstance(value, dict):
        return [value]
    return []


def _stable_json_hash(value: Any) -> str | None:
    """Return a stable sha256 hash for JSON-serializable payloads."""
    if value is None:
        return None
    payload = dumps_json(value)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_tool_audit_rows(
    session_id: str,
    tool_histories: list[dict[str, Any]],
    node_outcomes: list[dict[str, Any]],
) -> list[tuple[Any, ...]]:
    """Flatten runtime tool histories into forensic audit rows."""
    outcomes_by_call_id: dict[str, dict[str, Any]] = {}
    for outcome in node_outcomes:
        if not isinstance(outcome, dict):
            continue
        call_id = outcome.get("tool_call_id")
        if call_id:
            outcomes_by_call_id[str(call_id)] = outcome

    rows: list[tuple[Any, ...]] = []
    for history in tool_histories:
        if not isinstance(history, dict):
            continue
        agent_type = history.get("agent_type")
        for call in history.get("tool_calls", []):
            if not isinstance(call, dict):
                continue
            call_id = str(call.get("call_id") or f"call-{uuid.uuid4().hex[:12]}")
            outcome = outcomes_by_call_id.get(call_id, {})
            args_json = call.get("args") or {}
            result_summary = call.get("result_summary")
            rows.append((
                call_id,
                session_id,
                outcome.get("node_id"),
                agent_type,
                call.get("tool_name"),
                dumps_json(args_json),
                _stable_json_hash(args_json),
                call.get("status") or "pending",
                outcome.get("error_category"),
                outcome.get("error_message") or call.get("error"),
                int(outcome.get("retry_count") or 0),
                result_summary,
                _stable_json_hash(result_summary),
                int(call.get("tokens_used") or outcome.get("tokens_used") or 0),
                float(call.get("cost_usd") or outcome.get("cost_usd") or 0.0),
                None,
                None,
                None,
                call.get("started_at"),
                call.get("completed_at"),
            ))
    return rows


# ==============================================================
# Request/Response Models
# ==============================================================

class ResearchRequest(BaseModel):
    """Request body for starting a research task."""
    query: str = Field(..., min_length=5, max_length=2000, description="Research query")
    session_id: str | None = Field(default=None, description="Optional session ID for continuation")
    max_revision: int = Field(default=3, ge=1, le=5, description="Max revision loops")
    user_confirmed: bool = Field(default=False, description="User confirmed high-risk task")
    allow_web_after_rag_hit: bool = Field(
        default=False,
        description="If internal RAG finds evidence, also run internet search.",
    )
    rag_group: str | None = Field(
        default=None,
        max_length=100,
        description="Optional internal RAG source group filter.",
    )
    output_length: str = Field(
        default="medium",
        description="Output length: short, medium, long.",
    )


class ResearchStatus(BaseModel):
    """Response for research status query."""
    session_id: str
    status: str
    created_at: str
    updated_at: str | None = None
    runtime_status: str | None = None
    requires_confirmation: bool = False
    pending_approval_count: int = 0
    budget_state: dict[str, Any] | None = None
    last_error_category: str | None = None


class ResearchResponse(BaseModel):
    """Response for research creation."""
    session_id: str
    status: str
    message: str
    requires_confirmation: bool = False
    output_length: str = "medium"
    budget: dict[str, int | float] = Field(default_factory=dict)


class ToolCallAuditRecord(BaseModel):
    """Single persisted tool call audit row."""
    call_id: str
    session_id: str
    node_id: str | None = None
    agent_type: str
    tool_name: str
    args_json: dict[str, Any] = Field(default_factory=dict)
    args_hash: str | None = None
    status: str
    error_category: str | None = None
    error_message: str | None = None
    retry_count: int = 0
    result_summary: str | None = None
    result_hash: str | None = None
    tokens_used: int = 0
    cost_usd: float = 0.0
    decision_id: str | None = None
    approved_by: str | None = None
    server_fingerprint: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str | None = None


# ==============================================================
# SSE Event Streaming
# ==============================================================

async def research_event_generator(
    session_id: str,
) -> AsyncGenerator[dict[str, Any], None]:
    """
    SSE event generator for research progress.
    Yields events as SSE-compatible dictionaries.
    """
    sse = get_sse_manager()

    # Send initial connection event
    yield {
        "event": "connected",
        "data": {"session_id": session_id, "timestamp": datetime.utcnow().isoformat()},
    }

    try:
        # Stream events from the queue
        async for event in sse.stream(session_id):
            yield event
    except asyncio.CancelledError:
        logger.info(f"SSE stream cancelled for session {session_id}")
        yield {
            "event": "disconnected",
            "data": {"session_id": session_id},
        }


@router.get("/stream/{session_id}")
async def stream_research(session_id: str):
    """
    SSE endpoint for real-time research progress streaming.

    Clients should connect with:
        const eventSource = new EventSource(`/api/v1/research/stream/${sessionId}`);

    Event types:
    - connected: Initial connection confirmation
    - agent_start/end: Agent execution lifecycle
    - thought: LLM reasoning process
    - tool_call/result/error: Tool invocations
    - state_update: Workflow state changes
    - reflection: Reflection result
    - report_chunk: Report content chunks
    - done: Task completion
    - workflow_error: Workflow/business error occurred
    """
    return EventSourceResponse(
        research_event_generator(session_id),
        media_type="text/event-stream",
    )


# ==============================================================
# Research Task Management
# ==============================================================

@router.post("", response_model=ResearchResponse)
async def create_research(
    request: ResearchRequest,
    background_tasks: BackgroundTasks,
):
    """
    Start a new research task.

    Creates a research session, saves it to the database,
    and dispatches the LangGraph workflow to run in background.
    """
    # Generate or use provided session ID
    session_id = request.session_id or str(uuid.uuid4())
    decision = build_guardrail_decision(request.query, user_confirmed=request.user_confirmed)
    output_length = normalize_research_length(request.output_length)
    budget = get_research_budget(output_length)

    logger.info(f"Creating research session: {session_id}, query: {request.query[:50]}")

    # Save to database
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        review_status = build_review_status(
            blocked=decision.must_confirm and not request.user_confirmed,
            requires_confirmation=decision.must_confirm and not request.user_confirmed,
            approved=request.user_confirmed or not decision.must_confirm,
            reason="pending_confirmation" if decision.must_confirm and not request.user_confirmed else None,
            risk_level=decision.risk_level,
            intent=decision.intent,
            prompt_profile=decision.prompt_profile,
        )
        await conn.execute(
            """
            INSERT INTO research_sessions (id, user_query, status, guardrail_decision, guardrail_trace,
                                           evidence_status, review_status, prompt_profile, prompt_template,
                                           enabled_tools, created_at, updated_at)
            VALUES ($1::uuid, $2, $3, $4::jsonb, $5::jsonb, $6::jsonb, $7::jsonb, $8, $9, $10::jsonb, $11, $11)
            ON CONFLICT (id) DO UPDATE SET
                user_query = $2,
                status = $3,
                guardrail_decision = $4::jsonb,
                guardrail_trace = $5::jsonb,
                evidence_status = $6::jsonb,
                review_status = $7::jsonb,
                prompt_profile = $8,
                prompt_template = $9,
                enabled_tools = $10::jsonb,
                updated_at = $11
            """,
            session_id,
            request.query,
            "pending" if decision.must_confirm and not request.user_confirmed else "running",
            dumps_json(decision.model_dump()),
            dumps_json([]),
            dumps_json(None),
            dumps_json(review_status),
            decision.prompt_profile.value,
            compose_guardrail_prompt(request.query, decision),
            dumps_json(decision.enabled_tools),
            datetime.utcnow(),
        )

    if decision.must_confirm and not request.user_confirmed:
        return ResearchResponse(
            session_id=session_id,
            status="pending_confirmation",
            message="High-risk request requires user confirmation before execution.",
            requires_confirmation=True,
            output_length=output_length.value,
            budget=budget,
        )

    # Start background execution
    background_tasks.add_task(
        run_research_workflow,
        session_id=session_id,
        query=request.query,
        max_revision=request.max_revision,
        user_confirmed=request.user_confirmed,
        allow_web_after_rag_hit=request.allow_web_after_rag_hit,
        rag_group=request.rag_group,
        output_length=output_length.value,
    )

    return ResearchResponse(
        session_id=session_id,
        status="running",
        message=f"Research task started. Connect to /api/v1/research/stream/{session_id} for updates.",
        requires_confirmation=False,
        output_length=output_length.value,
        budget=budget,
    )


@router.get("/status/{session_id}", response_model=ResearchStatus)
async def get_research_status(session_id: str):
    """Get the current status of a research session."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT rs.id, rs.user_query, rs.status, rs.review_status, rs.created_at, rs.updated_at, rs.completed_at,
                   sbs.max_total_tokens, sbs.max_cost_usd, sbs.max_tool_calls, sbs.max_wall_clock_seconds,
                   sbs.used_total_tokens, sbs.used_cost_usd, sbs.used_tool_calls,
                   sbs.elapsed_wall_clock_seconds, sbs.hard_stop_reason
            FROM research_sessions
            rs
            LEFT JOIN session_budget_state sbs ON sbs.session_id = rs.id
            WHERE rs.id = $1::uuid
            """,
            session_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    review_status = row.get("review_status") or {}
    budget_state = review_status.get("budget_state")
    if row.get("max_tool_calls") is not None:
        budget_state = {
            "max_total_tokens": int(row.get("max_total_tokens") or 0),
            "max_cost_usd": float(row.get("max_cost_usd") or 0.0),
            "max_tool_calls": int(row.get("max_tool_calls") or 0),
            "max_wall_clock_seconds": int(row.get("max_wall_clock_seconds") or 0),
            "used_total_tokens": int(row.get("used_total_tokens") or 0),
            "used_cost_usd": float(row.get("used_cost_usd") or 0.0),
            "used_tool_calls": int(row.get("used_tool_calls") or 0),
            "elapsed_wall_clock_seconds": int(row.get("elapsed_wall_clock_seconds") or 0),
            "hard_stop_reason": row.get("hard_stop_reason"),
        }
    pending_approval_count = int(review_status.get("pending_approval_count", 0) or 0)
    return ResearchStatus(
        session_id=str(row["id"]),
        status=row["status"],
        created_at=row["created_at"].isoformat(),
        updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
        runtime_status=review_status.get("runtime_status"),
        requires_confirmation=bool(review_status.get("requires_confirmation", False)),
        pending_approval_count=pending_approval_count,
        budget_state=budget_state,
        last_error_category=review_status.get("last_error_category"),
    )


@router.get("/{session_id}")
async def get_research_result(session_id: str):
    """Get the final research result."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, user_query, status, final_report, citations, agent_trace, review_status, created_at, completed_at
            FROM research_sessions
            WHERE id = $1::uuid
            """,
            session_id,
        )
        citation_rows = await conn.fetch(
            """
            SELECT citation_id, source_url, source_title, source_type,
                   extracted_evidence, relevance_score, access_timestamp
            FROM citations
            WHERE session_id = $1::uuid
            ORDER BY CAST(SPLIT_PART(citation_id, ':', 2) AS INTEGER)
            """,
            session_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    citations = [dict(citation) for citation in citation_rows] if citation_rows else _normalize_citations(row["citations"])

    review_status = row.get("review_status") or {}
    return {
        "session_id": str(row["id"]),
        "query": row["user_query"],
        "status": row["status"],
        "runtime_status": review_status.get("runtime_status"),
        "report": row["final_report"],
        "citations": citations,
        "agent_trace": row["agent_trace"],
        "tool_audit_summary": review_status.get("tool_audit_summary", {}),
        "created_at": row["created_at"].isoformat(),
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
    }


@router.get("/{session_id}/tool-calls", response_model=list[ToolCallAuditRecord])
async def get_research_tool_calls(session_id: str):
    """Get persisted per-call tool audit rows for a research session."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        session_exists = await conn.fetchrow(
            "SELECT id FROM research_sessions WHERE id = $1::uuid",
            session_id,
        )
        if not session_exists:
            raise HTTPException(status_code=404, detail="Session not found")

        rows = await conn.fetch(
            """
            SELECT call_id, session_id, node_id, agent_type, tool_name,
                   args_json, args_hash, status, error_category, error_message,
                   retry_count, result_summary, result_hash, tokens_used, cost_usd,
                   decision_id, approved_by, server_fingerprint,
                   started_at, completed_at, created_at
            FROM tool_call_audit
            WHERE session_id = $1::uuid
            ORDER BY created_at ASC, call_id ASC
            """,
            session_id,
        )

    result: list[ToolCallAuditRecord] = []
    for row in rows:
        result.append(ToolCallAuditRecord(
            call_id=row["call_id"],
            session_id=str(row["session_id"]),
            node_id=row["node_id"],
            agent_type=row["agent_type"],
            tool_name=row["tool_name"],
            args_json=row["args_json"] or {},
            args_hash=row["args_hash"],
            status=row["status"],
            error_category=row["error_category"],
            error_message=row["error_message"],
            retry_count=int(row["retry_count"] or 0),
            result_summary=row["result_summary"],
            result_hash=row["result_hash"],
            tokens_used=int(row["tokens_used"] or 0),
            cost_usd=float(row["cost_usd"] or 0.0),
            decision_id=row["decision_id"],
            approved_by=row["approved_by"],
            server_fingerprint=row["server_fingerprint"],
            started_at=row["started_at"].isoformat() if row["started_at"] else None,
            completed_at=row["completed_at"].isoformat() if row["completed_at"] else None,
            created_at=row["created_at"].isoformat() if row["created_at"] else None,
        ))
    return result


# ==============================================================
# Background Workflow Execution
# ==============================================================

async def run_research_workflow(
    session_id: str,
    query: str,
    max_revision: int = 3,
    user_confirmed: bool = False,
    allow_web_after_rag_hit: bool = False,
    rag_group: str | None = None,
    output_length: str = "medium",
):
    """
    Execute the LangGraph research workflow in background.

    This function:
    1. Compiles the StateGraph
    2. Creates the initial state
    3. Streams events via SSE
    4. Saves final results to the database
    """
    sse = get_sse_manager()

    try:
        # Emit start event
        await sse.publish(session_id, "workflow_start", {
            "session_id": session_id,
            "query": query,
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Create initial state
        state = create_initial_state(query, session_id)
        state["session"]["max_revisions"] = max_revision
        state["session"]["output_length"] = output_length
        decision = build_guardrail_decision(query)
        state["guardrail_decision"] = decision.model_dump()
        state["user_confirmed"] = user_confirmed
        state["allow_web_after_rag_hit"] = allow_web_after_rag_hit
        state["rag_group"] = rag_group
        state["output_length"] = output_length
        state["retrieval_policy"] = {
            "mode": "internal_first",
            "allow_web_after_rag_hit": allow_web_after_rag_hit,
            "rag_group": rag_group,
            "rag_hit_count": 0,
            "web_search_required": None,
            "web_search_reason": None,
        }
        state["session"]["prompt_profile"] = decision.prompt_profile.value
        state["session"]["enabled_tools"] = decision.enabled_tools
        state["session"]["prompt_template"] = compose_guardrail_prompt(query, decision)
        state["runtime_status"] = RuntimeStatus.RUNNING.value
        state["budget_state"] = {
            "budget_profile": output_length,
            "estimated": True,
            **budget,
            "used_total_tokens": 0,
            "used_cost_usd": 0.0,
            "used_tool_calls": 0,
            "elapsed_wall_clock_seconds": 0,
            "hard_stop_reason": None,
            "warning": False,
        }

        # Compile graph
        graph = compile_research_graph()

        # Run with streaming
        config = {
            "configurable": {
                "thread_id": session_id,
            }
        }

        # Run the graph and accumulate state from all chunks
        # FIX: Use a dict to accumulate state, not just last chunk
        accumulated_state: dict[str, Any] = {}
        last_chunk: dict[str, Any] = {}
        async for chunk in graph.astream(state, config):
            # Emit state updates
            if isinstance(chunk, dict):
                last_chunk = chunk
                # Merge chunk into accumulated state
                for update in _iter_state_updates(chunk):
                    for key, value in update.items():
                        if key in ACCUMULATING_STATE_KEYS and isinstance(value, list):
                            accumulated_state.setdefault(key, [])
                            accumulated_state[key].extend(value)
                        else:
                            accumulated_state[key] = value

                        if key == "agent_trace":
                            # Forward agent trace events to SSE
                            for event in value:
                                event_type = event.get("event_type", "trace") if isinstance(event, dict) else "trace"
                                await sse.publish(session_id, event_type, event)
                        else:
                            # Forward other state updates
                            await sse.publish(session_id, "state_update", {
                                "key": key,
                                "value": str(value)[:500] if value else "",
                            })

        # Determine final state
        # Use accumulated state, with fallback to last chunk
        final_state: dict[str, Any] = accumulated_state if accumulated_state else last_chunk

        # Save results to database
        if final_state:
            pool = await get_db_pool()
            async with pool.acquire() as conn:
                completed_at = datetime.utcnow()
                citations = final_state.get("citations", [])
                tool_histories = final_state.get("tool_histories", [])
                tool_call_total = sum(
                    len(history.get("tool_calls", []))
                    for history in tool_histories
                    if isinstance(history, dict)
                )
                tool_call_errors = sum(
                    sum(1 for call in history.get("tool_calls", []) if call.get("status") == "error")
                    for history in tool_histories
                    if isinstance(history, dict)
                )
                pending_approval_count = len(final_state.get("pending_approvals", []))
                runtime_status = final_state.get("runtime_status", final_state.get("status", TaskStatus.COMPLETED.value))
                review_status = dict(final_state.get("review_status") or {})
                tool_audit_rows = _normalize_tool_audit_rows(
                    session_id=session_id,
                    tool_histories=tool_histories,
                    node_outcomes=final_state.get("node_outcomes", []),
                )
                session_budget_state = dict(final_state.get("budget_state") or {})
                review_status.update({
                    "runtime_status": runtime_status,
                    "pending_approval_count": pending_approval_count,
                    "budget_state": session_budget_state,
                    "tool_audit_summary": {
                        "total_calls": tool_call_total,
                        "error_calls": tool_call_errors,
                        "persisted_calls": len(tool_audit_rows),
                    },
                })
                last_error_category = None
                for outcome in reversed(final_state.get("node_outcomes", [])):
                    if isinstance(outcome, dict) and outcome.get("error_category"):
                        last_error_category = outcome.get("error_category")
                        break
                if last_error_category:
                    review_status["last_error_category"] = last_error_category
                async with conn.transaction():
                    await conn.execute(
                        """
                        UPDATE research_sessions
                        SET status = $1,
                            guardrail_decision = $2::jsonb,
                            guardrail_trace = $3::jsonb,
                            evidence_status = $4::jsonb,
                            review_status = $5::jsonb,
                            prompt_profile = $6,
                            prompt_template = $7,
                            enabled_tools = $8::jsonb,
                            final_report = $9,
                            citations = $10::jsonb,
                            agent_trace = $11::jsonb,
                            total_tokens = $12,
                            total_cost_usd = $13,
                            updated_at = $14,
                            completed_at = $14
                        WHERE id = $15::uuid
                        """,
                        final_state.get("status", TaskStatus.COMPLETED.value),
                        dumps_json(final_state.get("guardrail_decision")),
                        dumps_json(final_state.get("guardrail_trace", [])),
                        dumps_json(final_state.get("evidence_status")),
                        dumps_json(review_status),
                        final_state.get("session", {}).get("prompt_profile"),
                        final_state.get("session", {}).get("prompt_template"),
                        dumps_json(final_state.get("session", {}).get("enabled_tools", [])),
                        final_state.get("final_report", ""),
                        dumps_json(citations),
                        dumps_json(final_state.get("agent_trace", [])),
                        int(final_state.get("session", {}).get("total_tokens", session_budget_state.get("used_total_tokens", 0)) or 0),
                        float(final_state.get("session", {}).get("total_cost_usd", session_budget_state.get("used_cost_usd", 0.0)) or 0.0),
                        completed_at,
                        session_id,
                    )
                    await conn.execute(
                        """
                        INSERT INTO session_budget_state (
                            session_id,
                            max_total_tokens,
                            max_cost_usd,
                            max_tool_calls,
                            max_wall_clock_seconds,
                            max_retries_per_tool,
                            used_total_tokens,
                            used_cost_usd,
                            used_tool_calls,
                            elapsed_wall_clock_seconds,
                            hard_stop_reason,
                            updated_at
                        )
                        VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                        ON CONFLICT (session_id) DO UPDATE SET
                            max_total_tokens = EXCLUDED.max_total_tokens,
                            max_cost_usd = EXCLUDED.max_cost_usd,
                            max_tool_calls = EXCLUDED.max_tool_calls,
                            max_wall_clock_seconds = EXCLUDED.max_wall_clock_seconds,
                            max_retries_per_tool = EXCLUDED.max_retries_per_tool,
                            used_total_tokens = EXCLUDED.used_total_tokens,
                            used_cost_usd = EXCLUDED.used_cost_usd,
                            used_tool_calls = EXCLUDED.used_tool_calls,
                            elapsed_wall_clock_seconds = EXCLUDED.elapsed_wall_clock_seconds,
                            hard_stop_reason = EXCLUDED.hard_stop_reason,
                            updated_at = EXCLUDED.updated_at
                        """,
                        session_id,
                        int(session_budget_state.get("max_total_tokens", 0) or 0),
                        float(session_budget_state.get("max_cost_usd", 0.0) or 0.0),
                        int(session_budget_state.get("max_tool_calls", 0) or 0),
                        int(session_budget_state.get("max_wall_clock_seconds", 0) or 0),
                        int(session_budget_state.get("max_retries_per_tool", 0) or 0),
                        int(session_budget_state.get("used_total_tokens", 0) or 0),
                        float(session_budget_state.get("used_cost_usd", 0.0) or 0.0),
                        int(session_budget_state.get("used_tool_calls", 0) or 0),
                        int(session_budget_state.get("elapsed_wall_clock_seconds", 0) or 0),
                        session_budget_state.get("hard_stop_reason"),
                        completed_at,
                    )
                    await conn.execute(
                        "DELETE FROM citations WHERE session_id = $1::uuid",
                        session_id,
                    )
                    await conn.execute(
                        "DELETE FROM tool_call_audit WHERE session_id = $1::uuid",
                        session_id,
                    )
                    if citations:
                        await conn.executemany(
                            """
                            INSERT INTO citations (
                                session_id,
                                citation_id,
                                source_url,
                                source_title,
                                source_type,
                                extracted_evidence,
                                relevance_score,
                                access_timestamp
                            )
                            VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8)
                            """,
                            [
                                (
                                    session_id,
                                    citation.get("citation_id"),
                                    citation.get("source_url"),
                                    citation.get("source_title"),
                                    citation.get("source_type", "web"),
                                    citation.get("extracted_evidence"),
                                    citation.get("relevance_score", 0.0),
                                    completed_at,
                                )
                                for citation in citations
                            ],
                        )
                    if tool_audit_rows:
                        await conn.executemany(
                            """
                            INSERT INTO tool_call_audit (
                                call_id,
                                session_id,
                                node_id,
                                agent_type,
                                tool_name,
                                args_json,
                                args_hash,
                                status,
                                error_category,
                                error_message,
                                retry_count,
                                result_summary,
                                result_hash,
                                tokens_used,
                                cost_usd,
                                decision_id,
                                approved_by,
                                server_fingerprint,
                                started_at,
                                completed_at
                            )
                            VALUES (
                                $1, $2::uuid, $3, $4, $5, $6::jsonb, $7, $8, $9, $10,
                                $11, $12, $13, $14, $15, $16, $17, $18, $19, $20
                            )
                            """,
                            tool_audit_rows,
                        )

        # Emit completion
        await sse.publish(session_id, "done", {
            "session_id": session_id,
            "status": "completed",
            "timestamp": datetime.utcnow().isoformat(),
        })

        logger.info(f"Research workflow completed: {session_id}")

    except Exception as e:
        logger.error(f"Research workflow error for {session_id}: {e}", exc_info=True)

        # Emit error
        await sse.publish(session_id, "workflow_error", {
            "session_id": session_id,
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Update database status - FIX: properly log errors instead of bare except:pass
        try:
            pool = await get_db_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE research_sessions
                    SET status = 'failed', updated_at = $1
                    WHERE id = $2::uuid
                    """,
                    datetime.utcnow(),
                    session_id,
                )
        except Exception as db_error:
            # FIX: Log the error instead of silently swallowing
            logger.error(
                f"Failed to update session {session_id} status to 'failed': {db_error}"
            )
