"""
Database connection management and models.

PostgreSQL + pgvector for document storage and hybrid retrieval.
Redis for session cache and LLM response cache.
"""

from __future__ import annotations

import logging
from typing import Any

import asyncpg
import redis.asyncio as redis

from app.config import get_settings

logger = logging.getLogger(__name__)

# Global pool instances
_db_pool: asyncpg.Pool | None = None
_redis_client: redis.Redis | None = None


async def init_db() -> asyncpg.Pool:
    """
    Initialize PostgreSQL connection pool and create tables if needed.
    """
    global _db_pool
    if _db_pool is not None:
        return _db_pool

    settings = get_settings()
    pool = await asyncpg.create_pool(
        settings.database.url,
        min_size=2,
        max_size=20,
    )

    # Create tables
    async with pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                content TEXT NOT NULL,
                metadata JSONB DEFAULT '{}',
                embedding VECTOR(1024),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_embedding
            ON documents USING ivfflat (embedding cosine_ops)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_fts
            ON documents USING gin (to_tsvector('chinese', content))
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS research_sessions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_query TEXT NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                research_plan JSONB DEFAULT '[]',
                final_report TEXT,
                citations JSONB DEFAULT '[]',
                agent_trace JSONB DEFAULT '[]',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                completed_at TIMESTAMP
            )
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS citations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                session_id UUID REFERENCES research_sessions(id) ON DELETE CASCADE,
                citation_id VARCHAR(20),
                source_url TEXT,
                source_title TEXT,
                source_type VARCHAR(20),
                extracted_evidence TEXT,
                relevance_score FLOAT,
                access_timestamp TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

    _db_pool = pool
    logger.info("Database initialized successfully")
    return pool


async def get_db_pool() -> asyncpg.Pool:
    """Get the database connection pool."""
    global _db_pool
    if _db_pool is None:
        return await init_db()
    return _db_pool


async def get_redis() -> redis.Redis:
    """Get the Redis client."""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = redis.from_url(
            settings.redis.url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def close_db():
    """Close all database connections."""
    global _db_pool, _redis_client
    if _db_pool:
        await _db_pool.close()
        _db_pool = None
    if _redis_client:
        await _redis_client.close()
        _redis_client = None


# ==============================================================
# SQLAlchemy-style models (using raw asyncpg for simplicity)
# ==============================================================

class Document:
    """Document model for the knowledge base."""

    @staticmethod
    async def create(
        content: str,
        metadata: dict[str, Any],
        embedding: list[float] | None = None,
    ) -> str:
        """Create a new document and return its ID."""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO documents (content, metadata, embedding)
                VALUES ($1, $2, $3::vector)
                RETURNING id
                """,
                content,
                metadata,
                embedding,
            )
            return str(row["id"])

    @staticmethod
    async def search_by_vector(
        embedding: list[float],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Search documents by vector similarity."""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, content, metadata,
                       1 - (embedding <=> $1::vector) AS similarity
                FROM documents
                ORDER BY embedding <=> $1::vector
                LIMIT $2
                """,
                embedding,
                top_k,
            )
            return [dict(r) for r in rows]

    @staticmethod
    async def count() -> int:
        """Count total documents."""
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT COUNT(*) FROM documents")
            return int(row["count"])
