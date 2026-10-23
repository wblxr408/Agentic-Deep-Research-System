"""
Internal document retrieval tool, enabled explicitly for supplementary evidence.

Published lexical postings/BM25, FTS fallback and optional compatible exact dense
retrieval, with rank fusion and reranking.
"""

from __future__ import annotations

import json
import logging
import math
import time
import asyncpg

from typing_extensions import Self

from app.config import get_settings
from app.db.connection import get_text_search_config
from app.db.text_search import regconfig_sql_literal
from app.graph.state import Citation, PlanStep, RAGResult
from app.security.capabilities import CapabilityUnavailable, capability_registry
from app.source_lifecycle import access_clause,current_access

logger = logging.getLogger(__name__)


class RAGAgent:
    """
    Performs lexical retrieval and optional dense retrieval with model identity.

    Pipeline:
    1. Always permit owned lexical retrieval without model initialization
    2. Optionally encode and search compatible dense vectors via pgvector
    3. Published postings BM25 plus separate PostgreSQL full-text/literal fallback
    4. RRF fusion
    5. BGE Reranker for final ranking

    Lifecycle:
    - Use close() or async context manager to properly release resources
    - The agent lazily initializes the DB pool and models on first use
    """

    def __init__(self):
        settings = get_settings()
        self.rag_cfg = settings.rag
        self._db_pool = None
        self._embedder = None
        self._reranker = None
        self.last_channel_status=[]

    async def _get_db_pool(self):
        """Get or create the database connection pool."""
        if self._db_pool is None:
            import asyncpg
            db_settings = get_settings().database
            self._db_pool = await asyncpg.create_pool(
                db_settings.url,
                min_size=2,
                max_size=10,
            )
        return self._db_pool

    async def _get_embedder(self):
        """Lazy-load the embedding model."""
        if self._embedder is None:
            from app.rag.embedder import Embedder
            self._embedder = Embedder()
        return self._embedder

    async def _get_reranker(self):
        """Lazy-load the reranker model."""
        if self._reranker is None:
            from app.rag.reranker import Reranker
            self._reranker = Reranker()
        return self._reranker

    async def close(self) -> None:
        """
        Close all resources held by the agent.

        Call this when done using the agent, or use the async context manager:
            async with RAGAgent() as agent:
                results = await agent.execute_async(steps, query)
        """
        if self._db_pool is not None:
            await self._db_pool.close()
            self._db_pool = None
            logger.info("RAG Agent: database pool closed")

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - ensures cleanup."""
        await self.close()

    async def execute_async(self,plan_steps,user_query,group=None,owner_id=None,
                            context_mode='source_preference',session_id=None,filters=None,timeout_seconds=None,mode='hybrid',fusion=None,query_type=None):
        import asyncio
        try:
            async with asyncio.timeout(timeout_seconds):
                return await self._execute_async(plan_steps,user_query,group=group,owner_id=owner_id,
                    context_mode=context_mode,session_id=session_id,filters=filters,mode=mode,fusion=fusion,query_type=query_type)
        except TimeoutError as error:
            self.last_channel_status.append({'status':'timeout','reason':'retrieval_original_deadline_exhausted'})
            raise RuntimeError('retrieval_original_deadline_exhausted') from error

    async def _execute_async(
        self,
        plan_steps: list[PlanStep],
        user_query: str,
        group: str | None = None,
        owner_id: str | None = None,
        context_mode: str = 'source_preference',
        session_id: str | None = None,
        filters:dict|None=None,
        mode:str='hybrid',
        fusion:dict|None=None,
        query_type:str|None=None,
    ) -> list[RAGResult]:
        """
        Execute RAG retrieval for the given plan steps.
        """
        if not owner_id:
            logger.warning("RAG retrieval rejected because owner scope is missing")
            return []
        if context_mode not in {'source_preference','matched','parent'}:raise ValueError('invalid_retrieval_context_mode')
        from app.retrieval_filters import filter_plan,compile_filter,filter_selectivity,current_filtered_ids,current_document_clause
        filtering=filter_plan(filters)
        business,filter_parameters=compile_filter(filters)
        from app.retrieval_candidates import literal_query
        from app.candidate_fusion import FusionPolicy,fuse_candidates
        fusion_policy=FusionPolicy.model_validate(fusion or {}).model_dump(mode='json')
        for step in plan_steps:literal_query(step.target_query,mode)

        logger.info(f"RAG Agent: processing {len(plan_steps)} steps")

        self.last_channel_status=[]
        try:
            pool = await capability_registry.run("rag_database", self._get_db_pool)
        except CapabilityUnavailable as exc:
            logger.warning("RAG unavailable: %s", exc)
            self.last_channel_status=[{'status':'failed','reason':'retrieval_database_unavailable'}]
            raise RuntimeError('retrieval_database_unavailable') from exc
        results: list[RAGResult] = []

        for step in plan_steps:
            try:
                from app.retrieval_features import dense_configuration,validate_vectors,lexical_view,vector_parameter
                from app.db.retrieval_indexes import scoped_bm25
                from app.retrieval_candidates import literal_query,channel_contracts,literal_candidates,structure_candidates
                query_embedding=None;query_profile=None
                channel_status={'query':step.target_query,'lexical':'requested','dense':'disabled','reranker':'disabled'}
                candidate_limit=fusion_policy['per_route_top_k']
                contracts=channel_contracts(step.target_query,mode=mode,dense_enabled=self.rag_cfg.enable_dense_retrieval,
                    limit=candidate_limit,filter_id=filtering['filter_id'])
                channel_status['channels']=contracts
                async def collect(name,operation):
                    contract=contracts[name]
                    if contract['status']!='requested':return []
                    started=time.monotonic()
                    try:
                        rows=await operation()
                    except (asyncpg.PostgresError,OSError,RuntimeError,ValueError,TypeError) as error:
                        contract.update(status='failed',reason=type(error).__name__,result_count=0)
                        return []
                    else:
                        contract.update(status='completed' if rows else 'empty',result_count=len(rows))
                        return rows
                    finally:contract['duration_ms']=int((time.monotonic()-started)*1000)
                if contracts['dense']['status']=='requested':
                    encoded_at=time.monotonic()
                    embedding_status='failed'
                    try:
                        dense_configuration(self.rag_cfg)
                        embedder=await self._get_embedder()
                        query_embedding=await capability_registry.run('embedding',lambda:embedder.embed(step.target_query))
                        validate_vectors([query_embedding],1,self.rag_cfg.embed_dimension)
                        query_profile=embedder.last_profile
                        channel_status['dense']='encoded_compatible_profiles_only'
                        embedding_status='completed'
                    except (CapabilityUnavailable,OSError,RuntimeError,ValueError,TypeError,ModuleNotFoundError):
                        query_embedding=None;channel_status['dense']='unavailable_lexical_path_retained'
                        contracts['dense'].update(status='failed',reason='encoding_unavailable')
                        logger.warning('Dense retrieval unavailable; retaining independent lexical path')
                    finally:
                        channel_status.setdefault('resource_usage',[]).append({'kind':'query_embedding',
                            'execution':'local_model','status':embedding_status,
                            'attempt_scope':'configuration_and_dispatch_including_cooldown_not_proof_inference_started',
                            'duration_ms':round((time.monotonic()-encoded_at)*1000),
                            'input_characters':len(step.target_query),'input_documents':1,
                            'encoding_profile_id':(query_profile or {}).get('encoding_profile_id'),
                            'provider_charge_usd':None,'cost_basis':'local_compute_not_priced_no_provider_invoice'})
                lexical_query=lexical_view(step.target_query)
                query_terms=list(lexical_query['terms'])[:128]
                channel_status['query_terms_used']=len(query_terms)
                channel_status['query_terms_limited']=lexical_query['truncated'] or len(lexical_query['terms'])>128
                scope_sql=access_clause()

                # Fetch from DB
                async with pool.acquire() as conn:
                    fts_config = await get_text_search_config()
                    fts_config_sql = regconfig_sql_literal(fts_config)
                    channel_status['filter_plan']=filtering
                    channel_status['filter_selectivity']=await filter_selectivity(conn,owner_id,group,session_id,filters)
                    literal=literal_query(step.target_query,mode)
                    literal_rows=await collect('literal',lambda:literal_candidates(conn,literal,owner_id,group,session_id,candidate_limit,filters))
                    structure_rows=await collect('structure',lambda:structure_candidates(conn,literal_rows,owner_id,group,session_id,candidate_limit,filters))

                    vector_rows=[]
                    if query_embedding is not None and query_profile:
                        try:
                            vector_rows = await conn.fetch(f"""WITH scoped AS MATERIALIZED (
                        SELECT d.id,d.embedding,
                            COALESCE((SELECT revision FROM document_source_lifecycle WHERE source_id=d.source_id AND owner_id=d.owner_id),0) AS source_access_revision,
                            h.generation_id AS index_generation_id
                        FROM documents d LEFT JOIN document_sources s ON s.id=d.source_id
                        LEFT JOIN source_index_heads h ON h.source_id=d.source_id AND h.owner_id=d.owner_id
                        WHERE (
                            $2::text IS NULL
                            OR s.group_name=$2::text
                            OR (d.source_id IS NULL AND (d.metadata->>'group'=$2::text OR d.metadata->>'source_group'=$2::text OR d.metadata->>'knowledge_group'=$2::text))
                        )
                        AND d.owner_id=$3::uuid
                        AND (d.source_id IS NULL OR (s.owner_id=$3::uuid AND s.status='active'))
                        AND ((d.source_id IS NULL AND $2::text IS NOT NULL) OR (d.source_id IS NOT NULL AND {scope_sql}))
                        AND {business}
                        AND {current_document_clause()}
                        AND d.embedding IS NOT NULL
                        AND d.metadata->'dense_profile'->>'encoding_profile_id'=$4::text
                        ), nearest AS MATERIALIZED (
                            SELECT id,index_generation_id,source_access_revision,1-(embedding <=> $1::text::vector) AS similarity FROM scoped
                            ORDER BY embedding <=> $1::text::vector,id LIMIT $5
                        ) SELECT d.id,d.content,d.metadata,d.source_id AS document_source_id,nearest.index_generation_id,nearest.source_access_revision,nearest.similarity
                            FROM nearest JOIN documents d ON d.id=nearest.id AND d.owner_id=$3::uuid
                            ORDER BY nearest.similarity DESC,d.id
                    """, vector_parameter(query_embedding), group, owner_id,query_profile.get('encoding_profile_id'),candidate_limit,session_id,*filter_parameters)
                            channel_status['dense']='completed_authorized_materialized_exact_scope'
                            contracts['dense'].update(status='completed' if vector_rows else 'empty',result_count=len(vector_rows))
                        except (asyncpg.PostgresError,ValueError,TypeError) as error:
                            channel_status['dense']='database_vector_unavailable_lexical_path_retained'
                            contracts['dense'].update(status='failed',reason=type(error).__name__,result_count=0)
                            logger.warning('Dense vector query failed; retaining lexical path: %s',type(error).__name__)

                    # Lexical FTS + versioned literal terms, not a BM25 implementation.
                    fts_rows = await collect('fts',lambda:conn.fetch(
                        f"""
                        SELECT d.id, d.content, d.metadata,d.source_id AS document_source_id,h.generation_id AS index_generation_id,
                               COALESCE((SELECT revision FROM document_source_lifecycle WHERE source_id=d.source_id AND owner_id=d.owner_id),0) AS source_access_revision,
                               ts_rank(
                                   to_tsvector({fts_config_sql}, d.content),
                                   plainto_tsquery({fts_config_sql}, $1)
                               ) AS fts_score
                        FROM documents d LEFT JOIN document_sources s ON s.id=d.source_id
                        LEFT JOIN source_index_heads h ON h.source_id=d.source_id AND h.owner_id=d.owner_id
                        WHERE (to_tsvector({fts_config_sql}, d.content) @@ plainto_tsquery({fts_config_sql}, $1)
                            OR d.metadata->'feature_view'->'lexical'->'terms' ?| $4::text[])
                        AND (
                            $2::text IS NULL
                            OR s.group_name=$2::text
                            OR (d.source_id IS NULL AND (d.metadata->>'group'=$2::text OR d.metadata->>'source_group'=$2::text OR d.metadata->>'knowledge_group'=$2::text))
                        )
                        AND d.owner_id=$3::uuid
                        AND (d.source_id IS NULL OR (s.owner_id=$3::uuid AND s.status='active'))
                        AND ((d.source_id IS NULL AND $2::text IS NOT NULL) OR (d.source_id IS NOT NULL AND {scope_sql}))
                        AND {business}
                        AND {current_document_clause()}
                        ORDER BY fts_score DESC,d.id LIMIT $5
                        """,
                        step.target_query,
                        group,
                        owner_id,
                        query_terms,
                        candidate_limit,
                        session_id,
                        *filter_parameters,
                    ))
                    bm25_rows=await collect('bm25',lambda:scoped_bm25(conn,owner_id,group,query_terms,candidate_limit,session_id,filters))
                    channel_status['bm25']=contracts['bm25']['status']

                # Build result lists
                vector_results = {
                    str(r["id"]): {"row": r, "score": float(r["similarity"])}
                    for r in vector_rows
                }
                bm25_results = {
                    str(r["id"]): {"row": r, "score": float(r["bm25_score"])}
                    for r in bm25_rows
                }
                fts_results={str(row['id']):{'row':row,'score':float(row['fts_score'])} for row in fts_rows}
                literal_results={str(row['id']):{'row':row,'score':float(row['literal_score'])} for row in literal_rows}
                structure_results={str(row['id']):{'row':row,'score':float(row['structure_score'])} for row in structure_rows}
                failed=any(item['status']=='failed' for item in contracts.values())
                usable=any(item['status'] in {'completed','empty'} for item in contracts.values())
                channel_status['status']='partial' if failed and usable else 'failed' if failed else 'success'

                # Fuse route memberships without treating score agreement as corroboration.
                channels={'literal':literal_results,'bm25':bm25_results,'fts':fts_results,'dense':vector_results,'structure':structure_results}
                all_rows = {str(r['id']): r for r in vector_rows + fts_rows + bm25_rows + literal_rows + structure_rows}
                fusion_channels={name:[{'id':key,'score':item['score'],'score_direction':'higher',
                    'score_meaning':contracts[name]['score_meaning'],'content':item['row']['content'],
                    'source_key':str(item['row']['document_source_id'] or key)} for key,item in channel.items()]
                    for name,channel in channels.items() if contracts[name]['status']!='skipped'}
                # Metadata-only mode preserves the literal channel's ingestion/ID order.
                actual_fusion={**fusion_policy,**({'method':'borda','diversity':'none','route_minimum':0} if mode=='structured' else {})}
                fused,summary=fuse_candidates(fusion_channels,actual_fusion,query=step.target_query,query_type=query_type,route_status=contracts)
                channel_status['fusion']=summary
                channel_status['fusion']['structured_mode_order_override']=mode=='structured'
                top_ids=[row['id'] for row in fused]
                fusion_rows={row['id']:row for row in fused}
                fusion_scores={row['id']:row['fusion_score'] for row in fused}
                rrf_scores={key:sum(1/(fusion_policy['rrf_k']+list(channel).index(key)+1)
                    for channel in channels.values() if key in channel) for key in all_rows}

                # Revoke stale candidates before their text enters the optional
                # reranker, not just after the reranker has already consumed it.
                async with pool.acquire() as conn:
                    current_ids=await current_filtered_ids(conn,top_ids,owner_id,group,session_id,filters)
                    retained=[]
                    for item in top_ids:
                        if item not in current_ids:continue
                        row=all_rows[item]
                        source_id=row['document_source_id']
                        if source_id and not await current_access(conn,str(source_id),owner_id,session_id,group,row['source_access_revision']):continue
                        retained.append(item)
                    top_ids=retained

                # Prepare for reranker
                rerank_docs = [
                    all_rows[did]["content"]
                    for did in top_ids
                    if did in all_rows
                ]

                channel_status['lexical']='completed' if any(contracts[name]['status'] in {'completed','empty'} for name in ('fts','bm25')) else 'unavailable_or_skipped'
                self.last_channel_status.append(channel_status)
                channel_status['candidate_count']=len(top_ids)
                channel_status['requested_top_k']=self.rag_cfg.rerank_top_n
                channel_status['candidate_limit']=candidate_limit
                channel_status['shortfall']=max(0,self.rag_cfg.rerank_top_n-len(top_ids))
                channel_status['shortfall_action']='retain_scope_exact_prefilter_no_unauthorized_widening'
                if not rerank_docs:
                    continue

                # Rerank
                reranker=None
                if self.rag_cfg.enable_reranker and mode!='structured':
                    try:
                        reranker=await capability_registry.run('reranker',self._get_reranker)
                        channel_status['reranker']='requested'
                    except (CapabilityUnavailable,OSError,RuntimeError,ValueError,ModuleNotFoundError):
                        channel_status['reranker']='unavailable_fusion_order_retained'
                if reranker is not None:
                    reranked_at=time.monotonic()
                    try:
                        reranked = await capability_registry.run(
                            "reranker",
                        lambda query=step.target_query, documents=rerank_docs: reranker.rerank(
                            query=query,
                            documents=documents,
                                top_n=self.rag_cfg.rerank_top_n,
                            ),
                        )
                        if len(reranked)!=len(top_ids) or any(not math.isfinite(value) for value in reranked):raise ValueError('unaligned_or_nonfinite_reranker_scores')
                        channel_status['reranker']='completed_aligned_scores'
                    except (CapabilityUnavailable,OSError,RuntimeError,TypeError,ValueError,ModuleNotFoundError):
                        channel_status['reranker']='unavailable_fusion_order_retained'
                        reranked = [fusion_scores[doc_id] for doc_id in top_ids]
                    finally:
                        channel_status.setdefault('resource_usage',[]).append({'kind':'reranking',
                            'execution':'local_model','status':channel_status['reranker'],
                            'attempt_scope':'dispatch_including_cooldown_not_proof_inference_started',
                            'duration_ms':round((time.monotonic()-reranked_at)*1000),
                            'input_characters':sum(len(text) for text in rerank_docs)+len(step.target_query)*len(rerank_docs),
                            'input_documents':len(rerank_docs),'model':getattr(reranker,'model_name',None),
                            'provider_charge_usd':None,'cost_basis':'local_compute_not_priced_no_provider_invoice'})
                else:
                    reranked = [fusion_scores[doc_id] for doc_id in top_ids]

                # Build final results
                ranked_pairs=list(zip(reranked,top_ids))
                if channel_status['reranker']=='completed_aligned_scores':
                    ranked_pairs.sort(key=lambda pair:(-pair[0],pair[1]))
                ranked_pairs=ranked_pairs[:self.rag_cfg.rerank_top_n]
                for rerank_score, doc_id in ranked_pairs:
                    row = all_rows[doc_id]
                    meta = row["metadata"] or {}
                    if isinstance(meta,str):meta=json.loads(meta)
                    if not isinstance(meta,dict):raise ValueError('invalid_internal_source_metadata')
                    meta=dict(meta);content=row['content']
                    meta['retrieval_channel_status']=dict(channel_status)
                    meta['retrieval_selector']=literal
                    meta['candidate_fusion']={'version':summary['version'],'score':fusion_scores[doc_id],
                        'memberships':fusion_rows[doc_id]['fusion_routes'],'position':top_ids.index(doc_id)+1,
                        'score_semantics':'candidate_relevance_not_evidence_support',
                        'duplicate_groups':[item for item in summary['near_duplicate_groups'] if doc_id in item['candidate_ids']]}
                    meta['retrieval_routes']=[{'channel':name,'rank':list(channel).index(doc_id)+1,
                        'raw_score':channel[doc_id]['score'],'score_meaning':contracts[name]['score_meaning'],
                        'filter_id':filtering['filter_id'],'candidate_limit':candidate_limit}
                        for name,channel in channels.items() if doc_id in channel]
                    if doc_id in structure_results:
                        reference=meta.get('chunk_reference') or {}
                        seed_ids=[]
                        for seed in literal_rows[:5]:
                            seed_meta=seed['metadata'] or {}
                            if isinstance(seed_meta,str):seed_meta=json.loads(seed_meta)
                            if (str(seed['document_source_id'])==str(row['document_source_id'])
                                    and seed_meta.get('parse_version_id')==meta.get('parse_version_id')
                                    and (seed_meta.get('chunk_reference') or {}).get('parent_block_id')==reference.get('parent_block_id')):
                                seed_ids.append(str(seed['id']))
                        meta['structure_path']={'kind':'same_source_parent_adjacency_not_verified_entity_relation',
                            'parent_block_id':reference.get('parent_block_id'),'source_id':str(row['document_source_id']),
                            'parse_version_id':meta.get('parse_version_id'),'seed_limit':5,
                            'seed_chunk_ids':seed_ids}
                    meta['index_generation_id']=str(row['index_generation_id']) if row['index_generation_id'] else None
                    meta['lexical_fts_score']=fts_results.get(doc_id,{}).get('score')
                    meta['retrieval_score_scope']='matched_chunk_before_optional_parent_expansion'
                    if doc_id in bm25_results:
                        bm_row=bm25_results[doc_id]['row']
                        meta['lexical_statistics']={'scope':'current_authorized_published_generations','documents':bm_row['lexical_scope_documents'],
                            'average_length':bm_row['lexical_average_length'],'partial_documents':bm_row['lexical_partial_documents'],
                            'bm25':{'k1':1.2,'b':.75}}
                    actual_source_id=str(row['document_source_id']) if row['document_source_id'] else None
                    meta['source_id']=actual_source_id
                    meta['source_access_revision']=row['source_access_revision']
                    if actual_source_id:
                        async with pool.acquire() as conn:
                            if not await current_access(conn,actual_source_id,owner_id,session_id,group,row['source_access_revision']):continue
                    returned_context_mode=meta.get('context_preference','matched') if context_mode=='source_preference' else context_mode
                    reference=meta.get('chunk_reference') or {}
                    meta['returned_span']={'start':reference.get('start'),'end':reference.get('end'),'status':'matched_chunk'}
                    if returned_context_mode=='parent' and actual_source_id:
                        async with pool.acquire() as conn:
                            source=await conn.fetchrow('''SELECT original_text,metadata->>'parse_version_id' AS parse_version,
                                metadata->'chunk_plan'->>'profile_id' AS chunk_profile,
                                (SELECT item FROM jsonb_array_elements(COALESCE(metadata->'chunk_plan'->'parents','[]'::jsonb)) AS item
                                    WHERE item->>'parent_block_id'=$4::text LIMIT 1) AS parent FROM document_sources
                                WHERE id=$1::uuid AND owner_id=$2::uuid AND status='active'
                                AND ($3::text IS NULL OR group_name=$3::text)''',actual_source_id,owner_id,group,reference.get('parent_block_id'))
                        if source:
                            parent=source['parent'];parent=json.loads(parent) if isinstance(parent,str) else parent
                            original=source['original_text'] or ''
                            try:
                                from app.evidence_chunks import parent_window
                                if not reference or meta.get('parse_version_id')!=source['parse_version'] or source['chunk_profile']!=meta.get('chunk_profile_id'):
                                    raise ValueError('parent_version_not_established')
                                if original[reference['start']:reference['end']]!=content:raise ValueError('matched_text_differs_from_original_version')
                                window=parent_window(original,reference,parent)
                                content=window.pop('text');meta['returned_span']=window
                            except (ValueError,KeyError):meta['parent_context_gap']='stable_parent_or_version_unavailable_original_chunk_retained'
                        else:continue  # Source access changed; do not return its cached text.
                    elif returned_context_mode=='parent':meta['parent_context_gap']='legacy_chunk_has_no_parent_source_reference'

                    if meta.get('summary_excerpt_reference') and actual_source_id:
                        async with pool.acquire() as conn:
                            lead=await conn.fetchval('''SELECT substring(original_text from 1 for 400) FROM document_sources
                                WHERE id=$1::uuid AND owner_id=$2::uuid AND status='active'
                                AND ($3::text IS NULL OR group_name=$3::text) AND metadata->>'parse_version_id'=$4::text''',
                                actual_source_id,owner_id,group,meta.get('parse_version_id'))
                        if lead is None:continue
                        meta['source_lead_excerpt']={'text':lead,'start':0,'end':len(lead),
                            'status':'literal_source_lead_not_generated_summary','source_id':actual_source_id,'parse_version_id':meta.get('parse_version_id')}

                    if actual_source_id:
                        async with pool.acquire() as conn:
                            snapshot=await current_access(conn,actual_source_id,owner_id,session_id,group,row['source_access_revision'],with_snapshot=True)
                            if not snapshot:continue
                            meta['source_access_snapshot']=snapshot
                    citation = Citation(
                        source_url=meta.get("url", ""),
                        source_title=meta.get("title", "Document"),
                        source_type="knowledge_base",
                        extracted_evidence=content[:300],
                        relevance_score=rerank_score,
                        chunk_id=str(row["id"]),
                    )

                    results.append(RAGResult(
                        chunk_id=str(row["id"]),
                        content=content,
                        metadata=meta,
                        vector_score=vector_results.get(doc_id, {}).get("score", 0.0),
                        bm25_score=bm25_results.get(doc_id, {}).get("score", 0.0),
                        rrf_score=rrf_scores.get(doc_id, 0.0),
                        rerank_score=rerank_score,
                        citation=citation,
                    ))

            except (asyncpg.PostgresError,OSError, RuntimeError, TypeError, ValueError, KeyError) as e:
                logger.error(f"RAG step error for '{step.target_query}': {e}")
                channel_status.update(status='failed',reason=type(e).__name__)
                if not any(item is channel_status for item in self.last_channel_status):self.last_channel_status.append(channel_status)
                continue

        # Earlier steps can wait while later steps encode/rerank. Recheck the
        # complete returned set as well as each individual expansion boundary.
        current_results=[]
        async with pool.acquire() as conn:
            permitted=await current_filtered_ids(conn,[item.chunk_id for item in results],owner_id,group,session_id,filters)
            for result in results:
                if result.chunk_id not in permitted:continue
                source_id=result.metadata.get('source_id')
                if source_id and not await current_access(conn,source_id,owner_id,session_id,group,result.metadata.get('source_access_revision')):continue
                current_results.append(result)
        results=current_results
        if not results and any(item.get('status')=='failed' for item in self.last_channel_status):
            raise RuntimeError('internal_retrieval_channels_failed')
        for status in self.last_channel_status:
            returned=[item for item in results if (item.metadata.get('retrieval_channel_status') or {}).get('query')==status.get('query')]
            status['returned_total']=len(returned)
            if 'requested_top_k' in status:status['returned_shortfall']=max(0,status['requested_top_k']-len(returned))
            for item in returned:item.metadata['retrieval_channel_status']=dict(status)
        logger.info(f"RAG Agent: {len(results)} results retrieved")
        return results

    def execute(
        self,
        plan_steps: list[PlanStep],
        user_query: str,
        group: str | None = None,
        owner_id: str | None = None,
        context_mode: str = 'source_preference',
        session_id: str | None = None,
        filters:dict|None=None,
        timeout_seconds:float|None=None,
        mode:str='hybrid',
        fusion:dict|None=None,
        query_type:str|None=None,
    ) -> list[RAGResult]:
        """Synchronous wrapper."""
        import asyncio
        async def invoke():
            try:return await self.execute_async(plan_steps,user_query,group=group,owner_id=owner_id,
                context_mode=context_mode,session_id=session_id,filters=filters,timeout_seconds=timeout_seconds,mode=mode,fusion=fusion,query_type=query_type)
            finally:await self.close()
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(invoke())
        raise RuntimeError('await_execute_async_in_running_event_loop')

    def execute_retrieval(
        self,
        query: str,
        context: str = "",
        group: str | None = None,
        owner_id: str | None = None,
        session_id: str | None = None,
        filters:dict|None=None,
        timeout_seconds:float|None=None,
        mode:str='hybrid',
        fusion:dict|None=None,
        query_type:str|None=None,
    ) -> list[RAGResult]:
        """
        Execute RAG retrieval for a single query (主题 3 工具接口).

        直接执行单个检索查询，供 DAG executor 调用。
        """
        from app.graph.state import PlanStep
        step = PlanStep(target_query=query, node_type="rag")
        return self.execute([step], context or query, group=group, owner_id=owner_id,session_id=session_id,filters=filters,timeout_seconds=timeout_seconds,mode=mode,fusion=fusion,query_type=query_type)

    def execute_for_node(
        self,
        node_query: str,
        context: str = "",
        group: str | None = None,
        owner_id: str | None = None,
    ) -> list[RAGResult]:
        """兼容接口：根据节点 query 执行检索。"""
        return self.execute_retrieval(node_query, context, group=group, owner_id=owner_id)
