"""
Retrieval tools for LangChain/LangGraph integration.

Provides RAG retrieval as LangChain-compatible tools.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from langchain_core.tools import tool

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@tool
def knowledge_base_search(query: str, top_k: int = 5) -> str:
    """
    Search the internal knowledge base for relevant documents and context.

    Use this for:
    - Domain background knowledge
    - Previous research reports
    - Technical documentation
    - Historical data and trends

    Args:
        query: The search query
        top_k: Number of top results to return (default 5)

    Returns:
        JSON string of retrieved document chunks with metadata
    """
    try:
        from app.agents.rag import RAGAgent
        from app.graph.state import PlanStep

        # Quick single-query RAG retrieval
        step = PlanStep(
            description=f"Knowledge base search: {query}",
            assigned_agent="rag",
            target_query=query,
        )
        agent = RAGAgent()
        results = agent.execute([step], query)

        output = []
        for r in results[:top_k]:
            output.append({
                "chunk_id": r.chunk_id,
                "content": r.content[:500],
                "metadata": r.metadata,
                "rerank_score": r.rerank_score,
                "source": r.metadata.get("title", "Unknown") if r.metadata else "Unknown",
            })

        return json.dumps(output, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"Knowledge base search error: {e}")
        return json.dumps({"error": str(e)})


def get_retrieval_tools():
    """Return all retrieval tools for LangGraph."""
    return [knowledge_base_search]
