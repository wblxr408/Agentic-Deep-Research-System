"""
Retrieval tools for LangChain/LangGraph integration.

Provides RAG retrieval as LangChain-compatible tools.
"""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from typing import Literal

from langchain_core.tools import tool

logger = logging.getLogger(__name__)
_retrieval_owner_id: ContextVar[str | None] = ContextVar("retrieval_owner_id", default=None)
_retrieval_session_id: ContextVar[str | None] = ContextVar('retrieval_session_id',default=None)


@tool
def knowledge_base_search(
    query: str,
    top_k: int = 5,
    group: str | None = None,
    context_mode:Literal['source_preference','matched','parent']='source_preference',
) -> str:
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
        group: Optional current source group. Legacy rows without a source can
            match metadata.group/source_group/knowledge_group.
        context_mode: Use saved preference, matched span, or bounded parent.

    Returns:
        JSON string of retrieved document chunks with metadata
    """
    owner_id = _retrieval_owner_id.get()
    if not owner_id:
        return json.dumps({"error": "owner_scope_required"})
    if not 1<=top_k<=10:return json.dumps({'error':'top_k_must_be_between_1_and_10'})

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
        results = agent.execute([step], query, group=group, owner_id=owner_id,context_mode=context_mode,session_id=_retrieval_session_id.get())

        output = []
        for r in results[:top_k]:
            output.append({
                "chunk_id": r.chunk_id,
                "content": r.content[:4000],
                "metadata": r.metadata,
                "rerank_score": r.rerank_score,
                "source": (r.metadata.get("title") or r.metadata.get('source_name') or 'Unknown') if r.metadata else "Unknown",
                'content_truncated':len(r.content)>4000,
            })

        return json.dumps(output, ensure_ascii=False, indent=2)

    except (OSError, RuntimeError, TypeError, ValueError, KeyError) as e:
        logger.error(f"Knowledge base search error: {e}")
        return json.dumps({"error": str(e)})


def get_retrieval_tools(owner_id: str,session_id:str|None=None):
    """Return tools bound to a server-derived owner, never an LLM argument."""
    @tool
    def scoped_knowledge_base_search(query: str, top_k: int = 5, group: str | None = None,
            context_mode:Literal['source_preference','matched','parent']='source_preference') -> str:
        token = _retrieval_owner_id.set(owner_id)
        session_token=_retrieval_session_id.set(session_id)
        try:
            return knowledge_base_search.invoke({"query": query, "top_k": top_k, "group": group,'context_mode':context_mode})
        finally:
            _retrieval_owner_id.reset(token)
            _retrieval_session_id.reset(session_token)

    return [scoped_knowledge_base_search]
