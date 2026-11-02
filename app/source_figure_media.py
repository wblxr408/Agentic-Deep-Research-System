"""Owned figure-group delivery using the original acquisition and asset store."""
from __future__ import annotations

import asyncio
import base64
import time
import re
from copy import deepcopy

from app.source_figure_extraction import MEDIA_POLICY,EXTRACTOR,extract_figure_layout,match_figure,renderer_key,rasterize_figures
from app.source_figure_locations import select_source_pages
from app.db.source_assets import current_original,current_page,retain_page,current_figure_layout,retain_figure_layout


def report_sources(state,report=None,citations=None):
    from app.query_understanding import identity
    report=state.get('final_report') if report is None else report
    citations=state.get('citations') if citations is None else citations
    rows=[row.model_dump() if hasattr(row,'model_dump') else row for row in citations or []]
    if not isinstance(report,str) or not report.strip():raise ValueError('source_figure_report_binding_unavailable')
    mapping=[{'citation_id':row['citation_id'],'evidence_id':(row.get('locator') or {}).get('evidence_id')} for row in rows]
    used={'citation:'+number for number in re.findall(r'\[(?:citation:)?(\d+)\]',report)}
    return {row['evidence_id'] for row in mapping if row['citation_id'] in used and row['evidence_id']},identity({'report':report,'citations':mapping})


def select_figures(result,state,*,report=None,citations=None):
    used,binding=report_sources(state,report,citations)
    reading=(result or {}).get('technical_reading') or {};metadata=(result or {}).get('publication_metadata') or {}
    selected=[]
    for card in reading.get('cards') or []:
        sources=set((metadata.get(card.get('output_id')) or {}).get('evidence_ids') or [])
        sources.update(proof.get('evidence_id') for field in (card.get('fields') or {}).values() for proof in field.get('proofs') or [])
        sources.update((ref.get('proof') or {}).get('evidence_id') for ref in card.get('figure_references') or [])
        if used.intersection(sources):selected.append(card)
    result=select_source_pages({**reading,'cards':selected},state.get('collected_evidence'),
        max_pages=2000,per_output=20,locate_captions=True,figure_mode=True)
    result['report_binding']=binding
    return result


def page_figures(page,layout):
    selected=[];pending=[]
    for target in page['targets']:
        try:
            region=match_figure(layout,page=page['page'],label=target['label'],
                caption_quote=target['proofs'][0]['quote'])
            selected.append({'label':target['label'],'figure_id':region['figure_id'],
                'layout':region,'renderer':renderer_key(region)})
        except ValueError as error:
            pending.append({'asset_id':page['asset_id'],'page':page['page'],'label':target['label'],'reason':str(error)})
    return selected,pending


def _reuse_explanations(result,previous):
    if previous.get('policy')!=MEDIA_POLICY or previous.get('evidence_version')!=result['evidence_version']:return
    old={(row['asset_id'],row['page']):row for row in previous.get('pages',[])}
    complete=True
    for page in result['pages']:
        saved=old.get((page['asset_id'],page['page'])) or {}
        if not all(saved.get(key)==value for key,value in page.items()):complete=False;continue
        for key in ('explanation','report_anchor','explanation_binding','explanation_basis',
                'explanation_claim_context','explanation_draft'):
            if key in saved:page[key]=saved[key]
    if complete:
        for key in ('explanation_binding','explanation_model','explanation_status','explanation_contract','model_calls'):
            if key in previous:result[key]=previous[key]


async def prepare_source_figures(state,organization_result,*,deadline,report=None,citations=None):
    from app.db.connection import get_db_pool
    from app.execution_control import current_control
    from app.llm_budget import TokenBudgetExceeded
    from app.planning_control import retained_evidence_version
    from app.source_lifecycle import current_synthesis_state
    try:selected=select_figures(organization_result,state,report=report,citations=citations)
    except ValueError as error:return {'policy':MEDIA_POLICY,'status':'blocked','pages':[],'reason':str(error)}
    result={'policy':MEDIA_POLICY,'status':'ready','presentation':'original_pdf_figure_groups',
        'pages':[],'pending':deepcopy(selected['pending']),'model_calls':0,'network_calls':0,
        'evidence_version':retained_evidence_version(state),'report_binding':selected['report_binding'],
        'layout_cache_hits':0,'figure_cache_hits':0}
    # A corrected model-supplied page is diagnostic; the retained caption's
    # actual page remains authoritative. Other omitted targets remain gaps.
    hard_pending=[item for item in selected['pending'] if item['reason']!='requested_page_conflicts']
    if not selected['pages']:
        return {**result,'status':'blocked' if hard_pending else 'no_located_pages',
            **({'reason':'source_figure_locations_incomplete'} if hard_pending else {})}
    control=current_control()
    if control is None:return {**result,'status':'blocked','reason':'source_media_execution_binding_unavailable'}
    # A finite root deadline is the time authority for the full collection.
    # Per-call bounds remain below; a compatibility call without one is bounded.
    cutoff=deadline if deadline is not None else time.monotonic()+900
    def remaining(limit):
        control.check();seconds=cutoff-time.monotonic()
        if seconds<=0:raise ValueError('source_figure_original_deadline_exhausted')
        return min(limit,seconds)
    groups={};sources={row['evidence_id']:row for row in state.get('collected_evidence',[])}
    for page in selected['pages']:groups.setdefault(page['asset_id'],[]).append(page)
    try:
        current=await current_synthesis_state(state)
        if current.get('collected_evidence')!=state.get('collected_evidence'):raise ValueError('source_media_current_access_changed')
        pool=await get_db_pool()
        for asset_id,pages in groups.items():
            remaining(45);evidence=sources[pages[0]['evidence_ids'][0]]
            async with pool.acquire() as conn:
                original=await current_original(conn,state['task_id'],control.binding['owner_id'],evidence)
                layout=await current_figure_layout(conn,state['task_id'],control.binding['owner_id'],evidence)
            if layout is None:
                layout=await asyncio.to_thread(extract_figure_layout,original['original_bytes'],timeout=remaining(45))
                async with pool.acquire() as conn,conn.transaction():
                    await conn.execute("SELECT set_config('lock_timeout','1500',true)")
                    await conn.execute("SELECT set_config('statement_timeout','6000',true)")
                    remaining(45)
                    await retain_figure_layout(conn,control.binding,evidence,layout,local_mode=control.local_mode())
            else:result['layout_cache_hits']+=1
            if layout.get('extractor')!=EXTRACTOR:raise ValueError('source_figure_layout_version_changed')
            prepared=[];all_figures={}
            for page in pages:
                figures,pending=page_figures(page,layout)
                result['pending'].extend(pending);hard_pending.extend(pending)
                prepared.append({**page,'figures':figures})
                for figure in figures:all_figures[figure['figure_id']]=figure
            pixels={};missing=[]
            async with pool.acquire() as conn:
                for key,figure in all_figures.items():
                    remaining(15)
                    cached=await current_page(conn,state['task_id'],control.binding['owner_id'],evidence,
                        figure['layout']['page'],renderer=figure['renderer'])
                    if cached:
                        pixels[key]={'width':cached['width'],'height':cached['height']};result['figure_cache_hits']+=1
                    else:missing.append(figure['layout'])
            for offset in range(0,len(missing),8):
                rendered=await asyncio.to_thread(rasterize_figures,original['original_bytes'],missing[offset:offset+8],timeout=remaining(15))
                async with pool.acquire() as conn,conn.transaction():
                    await conn.execute("SELECT set_config('lock_timeout','1500',true)")
                    await conn.execute("SELECT set_config('statement_timeout','6000',true)")
                    for pixel in rendered:
                        remaining(15)
                        await retain_page(conn,control.binding,asset_id,pixel['page'],base64.b64decode(pixel['png'],validate=True),
                            pixel['width'],pixel['height'],renderer=pixel['renderer'],local_mode=control.local_mode())
                        pixels[pixel['figure_id']]={'width':pixel['width'],'height':pixel['height']}
            for page in prepared:
                for figure in page['figures']:figure.update(pixels[figure['figure_id']])
                result['pages'].append(page)
        result['status']='blocked' if hard_pending else 'rendered'
        if hard_pending:result['reason']='source_figure_targets_incomplete'
        else:_reuse_explanations(result,(organization_result or {}).get('source_media') or {})
        return result
    except TokenBudgetExceeded:raise
    except Exception as error:
        control.check()
        reason=str(error) if isinstance(error,ValueError) and str(error).startswith('source_') else 'source_figure_preparation_unavailable'
        return {**result,'status':'blocked','reason':reason}


async def hydrate_source_figures(conn,state,organization_result,owner_id):
    """Current source and immutable layout/pixels only; no parser or write on GET."""
    from app.planning_control import retained_evidence_version
    media=(organization_result or {}).get('source_media') or {}
    if media.get('policy')!=MEDIA_POLICY or media.get('evidence_version')!=retained_evidence_version(state):
        raise ValueError('source_media_current_version_changed')
    if media.get('status') not in {'rendered','no_located_pages'}:raise ValueError('source_media_not_complete')
    selected=select_figures(organization_result,state)
    if media.get('report_binding')!=selected['report_binding']:raise ValueError('source_figure_report_binding_changed')
    expected={(row['asset_id'],row['page']):row for row in selected['pages']}
    if len(media.get('pages') or [])!=len(expected):raise ValueError('source_media_current_locations_changed')
    sources={row['evidence_id']:row for row in state.get('collected_evidence',[])};layouts={};pages=[]
    for row in media.get('pages') or []:
        key=(row.get('asset_id'),row.get('page'));location=expected.pop(key,None)
        if not location or any(row.get(field)!=value for field,value in location.items()):
            raise ValueError('source_media_current_locations_changed')
        evidence=sources[location['evidence_ids'][0]]
        if key[0] not in layouts:layouts[key[0]]=await current_figure_layout(conn,state['task_id'],owner_id,evidence)
        if not layouts[key[0]]:raise ValueError('source_figure_layout_missing')
        figures,pending=page_figures(location,layouts[key[0]])
        if pending or len(figures)!=len(row.get('figures') or []):raise ValueError('source_figure_targets_changed')
        stored={figure['figure_id']:figure for figure in row['figures']};hydrated=[]
        if len(stored)!=len(figures):raise ValueError('source_figure_targets_changed')
        for figure in figures:
            saved=stored.get(figure['figure_id'])
            if not saved or any(saved.get(field)!=value for field,value in figure.items()):
                raise ValueError('source_figure_layout_version_changed')
            pixel=await current_page(conn,state['task_id'],owner_id,evidence,location['page'],renderer=figure['renderer'])
            if not pixel or any(pixel[field]!=saved.get(field) for field in ('width','height')):
                raise ValueError('source_figure_pixels_unavailable')
            hydrated.append({**saved,'png':'data:image/png;base64,'+base64.b64encode(pixel['png']).decode('ascii')})
        pages.append({**row,'figures':hydrated})
    live=await conn.fetchrow('''SELECT status,execution_id,final_report FROM research_sessions
        WHERE id=$1::uuid AND owner_id=$2::uuid''',str(state['task_id']),str(owner_id))
    if (not live or live['status']!='completed'
            or str(live['execution_id'])!=str((state.get('session') or {}).get('execution_id'))
            or live['final_report']!=state.get('final_report')):
        raise ValueError('source_media_task_binding_changed')
    return {**media,'pages':pages}
