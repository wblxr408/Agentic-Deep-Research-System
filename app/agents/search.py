"""
Search Agent: performs web search with query expansion and deduplication.

Implements multi-query expansion and result ranking.
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING

from app.config import get_settings
from app.graph.state import PlanStep, SearchResult

if TYPE_CHECKING:
    from openai import OpenAI

logger = logging.getLogger(__name__)


class SearchAgent:
    """
    Handles search query execution with query rewriting and deduplication.

    Expands each plan step into multiple search queries, executes them,
    then deduplicates and ranks the results.
    """

    EXPAND_PROMPT = """Given the original research query, generate 3-5 diverse search queries covering:
1. Core facts and hard data (numbers, statistics)
2. Expert analysis and authoritative opinions
3. Latest news and developments (past 6 months)

Return JSON with a "queries" array of strings."""

    def __init__(self):
        settings = get_settings()
        self.model = settings.llm.model
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            from app.llm_client import create_llm_client, get_llm_model
            self._client = create_llm_client()
            self.model = get_llm_model()
        return self._client

    def execute(self, plan_steps: list[PlanStep], user_query: str) -> list[SearchResult]:
        """
        Execute search for given plan steps.

        Args:
            plan_steps: Steps assigned to 'search' agent
            user_query: Original user query for context

        Returns:
            List of deduplicated SearchResult objects
        """
        logger.info(f"Search Agent: executing {len(plan_steps)} plan steps")

        all_results: list[SearchResult] = []

        for step in plan_steps:
            try:
                # Step 1: Expand the query
                expanded_queries = self._expand_query(step.target_query, user_query)

                # Step 2: Execute each expanded query
                for query in expanded_queries:
                    results = self._execute_search(query)
                    all_results.extend(results)
                    time.sleep(0.5)  # Rate limiting

            except Exception as e:
                logger.error(f"Search step error for '{step.target_query}': {e}")
                continue

        # Step 3: Deduplicate and rank
        deduplicated = self._deduplicate(all_results)
        ranked = self._rank_results(deduplicated, user_query)

        logger.info(f"Search Agent: {len(ranked)} unique results after ranking")
        return ranked[:15]  # Top 15 results

    def _expand_query(self, query: str, user_query: str) -> list[str]:
        """Expand a query into multiple search queries."""
        messages = [
            {"role": "system", "content": self.EXPAND_PROMPT},
            {"role": "user", "content": f"Original query: {query}\nContext: {user_query}"},
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
                max_tokens=512,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            if content:
                data = json.loads(content)
                queries = data.get("queries", [])
                if queries:
                    return queries[:5]
        except Exception as e:
            logger.warning(f"Query expansion failed: {e}")

        return [query]  # Fallback to original

    def _execute_search(self, query: str) -> list[SearchResult]:
        """
        Execute a single search query.

        Uses DuckDuckGo (no API key required) as primary,
        falls back to Brave Search if configured.
        """
        try:
            import requests

            # Try DuckDuckGo Instant Answer API (free, no auth)
            url = "https://api.duckduckgo.com/"
            params = {
                "q": query,
                "format": "json",
                "no_html": "1",
                "skip_disambig": "1",
            }

            response = requests.get(url, params=params, timeout=10)
            if response.status_code != 200:
                return []

            data = response.json()
            results: list[SearchResult] = []

            # Extract related topics
            for topic in data.get("RelatedTopics", [])[:8]:
                if "Text" in topic and "URL" in topic:
                    results.append(SearchResult(
                        url=topic["URL"],
                        title=self._clean_html(data.get("Heading", query)),
                        snippet=self._clean_html(topic["Text"])[:300],
                        relevance_score=0.5,
                    ))

            # Extract abstract
            if data.get("AbstractText"):
                results.insert(0, SearchResult(
                    url=data.get("AbstractURL", ""),
                    title=data.get("Heading", query),
                    snippet=data["AbstractText"][:300],
                    relevance_score=0.9,
                ))

            return results

        except Exception as e:
            logger.warning(f"Search execution failed for '{query}': {e}")
            return []

    def _clean_html(self, text: str) -> str:
        """Remove HTML entities and excess whitespace."""
        import html
        import re
        text = html.unescape(text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _deduplicate(self, results: list[SearchResult]) -> list[SearchResult]:
        """Remove duplicate URLs, keeping highest-scoring entry."""
        seen: dict[str, SearchResult] = {}
        for r in results:
            if r.url and r.url not in seen:
                seen[r.url] = r
            elif r.url in seen and r.relevance_score > seen[r.url].relevance_score:
                seen[r.url] = r
        return list(seen.values())

    def _rank_results(self, results: list[SearchResult], user_query: str) -> list[SearchResult]:
        """Re-rank results by relevance to the user query."""
        keywords = set(user_query.lower().split())
        for r in results:
            score = r.relevance_score
            title_words = set(r.title.lower().split())
            snippet_words = set(r.snippet.lower().split())
            overlap = len(keywords & title_words) + 0.5 * len(keywords & snippet_words)
            r.relevance_score = score + 0.1 * overlap
        return sorted(results, key=lambda r: r.relevance_score, reverse=True)

    def execute_search(self, query: str) -> list[SearchResult]:
        """
        Execute a single search query (主题 3 工具接口).

        直接执行单个搜索查询，供 DAG executor 调用。
        """
        from app.graph.state import PlanStep
        step = PlanStep(
            target_query=query,
            node_type="search",
        )
        return self.execute([step], query)

    def execute_for_node(self, node_query: str, context: str = "") -> list[SearchResult]:
        """兼容接口：根据节点 query 执行搜索。"""
        return self.execute_search(node_query)
