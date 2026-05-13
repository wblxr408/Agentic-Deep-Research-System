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
        assert state["research_plan"] == []
        assert state["status"] == "pending"
        assert state["revision_count"] == 0

    def test_research_state_has_required_keys(self):
        state = create_initial_state("query")
        required_keys = {
            "task_id", "user_query", "created_at", "research_plan",
            "current_step_index", "search_results", "browser_results",
            "rag_results", "aggregated_evidence", "analysis",
            "reflection_result", "revision_needed", "revision_count",
            "final_report", "citations", "agent_trace", "errors", "status"
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
        assert len(step.step_id) == 8

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
        assert hasattr(graph, "graph")
        assert hasattr(graph, "config")

    def test_graph_has_required_nodes(self):
        graph = compile_research_graph()
        nodes = set(graph.graph.nodes)
        required_nodes = {
            "planner", "search", "browser", "rag",
            "analyst", "reflection", "report"
        }
        assert required_nodes.issubset(nodes)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
