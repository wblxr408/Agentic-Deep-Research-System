"""Typed research records and a bounded view of the existing RAG sources."""
from __future__ import annotations

import base64
import binascii
from datetime import datetime
import json
from typing import Literal
from uuid import UUID

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
