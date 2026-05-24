"""
Tests for the research graph workflow.
"""

import pytest
from app.graph.state import ResearchState, create_initial_state, StepStatus, PlanStep
from app.graph.compiler import compile_research_graph, should_revise


class TestResearchState:
    def test_create_initial_state(self):
        state = create_initial_state("测试研究查询", "test-123")
        assert state["task_id"] == "test-123"
        assert state["user_query"] == "测试研究查询"
        assert state["status"] == "pending"
        assert state["revision_count"] == 0
        assert state["search_results"] == []

    def test_research_state_has_required_keys(self):
        state = create_initial_state("query")
        required_keys = {
            "task_id", "user_query", "created_at", "status", "session",
            "dag", "current_executing_nodes", "completed_nodes",
            "tool_histories", "collected_evidence", "verification",
            "search_results", "browser_results", "rag_results", "aggregated_evidence",
            "revision_needed", "revision_count", "analysis",
            "final_report", "citations", "guardrail_decision", "evidence_status",
            "review_status", "user_confirmed", "allow_web_after_rag_hit", "rag_group",
            "retrieval_policy", "agent_trace", "guardrail_trace", "errors"
        }
        assert set(state.keys()) == required_keys


class TestPlanStep:
    def test_plan_step_defaults(self):
        step = PlanStep(
            description="搜索市场数据",
            assigned_agent="search",
            target_query="2025年中国AI市场"
        )
        assert step.status == StepStatus.PENDING
        assert step.retry_count == 0
        assert step.evidence_ids == []
        assert len(step.step_id) == 7

    def test_plan_step_serialization(self):
        step = PlanStep(
            description="深度阅读文章",
            assigned_agent="browser",
            target_query="AI发展趋势"
        )
        data = step.model_dump()
        assert isinstance(data, dict)
        assert data["description"] == "深度阅读文章"
        assert data["assigned_agent"] == "browser"


class TestConditionalRouting:
    def test_should_revise_under_limit(self):
        state = {
            "revision_needed": True,
            "revision_count": 2,
        }
        assert should_revise(state) == "replan"

    def test_should_revise_at_limit(self):
        state = {
            "revision_needed": True,
            "revision_count": 3,
        }
        assert should_revise(state) == "generate_report"

    def test_should_not_revise(self):
        state = {
            "revision_needed": False,
            "revision_count": 0,
        }
        assert should_revise(state) == "generate_report"


class TestGraphCompilation:
    def test_compile_research_graph(self):
        graph = compile_research_graph()
        assert graph is not None
        # Verify it's a compiled graph
        assert hasattr(graph, "builder")
        assert hasattr(graph, "config")

    def test_graph_has_required_nodes(self):
        graph = compile_research_graph()
        nodes = set(graph.builder.nodes)
        required_nodes = {
            "planner", "search", "browser", "rag",
            "analyst", "reflection", "report"
        }
        assert required_nodes.issubset(nodes)

    def test_search_node_returns_tool_history(self):
        from unittest.mock import patch

        from app.graph.compiler import search_node
        from app.graph.state import AgentType, DAGDefinition, PlanNode, SearchResult, serialize_dag

        node = PlanNode(node_type="search", query="test query")
        state = create_initial_state("test query", "session-1")
        state["dag"] = serialize_dag(DAGDefinition(dag_name="test", nodes=[node], edges=[]))
        state["executing_nodes"] = [node.node_id]

        with patch("app.agents.search.SearchAgent.execute_search", return_value=[
            SearchResult(
                url="https://example.com",
                title="Example",
                snippet="Example snippet",
                relevance_score=0.9,
            )
        ]):
            result = search_node(state)

        assert len(result["tool_histories"]) == 1
        history = result["tool_histories"][0]
        assert history["agent_type"] == AgentType.SEARCH.value
        assert history["tool_calls"][0]["status"] == "success"
        assert "dag" not in result

    def test_search_node_handles_tool_error(self):
        from unittest.mock import patch

        from app.graph.compiler import search_node
        from app.graph.state import DAGDefinition, PlanNode, serialize_dag, deserialize_dag

        node = PlanNode(node_type="search", query="test query")
        state = create_initial_state("test query", "session-1")
        state["dag"] = serialize_dag(DAGDefinition(dag_name="test", nodes=[node], edges=[]))
        state["executing_nodes"] = [node.node_id]

        with patch("app.agents.search.SearchAgent.execute_search", side_effect=RuntimeError("boom")):
            result = search_node(state)

        assert len(result["tool_histories"]) == 1
        assert result["tool_histories"][0]["tool_calls"][0]["status"] == "error"

    def test_search_node_returns_tool_trace_events(self):
        from unittest.mock import patch

        from app.graph.compiler import search_node
        from app.graph.state import DAGDefinition, PlanNode, serialize_dag, deserialize_dag

        node = PlanNode(node_type="search", query="test query")
        state = create_initial_state("test query", "session-1")
        state["dag"] = serialize_dag(DAGDefinition(dag_name="test", nodes=[node], edges=[]))
        state["executing_nodes"] = [node.node_id]

        with patch("app.agents.search.SearchAgent.execute_search", return_value=[]):
            result = search_node(state)

        event_types = [event["event_type"] for event in result["agent_trace"]]
        assert "tool_start" in event_types
        assert "tool_error" in event_types

    def test_execute_tool_batch_includes_dag_payload(self):
        from app.graph.compiler import execute_tool_batch
        from app.graph.state import DAGDefinition, PlanNode, serialize_dag, deserialize_dag

        node = PlanNode(node_type="search", query="test query")
        state = create_initial_state("test query", "session-1")
        state["dag"] = serialize_dag(DAGDefinition(dag_name="test", nodes=[node], edges=[]))
        state["current_executing_nodes"] = [node.node_id]
        state["guardrail_decision"] = {"enabled_tools": ["search"]}

        sends = execute_tool_batch(state)

        assert len(sends) == 1
        payload = sends[0].arg
        assert "dag" in payload
        assert payload["executing_nodes"] == [node.node_id]

    def test_planner_enforces_internal_rag_before_search(self):
        from unittest.mock import patch

        from app.graph.compiler import planner_node
        from app.graph.state import DAGDefinition, PlanNode, serialize_dag, deserialize_dag

        search_node_only = PlanNode(node_id="s1", node_type="search", query="test query")
        dag = DAGDefinition(dag_name="test", nodes=[search_node_only], edges=[])
        state = create_initial_state("test query", "session-1")

        with patch("app.agents.planner.PlannerAgent.create_dag", return_value=dag):
            result = planner_node(state)

        planned = deserialize_dag(result["dag"])
        rag_nodes = [node for node in planned.nodes if node.node_type == "rag"]
        search_nodes = [node for node in planned.nodes if node.node_type == "search"]

        assert rag_nodes
        assert search_nodes[0].depends_on == [rag_nodes[0].node_id]

    def test_dag_aggregator_skips_web_after_rag_hit_by_default(self):
        from app.graph.compiler import dag_results_aggregator
        from app.graph.state import DAGDefinition, PlanNode, serialize_dag, deserialize_dag

        rag = PlanNode(node_id="r1", node_type="rag", query="internal")
        search = PlanNode(node_id="s1", node_type="search", query="web", depends_on=["r1"])
        rag.result = {"results": [{"content": "internal evidence"}]}
        state = create_initial_state("test query", "session-1")
        state["dag"] = serialize_dag(DAGDefinition(dag_name="test", nodes=[rag, search], edges=[]))
        state["current_executing_nodes"] = ["r1"]
        state["retrieval_policy"] = {"allow_web_after_rag_hit": False}

        result = dag_results_aggregator(state)
        planned = deserialize_dag(result["dag"])
        skipped = next(node for node in planned.nodes if node.node_id == "s1")

        assert skipped.status == StepStatus.SKIPPED
        assert "s1" in result["completed_nodes"]
        assert result["retrieval_policy"]["web_search_required"] is False

    def test_dag_aggregator_allows_web_when_rag_empty(self):
        from app.graph.compiler import dag_results_aggregator
        from app.graph.state import DAGDefinition, PlanNode, serialize_dag, deserialize_dag

        rag = PlanNode(node_id="r1", node_type="rag", query="internal")
        search = PlanNode(node_id="s1", node_type="search", query="web", depends_on=["r1"])
        rag.result = {"results": []}
        state = create_initial_state("test query", "session-1")
        state["dag"] = serialize_dag(DAGDefinition(dag_name="test", nodes=[rag, search], edges=[]))
        state["current_executing_nodes"] = ["r1"]
        state["retrieval_policy"] = {"allow_web_after_rag_hit": False}

        result = dag_results_aggregator(state)
        planned = deserialize_dag(result["dag"])
        web = next(node for node in planned.nodes if node.node_id == "s1")

        assert web.status == StepStatus.PENDING
        assert result["retrieval_policy"]["web_search_required"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
