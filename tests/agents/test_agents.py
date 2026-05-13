"""
Tests for individual agent implementations.
"""

import pytest
from unittest.mock import MagicMock, patch
from app.graph.state import PlanStep, StepStatus, Evidence, AgentType


class TestPlannerAgent:
    def test_planner_import(self):
        from app.agents.planner import PlannerAgent
        agent = PlannerAgent()
        assert agent is not None

    def test_fallback_plan_generation(self):
        from app.agents.planner import PlannerAgent

        agent = PlannerAgent()
        # Mock the client to fail
        agent._client = MagicMock()
        agent._client.chat.completions.create.side_effect = Exception("API Error")

        steps = agent.create_plan("中国新能源车市场分析")
        assert len(steps) == 3
        assert all(s.status == StepStatus.PENDING for s in steps)
        # Should have one of each agent type
        agent_types = {s.assigned_agent for s in steps}
        assert "search" in agent_types
        assert "browser" in agent_types
        assert "rag" in agent_types


class TestSearchAgent:
    def test_search_agent_import(self):
        from app.agents.search import SearchAgent
        agent = SearchAgent()
        assert agent is not None

    def test_deduplication(self):
        from app.agents.search import SearchAgent, SearchResult

        agent = SearchAgent()
        results = [
            SearchResult(url="https://example.com/1", title="A", snippet="x", relevance_score=0.5),
            SearchResult(url="https://example.com/1", title="A", snippet="x", relevance_score=0.8),
            SearchResult(url="https://example.com/2", title="B", snippet="y", relevance_score=0.6),
        ]
        deduped = agent._deduplicate(results)
        assert len(deduped) == 2
        # Should keep the one with higher score
        assert next(r for r in deduped if r.url == "https://example.com/1").relevance_score == 0.8


class TestBrowserAgent:
    def test_browser_agent_import(self):
        from app.agents.browser import BrowserAgent
        agent = BrowserAgent()
        assert agent is not None

    def test_page_classification(self):
        from app.agents.browser import BrowserAgent, PageType
        from unittest.mock import MagicMock

        agent = BrowserAgent()

        # News article
        result = agent._classify_page("https://news.example.com/article/123", MagicMock())
        assert result == PageType.NEWS_ARTICLE

        # GitHub
        result = agent._classify_page("https://github.com/user/repo", MagicMock())
        assert result == PageType.TECHNICAL

        # Search result
        result = agent._classify_page("https://www.google.com/search?q=AI", MagicMock())
        assert result == PageType.SEARCH_RESULT

        # Social
        result = agent._classify_page("https://zhihu.com/question/123", MagicMock())
        assert result == PageType.SOCIAL

        # General
        result = agent._classify_page("https://example.com/page", MagicMock())
        assert result == PageType.GENERAL

    def test_fallback_result(self):
        from app.agents.browser import BrowserAgent

        agent = BrowserAgent()
        result = agent._fallback_result("https://failed.com")
        assert result.url == "https://failed.com"
        assert result.extracted_content == ""
        assert len(result.citations) == 0


class TestRAGAgent:
    def test_rag_agent_import(self):
        from app.agents.rag import RAGAgent
        agent = RAGAgent()
        assert agent is not None


class TestAnalystAgent:
    def test_analyst_import(self):
        from app.agents.analyst import AnalystAgent
        agent = AnalystAgent()
        assert agent is not None

    def test_evidence_formatting(self):
        from app.agents.analyst import AnalystAgent, Evidence

        agent = AnalystAgent()
        evidence = [
            Evidence(
                content="这是测试内容的一部分",
                source_title="测试来源",
                source_url="https://test.com",
                source_type="web",
                agent_type=AgentType.SEARCH,
            )
        ]
        formatted = agent._format_evidence(evidence)
        assert "测试来源" in formatted
        assert "这是测试内容的一部分" in formatted


class TestReflectionAgent:
    def test_reflection_import(self):
        from app.agents.reflection import ReflectionAgent
        agent = ReflectionAgent()
        assert agent is not None

    def test_default_result(self):
        from app.agents.reflection import ReflectionAgent

        agent = ReflectionAgent()
        result = agent._default_result()
        assert result.overall_confidence == 0.5
        assert result.needs_revision is False
        assert len(result.hallucinated_claims) == 0


class TestReportAgent:
    def test_report_import(self):
        from app.agents.report import ReportAgent
        agent = ReportAgent()
        assert agent is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
