"""Derived in-process stop signals; PostgreSQL remains execution authority."""
from __future__ import annotations

import asyncio
import contextvars
import functools
import inspect
import logging
import threading
from contextlib import asynccontextmanager
from datetime import UTC,datetime,timedelta

logger=logging.getLogger(__name__)
_current=contextvars.ContextVar('adrs_current_execution',default=None)
_active={}
_active_lock=threading.Lock()


def current_control():
    return _current.get()


def check_execution():
    control=current_control()
    if control:control.check()


def signal_cancellation(session_id,execution_id):
    with _active_lock:control=_active.get((str(session_id),str(execution_id)))
    if control:control.stop('execution_canceled')


def execution_is_active(session_id,execution_id):
    with _active_lock:control=_active.get((str(session_id),str(execution_id)))
    return bool(control and not control.event.is_set())


class ExecutionControl:
    def __init__(self,session_id,owner_id,execution_id):
        self.binding={'session_id':str(session_id),'owner_id':str(owner_id),'execution_id':str(execution_id)}
        self.loop=asyncio.get_running_loop();self.event=threading.Event();self.reason=None
        self._closers={};self._lock=threading.Lock()
        self._trace_futures=[]

    def publish_trace(self,event):
        from app.observability.sse_manager import get_sse_manager
        if self.event.is_set() or self.loop.is_closed():return
        import copy
        value=copy.deepcopy(event)
        future=asyncio.run_coroutine_threadsafe(get_sse_manager().publish(
            self.binding['session_id'],value.get('event_type','trace'),value),self.loop)
        with self._lock:
            self._trace_futures=[item for item in self._trace_futures if not item.done()]
            self._trace_futures.append(future)

    async def flush_traces(self):
        with self._lock:
            futures=list(self._trace_futures);self._trace_futures=[]
        if futures:
            await asyncio.gather(*(asyncio.wrap_future(item) for item in futures),return_exceptions=True)

    def local_mode(self):
        from app.config import get_settings
        return not get_settings().security.auth_enabled and self.binding['owner_id']=='00000000-0000-0000-0000-000000000000'

    def check(self):
        if self.event.is_set():
            from app.llm_budget import TokenBudgetExceeded
            raise TokenBudgetExceeded(self.reason or 'execution_stopped')

    def stop(self,reason):
        with self._lock:
            if self.event.is_set():return
            self.reason=reason;self.event.set();closers=list(self._closers.values())
        for closer in closers:
            if not self.loop.is_closed():self.loop.call_soon_threadsafe(self._close_later,closer)

    def _close_later(self,closer):
        async def close():
            try:await asyncio.to_thread(closer)
            except Exception:logger.info('Execution transport closure did not finish cleanly')
        asyncio.create_task(close())

    def add_closer(self,key,closer):
        with self._lock:
            self._closers[key]=closer;stopped=self.event.is_set()
        if stopped and not self.loop.is_closed():self.loop.call_soon_threadsafe(self._close_later,closer)

    def remove_closer(self,key):
        with self._lock:self._closers.pop(key,None)

    async def status(self):
        from app.db.connection import get_db_pool
        pool=await get_db_pool()
        async with pool.acquire() as conn:
            row=await conn.fetchrow('''SELECT s.execution_id,s.status,p.is_active FROM research_sessions s
                LEFT JOIN auth_principals p ON p.id=s.owner_id WHERE s.id=$1::uuid AND s.owner_id=$2::uuid''',
                self.binding['session_id'],self.binding['owner_id'])
        if row is None or (not row['is_active'] and not self.local_mode()):self.stop('execution_authorization_revoked');return False
        if str(row['execution_id'])!=self.binding['execution_id']:self.stop('execution_superseded');return False
        if row['status']=='canceled':self.stop('execution_canceled');return False
        return row['status']=='running'

    async def observe(self):
        # One root-local observer for cross-worker DB cancellation, no daemon or
        # second source of state. It never launches a model or research step.
        from time import monotonic
        heartbeat=0.0
        while not self.event.is_set():
            try:
                if not await self.status():return
                if monotonic()-heartbeat>=15:
                    from app.db.connection import get_db_pool
                    pool=await get_db_pool()
                    async with pool.acquire() as conn:
                        await conn.execute('''UPDATE session_runtime_state SET last_heartbeat_at=NOW()
                            WHERE session_id=$1::uuid AND EXISTS(SELECT 1 FROM research_sessions s
                                WHERE s.id=$1::uuid AND s.owner_id=$2::uuid
                                  AND s.execution_id=$3::uuid AND s.status='running')''',
                            self.binding['session_id'],self.binding['owner_id'],self.binding['execution_id'])
                    heartbeat=monotonic()
            except Exception:
                self.stop('execution_authorization_unavailable');return
            await asyncio.sleep(.75)

    @asynccontextmanager
    async def publication_gate(self,*,terminal=False):
        if self.event.is_set() and (not terminal or self.reason in {
                'execution_canceled','execution_superseded','execution_authorization_revoked'}):
            yield False;return
        from app.db.connection import get_db_pool
        pool=await get_db_pool()
        async with pool.acquire() as conn,conn.transaction():
            await conn.execute("SELECT set_config('lock_timeout','3000',true)")
            await conn.execute("SELECT set_config('statement_timeout','5000',true)")
            row=await conn.fetchrow('''SELECT s.id FROM research_sessions s LEFT JOIN auth_principals p ON p.id=s.owner_id
                WHERE s.id=$1::uuid AND s.owner_id=$2::uuid AND s.execution_id=$3::uuid
                  AND s.status!='canceled' AND (p.is_active=TRUE OR $4::boolean) FOR SHARE OF s''',
                self.binding['session_id'],self.binding['owner_id'],self.binding['execution_id'],self.local_mode())
            # Cancellation locks the same root row. Enqueue happens before the
            # share lock releases, so it cannot follow a committed cancellation.
            yield bool(row)

    async def _write_model(self,record,admission):
        from app.db.connection import get_db_pool
        from app.db.execution_control import model_receipt
        pool=await get_db_pool()
        async with pool.acquire() as conn,conn.transaction():
            await conn.execute("SELECT set_config('lock_timeout','3000',true)")
            await conn.execute("SELECT set_config('statement_timeout','10000',true)")
            admitted=await model_receipt(conn,self.binding,record,admission=admission)
        if admission and not admitted:await self.status()
        return admitted

    async def tool_receipt(self,binding,payload=None,error=None,*,admission=False):
        from app.db.connection import get_db_pool
        from app.db.execution_control import tool_receipt
        if admission:self.check()
        pool=await get_db_pool()
        async with pool.acquire() as conn,conn.transaction():
            await conn.execute("SELECT set_config('lock_timeout','3000',true)")
            await conn.execute("SELECT set_config('statement_timeout','10000',true)")
            return await tool_receipt(conn,self.binding,binding,payload,error,admission=admission)

    def model_receipt(self,record,*,admission=False,deadline=None):
        """Synchronous model adapters run in worker threads, never block loop."""
        from copy import deepcopy
        from app.llm_budget import TokenBudgetExceeded
        try:
            if asyncio.get_running_loop() is self.loop:
                raise TokenBudgetExceeded('model_dispatch_requires_worker_thread')
        except RuntimeError as error:
            if isinstance(error,TokenBudgetExceeded):raise
        if admission:self.check()
        import time
        remaining=max(.1,deadline-time.monotonic()) if deadline is not None else 15
        value=deepcopy({key:value for key,value in record.items() if key!='started_monotonic'})
        if admission:
            value['admission_expires_at']=(datetime.now(UTC)+timedelta(seconds=remaining)).isoformat()
            record['admission_expires_at']=value['admission_expires_at']
        if self.loop.is_closed():
            if admission:raise TokenBudgetExceeded('model_admission_persistence_unavailable')
            return False
        future=asyncio.run_coroutine_threadsafe(self._write_model(value,admission),self.loop)
        try:return bool(future.result(timeout=min(15,remaining) if admission else 15))
        except Exception as error:
            future.cancel()
            if admission:raise TokenBudgetExceeded('model_admission_persistence_unavailable') from error
            logger.warning('Model settlement remains pending in durable admission receipt')
            return False

    async def finalize_receipts(self):
        from app.db.connection import get_db_pool
        from app.db.execution_control import task_budget,receipt_budget,persist_receipt_budget
        pool=await get_db_pool()
        async with pool.acquire() as conn,conn.transaction():
            row=await conn.fetchrow('SELECT review_status,status,execution_id,total_tokens,total_cost_usd FROM research_sessions WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE',
                self.binding['session_id'],self.binding['owner_id'])
            if row:
                budget=await receipt_budget(conn,self.binding['session_id'],self.binding['owner_id'],task_budget(row))
                await persist_receipt_budget(conn,self.binding['session_id'],self.binding['owner_id'],budget)
        if row and str(row['execution_id'])==self.binding['execution_id']:
            await self.mirror_runtime()

    async def mirror_runtime(self,harness=None):
        """Mirror only the authoritative current execution, holding its share fence.

        File delivery is best effort. A failure here must not spend another
        research attempt or invalidate a DB-committed result.
        """
        from app.db.connection import get_db_pool
        from app.db.execution_control import decoded,task_budget
        try:
            from app.config import get_settings
            from app.governance.harness import HarnessSupervisor
            settings=get_settings();harness=harness or HarnessSupervisor(settings.harness.state_root)
            pool=await get_db_pool()
            async with pool.acquire() as conn,conn.transaction():
                await conn.execute("SELECT set_config('lock_timeout','3000',true)")
                await conn.execute("SELECT set_config('statement_timeout','10000',true)")
                row=await conn.fetchrow('''SELECT s.status,s.review_status,s.total_tokens,s.total_cost_usd,
                    r.runtime_status,r.state_snapshot_json,r.checkpoint_seq,r.current_batch_json
                    FROM research_sessions s LEFT JOIN session_runtime_state r ON r.session_id=s.id
                    WHERE s.id=$1::uuid AND s.owner_id=$2::uuid AND s.execution_id=$3::uuid FOR SHARE OF s''',
                    self.binding['session_id'],self.binding['owner_id'],self.binding['execution_id'])
                if not row:return False
                snapshot=decoded(row['state_snapshot_json']);budget=task_budget(row)
                review=decoded(row['review_status'])
                runtime=({'completed':'completed','failed':'terminal_failed','canceled':'canceled'}.get(row['status'])
                    or review.get('runtime_status') or row['runtime_status'] or row['status'])
                pending=snapshot.get('pending_approvals') or []
                write=asyncio.create_task(asyncio.to_thread(harness.upsert_task,session_id=self.binding['session_id'],public_status=row['status'],
                    runtime_status=runtime,budget=budget,current_batch=snapshot.get('current_executing_nodes') or [],
                    pending_approval_id=pending[-1].get('approval_id') if pending else None,
                    checkpoint_seq=int(row['checkpoint_seq'] or 0),
                    used_total_tokens=int(budget.get('used_total_tokens') or 0),used_cost_usd=float(budget.get('used_cost_usd') or 0),
                    last_error=review.get('workflow_failure') or ({'category':review['last_error_category']}
                        if review.get('last_error_category') else None),
                    worker_id=settings.harness.worker_id,state_snapshot=snapshot))
                interrupted=False
                while True:
                    try:
                        await asyncio.shield(write)
                        break
                    except asyncio.CancelledError:
                        if write.cancelled():raise
                        # A thread cannot be canceled. Keep the DB fence until
                        # its bounded file write ends, even if the host stops us.
                        interrupted=True
                if interrupted:raise asyncio.CancelledError
            await asyncio.to_thread(harness.clear_active_if_idle)
            return True
        except Exception:
            logger.warning('Runtime file mirror unavailable; committed DB state remains authoritative')
            return False

    async def persist_failure(self,error,category='workflow_error'):
        from app.db.connection import get_db_pool
        from app.db.execution_control import persist_workflow_failure
        pool=await get_db_pool()
        async with pool.acquire() as conn,conn.transaction():
            await conn.execute("SELECT set_config('lock_timeout','3000',true)")
            await conn.execute("SELECT set_config('statement_timeout','10000',true)")
            return await persist_workflow_failure(conn,self.binding,error,category)


def controlled_execution(function):
    signature=inspect.signature(function)
    @functools.wraps(function)
    async def run(*args,**kwargs):
        values=signature.bind_partial(*args,**kwargs).arguments
        if not values.get('owner_id') or not values.get('execution_id'):
            raise ValueError('owned_execution_required')
        control=ExecutionControl(values['session_id'],values['owner_id'],values['execution_id'])
        if not await control.status():return
        key=(control.binding['session_id'],control.binding['execution_id'])
        with _active_lock:
            if key in _active:return  # Same local run cannot dispatch twice.
            _active[key]=control
        token=_current.set(control);watcher=asyncio.create_task(control.observe())
        try:return await function(*args,**kwargs)
        except asyncio.CancelledError as error:
            control.stop('execution_interrupted')
            try:await control.persist_failure(error,'execution_interrupted')
            except Exception:logger.warning('Interrupted execution state could not be saved; retained checkpoints remain authoritative')
            raise
        finally:
            watcher.cancel()
            try:await watcher
            except asyncio.CancelledError:pass
            try:await control.finalize_receipts()
            except Exception:logger.warning('Execution receipt reconciliation remains pending')
            with _active_lock:
                if _active.get(key) is control:_active.pop(key,None)
            _current.reset(token)
    return run
