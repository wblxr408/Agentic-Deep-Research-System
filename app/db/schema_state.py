"""One deployment generation; normal API restarts do not repeat live DDL."""
VERSION='adrs-rel-20261030-v1'

async def prepare_metadata(conn):
    await conn.execute('''CREATE TABLE IF NOT EXISTS app_schema_generation (
        singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK(singleton),version TEXT NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())''')

async def mark_ready(conn):
    await prepare_metadata(conn)
    await conn.execute('''INSERT INTO app_schema_generation(singleton,version) VALUES(TRUE,$1)
        ON CONFLICT(singleton) DO UPDATE SET version=EXCLUDED.version,updated_at=NOW()''',VERSION)

async def require_idle_upgrade(conn):
    if await conn.fetchval("SELECT to_regclass('research_execution_jobs')"):
        active=await conn.fetchval("SELECT EXISTS(SELECT 1 FROM research_execution_jobs WHERE status='running' AND lease_until>NOW())")
        if active:raise RuntimeError('schema_upgrade_requires_idle_research')
    if await conn.fetchval("SELECT to_regclass('research_sessions')"):
        active=await conn.fetchval("SELECT EXISTS(SELECT 1 FROM research_sessions WHERE status='running' AND updated_at>NOW()-INTERVAL '120 seconds')")
        if active:raise RuntimeError('schema_upgrade_requires_idle_research')
