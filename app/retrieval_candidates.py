"""Small source-bound candidate channels; no autonomous reasoning or new store."""
from __future__ import annotations

import json
import re
from uuid import UUID

from app.retrieval_filters import compile_filter,current_document_clause
from app.source_lifecycle import access_clause

VERSION='adrs-retrieval-candidates-v1'


def literal_query(query,mode='hybrid'):
    if mode not in {'hybrid','structured'}:raise ValueError('unsupported_internal_retrieval_mode')
    if mode=='structured':return {'kind':'structured','value':None,'score_meaning':'metadata_order_not_relevance'}
    match=re.fullmatch(r'(chunk|source):\s*([0-9a-f-]{36})',query.strip(),re.I)
    if match:return {'kind':match[1].lower(),'value':str(UUID(match[2])),'score_meaning':'binary_identifier_match'}
    if match:=re.fullmatch(r'entity:([^\r\n]{1,160})',query.strip(),re.I):
        if not match[1].strip():raise ValueError('explicit_entity_selector_is_blank')
        return {'kind':'entity','value':match[1].strip(),'score_meaning':'dictionary_literal_mention_unconfirmed_identity'}
    if match:=re.fullmatch(r'phrase:([^\r\n]{1,500})|“([^”\r\n]{1,500})”|"([^"\r\n]{1,500})"',query.strip(),re.I):
        value=next(item for item in match.groups() if item is not None).strip()
        if not value:raise ValueError('explicit_phrase_selector_is_blank')
        return {'kind':'phrase','value':value,'score_meaning':'binary_case_insensitive_literal_phrase'}
    return {'kind':'none','value':None,'score_meaning':None}


def channel_contracts(query,*,mode,dense_enabled,limit,filter_id):
    literal=literal_query(query,mode)
    result={name:{'status':'requested','candidate_limit':limit,'filter_id':filter_id,
        'filter_support':'trusted_current_scope_AND_business_pre_filter',
        'deadline':'shared_original_retrieval_timeout','duration_ms':None,
        'candidate_identity':'owned_document_chunk_uuid'} for name in ('literal','bm25','fts','dense','structure')}
    result['literal'].update(representation=literal['kind'],score_meaning=literal['score_meaning'])
    result['bm25'].update(representation='versioned_literal_terms',score_meaning='scoped_BM25_higher_is_more_relevant')
    result['fts'].update(representation='postgres_plain_tsquery_plus_literal_terms',score_meaning='ts_rank_higher_is_more_relevant')
    result['dense'].update(representation='configured_compatible_query_embedding',score_meaning='one_minus_cosine_distance')
    result['structure'].update(representation='same_source_parent_adjacency',score_meaning='shared_parent_context_not_factual_relation')
    if literal['kind']=='none':result['literal'].update(status='skipped',reason='no_explicit_literal_selector')
    if literal['kind'] not in {'entity','chunk'}:result['structure'].update(status='skipped',reason='no_explicit_graph_seed')
    if not dense_enabled:result['dense'].update(status='skipped',reason='dense_not_enabled')
    if mode=='structured':
        for name in ('bm25','fts','dense','structure'):result[name].update(status='skipped',reason='explicit_metadata_only_mode')
    for name,reason in {'learned_sparse':'no_configured_sparse_model_or_index','late_interaction':'no_token_embedding_index',
        'behavioral':'no_authorized_behavior_dataset','multimodal':'no_cross_modal_query_encoder_and_index',
        'community_summary':'no_evidenced_need_or_versioned_GraphRAG_summary_index'}.items():
        result[name]={'status':'skipped','reason':reason}
    return result


async def literal_candidates(conn,query,owner_id,group,session_id,limit,filters):
    business,parameters=compile_filter(filters,start_parameter=6)
    predicates={
        'chunk':"d.id::text=$4::jsonb->>'value'",
        'source':"d.source_id::text=$4::jsonb->>'value'",
        'phrase':"strpos(lower(d.content),lower($4::jsonb->>'value'))>0",
        'structured':"$4::jsonb->>'kind'='structured'",
        'entity':"""EXISTS(SELECT 1 FROM jsonb_array_elements(CASE WHEN
            jsonb_typeof(d.metadata->'chunk_reference'->'entity_mentions')='array'
            THEN d.metadata->'chunk_reference'->'entity_mentions' ELSE '[]'::jsonb END) mention
            WHERE mention->>'entity_id'=$4::jsonb->>'value')""",
    }
    if query['kind'] not in predicates:return []
    return await conn.fetch(f'''SELECT d.id,d.content,d.metadata,d.source_id AS document_source_id,
        COALESCE((SELECT revision FROM document_source_lifecycle WHERE source_id=d.source_id AND owner_id=d.owner_id),0) AS source_access_revision,
        h.generation_id AS index_generation_id,1.0::double precision AS literal_score
        FROM documents d LEFT JOIN document_sources s ON s.id=d.source_id
        LEFT JOIN source_index_heads h ON h.source_id=d.source_id AND h.owner_id=d.owner_id
        WHERE d.owner_id=$1::uuid
          AND ($2::text IS NULL OR s.group_name=$2::text OR (d.source_id IS NULL AND
            (d.metadata->>'group'=$2::text OR d.metadata->>'source_group'=$2::text OR d.metadata->>'knowledge_group'=$2::text)))
          AND (d.source_id IS NULL OR (s.owner_id=$1::uuid AND s.status='active'))
          AND ((d.source_id IS NULL AND $2::text IS NOT NULL) OR (d.source_id IS NOT NULL AND {access_clause('s','$3','$2')}))
          AND {current_document_clause()} AND {business} AND ({predicates[query['kind']]})
        ORDER BY COALESCE(s.created_at,d.created_at) DESC,d.id LIMIT $5''',str(owner_id),group,
        str(session_id) if session_id else None,json.dumps(query,ensure_ascii=False),int(limit),*parameters)


async def structure_candidates(conn,seeds,owner_id,group,session_id,limit,filters):
    """One bounded sibling expansion; identity/cooperation are not inferred."""
    if not seeds:return []
    business,parameters=compile_filter(filters,start_parameter=6)
    return await conn.fetch(f'''SELECT DISTINCT d.id,d.content,d.metadata,d.source_id AS document_source_id,
        COALESCE((SELECT revision FROM document_source_lifecycle WHERE source_id=d.source_id AND owner_id=d.owner_id),0) AS source_access_revision,
        h.generation_id AS index_generation_id,1.0::double precision AS structure_score
        FROM documents d LEFT JOIN document_sources s ON s.id=d.source_id
        LEFT JOIN source_index_heads h ON h.source_id=d.source_id AND h.owner_id=d.owner_id
        WHERE d.owner_id=$1::uuid AND ($2::text IS NULL OR s.group_name=$2::text)
          AND d.source_id IS NOT NULL AND s.owner_id=$1::uuid AND s.status='active'
          AND {access_clause('s','$3','$2')} AND {current_document_clause()} AND {business}
          AND EXISTS(SELECT 1 FROM documents seed WHERE seed.id=ANY($4::uuid[]) AND seed.owner_id=d.owner_id
            AND seed.source_id=d.source_id AND seed.id<>d.id
            AND seed.metadata->>'parse_version_id'=d.metadata->>'parse_version_id'
            AND EXISTS(SELECT 1 FROM retrieval_index_documents seed_publication
                WHERE seed_publication.document_id=seed.id AND seed_publication.owner_id=seed.owner_id
                  AND seed_publication.generation_id=h.generation_id AND seed_publication.source_id=seed.source_id)
            AND seed.metadata->'chunk_reference'->>'parent_block_id'=d.metadata->'chunk_reference'->>'parent_block_id')
        ORDER BY d.id LIMIT $5''',str(owner_id),group,str(session_id) if session_id else None,
        [UUID(str(row['id'])) for row in seeds[:5]],int(limit),*parameters)
