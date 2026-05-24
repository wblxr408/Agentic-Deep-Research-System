"""
Research API endpoints: SSE streaming and research session management.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.config import get_settings
from app.guardrails import build_guardrail_decision, build_review_status, compose_guardrail_prompt
from app.graph.compiler import compile_research_graph
from app.graph.state import create_initial_state, ResearchState, TaskStatus
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


class ResearchStatus(BaseModel):
    """Response for research status query."""
    session_id: str
    status: str
    created_at: str
    updated_at: str | None = None


class ResearchResponse(BaseModel):
    """Response for research creation."""
    session_id: str
    status: str
    message: str
    requires_confirmation: bool = False


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
    )

    return ResearchResponse(
        session_id=session_id,
        status="running",
        message=f"Research task started. Connect to /api/v1/research/stream/{session_id} for updates.",
        requires_confirmation=False,
    )


@router.get("/status/{session_id}", response_model=ResearchStatus)
async def get_research_status(session_id: str):
    """Get the current status of a research session."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, user_query, status, created_at, updated_at, completed_at
            FROM research_sessions
            WHERE id = $1::uuid
            """,
            session_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    return ResearchStatus(
        session_id=str(row["id"]),
        status=row["status"],
        created_at=row["created_at"].isoformat(),
        updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
    )


@router.get("/{session_id}")
async def get_research_result(session_id: str):
    """Get the final research result."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, user_query, status, final_report, citations, agent_trace, created_at, completed_at
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

    return {
        "session_id": str(row["id"]),
        "query": row["user_query"],
        "status": row["status"],
        "report": row["final_report"],
        "citations": citations,
        "agent_trace": row["agent_trace"],
        "created_at": row["created_at"].isoformat(),
        "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
    }


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
        decision = build_guardrail_decision(query)
        state["guardrail_decision"] = decision.model_dump()
        state["user_confirmed"] = user_confirmed
        state["allow_web_after_rag_hit"] = allow_web_after_rag_hit
        state["rag_group"] = rag_group
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
                            updated_at = $12,
                            completed_at = $12
                        WHERE id = $13::uuid
                        """,
                        final_state.get("status", TaskStatus.COMPLETED.value),
                        dumps_json(final_state.get("guardrail_decision")),
                        dumps_json(final_state.get("guardrail_trace", [])),
                        dumps_json(final_state.get("evidence_status")),
                        dumps_json(final_state.get("review_status")),
                        final_state.get("session", {}).get("prompt_profile"),
                        final_state.get("session", {}).get("prompt_template"),
                        dumps_json(final_state.get("session", {}).get("enabled_tools", [])),
                        final_state.get("final_report", ""),
                        dumps_json(citations),
                        dumps_json(final_state.get("agent_trace", [])),
                        completed_at,
                        session_id,
                    )
                    await conn.execute(
                        "DELETE FROM citations WHERE session_id = $1::uuid",
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
