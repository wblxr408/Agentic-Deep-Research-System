"""Owned lexical generations and atomic publication in the existing database."""
from __future__ import annotations

import json
import time
from typing import Literal
from uuid import UUID,uuid4

from pydantic import Field,model_validator
from app.research_scope import ScopeRecord
from app.retrieval_features import VERSION as FEATURE_VERSION,TOKENIZER_VERSION,normalize_term
from app.evidence_chunks import identity,VERSION as CHUNK_VERSION

VERSION='adrs-index-generation-v1'
MAX_POSTINGS=200000

RETRIEVAL_SCHEMA_SQL="""
ALTER TABLE documents ADD COLUMN IF NOT EXISTS owner_id UUID;
ALTER TABLE document_sources ADD COLUMN IF NOT EXISTS owner_id UUID;
CREATE TABLE IF NOT EXISTS retrieval_index_generations (
    id UUID PRIMARY KEY,owner_id UUID NOT NULL,source_id UUID NOT NULL REFERENCES document_sources(id) ON DELETE CASCADE,
    source_version TEXT NOT NULL,feature_profile_id TEXT NOT NULL,tokenizer_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ready','retired')),manifest JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),UNIQUE(id,owner_id,source_id)
);
CREATE INDEX IF NOT EXISTS idx_retrieval_generations_owner_source_time ON retrieval_index_generations(owner_id,source_id,created_at DESC);
CREATE TABLE IF NOT EXISTS retrieval_index_documents (
    generation_id UUID NOT NULL,document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    owner_id UUID NOT NULL,source_id UUID NOT NULL,length INTEGER NOT NULL CHECK(length>=0),
    token_coverage TEXT NOT NULL CHECK(token_coverage IN ('complete','partial')),
    PRIMARY KEY(generation_id,document_id),UNIQUE(generation_id,document_id,owner_id),
    FOREIGN KEY(generation_id,owner_id,source_id) REFERENCES retrieval_index_generations(id,owner_id,source_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_retrieval_documents_owner_source ON retrieval_index_documents(owner_id,source_id,generation_id);
CREATE TABLE IF NOT EXISTS retrieval_index_terms (
    generation_id UUID NOT NULL,document_id UUID NOT NULL,owner_id UUID NOT NULL,
    term TEXT NOT NULL CHECK(length(term) BETWEEN 1 AND 128),tf INTEGER NOT NULL CHECK(tf>0),
    PRIMARY KEY(generation_id,document_id,term),
    FOREIGN KEY(generation_id,document_id,owner_id) REFERENCES retrieval_index_documents(generation_id,document_id,owner_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_retrieval_terms_owner_term ON retrieval_index_terms(owner_id,term,generation_id,document_id);
CREATE TABLE IF NOT EXISTS source_index_heads (
    source_id UUID PRIMARY KEY REFERENCES document_sources(id) ON DELETE CASCADE,owner_id UUID NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('direct','lexical')),generation_id UUID,
    revision BIGINT NOT NULL CHECK(revision>0),updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK((mode='direct' AND generation_id IS NULL) OR (mode='lexical' AND generation_id IS NOT NULL)),
    FOREIGN KEY(generation_id,owner_id,source_id) REFERENCES retrieval_index_generations(id,owner_id,source_id)
);
CREATE INDEX IF NOT EXISTS idx_source_index_heads_owner_mode ON source_index_heads(owner_id,mode,source_id);
CREATE TABLE IF NOT EXISTS source_index_operations (
    owner_id UUID NOT NULL,request_id UUID NOT NULL,source_id UUID NOT NULL REFERENCES document_sources(id) ON DELETE CASCADE,
    payload_fingerprint TEXT NOT NULL,result JSONB NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(owner_id,request_id)
);
CREATE INDEX IF NOT EXISTS idx_documents_owner_source_chunk ON documents(owner_id,source_id,chunk_index);
CREATE INDEX IF NOT EXISTS idx_documents_owner_created ON documents(owner_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sources_owner_group_status ON document_sources(owner_id,group_name,status);
CREATE INDEX IF NOT EXISTS idx_sources_owner_parse_version ON document_sources(owner_id,(metadata->>'parse_version_id'));
CREATE INDEX IF NOT EXISTS idx_sources_owner_created ON document_sources(owner_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sources_owner_declared_date ON document_sources(owner_id,(metadata->'feature_plan'->'temporal'->>'source_date'));
CREATE INDEX IF NOT EXISTS idx_documents_literal_terms ON documents USING gin((metadata->'feature_view'->'lexical'->'terms'));
"""


class IndexPolicy(ScopeRecord):
    mode:Literal['direct','lexical']='lexical'
    reason:str=Field(default='explicit_internal_document_intake',max_length=500)


class IndexAction(ScopeRecord):
    request_id:UUID
    action:Literal['rebuild','disable','activate']
    expected_source_version:str|None=Field(default=None,min_length=1,max_length=260)
    expected_feature_profile_id:str|None=Field(default=None,pattern=r'^[0-9a-f]{64}$')
    expected_generation_id:UUID|None=None
    expected_revision:int=Field(default=0,ge=0)
    target_generation_id:UUID|None=None

    @model_validator(mode='after')
    def target_matches(self):
        if (self.action=='activate')!=(self.target_generation_id is not None):raise ValueError('only_activate_requires_target_generation')
        return self


def _object(value):
    result=json.loads(value) if isinstance(value,str) else value
    if not isinstance(result,dict):raise ValueError('index_source_metadata_unavailable')
    return result


async def _source(conn,source_id,owner_id,*,lock=False):
    row=await conn.fetchrow('''SELECT id,metadata,status,original_text,name,group_name,source_type,file_name,file_ext FROM document_sources
        WHERE id=$1::uuid AND owner_id=$2::uuid'''+(' FOR UPDATE' if lock else ''),str(source_id),str(owner_id))
    if row is None:raise ValueError('source_not_found')
    return row,_object(row['metadata'])


async def _head(conn,source_id,owner_id):
    return await conn.fetchrow('SELECT mode,generation_id,revision FROM source_index_heads WHERE source_id=$1::uuid AND owner_id=$2::uuid',str(source_id),str(owner_id))


async def _set_head(conn,source_id,owner_id,mode,generation_id):
    head=await conn.fetchrow('''INSERT INTO source_index_heads(source_id,owner_id,mode,generation_id,revision)
        VALUES($1::uuid,$2::uuid,$3,$4::uuid,1) ON CONFLICT(source_id) DO UPDATE
        SET mode=EXCLUDED.mode,generation_id=EXCLUDED.generation_id,revision=source_index_heads.revision+1,updated_at=NOW()
        WHERE source_index_heads.owner_id=EXCLUDED.owner_id RETURNING mode,generation_id,revision''',
        str(source_id),str(owner_id),mode,str(generation_id) if generation_id else None)
    if head is None:raise ValueError('index_head_owner_conflict')
    from app.source_lifecycle import bump_epoch
    await bump_epoch(conn,owner_id)
    return head


def source_chunk_metadata(metadata,source_id,index,*,name,group_name,source_type,file_name=None,file_ext=None):
    plan=metadata.get('chunk_plan') or {};features=metadata.get('feature_plan') or {}
    if features['children'][index]['logical_chunk_id']!=plan['children'][index]['logical_chunk_id']:
        raise ValueError('source_chunk_feature_order_conflict')
    return {**{key:value for key,value in metadata.items() if key in {'content_hash','source_version','owner_scope','parse_version_id','chunking_version','parse_profile','intake_mode'}},
        **{key:value for key,value in metadata.items() if key in {'url','title','author','language','published_on'} and isinstance(value,str) and len(value)<=500},
        'source_id':str(source_id),'chunk_reference':plan['children'][index],'chunk_profile_id':plan.get('profile_id'),
        'feature_profile_id':features.get('profile_id'),'feature_view':features['children'][index],
        'temporal_view':features.get('temporal'),'dense_profile':metadata.get('dense_profile'),
        'context_preference':((metadata.get('chunking_profile') or {}).get('policy') or {}).get('retrieval_context','matched'),
        'summary_excerpt_reference':plan.get('summary_excerpt'),
        'source_summary_reference':plan.get('source_summary'),
        'document_structure_reference':{'source_id':str(source_id),'parse_version_id':metadata.get('parse_version_id')},
        'group':group_name,'source_name':name,'source_type':source_type,'file_name':file_name,'file_ext':file_ext,
        'chunk_index':index,'chunk_count':len(plan['children'])}


async def publish_source_index(conn,source_id,owner_id):
    """Caller owns one transaction; new rows and head become visible together."""
    started=time.monotonic();source,metadata=await _source(conn,source_id,owner_id,lock=True)
    await conn.execute("SELECT set_config('statement_timeout','30000',true)")
    if source['status']!='active':raise ValueError('source_not_active_for_index_build')
    features=metadata.get('feature_plan') or {}
    if features.get('schema_version')!=FEATURE_VERSION or features.get('source_version')!=metadata.get('parse_version_id') or (features.get('profile') or {}).get('tokenizer_version')!=TOKENIZER_VERSION:
        raise ValueError('retained_feature_version_unavailable_reupload_required')
    plan=metadata.get('chunk_plan') or {}
    if plan.get('schema_version')!=CHUNK_VERSION or plan.get('source_version')!=metadata.get('parse_version_id') or plan.get('profile_id')!=features.get('chunk_profile_id'):
        raise ValueError('index_retained_chunk_version_conflict')
    entries={entry['logical_chunk_id']:entry for entry in features['children']}
    if len(entries)!=len(features['children']) or len(entries)>4000:raise ValueError('index_chunk_identity_or_limit_conflict')
    if {chunk['logical_chunk_id'] for chunk in plan.get('children',[])}!=set(entries) or len(plan.get('children',[]))!=len(entries):raise ValueError('index_chunk_feature_membership_conflict')
    rows=await conn.fetch('SELECT id,content,metadata FROM documents WHERE source_id=$1::uuid AND owner_id=$2::uuid ORDER BY chunk_index',str(source_id),str(owner_id))
    if not rows and entries:
        if ((metadata.get('feature_profile') or {}).get('policy') or {}).get('dense'):
            raise ValueError('missing_dense_representation_requires_explicit_new_intake')
        # A directly retained source has no keyword rows. Explicit publication
        # materializes only its frozen text spans, never a new model embedding.
        records=[]
        for index,chunk in enumerate((metadata.get('chunk_plan') or {}).get('children',[])):
            start,end=chunk['start'],chunk['end']
            if not isinstance(start,int) or isinstance(start,bool) or not isinstance(end,int) or isinstance(end,bool) or not 0<=start<end<=len(source['original_text'] or ''):raise ValueError('index_original_range_unavailable')
            chunk_meta=source_chunk_metadata(metadata,source_id,index,**{key:source[key] for key in ('name','group_name','source_type','file_name','file_ext')})
            records.append((str(uuid4()),str(source_id),source['name'],source['source_type'],index,len(entries),(source['original_text'] or '')[start:end],json.dumps(chunk_meta,ensure_ascii=False),str(owner_id)))
        if records:await conn.executemany('''INSERT INTO documents(id,source_id,source_name,source_type,chunk_index,chunk_count,content,metadata,owner_id)
            VALUES($1::uuid,$2::uuid,$3,$4,$5,$6,$7,$8::jsonb,$9::uuid)''',records)
        rows=await conn.fetch('SELECT id,content,metadata FROM documents WHERE source_id=$1::uuid AND owner_id=$2::uuid ORDER BY chunk_index',str(source_id),str(owner_id))
    if len(rows)!=len(entries):raise ValueError('index_source_chunk_count_conflict')
    generation=uuid4();documents=[];postings=[];truncated=0;omitted=0;seen=set()
    for row in rows:
        chunk_meta=_object(row['metadata']);reference=chunk_meta.get('chunk_reference') or {}
        logical=reference.get('logical_chunk_id');entry=entries.get(logical)
        if logical in seen or not entry or chunk_meta.get('feature_profile_id')!=features['profile_id']:
            raise ValueError('index_document_feature_identity_conflict')
        seen.add(logical)
        start,end=entry['start'],entry['end']
        if not isinstance(start,int) or isinstance(start,bool) or not isinstance(end,int) or isinstance(end,bool) or not 0<=start<end<=len(source['original_text'] or ''):
            raise ValueError('index_original_range_unavailable')
        if (source['original_text'] or '')[start:end]!=row['content'] or reference.get('start')!=start or reference.get('end')!=end:
            raise ValueError('index_original_version_text_conflict')
        lexical=entry.get('lexical')
        if lexical is None:omitted+=1;continue
        terms=lexical.get('terms');length=lexical.get('length')
        if not isinstance(terms,dict) or not isinstance(length,int) or isinstance(length,bool) or not 0<=length<=2048:
            raise ValueError('index_lexical_statistics_invalid')
        if any(not isinstance(term,str) or not 1<=len(term)<=128 or normalize_term(term)!=term or not isinstance(tf,int) or isinstance(tf,bool) or tf<=0 for term,tf in terms.items()) or sum(terms.values())!=length:
            raise ValueError('index_term_or_frequency_invalid')
        if len(postings)+len(terms)>MAX_POSTINGS:omitted+=1;continue
        partial=bool(lexical.get('truncated'));truncated+=partial
        documents.append((str(generation),str(row['id']),str(owner_id),str(source_id),length,'partial' if partial else 'complete'))
        postings.extend((str(generation),str(row['id']),str(owner_id),term,tf) for term,tf in terms.items())
    before=await _head(conn,source_id,owner_id)
    manifest={'schema_version':VERSION,'generation_id':str(generation),'source_version':metadata['parse_version_id'],
        'feature_profile_id':features['profile_id'],'chunk_profile_id':features['chunk_profile_id'],
        'document_count':len(documents),'source_chunk_count':len(rows),'postings':len(postings),
        'omitted_documents':omitted,'truncated_documents':truncated,'token_events':sum(item[4] for item in documents),
        'coverage':'unavailable' if rows and not documents else 'partial' if omitted or truncated else 'complete_retained_lexical_policy',
        'algorithm':'owned_postings_bm25_v1','bm25':{'k1':1.2,'b':.75,'statistics':'current_authorized_published_generations'},
        'tokenizer_version':TOKENIZER_VERSION,'parent_vectors_duplicated':False,
        'vector_access':'filtered_exact_only_no_new_ann','preparation_elapsed_seconds':round(time.monotonic()-started,6),
        'effects':{'scope':'index_construction_only','model_calls':0,'embedding_calls':0,'source_text_modified':False,'old_reports_modified':False}}
    await conn.execute("INSERT INTO retrieval_index_generations(id,owner_id,source_id,source_version,feature_profile_id,tokenizer_version,status,manifest) VALUES($1::uuid,$2::uuid,$3::uuid,$4,$5,$6,'ready',$7::jsonb)",
        str(generation),str(owner_id),str(source_id),metadata['parse_version_id'],features['profile_id'],TOKENIZER_VERSION,json.dumps(manifest,ensure_ascii=False))
    if documents:await conn.executemany('INSERT INTO retrieval_index_documents(generation_id,document_id,owner_id,source_id,length,token_coverage) VALUES($1::uuid,$2::uuid,$3::uuid,$4::uuid,$5,$6)',documents)
    if postings:await conn.executemany('INSERT INTO retrieval_index_terms(generation_id,document_id,owner_id,term,tf) VALUES($1::uuid,$2::uuid,$3::uuid,$4,$5)',postings)
    head=await _set_head(conn,source_id,owner_id,'lexical',generation)
    if before and before['generation_id']:
        await conn.execute("UPDATE retrieval_index_generations SET status='retired' WHERE id=$1::uuid AND owner_id=$2::uuid AND source_id=$3::uuid",str(before['generation_id']),str(owner_id),str(source_id))
    manifest['elapsed_until_head_switch_seconds']=round(time.monotonic()-started,6)
    await conn.execute('UPDATE retrieval_index_generations SET manifest=$2::jsonb WHERE id=$1::uuid',str(generation),json.dumps(manifest,ensure_ascii=False))
    return {**manifest,'mode':head['mode'],'revision':head['revision'],'previous_generation_id':str(before['generation_id']) if before and before['generation_id'] else None}


async def initialize_source_index(conn,source_id,owner_id,policy):
    if policy.mode=='lexical':return await publish_source_index(conn,source_id,owner_id)
    head=await _set_head(conn,source_id,owner_id,'direct',None)
    return {'mode':'direct','generation_id':None,'revision':head['revision'],'effects':{'model_calls':0,'embedding_calls':0}}


async def apply_index_action(conn,source_id,owner_id,request):
    source,metadata=await _source(conn,source_id,owner_id,lock=True)
    fingerprint=identity({'source_id':str(source_id),'request':request.model_dump(mode='json')})
    prior=await conn.fetchrow('SELECT payload_fingerprint,result FROM source_index_operations WHERE owner_id=$1::uuid AND request_id=$2::uuid',str(owner_id),str(request.request_id))
    if prior:
        if prior['payload_fingerprint']!=fingerprint:raise ValueError('index_request_id_payload_conflict')
        return {**_object(prior['result']),'replayed':True}
    features=metadata.get('feature_plan') or {}
    if metadata.get('parse_version_id')!=request.expected_source_version or features.get('profile_id')!=request.expected_feature_profile_id:
        raise ValueError('index_expected_source_or_feature_version_conflict')
    before=await _head(conn,source_id,owner_id)
    if (before['revision'] if before else 0)!=request.expected_revision or (str(before['generation_id']) if before and before['generation_id'] else None)!=(str(request.expected_generation_id) if request.expected_generation_id else None):
        raise ValueError('index_expected_head_revision_conflict')
    if request.action=='rebuild':result=await publish_source_index(conn,source_id,owner_id)
    elif request.action=='activate':
        if source['status']!='active':raise ValueError('source_not_active_for_index_activation')
        target=await conn.fetchrow('''SELECT manifest FROM retrieval_index_generations WHERE id=$1::uuid AND source_id=$2::uuid AND owner_id=$3::uuid AND source_version=$4 AND feature_profile_id=$5 AND tokenizer_version=$6''',
            str(request.target_generation_id),str(source_id),str(owner_id),request.expected_source_version,request.expected_feature_profile_id,TOKENIZER_VERSION)
        if not target:raise ValueError('retained_target_generation_unavailable')
        manifest=_object(target['manifest'])
        materialized=await conn.fetchval('SELECT count(*) FROM retrieval_index_documents WHERE generation_id=$1::uuid AND owner_id=$2::uuid AND source_id=$3::uuid',str(request.target_generation_id),str(owner_id),str(source_id))
        retained_postings=await conn.fetchval('SELECT count(*) FROM retrieval_index_terms WHERE generation_id=$1::uuid AND owner_id=$2::uuid',str(request.target_generation_id),str(owner_id))
        if materialized!=manifest['document_count'] or retained_postings!=manifest['postings']:raise ValueError('retained_target_generation_no_longer_complete')
        head=await _set_head(conn,source_id,owner_id,'lexical',request.target_generation_id)
        await conn.execute("UPDATE retrieval_index_generations SET status=CASE WHEN id=$3::uuid THEN 'ready' ELSE 'retired' END WHERE source_id=$1::uuid AND owner_id=$2::uuid",str(source_id),str(owner_id),str(request.target_generation_id))
        result={**manifest,'mode':head['mode'],'revision':head['revision']}
    else:
        head=await _set_head(conn,source_id,owner_id,'direct',None)
        if before and before['generation_id']:await conn.execute("UPDATE retrieval_index_generations SET status='retired' WHERE id=$1::uuid AND owner_id=$2::uuid",str(before['generation_id']),str(owner_id))
        result={'mode':'direct','generation_id':None,'revision':head['revision'],'effects':{'model_calls':0,'embedding_calls':0,'source_text_modified':False,'old_reports_modified':False}}
    result.update(request_id=str(request.request_id),action=request.action,replayed=False)
    await conn.execute('INSERT INTO source_index_operations(owner_id,request_id,source_id,payload_fingerprint,result) VALUES($1::uuid,$2::uuid,$3::uuid,$4,$5::jsonb)',
        str(owner_id),str(request.request_id),str(source_id),fingerprint,json.dumps(result,ensure_ascii=False))
    return result


def adjacency_view(plan,limit=10000):
    outgoing={};links=0;truncated=False
    def add(left,right,kind):
        nonlocal links,truncated
        if links>=limit:truncated=True;return
        outgoing.setdefault(left,[]).append({'target':right,'kind':kind});links+=1
    for parent in plan.get('parents',[]):
        if parent.get('parent_id'):add(parent['parent_id'],parent['parent_block_id'],'source_structure_parent_child')
    for chunk in plan.get('children',[]):
        add(chunk['parent_block_id'],chunk['logical_chunk_id'],'source_structure_contains_chunk')
        for mention in chunk.get('entity_mentions',[]):add('term:'+mention['entity_id'],chunk['logical_chunk_id'],'dictionary_literal_mention_unconfirmed_identity')
    return {'source_version':plan.get('source_version'),'outgoing':outgoing,'links':links,'limit':limit,'truncated':truncated,
        'semantics':'source_structure_and_mentions_not_confirmed_entity_relationship_graph'}


async def scoped_bm25(conn,owner_id,group,terms,top_k,session_id=None,filters=None):
    """One SQL snapshot supplies both candidates and the authorized N/DF."""
    if not terms:return []
    from app.source_lifecycle import access_clause
    from app.retrieval_filters import compile_filter
    business,parameters=compile_filter(filters)
    scope_sql=access_clause()
    return await conn.fetch(f'''WITH eligible AS MATERIALIZED (
        SELECT x.generation_id,x.document_id,x.length,x.token_coverage FROM retrieval_index_documents x
        JOIN source_index_heads h ON h.source_id=x.source_id AND h.owner_id=x.owner_id AND h.generation_id=x.generation_id AND h.mode='lexical'
        JOIN retrieval_index_generations g ON g.id=x.generation_id AND g.owner_id=x.owner_id AND g.source_id=x.source_id
        JOIN document_sources s ON s.id=x.source_id AND s.owner_id=x.owner_id
        JOIN documents d ON d.id=x.document_id AND d.owner_id=x.owner_id AND d.source_id=x.source_id
        WHERE x.owner_id=$1::uuid AND s.status='active' AND ($2::text IS NULL OR s.group_name=$2::text)
          AND {scope_sql}
          AND {business}
          AND g.status='ready' AND g.tokenizer_version=$4
          AND g.source_version=s.metadata->>'parse_version_id'
          AND g.feature_profile_id=s.metadata->'feature_plan'->>'profile_id'
    ), stats AS (
        SELECT count(*) AS n,avg(length::double precision) AS avgdl,
            count(*) FILTER(WHERE token_coverage='partial') AS partial_documents FROM eligible
    ), df AS (
        SELECT t.term,count(*)::double precision AS df FROM retrieval_index_terms t
        JOIN eligible e ON e.generation_id=t.generation_id AND e.document_id=t.document_id
        WHERE t.owner_id=$1::uuid AND t.term=ANY($3::text[]) GROUP BY t.term
    ), scored AS (
        SELECT t.document_id,sum(ln(1+(stats.n-df.df+0.5)/(df.df+0.5))
            *t.tf*2.2/(t.tf+1.2*(0.25+0.75*e.length/greatest(stats.avgdl,1)))) AS score
        FROM retrieval_index_terms t JOIN eligible e ON e.generation_id=t.generation_id AND e.document_id=t.document_id
        JOIN df ON df.term=t.term CROSS JOIN stats
        WHERE t.owner_id=$1::uuid AND t.term=ANY($3::text[]) GROUP BY t.document_id
    ) SELECT d.id,d.content,d.metadata,d.source_id AS document_source_id,scored.score AS bm25_score,
        COALESCE((SELECT revision FROM document_source_lifecycle WHERE source_id=d.source_id AND owner_id=d.owner_id),0) AS source_access_revision,
        h.generation_id AS index_generation_id,stats.n AS lexical_scope_documents,stats.avgdl AS lexical_average_length,
        stats.partial_documents AS lexical_partial_documents FROM scored
        JOIN documents d ON d.id=scored.document_id AND d.owner_id=$1::uuid
        JOIN source_index_heads h ON h.source_id=d.source_id AND h.owner_id=d.owner_id CROSS JOIN stats
        ORDER BY scored.score DESC,d.id LIMIT $5''',str(owner_id),group,list(terms),TOKENIZER_VERSION,int(top_k),str(session_id) if session_id else None,*parameters)


def index_choices():
    return {'exact':{'selected':'UUID_primary_BTree_scoped_source_version_lookup'},
        'lexical':{'selected':'versioned_weighted_postings_and_FTS_GIN','learned_sparse':'not_selected_no_frozen_sparse_model'},
        'metadata_time':{'selected':'JSONB_GIN_and_owner_source_group_status_version_time_BTree','bitmap_roaring':'not_selected_no_measured_need'},
        'relations':{'selected':'bounded_source_structure_adjacency','confirmed_entity_graph':False},
        'vector':{'selected':'authorized_compatible_materialized_scope_exact_distance','existing_ann_indexes_removed':False,
            'not_selected':['HNSW','Vamana','IVF_Flat','IVF_PQ','PQ','OPQ','SQ','DiskANN','token_multi_vector_late_interaction'],
            'reconsider_when':'measured_scale_latency_and_recall_cost_benefit_with_owner_filtering_and_rollback_evidence'},
        'training':'not_required_for_selected_lexical_or_exact_distance','default_ann_build':False}
