"""Authorized, versioned auxiliary posting candidates for internal research."""
from __future__ import annotations

import json

from app.evidence_chunks import identity
from app.retrieval_filters import compile_filter,current_document_clause
from app.source_lifecycle import access_clause


async def has_sparse_index(conn,owner_id,group,session_id,filters,model,revision):
    business,parameters=compile_filter(filters,start_parameter=6)
    return await conn.fetchval(f'''SELECT EXISTS(SELECT 1 FROM retrieval_sparse_postings p
        JOIN documents d ON d.id=p.document_id AND d.owner_id=p.owner_id AND d.source_id=p.source_id
        JOIN document_sources s ON s.id=p.source_id AND s.owner_id=p.owner_id
        JOIN source_index_heads h ON h.source_id=p.source_id AND h.owner_id=p.owner_id AND h.mode='lexical' AND h.generation_id=p.generation_id
        JOIN retrieval_index_generations g ON g.id=p.generation_id AND g.owner_id=p.owner_id AND g.source_id=p.source_id AND g.status='ready'
        WHERE p.owner_id=$1::uuid AND ($2::text IS NULL OR s.group_name=$2::text) AND s.status='active'
          AND s.metadata->'feature_plan'->'profile'->'sparse_configuration'->>'model'=$4::text
          AND s.metadata->'feature_plan'->'profile'->'sparse_configuration'->>'revision'=$5::text
          AND g.source_version=s.metadata->>'parse_version_id' AND g.feature_profile_id=s.metadata->'feature_plan'->>'profile_id'
          AND {access_clause('s','$3','$2')} AND {current_document_clause()} AND {business})''',
        str(owner_id),group,str(session_id) if session_id else None,model,revision,*parameters)


async def sparse_candidates(conn,owner_id,group,session_id,limit,filters,encoded):
    business,parameters=compile_filter(filters,start_parameter=7)
    profile=encoded['profile'];vector=encoded['vectors'][0]
    query={'vocabulary_id':profile['tokenizer_vocabulary_id'],'terms':vector['terms']}
    if not query['terms']:return []
    return await conn.fetch(f'''WITH terms AS MATERIALIZED (
        SELECT (term->>'token_id')::integer AS token_id,(term->>'weight')::double precision AS weight
        FROM jsonb_array_elements($4::jsonb->'terms') term), scored AS MATERIALIZED (
        SELECT p.document_id,p.generation_id,SUM(p.weight::double precision*terms.weight) AS score
        FROM retrieval_sparse_postings p JOIN terms ON terms.token_id=p.token_id
        JOIN documents d ON d.id=p.document_id AND d.owner_id=p.owner_id AND d.source_id=p.source_id
        JOIN document_sources s ON s.id=p.source_id AND s.owner_id=p.owner_id
        JOIN source_index_heads h ON h.source_id=p.source_id AND h.owner_id=p.owner_id AND h.mode='lexical' AND h.generation_id=p.generation_id
        JOIN retrieval_index_generations g ON g.id=p.generation_id AND g.owner_id=p.owner_id AND g.source_id=p.source_id AND g.status='ready'
        WHERE p.owner_id=$1::uuid AND ($2::text IS NULL OR s.group_name=$2::text) AND s.status='active'
          AND p.model_profile_id=$5::text AND p.vocabulary_id=$4::jsonb->>'vocabulary_id'
          AND g.source_version=s.metadata->>'parse_version_id' AND g.feature_profile_id=s.metadata->'feature_plan'->>'profile_id'
          AND {access_clause('s','$3','$2')} AND {current_document_clause()} AND {business}
        GROUP BY p.document_id,p.generation_id ORDER BY score DESC,p.document_id LIMIT $6)
        SELECT d.id,d.content,d.metadata,d.source_id AS document_source_id,scored.generation_id AS index_generation_id,
            COALESCE((SELECT revision FROM document_source_lifecycle WHERE source_id=d.source_id AND owner_id=d.owner_id),0) AS source_access_revision,
            scored.score AS auxiliary_score FROM scored JOIN documents d ON d.id=scored.document_id AND d.owner_id=$1::uuid
        ORDER BY scored.score DESC,d.id''',str(owner_id),group,str(session_id) if session_id else None,
        json.dumps(query,ensure_ascii=False),identity(profile),int(limit),*parameters)


async def stem_candidates(conn,owner_id,group,session_id,limit,filters,encoded):
    business,parameters=compile_filter(filters,start_parameter=7)
    lexemes=encoded['vectors'][0]['lexemes']
    if not lexemes:return []
    return await conn.fetch(f'''WITH scored AS MATERIALIZED (
        SELECT p.document_id,p.generation_id,count(*)::double precision AS score
        FROM retrieval_english_lexemes p JOIN documents d ON d.id=p.document_id AND d.owner_id=p.owner_id AND d.source_id=p.source_id
        JOIN document_sources s ON s.id=p.source_id AND s.owner_id=p.owner_id
        JOIN source_index_heads h ON h.source_id=p.source_id AND h.owner_id=p.owner_id AND h.mode='lexical' AND h.generation_id=p.generation_id
        JOIN retrieval_index_generations g ON g.id=p.generation_id AND g.owner_id=p.owner_id AND g.source_id=p.source_id AND g.status='ready'
        WHERE p.owner_id=$1::uuid AND ($2::text IS NULL OR s.group_name=$2::text) AND s.status='active'
          AND p.lexeme=ANY($4::text[]) AND p.configuration_id=$5::text
          AND g.source_version=s.metadata->>'parse_version_id' AND g.feature_profile_id=s.metadata->'feature_plan'->>'profile_id'
          AND {access_clause('s','$3','$2')} AND {current_document_clause()} AND {business}
        GROUP BY p.document_id,p.generation_id ORDER BY score DESC,p.document_id LIMIT $6)
        SELECT d.id,d.content,d.metadata,d.source_id AS document_source_id,scored.generation_id AS index_generation_id,
            COALESCE((SELECT revision FROM document_source_lifecycle WHERE source_id=d.source_id AND owner_id=d.owner_id),0) AS source_access_revision,
            scored.score AS auxiliary_score FROM scored JOIN documents d ON d.id=scored.document_id AND d.owner_id=$1::uuid
        ORDER BY scored.score DESC,d.id''',str(owner_id),group,str(session_id) if session_id else None,
        lexemes,identity(encoded['profile']),int(limit),*parameters)
