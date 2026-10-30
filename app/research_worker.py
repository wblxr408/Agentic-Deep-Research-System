"""One explicitly queued research execution, independent of the API process."""
from __future__ import annotations
import asyncio
import sys
from datetime import UTC,datetime

async def execute(execution_id,token):
    from app.disclosure import install_log_redaction
    install_log_redaction()
    from app.db.connection import init_db,close_db
    from app.db.execution_control import decoded,persist_workflow_failure
    pool=await init_db(initialize_schema=False)
    async with pool.acquire() as conn:
        row=await conn.fetchrow("SELECT * FROM research_execution_jobs WHERE execution_id=$1::uuid AND claim_token=$2::uuid AND status='running' AND lease_until>NOW()",execution_id,token)
        values=decoded(row['payload']) if row else {}
        root=await conn.fetchrow('SELECT created_at,review_status,status,execution_id FROM research_sessions WHERE id=$1::uuid AND owner_id=$2::uuid',str(row['session_id']),str(row['owner_id'])) if row else None
    if not root or root['status']!='running' or str(root['execution_id'])!=execution_id:
        async with pool.acquire() as conn:
            await conn.execute("UPDATE research_execution_jobs SET status='superseded',finished_at=NOW(),lease_until=NULL WHERE execution_id=$1::uuid AND claim_token=$2::uuid AND status='running'",execution_id,token)
        await close_db();return
    binding={'session_id':str(row['session_id']),'owner_id':str(row['owner_id']),'execution_id':execution_id}
    if any(str(values.get(key))!=value for key,value in binding.items()):
        async with pool.acquire() as conn,conn.transaction():
            await persist_workflow_failure(conn,binding,RuntimeError('research_dispatch_binding_changed'),'research_dispatch_binding_changed')
            await conn.execute("UPDATE research_execution_jobs SET status='rejected',error_category='research_dispatch_binding_changed',finished_at=NOW(),lease_until=NULL WHERE execution_id=$1::uuid AND claim_token=$2::uuid",execution_id,token)
        await close_db();return
    start=root['created_at'];start=start.replace(tzinfo=UTC) if start.tzinfo is None else start
    review=decoded(root['review_status'])
    budget=(values.get('resume_state') or {}).get('budget_state') or values.get('initial_budget') or review.get('initial_budget') or {}
    remaining=int(budget.get('max_wall_clock_seconds') or 2700)-(datetime.now(UTC)-start).total_seconds()
    async def heartbeat():
        while True:
            await asyncio.sleep(15)
            async with pool.acquire() as conn:
                renewed=await conn.fetchval("UPDATE research_execution_jobs SET lease_until=NOW()+INTERVAL '120 seconds',updated_at=NOW() WHERE execution_id=$1::uuid AND claim_token=$2::uuid AND status='running' RETURNING execution_id",execution_id,token)
            if not renewed:
                task.cancel();return
    async def run():
        if remaining<=0:raise TimeoutError('execution_deadline_expired')
        async with asyncio.timeout(max(.001,remaining)):
            from app.skills import get_skill_registry
            await get_skill_registry().load()
            from app.api.research import run_research_workflow
            await run_research_workflow(**values)
    task=asyncio.create_task(run());beat=asyncio.create_task(heartbeat())
    try:
        await task
    except BaseException as error:
        category='execution_deadline_expired' if isinstance(error,TimeoutError) or remaining<=0 else 'execution_interrupted'
        async with pool.acquire() as conn,conn.transaction():await persist_workflow_failure(conn,binding,error,category)
    finally:
        beat.cancel();await asyncio.gather(beat,return_exceptions=True)
        async with pool.acquire() as conn:
            await conn.execute("UPDATE research_execution_jobs SET status='finished',finished_at=NOW(),lease_until=NULL,updated_at=NOW() WHERE execution_id=$1::uuid AND claim_token=$2::uuid AND status='running'",execution_id,token)
        await close_db()

if __name__=='__main__':asyncio.run(execute(sys.argv[1],sys.argv[2]))
