"""Immutable source revisions, current access and bounded owned mutations."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, model_validator
from app.research_scope import ScopeRecord
from app.evidence_chunks import identity

VERSION = 'adrs-source-lifecycle-v1'
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS document_source_lifecycle (
    source_id UUID PRIMARY KEY REFERENCES document_sources(id) ON DELETE CASCADE,
    owner_id UUID NOT NULL,family_id UUID NOT NULL,predecessor_id UUID,
    revision BIGINT NOT NULL DEFAULT 1 CHECK(revision>0),
    is_current BOOLEAN NOT NULL DEFAULT TRUE,state TEXT NOT NULL CHECK(state IN ('retained','tombstone')),
    reuse_scope TEXT NOT NULL CHECK(reuse_scope IN ('task','group','owner')),task_id UUID,
    valid_from TIMESTAMPTZ,valid_until TIMESTAMPTZ,purge_after TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK(valid_until IS NULL OR valid_from IS NULL OR valid_until>valid_from),
    CHECK(reuse_scope='task' OR task_id IS NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_source_family_current ON document_source_lifecycle(owner_id,family_id) WHERE is_current;
CREATE INDEX IF NOT EXISTS idx_source_lifecycle_scope ON document_source_lifecycle(owner_id,reuse_scope,task_id,state,is_current);
CREATE INDEX IF NOT EXISTS idx_source_lifecycle_family ON document_source_lifecycle(owner_id,family_id,created_at DESC);
CREATE TABLE IF NOT EXISTS source_access_epochs(owner_id UUID PRIMARY KEY,epoch BIGINT NOT NULL CHECK(epoch>0));
CREATE TABLE IF NOT EXISTS source_lifecycle_events (
    owner_id UUID NOT NULL,request_id UUID NOT NULL,payload_fingerprint TEXT NOT NULL,
    source_id UUID,kind TEXT NOT NULL,reason TEXT NOT NULL,result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),PRIMARY KEY(owner_id,request_id)
);
CREATE INDEX IF NOT EXISTS idx_source_lifecycle_events_source ON source_lifecycle_events(owner_id,source_id,created_at DESC);
"""


class RetentionPolicy(ScopeRecord):
    reuse_scope: Literal['task','group','owner'] = 'task'
    task_id: UUID | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    purge_after: datetime | None = None

    @model_validator(mode='after')
    def consistent(self):
        if self.reuse_scope!='task' and self.task_id is not None:raise ValueError('only_task_scope_accepts_task_id')
        for value in (self.valid_from,self.valid_until,self.purge_after):
            if value and value.tzinfo is None:raise ValueError('lifecycle_dates_require_timezone')
        if self.valid_from and self.valid_until and self.valid_until<=self.valid_from:raise ValueError('invalid_source_validity_interval')
        return self


class LifecycleAction(ScopeRecord):
    request_id: UUID
    action: Literal['tombstone','restore','activate','set_access','purge','cleanup','prune_indexes']
    expected_revision: int = Field(ge=0)
    reason: str = Field(min_length=1,max_length=2000)
    policy: RetentionPolicy | None = None
    before: datetime | None = None

    @model_validator(mode='after')
    def consistent(self):
        if not self.reason.strip():raise ValueError('lifecycle_reason_required')
        if (self.action=='set_access')!=(self.policy is not None):raise ValueError('only_set_access_requires_policy')
        if (self.action=='prune_indexes')!=(self.before is not None):raise ValueError('only_index_pruning_requires_cutoff')
        if self.before and (self.before.tzinfo is None or self.before>datetime.now(timezone.utc)):raise ValueError('prune_cutoff_requires_past_timezone_date')
        return self


class SourceRevision(ScopeRecord):
    request_id: UUID
    expected_revision: int = Field(ge=0)
    expected_parse_version: str | None = Field(min_length=1,max_length=260)
    reason: str = Field(min_length=1,max_length=2000)
    mode: Literal['replace','patch'] = 'replace'
    text: str = Field(max_length=8_000_000)
    start: int | None = Field(default=None,ge=0)
    end: int | None = Field(default=None,ge=0)
    format: Literal['txt','md','json'] = 'txt'
    publish: bool = True

    @model_validator(mode='after')
    def consistent(self):
        if not self.reason.strip():raise ValueError('revision_reason_required')
        if self.mode=='patch':
            if self.start is None or self.end is None or self.end<self.start:raise ValueError('patch_requires_original_range')
        elif self.start is not None or self.end is not None:raise ValueError('replace_cannot_supply_patch_range')
        return self


class PublishMember(ScopeRecord):
    source_id: UUID
    expected_revision: int = Field(ge=0)


class BatchPublication(ScopeRecord):
    request_id: UUID
    members: list[PublishMember] = Field(min_length=1,max_length=20)
    reason: str = Field(min_length=1,max_length=2000)

    @model_validator(mode='after')
    def distinct(self):
        if not self.reason.strip() or len({item.source_id for item in self.members})!=len(self.members):raise ValueError('unique_publication_members_and_reason_required')
        return self


def object_value(value):
    result=json.loads(value) if isinstance(value,str) else value or {}
    if not isinstance(result,dict):raise ValueError('invalid_source_metadata')
    return result


async def lock_owner(conn,owner_id):
    await conn.execute("SELECT set_config('lock_timeout','3000',true)")
    await conn.execute("SELECT set_config('statement_timeout','30000',true)")
    await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))','source-lifecycle:'+str(owner_id))


async def bump_epoch(conn,owner_id):
    return await conn.fetchval('''INSERT INTO source_access_epochs(owner_id,epoch) VALUES($1::uuid,1)
        ON CONFLICT(owner_id) DO UPDATE SET epoch=source_access_epochs.epoch+1 RETURNING epoch''',str(owner_id))


async def validate_policy(conn,owner_id,policy):
    if policy.task_id is not None and not await conn.fetchval('SELECT id FROM research_sessions WHERE id=$1::uuid AND owner_id=$2::uuid',str(policy.task_id),str(owner_id)):
        raise ValueError('retention_task_not_owned_or_missing')


async def initialize_lifecycle(conn,source_id,owner_id,policy):
    await validate_policy(conn,owner_id,policy)
    await conn.execute('''INSERT INTO document_source_lifecycle(source_id,owner_id,family_id,state,reuse_scope,task_id,valid_from,valid_until,purge_after)
        VALUES($1::uuid,$2::uuid,$1::uuid,'retained',$3,$4::uuid,$5,$6,$7)''',str(source_id),str(owner_id),policy.reuse_scope,str(policy.task_id) if policy.task_id else None,policy.valid_from,policy.valid_until,policy.purge_after)
    return await bump_epoch(conn,owner_id)


def access_clause(alias='s',task_parameter='$6',group_parameter='$2'):
    """Identifiers/placeholders are internal constants, never caller-provided SQL."""
    if alias not in {'s','document_sources'} or task_parameter not in {'$3','$6'} or group_parameter not in {'$2','$4'}:raise ValueError('unsupported_internal_access_sql_shape')
    return f"""(
      EXISTS(SELECT 1 FROM document_source_lifecycle lc WHERE lc.source_id={alias}.id AND lc.owner_id={alias}.owner_id
        AND lc.state='retained' AND lc.is_current
        AND (lc.valid_from IS NULL OR lc.valid_from<=CURRENT_TIMESTAMP)
        AND (lc.valid_until IS NULL OR lc.valid_until>CURRENT_TIMESTAMP)
        AND ((lc.reuse_scope='task' AND lc.task_id={task_parameter}::uuid)
          OR (lc.reuse_scope='group' AND {group_parameter}::text IS NOT NULL AND {alias}.group_name={group_parameter}::text)
          OR lc.reuse_scope='owner'))
      OR ({group_parameter}::text IS NOT NULL AND NOT EXISTS(SELECT 1 FROM document_source_lifecycle legacy WHERE legacy.source_id={alias}.id))
    )"""


async def current_access(conn,source_id,owner_id,task_id,group,expected_revision=None,*,with_snapshot=False):
    from app.data_governance import PUBLIC_ARCHIVE_VERSION
    row=await conn.fetchrow(f'''SELECT s.id,COALESCE(lc.revision,0) AS revision,
        jsonb_build_object('source_id',s.id,'family_id',lc.family_id,'revision',COALESCE(lc.revision,0),
            'reuse_scope',COALESCE(lc.reuse_scope,'legacy_explicit_group'),'bound_task_id',lc.task_id,
            'actual_task_id',$3::uuid,'group_name',s.group_name,'valid_from',lc.valid_from,'valid_until',lc.valid_until,
            'checked_at',CURRENT_TIMESTAMP,
            'public_archive_origin',(SELECT jsonb_build_object('version','{PUBLIC_ARCHIVE_VERSION}',
                'source_id',s.id,'source_content_version',s.metadata->>'content_hash',
                'origin_version_id',event.result->>'source_version_id')
                FROM source_lifecycle_events event WHERE event.owner_id=s.owner_id AND event.source_id=s.id
                AND event.kind='archive_task_evidence' AND event.result->>'source_id'=s.id::text
                AND event.result->>'archived_content_hash'=s.metadata->>'content_hash'
                ORDER BY event.created_at DESC LIMIT 1)) AS access_snapshot FROM document_sources s
        LEFT JOIN document_source_lifecycle lc ON lc.source_id=s.id AND lc.owner_id=s.owner_id
        WHERE s.id=$1::uuid AND s.owner_id=$2::uuid AND s.status='active'
        AND (EXISTS(SELECT 1 FROM source_index_heads h WHERE h.source_id=s.id AND h.owner_id=s.owner_id AND h.mode='lexical')
            OR (s.metadata->'index_policy' IS NULL AND NOT EXISTS(SELECT 1 FROM source_index_heads h WHERE h.source_id=s.id)))
        AND ($4::text IS NULL OR s.group_name=$4::text) AND {access_clause('s','$3','$4')}''',
        str(source_id),str(owner_id),str(task_id) if task_id else None,group)
    allowed=bool(row and (expected_revision is None or row['revision']==expected_revision))
    return object_value(row['access_snapshot']) if allowed and with_snapshot else allowed


async def owned_source(conn,source_id,owner_id):
    source=await conn.fetchrow('SELECT * FROM document_sources WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE',str(source_id),str(owner_id))
    if not source:raise ValueError('source_not_found')
    lifecycle=await conn.fetchrow('SELECT * FROM document_source_lifecycle WHERE source_id=$1::uuid AND owner_id=$2::uuid FOR UPDATE',str(source_id),str(owner_id))
    return source,lifecycle


async def adopt_legacy(conn,source_id,owner_id):
    # A legacy source is retained under the already explicit group convention;
    # adoption does not assign an unowned row or authorize unscoped reuse.
    await conn.execute('''INSERT INTO document_source_lifecycle(source_id,owner_id,family_id,state,reuse_scope)
        VALUES($1::uuid,$2::uuid,$1::uuid,'retained','group') ON CONFLICT(source_id) DO NOTHING''',str(source_id),str(owner_id))


async def prior_operation(conn,owner_id,request_id,fingerprint):
    row=await conn.fetchrow('SELECT payload_fingerprint,result FROM source_lifecycle_events WHERE owner_id=$1::uuid AND request_id=$2::uuid',str(owner_id),str(request_id))
    if not row:return None
    if row['payload_fingerprint']!=fingerprint:raise ValueError('lifecycle_request_id_payload_conflict')
    return {**object_value(row['result']),'replayed':True}


async def record_operation(conn,owner_id,request_id,fingerprint,source_id,kind,reason,result):
    await conn.execute('''INSERT INTO source_lifecycle_events(owner_id,request_id,payload_fingerprint,source_id,kind,reason,result)
        VALUES($1::uuid,$2::uuid,$3,$4::uuid,$5,$6,$7::jsonb)''',str(owner_id),str(request_id),fingerprint,str(source_id) if source_id else None,kind,reason,json.dumps(result,ensure_ascii=False,default=str))


async def affected_reports(conn,source_id,owner_id):
    # Inspect only the authenticated owner's immutable retained acquisition refs.
    rows=await conn.fetch('''SELECT s.id,s.status,s.completed_at FROM research_sessions s
        JOIN session_runtime_state r ON r.session_id=s.id WHERE s.owner_id=$1::uuid
        AND EXISTS(SELECT 1 FROM jsonb_each(COALESCE(r.state_snapshot_json->'evidence_ledger'->'sources','{}'::jsonb)) src,
            LATERAL jsonb_each(COALESCE(src.value->'versions','{}'::jsonb)) ver
            WHERE ver.value->'acquisition'->>'source_document_id'=$2)
        ORDER BY s.created_at DESC,s.id LIMIT 51''',str(owner_id),str(source_id))
    return {'items':[{'session_id':str(row['id']),'status':row['status'],'completed_at':str(row['completed_at']) if row['completed_at'] else None} for row in rows[:50]],'has_more':len(rows)>50,
        'coverage':'retained_ledger_source_document_id_only_legacy_unlinked_unknown','reports_automatically_rewritten':False}


async def activate_version(conn,source_id,owner_id,expected_revision):
    source,lc=await owned_source(conn,source_id,owner_id)
    if (lc['revision'] if lc else 0)!=expected_revision:raise ValueError('source_lifecycle_revision_conflict')
    if lc is None:
        await adopt_legacy(conn,source_id,owner_id);source,lc=await owned_source(conn,source_id,owner_id)
    if lc['state']!='retained' or source['status']!='active':raise ValueError('cannot_publish_deleted_or_inactive_source')
    if (lc['valid_from'] and lc['valid_from']>datetime.now(timezone.utc)) or (lc['valid_until'] and lc['valid_until']<=datetime.now(timezone.utc)):
        raise ValueError('source_outside_effective_interval')
    await conn.execute('''UPDATE document_source_lifecycle SET is_current=FALSE,revision=revision+1,updated_at=NOW()
        WHERE owner_id=$1::uuid AND family_id=$2::uuid AND is_current AND source_id<>$3::uuid''',str(owner_id),str(lc['family_id']),str(source_id))
    return await conn.fetchval('''UPDATE document_source_lifecycle SET is_current=TRUE,revision=revision+1,updated_at=NOW()
        WHERE source_id=$1::uuid AND owner_id=$2::uuid RETURNING revision''',str(source_id),str(owner_id))


async def publish_batch(conn,owner_id,request):
    await lock_owner(conn,owner_id)
    fingerprint=identity({'kind':'publish_batch','request':request.model_dump(mode='json')})
    replay=await prior_operation(conn,owner_id,request.request_id,fingerprint)
    if replay:return replay
    members=[];families=set()
    # Validate every expected version before any mutation, including families.
    for member in request.members:
        source,lc=await owned_source(conn,member.source_id,owner_id)
        if (lc['revision'] if lc else 0)!=member.expected_revision:raise ValueError('source_lifecycle_revision_conflict')
        family=str(lc['family_id']) if lc else str(member.source_id)
        if family in families:raise ValueError('batch_cannot_publish_two_versions_of_one_family')
        families.add(family)
    for member in request.members:
        revision=await activate_version(conn,member.source_id,owner_id,member.expected_revision)
        members.append({'source_id':str(member.source_id),'revision':revision})
    result={'members':members,'access_epoch':await bump_epoch(conn,owner_id),'request_id':str(request.request_id),'replayed':False,'atomic':True}
    await record_operation(conn,owner_id,request.request_id,fingerprint,None,'publish_batch',request.reason,result)
    return result


async def apply_lifecycle_action(conn,source_id,owner_id,request):
    await lock_owner(conn,owner_id)
    fingerprint=identity({'source_id':str(source_id),'request':request.model_dump(mode='json')})
    replay=await prior_operation(conn,owner_id,request.request_id,fingerprint)
    if replay:return replay
    source,lc=await owned_source(conn,source_id,owner_id)
    if (lc['revision'] if lc else 0)!=request.expected_revision:raise ValueError('source_lifecycle_revision_conflict')
    if lc is None:
        await adopt_legacy(conn,source_id,owner_id);source,lc=await owned_source(conn,source_id,owner_id)
    before_access=dict(lc)
    impact=await affected_reports(conn,source_id,owner_id)
    removed=[];removed_indexes=[]
    if request.action=='activate':await activate_version(conn,source_id,owner_id,lc['revision'])
    elif request.action=='set_access':
        policy=request.policy;await validate_policy(conn,owner_id,policy)
        await conn.execute('''UPDATE document_source_lifecycle SET reuse_scope=$3,task_id=$4::uuid,valid_from=$5,valid_until=$6,purge_after=$7,
            revision=revision+1,updated_at=NOW() WHERE source_id=$1::uuid AND owner_id=$2::uuid''',str(source_id),str(owner_id),policy.reuse_scope,str(policy.task_id) if policy.task_id else None,policy.valid_from,policy.valid_until,policy.purge_after)
    elif request.action=='tombstone':
        await conn.execute("UPDATE document_source_lifecycle SET state='tombstone',is_current=FALSE,revision=revision+1,updated_at=NOW() WHERE source_id=$1::uuid AND owner_id=$2::uuid",str(source_id),str(owner_id))
        await conn.execute("UPDATE document_sources SET status='archived',updated_at=NOW() WHERE id=$1::uuid AND owner_id=$2::uuid",str(source_id),str(owner_id))
    elif request.action=='restore':
        current=await conn.fetchval('SELECT source_id FROM document_source_lifecycle WHERE owner_id=$1::uuid AND family_id=$2::uuid AND is_current',str(owner_id),str(lc['family_id']))
        await conn.execute("UPDATE document_source_lifecycle SET state='retained',is_current=$3,revision=revision+1,updated_at=NOW() WHERE source_id=$1::uuid AND owner_id=$2::uuid",str(source_id),str(owner_id),current is None or str(current)==str(source_id))
        await conn.execute("UPDATE document_sources SET status='active',updated_at=NOW() WHERE id=$1::uuid AND owner_id=$2::uuid",str(source_id),str(owner_id))
    elif request.action=='prune_indexes':
        # The source row lock also serializes this with index publication.
        rows=await conn.fetch('''SELECT g.id FROM retrieval_index_generations g WHERE g.source_id=$1::uuid AND g.owner_id=$2::uuid
            AND g.status='retired' AND g.created_at<$3 AND NOT EXISTS(SELECT 1 FROM source_index_heads h WHERE h.generation_id=g.id)
            ORDER BY g.created_at,g.id LIMIT 20 FOR UPDATE''',str(source_id),str(owner_id),request.before)
        removed_indexes=[str(row['id']) for row in rows]
        if removed_indexes:await conn.execute('DELETE FROM retrieval_index_generations WHERE owner_id=$1::uuid AND id=ANY($2::uuid[])',str(owner_id),[UUID(item) for item in removed_indexes])
    else:
        if request.action=='purge':
            if lc['is_current'] or (lc['state']!='tombstone' and (lc['purge_after'] is None or lc['purge_after']>datetime.now(timezone.utc))):raise ValueError('only_deleted_or_due_noncurrent_source_can_be_purged')
            removed=[str(source_id)]
        else:
            rows=await conn.fetch('''SELECT source_id FROM document_source_lifecycle WHERE owner_id=$1::uuid AND family_id=$2::uuid
                AND NOT is_current AND purge_after<=NOW() ORDER BY purge_after,source_id LIMIT 20 FOR UPDATE''',str(owner_id),str(lc['family_id']))
            removed=[str(row['source_id']) for row in rows]
        if removed:
            impact={'by_source':{item:await affected_reports(conn,item,owner_id) for item in removed},
                'reports_automatically_rewritten':False}
            await conn.execute('DELETE FROM documents WHERE owner_id=$1::uuid AND source_id=ANY($2::uuid[])',str(owner_id),[UUID(item) for item in removed])
            await conn.execute('DELETE FROM document_sources WHERE owner_id=$1::uuid AND id=ANY($2::uuid[])',str(owner_id),[UUID(item) for item in removed])
    next_revision=await conn.fetchval('SELECT revision FROM document_source_lifecycle WHERE source_id=$1::uuid AND owner_id=$2::uuid',str(source_id),str(owner_id))
    after_access=await conn.fetchrow('SELECT * FROM document_source_lifecycle WHERE source_id=$1::uuid AND owner_id=$2::uuid',str(source_id),str(owner_id))
    result={'source_id':str(source_id),'action':request.action,'revision':next_revision,'purged_source_ids':removed,
        'before_access':before_access,'after_access':dict(after_access) if after_access else None,
        'pruned_index_generation_ids':removed_indexes,
        'access_epoch':await bump_epoch(conn,owner_id),'affected_reports':impact,'request_id':str(request.request_id),'replayed':False,
        'effects':{'model_calls':0,'report_rewrites':0,'automatic_background_jobs':0}}
    await record_operation(conn,owner_id,request.request_id,fingerprint,source_id,request.action,request.reason,result)
    return result


async def revise_source(conn,source_id,owner_id,request,create_revision):
    await lock_owner(conn,owner_id)
    fingerprint=identity({'source_id':str(source_id),'revision':request.model_dump(mode='json')})
    replay=await prior_operation(conn,owner_id,request.request_id,fingerprint)
    if replay:return replay
    source,lc=await owned_source(conn,source_id,owner_id)
    if (lc['revision'] if lc else 0)!=request.expected_revision:raise ValueError('source_lifecycle_revision_conflict')
    metadata=object_value(source['metadata'])
    if metadata.get('parse_version_id')!=request.expected_parse_version:raise ValueError('revision_original_parse_version_conflict')
    if lc is None:
        await adopt_legacy(conn,source_id,owner_id);source,lc=await owned_source(conn,source_id,owner_id)
    if lc['state']!='retained' or source['status']!='active':raise ValueError('cannot_revise_deleted_or_inactive_source')
    original=source['original_text'] or ''
    if request.mode=='patch':
        if not metadata.get('parse_version_id'):raise ValueError('legacy_patch_requires_stable_parse_version')
        if request.end>len(original):raise ValueError('patch_outside_retained_original')
        text=original[:request.start]+request.text+original[request.end:]
    else:text=request.text
    if text==original:raise ValueError('revision_has_no_text_change')
    policy=RetentionPolicy.model_validate({key:lc[key] for key in ('reuse_scope','task_id','valid_from','valid_until','purge_after')})
    created=await create_revision(text,source,metadata,policy)
    new_id=created['source_id']
    previous_current=await conn.fetchval('SELECT source_id FROM document_source_lifecycle WHERE owner_id=$1::uuid AND family_id=$2::uuid AND is_current',str(owner_id),str(lc['family_id']))
    await conn.execute('''UPDATE document_source_lifecycle SET family_id=$3::uuid,predecessor_id=$4::uuid,is_current=FALSE,
        revision=revision+1,updated_at=NOW() WHERE source_id=$1::uuid AND owner_id=$2::uuid''',str(new_id),str(owner_id),str(lc['family_id']),str(source_id))
    if request.publish:await activate_version(conn,new_id,owner_id,2)
    result={**created,'predecessor_id':str(source_id),'family_id':str(lc['family_id']),
        'published':request.publish,'reason':request.reason,'patch_range':{'start':request.start,'end':request.end} if request.mode=='patch' else None,
        'predecessor_access_before':dict(lc),'previous_current_source_id':str(previous_current) if previous_current else None,
        'revision':await conn.fetchval('SELECT revision FROM document_source_lifecycle WHERE source_id=$1::uuid AND owner_id=$2::uuid',str(new_id),str(owner_id)),
        'affected_reports':{'by_source':{item:await affected_reports(conn,item,owner_id) for item in sorted({str(source_id)}|({str(previous_current)} if request.publish and previous_current else set()))},'reports_automatically_rewritten':False},'access_epoch':await bump_epoch(conn,owner_id),
        'request_id':str(request.request_id),'replayed':False,'old_reports_rewritten':False}
    await record_operation(conn,owner_id,request.request_id,fingerprint,source_id,'revise_source',request.reason,result)
    return result


async def lifecycle_view(conn,source_id,owner_id):
    source=await conn.fetchrow('SELECT status,group_name,metadata->>\'parse_version_id\' AS parse_version FROM document_sources WHERE id=$1::uuid AND owner_id=$2::uuid',str(source_id),str(owner_id))
    if not source:raise ValueError('source_not_found')
    lc=await conn.fetchrow('SELECT * FROM document_source_lifecycle WHERE source_id=$1::uuid AND owner_id=$2::uuid',str(source_id),str(owner_id))
    versions=await conn.fetch('''SELECT l.*,s.name,s.status,s.metadata->>'parse_version_id' AS parse_version FROM document_source_lifecycle l
        JOIN document_sources s ON s.id=l.source_id AND s.owner_id=l.owner_id
        WHERE l.owner_id=$1::uuid AND l.family_id=$2::uuid ORDER BY l.created_at DESC,l.source_id LIMIT 51''',str(owner_id),str(lc['family_id']) if lc else str(source_id))
    events=await conn.fetch('SELECT request_id,kind,reason,created_at,result FROM source_lifecycle_events WHERE owner_id=$1::uuid AND (source_id=$2::uuid OR result->>\'source_id\'=$2::text OR kind=\'publish_batch\' AND result->\'members\' @> $3::jsonb) ORDER BY created_at DESC LIMIT 20',str(owner_id),str(source_id),json.dumps([{'source_id':str(source_id)}]))
    return {'schema_version':VERSION,'source_id':str(source_id),'source_status':source['status'],'group_name':source['group_name'],'parse_version':source['parse_version'],
        'current':dict(lc) if lc else {'revision':0,'reuse_scope':'legacy_explicit_group','state':'unknown_legacy','is_current':None},
        'versions':[dict(row) for row in versions[:50]],'has_more_versions':len(versions)>50,
        'events':[{**dict(row),'result':object_value(row['result'])} for row in events],
        'access_epoch':await conn.fetchval('SELECT epoch FROM source_access_epochs WHERE owner_id=$1::uuid',str(owner_id)) or 0,
        'maintenance':{'selected':'transactional_per_source_increment_and_explicit_retained_feature_rebuild','not_selected':['background_merge','ANN_retraining','vector_compression','automatic_purge_daemon'],
            'reason':'current_lexical_and_exact_indexes_need_no_training; no measured scale benefit or unattended cleanup requirement','reconsider_when':'measured_maintenance_backlog_or_scale_with_owned_rollback_and_cost_evidence'},
        'report_semantics':'historical_task_evidence_remains_immutable; source_purge_is_not_task_deletion'}


async def current_synthesis_state(state):
    """Retained history stays intact; a new synthesis rechecks private evidence."""
    import asyncio
    import asyncpg
    from app.db.connection import get_db_pool
    gaps=list(state.get('evidence_access_gaps') or [])
    blocked={gap['evidence_id'] for gap in gaps};accepted=[];new_gap=False
    candidates=[]
    for evidence in state.get('collected_evidence',[]):
        if evidence.get('evidence_id') in blocked:continue
        if evidence.get('source_type')=='knowledge_base':candidates.append(evidence)
        else:
            from app.external_evidence import public_synthesis_gap
            reason=public_synthesis_gap(evidence,state)
            if reason:
                gaps.append({'evidence_id':evidence.get('evidence_id'),'reason':reason});new_gap=True
            else:accepted.append(evidence)
    if not candidates:
        result={**state,'collected_evidence':accepted,'evidence_access_gaps':gaps}
        if new_gap:result.update(analysis='',verification=None,organization_result=None)
        return result
    session=state.get('session') or {};memo={}
    try:
        pool=await get_db_pool()
        async with asyncio.timeout(10),pool.acquire() as conn,conn.transaction(readonly=True):
            for evidence in candidates:
                acquisition=evidence.get('acquisition') or {};source_id=acquisition.get('source_document_id')
                key=(source_id,acquisition.get('source_access_revision'))
                if key not in memo:
                    memo[key]=bool(source_id and session.get('owner_id') and await current_access(conn,source_id,session['owner_id'],session.get('session_id'),state.get('rag_group'),key[1]))
    except (asyncpg.PostgresError,TimeoutError,OSError,ValueError):memo={}
    for evidence in candidates:
        acquisition=evidence.get('acquisition') or {};key=(acquisition.get('source_document_id'),acquisition.get('source_access_revision'))
        if memo.get(key):accepted.append(evidence)
        else:
            gaps.append({'evidence_id':evidence.get('evidence_id'),'source_id':key[0],'reason':'current_internal_source_access_not_established'})
            new_gap=True
    result={**state,'collected_evidence':accepted,'evidence_access_gaps':gaps}
    if new_gap:result.update(analysis='',verification=None,organization_result=None)
    return result
