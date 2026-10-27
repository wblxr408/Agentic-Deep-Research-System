"""Monotonic owner-scoped registry changes across application processes."""
from app.db.connection import get_db_pool


async def bump_generation(conn,owner_id):
    await conn.execute('''INSERT INTO skill_registry_generations(owner_id,generation)
        VALUES($1::uuid,1) ON CONFLICT(owner_id) DO UPDATE
        SET generation=skill_registry_generations.generation+1''',owner_id)


async def read_generation(owner_id):
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        return int(await conn.fetchval('SELECT generation FROM skill_registry_generations WHERE owner_id=$1::uuid',owner_id) or 0)
