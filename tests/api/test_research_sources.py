from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import BackgroundTasks

from app.api.research import ResearchRequest, create_research
from app.security.auth import Principal


@pytest.mark.asyncio
@pytest.mark.parametrize("internal", [False, True])
async def test_research_request_delivers_explicit_document_selection_to_workflow(monkeypatch, mock_db_pool, internal):
    registry = MagicMock()
    registry.resolve_for_session = AsyncMock(return_value=SimpleNamespace(as_dict=lambda: {}))
    monkeypatch.setattr("app.api.research.get_skill_registry", lambda owner_id: registry)
    monkeypatch.setattr("app.api.research.get_db_pool", AsyncMock(return_value=mock_db_pool))
    tasks = BackgroundTasks()
    principal = Principal(id="11111111-1111-4111-8111-111111111111", username="reader", auth_type="session")
    request = ResearchRequest(query="分析公开市场的最新趋势", use_internal_docs=internal, rag_group="project-a", allow_web_after_rag_hit=False, channels=["github"])
    response = await create_research(request, tasks, principal)
    assert response.status == "running"
    assert tasks.tasks[0].kwargs.get("use_internal_docs") is internal
    assert tasks.tasks[0].kwargs["rag_group"] == ("project-a" if internal else None)
    assert tasks.tasks[0].kwargs["owner_id"] == principal.id
    assert tasks.tasks[0].kwargs["channels"] == ["github"]


@pytest.mark.asyncio
@pytest.mark.parametrize("internal", [False, True])
async def test_background_workflow_preserves_source_selection_in_checkpoint_and_graph(monkeypatch, internal):
    from app.api import research

    captured = []
    class Graph:
        async def astream(self, state, config):
            captured.append(state.copy())
            if False:
                yield {}

    persistence = SimpleNamespace(persist_runtime_snapshot=AsyncMock())
    monkeypatch.setattr(research, "compile_research_graph", lambda: Graph())
    monkeypatch.setattr(research, "get_settings", lambda: SimpleNamespace(harness=SimpleNamespace(state_root="unused", worker_id="test")))
    monkeypatch.setattr(research, "get_sse_manager", lambda: SimpleNamespace(publish=AsyncMock()))
    monkeypatch.setattr(research, "RuntimePersistence", lambda: persistence)
    monkeypatch.setattr(research, "HarnessSupervisor", lambda *args: MagicMock())
    await research.run_research_workflow("source-test", "公开市场研究", use_internal_docs=internal, rag_group="project-a", owner_id="11111111-1111-4111-8111-111111111111", channels=["github"])
    for state in [captured[0], persistence.persist_runtime_snapshot.call_args_list[0].kwargs["state"]]:
        assert state["use_internal_docs"] is internal
        assert state["rag_group"] == ("project-a" if internal else None)
        assert state["session"]["channels"] == ["github"]


@pytest.mark.asyncio
@pytest.mark.parametrize("internal", [None, True])
async def test_approval_resume_uses_new_source_choice_and_ignores_legacy_switch(monkeypatch, mock_db_pool, internal):
    from app.api import research

    snapshot = {"user_query": "公开市场研究", "session": {"owner_id": "11111111-1111-4111-8111-111111111111", "channels": ["github"]}, "allow_web_after_rag_hit": False, "rag_group": "project-a"}
    if internal is not None:
        snapshot["use_internal_docs"] = internal
    conn = await mock_db_pool.acquire().__aenter__()
    conn.fetchrow.return_value = {"status": "pending", "request_payload_json": {}}
    monkeypatch.setattr(research, "get_db_pool", AsyncMock(return_value=mock_db_pool))
    monkeypatch.setattr(research, "HarnessSupervisor", lambda *args: SimpleNamespace(get_task=lambda session_id: {"checkpoint": {"state_snapshot": snapshot}}))
    monkeypatch.setattr(research, "compile_research_graph", MagicMock())
    resumed = AsyncMock()
    monkeypatch.setattr(research, "run_research_workflow", resumed)
    pending = []
    monkeypatch.setattr(research.asyncio, "create_task", lambda coroutine: pending.append(coroutine))
    principal = Principal(id=snapshot["session"]["owner_id"], username="reader", auth_type="session")
    await research.resolve_research_approval("source-test", "approval-test", research.ApprovalActionRequest(action="approve", approved_by="reader"), principal)
    await pending[0]
    assert resumed.call_args.kwargs["use_internal_docs"] is bool(internal)
    assert "allow_web_after_rag_hit" not in resumed.call_args.kwargs
    assert resumed.call_args.kwargs["owner_id"] == principal.id
