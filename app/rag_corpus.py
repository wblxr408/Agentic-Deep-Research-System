"""Typed research records and a bounded view of the existing RAG sources."""
from __future__ import annotations

import base64
import binascii
from datetime import datetime
import json
from typing import Literal
from uuid import UUID
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from app.research_scope import ScopeRecord
from app.evidence_chunks import identity

VERSION = 'adrs-rag-research-record-v1'
RecordKind = Literal['bibliography', 'abstract', 'fulltext', 'derived_card']


class SourceVersionReference(ScopeRecord):
    source_id: UUID
    parse_version_id: str = Field(min_length=1, max_length=260)


class ResearchSourceRecord(ScopeRecord):
    schema_version: Literal['adrs-rag-research-record-v1'] = VERSION
    work_id: str = Field(min_length=1, max_length=260)
    kind: RecordKind
    primary_sources: tuple[SourceVersionReference, ...] = Field(default=(), max_length=128)

    @model_validator(mode='after')
    def references(self):
        if not self.work_id.strip() or self.work_id != self.work_id.strip() or any(ord(c) < 32 for c in self.work_id):
            raise ValueError('research_work_id_invalid')
        if len({item.source_id for item in self.primary_sources}) != len(self.primary_sources):
            raise ValueError('research_primary_source_duplicate')
        if self.kind == 'derived_card' and not self.primary_sources:
            raise ValueError('derived_card_requires_versioned_primary_sources')
        return self


def normalize_metadata(metadata):
    if 'research_record' not in metadata:
        return metadata
    record = ResearchSourceRecord.model_validate(metadata['research_record'])
    value = record.model_dump(mode='json')
    value['primary_sources'] = sorted(value['primary_sources'], key=lambda item: (item['source_id'], item['parse_version_id']))
    return {**metadata, 'research_record': value}


async def validate_primary_sources(conn, owner_id, metadata):
    value = metadata.get('research_record')
    if value is None:
        return
    record = ResearchSourceRecord.model_validate(value)
    if not record.primary_sources:
        return
    rows = await conn.fetch('''SELECT id,metadata->>'parse_version_id' AS parse_version_id,
        metadata->'research_record'->>'kind' AS kind FROM document_sources
        WHERE owner_id=$1::uuid AND id=ANY($2::uuid[])''', str(owner_id),
        [item.source_id for item in record.primary_sources])
    current = {str(row['id']): row for row in rows}
    for reference in record.primary_sources:
        source = current.get(str(reference.source_id))
        if (not source or source['parse_version_id'] != reference.parse_version_id
                or source['kind'] == 'derived_card'):
            raise ValueError('research_primary_source_not_owned_original_version')


class CatalogCursor(ScopeRecord):
    version: Literal['adrs-rag-source-catalog-v1'] = 'adrs-rag-source-catalog-v1'
    scope_id: str = Field(pattern=r'^[0-9a-f]{64}$')
    access_epoch: int = Field(ge=0)
    created_at: datetime
    source_id: UUID

    @model_validator(mode='after')
    def database_time(self):
        # document_sources.created_at is the existing UTC-naive TIMESTAMP.
        if self.created_at.tzinfo is not None:
            raise ValueError('catalog_cursor_requires_source_timestamp')
        return self


async def catalog_page(conn, owner_id, *, group_name, record_kind, work_id,
                       status, lifecycle_state, is_current, page_size, cursor):
    """Caller holds a read-only repeatable-read transaction; cursors grant no access."""
    if not isinstance(page_size, int) or isinstance(page_size, bool) or not 1 <= page_size <= 200:
        raise ValueError('catalog_page_size_out_of_range')
    if cursor is not None and (not isinstance(cursor, str) or not 1 <= len(cursor) <= 2048):
        raise ValueError('catalog_cursor_invalid')
    scope_id = identity({'version': 'adrs-rag-source-catalog-v1', 'owner_id': str(owner_id),
        'group_name': group_name, 'record_kind': record_kind, 'work_id': work_id,
        'status': status, 'lifecycle_state': lifecycle_state, 'is_current': is_current,
        'page_size': page_size, 'order': 'created_at_null_epoch_desc_id_desc'})
    epoch = int(await conn.fetchval('SELECT epoch FROM source_access_epochs WHERE owner_id=$1::uuid', str(owner_id)) or 0)
    position = None
    if cursor:
        try:
            raw = base64.b64decode(cursor + '=' * (-len(cursor) % 4), altchars=b'-_', validate=True)
            position = CatalogCursor.model_validate_json(raw)
        except (ValueError, TypeError, binascii.Error):
            raise ValueError('catalog_cursor_invalid') from None
        if position.scope_id != scope_id:
            raise ValueError('catalog_cursor_scope_changed')
        if position.access_epoch != epoch:
            raise ValueError('catalog_snapshot_changed_restart_enumeration')
    rows = await conn.fetch('''SELECT s.id,s.name,s.group_name,s.source_type,s.file_name,s.file_ext,
        s.status,s.created_at,s.updated_at,COALESCE(s.created_at,TIMESTAMP '1970-01-01') AS catalog_order_time,
        s.metadata->'research_record' AS research_record,
        s.metadata->>'parse_version_id' AS parse_version_id,s.metadata->>'source_version' AS source_version,
        s.metadata->>'url' AS source_url,l.state AS lifecycle_state,l.is_current,l.revision AS source_access_revision,
        l.reuse_scope,l.task_id AS bound_task_id,l.valid_from,l.valid_until,
        h.mode AS index_mode,h.generation_id AS index_generation_id
        FROM document_sources s
        LEFT JOIN document_source_lifecycle l ON l.source_id=s.id AND l.owner_id=s.owner_id
        LEFT JOIN source_index_heads h ON h.source_id=s.id AND h.owner_id=s.owner_id
        WHERE s.owner_id=$1::uuid AND ($2::text IS NULL OR s.group_name=$2)
        AND ($3::text IS NULL OR s.metadata->'research_record'->>'kind'=$3)
        AND ($4::text IS NULL OR s.metadata->'research_record'->>'work_id'=$4)
        AND ($5::text IS NULL OR s.status=$5)
        AND ($6::text IS NULL OR COALESCE(l.state,'legacy')=$6)
        AND ($7::boolean IS NULL OR l.is_current=$7)
        AND ($8::timestamp IS NULL OR (COALESCE(s.created_at,TIMESTAMP '1970-01-01'),s.id)<($8::timestamp,$9::uuid))
        ORDER BY COALESCE(s.created_at,TIMESTAMP '1970-01-01') DESC,s.id DESC LIMIT $10''', str(owner_id), group_name,
        record_kind, work_id, status, lifecycle_state, is_current,
        position.created_at if position else None, position.source_id if position else None, page_size + 1)
    more = len(rows) > page_size
    rows = rows[:page_size]
    items = []
    for row in rows:
        item = dict(row)
        item.pop('catalog_order_time', None)
        record = item['research_record']
        if isinstance(record, str):
            record = json.loads(record)
        item['research_record'] = record
        item['material_kind'] = record.get('kind') if isinstance(record, dict) else None
        item['work_id'] = record.get('work_id') if isinstance(record, dict) else None
        items.append(item)
    next_cursor = None
    if more:
        tail = rows[-1]
        value = CatalogCursor(scope_id=scope_id, access_epoch=epoch,
            created_at=tail['catalog_order_time'], source_id=tail['id'])
        next_cursor = base64.urlsafe_b64encode(value.model_dump_json().encode()).decode().rstrip('=')
    return {'version': 'adrs-rag-source-catalog-v1', 'scope_id': scope_id, 'access_epoch': epoch,
        'items': items, 'next_cursor': next_cursor, 'enumeration_complete': not more,
        'membership_unit': 'source_version_record_not_unique_work',
        'semantics': 'owned_catalog_not_task_reading_completion_source_support_or_retrieval_permission',
        'snapshot_rule': 'owner_source_mutation_invalidates_cursor_no_silent_membership_skip'}


async def freeze_members(conn, owner_id, source_ids, *, group, task_id, max_nodes, read_max_chars):
    """Freeze exact owned source versions at submission, without reading/embedding bodies."""
    from app.source_lifecycle import current_access
    from app.data_governance import sensitive_url
    task_id=str(UUID(str(task_id))) if task_id else None
    ids=[str(UUID(str(value))) for value in source_ids]
    if not ids or len(ids)!=len(set(ids)):raise ValueError('rag_corpus_members_invalid')
    if (len(ids)+1)//2+1>max_nodes:raise ValueError('rag_corpus_exceeds_existing_plan_node_limit')
    rows=await conn.fetch('''SELECT id,name,group_name,metadata FROM document_sources
        WHERE owner_id=$1::uuid AND id=ANY($2::uuid[])''',str(owner_id),[UUID(value) for value in ids])
    by_id={str(row['id']):row for row in rows};members=[]
    for source_id in ids:
        row=by_id.get(source_id)
        if not row:raise ValueError('rag_corpus_source_not_owned')
        metadata=json.loads(row['metadata']) if isinstance(row['metadata'],str) else row['metadata'] or {}
        try:record=ResearchSourceRecord.model_validate(metadata.get('research_record'))
        except ValueError:raise ValueError('rag_corpus_requires_typed_work_identity') from None
        if record.kind=='derived_card':raise ValueError('rag_corpus_requires_original_sources_not_cards')
        snapshot=await current_access(conn,source_id,owner_id,task_id,group,with_snapshot=True)
        if not snapshot:raise ValueError('rag_corpus_source_not_current_or_not_in_task_scope')
        version=metadata.get('parse_version_id');url=metadata.get('url')
        if not version:raise ValueError('rag_corpus_source_version_unavailable')
        if not isinstance(url,str) or not 1<=len(url)<=4000:
            raise ValueError('rag_corpus_requires_stable_original_source_locator')
        parts=urlsplit(url)
        if (parts.scheme not in {'http','https'} or not parts.hostname or parts.username or parts.password
                or sensitive_url(url)):
            raise ValueError('rag_corpus_requires_stable_original_source_locator')
        members.append({'source_id':source_id,'work_id':record.work_id,'record_kind':record.kind,
            'name':row['name'],'source_url':url,'parse_version_id':version,
            'source_content_version':metadata.get('content_hash'),
            'source_access_revision':snapshot['revision']})
    body={'version':'adrs-rag-membership-v1','owner_id':str(owner_id),'group_name':group,
        'read_max_chars':int(read_max_chars),'members':members,
        'declared_work_count':len({item['work_id'] for item in members}),
        'semantics':'declared_source_set_not_screening_reading_or_support_approval'}
    return {**body,'scope_id':identity(body)}


async def read_frozen_sources(conn,source_ids,manifest,*,owner_id,task_id,group):
    """Read at most two explicit sources; ranking and model encoders are not used."""
    from app.source_lifecycle import current_access
    if not owner_id or not task_id:raise ValueError('rag_source_read_requires_task_context')
    if (not manifest or manifest.get('version')!='adrs-rag-membership-v1'
            or manifest.get('owner_id')!=str(owner_id) or manifest.get('group_name')!=group):
        raise ValueError('frozen_rag_corpus_scope_required')
    ids=[str(UUID(str(value))) for value in source_ids]
    if not 1<=len(ids)<=2 or len(set(ids))!=len(ids):raise ValueError('rag_source_read_batch_invalid')
    members={item['source_id']:item for item in manifest['members']}
    if any(source_id not in members for source_id in ids):raise ValueError('rag_source_not_in_frozen_membership')
    limit=manifest.get('read_max_chars')
    if not isinstance(limit,int) or isinstance(limit,bool) or limit<1:raise ValueError('rag_source_read_bound_invalid')
    results=[];gaps=[]
    for source_id in ids:
        member=members[source_id]
        snapshot=await current_access(conn,source_id,owner_id,task_id,group,
            member['source_access_revision'],with_snapshot=True)
        if not snapshot:
            gaps.append({'source_id':source_id,'work_id':member['work_id'],'reason':'current_source_access_or_revision_changed'})
            continue
        row=await conn.fetchrow('''SELECT name,original_text,metadata FROM document_sources
            WHERE id=$1::uuid AND owner_id=$2::uuid AND metadata->>'parse_version_id'=$3
            AND metadata->>'content_hash' IS NOT DISTINCT FROM $4::text''',
            source_id,str(owner_id),member['parse_version_id'],member['source_content_version'])
        if not row:
            gaps.append({'source_id':source_id,'work_id':member['work_id'],'reason':'frozen_source_version_unavailable'})
            continue
        text=row['original_text'] or ''
        if not text.strip() or len(text)>limit:
            gaps.append({'source_id':source_id,'work_id':member['work_id'],
                'reason':'retained_text_unavailable' if not text.strip() else 'retained_text_exceeds_source_read_bound',
                'text_characters':len(text),'read_bound':limit})
            continue
        metadata=json.loads(row['metadata']) if isinstance(row['metadata'],str) else row['metadata'] or {}
        record=ResearchSourceRecord.model_validate(metadata.get('research_record'))
        if (record.work_id!=member['work_id'] or record.kind!=member['record_kind']
                or metadata.get('url')!=member['source_url']):
            gaps.append({'source_id':source_id,'work_id':member['work_id'],'reason':'frozen_source_identity_changed'})
            continue
        # Check again after the body read; stale text cannot enter model context.
        current=await current_access(conn,source_id,owner_id,task_id,group,member['source_access_revision'],with_snapshot=True)
        if not current:
            gaps.append({'source_id':source_id,'work_id':member['work_id'],'reason':'source_access_changed_during_read'})
            continue
        parse=metadata.get('document_parse') or {}
        complete=record.kind=='fulltext' and not parse.get('truncated') and not parse.get('unreadable_pages')
        stable_access={key:value for key,value in current.items() if key!='checked_at'}
        results.append({'source_id':source_id,'content':text,'metadata':{
            'source_id':source_id,'title':row['name'],'url':member['source_url'],
            'parse_version_id':member['parse_version_id'],'content_hash':member['source_content_version'],
            'research_record':{key:value for key,value in record.model_dump(mode='json').items() if key!='primary_sources'},
            'corpus_scope_id':manifest['scope_id'],'source_access_revision':member['source_access_revision'],
            'source_access_snapshot':stable_access,
            'retrieval_selector':'explicit_frozen_source','retrieval_score_scope':'selection_not_relevance',
            'retained_source':{'format':'internal_source','coverage':'full_text' if complete else 'abstract_or_partial_text',
                'truncated':bool(parse.get('truncated')),'complete_retained_artifact':complete,
                'retained_characters':len(text),'pages':[
                    {key:page[key] for key in ('number','start','end') if key in page}
                    for page in parse.get('pages') or [] if isinstance(page,dict)],
                'full_text_basis':'owner_declared_original_complete_retained_artifact_not_publication_authentication'}}})
    return results,gaps
