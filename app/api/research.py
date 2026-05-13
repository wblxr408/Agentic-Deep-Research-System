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
from app.graph.compiler import compile_research_graph
from app.graph.state import create_initial_state, ResearchState, TaskStatus
from app.observability.sse_manager import get_sse_manager
from app.db.connection import get_db_pool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/research", tags=["research"])


# ==============================================================
# Request/Response Models
# ==============================================================

class ResearchRequest(BaseModel):
    """Request body for starting a research task."""
    query: str = Field(..., min_length=5, max_length=2000, description="Research query")
    session_id: str | None = Field(default=None, description="Optional session ID for continuation")
    max_revision: int = Field(default=3, ge=1, le=5, description="Max revision loops")


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
    - error: Error occurred
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

    logger.info(f"Creating research session: {session_id}, query: {request.query[:50]}")

    # Save to database
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO research_sessions (id, user_query, status, created_at, updated_at)
            VALUES ($1::uuid, $2, 'running', $3, $3)
            ON CONFLICT (id) DO UPDATE SET
                user_query = $2,
                status = 'running',
                updated_at = $3
            """,
            session_id,
            request.query,
            datetime.utcnow(),
        )

    # Start background execution
    background_tasks.add_task(
        run_research_workflow,
        session_id=session_id,
        query=request.query,
        max_revision=request.max_revision,
    )

    return ResearchResponse(
        session_id=session_id,
        status="running",
        message=f"Research task started. Connect to /api/v1/research/stream/{session_id} for updates.",
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

    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": str(row["id"]),
        "query": row["user_query"],
        "status": row["status"],
        "report": row["final_report"],
        "citations": row["citations"],
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
        async for chunk in graph.astream(state, config):
            # Emit state updates
            if isinstance(chunk, dict):
                # Merge chunk into accumulated state
                for key, value in chunk.items():
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
        final_state: dict[str, Any] = accumulated_state if accumulated_state else chunk if chunk else {}

        # Save results to database
        if final_state:
            pool = await get_db_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE research_sessions
                    SET status = $1,
                        final_report = $2,
                        citations = $3::jsonb,
                        agent_trace = $4::jsonb,
                        updated_at = $5,
                        completed_at = $5
                    WHERE id = $6::uuid
                    """,
                    final_state.get("status", TaskStatus.COMPLETED.value),
                    final_state.get("final_report", ""),
                    final_state.get("citations", []),
                    final_state.get("agent_trace", []),
                    datetime.utcnow(),
                    session_id,
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
        await sse.publish(session_id, "error", {
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
