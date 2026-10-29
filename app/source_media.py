"""Source-page delivery orchestration; existing acquisition and audit own facts."""
from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path

from app.db.source_assets import PAGE_RENDERER,current_original,current_page,retain_page
from app.source_figure_locations import select_source_pages

POLICY='adrs-source-media-v2'


def _rasterize(original,pages,timeout):
    from app.research_figures import run_renderer
    completed=run_renderer([sys.executable,'-m','app.source_page_renderer'],
        json.dumps({'pdf':base64.b64encode(original).decode('ascii'),'pages':pages}),
        timeout=timeout,cwd=str(Path(__file__).resolve().parent.parent),env=dict(os.environ))
    if completed.returncode!=0:raise ValueError('source_page_renderer_failed')
    if len(completed.stdout)>16_100_000:raise ValueError('source_page_result_byte_limit')
    result=json.loads(completed.stdout)
    if (result.get('renderer')!=PAGE_RENDERER or not isinstance(result.get('pages'),list)
            or len(result['pages'])!=len(pages) or {row.get('page') for row in result['pages']}!=set(pages)):
        raise ValueError('source_page_renderer_binding_invalid')
    return result['pages']


async def prepare_source_media(state,organization_result,*,deadline):
    from app.db.connection import get_db_pool
    from app.execution_control import current_control
    from app.llm_budget import TokenBudgetExceeded
    from app.source_lifecycle import current_synthesis_state
    from app.planning_control import retained_evidence_version
    result={'policy':POLICY,'status':'ready','pages':[],'pending':[],'model_calls':0,'network_calls':0,
        'presentation':'original_pdf_page_not_segmented_figure',
        'evidence_version':retained_evidence_version(state)}
    selected=select_source_pages((organization_result or {}).get('technical_reading'),state.get('collected_evidence'))
    result['pending']=selected['pending']
    # A missing or ambiguous caption remains a documented source gap; it does
    # not authorize guessing an image. An eligible page that fails rendering
    # is a delivery failure, never silently counted as illustrated.
    if not selected['pages']:return {**result,'status':'no_located_pages'}
    control=current_control()
    if control is None:return {**result,'status':'blocked','reason':'source_media_execution_binding_unavailable'}
    cutoff=min(time.monotonic()+45,deadline) if deadline is not None else time.monotonic()+45
    sources={item['evidence_id']:item for item in state.get('collected_evidence',[])}
    groups={}
    for page in selected['pages']:groups.setdefault(page['asset_id'],[]).append(page)
    try:
        current=await current_synthesis_state(state)
        if current.get('collected_evidence')!=state.get('collected_evidence'):
            raise ValueError('source_media_current_access_changed')
        pool=await get_db_pool()
        for asset_id,pages in groups.items():
            control.check()
            if time.monotonic()>=cutoff:raise ValueError('source_media_original_deadline_exhausted')
            evidence=sources[pages[0]['evidence_ids'][0]]
            async with pool.acquire() as conn:
                original=await current_original(conn,state['task_id'],control.binding['owner_id'],evidence)
                cached={}
                for page in pages:
                    cached[page['page']]=await current_page(conn,state['task_id'],control.binding['owner_id'],evidence,page['page'])
            missing=[page['page'] for page in pages if not cached[page['page']]]
            if missing:
                remaining=cutoff-time.monotonic()
                if remaining<=0:raise ValueError('source_media_original_deadline_exhausted')
                pixels=await asyncio.to_thread(_rasterize,original['original_bytes'],missing,min(15,remaining))
                async with pool.acquire() as conn,conn.transaction():
                    await conn.execute("SELECT set_config('lock_timeout','1500',true)")
                    await conn.execute("SELECT set_config('statement_timeout','6000',true)")
                    for row in pixels:
                        control.check()
                        if time.monotonic()>=cutoff:raise ValueError('source_media_original_deadline_exhausted')
                        await retain_page(conn,control.binding,asset_id,row['page'],base64.b64decode(row['png'],validate=True),
                            row['width'],row['height'],local_mode=control.local_mode())
                        cached[row['page']]={'width':row['width'],'height':row['height']}
            for page in pages:
                pixel=cached[page['page']]
                result['pages'].append({**page,'renderer':PAGE_RENDERER,'width':pixel['width'],'height':pixel['height']})
        result['status']='rendered'
        return result
    except TokenBudgetExceeded:raise
    except Exception as error:
        control.check()
        reason=str(error) if isinstance(error,ValueError) and str(error).startswith('source_') else 'source_media_render_unavailable'
        return {**result,'status':'blocked','reason':reason}


async def hydrate_source_media(conn,state,organization_result,owner_id):
    """Read saved pixels for the current authorized snapshot, never render here."""
    from app.planning_control import retained_evidence_version
    media=(organization_result or {}).get('source_media')
    if not media:return {'status':'legacy_no_original_pages','pages':[]}
    if media.get('policy')!=POLICY or media.get('evidence_version')!=retained_evidence_version(state):
        raise ValueError('source_media_current_version_changed')
    if media.get('status') not in {'rendered','no_located_pages'}:raise ValueError('source_media_not_complete')
    selected=select_source_pages((organization_result or {}).get('technical_reading'),state.get('collected_evidence'))
    expected={(page['asset_id'],page['page']):page for page in selected['pages']}
    stored=media.get('pages') or []
    if len(stored)!=len(expected):raise ValueError('source_media_current_locations_changed')
    sources={item['evidence_id']:item for item in state.get('collected_evidence',[])}
    pages=[]
    for row in stored:
        key=(row.get('asset_id'),row.get('page'));location=expected.pop(key,None)
        if not location or any(row.get(field)!=location[field] for field in location):
            raise ValueError('source_media_current_locations_changed')
        pixel=await current_page(conn,state['task_id'],owner_id,sources[location['evidence_ids'][0]],location['page'])
        if not pixel or pixel['width']!=row.get('width') or pixel['height']!=row.get('height'):
            raise ValueError('source_media_page_unavailable')
        pages.append({**row,'png':'data:image/png;base64,'+base64.b64encode(pixel['png']).decode('ascii')})
    return {'status':media['status'],'pages':pages}


async def owned_delivery_snapshot(session_id,owner_id,*,execution_id=None,report=None):
    """Download/read authority comes from the live task, not a media pointer."""
    from app.db.connection import get_db_pool
    from app.db.execution_control import decoded
    from app.source_lifecycle import current_synthesis_state
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        row=await conn.fetchrow('''SELECT s.status,s.execution_id,s.final_report,r.state_snapshot_json
            FROM research_sessions s JOIN session_runtime_state r ON r.session_id=s.id
            WHERE s.id=$1::uuid AND s.owner_id=$2::uuid''',str(session_id),str(owner_id))
    if row is None:raise ValueError('source_media_task_not_found')
    state=decoded(row['state_snapshot_json']);root=state.get('session') or {}
    if (row['status']!='completed' or not row['final_report']
            or str(root.get('owner_id'))!=str(owner_id) or str(state.get('task_id'))!=str(session_id)
            or str(root.get('session_id'))!=str(session_id) or str(root.get('execution_id'))!=str(row['execution_id'])
            or (execution_id is not None and str(row['execution_id'])!=str(execution_id))
            or (report is not None and row['final_report']!=report)):
        raise ValueError('source_media_task_binding_changed')
    current=await current_synthesis_state(state)
    if current.get('collected_evidence')!=state.get('collected_evidence'):
        raise ValueError('source_media_current_access_changed')
    return state
