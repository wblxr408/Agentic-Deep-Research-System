"""Cancellation and model receipts share the existing task owner/row lock."""
from __future__ import annotations

import json
from datetime import UTC,datetime

from app.disclosure import projection
from app.query_understanding import identity

SCHEMA_SQL='''
CREATE TABLE IF NOT EXISTS research_cancellations (
 owner_id UUID NOT NULL, request_id UUID NOT NULL, session_id UUID NOT NULL REFERENCES research_sessions(id) ON DELETE CASCADE,
 execution_id UUID, fingerprint TEXT NOT NULL, response JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(owner_id,request_id)
);
CREATE TABLE IF NOT EXISTS research_model_receipts (
 call_id UUID PRIMARY KEY, owner_id UUID NOT NULL, session_id UUID NOT NULL REFERENCES research_sessions(id) ON DELETE CASCADE,
 execution_id UUID NOT NULL, payload JSONB NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_model_receipts_owner_task ON research_model_receipts(owner_id,session_id,updated_at,call_id);
CREATE TABLE IF NOT EXISTS research_tool_receipts (
 operation_id TEXT PRIMARY KEY,owner_id UUID NOT NULL,session_id UUID NOT NULL REFERENCES research_sessions(id) ON DELETE CASCADE,
 execution_id UUID NOT NULL,payload JSONB NOT NULL,updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tool_receipts_owner_task ON research_tool_receipts(owner_id,session_id,updated_at,operation_id);
'''


def decoded(value):
    value=json.loads(value) if isinstance(value,str) else value
    return value if isinstance(value,dict) else {}


def task_budget(row):
    review=decoded(row['review_status'])
    value=dict(review.get('budget_state') or review.get('initial_budget') or {})
    value['used_total_tokens']=max(int(value.get('used_total_tokens') or 0),int(row.get('total_tokens') or 0))
    value['used_cost_usd']=max(float(value.get('used_cost_usd') or 0),float(row.get('total_cost_usd') or 0))
    return value


def repeated_rollup_usage(rollups):
    """Find proven repeats of the same settled call in cumulative summaries.

    Unknown identities, incomplete summaries and conflicting amounts remain
    charged. This reads bookkeeping observations, never refunds provider work.
    """
    tokens={};costs={}
    for summary in rollups:
        calls=summary.get('model_requests')
        if not isinstance(calls,list) or not calls or any(not isinstance(call,dict)
                or not isinstance(call.get('call_id'),str) or not call['call_id']
                or call.get('status')!='settled' or call.get('estimated') is True
                or type(call.get('total_tokens')) is not int
                or call['total_tokens']<0 for call in calls):continue
        if sum(call['total_tokens'] for call in calls)!=int(summary.get('total_tokens') or 0):continue
        known_cost=all(isinstance(call.get('cost_usd'),(int,float)) and call['cost_usd']>=0 for call in calls)
        cost_covered=known_cost and abs(sum(call['cost_usd'] for call in calls)-float(summary.get('cost_usd') or 0))<0.0000005
        for call in calls:
            tokens.setdefault(call['call_id'],[]).append(call['total_tokens'])
            if cost_covered:costs.setdefault(call['call_id'],[]).append(call['cost_usd'])
    duplicates={key:values for key,values in tokens.items() if len(values)>1 and len(set(values))==1}
    return {'tokens':sum((len(values)-1)*values[0] for values in duplicates.values()),
        'cost_usd':round(sum((len(values)-1)*values[0] for values in costs.values()
            if len(values)>1 and len(set(values))==1),6),
        'call_ids':list(duplicates)}


def merge_receipt_budget(budget,receipts):
    """Replace a call's provisional receipt, never add its stage summary twice."""
    budget=dict(budget or {});old=budget.get('model_requests') or []
    prior={};legacy=[]
    for row in old:
        if row.get('call_id'):prior[row['call_id']]=row
        else:legacy.append(row)
    combined=dict(prior)
    for row in receipts:
        key=row['call_id'];previous=combined.get(key)
        if previous and previous.get('status')!='inflight' and row.get('status')=='inflight':continue
        combined[key]=row
    previous_tokens=sum(int(row.get('total_tokens') or 0) for row in [*legacy,*prior.values()] if row.get('status')!='inflight')
    previous_cost=sum(float(row.get('cost_usd') or 0) for row in [*legacy,*prior.values()] if row.get('status')!='inflight')
    values=[*legacy,*combined.values()]
    settled=[row for row in values if row.get('status')!='inflight']
    pending=[row for row in values if row.get('status')=='inflight']
    budget.update(model_requests=values,
        used_total_tokens=max(0,int(budget.get('used_total_tokens') or 0)-previous_tokens)+sum(int(row.get('total_tokens') or 0) for row in settled),
        used_cost_usd=round(max(0,float(budget.get('used_cost_usd') or 0)-previous_cost)+sum(float(row.get('cost_usd') or 0) for row in settled),6),
        reserved_inflight_tokens=sum(int(row.get('reserved_tokens') or 0) for row in pending),
        inflight_model_requests=len(pending),
        reserved_known_model_cost_usd=sum(float(row.get('reserved_known_cost_usd') or 0) for row in pending),
        model_receipt_accounting='one_call_identity_across_admission_settlement_and_cancellation')
    if any(row.get('cost_known') is not True for row in values):budget['cost_status']='unknown_price_or_usage'
    if any(row.get('estimated') or row.get('status')=='inflight' for row in values):budget['token_usage_estimated']=True
    return budget


async def receipt_budget(conn,session_id,owner_id,budget):
    rows=await conn.fetch('''SELECT payload FROM research_model_receipts WHERE session_id=$1::uuid AND owner_id=$2::uuid
        ORDER BY updated_at,call_id''',str(session_id),str(owner_id))
    budget=merge_receipt_budget(budget,[decoded(row['payload']) for row in rows])
    tool_rows=await conn.fetch('''SELECT payload FROM research_tool_receipts WHERE session_id=$1::uuid AND owner_id=$2::uuid
        ORDER BY updated_at,operation_id''',str(session_id),str(owner_id))
    tools=[decoded(row['payload']) for row in tool_rows]
    counts=dict(budget.get('tool_call_counts') or {})
    if not counts and budget.get('used_tool_calls'):
        historical=await conn.fetch('''SELECT a.call_id,a.safety_json FROM tool_call_audit a WHERE a.session_id=$1::uuid
            AND EXISTS(SELECT 1 FROM research_sessions WHERE id=$1::uuid AND owner_id=$2::uuid)''',str(session_id),str(owner_id))
        for row in historical:
            attempts=(decoded(row['safety_json'])).get('channel_attempts') or []
            counts[row['call_id']]=max(1,sum(int(item.get('call_count') or 0) for item in attempts))
        budget['legacy_tool_accounting']='persisted_audit_ids_plus_unattributed_counter_remainder'
    legacy=max(0,int(budget.get('used_tool_calls') or 0)-sum(counts.values()))
    for tool in tools:
        for call in tool.get('calls') or []:
            counts[call['call_id']]=max(counts.get(call['call_id'],0),int(call['accounted_calls']))
    budget.update(tool_operation_receipts=tools,tool_call_counts=counts,
        used_tool_calls=legacy+sum(counts.values()),
        reserved_inflight_tool_calls=sum(int(row.get('call_allowance') or 0) for row in tools if row.get('status')=='inflight'))
    return budget


async def persist_receipt_budget(conn,session_id,owner_id,budget):
    encoded=json.dumps(budget,ensure_ascii=False,default=str)
    await conn.execute('''UPDATE research_sessions SET review_status=jsonb_set(COALESCE(review_status,'{}'::jsonb),'{budget_state}',$3::jsonb),
        total_tokens=$4,total_cost_usd=$5 WHERE id=$1::uuid AND owner_id=$2::uuid''',str(session_id),str(owner_id),encoded,
        int(budget.get('used_total_tokens') or 0),float(budget.get('used_cost_usd') or 0))
    await conn.execute('''UPDATE session_runtime_state SET state_snapshot_json=jsonb_set(
        COALESCE(state_snapshot_json,'{}'::jsonb),'{budget_state}',$3::jsonb)||jsonb_build_object('session',
        COALESCE(state_snapshot_json->'session','{}'::jsonb)||jsonb_build_object('total_tokens',$4::integer,'total_cost_usd',$5::double precision))
        WHERE session_id=$1::uuid AND EXISTS(SELECT 1 FROM research_sessions WHERE id=$1::uuid AND owner_id=$2::uuid)''',
        str(session_id),str(owner_id),encoded,int(budget.get('used_total_tokens') or 0),float(budget.get('used_cost_usd') or 0))
    # This row is the existing numeric view, not a second source of allowance.
    await conn.execute('''UPDATE session_budget_state SET used_total_tokens=$3,used_cost_usd=$4,used_tool_calls=$5
        WHERE session_id=$1::uuid AND EXISTS(SELECT 1 FROM research_sessions WHERE id=$1::uuid AND owner_id=$2::uuid)''',
        str(session_id),str(owner_id),int(budget.get('used_total_tokens') or 0),float(budget.get('used_cost_usd') or 0),int(budget.get('used_tool_calls') or 0))


async def persist_workflow_failure(conn,binding,error,category='workflow_error'):
    """The caller owns one transaction; never replace a committed research result."""
    session_id,owner_id,execution_id=(binding[key] for key in ('session_id','owner_id','execution_id'))
    row=await conn.fetchrow('''SELECT status,execution_id,review_status,total_tokens,total_cost_usd,created_at
        FROM research_sessions WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE''',session_id,owner_id)
    if not row or str(row['execution_id'])!=execution_id:return None
    review=decoded(row['review_status'])
    budget=await receipt_budget(conn,session_id,owner_id,task_budget(row))
    await persist_receipt_budget(conn,session_id,owner_id,budget)
    review['budget_state']=budget
    stored=await conn.fetchrow('''SELECT state_snapshot_json,checkpoint_seq,last_checkpoint_ref,current_batch_json
        FROM session_runtime_state WHERE session_id=$1::uuid FOR UPDATE''',session_id)
    snapshot=decoded(stored['state_snapshot_json']) if stored else {}
    if row['created_at']:snapshot.setdefault('created_at',row['created_at'].isoformat())
    event={'category':category,'error_type':type(error).__name__,
        'message':str(projection(str(error)))[:1500],'at':datetime.now(UTC).isoformat(),
        'execution_id':execution_id,'checkpoint_seq':int(stored['checkpoint_seq'] or 0) if stored else 0}
    if row['status'] not in {'pending','running'}:
        # Publication, SSE or file I/O after commit cannot invalidate that result.
        event['effect']='committed_research_state_preserved'
        events=[*(review.get('operational_events') or []),event][-32:]
        await conn.execute('''UPDATE research_sessions SET review_status=jsonb_set(
            COALESCE(review_status,'{}'::jsonb),'{operational_events}',$3::jsonb)
            WHERE id=$1::uuid AND owner_id=$2::uuid''',session_id,owner_id,json.dumps(events,ensure_ascii=False))
        runtime=({'completed':'completed','failed':'terminal_failed','canceled':'canceled'}.get(row['status'])
            or review.get('runtime_status') or snapshot.get('runtime_status') or 'analysis_paused')
        snapshot.update(status=row['status'],runtime_status=runtime,budget_state=budget,
            review_status={**review,'operational_events':events})
        if row['status'] in {'completed','failed','canceled'}:
            snapshot.update(current_executing_nodes=[],pending_approvals=[])
        snapshot['session']={**(snapshot.get('session') or {}),**binding,'status':row['status'],
            'checkpoint_seq':event['checkpoint_seq']}
        await conn.execute('''UPDATE session_runtime_state SET public_status=$2,runtime_status=$3,
            state_snapshot_json=$4::jsonb,current_batch_json=$5::jsonb,pending_approval_count=$6
            WHERE session_id=$1::uuid''',session_id,row['status'],runtime,
            json.dumps(snapshot,ensure_ascii=False,default=str),json.dumps(snapshot.get('current_executing_nodes') or []),
            len(snapshot.get('pending_approvals') or []))
        return {'status':row['status'],'transitioned':False}
    event.update(effect='root_execution_failed',
        interrupted_batch=snapshot.get('current_executing_nodes') or [],
        analysis_status=(snapshot.get('analysis_workflow') or {}).get('status'),
        last_checkpoint_ref=stored['last_checkpoint_ref'] if stored else None)
    review.update(runtime_status='terminal_failed',last_error_category=category,
        workflow_failure=event,budget_state=budget,pending_approval_count=0)
    snapshot.update(status='failed',runtime_status='terminal_failed',review_status=review,
        budget_state=budget,current_executing_nodes=[],pending_approvals=[])
    snapshot['session']={**(snapshot.get('session') or {}),**binding,'status':'failed',
        'checkpoint_seq':event['checkpoint_seq'],'total_tokens':int(budget.get('used_total_tokens') or 0),
        'total_cost_usd':float(budget.get('used_cost_usd') or 0)}
    snapshot.setdefault('task_id',session_id)
    from app.research_diagnostics import diagnose_stop
    review['pause_diagnosis']=diagnose_stop(snapshot)
    snapshot['review_status']=review
    await conn.execute('''UPDATE research_sessions SET status='failed',updated_at=NOW(),
        completed_at=COALESCE(completed_at,NOW()),review_status=$3::jsonb
        WHERE id=$1::uuid AND owner_id=$2::uuid''',session_id,owner_id,json.dumps(review,ensure_ascii=False,default=str))
    await conn.execute('''INSERT INTO session_runtime_state(session_id,runtime_status,public_status,
        terminal_failure_reason,state_snapshot_json) VALUES($1::uuid,'terminal_failed','failed',$2,$3::jsonb)
        ON CONFLICT(session_id) DO UPDATE SET runtime_status='terminal_failed',public_status='failed',
        terminal_failure_reason=EXCLUDED.terminal_failure_reason,state_snapshot_json=EXCLUDED.state_snapshot_json,
        current_batch_json='[]'::jsonb,pending_approval_count=0,last_heartbeat_at=NOW()''',
        session_id,category,json.dumps(snapshot,ensure_ascii=False,default=str))
    await conn.execute("UPDATE approval_requests SET status='denied' WHERE session_id=$1::uuid AND status='pending'",session_id)
    return {'status':'failed','transitioned':True,'failure':event}


async def model_receipt(conn,binding,record,*,admission=False):
    session_id,owner_id,execution_id=(binding[key] for key in ('session_id','owner_id','execution_id'))
    from app.config import get_settings
    local=not get_settings().security.auth_enabled and owner_id=='00000000-0000-0000-0000-000000000000'
    task=await conn.fetchrow('''SELECT owner_id,execution_id,status,review_status,total_tokens,total_cost_usd,
        EXISTS(SELECT 1 FROM auth_principals p WHERE p.id=research_sessions.owner_id AND p.is_active=TRUE) AS active_owner FROM research_sessions
        WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE''',session_id,owner_id)
    if task is None:return False
    current=str(task['execution_id']) if task['execution_id'] else None
    if admission and (not (task['active_owner'] or local) or task['status']!='running' or current!=execution_id):return False
    previous=await conn.fetchrow('SELECT owner_id,session_id,execution_id,payload FROM research_model_receipts WHERE call_id=$1::uuid',record['call_id'])
    if previous and (str(previous['owner_id'])!=owner_id or str(previous['session_id'])!=session_id or str(previous['execution_id'])!=execution_id):
        raise ValueError('model_receipt_binding_conflict')
    old=decoded(previous['payload']) if previous else {}
    if previous and admission:return False
    if old and old.get('status')!='inflight':return True
    if not admission and not previous:
        # A refused pre-dispatch request has no durable admission and no charge.
        if record.get('status')=='blocked_before_dispatch':return True
        raise ValueError('model_settlement_without_admission')
    budget=await receipt_budget(conn,session_id,owner_id,task_budget(task))
    if admission and not previous:
        tokens=int(record.get('reserved_tokens') or 0)
        limit=budget.get('max_total_tokens')
        if limit is None or int(budget.get('used_total_tokens') or 0)+int(budget.get('reserved_inflight_tokens') or 0)+tokens>int(limit):
            return False
        known=record.get('reserved_known_cost_usd')
        cost_limit=budget.get('max_cost_usd')
        if known is not None and cost_limit is not None and (
                float(budget.get('used_cost_usd') or 0)+float(budget.get('reserved_known_model_cost_usd') or 0)+known>float(cost_limit)):
            return False
    safe=projection({key:value for key,value in record.items() if key!='started_monotonic'})
    await conn.execute('''INSERT INTO research_model_receipts(call_id,owner_id,session_id,execution_id,payload)
        VALUES($1::uuid,$2::uuid,$3::uuid,$4::uuid,$5::jsonb) ON CONFLICT(call_id) DO UPDATE
        SET payload=EXCLUDED.payload,updated_at=NOW()''',record['call_id'],owner_id,session_id,execution_id,json.dumps(safe,ensure_ascii=False,default=str))
    budget=merge_receipt_budget(budget,[safe])
    await persist_receipt_budget(conn,session_id,owner_id,budget)
    return True


def summarize_tool(binding,payload,error,*,admission=False):
    calls=[]
    for history in (payload or {}).get('tool_histories') or []:
        for call in history.get('tool_calls') or []:
            safe=call.get('safety_json') or {};attempts=safe.get('channel_attempts') or []
            observations=safe.get('retrieval_channels') or []
            if isinstance(observations,dict):observations=[observations]
            calls.append({'call_id':call['call_id'],'tool_name':call.get('tool_name'),'status':call.get('status'),
                'duration_ms':call.get('duration_ms'),'tokens_used':call.get('tokens_used'),
                'accounted_calls':max(1,sum(int(row.get('call_count') or 0) for row in attempts)),
                'network_calls':sum(int(row.get('call_count') or 0) for row in attempts) if attempts else None,
                'cost_usd':None,'cost_basis':'no_independent_provider_receipt',
                'resource_usage':[event for row in observations for event in row.get('resource_usage') or []]})
    if not admission and error and not calls:
        calls=[{'call_id':'unknown-'+binding['operation_id'],'tool_name':'bound_tool_result','status':'unknown',
            'accounted_calls':int(binding.get('call_allowance') or 0),'network_calls':None,'cost_usd':None,
            'cost_basis':'reserved_allowance_result_unknown_not_free'}]
    return {'operation_id':binding['operation_id'],'node_id':binding['node_id'],'tool':binding['node_type'],
        'status':'inflight' if admission else 'unknown' if error else 'settled','error_category':error,
        'call_allowance':binding['call_allowance'],'expires_at':binding['expires_at'],'calls':calls,
        'counting_semantics':'bounded_tool_attempts_and_unknown_allowance_not_verified_network_invoice'}


async def tool_receipt(conn,control_binding,binding,payload=None,error=None,*,admission=False):
    session_id,owner_id,execution_id=(control_binding[key] for key in ('session_id','owner_id','execution_id'))
    if (binding.get('task_id'),binding.get('owner_id'),binding.get('execution_id'))!=(session_id,owner_id,execution_id):
        raise ValueError('tool_receipt_execution_binding_conflict')
    from app.config import get_settings
    local=not get_settings().security.auth_enabled and owner_id=='00000000-0000-0000-0000-000000000000'
    task=await conn.fetchrow('''SELECT status,execution_id,review_status,total_tokens,total_cost_usd,
        EXISTS(SELECT 1 FROM auth_principals p WHERE p.id=research_sessions.owner_id AND p.is_active=TRUE) AS active_owner
        FROM research_sessions WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE''',session_id,owner_id)
    if task is None:return False
    if admission and (not (task['active_owner'] or local) or task['status']!='running' or str(task['execution_id'])!=execution_id):return False
    old=await conn.fetchrow('SELECT owner_id,session_id,execution_id,payload FROM research_tool_receipts WHERE operation_id=$1',binding['operation_id'])
    if old and (str(old['owner_id']),str(old['session_id']),str(old['execution_id']))!=(owner_id,session_id,execution_id):
        raise ValueError('tool_receipt_owner_binding_conflict')
    if admission and old:return False
    if not admission and old is None:raise ValueError('tool_settlement_without_admission')
    if old and decoded(old['payload']).get('status')!='inflight':return True
    budget=await receipt_budget(conn,session_id,owner_id,task_budget(task))
    if admission and int(budget.get('used_tool_calls') or 0)+int(budget.get('reserved_inflight_tool_calls') or 0)+binding['call_allowance']>int(budget.get('max_tool_calls') or 0):
        return False
    safe=projection(summarize_tool(binding,payload,error,admission=admission))
    await conn.execute('''INSERT INTO research_tool_receipts(operation_id,owner_id,session_id,execution_id,payload)
        VALUES($1,$2::uuid,$3::uuid,$4::uuid,$5::jsonb) ON CONFLICT(operation_id) DO UPDATE SET payload=EXCLUDED.payload,updated_at=NOW()''',
        binding['operation_id'],owner_id,session_id,execution_id,json.dumps(safe,ensure_ascii=False,default=str))
    budget=await receipt_budget(conn,session_id,owner_id,budget)
    await persist_receipt_budget(conn,session_id,owner_id,budget)
    return True


async def cancel_execution(conn,session_id,owner_id,request):
    await conn.execute("SELECT set_config('lock_timeout','3000',true)")
    await conn.execute("SELECT set_config('statement_timeout','15000',true)")
    await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))','research-cancel:'+str(owner_id))
    task=await conn.fetchrow('''SELECT id,status,execution_id,review_status,total_tokens,total_cost_usd FROM research_sessions
        WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE''',str(session_id),str(owner_id))
    if task is None:raise ValueError('cancel_task_not_found')
    fingerprint=identity({'session_id':str(session_id),'request':request.model_dump(mode='json')})
    prior=await conn.fetchrow('SELECT fingerprint,response FROM research_cancellations WHERE owner_id=$1::uuid AND request_id=$2::uuid',str(owner_id),str(request.request_id))
    if prior:
        if prior['fingerprint']!=fingerprint:raise ValueError('cancel_request_id_payload_conflict')
        return {**decoded(prior['response']),'replayed':True}
    execution=str(task['execution_id']) if task['execution_id'] else None
    expected=str(request.execution_id) if request.execution_id else None
    if execution!=expected:raise ValueError('cancel_execution_changed_reload')
    if task['status'] not in {'pending','running','paused','canceled'}:raise ValueError('cancel_task_already_terminal')
    if await conn.fetchval('SELECT COUNT(*) FROM research_cancellations WHERE owner_id=$1::uuid AND session_id=$2::uuid',str(owner_id),str(session_id))>=128:
        raise ValueError('cancel_command_limit_128')
    now=datetime.now(UTC).isoformat();review=decoded(task['review_status'])
    budget=await receipt_budget(conn,session_id,owner_id,task_budget(task))
    response={'session_id':str(session_id),'execution_id':execution,'status':'canceled',
        'transitioned':task['status']!='canceled',
        'request_id':str(request.request_id),'canceled_at':now,'inflight_model_requests':budget.get('inflight_model_requests',0),
        'cost_semantics':'already_dispatched_requests_may_still_be_billed_no_automatic_refund','replayed':False}
    cancellation=review.get('cancellation') or {key:value for key,value in response.items() if key!='replayed'}
    if task['status']=='canceled':response['canceled_at']=cancellation.get('canceled_at',now)
    review.update(runtime_status='canceled',pending_approval_count=0,cancellation=cancellation,budget_state=budget)
    await conn.execute('''UPDATE research_sessions SET status='canceled',review_status=$3::jsonb,updated_at=NOW(),completed_at=COALESCE(completed_at,NOW())
        WHERE id=$1::uuid AND owner_id=$2::uuid''',str(session_id),str(owner_id),json.dumps(review,ensure_ascii=False,default=str))
    await conn.execute('''UPDATE session_runtime_state SET runtime_status='canceled',public_status='canceled',pending_approval_count=0,
        current_batch_json='[]'::jsonb,state_snapshot_json=COALESCE(state_snapshot_json,'{}'::jsonb)||$3::jsonb||
        jsonb_build_object('session',COALESCE(state_snapshot_json->'session','{}'::jsonb)||'{"status":"canceled"}'::jsonb)
        WHERE session_id=$1::uuid AND EXISTS(SELECT 1 FROM research_sessions WHERE id=$1::uuid AND owner_id=$2::uuid)''',
        str(session_id),str(owner_id),json.dumps({'status':'canceled','runtime_status':'canceled','review_status':review,
            'pending_approvals':[],'budget_state':budget},ensure_ascii=False,default=str))
    await conn.execute('''UPDATE approval_requests SET status='denied' WHERE session_id=$1::uuid AND status='pending'
        AND EXISTS(SELECT 1 FROM research_sessions WHERE id=$1::uuid AND owner_id=$2::uuid)''',str(session_id),str(owner_id))
    await persist_receipt_budget(conn,session_id,owner_id,budget)
    await conn.execute('''INSERT INTO research_cancellations(owner_id,request_id,session_id,execution_id,fingerprint,response)
        VALUES($1::uuid,$2::uuid,$3::uuid,$4::uuid,$5,$6::jsonb)''',str(owner_id),str(request.request_id),str(session_id),
        execution,fingerprint,json.dumps(response,ensure_ascii=False))
    return response
