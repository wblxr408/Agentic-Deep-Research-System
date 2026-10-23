"""Immutable feedback in the existing owner-scoped task transaction."""
from __future__ import annotations

import json
from app.query_understanding import identity
from app.disclosure import projection
from app.research_quality import validate_feedback

SCHEMA_SQL='''
CREATE TABLE IF NOT EXISTS research_quality_feedback (
 owner_id UUID NOT NULL, session_id UUID NOT NULL REFERENCES research_sessions(id) ON DELETE CASCADE,
 request_id UUID NOT NULL, fingerprint TEXT NOT NULL, binding_id TEXT NOT NULL,
 kind TEXT NOT NULL, payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(owner_id,request_id)
);
CREATE INDEX IF NOT EXISTS idx_quality_feedback_task ON research_quality_feedback(owner_id,session_id,created_at,request_id);
'''


def decoded(value):
    return json.loads(value) if isinstance(value,str) else value or {}


async def load_quality_state(conn,session_id,owner_id,*,for_update=False):
    row=await conn.fetchrow('''SELECT s.id,s.execution_id,s.user_query,s.status,s.final_report,s.citations,s.review_status,
        r.state_snapshot_json FROM research_sessions s LEFT JOIN session_runtime_state r ON r.session_id=s.id
        WHERE s.id=$1::uuid AND s.owner_id=$2::uuid'''+(' FOR UPDATE OF s' if for_update else ''),str(session_id),str(owner_id))
    if row is None:raise ValueError('quality_task_not_found')
    state=decoded(row['state_snapshot_json']);review=decoded(row['review_status'])
    citations=decoded(row['citations'])
    return {**state,'task_id':str(row['id']),'status':row['status'],'user_query':row['user_query'],
        'final_report':row['final_report'],'citations':citations if isinstance(citations,list) else [],
        'session':{**state.get('session',{}),'owner_id':str(owner_id),'execution_id':str(row['execution_id']) if row['execution_id'] else None},
        'review_status':review,'organization_result':review.get('organization_result') or state.get('organization_result'),
        'organization_research':review.get('organization_research') or state.get('organization_research'),
        'query_understanding':review.get('query_understanding') or state.get('query_understanding')}


async def load_feedback(conn,session_id,owner_id):
    rows=await conn.fetch('''SELECT request_id,binding_id,kind,payload,created_at FROM research_quality_feedback
        WHERE owner_id=$1::uuid AND session_id=$2::uuid ORDER BY created_at,request_id''',str(owner_id),str(session_id))
    return [{'request_id':str(row['request_id']),'binding_id':row['binding_id'],'kind':row['kind'],
        'payload':decoded(row['payload']),'created_at':row['created_at'].isoformat()} for row in rows]


async def save_feedback(conn,session_id,owner_id,request):
    await conn.execute("SELECT set_config('lock_timeout','3000',true)")
    await conn.execute("SELECT set_config('statement_timeout','30000',true)")
    await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))','quality-feedback:'+str(owner_id))
    state=await load_quality_state(conn,session_id,owner_id,for_update=True)
    fingerprint=identity({'session_id':str(session_id),'request':request.model_dump(mode='json')})
    old=await conn.fetchrow('SELECT session_id,fingerprint FROM research_quality_feedback WHERE owner_id=$1::uuid AND request_id=$2::uuid',str(owner_id),str(request.request_id))
    if old:
        if str(old['session_id'])!=str(session_id) or old['fingerprint']!=fingerprint:raise ValueError('feedback_request_id_payload_conflict')
        return {'request_id':str(request.request_id),'binding_id':request.binding_id,'replayed':True}
    if state['status'] not in {'completed','paused','failed'}:raise ValueError('feedback_requires_stopped_task')
    validate_feedback(state,request)
    count=await conn.fetchval('SELECT COUNT(*) FROM research_quality_feedback WHERE owner_id=$1::uuid AND session_id=$2::uuid',str(owner_id),str(session_id))
    if count>=1000:raise ValueError('task_feedback_limit_1000')
    payload=projection(request.model_dump(mode='json'))
    await conn.execute('''INSERT INTO research_quality_feedback(owner_id,session_id,request_id,fingerprint,binding_id,kind,payload)
        VALUES($1::uuid,$2::uuid,$3::uuid,$4,$5,$6,$7::jsonb)''',str(owner_id),str(session_id),str(request.request_id),fingerprint,
        request.binding_id,request.kind,json.dumps(payload,ensure_ascii=False))
    return {'request_id':str(request.request_id),'binding_id':request.binding_id,'replayed':False}
