"""Durable dispatch, detached execution and bounded event replay on PostgreSQL.

Only explicit create/resume handlers enqueue work. A missing worker never grants
permission to replay unknown requests or reset a root's deadline.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from app.db.json import dumps_json
from app.db.execution_control import decoded,persist_workflow_failure

logger=logging.getLogger(__name__)
SCHEMA_SQL='''
CREATE TABLE IF NOT EXISTS research_execution_jobs (
 execution_id UUID PRIMARY KEY,session_id UUID NOT NULL REFERENCES research_sessions(id) ON DELETE CASCADE,
 owner_id UUID NOT NULL,payload JSONB NOT NULL,status TEXT NOT NULL DEFAULT 'queued',
 claim_token UUID,worker_pid INTEGER,lease_until TIMESTAMPTZ,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),finished_at TIMESTAMPTZ,error_category TEXT
);
CREATE INDEX IF NOT EXISTS idx_research_jobs_dispatch ON research_execution_jobs(status,created_at);
CREATE TABLE IF NOT EXISTS research_execution_events (
 id BIGSERIAL PRIMARY KEY,session_id UUID NOT NULL REFERENCES research_sessions(id) ON DELETE CASCADE,
 execution_id UUID NOT NULL,event_type TEXT NOT NULL,payload JSONB NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_research_events_replay ON research_execution_events(session_id,execution_id,id);
'''


async def enqueue(conn,**values):
    """The caller's root transition transaction also commits its dispatch intent."""
    root=await conn.fetchrow('SELECT status,execution_id,created_at FROM research_sessions WHERE id=$1::uuid AND owner_id=$2::uuid',
        str(values['session_id']),str(values['owner_id']))
    if not root or root['status']!='running' or str(root['execution_id'])!=str(values['execution_id']):
        raise ValueError('research_dispatch_binding_changed')
    values['original_created_at']=root['created_at'].isoformat()
    if values.get('resume_state') is None:
        from app.model_routing import freeze_model_routing
        from app.data_governance import model_class
        understanding=values.get('query_understanding') or {}
        values['frozen_model_routing']=freeze_model_routing(private=bool(values.get('use_internal_docs')),
            data_class=model_class((understanding.get('data_governance') or {}).get('initial_class','public')),
            deep=(understanding.get('slots') or {}).get('depth')=='deep',
            complexity=(understanding.get('complexity') or {}).get('level','moderate'))
    await conn.execute('''INSERT INTO research_execution_jobs(execution_id,session_id,owner_id,payload)
        VALUES($1::uuid,$2::uuid,$3::uuid,$4::jsonb) ON CONFLICT(execution_id) DO NOTHING''',
        str(values['execution_id']),str(values['session_id']),str(values['owner_id']),dumps_json(values))


async def reconcile(conn,*,session_id=None,owner_id=None):
    """Fence stale/expired execution state; never dispatch old research."""
    rows=await conn.fetch('''SELECT s.id,s.owner_id,s.execution_id,s.created_at,s.review_status,
        r.last_heartbeat_at,j.status AS job_status,j.lease_until,j.payload
        FROM research_sessions s LEFT JOIN session_runtime_state r ON r.session_id=s.id
        LEFT JOIN research_execution_jobs j ON j.execution_id=s.execution_id
        WHERE s.status='running' AND ($1::uuid IS NULL OR s.id=$1::uuid)
          AND ($2::uuid IS NULL OR s.owner_id=$2::uuid)
          AND ((j.status='running' AND j.lease_until<NOW()) OR
               (COALESCE(j.status,'legacy')!='running' AND
                COALESCE(r.last_heartbeat_at,s.created_at)<NOW()-INTERVAL '120 seconds'))
        ORDER BY s.created_at LIMIT 64 FOR UPDATE OF s SKIP LOCKED''',session_id,owner_id)
    from datetime import UTC,datetime
    for row in rows:
        review=decoded(row['review_status']);payload=decoded(row['payload'])
        budget=review.get('budget_state') or review.get('initial_budget') or payload.get('initial_budget') or {}
        seconds=int(budget.get('max_wall_clock_seconds') or 2700)
        start=row['created_at'];start=start.replace(tzinfo=UTC) if start.tzinfo is None else start
        expired=(datetime.now(UTC)-start).total_seconds()>=seconds
        if row['job_status']=='queued' and not expired:continue
        category='execution_deadline_expired' if expired else 'worker_lease_expired'
        binding={'session_id':str(row['id']),'owner_id':str(row['owner_id']),'execution_id':str(row['execution_id'])}
        await persist_workflow_failure(conn,binding,RuntimeError(category),category)
        await conn.execute('''UPDATE research_execution_jobs SET status='interrupted',error_category=$2,
            finished_at=NOW(),updated_at=NOW() WHERE execution_id=$1::uuid AND status IN ('queued','running')''',
            binding['execution_id'],category)


async def retain_event(session_id,execution_id,event_type,data):
    from app.db.connection import get_db_pool
    pool=await get_db_pool()
    value=dumps_json(data)
    if len(value.encode('utf-8'))>262144:
        value=dumps_json({'execution_id':execution_id,'delivery_gap':True,'recovery':'reload_saved_research'})
    async with pool.acquire() as conn:
        event_id=await conn.fetchval('''INSERT INTO research_execution_events(session_id,execution_id,event_type,payload)
            SELECT s.id,s.execution_id,$3,$4::jsonb FROM research_sessions s
            WHERE s.id=$1::uuid AND s.execution_id=$2::uuid RETURNING id''',session_id,execution_id,event_type,value)
        if event_id and event_id%64==0:
            await conn.execute('''DELETE FROM research_execution_events WHERE session_id=$1::uuid AND id<
                COALESCE((SELECT id FROM research_execution_events WHERE session_id=$1::uuid ORDER BY id DESC OFFSET 599 LIMIT 1),0)''',session_id)
    return event_id


async def event_rows(session_id,execution_id,cursor):
    from app.db.connection import get_db_pool
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        return await conn.fetch('''SELECT id,event_type,payload FROM research_execution_events
            WHERE session_id=$1::uuid AND execution_id=$2::uuid AND id>$3 ORDER BY id LIMIT 100''',session_id,execution_id,cursor)


class ResearchDispatcher:
    """Dispatch committed requests to bounded, independently owned OS processes."""
    def __init__(self):self.task=None;self.children={}

    def start(self):
        if self.task is None:self.task=asyncio.create_task(self._loop())

    async def stop(self):
        if self.task:
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True);self.task=None
        # Running children own their leases. API shutdown does not cancel them.

    async def _dispatch(self):
        from app.db.connection import get_db_pool
        pool=await get_db_pool()
        async with pool.acquire() as conn,conn.transaction():
            await reconcile(conn)
            await conn.execute('''UPDATE research_execution_jobs j SET status='superseded',finished_at=NOW(),updated_at=NOW()
                WHERE j.status='queued' AND NOT EXISTS(SELECT 1 FROM research_sessions s WHERE s.id=j.session_id
                    AND s.execution_id=j.execution_id AND s.status='running')''')
            await conn.execute("SELECT pg_advisory_xact_lock(1938402,1)")
            active=await conn.fetchval("SELECT COUNT(*) FROM research_execution_jobs WHERE status='running' AND lease_until>NOW()")
            if active>=2:return
            from app.config import get_settings
            local=not get_settings().security.auth_enabled
            row=await conn.fetchrow('''SELECT j.execution_id FROM research_execution_jobs j JOIN research_sessions s ON s.id=j.session_id AND s.owner_id=j.owner_id
                LEFT JOIN auth_principals p ON p.id=j.owner_id WHERE j.status='queued' AND s.status='running'
                AND s.execution_id=j.execution_id AND (p.is_active=TRUE OR ($1 AND j.owner_id='00000000-0000-0000-0000-000000000000'::uuid))
                ORDER BY j.created_at LIMIT 1 FOR UPDATE OF j SKIP LOCKED''',local)
            if not row:return
            token=str(uuid4());execution=str(row['execution_id'])
            await conn.execute("UPDATE research_execution_jobs SET status='running',claim_token=$2::uuid,lease_until=NOW()+INTERVAL '120 seconds',updated_at=NOW() WHERE execution_id=$1::uuid",execution,token)
        root=Path(__file__).resolve().parent.parent
        log_dir=root/'outputs'/'research-workers';log_dir.mkdir(parents=True,exist_ok=True)
        try:
            with (log_dir/(execution+'.log')).open('ab') as output:
                process=subprocess.Popen([sys.executable,'-m','app.research_worker',execution,token],cwd=str(root),
                    stdin=subprocess.DEVNULL,stdout=output,stderr=output,
                    env={**os.environ,'PYTHONUTF8':'1'},
                    creationflags=(subprocess.DETACHED_PROCESS|subprocess.CREATE_NEW_PROCESS_GROUP) if os.name=='nt' else 0,
                    start_new_session=os.name!='nt',close_fds=True)
            self.children[execution]=process
            async with pool.acquire() as conn:
                await conn.execute('UPDATE research_execution_jobs SET worker_pid=$3 WHERE execution_id=$1::uuid AND claim_token=$2::uuid',execution,token,process.pid)
        except OSError as error:
            logger.error('Research worker launch failed: %s',type(error).__name__)
            async with pool.acquire() as conn,conn.transaction():
                await conn.execute("UPDATE research_execution_jobs SET lease_until=NOW()-INTERVAL '121 seconds' WHERE execution_id=$1::uuid AND claim_token=$2::uuid",execution,token)
                await reconcile(conn)
        self.children={key:value for key,value in self.children.items() if value.poll() is None}

    async def _loop(self):
        while True:
            try:await self._dispatch()
            except asyncio.CancelledError:raise
            except Exception as error:logger.warning('Research dispatch unavailable: %s',type(error).__name__)
            await asyncio.sleep(2)
