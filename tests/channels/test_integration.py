"""User-facing contracts for channel maintenance and research evidence."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.security.auth import Principal, require_principal
from app.channels.models import Attempt, CollectionResult, SourceItem

OWNER = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CHANNELS_STATE_ROOT", str(tmp_path))
    app.dependency_overrides[require_principal] = lambda: Principal(OWNER, "owner", "test")
    yield TestClient(app, headers={"Authorization": "Bearer test"})
    app.dependency_overrides.clear()


def test_owner_can_maintain_priority_then_collect_and_inspect_history(client):
    response = client.put("/api/v1/channels/github/config", json={"backends": ["github-api"], "enabled": False})
    assert response.status_code == 200
    assert response.json()["backends"] == ["github-api"]
    result = client.post("/api/v1/channels/collect", json={"channel": "github", "query": "langgraph"})
    assert result.status_code == 200
    assert result.json()["items"] == []
    assert result.json()["attempts"][0]["error_category"] == "disabled"
    history = client.get("/api/v1/channels/history").json()["items"]
    assert history[-1]["error_category"] == "disabled"
    assert "query" not in history[-1]
    app.dependency_overrides[require_principal] = lambda: Principal("00000000-0000-0000-0000-000000000002", "other", "test")
    assert client.get("/api/v1/channels/history").json()["items"] == []
    github = next(c for c in client.get("/api/v1/channels").json()["items"] if c["name"] == "github")
    assert github["config"]["enabled"] is True


def test_configuration_rejects_shell_backend_and_private_feed(client):
    assert client.put("/api/v1/channels/github/config", json={"backends": ["powershell"]}).status_code == 422
    assert client.put("/api/v1/channels/rss/config", json={"feeds": ["https://127.0.0.1/feed"]}).status_code == 422
    assert client.post("/api/v1/channels/collect", json={"channel": "github", "query": "x", "owner_id": OWNER}).status_code == 422


def test_research_request_preserves_selected_channels_and_rejects_invalid_selection():
    from app.api.research import ResearchRequest
    assert ResearchRequest(query="research question", channels=["github", "rss"]).model_dump()["channels"] == ["github", "rss"]
    for selection in (["shell"], ["github", "github"], ["web", "github", "rss", "v2ex", "twitter", "reddit", "exa", "youtube", "bilibili"]):
        with pytest.raises(ValidationError):
            ResearchRequest(query="research question", channels=selection)


def test_browser_platform_content_keeps_provenance_and_does_not_open_generic_browser():
    from app.agents.browser import BrowserAgent
    item = SourceItem(url="https://www.v2ex.com/t/123", title="Topic", content="Question and replies", channel="v2ex", backend="v2ex-api", collected_at="2026-10-12T00:00:00+00:00")
    with patch("app.channels.ChannelService.collect", return_value=CollectionResult(items=[item], status="success")), patch.object(BrowserAgent, "_async_browse", side_effect=AssertionError("generic browser must not execute")):
        result = BrowserAgent().execute_browse(item.url, owner_id=OWNER)
    assert result[0].extracted_content == item.content
    assert result[0].backend == "v2ex-api"
    assert result[0].citations == [item.url]


def test_search_node_carries_channel_provenance_and_attempts_into_trace():
    from app.graph.compiler import search_node
    from app.graph.state import create_initial_state, DAGDefinition, PlanNode, serialize_dag, SearchResult
    state = create_initial_state("research question", "session-1")
    node = PlanNode(node_type="search", query="research question")
    state["dag"] = serialize_dag(DAGDefinition(dag_name="research", nodes=[node], edges=[]))
    state["executing_nodes"] = [node.node_id]
    state["session"]["channels"] = ["github"]
    state["session"]["owner_id"] = OWNER
    def collect(agent, query, **kwargs):
        assert kwargs["channels"] == ["github"] and kwargs["owner_id"] == OWNER
        agent.last_channel_attempts = [Attempt(channel="github", backend="gh", status="failed", error_category="dependency_missing").model_dump(), Attempt(channel="github", backend="github-api", status="success", result_count=1).model_dump()]
        return [SearchResult(url="https://github.com/a/b", title="Repo", snippet="Evidence", channel="github", backend="github-api", collected_at="2026-10-12T00:00:00+00:00")]
    with patch("app.agents.search.SearchAgent.execute_search", collect):
        result = search_node(state)
    assert result["collected_evidence"][0]["source_channel"] == "github"
    assert result["collected_evidence"][0]["source_backend"] == "github-api"
    assert any(event.get("channel_attempts") for event in result["agent_trace"])


def test_channel_auth_failure_is_terminal_in_workflow_without_false_success():
    from app.graph.compiler import search_node
    from app.graph.state import create_initial_state, DAGDefinition, PlanNode, serialize_dag
    state = create_initial_state("research question", "session-1")
    node = PlanNode(node_type="search", query="twitter: research")
    state["dag"] = serialize_dag(DAGDefinition(dag_name="research", nodes=[node], edges=[]))
    state["executing_nodes"] = [node.node_id]
    def collect(agent, query, **kwargs):
        agent.last_channel_attempts = [Attempt(channel="twitter", backend="twitter", status="failed", error_category="auth_required").model_dump()]
        return []
    with patch("app.agents.search.SearchAgent.execute_search", collect):
        result = search_node(state)
    assert result["collected_evidence"] == []
    assert result["node_outcomes"][0]["status"] == "terminal_error"
    assert result["node_outcomes"][0]["error_category"] == "auth_required"


def test_workflow_budget_counts_channel_transport_calls_and_stops_following_nodes():
    from app.graph.compiler import search_node, _build_budget_state
    from app.graph.state import create_initial_state, DAGDefinition, PlanNode, serialize_dag, SearchResult
    state = create_initial_state("research question", "session-1")
    nodes = [PlanNode(node_type="search", query="research one"), PlanNode(node_type="search", query="research two")]
    state["dag"] = serialize_dag(DAGDefinition(dag_name="research", nodes=nodes, edges=[]))
    state["executing_nodes"] = [n.node_id for n in nodes]
    state["session"]["channels"] = ["github"]
    state["budget_state"] = {"max_tool_calls": 2}
    calls = []
    def collect(agent, query, **kwargs):
        calls.append(query)
        assert kwargs["max_calls"] == 2
        agent.last_channel_attempts = [Attempt(channel="github", backend="gh", status="failed", error_category="dependency_missing", call_count=1).model_dump(), Attempt(channel="github", backend="github-api", status="success", result_count=1, call_count=1).model_dump()]
        return [SearchResult(url="https://github.com/a/b", title="Repo", snippet="Evidence", channel="github", backend="github-api")]
    with patch("app.agents.search.SearchAgent.execute_search", collect):
        result = search_node(state)
    assert len(calls) == 1
    state["tool_histories"] = result["tool_histories"]
    assert _build_budget_state(state)["used_tool_calls"] == 2


def test_parallel_dispatch_shares_remaining_call_budget_and_keeps_source_selection():
    from app.graph.compiler import execute_tool_batch
    from app.graph.state import create_initial_state, DAGDefinition, PlanNode, serialize_dag
    state = create_initial_state("research question", "session-1")
    nodes = [PlanNode(node_type="search", query="research one"), PlanNode(node_type="browser", query="https://www.v2ex.com/t/123")]
    state["dag"] = serialize_dag(DAGDefinition(dag_name="research", nodes=nodes, edges=[]))
    state["current_executing_nodes"] = [n.node_id for n in nodes]
    state["session"]["channels"] = ["github"]
    state["budget_state"] = {"max_tool_calls": 5}
    state["tool_histories"] = [{"tool_calls": [{"status": "success"}]}]
    sends = execute_tool_batch(state)
    assert len(sends) == 2
    assert sum(send.arg["channel_call_allowance"] for send in sends) == 4
    assert all(send.arg["session"]["channels"] == ["github"] for send in sends)
    assert all(send.arg["budget_state"]["max_tool_calls"] == 5 for send in sends)


def test_parallel_graph_delivers_repository_and_topic_evidence_with_disjoint_budgets(tmp_path, monkeypatch):
    from langgraph.graph import StateGraph, START, END
    from app.graph.compiler import execute_tool_batch, search_node, browser_node, _build_budget_state
    from app.graph.state import ResearchState, create_initial_state, DAGDefinition, PlanNode, serialize_dag
    from app.channels.execution import CommandRunner, HttpReader
    import json
    monkeypatch.setenv("CHANNELS_STATE_ROOT", str(tmp_path))
    def command(*args, **kwargs):
        from app.channels.models import ChannelError
        raise ChannelError("dependency_missing")
    def read(self, url, **kwargs):
        if "search/repositories" in url:
            return json.dumps({"items": [{"html_url": "https://github.com/a/b", "name": "Repository", "description": "Repository evidence"}]})
        if "topics/show" in url:
            return json.dumps([{"url": "https://www.v2ex.com/t/123", "title": "Topic", "content": "Topic evidence"}])
        return json.dumps([{"content": "Reply evidence"}])
    monkeypatch.setattr(CommandRunner, "run", command)
    monkeypatch.setattr(HttpReader, "get", read)
    state = create_initial_state("research question", "session-1")
    nodes = [PlanNode(node_type="search", query="research one"), PlanNode(node_type="browser", query="https://www.v2ex.com/t/123")]
    state["dag"] = serialize_dag(DAGDefinition(dag_name="research", nodes=nodes, edges=[]))
    state["current_executing_nodes"] = [n.node_id for n in nodes]
    state["session"].update({"channels": ["github"], "owner_id": OWNER})
    state["budget_state"] = {"max_tool_calls": 4}
    graph = StateGraph(ResearchState)
    graph.add_node("dispatch", lambda value: {})
    graph.add_node("search", search_node)
    graph.add_node("browser", browser_node)
    graph.add_edge(START, "dispatch")
    graph.add_conditional_edges("dispatch", execute_tool_batch)
    graph.add_edge("search", END)
    graph.add_edge("browser", END)
    result = graph.compile().invoke(state)
    assert {e["source_channel"] for e in result["collected_evidence"]} == {"github", "v2ex"}
    assert any("Reply evidence" in e["content"] for e in result["collected_evidence"])
    assert _build_budget_state(result)["used_tool_calls"] == 4


@pytest.mark.asyncio
async def test_workflow_checkpoint_keeps_authenticated_owner_and_selection(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    from types import SimpleNamespace
    from app.api import research
    captured = []
    class Graph:
        async def astream(self, state, config):
            captured.append(state["session"].copy())
            if False:
                yield {}
    persistence = SimpleNamespace(persist_runtime_snapshot=AsyncMock())
    sse = SimpleNamespace(publish=AsyncMock())
    settings = SimpleNamespace(harness=SimpleNamespace(state_root="unused", worker_id="test"))
    monkeypatch.setattr(research, "compile_research_graph", lambda: Graph())
    monkeypatch.setattr(research, "get_settings", lambda: settings)
    monkeypatch.setattr(research, "get_sse_manager", lambda: sse)
    monkeypatch.setattr(research, "RuntimePersistence", lambda: persistence)
    monkeypatch.setattr(research, "HarnessSupervisor", lambda *args: MagicMock())
    await research.run_research_workflow("session-1", "research question", channels=["github", "rss"], owner_id=OWNER)
    assert captured[0]["channels"] == ["github", "rss"]
    assert captured[0]["owner_id"] == OWNER
    snapshot = persistence.persist_runtime_snapshot.call_args_list[0].kwargs["state"]
    assert snapshot["session"]["channels"] == ["github", "rss"]
