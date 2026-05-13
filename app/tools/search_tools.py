"""
Search tools for LangChain/LangGraph integration.

Provides DuckDuckGo search as a LangChain-compatible tool.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from langchain_core.tools import tool

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@tool
def duckduckgo_search(query: str) -> str:
    """
    Search the web using DuckDuckGo. Use this for quick factual lookups,
    statistics, market data, and news.

    Args:
        query: The search query (be specific and use Chinese for Chinese sources)

    Returns:
        JSON string of search results with title, URL, and snippet
    """
    import json
    import requests
    import html

    try:
        url = "https://api.duckduckgo.com/"
        params = {
            "q": query,
            "format": "json",
            "no_html": "1",
            "skip_disambig": "1",
        }
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return json.dumps({"error": "Search failed", "status": response.status_code})

        data = response.json()
        results: list[dict[str, Any]] = []

        # Extract abstract
        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", query),
                "url": data.get("AbstractURL", ""),
                "snippet": html.unescape(data["AbstractText"])[:400],
                "type": "abstract",
            })

        # Extract related topics
        for topic in data.get("RelatedTopics", [])[:10]:
            if "Text" in topic and "URL" in topic:
                results.append({
                    "title": query,
                    "url": topic["URL"],
                    "snippet": html.unescape(topic["Text"])[:300],
                    "type": "related",
                })

        return json.dumps(results, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"DuckDuckGo search error: {e}")
        return json.dumps({"error": str(e)})


def get_search_tools():
    """Return all search tools for LangGraph."""
    return [duckduckgo_search]
