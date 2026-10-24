"""Only the six currently requested defect contracts; never a suite runner."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import asyncio
import json
from datetime import datetime
from contextlib import asynccontextmanager
from copy import deepcopy
from fastapi import BackgroundTasks, HTTPException

import pytest


class MemoryDatabase:
    """External PostgreSQL adapter with atomic insert and row-lock semantics."""
    def __init__(self):
        self.sessions = {}
        self.approvals = {}
        self.credential_valid = True
        self.lock = asyncio.Lock()

    @asynccontextmanager
    async def acquire(self):
        yield self

    @asynccontextmanager
    async def transaction(self):
        async with self.lock:
            yield

    def _insert(self, args, *, overwrite):
        exists = args[0] in self.sessions
        if not exists or overwrite:
            self.sessions[args[0]] = {"id": args[0], "user_query": args[1], "status": args[2], "owner_id": args[11], "review_status": {"requires_confirmation": args[2] == "pending"}, "request_payload": args[13] if len(args) > 13 else None}
        return None if exists and not overwrite else self.sessions[args[0]]

    async def execute(self, sql, *args):
        if "INSERT INTO research_sessions" in sql:
            self._insert(args, overwrite="DO UPDATE" in sql)
        elif "UPDATE approval_requests" in sql:
            self.approvals[args[4]]["status"] = args[0]
        elif "UPDATE research_sessions SET status = 'running'" in sql:
            row = self.sessions[args[0]]
            row["status"] = "running"
            row["execution_id"] = args[2]
        elif "INSERT INTO session_runtime_state" in sql:
            self.sessions[args[0]]["state_snapshot_json"] = json.loads(args[11])
        elif "UPDATE research_sessions" in sql and "SET status = $1" in sql:
            self.sessions[args[-1]]["status"] = args[0]
        return "UPDATE 1"

    async def fetchrow(self, sql, *args):
        if "INSERT INTO research_sessions" in sql:
            return self._insert(args, overwrite=False)
        if "FROM auth_sessions" in sql or "FROM auth_api_tokens" in sql:
            return {"id": OWNER, "username": "owner"} if self.credential_valid else None
        if "FROM approval_requests" in sql:
            return deepcopy(self.approvals.get(args[0]))
        if "FROM research_sessions" in sql:
            row = self.sessions.get(args[0])
            return deepcopy(row) if row and (len(args) == 1 or row["owner_id"] == args[1]) else None
        return None

    async def fetchval(self, sql, *args):
        if "auth_sessions" in sql or "auth_api_tokens" in sql:
            return self.credential_valid
        row = self.sessions.get(args[0])
        if "execution_id" in sql:
            return bool(row and row.get("execution_id") == args[1])
        return bool(row and row["owner_id"] == args[1])

    async def fetch(self, sql, *args):
        return [deepcopy(a) for a in self.approvals.values() if a["session_id"] == args[0]]

    async def executemany(self, sql, rows):
        if "INSERT INTO approval_requests" in sql:
            for row in rows:
                if not isinstance(row[8], datetime):
                    raise TypeError("PostgreSQL TIMESTAMP requires datetime")
                self.approvals[row[0]] = {"approval_id": row[0], "session_id": row[1], "node_id": row[2], "tool_name": row[3], "request_payload_json": json.loads(row[6]), "status": row[7]}
        if "INSERT INTO tool_call_audit" in sql:
            for row in rows:
                if any(value is not None and not isinstance(value, datetime) for value in row[-2:]):
                    raise TypeError("PostgreSQL TIMESTAMP requires datetime")


OWNER = "00000000-0000-0000-0000-000000000001"
SESSION = "00000000-0000-0000-0000-000000000002"


@pytest.mark.asyncio
async def test_duplicate_session_starts_one_business_execution(monkeypatch):
    import app.api.research as module
    from app.security.auth import Principal
    db = MemoryDatabase()
    monkeypatch.setattr(module, "get_db_pool", AsyncMock(return_value=db))
    registry = SimpleNamespace(resolve_for_session=AsyncMock(return_value=SimpleNamespace(as_dict=lambda: {})))
    monkeypatch.setattr(module, "get_skill_registry", lambda *a: registry)
    request = module.ResearchRequest(query="public research", session_id=SESSION)
    background = [BackgroundTasks(), BackgroundTasks()]
    results = await asyncio.gather(*(module.create_research(request, bg, Principal(OWNER, "owner", "session")) for bg in background), return_exceptions=True)
    assert sum(len(bg.tasks) for bg in background) == 1
    assert sum(isinstance(r, HTTPException) and r.status_code == 409 for r in results) == 1
    assert db.sessions[SESSION]["user_query"] == request.query


@pytest.mark.asyncio
async def test_revoked_credential_stops_established_stream(monkeypatch):
    import app.api.research as module
    import app.security.auth as auth
    from app.observability.sse_manager import SSEManager
    db = MemoryDatabase()
    db.sessions[SESSION] = {"owner_id": OWNER}
    monkeypatch.setattr(module, "get_db_pool", AsyncMock(return_value=db))
    monkeypatch.setattr(auth, "get_db_pool", AsyncMock(return_value=db))
    sse = SSEManager()
    monkeypatch.setattr(module, "get_sse_manager", lambda: sse)
    principal = await auth._principal_from_token("test-token", "session")
    response = await module.stream_research(SESSION, principal)
    stream = response.body_iterator
    await anext(stream)
    db.credential_valid = False
    await sse.publish(SESSION, "report_chunk", {"chunk": "PRIVATE REPORT"})
    delivered = []
    try:
        for _ in range(3):
            delivered.append(await asyncio.wait_for(anext(stream), 2))
    except StopAsyncIteration:
        pass
    finally:
        await stream.aclose()
    assert not any(event.get("event") == "report_chunk" for event in delivered)


@pytest.mark.asyncio
async def test_private_redirect_and_dns_resource_are_blocked_by_pinned_browser_transport(monkeypatch):
    import app.channels.execution as transport
    from app.tools.public_browser import PublicBrowserGateway
    targets = []
    monkeypatch.setattr(transport.socket, "getaddrinfo", lambda host, *a, **k: [(2, 1, 6, "", ("127.0.0.1" if host == "rebind.example" else "93.184.216.34", 443))])
    class Redirect:
        status = 302
        def getheader(self, key, default=None):
            return "https://127.0.0.1/private" if key == "Location" else default
    class Connection:
        def __init__(self, host, address, timeout):
            targets.append((host, address))
        def request(self, *a, **k):
            pass
        def getresponse(self):
            return Redirect()
        def close(self):
            pass
    monkeypatch.setattr(transport, "_PinnedHTTPS", Connection)
    gateway = PublicBrowserGateway()
    for url in ["https://public.example/redirect", "https://rebind.example/secret"]:
        route = SimpleNamespace(request=SimpleNamespace(url=url, method="GET"), abort=AsyncMock(), fulfill=AsyncMock())
        await gateway.route(route)
        assert route.abort.await_count == 1
        assert route.fulfill.await_count == 0
    assert targets == [("public.example", "93.184.216.34")]


@pytest.mark.asyncio
async def test_mcp_pending_action_is_bound_to_resume_node(monkeypatch):
    import app.graph.compiler as compiler
    import app.governance.mcp as mcp
    from app.graph.approval import resume_approved_state
    from app.graph.state import DAGDefinition, PlanNode, create_initial_state, serialize_dag
    db = MemoryDatabase()
    registry = {"server_id": "internal", "trust_status": "trusted", "allowed_tools_json": ["publish"], "read_only_default": False, "secret_policy_json": {}, "fingerprint": "registry-v1"}
    original_fetch = db.fetchrow
    async def fetch(sql, *args):
        if "FROM mcp_server_registry" in sql:
            return registry
        return await original_fetch(sql, *args)
    monkeypatch.setattr(db, "fetchrow", fetch)
    monkeypatch.setattr(mcp, "get_db_pool", AsyncMock(return_value=db))
    state = create_initial_state("public research", SESSION)
    state["session"]["owner_id"] = OWNER
    state["skill_context"] = {"effective_tool_allowlist": ["mcp"]}
    state["current_executing_nodes"] = ["mcp-1"]
    state["executing_nodes"] = ["mcp-1"]
    state["dag"] = serialize_dag(DAGDefinition(dag_name="MCP approval", nodes=[PlanNode(node_id="mcp-1", node_type="mcp", query="internal:publish")]))
    outcome = await compiler.mcp_node(state)
    approval = outcome["pending_approvals"][0]
    assert approval["node_id"] == "mcp-1"
    merged = {**state, **outcome}
    merged.update(compiler.dag_results_aggregator(merged))
    merged["runtime_status"] = "awaiting_approval"
    resumed = resume_approved_state(merged, {approval["approval_id"]: {**approval, "status": "approved"}}, owner_id=OWNER, session_id=SESSION)
    db.sessions[SESSION] = {"owner_id": OWNER}
    db.approvals[approval["approval_id"]] = {**approval, "session_id": SESSION, "status": "approved", "request_payload_json": approval["request_payload"]}
    final = await compiler.mcp_node(resumed)
    assert not final.get("pending_approvals")
    assert final["node_outcomes"][0]["error_category"] == "unsupported_input"


@pytest.mark.asyncio
async def test_mcp_approval_cannot_authorize_changed_arguments(monkeypatch):
    import app.governance.mcp as mcp
    db = MemoryDatabase()
    registry = {"server_id": "internal", "trust_status": "trusted", "allowed_tools_json": ["publish"], "read_only_default": False, "secret_policy_json": {}, "fingerprint": "registry-v1"}
    original_fetch = db.fetchrow
    async def fetch(sql, *args):
        if "FROM mcp_server_registry" in sql:
            return registry
        return await original_fetch(sql, *args)
    monkeypatch.setattr(db, "fetchrow", fetch)
    monkeypatch.setattr(mcp, "get_db_pool", AsyncMock(return_value=db))
    executor = AsyncMock(return_value={"published": True})
    proxy = mcp.McpPolicyProxy(executor=executor)
    pending = await proxy.invoke(mcp.McpToolRequest(SESSION, None, "publish", {"query": "original action"}, "internal", owner_id=OWNER, node_id="mcp-1"))
    approval = pending.approval_request
    db.sessions[SESSION] = {"owner_id": OWNER}
    db.approvals[approval["approval_id"]] = {**approval, "session_id": SESSION, "status": "approved", "request_payload_json": approval["request_payload"]}
    changed = await proxy.invoke(mcp.McpToolRequest(SESSION, None, "publish", {"query": "changed action"}, "internal", approval_id=approval["approval_id"], owner_id=OWNER, node_id="mcp-1"))
    assert executor.await_count == 0
    assert changed.status == "terminal_error"


@pytest.mark.asyncio
async def test_paused_worker_saves_complete_source_and_authority_context(monkeypatch, tmp_path):
    import app.api.research as module
    import app.graph.compiler as compiler
    import app.governance.runtime as runtime
    from app.agents.planner import PlannerAgent
    from app.graph.state import DAGDefinition, PlanNode
    db = MemoryDatabase()
    db.sessions[SESSION] = {"owner_id": OWNER, "status": "running", "execution_id": None}
    monkeypatch.setattr(module, "get_db_pool", AsyncMock(return_value=db))
    monkeypatch.setattr(runtime, "get_db_pool", AsyncMock(return_value=db))
    settings = module.get_settings()
    settings.harness = SimpleNamespace(state_root=str(tmp_path), worker_id="test")
    settings.redis.url = None
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(compiler, "get_settings", lambda: settings)
    monkeypatch.setattr(PlannerAgent, "create_dag", lambda *a, **k: DAGDefinition(dag_name="Paused research", nodes=[PlanNode(node_id="search-1", node_type="search", query="public research")]))
    monkeypatch.setattr(compiler, "should_require_action_approval", lambda **k: (True, "approve_read"))
    saved = []
    class Persistence:
        def __init__(self):
            self.real = runtime.RuntimePersistence()
        async def persist_runtime_snapshot(self, **kwargs):
            saved.append(deepcopy(kwargs["state"]))
            return await self.real.persist_runtime_snapshot(**kwargs)
    monkeypatch.setattr(module, "RuntimePersistence", Persistence)
    await module.run_research_workflow(SESSION, "public research", use_internal_docs=True, rag_group="internal", owner_id=OWNER, skill_context={"effective_tool_allowlist": ["search"]})
    paused = next((s for s in reversed(saved) if s.get("runtime_status") == "awaiting_approval"), {})
    assert paused.get("user_query") == "public research"
    assert paused["use_internal_docs"] is True
    assert paused["rag_group"] == "internal"
    assert paused["session"]["owner_id"] == OWNER
    assert paused["skill_context"]["effective_tool_allowlist"] == ["search"]
    assert db.sessions[SESSION]["status"] == "paused"
    assert db.sessions[SESSION]["state_snapshot_json"]["user_query"] == "public research"


@pytest.mark.asyncio
async def test_approval_dispatch_preserves_state_and_continues_bound_action(monkeypatch, tmp_path):
    import app.api.research as module
    import app.graph.compiler as compiler
    from app.security.auth import Principal
    from app.agents.planner import PlannerAgent
    from app.agents.search import SearchAgent
    from app.agents.reflection import ReflectionAgent
    from app.graph.state import DAGDefinition, PlanNode, VerificationResult, create_initial_state, serialize_dag
    db = MemoryDatabase()
    state = create_initial_state("original public research", SESSION)
    state["session"]["owner_id"] = OWNER
    state["session"]["max_revisions"] = 0
    state["use_internal_docs"] = True
    state["rag_group"] = "internal"
    state["skill_context"] = {"effective_tool_allowlist": ["search"]}
    state["runtime_status"] = "awaiting_approval"
    state["status"] = "paused"
    state["budget_state"] = {"used_total_tokens": 120, "used_tool_calls": 7, "max_tool_calls": 15}
    state["dag"] = serialize_dag(DAGDefinition(dag_name="Approved research", nodes=[PlanNode(node_id="search-1", node_type="search", query="original public research", waiting_approval=True)]))
    approval = {"approval_id": "ap-1", "node_id": "search-1", "tool_name": "duckduckgo_search", "request_payload": {"query": "original public research"}, "status": "pending"}
    state["pending_approvals"] = [approval]
    db.approvals["ap-1"] = {**approval, "session_id": SESSION, "request_payload_json": approval["request_payload"]}
    db.sessions[SESSION] = {"owner_id": OWNER, "status": "paused", "state_snapshot_json": state, "execution_id": None}
    settings = module.get_settings()
    settings.harness = SimpleNamespace(state_root=str(tmp_path), worker_id="test")
    settings.redis.url = None
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(compiler, "get_settings", lambda: settings)
    monkeypatch.setattr(module, "get_db_pool", AsyncMock(return_value=db))
    module.HarnessSupervisor(str(tmp_path)).upsert_task(session_id=SESSION, public_status="paused", runtime_status="awaiting_approval", budget=state["budget_state"], state_snapshot=state)
    worker = module.run_research_workflow
    dispatched = AsyncMock()
    monkeypatch.setattr(module, "run_research_workflow", dispatched)
    result = await module.resolve_research_approval(SESSION, "ap-1", module.ApprovalActionRequest(action="approve", approved_by="client label"), Principal(OWNER, "owner", "session"))
    await asyncio.sleep(0)
    assert result["status"] == "approved"
    resumed = dispatched.call_args.kwargs
    assert resumed.get("resume_state", {}).get("budget_state", {}).get("used_tool_calls") == 7
    assert resumed["resume_state"]["user_query"] == "original public research"
    assert resumed["resume_state"]["skill_context"] == state["skill_context"]
    monkeypatch.setattr(PlannerAgent, "create_dag", lambda *a, **k: pytest.fail("resume restarted planner"))
    search = MagicMock(return_value=[])
    monkeypatch.setattr(SearchAgent, "execute_search", search)
    monkeypatch.setattr(ReflectionAgent, "reflect", lambda *a, **k: VerificationResult(needs_revision=False))
    monkeypatch.setattr(compiler, "should_require_action_approval", lambda **k: (True, "approve_read"))
    saved = []
    class Persistence:
        async def persist_runtime_snapshot(self, **kwargs):
            saved.append(deepcopy(kwargs["state"]))
    monkeypatch.setattr(module, "RuntimePersistence", Persistence)
    await worker(**resumed)
    assert search.call_count == 1
    assert saved[-1]["status"] == "completed"
    assert not saved[-1]["pending_approvals"]
    assert saved[-1]["budget_state"]["used_tool_calls"] >= 7


@pytest.mark.asyncio
async def test_private_browser_target_never_becomes_evidence(monkeypatch):
    from app.agents.browser import BrowserAgent
    agent = BrowserAgent()
    page = MagicMock()
    page.goto = AsyncMock(return_value=SimpleNamespace(status=200))
    page.title = AsyncMock(return_value="Private service")
    page.close = AsyncMock()
    browser = MagicMock()
    browser.new_page = AsyncMock(return_value=page)
    monkeypatch.setattr(agent, "_ensure_browser", AsyncMock(return_value=browser))
    monkeypatch.setattr(agent, "_classify_page", AsyncMock(return_value="general"))
    monkeypatch.setattr(agent._scroller, "auto_scroll", AsyncMock(return_value={"scroll_count": 0, "reached_bottom": True}))
    monkeypatch.setattr(agent, "_extract_deep", AsyncMock(return_value="PRIVATE SECRET"))
    monkeypatch.setattr(agent._extractor, "extract_all", AsyncMock(return_value={}))
    monkeypatch.setattr(agent._analyzer, "analyze_and_plan", AsyncMock(return_value={}))
    result = await agent.open_and_browse("https://127.0.0.1/admin", "read page")
    assert "PRIVATE SECRET" not in result.extracted_content
    assert page.goto.await_count == 0
    assert result.error_message


@pytest.mark.asyncio
async def test_real_rag_hit_delivers_body_and_structured_citation(monkeypatch):
    import app.agents.rag as module
    from app.graph.state import PlanNode
    row = {"id": "doc-1", "content": "Internal evidence", "metadata": {"title": "Internal memo", "url": "https://example.com/memo"}, "similarity": 0.9, "bm25_score": 0.7}
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[row])
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    agent = module.RAGAgent()
    monkeypatch.setattr(agent, "_get_db_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(agent, "_get_embedder", AsyncMock(return_value=SimpleNamespace(embed=AsyncMock(return_value=[0.1]))))
    monkeypatch.setattr(agent, "_get_reranker", AsyncMock(return_value=SimpleNamespace(rerank=AsyncMock(return_value=[0.8]))))
    async def capability(name, operation):
        return await operation()
    monkeypatch.setattr(module.capability_registry, "run", capability)
    monkeypatch.setattr(module, "get_text_search_config", AsyncMock(return_value="english"))
    results = await agent.execute_async([PlanNode(node_id="rag-1", node_type="rag", target_query="memo")], "memo", owner_id="00000000-0000-0000-0000-000000000001")
    assert len(results) == 1
    delivered = results[0].model_dump()
    assert delivered["content"] == "Internal evidence"
    assert delivered["citation"]["source_title"] == "Internal memo"
    assert delivered["chunk_id"] == "doc-1"


@pytest.mark.asyncio
async def test_real_graph_all_tools_denied_delivers_restricted_report(monkeypatch):
    import app.graph.compiler as module
    from app.agents.planner import PlannerAgent
    from app.agents.reflection import ReflectionAgent
    from app.graph.state import DAGDefinition, PlanNode, VerificationResult, create_initial_state
    monkeypatch.setattr(module.get_settings().redis, "url", None)
    dag = DAGDefinition(dag_name="Denied research", nodes=[PlanNode(node_id="search-1", node_type="search", query="public sources")])
    monkeypatch.setattr(PlannerAgent, "create_dag", lambda *a, **k: dag.model_copy(deep=True))
    monkeypatch.setattr(ReflectionAgent, "reflect", lambda *a, **k: VerificationResult(needs_revision=False))
    state = create_initial_state("public sources", "denied-tools")
    state["skill_context"] = {"effective_tool_allowlist": ["rag"]}
    state["use_internal_docs"] = False
    state["session"]["max_revisions"] = 0
    final = await module.compile_research_graph().ainvoke(state, {"configurable": {"thread_id": "denied-tools"}})
    assert final.get("final_report")
    assert final["status"] == "completed"
    assert final["review_status"]["blocked"] is True
    assert not final["tool_histories"]
