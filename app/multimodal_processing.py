"""Owner/version scoped image-text feature jobs using the shared processing lease."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
from datetime import UTC,datetime
from uuid import uuid4

from fastapi import HTTPException

from app.channels.models import ChannelError
from app.db.connection import get_db_pool
from app.document_processing import (_active_owner,_expire,_fail,_object,_public,_render,_source,
    MAX_ACTIVE_PER_OWNER,MAX_OPERATIONS_PER_SOURCE)
from app.evidence_chunks import identity
from app.multimodal import configuration,encode_image_text

logger=logging.getLogger(__name__)


async def _begin(owner,source_id,request_id,parse_version,raw,selection,config):
    digest=hashlib.sha256(raw).hexdigest()
    fingerprint=identity({'source_id':str(source_id),'kind':'image_embedding','parse_version':parse_version,
        'file_version':digest,'selection':selection,'model':config})
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await _active_owner(conn,owner);await _expire(conn,owner)
        source=await _source(conn,owner,source_id,lock=True);metadata=_object(source['metadata'])
        structure=metadata.get('document_parse') or {}
        if metadata.get('parse_version_id')!=parse_version:raise HTTPException(409,'processing_source_version_changed')
        if metadata.get('content_hash')!=digest or metadata.get('intake_mode')!='explicit_upload_event':
            raise HTTPException(409,'processing_original_file_mismatch')
        prior=await conn.fetchrow('SELECT * FROM document_processing_operations WHERE owner_id=$1::uuid AND request_id=$2::uuid',str(owner),str(request_id))
        if prior:
            if prior['request_fingerprint']!=fingerprint:raise HTTPException(409,'processing_request_conflict')
            record=_public(prior)
            if prior['lifecycle_revision']!=source['lifecycle_revision']:record.update(result=None,error_category='processing_context_changed')
            return record,None
        fmt=source['file_ext'];start=end=None
        if fmt=='pdf' and selection['kind']=='page':
            item=next((item for item in structure.get('pages',[]) if item.get('number')==selection['page']),None)
            if not item:raise HTTPException(422,'visual_page_not_available')
            start=item.get('start');end=item.get('end');actual=selection
        elif fmt=='docx' and selection['kind']=='figure':
            item=next((item for item in structure.get('figures',[]) if item.get('figure_id')==selection['figure_id']),None)
            if not item or not item.get('embedded_image_present') or item.get('target_mode')=='External':raise HTTPException(422,'visual_embedded_image_unavailable')
            actual={**selection,'target':item.get('source_target','')}
            block=next((block for block in structure.get('blocks',[]) if block.get('block_id')==item.get('associated_block_id')),None)
            if block:start=block.get('start');end=block.get('end')
        else:raise HTTPException(422,'visual_source_format_unsupported')
        text=source['original_text'] or ''
        if type(start) is not int or type(end) is not int or not 0<=start<=end<=len(text):start=end=0
        source_range={'start':start,'end':end} if end>start else None
        selected=text[start:end]
        if await conn.fetchval("SELECT count(*) FROM document_processing_operations WHERE owner_id=$1::uuid AND status IN ('preparing','running')",str(owner))>=MAX_ACTIVE_PER_OWNER:
            raise HTTPException(429,'processing_active_limit')
        if await conn.fetchval("SELECT id FROM document_processing_operations WHERE owner_id=$1::uuid AND source_id=$2::uuid AND status IN ('preparing','running')",str(owner),str(source_id)):
            raise HTTPException(409,'processing_source_busy')
        if await conn.fetchval('SELECT count(*) FROM document_processing_operations WHERE owner_id=$1::uuid AND source_id=$2::uuid',str(owner),str(source_id))>=MAX_OPERATIONS_PER_SOURCE:
            raise HTTPException(429,'processing_history_limit')
        row=await conn.fetchrow('''INSERT INTO document_processing_operations(id,owner_id,source_id,request_id,request_fingerprint,kind,
            parse_version,lifecycle_revision,model_provider,model_name,model_config_version,input_description,status,deadline_at)
            VALUES($1::uuid,$2::uuid,$3::uuid,$4::uuid,$5,'image_embedding',$6,$7,'local',$8,$9,$10::jsonb,'running',NOW()+INTERVAL '240 seconds') RETURNING *''',
            uuid4(),str(owner),str(source_id),str(request_id),fingerprint,parse_version,source['lifecycle_revision'],
            config['model'],identity(config),json.dumps({'selection':selection,'source_file_version':digest,'source_text_range':source_range,
                'source_task_id':str(source['task_id']) if source['task_id'] else None}))
        return _public(row),{'format':fmt,'selection':actual,'text':selected[:16000],'text_start':start,'source_text_characters':len(selected),
            'lifecycle_revision':source['lifecycle_revision'],'file_version':digest}


async def _complete(owner,source_id,operation_id,parse_version,job,encoded,config,image):
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await _active_owner(conn,owner)
        try:source=await _source(conn,owner,source_id,lock=True)
        except HTTPException:source=None
        row=await conn.fetchrow('SELECT * FROM document_processing_operations WHERE id=$1::uuid AND owner_id=$2::uuid AND source_id=$3::uuid FOR UPDATE',str(operation_id),str(owner),str(source_id))
        if not row:return None
        if row['status']!='running':return _public(row)
        invalid=(not source or row['deadline_at']<=datetime.now(UTC) or row['lifecycle_revision']!=source['lifecycle_revision']
            or row['parse_version']!=_object(source['metadata']).get('parse_version_id') or row['model_config_version']!=identity(configuration())
            or _object(source['metadata']).get('content_hash')!=job['file_version'])
        if invalid:
            row=await conn.fetchrow("UPDATE document_processing_operations SET status='failed',error_category='processing_context_changed',updated_at=NOW() WHERE id=$1::uuid AND owner_id=$2::uuid RETURNING *",str(operation_id),str(owner))
            return _public(row)
        selection=_object(row['input_description']).get('selection') or {}
        preview=base64.b64decode(image['data'],validate=True)
        if len(preview)>1_400_000 or not preview.startswith(b'\xff\xd8\xff'):raise ValueError('multimodal_preview_invalid')
        retained=await conn.fetchval('SELECT COALESCE(sum(octet_length(image_preview)),0) FROM retrieval_multimodal_features WHERE owner_id=$1::uuid AND source_id=$2::uuid',str(owner),str(source_id))
        if retained+len(preview)>10*1024*1024:preview=None
        await conn.execute('''INSERT INTO retrieval_multimodal_features(operation_id,owner_id,source_id,source_version,model_profile,
            selection,dimension,image_vector,text_vectors,text_windows,image_preview) VALUES($1::uuid,$2::uuid,$3::uuid,$4,$5::jsonb,$6::jsonb,$7,$8,$9,$10::jsonb,$11)''',
            str(operation_id),str(owner),str(source_id),parse_version,json.dumps(encoded['profile']),json.dumps(selection),encoded['dimension'],
            encoded['image_bytes'],encoded['text_bytes'],json.dumps(encoded['windows']),preview)
        result={'status':'encoded','model_profile':encoded['profile'],'dimension':encoded['dimension'],'image_encoded':True,
            'text_windows':encoded['windows'],'coverage':encoded['coverage'],'preview_retained':preview is not None,'index_status':'not_published'}
        row=await conn.fetchrow('''UPDATE document_processing_operations SET status='completed',result=$3::jsonb,
            usage='{"status":"local_computation","cost_status":"not_measured"}'::jsonb,updated_at=NOW()
            WHERE id=$1::uuid AND owner_id=$2::uuid RETURNING *''',str(operation_id),str(owner),json.dumps(result))
        head=await conn.fetchrow('SELECT mode FROM source_index_heads WHERE source_id=$1::uuid AND owner_id=$2::uuid',str(source_id),str(owner))
        if head and head['mode']=='lexical':
            from app.db.retrieval_indexes import publish_source_index
            generation=await publish_source_index(conn,source_id,owner)
            if row['deadline_at']<=datetime.now(UTC):raise HTTPException(409,'processing_context_changed')
            result.update(index_status='published',generation_id=generation['generation_id'])
            row=await conn.fetchrow('''UPDATE document_processing_operations SET result=$3::jsonb,updated_at=NOW()
                WHERE id=$1::uuid AND owner_id=$2::uuid RETURNING *''',str(operation_id),str(owner),json.dumps(result))
        return _public(row)


async def image_text_operation(owner,source_id,request_id,parse_version,raw,selection):
    try:config=configuration()
    except ValueError:raise HTTPException(422,'multimodal_configuration_unavailable') from None
    operation,job=await _begin(owner,source_id,request_id,parse_version,raw,selection,config)
    if job is None:return operation
    operation_id=operation['operation_id']
    try:
        image=await asyncio.to_thread(_render,raw,job['format'],job['selection'])
        encoded=await asyncio.to_thread(encode_image_text,image,job['text'],job['text_start'],job['source_text_characters'])
        return await _complete(owner,source_id,operation_id,parse_version,job,encoded,config,image)
    except HTTPException as error:
        return await _fail(owner,source_id,operation_id,error.detail if isinstance(error.detail,str) else 'multimodal_processing_failed')
    except (ValueError,ChannelError):
        return await _fail(owner,source_id,operation_id,'multimodal_processing_failed')
    except Exception as error:
        logger.warning('Local image feature processing failed: %s',type(error).__name__)
        return await _fail(owner,source_id,operation_id,'multimodal_processing_failed')
