"""User-selected root limits and model-free advice; no execution authority."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from math import ceil
import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ResearchLimits(BaseModel):
    model_config = ConfigDict(extra='forbid')
    max_total_tokens: int = Field(ge=4000, le=2_000_000, strict=True)
    max_tool_calls: int = Field(ge=1, le=256, strict=True)
    max_wall_clock_seconds: int = Field(ge=60, le=21600, strict=True)


class BudgetRevision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    limits: ResearchLimits
    expected_revision: int = Field(ge=0, strict=True)
    execution_id: UUID
    request_id: UUID


def limits_view(budget):
    return {key:int(budget.get(key) or 0) for key in ResearchLimits.model_fields}


def recommend_limits(payload):
    """Initial configuration estimate; not a usage forecast or price quote."""
    from app.guardrails import get_research_budget
    from app.organization_purpose import DEFAULTS
    from app.query_understanding import query_classification
    options=payload.get('query_options') or {}
    organization=payload.get('organization_research') or {}
    scope=organization.get('scope') or {}
    delivery=payload.get('delivery') or {}
    entities=max(1,len(scope.get('entities') or options.get('entities') or []))
    modules=organization.get('modules') or options.get('modules') or (
        DEFAULTS.get(organization.get('purpose') or options.get('purpose'),()) if organization or options.get('purpose') else ())
    query_type,_=query_classification(payload.get('query',''),options.get('query_type'))
    depth=options.get('depth','auto')
    if depth=='auto':depth='brief' if query_type=='fact' else 'standard'
    deep=depth=='deep' or 'deep_dive' in modules
    complex_task=deep or query_type=='multi_hop' or entities>1 or len(modules)>=4
    level='complex' if complex_task else 'simple' if depth=='brief' else 'moderate'
    margin={'simple':35,'moderate':50,'complex':75}[level]
    illustrated=delivery.get('template','markdown-v1')!='markdown-v1' or delivery.get('drawing_mode','builtin')!='builtin'
    base=get_research_budget(payload.get('output_length'))
    tokens=(12000 if depth=='brief' else 28000)+16000*entities+14000*len(modules)
    if deep:tokens+=85000+18000*entities
    if illustrated:tokens+=16000
    # A long factual report needs a full audit, including a possible revision.
    audit=12000 if depth=='brief' else 45000 if not modules else 18000*len(modules)
    tokens+=audit
    calls=4+entities*4+len(modules)*2+(12 if deep else 0)
    seconds=180+entities*120+len(modules)*180+(900 if deep else 0)+(180 if illustrated else 0)
    workload=None
    corpus=organization.get('corpus') or {}
    organization_task=bool(organization or options.get('entities') or re.search(
        r'大学|学院|实验室|研究院|研究所|公司|\buniversity\b|\blaborator(?:y|ies)\b',payload.get('query',''),re.I))
    if deep and organization_task and corpus.get('collection_mode')!='seeds_only':
        # Capacity describes possible reads, not additional permissions. Root
        # consumers still stop when no useful current source remains.
        read_slots=24
        representative_count=max(4,min(20,entities))
        extraction_batches=ceil(read_slots/4)
        analysis_calls=extraction_batches+max(0,len(modules)-1)+2*ceil(representative_count/2)
        collection_seconds=read_slots*75+90
        analysis_seconds=analysis_calls*75
        delivery_seconds=max(300,len(modules)*90+180)+(60 if illustrated else 0)
        calls=max(calls,(read_slots+3)*3)
        seconds=max(seconds,180+collection_seconds+analysis_seconds+delivery_seconds)
        workload={'source_read_capacity':read_slots,'representative_reading_capacity':representative_count,
            'estimated_analysis_calls':analysis_calls,'collection_seconds':collection_seconds,
            'analysis_seconds':analysis_seconds,'delivery_seconds':delivery_seconds,
            'basis':'bounded_read_paths_stage_outputs_and_final_audit_not_a_service_latency_guarantee'}
    estimated={'max_total_tokens':min(1_100_000,ceil(tokens/1000)*1000),
               'max_tool_calls':min(140,calls),'max_wall_clock_seconds':min(12000,ceil(seconds/60)*60)}
    recommended={key:max(int(base[key]),ceil(value*(1+margin/100)/unit)*unit)
        for key,value,unit in [(key,value,10000 if key=='max_total_tokens' else 60 if key=='max_wall_clock_seconds' else 1)
                               for key,value in estimated.items()]}
    recommended=ResearchLimits.model_validate(recommended).model_dump()
    return {'version':'adrs-limit-advice-v2','complexity':level,'headroom_percent':margin,
            'estimated':estimated,'recommended':recommended,'defaults':limits_view(base),
            'basis':{'entity_count':entities,'module_count':len(modules),'depth':depth,'illustrated':illustrated,
                'query_type':query_type,**({'workload':workload} if workload else {})},
            'method':'configuration_rules_no_model_call','cost_usd':None}


def selected_budget(base, limits):
    budget=deepcopy(base)
    if limits is None:return budget
    values=limits.model_dump() if isinstance(limits,ResearchLimits) else ResearchLimits.model_validate(limits).model_dump()
    budget.update(values,budget_policy_version=3,
        audit_token_reserve=int(values['max_total_tokens']*.30),
        report_token_reserve=int(values['max_total_tokens']*.10),
        audit_seconds_reserve=min(1200,int(values['max_wall_clock_seconds']*.20)),
        budget_selection='explicit_user_limits')
    return budget


async def read_budget(conn, session_id, owner_id, *, locked=False):
    from app.db.execution_control import decoded,task_budget,receipt_budget
    row=await conn.fetchrow('''SELECT s.status,s.execution_id,s.created_at,s.request_payload,
        s.review_status,s.total_tokens,s.total_cost_usd,r.state_snapshot_json,r.checkpoint_seq
        FROM research_sessions s JOIN session_runtime_state r ON r.session_id=s.id
        WHERE s.id=$1::uuid AND s.owner_id=$2::uuid'''+(' FOR UPDATE OF s,r' if locked else ''),str(session_id),str(owner_id))
    if not row:raise ValueError('budget_task_not_found')
    state=deepcopy(decoded(row['state_snapshot_json']))
    budget=await receipt_budget(conn,session_id,owner_id,task_budget(row))
    advice=recommend_limits(decoded(row['request_payload']))
    start=row['created_at']
    if start.tzinfo is None:start=start.replace(tzinfo=UTC)
    elapsed=max(0,int((datetime.now(UTC)-start).total_seconds()))
    advice['recommended']={key:max(value,int(budget.get(key) or 0)) for key,value in advice['recommended'].items()}
    for key,value in {'max_total_tokens':int(budget.get('used_total_tokens') or 0)+20000,
                      'max_tool_calls':int(budget.get('used_tool_calls') or 0)+3,
                      'max_wall_clock_seconds':elapsed+600}.items():
        ceiling={'max_total_tokens':2_000_000,'max_tool_calls':256,'max_wall_clock_seconds':21600}[key]
        advice['recommended'][key]=min(ceiling,max(advice['recommended'][key],value))
    advice['recommended']['max_wall_clock_seconds']=min(21600,ceil(advice['recommended']['max_wall_clock_seconds']/60)*60)
    view={'session_id':str(session_id),'execution_id':str(row['execution_id']),
          'status':row['status'],'revision':int(budget.get('budget_revision') or 0),'limits':limits_view(budget),
          'usage':{'tokens':int(budget.get('used_total_tokens') or 0),'tool_calls':int(budget.get('used_tool_calls') or 0),
                   'elapsed_seconds':elapsed},'advice':advice,
          'adjustments':budget.get('budget_adjustments') or []}
    return row,state,budget,view


async def revise_budget(conn,session_id,owner_id,request):
    from app.db.execution_control import decoded,persist_receipt_budget
    from app.db.json import dumps_json
    await conn.execute("SELECT set_config('lock_timeout','3000',true)")
    row,state,budget,view=await read_budget(conn,session_id,owner_id,locked=True)
    history=list(budget.get('budget_adjustments') or [])
    values=request.limits.model_dump()
    for event in history:
        if event['request_id']==str(request.request_id):
            if (event['limits']!=values or event['execution_id']!=str(request.execution_id)
                    or event['previous_revision']!=request.expected_revision):
                raise ValueError('budget_request_conflict')
            return {**view,'replayed':True}
    if row['status']!='paused' or state.get('status')!='paused':raise ValueError('budget_pause_required')
    session=state.get('session') or {}
    if (str(row['execution_id'])!=str(request.execution_id) or
            str(session.get('execution_id'))!=str(request.execution_id) or
            str(session.get('owner_id'))!=str(owner_id) or str(state.get('task_id'))!=str(session_id) or
            str(session.get('session_id'))!=str(session_id)):
        raise ValueError('budget_execution_changed')
    if view['revision']!=request.expected_revision:raise ValueError('budget_revision_changed')
    if (budget.get('inflight_model_requests') or budget.get('reserved_inflight_tokens') or
            budget.get('reserved_inflight_tool_calls')):raise ValueError('budget_requests_inflight')
    if view['usage']['tokens']>=2_000_000 or view['usage']['tool_calls']>256 or view['usage']['elapsed_seconds']>=21600:
        raise ValueError('budget_new_research_required')
    if (values['max_total_tokens']<=view['usage']['tokens'] or values['max_tool_calls']<view['usage']['tool_calls'] or
            values['max_wall_clock_seconds']<=view['usage']['elapsed_seconds']):
        raise ValueError('budget_below_used_allowance')
    review=deepcopy(decoded(row['review_status']))
    event={'revision':view['revision']+1,'previous_revision':view['revision'],'request_id':str(request.request_id),
           'execution_id':str(request.execution_id),'owner_id':str(owner_id),'at':datetime.now(UTC).isoformat(),
           'previous_limits':view['limits'],'limits':values,'usage_at_revision':view['usage'],
           'previous_stop_reason':review.get('reason'),'authority':'explicit_owner_budget_revision'}
    budget=selected_budget(budget,request.limits)
    budget.update(budget_revision=event['revision'],budget_adjustments=[*history,event],
                  elapsed_wall_clock_seconds=view['usage']['elapsed_seconds'])
    # New limits do not clear provider, authorization, receipt or cost guards.
    resettable={'token_limit','tool_call_limit','wall_clock_limit','final_audit_budget_exhausted','model_time_reservation_exhausted',
        'token_budget_exhausted','tool_budget_exhausted','time_budget_exhausted',
        'model_token_budget_exhausted','model_time_budget_exhausted'}
    for field in ('hard_stop_reason','model_stop_reason'):
        if budget.get(field) in resettable:budget[field]=None
    # A budget change can expose the existing unfinished-audit continuation;
    # it never approves claims or resets that continuation's attempt counter.
    if (review.get('reason')=='final_audit_budget_exhausted' and
            (review.get('final_report_audit') or {}).get('audit_incomplete')):
        review.update(reason='final_audit_incomplete',runtime_status='report_paused')
        state['runtime_status']='report_paused'
    state.update(budget_state=budget,review_status={**review,'budget_state':budget})
    await conn.execute('''UPDATE research_sessions SET review_status=$3::jsonb,updated_at=NOW()
        WHERE id=$1::uuid AND owner_id=$2::uuid''',str(session_id),str(owner_id),dumps_json(state['review_status']))
    await conn.execute('''UPDATE session_runtime_state SET state_snapshot_json=$2::jsonb,
        runtime_status=$3,checkpoint_seq=checkpoint_seq+1 WHERE session_id=$1::uuid''',
        str(session_id),dumps_json(state),state.get('runtime_status','analysis_paused'))
    await persist_receipt_budget(conn,session_id,owner_id,budget)
    await conn.execute('''UPDATE session_budget_state SET max_total_tokens=$2,max_tool_calls=$3,
        max_wall_clock_seconds=$4 WHERE session_id=$1::uuid''',str(session_id),values['max_total_tokens'],
        values['max_tool_calls'],values['max_wall_clock_seconds'])
    return {**view,'revision':event['revision'],'limits':values,'adjustments':[*history,event],'replayed':False}
