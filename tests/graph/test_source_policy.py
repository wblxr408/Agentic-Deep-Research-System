"""Behavior contract for public research and optional private documents."""

from unittest.mock import MagicMock, patch

import pytest

from app.graph.compiler import (
    dag_executor_node,
    dag_results_aggregator,
    execute_tool_batch,
    planner_node,
    rag_node,
    replan_node,
)
from app.graph.state import DAGDefinition, PlanEdge, PlanNode, RAGResult, StepStatus, create_initial_state, deserialize_dag, serialize_dag


def research_state(*, internal=False):
    state = create_initial_state("分析公开市场的最新趋势", "source-policy-test")
    state["use_internal_docs"] = internal
    state["session"]["owner_id"] = "11111111-1111-4111-8111-111111111111"
    return state


def dispatch(state):
    state.update(dag_executor_node(state))
    return execute_tool_batch(state)


@pytest.mark.parametrize("plan", ["web_only", "unexpected_rag", "rag_only"])
def test_public_research_dispatches_web_without_internal_access(plan):
    state = research_state()
    state["rag_group"] = "private-project"
    nodes = [PlanNode(node_id="s", node_type="search", query="公开市场数据")]
    if plan != "web_only":
        nodes.insert(0, PlanNode(node_id="r", node_type="rag", query="内部资料"))
        nodes[-1].depends_on = ["r"]
    if plan == "rag_only":
        nodes = nodes[:1]
    with patch("app.agents.planner.PlannerAgent.create_dag", return_value=DAGDefinition(dag_name="model", nodes=nodes)):
        state.update(planner_node(state))
    sends = dispatch(state)
    assert {send.node for send in sends} == {"search"}


def test_opt_in_dispatches_internal_documents_alongside_web_with_scope():
    state = research_state(internal=True)
    state["rag_group"] = "project-a"
    with patch("app.agents.planner.PlannerAgent.create_dag", return_value=DAGDefinition(dag_name="web", nodes=[PlanNode(node_id="s", node_type="search", query="公开市场")])):
        state.update(planner_node(state))
    sends = dispatch(state)
    assert {send.node for send in sends} == {"search", "rag"}
    internal = next(send for send in sends if send.node == "rag")
    assert internal.arg["use_internal_docs"] is True
    assert internal.arg["rag_group"] == "project-a"
    assert internal.arg["session"]["owner_id"] == state["session"]["owner_id"]


@pytest.mark.parametrize("results", [[], [{"content": "old background"}]])
def test_internal_results_do_not_skip_search_or_browser(results):
    state = research_state(internal=True)
    state["dag"] = serialize_dag(DAGDefinition(dag_name="supplement", nodes=[
        PlanNode(node_id="r", node_type="rag", query="内部资料", result={"results": results}),
        PlanNode(node_id="s", node_type="search", query="公开数据", depends_on=["r"]),
        PlanNode(node_id="b", node_type="browser", query="https://example.org/report", depends_on=["s"]),
    ], edges=[PlanEdge(from_node="r", to_node="s"), PlanEdge(from_node="s", to_node="b")]))
    state["current_executing_nodes"] = ["r"]
    state["retrieval_policy"] = {"mode": "internal_first", "allow_web_after_rag_hit": False}
    state.update(dag_results_aggregator(state))
    planned = deserialize_dag(state["dag"])
    assert [n.status for n in planned.nodes if n.node_type in {"search", "browser"}] == [StepStatus.PENDING, StepStatus.PENDING]
    assert {send.node for send in dispatch(state)} == {"search"}


@pytest.mark.parametrize("internal", [False, True])
def test_replanning_keeps_the_source_selection(internal):
    state = research_state(internal=internal)
    proposed = DAGDefinition(dag_name="revision", nodes=[PlanNode(node_id="r", node_type="rag", query="内部资料")])
    with patch("app.agents.planner.PlannerAgent.create_dag", return_value=proposed):
        state.update(replan_node(state))
    sends = dispatch(state)
    assert {send.node for send in sends} == ({"search", "rag"} if internal else {"search"})


def test_pending_legacy_plan_cannot_authorize_internal_reads():
    state = research_state()
    state.pop("use_internal_docs", None)
    state["allow_web_after_rag_hit"] = False
    state["retrieval_policy"] = {"mode": "internal_first"}
    state["dag"] = serialize_dag(DAGDefinition(dag_name="legacy", nodes=[
        PlanNode(node_id="r", node_type="rag", query="内部资料"),
        PlanNode(node_id="s", node_type="search", query="公开数据", depends_on=["r"]),
    ], edges=[PlanEdge(from_node="r", to_node="s")]))
    assert {send.node for send in dispatch(state)} == {"search"}


def test_dispatch_rejects_unselected_internal_tool_even_in_model_plan():
    state = research_state()
    state["dag"] = serialize_dag(DAGDefinition(dag_name="untrusted", nodes=[
        PlanNode(node_id="r", node_type="rag", query="内部资料"),
        PlanNode(node_id="s", node_type="search", query="公开数据"),
    ]))
    state["current_executing_nodes"] = ["r", "s"]
    assert {send.node for send in execute_tool_batch(state)} == {"search"}


def test_internal_opt_in_cannot_override_skill_tool_permissions():
    state = research_state(internal=True)
    state["skill_context"] = {"effective_tool_allowlist": ["search"]}
    with patch("app.agents.planner.PlannerAgent.create_dag", return_value=DAGDefinition(dag_name="web", nodes=[PlanNode(node_id="s", node_type="search", query="公开数据")])):
        state.update(planner_node(state))
    assert {send.node for send in dispatch(state)} == {"search"}


@pytest.mark.parametrize("internal", [False, True])
def test_internal_tool_checks_selection_before_access_and_preserves_scope(internal):
    state = research_state(internal=internal)
    state["rag_group"] = "project-a"
    state["dag"] = serialize_dag(DAGDefinition(dag_name="private", nodes=[PlanNode(node_id="r", node_type="rag", query="内部资料")]))
    state["current_executing_nodes"] = ["r"]
    state["user_confirmed"] = True
    with patch("app.agents.rag.RAGAgent.execute_retrieval", return_value=[RAGResult(chunk_id="chunk-1", content="private evidence")]) as retrieve:
        result = rag_node(state)
    if internal:
        assert result["collected_evidence"][0]["content"] == "private evidence"
        assert retrieve.call_args.kwargs == {"group": "project-a", "owner_id": state["session"]["owner_id"]}
    else:
        assert result["collected_evidence"] == []
        retrieve.assert_not_called()
        assert result["node_outcomes"][0]["status"] == "skipped"


@pytest.mark.parametrize("query", ["量子计算是什么", "分析公开市场的最新趋势"])
def test_fact_and_model_failure_plans_keep_public_collection(query):
    from app.agents.planner import PlannerAgent

    agent = PlannerAgent()
    agent._client = MagicMock()
    agent._client.chat.completions.create.side_effect = RuntimeError("provider unavailable")
    with patch("app.agents.planner.create_fallback_llm_client", return_value=None):
        dag = agent.create_dag(query)
    state = research_state()
    state["dag"] = serialize_dag(dag)
    assert {send.node for send in dispatch(state)} == {"search"}


@pytest.mark.parametrize("internal", [False, True])
@pytest.mark.parametrize("max_calls", [1, 2])
def test_parallel_collection_combines_sources_without_sending_private_text_to_search(internal, max_calls):
    from langgraph.graph import END, START, StateGraph
    from app.graph.compiler import search_node
    from app.graph.state import ResearchState, SearchResult

    state = research_state(internal=internal)
    state["rag_group"] = "project-a"
    state["budget_state"] = {"max_tool_calls": max_calls}
    dag = DAGDefinition(dag_name="collection", nodes=[PlanNode(node_id="s", node_type="search", query="public market query")])
    with patch("app.agents.planner.PlannerAgent.create_dag", return_value=dag):
        state.update(planner_node(state))

    graph = StateGraph(ResearchState)
    graph.add_node("dispatch", dag_executor_node)
    graph.add_node("search", search_node)
    graph.add_node("rag", rag_node)
    graph.add_edge(START, "dispatch")
    graph.add_conditional_edges("dispatch", execute_tool_batch)
    graph.add_edge("search", END)
    graph.add_edge("rag", END)
    with patch("app.agents.search.SearchAgent.execute_search", return_value=[SearchResult(url="https://example.org/report", title="Public report", snippet="public evidence")]) as search, patch("app.agents.rag.RAGAgent.execute_retrieval", return_value=[RAGResult(chunk_id="private-1", content="confidential document text")]) as retrieve:
        result = graph.compile().invoke(state)

    evidence = result["collected_evidence"]
    collect_internal = internal and max_calls > 1
    assert len(evidence) == (2 if collect_internal else 1)
    assert any(item["source_type"] == "web" for item in evidence)
    public = next(item for item in evidence if item["source_type"] == "web")
    assert "public evidence" in public["content"]
    if collect_internal:
        assert next(item for item in evidence if item["source_type"] == "knowledge_base")["content"] == "confidential document text"
    assert search.call_args.args[0] == "public market query"
    if collect_internal:
        assert retrieve.call_args.kwargs["owner_id"] == state["session"]["owner_id"]
        assert retrieve.call_args.kwargs["group"] == "project-a"
    else:
        retrieve.assert_not_called()
