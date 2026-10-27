"""Explicit, reversible identity links for source-anchored entity candidates."""
from __future__ import annotations

import json
import re
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID,uuid4

from fastapi import HTTPException
from pydantic import Field,model_validator

from app.db.connection import get_db_pool
from app.document_processing import _active_owner,_object,_source
from app.evidence_chunks import identity
from app.research_scope import ScopeRecord


class EntityLinkAction(ScopeRecord):
    request_id:UUID
    action:Literal['link','revoke']
    operation_id:UUID|None=None
    entity_index:int|None=Field(default=None,ge=0,le=99)
    target_uri:str|None=Field(default=None,min_length=3,max_length=1000)
    link_id:UUID|None=None
    expected_revision:int|None=Field(default=None,ge=1)

    @model_validator(mode='after')
    def fields_for_action(self):
        if self.action=='link':
            if self.operation_id is None or self.entity_index is None or self.target_uri is None or self.link_id is not None or self.expected_revision is not None:
                raise ValueError('entity_link_request_invalid')
        elif self.link_id is None or self.expected_revision is None or self.operation_id is not None or self.entity_index is not None or self.target_uri is not None:
            raise ValueError('entity_link_request_invalid')
        return self


def _uri(value):
    value=value.strip()
    if any(ord(char)<33 or char in '<>"' for char in value):raise HTTPException(422,'entity_link_uri_invalid')
    if re.fullmatch(r'urn:[A-Za-z0-9][A-Za-z0-9-]{0,31}:[^\s]+',value,re.IGNORECASE):return value
    try:parts=urlsplit(value)
    except ValueError:raise HTTPException(422,'entity_link_uri_invalid') from None
    if parts.scheme!='https' or not parts.hostname or parts.username is not None or parts.password is not None or parts.query:
        raise HTTPException(422,'entity_link_uri_invalid')
    return value


def _view(row):
    return {'id':str(row['id']),'operation_id':str(row['operation_id']),'entity_index':row['entity_index'],
        'name':row['entity_name'],'kind':row['entity_kind'],'start':row['span_start'],'end':row['span_end'],
        'target_uri':row['target_uri'],'state':row['state'],'revision':row['revision'],
        'identity_status':'user_declared_not_independently_verified','parse_version':row['parse_version'],
        'chunk_id':row['chunk_id']}


async def list_links(owner,source_id):
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        source=await _source(conn,owner,source_id);version=_object(source['metadata']).get('parse_version_id')
        rows=await conn.fetch('''SELECT * FROM source_entity_links WHERE owner_id=$1::uuid AND source_id=$2::uuid
            AND parse_version=$3 AND lifecycle_revision=$4 ORDER BY created_at DESC,id DESC LIMIT 501''',str(owner),str(source_id),version,source['lifecycle_revision'])
    return {'items':[_view(row) for row in rows[:500]],'has_more':len(rows)>500}


async def apply_link(owner,source_id,request):
    uri=_uri(request.target_uri) if request.action=='link' else None
    payload=request.model_dump(mode='json',exclude={'request_id'});payload['target_uri']=uri
    fingerprint=identity({'source_id':str(source_id),**payload});pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await _active_owner(conn,owner);source=await _source(conn,owner,source_id,lock=True)
        prior=await conn.fetchrow('SELECT * FROM source_entity_link_actions WHERE owner_id=$1::uuid AND request_id=$2::uuid',str(owner),str(request.request_id))
        if prior:
            if prior['fingerprint']!=fingerprint or str(prior['source_id'])!=str(source_id):raise HTTPException(409,'entity_link_request_conflict')
            return {**_object(prior['result']),'replayed':True}
        metadata=_object(source['metadata']);parse_version=metadata.get('parse_version_id')
        changed=False
        if request.action=='link':
            op=await conn.fetchrow('''SELECT * FROM document_processing_operations WHERE id=$1::uuid AND owner_id=$2::uuid AND source_id=$3::uuid FOR UPDATE''',
                str(request.operation_id),str(owner),str(source_id))
            if (not op or op['kind']!='entity_extraction' or op['status']!='completed' or op['parse_version']!=parse_version
                    or op['lifecycle_revision']!=source['lifecycle_revision']):raise HTTPException(409,'entity_link_candidate_unavailable')
            result=_object(op['result']);entities=result.get('entities') or []
            if request.entity_index>=len(entities):raise HTTPException(422,'entity_link_candidate_unavailable')
            entity=entities[request.entity_index];text=source['original_text'] or '';start=entity.get('start');end=entity.get('end')
            if type(start) is not int or type(end) is not int or not 0<=start<end<=len(text) or text[start:end]!=entity.get('name'):
                raise HTTPException(409,'entity_link_source_span_changed')
            primary=_object(op['input_description']).get('primary') or {};chunk_id=primary.get('chunk_id')
            if not chunk_id:raise HTTPException(409,'entity_link_candidate_unavailable')
            existing=await conn.fetchrow('''SELECT * FROM source_entity_links WHERE owner_id=$1::uuid AND operation_id=$2::uuid AND entity_index=$3 AND state='active' FOR UPDATE''',
                str(owner),str(request.operation_id),request.entity_index)
            if existing and existing['target_uri']!=uri:raise HTTPException(409,'entity_link_already_has_target')
            if existing:row=existing
            else:
                reused=await conn.fetchval('''SELECT id FROM source_entity_links WHERE owner_id=$1::uuid AND operation_id=$2::uuid AND entity_index=$3 AND target_uri=$4''',
                    str(owner),str(request.operation_id),request.entity_index,uri)
                if not reused and await conn.fetchval('SELECT count(*) FROM source_entity_links WHERE owner_id=$1::uuid AND source_id=$2::uuid',str(owner),str(source_id))>=500:
                    raise HTTPException(429,'entity_link_limit')
                row=await conn.fetchrow('''INSERT INTO source_entity_links(id,owner_id,source_id,operation_id,parse_version,lifecycle_revision,chunk_id,
                    entity_index,entity_kind,entity_name,span_start,span_end,target_uri,state,revision)
                    VALUES($1::uuid,$2::uuid,$3::uuid,$4::uuid,$5,$6,$7,$8,$9,$10,$11,$12,$13,'active',1)
                    ON CONFLICT(owner_id,operation_id,entity_index,target_uri) DO UPDATE SET state='active',revision=source_entity_links.revision+1,updated_at=NOW()
                    RETURNING *''',uuid4(),str(owner),str(source_id),str(request.operation_id),parse_version,source['lifecycle_revision'],chunk_id,
                    request.entity_index,entity['kind'],entity['name'],start,end,uri)
                changed=True
        else:
            row=await conn.fetchrow('SELECT * FROM source_entity_links WHERE id=$1::uuid AND owner_id=$2::uuid AND source_id=$3::uuid FOR UPDATE',
                str(request.link_id),str(owner),str(source_id))
            if not row:raise HTTPException(404,'entity_link_not_found')
            if row['parse_version']!=parse_version or row['lifecycle_revision']!=source['lifecycle_revision'] or row['revision']!=request.expected_revision:
                raise HTTPException(409,'entity_link_revision_conflict')
            if row['state']=='active':
                row=await conn.fetchrow("UPDATE source_entity_links SET state='revoked',revision=revision+1,updated_at=NOW() WHERE id=$1::uuid AND owner_id=$2::uuid RETURNING *",str(request.link_id),str(owner))
                changed=True
        view=_view(row)
        if changed:
            from app.source_lifecycle import bump_epoch
            view['access_epoch']=await bump_epoch(conn,owner)
        await conn.execute('INSERT INTO source_entity_link_actions(owner_id,request_id,source_id,fingerprint,result) VALUES($1::uuid,$2::uuid,$3::uuid,$4,$5::jsonb)',
            str(owner),str(request.request_id),str(source_id),fingerprint,json.dumps(view,ensure_ascii=False))
        return {**view,'replayed':False}
