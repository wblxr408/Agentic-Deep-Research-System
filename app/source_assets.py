"""Capture already-fetched originals without another network or model call."""
from __future__ import annotations

import asyncio
import time


async def _retain(control,source_url,original,retained_text,deadline):
    from app.db.connection import get_db_pool
    from app.db.source_assets import retain_original
    control.check()
    if time.monotonic()>=deadline:raise TimeoutError('source_asset_deadline')
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await conn.execute("SELECT set_config('lock_timeout','1500',true)")
        await conn.execute("SELECT set_config('statement_timeout','6000',true)")
        control.check()
        if time.monotonic()>=deadline:raise TimeoutError('source_asset_deadline')
        return await retain_original(conn,control.binding,source_url,original,retained_text,local_mode=control.local_mode())


def retain_acquired_pdf(source_url,original,retained_text,*,deadline):
    from app.execution_control import current_control
    from app.llm_budget import TokenBudgetExceeded
    control=current_control()
    unavailable=lambda reason:{'status':'not_retained','format':'pdf','reason':reason}
    if control is None:return unavailable('source_asset_execution_binding_unavailable')
    control.check()
    remaining=deadline-time.monotonic()
    if remaining<=0:return unavailable('source_asset_acquisition_deadline')
    if control.loop.is_closed():return unavailable('source_asset_execution_loop_closed')
    try:
        if asyncio.get_running_loop() is control.loop:return unavailable('source_asset_requires_worker_thread')
    except RuntimeError:pass
    future=asyncio.run_coroutine_threadsafe(_retain(control,source_url,original,retained_text,deadline),control.loop)
    try:
        result=future.result(timeout=min(8,remaining))
        control.check()
        return result
    except TokenBudgetExceeded:
        future.cancel();raise
    except Exception as error:
        future.cancel();control.check()
        # Storage failure is a declared delivery gap, never a claim that pixels
        # have been acquired. Do not expose SQL, credentials or source text.
        code=str(error) if isinstance(error,ValueError) and str(error).startswith('source_asset_') else 'source_asset_persistence_unavailable'
        return unavailable(code)
