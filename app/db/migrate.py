"""
Database migration script.

Initializes the PostgreSQL schema with pgvector extension,
creates all tables, indexes, and applies initial seed data.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import asyncpg

logger = logging.getLogger(__name__)

# SQL for schema creation
SCHEMA_SQL = """
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- ==============================================================
-- Documents table (knowledge base with vector embeddings)
-- ==============================================================
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    embedding VECTOR({dimension}),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Vector similarity index (IVF for approximate nearest neighbor)
CREATE INDEX IF NOT EXISTS idx_documents_embedding
    ON documents USING ivfflat (embedding cosine_ops)
    WITH (lists = 100);

-- Full-text search index (Chinese and English)
CREATE INDEX IF NOT EXISTS idx_documents_fts_zh
    ON documents USING gin (to_tsvector('chinese', content));

CREATE INDEX IF NOT EXISTS idx_documents_fts_en
    ON documents USING gin (to_tsvector('english', content));

-- Metadata filtering index
CREATE INDEX IF NOT EXISTS idx_documents_metadata
    ON documents USING gin (metadata);

-- ==============================================================
-- Research sessions table
-- ==============================================================
CREATE TABLE IF NOT EXISTS research_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_query TEXT NOT NULL,
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    research_plan JSONB DEFAULT '[]',
    final_report TEXT,
    citations JSONB DEFAULT '[]',
    agent_trace JSONB DEFAULT '[]',
    error_message TEXT,
    revision_count INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    total_cost_usd NUMERIC(10, 6) DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Status query index
CREATE INDEX IF NOT EXISTS idx_sessions_status ON research_sessions (status);
CREATE INDEX IF NOT EXISTS idx_sessions_created ON research_sessions (created_at DESC);

-- ==============================================================
-- Citations table
-- ==============================================================
CREATE TABLE IF NOT EXISTS citations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES research_sessions(id) ON DELETE CASCADE,
    citation_id VARCHAR(20) NOT NULL,
    source_url TEXT,
    source_title TEXT,
    source_type VARCHAR(20) DEFAULT 'web'
        CHECK (source_type IN ('web', 'document', 'knowledge_base')),
    extracted_evidence TEXT,
    relevance_score FLOAT DEFAULT 0,
    access_timestamp TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(session_id, citation_id)
);

CREATE INDEX IF NOT EXISTS idx_citations_session ON citations (session_id);

-- ==============================================================
-- Agent trace events table (for detailed analytics)
-- ==============================================================
CREATE TABLE IF NOT EXISTS agent_events (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID REFERENCES research_sessions(id) ON DELETE CASCADE,
    agent_name VARCHAR(50) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    content TEXT,
    duration_ms INTEGER,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_events_session ON agent_events (session_id);
CREATE INDEX IF NOT EXISTS idx_events_agent ON agent_events (agent_name);
CREATE INDEX IF NOT EXISTS idx_events_type ON agent_events (event_type);

-- ==============================================================
-- Tool call metrics table
-- ==============================================================
CREATE TABLE IF NOT EXISTS tool_metrics (
    id BIGSERIAL PRIMARY KEY,
    session_id UUID REFERENCES research_sessions(id) ON DELETE CASCADE,
    tool_name VARCHAR(100) NOT NULL,
    call_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    total_duration_ms BIGINT DEFAULT 0,
    avg_duration_ms FLOAT DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tool_metrics_session ON tool_metrics (session_id);

-- ==============================================================
-- System configuration table (for frontend-configurable settings)
-- ==============================================================
CREATE TABLE IF NOT EXISTS system_config (
    config_key VARCHAR(50) PRIMARY KEY,
    config_data JSONB NOT NULL DEFAULT '{}',
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_system_config_key ON system_config (config_key);

-- ==============================================================
-- Trigger: auto-update updated_at
-- ==============================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE OR REPLACE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE OR REPLACE TRIGGER update_sessions_updated_at
    BEFORE UPDATE ON research_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
"""


async def run_migration(
    database_url: str,
    embed_dimension: int = 1024,
    drop_existing: bool = False,
) -> None:
    """
    Run database migrations.

    Args:
        database_url: PostgreSQL connection URL
        embed_dimension: Embedding vector dimension (for pgvector column)
        drop_existing: If True, drop existing tables before creating
    """
    logger.info("Starting database migration...")

    pool = await asyncpg.create_pool(
        database_url,
        min_size=1,
        max_size=5,
    )

    try:
        async with pool.acquire() as conn:
            # Enable pgvector extension
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

            if drop_existing:
                logger.warning("Dropping existing tables (drop_existing=True)")
                await conn.execute("""
                    DROP TABLE IF EXISTS tool_metrics CASCADE;
                    DROP TABLE IF EXISTS agent_events CASCADE;
                    DROP TABLE IF EXISTS citations CASCADE;
                    DROP TABLE IF EXISTS research_sessions CASCADE;
                    DROP TABLE IF EXISTS documents CASCADE;
                """)

            # Create schema
            schema = SCHEMA_SQL.format(dimension=embed_dimension)
            await conn.execute(schema)

            logger.info("Database migration completed successfully")

            # Verify tables
            tables = await conn.fetch("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)
            logger.info(f"Created tables: {[t['table_name'] for t in tables]}")

    finally:
        await pool.close()


def main() -> None:
    """CLI entry point for migration."""
    import argparse
    from app.config import get_settings

    parser = argparse.ArgumentParser(description="Run database migrations")
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop existing tables before creating (destructive!)",
    )
    parser.add_argument(
        "--dimension",
        type=int,
        default=1024,
        help="Embedding dimension (default: 1024)",
    )
    args = parser.parse_args()

    settings = get_settings()
    asyncio.run(
        run_migration(
            database_url=settings.database.url,
            embed_dimension=args.dimension,
            drop_existing=args.drop,
        )
    )


if __name__ == "__main__":
    main()
