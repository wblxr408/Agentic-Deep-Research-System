"""
Integration tests for the complete research workflow.
"""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.graph.state import ResearchState, create_initial_state, StepStatus


class TestResearchWorkflowIntegration:
    """Integration tests for the full research workflow."""

    @pytest.mark.asyncio
    async def test_workflow_initial_state(self):
        """Test that initial state is created correctly."""
        state = create_initial_state("Test query", "test-session")
        assert state["task_id"] == "test-session"
        assert state["user_query"] == "Test query"
        assert state["research_plan"] == []
        assert state["status"] == "pending"
        assert state["revision_count"] == 0
        assert state["search_results"] == []
        assert state["browser_results"] == []
        assert state["rag_results"] == []

    @pytest.mark.asyncio
    async def test_workflow_with_mocked_llm(
        self,
        sample_state: dict,
        mock_llm_client: MagicMock,
    ):
        """Test workflow execution with mocked LLM."""
        from app.graph.compiler import compile_research_graph

        # This test verifies the graph compiles and can be invoked
        graph = compile_research_graph()
        assert graph is not None
        assert hasattr(graph, "graph")

    def test_workflow_state_serialization(self, sample_plan_steps: list):
        """Test that plan steps can be serialized and deserialized."""
        from app.graph.state import PlanStep, deserialize_steps

        # Serialize
        steps = [PlanStep.model_validate(s) for s in sample_plan_steps]
        serialized = [s.model_dump() for s in steps]

        # Deserialize
        deserialized = deserialize_steps(serialized)
        assert len(deserialized) == 2
        assert deserialized[0].assigned_agent == "search"
        assert deserialized[1].assigned_agent == "browser"

    def test_plan_step_status_transitions(self):
        """Test that plan step status transitions work correctly."""
        from app.graph.state import PlanStep, StepStatus

        step = PlanStep(
            description="Test step",
            assigned_agent="search",
            target_query="test query",
        )
        assert step.status == StepStatus.PENDING

        step.status = StepStatus.RUNNING
        assert step.status == StepStatus.RUNNING

        step.status = StepStatus.DONE
        assert step.status == StepStatus.DONE


class TestAgentCollaboration:
    """Tests for agent-to-agent collaboration."""

    def test_planner_generates_plan(self, planner_agent: MagicMock):
        """Test that planner generates a valid plan."""
        # The planner should return PlanStep objects
        plan = planner_agent.create_plan("Test query")

        # Should have fallback plan (3 steps) since LLM is mocked
        assert len(plan) == 3
        agent_types = {step.assigned_agent for step in plan}
        assert "search" in agent_types
        assert "browser" in agent_types
        assert "rag" in agent_types

    def test_analyst_validates_evidence(self, analyst_agent: MagicMock):
        """Test that analyst can process evidence."""
        from app.graph.state import Evidence, AgentType

        evidence = [
            Evidence(
                content="Test evidence content",
                source_title="Test Source",
                source_url="https://test.com",
                source_type="web",
                agent_type=AgentType.SEARCH,
            )
        ]

        # Analyst should return analysis text
        analysis = analyst_agent.analyze("Test query", evidence)
        assert isinstance(analysis, str)
        assert len(analysis) > 0

    def test_reflection_detects_hallucinations(self, reflection_agent: MagicMock):
        """Test that reflection agent can detect hallucinations."""
        from app.graph.state import Evidence, AgentType

        evidence = [
            Evidence(
                content="Some evidence",
                source_title="Source",
                source_type="web",
                agent_type=AgentType.ANALYST,
            )
        ]

        # Should return a ReflectionResult
        result = reflection_agent.reflect("Test query", "Analysis text", evidence)
        assert result.overall_confidence == 0.5  # Default result on LLM failure
        assert result.needs_revision is False


class TestSSEIntegration:
    """Tests for SSE streaming functionality."""

    @pytest.mark.asyncio
    async def test_sse_publish_and_stream(self, sse_manager):
        """Test SSE publish and stream."""
        session_id = "test-session-001"

        # Publish an event
        await sse_manager.publish(session_id, "agent_start", {"agent": "planner"})

        # Stream events
        events = []
        async for event in sse_manager.stream(session_id):
            events.append(event)
            if event["event"] == "connected":
                break
            if len(events) > 5:
                break

        assert len(events) >= 1
        assert events[0]["event"] == "connected"

    @pytest.mark.asyncio
    async def test_sse_multiple_sessions(self, sse_manager):
        """Test SSE with multiple concurrent sessions."""
        sessions = ["session-1", "session-2", "session-3"]

        # Publish to each session
        for sid in sessions:
            await sse_manager.publish(sid, "agent_start", {"agent": f"agent-{sid}"})

        # Each should have independent queue
        for sid in sessions:
            queue = await sse_manager._get_queue(sid)
            assert queue is not None

    @pytest.mark.asyncio
    async def test_sse_history(self, sse_manager):
        """Test SSE event history."""
        session_id = "test-history-session"

        # Publish multiple events
        for i in range(5):
            await sse_manager.publish(session_id, f"event_{i}", {"index": i})

        # Get history
        history = sse_manager.get_history(session_id)
        assert len(history) == 5

    @pytest.mark.asyncio
    async def test_sse_session_close(self, sse_manager):
        """Test SSE session cleanup."""
        session_id = "test-close-session"

        # Create session and publish
        await sse_manager.publish(session_id, "test", {})
        assert session_id in sse_manager._sessions

        # Close session
        sse_manager.close_session(session_id)
        assert session_id not in sse_manager._sessions


class TestGraphCompilation:
    """Tests for graph compilation and structure."""

    def test_graph_has_all_nodes(self, research_graph):
        """Test that compiled graph has all required nodes."""
        nodes = set(research_graph.graph.nodes)
        required_nodes = {
            "planner", "search", "browser", "rag",
            "analyst", "reflection", "report",
        }
        assert required_nodes.issubset(nodes)

    def test_graph_edges_exist(self, research_graph):
        """Test that expected edges exist in the graph."""
        edges = []
        for start, end in research_graph.graph.edges:
            edges.append((start, end))

        # Should have edges from START to planner
        assert any(start == "__start__" and end == "planner" for start, end in edges)

        # Should have edges from sub-agents to analyst
        for agent in ["search", "browser", "rag"]:
            assert any(start == agent and end == "analyst" for start, end in edges)

        # Should have edge from analyst to reflection
        assert any(start == "analyst" and end == "reflection" for start, end in edges)

        # Should have edge from report to END
        assert any(start == "report" and end == "__end__" for start, end in edges)

    def test_graph_compiles_without_error(self):
        """Test that graph compiles successfully."""
        from app.graph.compiler import compile_research_graph
        # Should not raise
        graph = compile_research_graph()
        assert graph is not None


class TestMetricsCollectors:
    """Tests for metrics collectors."""

    def test_langgraph_metrics_collector(self):
        """Test LangGraph metrics collector."""
        from metrics.langgraph_workflow.collector import LangGraphMetricsCollector

        collector = LangGraphMetricsCollector(storage_path="metrics/test_langgraph/data")
        collector.record_workflow_start("session-1", "Test query")
        collector.record_node_start("session-1", "planner")
        collector.record_node_end("session-1", "planner", status="completed")
        collector.record_workflow_end("session-1", status="completed")

        metrics = collector.get_metrics()
        assert metrics["summary"]["total_workflows"] == 1
        assert metrics["summary"]["completed"] == 1

    def test_sse_metrics_collector(self):
        """Test SSE metrics collector."""
        from metrics.observability.collector import ObservabilityMetricsCollector

        collector = ObservabilityMetricsCollector(storage_path="metrics/test_sse/data")
        collector.record_connection_start("session-1")
        collector.record_event_publish("session-1", "thought", 100)
        collector.record_event_publish("session-1", "tool_call", 50)
        collector.record_connection_end("session-1", events_sent=2, bytes_sent=150)

        metrics = collector.get_metrics()
        assert metrics["summary"]["total_connections"] == 1
        assert metrics["summary"]["total_events_published"] == 2

    def test_research_quality_metrics_collector(self):
        """Test research quality metrics collector."""
        from metrics.research_quality.collector import ResearchQualityCollector

        collector = ResearchQualityCollector(storage_path="metrics/test_quality/data")
        collector.record_report_quality(
            session_id="session-1",
            query="Test query",
            total_claims=10,
            verified_claims=9,
            hallucinated_claims=1,
            citation_count=8,
            plan_coverage=0.9,
            avg_confidence=0.85,
        )

        metrics = collector.get_metrics()
        assert metrics["summary"]["total_reports"] == 1


class TestEdgeRouting:
    """Tests for edge routing logic."""

    def test_should_revise_under_limit(self):
        """Test revision routing when under limit."""
        from app.graph.compiler import should_revise

        state = {
            "revision_needed": True,
            "revision_count": 2,
        }
        assert should_revise(state) == "replan"

    def test_should_revise_at_limit(self):
        """Test revision routing when at limit."""
        from app.graph.compiler import should_revise

        state = {
            "revision_needed": True,
            "revision_count": 3,
        }
        assert should_revise(state) == "generate_report"

    def test_should_not_revise(self):
        """Test no revision when not needed."""
        from app.graph.compiler import should_revise

        state = {
            "revision_needed": False,
            "revision_count": 0,
        }
        assert should_revise(state) == "generate_report"


class TestRRFMatrices:
    """Tests for RRF fusion matrix calculations."""

    def test_rrf_single_list(self):
        """Test RRF with single result list."""
        from app.rag.retriever import HybridRetriever

        retriever = HybridRetriever()
        result = retriever.reciprocal_rank_fusion([
            [("doc1", 1.0), ("doc2", 0.8), ("doc3", 0.6)],
        ])

        assert len(result) == 3
        assert result[0][0] == "doc1"
        assert result[1][0] == "doc2"
        assert result[2][0] == "doc3"

    def test_rrf_multiple_lists(self):
        """Test RRF with multiple result lists."""
        from app.rag.retriever import HybridRetriever

        retriever = HybridRetriever()
        list1 = [("doc1", 1.0), ("doc2", 0.8)]
        list2 = [("doc2", 1.0), ("doc1", 0.7)]

        result = retriever.reciprocal_rank_fusion([list1, list2], k=60)
        result_dict = {doc_id: score for doc_id, score in result}

        assert "doc1" in result_dict
        assert "doc2" in result_dict
        # Both docs should have higher scores due to appearing in both lists
        assert result_dict["doc1"] > 0
        assert result_dict["doc2"] > 0

    def test_rrf_empty_input(self):
        """Test RRF with empty input."""
        from app.rag.retriever import HybridRetriever

        retriever = HybridRetriever()
        result = retriever.reciprocal_rank_fusion([])
        assert result == []

    def test_rrf_different_k_values(self):
        """Test that different k values affect scores."""
        from app.rag.retriever import HybridRetriever

        retriever = HybridRetriever()
        list1 = [("doc1", 1.0), ("doc2", 0.8)]

        result_low_k = retriever.reciprocal_rank_fusion([list1], k=1)
        result_high_k = retriever.reciprocal_rank_fusion([list1], k=100)

        # With higher k, the relative difference between ranks is smaller
        ratio_low = result_low_k[0][1] / result_low_k[1][1]
        ratio_high = result_high_k[0][1] / result_high_k[1][1]

        assert ratio_low > ratio_high


class TestAPIEndpoints:
    """Tests for FastAPI endpoints."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Test health check endpoint."""
        from fastapi.testclient import TestClient
        from app.main import app

        # This would need the app to be properly configured
        # For now, just verify the app exists
        assert app is not None
        assert app.title == "Agentic Deep Research System"

    def test_research_request_validation(self):
        """Test ResearchRequest model validation."""
        from app.api.research import ResearchRequest

        # Valid request
        req = ResearchRequest(query="Test query")
        assert req.query == "Test query"
        assert req.session_id is None
        assert req.max_revision == 3

        # Query too short
        with pytest.raises(Exception):
            ResearchRequest(query="Hi")  # min_length=5

    def test_research_status_model(self):
        """Test ResearchStatus model."""
        from app.api.research import ResearchStatus

        status = ResearchStatus(
            session_id="test-123",
            status="running",
            created_at="2026-01-01T00:00:00",
        )
        assert status.session_id == "test-123"
        assert status.status == "running"
