"""Authorized, versioned auxiliary posting candidates for internal research."""
from __future__ import annotations

import json
import time
from uuid import UUID

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


async def has_paired_index(conn,owner_id,group,session_id,filters,pair_id):
    business,parameters=compile_filter(filters,start_parameter=5)
    return await conn.fetchval(f'''SELECT EXISTS(SELECT 1 FROM retrieval_model_features m
        JOIN documents d ON d.id=m.document_id AND d.owner_id=m.owner_id AND d.source_id=m.source_id
        JOIN document_sources s ON s.id=m.source_id AND s.owner_id=m.owner_id
        JOIN source_index_heads h ON h.source_id=m.source_id AND h.owner_id=m.owner_id AND h.mode='lexical'
        JOIN retrieval_index_generations g ON g.id=h.generation_id AND g.owner_id=m.owner_id AND g.source_id=m.source_id AND g.status='ready'
        WHERE m.owner_id=$1::uuid AND ($2::text IS NULL OR s.group_name=$2::text) AND s.status='active' AND m.pair_id=$4::text
        AND m.source_version=g.source_version AND m.feature_profile_id=g.feature_profile_id
        AND g.manifest->'multivector'->>'status'='published' AND g.manifest->'multivector'->>'pair_id'=m.pair_id
        AND {access_clause('s','$3','$2')} AND {current_document_clause()} AND {business})''',
        str(owner_id),group,str(session_id) if session_id else None,pair_id,*parameters)


async def paired_candidates(conn,owner_id,group,session_id,limit,filters,encoded,deadline=None):
    """Exact pooled-vector scores over a bounded, already-authorized cohort."""
    import asyncio
    business,parameters=compile_filter(filters,start_parameter=8)
    rows=await conn.fetch(f'''SELECT d.id,d.content,d.metadata,d.source_id AS document_source_id,h.generation_id AS index_generation_id,
        COALESCE((SELECT revision FROM document_source_lifecycle WHERE source_id=d.source_id AND owner_id=d.owner_id),0) AS source_access_revision,
        m.pooled_vector,m.pooled_dimension FROM retrieval_model_features m
        JOIN documents d ON d.id=m.document_id AND d.owner_id=m.owner_id AND d.source_id=m.source_id
        JOIN document_sources s ON s.id=m.source_id AND s.owner_id=m.owner_id
        JOIN source_index_heads h ON h.source_id=m.source_id AND h.owner_id=m.owner_id AND h.mode='lexical'
        JOIN retrieval_index_generations g ON g.id=h.generation_id AND g.owner_id=m.owner_id AND g.source_id=m.source_id AND g.status='ready'
        WHERE m.owner_id=$1::uuid AND ($2::text IS NULL OR s.group_name=$2::text) AND s.status='active'
          AND m.pair_id=$4::text AND m.pooled_dimension=$5::integer AND m.source_version=g.source_version AND m.feature_profile_id=g.feature_profile_id
          AND g.manifest->'multivector'->>'status'='published' AND g.manifest->'multivector'->>'pair_id'=m.pair_id
          AND s.metadata->'feature_plan'->'profile'->'multivector_configuration'->'observed'->>'sentence_transformers_version'=$7::jsonb->>'sentence_transformers_version'
          AND s.metadata->'feature_plan'->'profile'->'multivector_configuration'->'observed'->>'transformers_version'=$7::jsonb->>'transformers_version'
          AND s.metadata->'feature_plan'->'profile'->'multivector_configuration'->'observed'->>'torch_version'=$7::jsonb->>'torch_version'
          AND s.metadata->'feature_plan'->'profile'->'multivector_configuration'->'observed'->>'normalization'=$7::jsonb->>'normalization'
          AND {access_clause('s','$3','$2')} AND {current_document_clause()} AND {business}
        ORDER BY d.id LIMIT $6''',str(owner_id),group,str(session_id) if session_id else None,encoded['pair']['pair_id'],
        encoded['observed']['pooled_dimension'],2001,json.dumps(encoded['observed']),*parameters)
    scanned=min(len(rows),2000);truncated=len(rows)>2000
    def score():
        import numpy as np
        query=np.frombuffer(encoded['vectors'][0]['pooled_bytes'],dtype='<f4')
        found=[];evaluated=0
        for row in rows[:scanned]:
            if deadline is not None and time.monotonic()>=deadline:break
            vector=np.frombuffer(row['pooled_vector'],dtype='<f4')
            if len(vector)!=len(query):continue
            value=float(np.dot(query,vector))
            evaluated+=1
            if not np.isfinite(value):continue
            item={key:row[key] for key in ('id','content','metadata','document_source_id','index_generation_id','source_access_revision')}
            item['auxiliary_score']=value;found.append(item)
        return sorted(found,key=lambda item:(-item['auxiliary_score'],str(item['id'])))[:limit],evaluated
    found,evaluated=await asyncio.to_thread(score)
    return found,{'scanned':scanned,'scored':evaluated,'scan_limit':2000,'scope_truncated':truncated or evaluated<scanned}


async def late_candidates(conn,owner_id,group,session_id,filters,encoded,seeds,limit,deadline=None):
    """Bounded exact MaxSim on the actually encoded source tokens of pooled seeds."""
    import asyncio
    if not seeds:return [],{'seed_count':0,'scored':0,'coverage':'no_pooled_seeds'}
    query_vector=encoded['vectors'][0];valid=[i for i,item in enumerate(query_vector['locations']) if item is not None]
    if not valid or len(valid)>512:raise ValueError('late_query_token_limit')
    business,parameters=compile_filter(filters,start_parameter=7)
    seed_ids=[UUID(str(item['id'])) for item in seeds[:min(30,len(seeds))]]
    rows=await conn.fetch(f'''WITH eligible AS MATERIALIZED (
        SELECT d.id,d.content,d.metadata,d.source_id AS document_source_id,h.generation_id AS index_generation_id,
          COALESCE((SELECT revision FROM document_source_lifecycle WHERE source_id=d.source_id AND owner_id=d.owner_id),0) AS source_access_revision,
          m.token_vectors,m.token_locations,m.token_dimension,m.token_count,array_position($4::uuid[],d.id) AS seed_order
        FROM retrieval_model_features m JOIN documents d ON d.id=m.document_id AND d.owner_id=m.owner_id AND d.source_id=m.source_id
        JOIN document_sources s ON s.id=m.source_id AND s.owner_id=m.owner_id
        JOIN source_index_heads h ON h.source_id=m.source_id AND h.owner_id=m.owner_id AND h.mode='lexical'
        JOIN retrieval_index_generations g ON g.id=h.generation_id AND g.owner_id=m.owner_id AND g.source_id=m.source_id AND g.status='ready'
        WHERE m.owner_id=$1::uuid AND ($2::text IS NULL OR s.group_name=$2::text) AND s.status='active' AND d.id=ANY($4::uuid[])
          AND m.token_dimension=$5::integer AND m.pair_id=$6::text AND m.source_version=g.source_version AND m.feature_profile_id=g.feature_profile_id
          AND g.manifest->'multivector'->>'status'='published' AND g.manifest->'multivector'->>'pair_id'=m.pair_id
          AND {access_clause('s','$3','$2')} AND {current_document_clause()} AND {business}), sized AS (
        SELECT *,SUM(octet_length(token_vectors)) OVER(ORDER BY seed_order,id) AS cumulative_bytes FROM eligible)
        SELECT * FROM sized WHERE cumulative_bytes<=16777216 ORDER BY seed_order,id LIMIT 30''',
        str(owner_id),group,str(session_id) if session_id else None,seed_ids,encoded['observed']['token_dimension'],
        encoded['pair']['pair_id'],*parameters)
    def score():
        import numpy as np
        dimension=encoded['observed']['token_dimension'];query=np.frombuffer(query_vector['token_bytes'],dtype='<f4').reshape(query_vector['input_tokens'],dimension)[valid]
        output=[];operations=0
        for row in rows:
            if deadline is not None and time.monotonic()>=deadline:break
            locations=json.loads(row['token_locations']) if isinstance(row['token_locations'],str) else row['token_locations']
            indices=[i for i,item in enumerate(locations) if item is not None]
            if not indices:continue
            cost=len(valid)*len(indices)*dimension
            if operations+cost>120_000_000:break
            source=np.frombuffer(row['token_vectors'],dtype='<f4').reshape(row['token_count'],dimension)[indices]
            value=float((query@source.T).max(axis=1).sum());operations+=cost
            if not np.isfinite(value):continue
            item={key:row[key] for key in ('id','content','metadata','document_source_id','index_generation_id','source_access_revision')}
            item['auxiliary_score']=value;output.append(item)
        output.sort(key=lambda item:(-item['auxiliary_score'],str(item['id'])))
        return output[:limit],{'seed_count':len(seed_ids),'available_matrices':len(rows),'scored':len(output),
            'coverage':'all_selected_seeds' if len(output)==len(seed_ids) else 'bounded_or_changed_seed_subset',
            'max_vector_bytes':16777216,'max_scalar_products':120_000_000,'scalar_products':operations}
    return await asyncio.to_thread(score)
