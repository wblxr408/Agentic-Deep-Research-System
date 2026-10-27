"""
Document source CRUD and ingest API.
"""

from __future__ import annotations

import hashlib
import asyncio
import io
import json
import logging
import re
import uuid
import asyncpg
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, model_validator

from app.core.time import utc_now_naive
from app.db.connection import get_db_pool
from app.rag.embedder import Embedder
from app.security.auth import Principal, require_principal
from app.evidence_chunks import ChunkPolicy,VERSION as CHUNK_VERSION,build_chunk_plan,parent_window,_span
from app.retrieval_features import FeaturePolicy,build_feature_plan,dense_configuration,validate_vectors,vector_parameter
from app.db.retrieval_indexes import IndexPolicy,IndexAction,initialize_source_index,apply_index_action,adjacency_view,index_choices,source_chunk_metadata,VERSION as INDEX_VERSION
from app.source_lifecycle import (RetentionPolicy,LifecycleAction,SourceRevision,BatchPublication,lock_owner,
    initialize_lifecycle,apply_lifecycle_action,publish_batch,revise_source,lifecycle_view,bump_epoch)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/documents", tags=["documents"], dependencies=[Depends(require_principal)])
PrincipalDep = Annotated[Principal, Depends(require_principal)]
DocumentUpload = Annotated[UploadFile, File(...)]

ALLOWED_EXTENSIONS = {"json", "md", "docx", "pdf", "txt"}
TEXT_CONTENT_TYPES = {"text/plain", "text/markdown", "application/json", "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


class DocumentSourceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    group_name: str = Field(min_length=1, max_length=100)
    source_type: str = Field(default="manual", max_length=20)
    content: str | None = None
    file_name: str | None = None
    file_ext: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    chunk_size: int = Field(default=400, ge=100, le=4000)
    chunk_overlap: int = Field(default=80, ge=0, le=1000)
    chunk_policy:ChunkPolicy=Field(default_factory=ChunkPolicy)
    feature_policy:FeaturePolicy=Field(default_factory=FeaturePolicy)
    index_policy:IndexPolicy=Field(default_factory=IndexPolicy)
    retention_policy:RetentionPolicy=Field(default_factory=RetentionPolicy)


class DocumentSourceUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    group_name: str | None = Field(default=None, min_length=1, max_length=100)
    metadata: dict[str, Any] | None = None
    status: Literal['active','archived'] | None = None


class ParseReviewRequest(BaseModel):
    request_id:uuid.UUID
    parse_version_id:str=Field(min_length=1,max_length=260)
    status:Literal['accepted_structure','needs_correction','unreadable']
    note:str=Field(min_length=1,max_length=2000)


class DocumentTextProcessingRequest(BaseModel):
    request_id:uuid.UUID
    parse_version_id:str=Field(min_length=1,max_length=260)
    kind:Literal['cleaning','semantic_comparison','entity_extraction']
    block_id:str|None=Field(default=None,pattern=r'^block:[1-9][0-9]*$',max_length=40)
    chunk_id:str|None=Field(default=None,pattern=r'^chunk:[0-9a-f]{64}$',max_length=70)
    chunk_profile_id:str|None=Field(default=None,pattern=r'^[0-9a-f]{64}$',max_length=64)
    secondary_source_id:uuid.UUID|None=None
    secondary_parse_version:str|None=Field(default=None,min_length=1,max_length=260)
    secondary_block_id:str|None=Field(default=None,pattern=r'^block:[1-9][0-9]*$',max_length=40)
    language:Literal['zh','en']='zh'

    @model_validator(mode='after')
    def validate_secondary(self):
        complete=all((self.secondary_source_id,self.secondary_parse_version,self.secondary_block_id))
        supplied=any((self.secondary_source_id,self.secondary_parse_version,self.secondary_block_id))
        if (self.kind=='semantic_comparison' and not complete or self.kind!='semantic_comparison' and supplied
                or self.kind=='entity_extraction' and (not self.chunk_id or not self.chunk_profile_id or self.block_id is not None)
                or self.kind!='entity_extraction' and (not self.block_id or self.chunk_id is not None or self.chunk_profile_id is not None)):
            raise ValueError('processing_secondary_selection_invalid')
        return self


class DocumentAnnotationRequest(BaseModel):
    accepted:bool


class MarginCleaningRequest(BaseModel):
    request_id:uuid.UUID
    expected_parse_version:str=Field(min_length=1,max_length=260)
    expected_revision:int=Field(ge=0)
    candidate_id:str=Field(pattern=r'^margin:[1-9][0-9]*$',max_length=40)


def _slug_group(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]+", "_", name.strip()).strip("_").lower() or "default"


def _metadata(value):
    result=json.loads(value) if isinstance(value,str) else value or {}
    if not isinstance(result,dict):raise HTTPException(409,'invalid_stored_source_metadata')
    return result


def _chunk_text(text: str, chunk_size: int = 400, overlap: int = 80) -> list[str]:
    text = re.sub(r"\r\n?", "\n", text).strip()
    if not text:
        return []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current = ""

    def flush_current() -> None:
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            flush_current()
            start = 0
            while start < len(paragraph):
                end = min(start + chunk_size, len(paragraph))
                chunks.append(paragraph[start:end].strip())
                if end >= len(paragraph):
                    break
                start = max(end - overlap, start + 1)
            continue

        if not current:
            current = paragraph
            continue

        if len(current) + len(paragraph) + 2 <= chunk_size:
            current = current + "\n\n" + paragraph
        else:
            flush_current()
            current = paragraph

    flush_current()
    return chunks


def _extract_text_from_json(data: Any) -> str:
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        return "\n".join(_extract_text_from_json(item) for item in data)
    if isinstance(data, dict):
        lines: list[str] = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                nested = _extract_text_from_json(value)
                if nested:
                    lines.append(f"{key}: {nested}")
            else:
                lines.append(f"{key}: {value}")
        return "\n".join(lines)
    return str(data)


def _validate_file_signature(file_ext: str, raw: bytes) -> None:
    if file_ext == "pdf" and not raw.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="invalid_pdf_signature")
    if file_ext == "docx" and not raw.startswith(b"PK\x03\x04"):
        raise HTTPException(status_code=400, detail="invalid_docx_signature")


def _extract_plain_text(file_name: str, file_ext: str, raw: bytes) -> str:
    from app.research_documents import read_document
    return read_document(raw,format=file_ext.lower(),timeout=25)['text']


async def _ingest_source(
    *,
    name: str,
    group_name: str,
    source_type: str,
    content: str,
    metadata: dict[str, Any],
    file_name: str | None = None,
    file_ext: str | None = None,
    chunk_size: int = 400,
    chunk_overlap: int = 80,
    owner_id: str | None = None,
    content_hash: str | None = None,
    connection: Any | None = None,
    parsed_document:dict|None=None,
    chunk_policy:ChunkPolicy|None=None,
    feature_policy:FeaturePolicy|None=None,
    index_policy:IndexPolicy|None=None,
    retention_policy:RetentionPolicy|None=None,
    revision_intake_key:str|None=None,
) -> dict[str, Any]:
    text = content
    retain_unreadable_pdf=bool(parsed_document and parsed_document.get('format')=='pdf' and parsed_document.get('total_pages',0)>0)
    if not text.strip() and not retain_unreadable_pdf:
        raise HTTPException(status_code=400, detail="empty_content")
    from app.config import get_settings
    if len(text.encode('utf-8'))>get_settings().security.upload_max_bytes:
        raise HTTPException(413,'document_text_too_large')

    if not owner_id or not group_name.strip() or not 100<=chunk_size<=4000 or not 0<=chunk_overlap<=1000 or chunk_overlap>=chunk_size:
        raise HTTPException(422,'invalid_owner_group_or_chunk_overlap')
    digest=content_hash or hashlib.sha256(text.encode('utf-8')).hexdigest()
    profile=(parsed_document or {}).get('parse_profile') or {'schema_version':'legacy_plain_text'}
    profile_key=hashlib.sha256(json.dumps(profile,sort_keys=True,ensure_ascii=False).encode('utf-8')).hexdigest()
    index_policy=index_policy or IndexPolicy()
    retention_policy=retention_policy or RetentionPolicy()
    feature_policy=feature_policy or FeaturePolicy()
    if index_policy.mode=='direct' and feature_policy.dense:raise HTTPException(422,'direct_only_source_cannot_request_dense_encoding')
    if index_policy.mode=='direct' and feature_policy.sparse:raise HTTPException(422,'direct_only_source_cannot_request_sparse_encoding')
    if index_policy.mode=='direct' and feature_policy.english_stemming:raise HTTPException(422,'direct_only_source_cannot_request_stemming')
    if index_policy.mode=='direct' and feature_policy.multivector:raise HTTPException(422,'direct_only_source_cannot_request_multivector')
    semantic_plan=None
    if chunk_policy and chunk_policy.strategy=='semantic':
        from app.semantic_chunking import build_semantic_plan
        from app.channels.models import ChannelError
        try:semantic_plan=await asyncio.to_thread(build_semantic_plan,text,chunk_size,chunk_policy.semantic_similarity)
        except (ValueError,ChannelError):raise HTTPException(422,'semantic_chunking_unavailable_or_incomplete') from None
    plan=await asyncio.to_thread(build_chunk_plan,text,parsed_document,digest+':'+profile_key,
        size=chunk_size,overlap=chunk_overlap,policy=chunk_policy,semantic_plan=semantic_plan)
    try:dense_profile=dense_configuration(get_settings().rag) if feature_policy.dense else None
    except ValueError as error:raise HTTPException(409,str(error)) from None
    sparse_output=None
    if feature_policy.sparse:
        from app.channels.models import ChannelError
        from app.learned_sparse import build_sparse_features
        try:sparse_output=await asyncio.to_thread(build_sparse_features,[text[chunk['start']:chunk['end']] for chunk in plan['children']])
        except (ValueError,ChannelError):raise HTTPException(422,'sparse_encoding_unavailable_or_incomplete') from None
    stem_output=None
    if feature_policy.english_stemming:
        from app.db.retrieval_stemming import english_stem_features
        chunk_text=[text[chunk['start']:chunk['end']] for chunk in plan['children']]
        if connection is not None:stem_output=await english_stem_features(connection,chunk_text)
        else:
            pool=await get_db_pool()
            async with pool.acquire() as conn:stem_output=await english_stem_features(conn,chunk_text)
    multivector_output=None
    if feature_policy.multivector:
        from app.channels.models import ChannelError
        from app.multivector import encode_paired_texts
        try:multivector_output=await asyncio.to_thread(encode_paired_texts,[text[chunk['start']:chunk['end']] for chunk in plan['children']])
        except (ValueError,ChannelError):raise HTTPException(422,'multivector_encoding_unavailable_or_incomplete') from None
    try:features=await asyncio.to_thread(build_feature_plan,text,plan,parsed_document,policy=feature_policy,
        dense_profile=dense_profile,sparse_output=sparse_output,stem_output=stem_output,multivector_output=multivector_output)
    except ValueError as error:
        if str(error).startswith(('sparse_','stemming_','multivector_')):raise HTTPException(422,str(error)) from None
        raise
    source_metadata = {**{key:value for key,value in metadata.items() if key not in {'document_parse','parse_profile','parse_version_id','parsing_reviews','chunk_plan','chunking_profile','feature_plan','feature_profile','dense_profile','index_policy','retention_policy','revision_intake_key'}},
        'content_hash':digest,'source_version':digest,'owner_scope':'private',
        'parse_profile':profile,'parse_version_id':digest+':'+profile_key,'parsing_reviews':[],
        'destination_group':group_name,'chunking_version':CHUNK_VERSION,'chunking_profile':plan['profile'],
        'chunk_plan':plan,'feature_plan':features,'feature_profile':features['profile'],'index_policy':index_policy.model_dump(mode='json'),
        'retention_policy':retention_policy.model_dump(mode='json'),'revision_intake_key':revision_intake_key}
    if parsed_document:source_metadata['document_parse']={key:value for key,value in parsed_document.items() if key!='text'}

    async def intake(conn):
        await lock_owner(conn,owner_id)
        from app.source_lifecycle import validate_policy
        try:await validate_policy(conn,owner_id,retention_policy)
        except ValueError as error:raise HTTPException(422,str(error)) from None
        index_policy_key=hashlib.sha256(json.dumps(source_metadata['index_policy'],sort_keys=True).encode()).hexdigest()
        key=json.dumps([str(owner_id),group_name,digest,chunk_size,chunk_overlap,profile_key,plan['profile_id'],features['profile_id'],index_policy_key,source_metadata['retention_policy'],revision_intake_key],ensure_ascii=False)
        await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))',key)
        existing=await conn.fetchrow('''SELECT s.id FROM document_sources s
            JOIN source_index_heads h ON h.source_id=s.id AND h.owner_id=s.owner_id AND h.mode=$10
            JOIN document_source_lifecycle lc ON lc.source_id=s.id AND lc.owner_id=s.owner_id AND lc.is_current AND lc.state='retained'
            WHERE s.owner_id=$1::uuid AND s.group_name=$2 AND s.metadata->>'content_hash'=$3 AND s.chunk_size=$4 AND s.chunk_overlap=$5
            AND s.metadata->>'parse_version_id'=$6 AND s.metadata->'chunk_plan'->>'profile_id'=$7
            AND s.metadata->'feature_plan'->>'profile_id'=$8 AND s.metadata->'index_policy'=$9::jsonb AND s.status='active'
            AND s.metadata->'retention_policy'=$11::jsonb AND s.metadata->>'revision_intake_key' IS NOT DISTINCT FROM $12::text
            AND lc.reuse_scope=$13 AND lc.task_id IS NOT DISTINCT FROM $14::uuid
            AND lc.valid_from IS NOT DISTINCT FROM $15::timestamptz AND lc.valid_until IS NOT DISTINCT FROM $16::timestamptz
            AND lc.purge_after IS NOT DISTINCT FROM $17::timestamptz''',
            owner_id,group_name,digest,chunk_size,chunk_overlap,source_metadata['parse_version_id'],plan['profile_id'],features['profile_id'],json.dumps(source_metadata['index_policy']),index_policy.mode,json.dumps(source_metadata['retention_policy']),revision_intake_key,
            retention_policy.reuse_scope,str(retention_policy.task_id) if retention_policy.task_id else None,retention_policy.valid_from,retention_policy.valid_until,retention_policy.purge_after)
        if existing:
            return {'source_id':str(existing['id']),'deduplicated':True,'chunk_count':0,'document_ids':[],
                'representation':{'status':'reused_compatible_effective_index_mode','new_embedding_api_calls':0,
                    'semantic_local_encoding_calls':int(semantic_plan is not None),'local_sparse_encoding_calls':int(sparse_output is not None),
                    'local_multivector_encoding_calls':int(multivector_output is not None)},'index':{'mode':index_policy.mode}}
        chunks=[text[chunk['start']:chunk['end']] for chunk in plan['children']]
        embeddings=[None]*len(chunks)
        coverage=[]
        if feature_policy.dense and chunks:
            encoder=Embedder()
            try:
                embeddings=await encoder.embed_batch(chunks)
                validate_vectors(embeddings,len(chunks),get_settings().rag.embed_dimension)
            except (OSError,RuntimeError,ValueError,TypeError,ModuleNotFoundError) as error:
                logger.warning('Dense source encoding failed without source commit: %s',type(error).__name__)
                raise HTTPException(502,'dense_encoding_failed_no_source_committed') from None
            source_metadata['dense_profile']=encoder.last_profile
            features['dense']={'status':'encoded','profile':encoder.last_profile,
                'input_coverage':{'chunks':len(chunks),'truncated_chunks':sum(item.get('truncated') is True for item in encoder.last_batch_coverage),
                    'unknown_token_length_chunks':sum(item.get('truncated') is None for item in encoder.last_batch_coverage)}}
            coverage=encoder.last_batch_coverage
        elif feature_policy.dense:
            features['dense']={'status':'no_text_chunks_no_encoding','profile':None}
        features['effects'].update(embedding_api_calls=1 if features['dense']['status']=='encoded' else 0,
            encoded_chunks=len(chunks) if features['dense']['status']=='encoded' else 0,
            embedding_cost_usd=None,embedding_cost_status='local_encoding_cost_not_measured')
        if len(chunks)!=len(embeddings):raise HTTPException(502,'embedding_count_mismatch_no_source_committed')
        result=await _persist_ingested_source(conn,name=name,group_name=group_name,source_type=source_type,
            file_name=file_name,file_ext=file_ext,text=text,chunk_size=chunk_size,chunk_overlap=chunk_overlap,
            metadata=source_metadata,owner_id=owner_id,chunks=chunks,embeddings=embeddings,dense_coverage=coverage)
        if multivector_output is not None:
            from app.db.retrieval_multivector import persist_document_vectors
            await persist_document_vectors(conn,owner_id,result['source_id'],result['document_ids'],
                source_metadata['parse_version_id'],features['profile_id'],multivector_output)
        return {**result,'parse_version_id':source_metadata['parse_version_id'],'parse_quality':(parsed_document or {}).get('quality'),
            'representation':{'dense_status':features['dense']['status'],'semantic_local_encoding_calls':int(semantic_plan is not None),**features['effects']}}

    if connection is None:
        pool = await get_db_pool()
        async with pool.acquire() as conn, conn.transaction():
            return await intake(conn)
    return await intake(connection)


async def _persist_ingested_source(
    conn: Any,
    *,
    name: str,
    group_name: str,
    source_type: str,
    file_name: str | None,
    file_ext: str | None,
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    metadata: dict[str, Any],
    owner_id: str | None,
    chunks: list[str],
    embeddings: list[list[float]|None],
    dense_coverage:list[dict]|None=None,
) -> dict[str, Any]:
    source = await conn.fetchrow(
        """INSERT INTO document_sources (
               name, group_name, source_type, file_name, file_ext,
               original_text, chunk_size, chunk_overlap, metadata, owner_id
           ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10::uuid)
           RETURNING id""",
        name,
        group_name,
        source_type,
        file_name,
        file_ext,
        text,
        chunk_size,
        chunk_overlap,
        json.dumps(metadata, ensure_ascii=False),
        owner_id,
    )
    source_id = str(source["id"])
    access_epoch=await initialize_lifecycle(conn,source_id,owner_id,RetentionPolicy.model_validate(metadata.get('retention_policy') or {}))

    created_doc_ids: list[str] = []
    indexed=[] if (metadata.get('index_policy') or {}).get('mode')=='direct' else list(zip(chunks,embeddings,strict=True))
    for index,(chunk,embedding) in enumerate(indexed):
        chunk_metadata=source_chunk_metadata(metadata,source_id,index,name=name,group_name=group_name,
            source_type=source_type,file_name=file_name,file_ext=file_ext)
        chunk_metadata['dense_input_coverage']=dense_coverage[index] if dense_coverage else None
        document = await conn.fetchrow(
            """INSERT INTO documents (
                   source_id, source_name, source_type, chunk_index, chunk_count,
                   content, metadata, embedding, owner_id
               ) VALUES ($1::uuid, $2, $3, $4, $5, $6, $7::jsonb, $8::text::vector, $9::uuid)
               RETURNING id""",
            source_id,
            name,
            source_type,
            index,
            len(chunks),
            chunk,
            json.dumps(chunk_metadata, ensure_ascii=False),
            vector_parameter(embedding) if embedding is not None else None,
            owner_id,
        )
        created_doc_ids.append(str(document["id"]))

    try:index_result=await initialize_source_index(conn,source_id,owner_id,IndexPolicy.model_validate(metadata.get('index_policy') or {}))
    except ValueError as error:raise HTTPException(409,str(error)) from None
    except asyncpg.PostgresError as error:
        logger.warning('Source index preparation failed without intake commit: %s',type(error).__name__)
        raise HTTPException(503,'source_index_preparation_failed_no_source_committed') from None
    return {
        "source_id": source_id,
        'access_epoch':access_epoch,
        'index':index_result,
        "chunk_count": len(created_doc_ids),
        'planned_chunk_count':len(chunks),
        "document_ids": created_doc_ids,
    }


@router.get("/sources")
async def list_sources(group_name: str | None = None,summary:bool=False, principal: PrincipalDep = None):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.id,s.name,s.group_name,s.source_type,s.file_name,s.file_ext,s.status,
                   CASE WHEN $2::boolean THEN NULL ELSE s.original_text END AS original_text,
                   s.chunk_size,s.chunk_overlap,
                   CASE WHEN $2::boolean THEN s.metadata - ARRAY['document_parse','chunk_plan','feature_plan']::text[] ELSE s.metadata END AS metadata,
                   s.created_at,s.updated_at,l.state AS lifecycle_state,l.is_current
            FROM document_sources s
            LEFT JOIN document_source_lifecycle l ON l.source_id=s.id AND l.owner_id=s.owner_id
            WHERE s.owner_id=$1::uuid AND ($3::text IS NULL OR s.group_name=$3)
            ORDER BY s.created_at DESC
            """,principal.id,summary,group_name or None,
        )
    return {"items": [{**dict(row),'metadata':_metadata(row['metadata'])} for row in rows]}


@router.get('/sources/{source_id}/parsing')
async def get_source_parsing(source_id:uuid.UUID,include_content:bool=False,principal:PrincipalDep=None):
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        row=await conn.fetchrow('''SELECT s.original_text,s.metadata,COALESCE(l.revision,0) AS lifecycle_revision FROM document_sources s
            LEFT JOIN document_source_lifecycle l ON l.source_id=s.id AND l.owner_id=s.owner_id
            WHERE s.id=$1::uuid AND s.owner_id=$2::uuid''',str(source_id),principal.id)
    if not row:raise HTTPException(404,'source_not_found')
    meta=_metadata(row['metadata'])
    structure=meta.get('document_parse')
    if not isinstance(structure,dict) or not meta.get('parse_version_id') or any(not isinstance(structure.get(key),list) for key in ('blocks','tables','figures')):
        structure=None
    return {'source_id':str(source_id),'parse_version_id':meta.get('parse_version_id'),'lifecycle_revision':row['lifecycle_revision'],'profile':meta.get('parse_profile'),
        'structure':structure,'text':row['original_text'] if include_content else None,
        'reviews':meta.get('parsing_reviews',[]),'status':'retained' if structure else 'legacy_structure_not_retained',
        'semantics':'人工接受仅指该版本结构，不代表事实、表格数值或图像理解已核实。'}


@router.post('/sources/{source_id}/parsing/reviews',status_code=201)
async def record_parse_review(source_id:uuid.UUID,payload:ParseReviewRequest,principal:PrincipalDep=None):
    if not payload.note.strip():raise HTTPException(422,'parse_review_note_required')
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        row=await conn.fetchrow('SELECT metadata FROM document_sources WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE',str(source_id),principal.id)
        if not row:raise HTTPException(404,'source_not_found')
        meta=_metadata(row['metadata'])
        if not meta.get('document_parse') or meta.get('parse_version_id')!=payload.parse_version_id:
            raise HTTPException(409,'parsing_version_not_available')
        reviews=meta.get('parsing_reviews',[])
        parameters=payload.model_dump(mode='json')
        for prior in reviews:
            if prior['request_id']==parameters['request_id']:
                if any(prior[key]!=value for key,value in parameters.items()):raise HTTPException(409,'review_request_id_payload_conflict')
                return prior
        if len(reviews)>=20:raise HTTPException(409,'parsing_review_limit_20')
        record={**parameters,'review_id':str(uuid.uuid4()),'reviewed_by':str(principal.id),'created_at':utc_now_naive().isoformat(),
            'semantics':'structure_review_not_fact_verification','source_text_modified':False}
        await conn.execute("UPDATE document_sources SET metadata=jsonb_set(metadata,'{parsing_reviews}',$3::jsonb),updated_at=$4 WHERE id=$1::uuid AND owner_id=$2::uuid",
            str(source_id),principal.id,json.dumps(reviews+[record],ensure_ascii=False),utc_now_naive())
    return record


@router.get('/sources/{source_id}/processing')
async def document_processing_records(source_id:uuid.UUID,principal:PrincipalDep=None):
    from app.document_processing import list_operations
    return await list_operations(principal.id,source_id)


@router.post('/sources/{source_id}/processing/{operation_id}/cancel')
async def cancel_document_processing(source_id:uuid.UUID,operation_id:uuid.UUID,principal:PrincipalDep=None):
    from app.document_processing import cancel_operation
    return await cancel_operation(principal.id,source_id,operation_id)


@router.post('/sources/{source_id}/processing/vision')
async def parse_document_image(source_id:uuid.UUID,file:DocumentUpload,request_id:uuid.UUID=Form(...),
        parse_version_id:str=Form(...,min_length=1,max_length=260),target_kind:Literal['page','figure']=Form(...),
        page:int|None=Form(default=None,ge=1,le=500),figure_id:str|None=Form(default=None,max_length=100),
        language:Literal['zh','en']=Form(default='zh'),detail:Literal['low','high']=Form(default='low'),principal:PrincipalDep=None):
    from app.config import get_settings
    from app.document_processing import visual_operation
    if (target_kind=='page' and (page is None or figure_id is not None)
            or target_kind=='figure' and (not figure_id or page is not None)):
        raise HTTPException(422,'visual_target_invalid')
    maximum=get_settings().security.upload_max_bytes
    raw=await file.read(maximum+1)
    if len(raw)>maximum:raise HTTPException(413,'upload_too_large')
    selection={'kind':'page','page':page,'detail':detail} if target_kind=='page' else {'kind':'figure','figure_id':figure_id,'detail':detail}
    return await visual_operation(principal.id,source_id,request_id,parse_version_id,raw,selection,language)


@router.post('/sources/{source_id}/processing/text')
async def process_document_text(source_id:uuid.UUID,payload:DocumentTextProcessingRequest,principal:PrincipalDep=None):
    from app.document_processing import text_operation
    secondary={'source_id':str(payload.secondary_source_id),'parse_version':payload.secondary_parse_version,
        'block_id':payload.secondary_block_id} if payload.kind=='semantic_comparison' else None
    return await text_operation(principal.id,source_id,payload.request_id,payload.parse_version_id,payload.kind,
        payload.block_id,secondary,payload.language,payload.chunk_id,payload.chunk_profile_id)


@router.post('/sources/{source_id}/processing/{operation_id}/annotation')
async def change_document_annotation(source_id:uuid.UUID,operation_id:uuid.UUID,payload:DocumentAnnotationRequest,principal:PrincipalDep=None):
    from app.document_processing import change_annotation
    return await change_annotation(principal.id,source_id,operation_id,payload.accepted)


@router.post('/sources/{source_id}/parsing/remove-repeated-margin',status_code=201)
async def remove_repeated_margin(source_id:uuid.UUID,payload:MarginCleaningRequest,principal:PrincipalDep=None):
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        row=await conn.fetchrow('''SELECT original_text,metadata FROM document_sources WHERE id=$1::uuid AND owner_id=$2::uuid''',
            str(source_id),principal.id)
    if not row:raise HTTPException(404,'source_not_found')
    metadata=_metadata(row['metadata'])
    if metadata.get('parse_version_id')!=payload.expected_parse_version:raise HTTPException(409,'parsing_version_not_available')
    candidates=((metadata.get('document_parse') or {}).get('cleaning') or {}).get('repeated_page_margin_candidates') or []
    candidate=next((item for item in candidates if item.get('candidate_id')==payload.candidate_id),None)
    if not candidate:raise HTTPException(422,'cleaning_candidate_not_available')
    text=row['original_text'] or '';occurrences=candidate.get('occurrences') or [];ranges=[]
    for item in occurrences:
        start,end=item.get('start'),item.get('end')
        if type(start) is not int or type(end) is not int or start<0 or end<=start or end>len(text) or text[start:end].strip()!=item.get('text'):
            raise HTTPException(409,'cleaning_candidate_location_changed')
        ranges.append((start,end))
    ranges.sort()
    if len(ranges)<3 or any(ranges[index][1]>ranges[index+1][0] for index in range(len(ranges)-1)):
        raise HTTPException(409,'cleaning_candidate_location_changed')
    for start,end in reversed(ranges):text=text[:start]+text[end:]
    revision=SourceRevision(request_id=payload.request_id,expected_revision=payload.expected_revision,
        expected_parse_version=payload.expected_parse_version,reason='repeated_page_margin:'+payload.candidate_id,
        mode='replace',text=text,format='txt',publish=True)
    return await create_source_revision(source_id,revision,principal)


@router.get('/sources/{source_id}/chunk-plan')
async def get_source_chunk_plan(source_id:uuid.UUID,include_content:bool=False,principal:PrincipalDep=None):
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        row=await conn.fetchrow('SELECT metadata,original_text FROM document_sources WHERE id=$1::uuid AND owner_id=$2::uuid',str(source_id),principal.id)
    if not row:raise HTTPException(404,'source_not_found')
    meta=_metadata(row['metadata'])
    plan=meta.get('chunk_plan');summary=None
    if plan and plan.get('source_summary'):
        from app.evidence_chunks import materialize_summary
        try:summary=materialize_summary(row['original_text'] or '',plan['source_summary'],meta.get('parse_version_id'))
        except ValueError:summary=None
    return {'source_id':str(source_id),'parse_version_id':meta.get('parse_version_id'),'view':meta.get('chunk_plan'),
        'text':row['original_text'] if include_content else None,'summary':summary,'legacy_gap':not bool(meta.get('chunk_plan'))}


@router.get('/sources/{source_id}/features')
async def get_source_features(source_id:uuid.UUID,include_chunks:bool=False,principal:PrincipalDep=None):
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        row=await conn.fetchrow('''SELECT metadata->'feature_plan' AS feature_plan,metadata->>'parse_version_id' AS parse_version
            FROM document_sources WHERE id=$1::uuid AND owner_id=$2::uuid''',str(source_id),principal.id)
    if not row:raise HTTPException(404,'source_not_found')
    view=json.loads(row['feature_plan']) if isinstance(row['feature_plan'],str) else row['feature_plan']
    if view and view.get('source_version')!=row['parse_version']:raise HTTPException(409,'feature_source_version_conflict')
    if view and not include_chunks:
        view={**view,'children':view.get('children',[])[:20],'display_limit':20,'complete_children_included':False}
    return {'source_id':str(source_id),'parse_version_id':row['parse_version'],'view':view,'legacy_gap':not bool(view),
        'effects':{'model_calls':0,'network_requests':0,'index_writes':0,'training':False}}


@router.get('/sources/{source_id}/index')
async def get_source_index(source_id:uuid.UUID,include_adjacency:bool=False,principal:PrincipalDep=None):
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction(isolation='repeatable_read',readonly=True):
        source=await conn.fetchrow('''SELECT status,group_name,metadata->>'parse_version_id' AS source_version,
            metadata->'feature_plan'->>'profile_id' AS feature_profile_id,metadata->'index_policy' AS requested_policy
            FROM document_sources WHERE id=$1::uuid AND owner_id=$2::uuid''',str(source_id),principal.id)
        if not source:raise HTTPException(404,'source_not_found')
        head=await conn.fetchrow('SELECT mode,generation_id,revision FROM source_index_heads WHERE source_id=$1::uuid AND owner_id=$2::uuid',str(source_id),principal.id)
        rows=await conn.fetch('''SELECT manifest,status,created_at FROM retrieval_index_generations
            WHERE source_id=$1::uuid AND owner_id=$2::uuid ORDER BY created_at DESC,id DESC LIMIT 21''',str(source_id),principal.id)
        relations=None
        if include_adjacency:
            plan=await conn.fetchval("SELECT metadata->'chunk_plan' FROM document_sources WHERE id=$1::uuid AND owner_id=$2::uuid",str(source_id),principal.id)
            relations=adjacency_view(_metadata(plan)) if plan else None
    return {'schema_version':INDEX_VERSION,'source_id':str(source_id),'source_status':source['status'],'group_name':source['group_name'],
        'source_version':source['source_version'],'feature_profile_id':source['feature_profile_id'],
        'requested_policy':_metadata(source['requested_policy']) if source['requested_policy'] else None,
        'current':{'mode':head['mode'] if head else 'unpublished_no_head' if source['requested_policy'] else 'legacy_fts_no_generation','generation_id':str(head['generation_id']) if head and head['generation_id'] else None,'revision':head['revision'] if head else 0},
        'generations':[{**_metadata(row['manifest']),'status':row['status'],'created_at':row['created_at'].isoformat()} for row in rows[:20]],
        'has_more_generations':len(rows)>20,'adjacency':relations,'choices':index_choices(),
        'effects':{'model_calls':0,'network_requests':0,'index_writes':0}}


@router.post('/sources/{source_id}/index/actions')
async def source_index_action(source_id:uuid.UUID,payload:IndexAction,principal:PrincipalDep=None):
    pool=await get_db_pool()
    try:
        async with asyncio.timeout(45),pool.acquire() as conn,conn.transaction():
            await conn.execute("SELECT set_config('lock_timeout','3000',true)")
            await conn.execute("SELECT set_config('statement_timeout','30000',true)")
            result=await apply_index_action(conn,source_id,principal.id,payload)
    except ValueError as error:raise HTTPException(404 if str(error)=='source_not_found' else 409,str(error)) from None
    except (asyncpg.PostgresError,TimeoutError) as error:
        logger.warning('Index operation rolled back: %s',type(error).__name__)
        raise HTTPException(503,'index_operation_not_committed_retry_same_request_id') from None
    return result


@router.get('/sources/{source_id}/chunks/{logical_chunk_id}')
async def get_retained_source_chunk(source_id:uuid.UUID,logical_chunk_id:str,context:Literal['matched','parent']='matched',
        group_name:str|None=None,principal:PrincipalDep=None):
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        row=await conn.fetchrow('SELECT metadata,original_text,status,group_name FROM document_sources WHERE id=$1::uuid AND owner_id=$2::uuid',str(source_id),principal.id)
    if not row or (group_name is not None and row['group_name']!=group_name):raise HTTPException(404,'source_not_found')
    meta=_metadata(row['metadata']);plan=meta.get('chunk_plan') or {}
    if plan.get('schema_version')!=CHUNK_VERSION or plan.get('source_version')!=meta.get('parse_version_id'):
        raise HTTPException(409,'retained_chunk_version_not_established')
    chunk=next((item for item in plan.get('children',[]) if item['logical_chunk_id']==logical_chunk_id),None)
    if not chunk:raise HTTPException(404,'stable_chunk_not_found')
    text=row['original_text'] or ''
    if _span(chunk,len(text)) is None:raise HTTPException(409,'unavailable_original_chunk_range')
    if context=='parent':
        if row['status']!='active':raise HTTPException(409,'source_not_active_for_context_expansion')
        parent=next((item for item in plan.get('parents',[]) if item['parent_block_id']==chunk['parent_block_id']),None)
        try:result=parent_window(text,chunk,parent)
        except ValueError as error:raise HTTPException(409,str(error)) from None
    else:result={'text':text[chunk['start']:chunk['end']],'start':chunk['start'],'end':chunk['end'],'status':'matched_original_span'}
    return {'source_id':str(source_id),'parse_version_id':meta.get('parse_version_id'),'chunk':chunk,'context':result,
        'effects':{'model_calls':0,'network_requests':0,'index_writes':0}}


@router.post("/sources")
async def create_source(payload: DocumentSourceCreateRequest, principal: PrincipalDep = None):
    if {'source_sync','source_cdc'} & payload.metadata.keys() or payload.source_type in {'web_sync','cdc'}:
        raise HTTPException(422,'server_managed_intake_metadata')
    content = payload.content or ""
    from app.config import get_settings
    from app.research_documents import read_document
    from app.channels.models import ChannelError
    if len(content.encode('utf-8'))>get_settings().security.upload_max_bytes:raise HTTPException(413,'document_text_too_large')
    try:parsed=await asyncio.to_thread(read_document,content.encode('utf-8'),format=payload.file_ext if payload.file_ext in {'md','json'} else 'txt',
        timeout=get_settings().document_parsing.timeout_seconds,max_chars=get_settings().document_parsing.max_chars)
    except ChannelError as error:raise HTTPException(400,error.category) from None
    result = await _ingest_source(
        name=payload.name,
        group_name=payload.group_name,
        source_type=payload.source_type,
        content=parsed['text'],
        metadata=payload.metadata,
        file_name=payload.file_name,
        file_ext=payload.file_ext,
        chunk_size=payload.chunk_size,
        chunk_overlap=payload.chunk_overlap, owner_id=principal.id,parsed_document=parsed,
        content_hash=hashlib.sha256(content.encode('utf-8')).hexdigest(),
        chunk_policy=payload.chunk_policy,
        feature_policy=payload.feature_policy,
        index_policy=payload.index_policy,
        retention_policy=payload.retention_policy,
    )
    return result


@router.get('/sources/{source_id}/lifecycle')
async def get_source_lifecycle(source_id:uuid.UUID,principal:PrincipalDep=None):
    pool=await get_db_pool()
    try:
        async with pool.acquire() as conn,conn.transaction(isolation='repeatable_read',readonly=True):
            return await lifecycle_view(conn,source_id,principal.id)
    except ValueError as error:raise HTTPException(404 if str(error)=='source_not_found' else 409,str(error)) from None


@router.post('/sources/{source_id}/lifecycle/actions')
async def source_lifecycle_action(source_id:uuid.UUID,payload:LifecycleAction,principal:PrincipalDep=None):
    pool=await get_db_pool()
    try:
        async with asyncio.timeout(45),pool.acquire() as conn,conn.transaction():
            return await apply_lifecycle_action(conn,source_id,principal.id,payload)
    except ValueError as error:raise HTTPException(404 if str(error)=='source_not_found' else 409,str(error)) from None
    except (asyncpg.PostgresError,TimeoutError):raise HTTPException(503,'lifecycle_result_unconfirmed_retry_same_request_id') from None


@router.post('/sources/publish')
async def publish_source_versions(payload:BatchPublication,principal:PrincipalDep=None):
    pool=await get_db_pool()
    try:
        async with asyncio.timeout(45),pool.acquire() as conn,conn.transaction():
            return await publish_batch(conn,principal.id,payload)
    except ValueError as error:raise HTTPException(404 if str(error)=='source_not_found' else 409,str(error)) from None
    except (asyncpg.PostgresError,TimeoutError):raise HTTPException(503,'lifecycle_result_unconfirmed_retry_same_request_id') from None


@router.post('/sources/{source_id}/versions',status_code=201)
async def create_source_revision(source_id:uuid.UUID,payload:SourceRevision,principal:PrincipalDep=None):
    from app.config import get_settings
    from app.research_documents import read_document
    from app.channels.models import ChannelError
    settings=get_settings();pool=await get_db_pool()
    try:
        async with asyncio.timeout(45),pool.acquire() as conn,conn.transaction():
            async def create(text,source,metadata,policy):
                if len(text.encode('utf-8'))>settings.security.upload_max_bytes:raise HTTPException(413,'document_text_too_large')
                parsed=await asyncio.to_thread(read_document,text.encode('utf-8'),format=payload.format,
                    timeout=settings.document_parsing.timeout_seconds,max_chars=settings.document_parsing.max_chars)
                mode=await conn.fetchval('SELECT mode FROM source_index_heads WHERE source_id=$1::uuid AND owner_id=$2::uuid',str(source_id),principal.id)
                index_policy=IndexPolicy(mode=mode or 'lexical',reason='explicit_source_revision_inherit_effective_mode')
                feature_policy=FeaturePolicy.model_validate((metadata.get('feature_profile') or {}).get('policy') or {})
                if index_policy.mode=='direct':feature_policy=feature_policy.model_copy(update={'dense':False,'sparse':False,'english_stemming':False,'multivector':False})
                return await _ingest_source(name=source['name'],group_name=source['group_name'],source_type='revision',content=parsed['text'],
                    metadata={key:value for key,value in metadata.items() if key not in {'source_sync','source_cdc'}},file_ext=payload.format,chunk_size=source['chunk_size'],chunk_overlap=source['chunk_overlap'],
                    owner_id=principal.id,connection=conn,parsed_document=parsed,
                    chunk_policy=ChunkPolicy.model_validate((metadata.get('chunking_profile') or {}).get('policy') or {}),
                    feature_policy=feature_policy,index_policy=index_policy,retention_policy=policy,revision_intake_key=str(payload.request_id))
            return await revise_source(conn,source_id,principal.id,payload,create)
    except ChannelError as error:raise HTTPException(400,error.category) from None
    except ValueError as error:raise HTTPException(404 if str(error)=='source_not_found' else 409,str(error)) from None
    except (asyncpg.PostgresError,TimeoutError):raise HTTPException(503,'lifecycle_result_unconfirmed_retry_same_request_id') from None


@router.put("/sources/{source_id}")
async def update_source(source_id: str, payload: DocumentSourceUpdateRequest, principal: PrincipalDep = None):
    pool = await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await lock_owner(conn,principal.id)
        row = await conn.fetchrow(
            "SELECT * FROM document_sources WHERE id = $1::uuid AND owner_id = $2::uuid FOR UPDATE",
            source_id, principal.id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="source_not_found")

        next_name = payload.name or row["name"]
        next_group = payload.group_name or row["group_name"]
        old_metadata=json.loads(row['metadata']) if isinstance(row['metadata'],str) else row['metadata'] or {}
        next_metadata = dict(payload.metadata) if payload.metadata is not None else dict(old_metadata)
        for field in ('content_hash','source_version','owner_scope','chunking_version','document_parse','parse_profile','parse_version_id','parsing_reviews','chunk_plan','chunking_profile','feature_plan','feature_profile','dense_profile','index_policy','retention_policy','revision_intake_key','source_sync','source_cdc'):
            if field in next_metadata and next_metadata[field]!=old_metadata.get(field):
                raise HTTPException(422,'server_managed_intake_metadata:'+field)
            if field in old_metadata:next_metadata[field]=old_metadata[field]
        next_metadata['destination_group']=next_group
        next_status = payload.status or row["status"]
        lifecycle_state=await conn.fetchval('SELECT state FROM document_source_lifecycle WHERE source_id=$1::uuid AND owner_id=$2::uuid',source_id,principal.id)
        if lifecycle_state=='tombstone' and next_status=='active':raise HTTPException(409,'restore_tombstone_through_lifecycle_action')
        await conn.execute(
            """
            UPDATE document_sources
            SET name = $2, group_name = $3, metadata = $4::jsonb, status = $5, updated_at = $6
            WHERE id = $1::uuid AND owner_id = $7::uuid
            """,
            source_id,
            next_name,
            next_group,
            json.dumps(next_metadata, ensure_ascii=False),
            next_status,
            utc_now_naive(),
            principal.id,
        )

        await conn.execute('''UPDATE documents SET metadata=metadata || jsonb_build_object('group',$2::text,'source_name',$3::text),
            source_name=$3,updated_at=$4 WHERE source_id=$1::uuid AND owner_id=$5::uuid''',
            source_id,next_group,next_name,utc_now_naive(),principal.id)
        await conn.execute('UPDATE document_source_lifecycle SET revision=revision+1,updated_at=NOW() WHERE source_id=$1::uuid AND owner_id=$2::uuid',source_id,principal.id)
        access_epoch=await bump_epoch(conn,principal.id)

    return {"source_id": source_id, "name": next_name, "group_name": next_group,'access_epoch':access_epoch}


@router.delete("/sources/{source_id}")
async def delete_source(source_id: str, principal: PrincipalDep = None):
    pool = await get_db_pool()
    async with asyncio.timeout(45),pool.acquire() as conn,conn.transaction():
        await lock_owner(conn,principal.id)
        state=await conn.fetchrow('SELECT l.revision,l.state FROM document_sources s LEFT JOIN document_source_lifecycle l ON l.source_id=s.id AND l.owner_id=s.owner_id WHERE s.id=$1::uuid AND s.owner_id=$2::uuid FOR UPDATE OF s',source_id,principal.id)
        if not state:raise HTTPException(404,'source_not_found')
        if state['state']=='tombstone':return {'source_id':source_id,'deleted':True,'removal':'tombstone','already_hidden':True}
        result=await apply_lifecycle_action(conn,source_id,principal.id,LifecycleAction(request_id=uuid.uuid4(),action='tombstone',expected_revision=state['revision'] or 0,reason='explicit_source_delete'))
    return {**result,'deleted':True,'removal':'tombstone'}


@router.post("/upload")
async def upload_source(
    file: DocumentUpload,
    name: str = Form(...,min_length=1,max_length=200),
    group_name: str = Form(...,min_length=1,max_length=100),
    source_type: str = Form(default="upload",max_length=20),
    chunk_size: int = Form(default=400,ge=100,le=4000),
    chunk_overlap: int = Form(default=80,ge=0,le=1000),
    allow_ocr:bool=Form(default=False),
    chunk_policy_json:str=Form(default='{}',max_length=40000),
    feature_policy_json:str=Form(default='{}',max_length=4000),
    index_policy_json:str=Form(default='{}',max_length=2000),
    retention_policy_json:str=Form(default='{}',max_length=4000),
    principal: PrincipalDep = None,
):
    if source_type in {'web_sync','cdc'}:raise HTTPException(422,'server_managed_source_type')
    suffix = Path(file.filename or "").suffix.lower().lstrip(".")
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"unsupported_file_type:{suffix}")

    if file.content_type and file.content_type not in TEXT_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="unsupported_content_type")
    from app.config import get_settings
    maximum=get_settings().security.upload_max_bytes
    raw = await file.read(maximum+1)
    if len(raw) > maximum:
        raise HTTPException(status_code=413, detail="upload_too_large")
    if not name.strip() or not group_name.strip() or chunk_overlap>=chunk_size:
        raise HTTPException(422,'invalid_name_group_or_chunk_overlap')
    _validate_file_signature(suffix, raw)
    try:chunk_policy=ChunkPolicy.model_validate_json(chunk_policy_json)
    except ValueError:raise HTTPException(422,'invalid_chunk_policy') from None
    try:feature_policy=FeaturePolicy.model_validate_json(feature_policy_json)
    except ValueError:raise HTTPException(422,'invalid_feature_policy') from None
    try:index_policy=IndexPolicy.model_validate_json(index_policy_json)
    except ValueError:raise HTTPException(422,'invalid_index_policy') from None
    try:retention_policy=RetentionPolicy.model_validate_json(retention_policy_json)
    except ValueError:raise HTTPException(422,'invalid_retention_policy') from None
    digest = hashlib.sha256(raw).hexdigest()
    from app.research_documents import read_document
    from app.channels.models import ChannelError
    try:
        parsed=await asyncio.to_thread(read_document,raw,format=suffix,timeout=get_settings().document_parsing.timeout_seconds,
            max_pages=get_settings().security.upload_max_pages,max_chars=get_settings().document_parsing.max_chars,allow_ocr=allow_ocr and suffix=='pdf')
    except ChannelError as error:raise HTTPException(400,error.category) from None
    return await _ingest_source(name=name,group_name=group_name,source_type=source_type,content=parsed['text'],
        metadata={"uploaded_file":file.filename,'intake_mode':'explicit_upload_event'},
        file_name=file.filename,file_ext=suffix,chunk_size=chunk_size,chunk_overlap=chunk_overlap,
        owner_id=principal.id,content_hash=digest,parsed_document=parsed,chunk_policy=chunk_policy,feature_policy=feature_policy,index_policy=index_policy,retention_policy=retention_policy)


@router.get("/chunks")
async def list_chunks(source_id: str | None = None, group_name: str | None = None, principal: PrincipalDep = None):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        if source_id:
            rows = await conn.fetch(
                """
                SELECT id, source_id, source_name, source_type, chunk_index, chunk_count,
                       content, metadata, created_at, updated_at
                FROM documents
                WHERE source_id = $1::uuid AND owner_id = $2::uuid
                ORDER BY chunk_index ASC
                """,
                source_id, principal.id,
            )
        elif group_name:
            rows = await conn.fetch(
                """
                SELECT d.id, d.source_id, d.source_name, d.source_type, d.chunk_index, d.chunk_count,
                       d.content, d.metadata, d.created_at, d.updated_at
                FROM documents d
                LEFT JOIN document_sources s ON s.id = d.source_id
                WHERE (s.group_name = $1 OR d.metadata->>'group' = $1) AND d.owner_id = $2::uuid
                ORDER BY d.created_at DESC, d.chunk_index ASC
                """,
                group_name, principal.id,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, source_id, source_name, source_type, chunk_index, chunk_count,
                       content, metadata, created_at, updated_at
                FROM documents
                WHERE owner_id = $1::uuid ORDER BY created_at DESC LIMIT 200
                """, principal.id
            )
    return {"items": [{**dict(row),'metadata':_metadata(row['metadata'])} for row in rows]}
