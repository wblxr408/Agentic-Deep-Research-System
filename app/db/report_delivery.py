"""Owner-scoped immutable report snapshots and declarative template revisions."""
from __future__ import annotations

import json
from uuid import UUID,uuid4

from pydantic import Field, model_serializer
from app.query_understanding import DeliveryRequest,identity
from app.research_scope import Label,ScopeRecord

SCHEMA_SQL='''
CREATE TABLE IF NOT EXISTS research_report_versions (
 session_id UUID NOT NULL REFERENCES research_sessions(id) ON DELETE CASCADE,
 owner_id UUID NOT NULL, report_id TEXT NOT NULL, sequence INTEGER NOT NULL CHECK(sequence>0),
 execution_id UUID, payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(session_id,report_id), UNIQUE(session_id,sequence)
);
CREATE INDEX IF NOT EXISTS idx_research_report_versions_owner ON research_report_versions(owner_id,session_id,sequence DESC);
CREATE TABLE IF NOT EXISTS research_delivery_templates (
 template_id UUID NOT NULL, owner_id UUID NOT NULL, version INTEGER NOT NULL CHECK(version>0),
 request_id UUID NOT NULL, fingerprint TEXT NOT NULL, name TEXT NOT NULL, project_label TEXT,
 configuration JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(template_id,version), UNIQUE(owner_id,request_id)
);
CREATE INDEX IF NOT EXISTS idx_delivery_templates_owner ON research_delivery_templates(owner_id,template_id,version DESC);
ALTER TABLE research_delivery_templates ADD COLUMN IF NOT EXISTS layout_source_id UUID;
CREATE TABLE IF NOT EXISTS research_layout_samples (
 source_id UUID PRIMARY KEY, owner_id UUID NOT NULL REFERENCES auth_principals(id) ON DELETE CASCADE,
 request_id UUID NOT NULL, file_name TEXT NOT NULL, format TEXT NOT NULL,
 file_bytes BYTEA NOT NULL, parsed JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(owner_id,request_id)
);
'''


class TemplateSave(ScopeRecord):
    request_id:UUID
    name:Label
    project_label:Label|None=None
    configuration:DeliveryRequest
    expected_version:int|None=Field(default=None,ge=1)
    layout_source_id:UUID|None=None

    @model_serializer(mode='wrap')
    def wire_request(self, handler):
        data = handler(self)
        if self.layout_source_id is None:
            data.pop('layout_source_id', None)
        return data


def _json(value):
    return json.loads(value) if isinstance(value,str) else value


def template_record(row):
    return None if row is None else {'template_id':str(row['template_id']),'version':row['version'],
        'name':row['name'],'project_label':row['project_label'],'configuration':_json(row['configuration']),
        'created_at':row['created_at'].isoformat(),
        **({'layout_source_id':str(row['layout_source_id'])} if row.get('layout_source_id') else {})}


async def load_template(conn,owner_id,template_id,version=None):
    return template_record(await conn.fetchrow('''SELECT * FROM research_delivery_templates
        WHERE owner_id=$1::uuid AND template_id=$2::uuid AND ($3::integer IS NULL OR version=$3)
        ORDER BY version DESC LIMIT 1''',str(owner_id),str(template_id),version))


async def save_template(conn,owner_id,request,template_id=None):
    """Caller opens transaction; serialize this owner's version/replay decisions."""
    await conn.execute("SELECT set_config('lock_timeout','3000',true)")
    await conn.execute("SELECT set_config('statement_timeout','30000',true)")
    await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))','delivery-template:'+str(owner_id))
    fingerprint=identity({'template_id':str(template_id) if template_id else None,'request':request.model_dump(mode='json')})
    prior=await conn.fetchrow('SELECT * FROM research_delivery_templates WHERE owner_id=$1::uuid AND request_id=$2::uuid',str(owner_id),str(request.request_id))
    if prior:
        if prior['fingerprint']!=fingerprint:raise ValueError('template_request_id_payload_conflict')
        return {**template_record(prior),'replayed':True}
    origin=request.configuration.copied_from_template
    if request.layout_source_id:
        if request.configuration.layout is None or not await conn.fetchval('SELECT 1 FROM research_layout_samples WHERE source_id=$1::uuid AND owner_id=$2::uuid', request.layout_source_id, str(owner_id)):
            raise ValueError('layout_source_not_owned_or_missing')
    if origin and not await load_template(conn,owner_id,origin.template_id,origin.version):
        raise ValueError('template_origin_not_owned_or_missing')
    if template_id:
        latest=await load_template(conn,owner_id,template_id)
        if not latest:raise ValueError('template_not_found')
        if request.expected_version!=latest['version']:raise ValueError('template_version_changed')
        if latest['version']>=100:raise ValueError('template_version_limit_100')
        version=latest['version']+1
    else:
        if request.expected_version is not None:raise ValueError('new_template_cannot_have_expected_version')
        count=await conn.fetchval('SELECT COUNT(DISTINCT template_id) FROM research_delivery_templates WHERE owner_id=$1::uuid',str(owner_id))
        if count>=50:raise ValueError('personal_template_limit_50')
        template_id=uuid4();version=1
    row=await conn.fetchrow('''INSERT INTO research_delivery_templates
        (template_id,owner_id,version,request_id,fingerprint,name,project_label,configuration,layout_source_id)
        VALUES($1::uuid,$2::uuid,$3,$4::uuid,$5,$6,$7,$8::jsonb,$9::uuid) RETURNING *''',str(template_id),str(owner_id),version,
        str(request.request_id),fingerprint,request.name,request.project_label,request.configuration.model_dump_json(),request.layout_source_id)
    return {**template_record(row),'replayed':False}


async def retain_report_version(conn,state,review,*,owner_id,session_id):
    """Only called inside the existing owner/execution-fenced root transaction."""
    if state.get('status') not in {'paused','completed','failed'} or review.get('output_stage')!='report':return None
    if review.get('report_binding')!=report_binding(state):return None
    kind=review.get('report_payload_kind','report')
    report=state.get('final_report') if kind=='report' else review.get('partial_model_response')
    if kind not in {'report','partial_response'}:raise ValueError('unsupported_report_history_payload_kind')
    if not isinstance(report,str) or not report.strip():return None
    audit=review.get('final_report_audit') or {}
    completed=state.get('status')=='completed'
    supported=bool(completed and audit and not audit.get('needs_review',True)
        and not audit.get('audit_incomplete') and not audit.get('budget_incomplete') and kind=='report')
    ledger=state.get('evidence_ledger') or {}
    if ledger and (ledger.get('owner_id')!=str(owner_id) or ledger.get('session_id')!=str(session_id)):
        raise ValueError('report_history_evidence_scope_conflict')
    sources=[{'evidence_id':key,'source_id':event['source_id'],'version_id':event['version_id'],'coverage':event.get('coverage')}
        for key,event in sorted((ledger.get('events') or {}).items())]
    result=state.get('organization_result') or {}
    payload={'schema_version':'adrs-report-history-v1','session_id':str(session_id),
        'owner_id':str(owner_id),'execution_id':str((state.get('session') or {}).get('execution_id') or ''),
        'kind':kind,'report':report,'citations':state.get('citations') or [],'audit':audit,
        'status':'supported_report' if supported else 'saved_draft' if kind=='report' else 'incomplete_response',
        'source_versions':sources,'source_semantics':'retained_candidate_source_map_not_proof_all_sources_were_read',
        'plan_version':(state.get('plan_manifest') or {}).get('plan_version'),
        'interpretation_id':(state.get('query_understanding') or {}).get('interpretation_id'),
        'delivery':(state.get('query_understanding') or {}).get('delivery'),
        'writing_plan':result.get('writing_plan') or (state.get('query_understanding') or {}).get('writing_plan'),
        'statistics_id':(result.get('statistics') or {}).get('snapshot_id'),
        'figure_snapshot':'current_file_assets_not_duplicated_in_text_history; historical_figure_availability_not_asserted',
        'automatic_fact_ingestion':False}
    from app.disclosure import report_history_projection
    payload=report_history_projection(payload)
    report_id='report:'+identity(payload)
    if await conn.fetchval('SELECT 1 FROM research_report_versions WHERE session_id=$1::uuid AND owner_id=$2::uuid AND report_id=$3',str(session_id),str(owner_id),report_id):return report_id
    # Bounded by the original task's finite revisions and paid budget; never delete history to fit.
    count=await conn.fetchval('SELECT COUNT(*) FROM research_report_versions WHERE session_id=$1::uuid',str(session_id))
    if count>=64:raise ValueError('report_history_version_limit_64')
    encoded=json.dumps(payload,ensure_ascii=False,default=str)
    if len(encoded.encode('utf-8'))>8_000_000:raise ValueError('report_history_payload_limit')
    await conn.execute('''INSERT INTO research_report_versions(session_id,owner_id,report_id,sequence,execution_id,payload)
        VALUES($1::uuid,$2::uuid,$3,$4,$5::uuid,$6::jsonb)''',str(session_id),str(owner_id),report_id,int(count)+1,
        (state.get('session') or {}).get('execution_id'),encoded)
    return report_id


def report_binding(state):
    from app.planning_control import retained_evidence_version
    return {'execution_id':(state.get('session') or {}).get('execution_id'),
        'plan_version':(state.get('plan_manifest') or {}).get('plan_version'),
        'retained_evidence_version':retained_evidence_version(state)}
