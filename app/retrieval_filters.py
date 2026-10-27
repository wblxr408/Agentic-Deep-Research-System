"""Bounded business predicates. Authorization is always a separate SQL AND."""
from __future__ import annotations

from datetime import datetime
import json
from typing import Literal
from uuid import UUID

from pydantic import Field,model_validator
from app.research_scope import ScopeRecord

VERSION='adrs-retrieval-filters-v1'
# SQL expressions are application-owned. Client field names never become SQL.
FIELDS={
    'source_id':('d.source_id::text','text'),
    'group_name':("COALESCE(s.group_name,d.metadata->>'group',d.metadata->>'source_group',d.metadata->>'knowledge_group')",'text'),
    'source_name':("COALESCE(s.name,d.source_name,d.metadata->>'source_name',d.metadata->>'title')",'text'),
    'source_type':('COALESCE(s.source_type,d.source_type)','text'),
    'format':("COALESCE(s.file_ext,d.metadata->>'file_ext')",'text'),
    'chunk_kind':("d.metadata->'chunk_reference'->>'kind'",'text'),
    'chunk_index':('d.chunk_index','integer'),
    'created_at':('COALESCE(s.created_at,d.created_at)','timestamptz'),
}


def typed_value(field,value):
    if not isinstance(value,str) or not value.strip() or len(value)>300 or any(ord(c)<32 for c in value):
        raise ValueError('filter_values_must_be_bounded_nonblank_strings')
    if field=='source_id':return str(UUID(value))
    if field=='chunk_index':
        number=int(value)
        if not 0<=number<=10000000:raise ValueError('filter_chunk_index_out_of_range')
        return number
    if field=='created_at':
        instant=datetime.fromisoformat(value.replace('Z','+00:00'))
        if instant.tzinfo is None:raise ValueError('filter_created_at_requires_timezone')
        return instant
    return value.strip()


class FilterAtom(ScopeRecord):
    field:Literal['source_id','group_name','source_name','source_type','format','chunk_kind','chunk_index','created_at']
    op:Literal['eq','ne','in','not_in','gte','lte','exists','missing']='eq'
    value:str|tuple[str,...]|None=None

    @model_validator(mode='after')
    def typed(self):
        if self.op in {'exists','missing'}:
            if self.value is not None:raise ValueError('presence_filter_cannot_accept_value')
            return self
        if self.op in {'gte','lte'} and self.field not in {'chunk_index','created_at'}:
            raise ValueError('filter_range_requires_numeric_or_timestamp_field')
        values=self.value if isinstance(self.value,tuple) else (self.value,)
        if self.op in {'in','not_in'}:
            if not isinstance(self.value,tuple) or not 1<=len(values)<=32:raise ValueError('filter_set_requires_one_to_32_values')
        elif not isinstance(self.value,str):raise ValueError('filter_comparison_requires_scalar_string')
        normalized=[typed_value(self.field,item) for item in values]
        if len(set(normalized))!=len(normalized):raise ValueError('filter_set_has_duplicate_values')
        return self


class FilterClause(ScopeRecord):
    all_of:tuple[FilterAtom,...]=Field(min_length=1,max_length=8)


class RetrievalFilter(ScopeRecord):
    any_of:tuple[FilterClause,...]=Field(default=(),max_length=8)
    strategy:Literal['auto','pre_filter']='auto'

    @model_validator(mode='after')
    def bounded(self):
        if sum(len(item.all_of) for item in self.any_of)>32:raise ValueError('filter_atom_limit_32')
        if len(json.dumps(self.model_dump(mode='json'),ensure_ascii=False))>16000:raise ValueError('filter_payload_limit_16000_characters')
        return self


def filter_plan(value):
    from app.query_understanding import identity
    policy=value if isinstance(value,RetrievalFilter) else RetrievalFilter.model_validate(value or {})
    snapshot=policy.model_dump(mode='json')
    return {'version':VERSION,'policy':snapshot,'filter_id':identity(snapshot),'strategy':'pre_filter',
        'authority':'business_conditions_AND_current_owner_lifecycle_and_index_head',
        'missing_semantics':'comparison_excludes_missing_explicit_missing_or_exists_available',
        'created_at_semantics':'source_ingestion_timestamp_not_publication_or_event_date',
        'not_selected':{'post_filter':'authorized_exact_prefilter_retains_top_k_without_post_loss',
            'in_search_graph':'no_active_approximate_graph_index','roaring_bitmap':'no_measured_need_beyond_existing_SQL_indexes'}}


def frozen_filter_policy(snapshot):
    if not snapshot:return None
    plan=filter_plan(snapshot.get('policy'))
    if (snapshot.get('version')!=VERSION or snapshot.get('filter_id')!=plan['filter_id']
            or snapshot.get('strategy')!='pre_filter'):
        raise ValueError('frozen_filter_contract_invalid')
    return plan['policy']


def compile_filter(value,*,start_parameter=7):
    """SQL text comes solely from FIELDS/operators; all values use parameters."""
    policy=value if isinstance(value,RetrievalFilter) else RetrievalFilter.model_validate(value or {})
    parameters=[];groups=[]
    for clause in policy.any_of:
        atoms=[]
        for atom in clause.all_of:
            expression,cast=FIELDS[atom.field]
            if atom.op in {'exists','missing'}:
                atoms.append(f"({expression} IS {'NOT ' if atom.op=='exists' else ''}NULL)")
                continue
            bound=f'${start_parameter+len(parameters)}'
            if atom.op in {'in','not_in'}:
                parameters.append([typed_value(atom.field,item) for item in atom.value])
                comparison=f"{expression} {'<>' if atom.op=='not_in' else '='} {'ALL' if atom.op=='not_in' else 'ANY'}({bound}::{cast}[])"
            else:
                parameters.append(typed_value(atom.field,atom.value))
                operator={'eq':'=','ne':'<>','gte':'>=','lte':'<='}[atom.op]
                comparison=f'{expression} {operator} {bound}::{cast}'
            atoms.append(f'({expression} IS NOT NULL AND {comparison})')
        groups.append('('+' AND '.join(atoms)+')')
    return '('+' OR '.join(groups)+')' if groups else 'TRUE',parameters


def current_document_clause():
    return """(d.source_id IS NULL OR ((h.source_id IS NULL AND s.metadata->'index_policy' IS NULL)
      OR (h.mode='lexical' AND EXISTS(SELECT 1 FROM retrieval_index_generations generation
        WHERE generation.id=h.generation_id AND generation.owner_id=d.owner_id AND generation.source_id=d.source_id
          AND generation.status='ready' AND generation.source_version=s.metadata->>'parse_version_id'
          AND generation.feature_profile_id=s.metadata->'feature_plan'->>'profile_id' AND (
            EXISTS(SELECT 1 FROM retrieval_index_documents published WHERE published.generation_id=generation.id AND published.owner_id=d.owner_id AND published.document_id=d.id)
            OR EXISTS(SELECT 1 FROM retrieval_sparse_postings sparse WHERE sparse.generation_id=generation.id AND sparse.owner_id=d.owner_id AND sparse.document_id=d.id)
            OR EXISTS(SELECT 1 FROM retrieval_english_lexemes stems WHERE stems.generation_id=generation.id AND stems.owner_id=d.owner_id AND stems.document_id=d.id)
            OR EXISTS(SELECT 1 FROM retrieval_model_features vectors WHERE vectors.document_id=d.id AND vectors.owner_id=d.owner_id AND vectors.source_id=d.source_id
              AND vectors.source_version=generation.source_version AND vectors.feature_profile_id=generation.feature_profile_id
              AND generation.manifest->'multivector'->>'status'='published' AND generation.manifest->'multivector'->>'pair_id'=vectors.pair_id)
            OR EXISTS(SELECT 1 FROM retrieval_multimodal_generations images WHERE images.generation_id=generation.id AND images.owner_id=d.owner_id AND images.source_id=d.source_id)
          )))))"""


async def current_filtered_ids(conn,ids,owner_id,group,session_id,filters):
    """Recheck before content enters reranking or crosses the return boundary."""
    if not ids:return set()
    from app.source_lifecycle import access_clause
    business,parameters=compile_filter(filters,start_parameter=5)
    rows=await conn.fetch(f'''SELECT d.id FROM documents d LEFT JOIN document_sources s ON s.id=d.source_id
        LEFT JOIN source_index_heads h ON h.source_id=d.source_id AND h.owner_id=d.owner_id
        WHERE d.owner_id=$1::uuid AND d.id=ANY($4::uuid[])
          AND ($2::text IS NULL OR s.group_name=$2::text OR (d.source_id IS NULL AND
            (d.metadata->>'group'=$2::text OR d.metadata->>'source_group'=$2::text OR d.metadata->>'knowledge_group'=$2::text)))
          AND (d.source_id IS NULL OR (s.owner_id=$1::uuid AND s.status='active'))
          AND ((d.source_id IS NULL AND $2::text IS NOT NULL) OR (d.source_id IS NOT NULL AND {access_clause('s','$3','$2')}))
          AND {current_document_clause()}
          AND {business}''',str(owner_id),group,str(session_id) if session_id else None,[UUID(str(item)) for item in ids],*parameters)
    return {str(row['id']) for row in rows}


async def filter_selectivity(conn,owner_id,group,session_id,filters):
    """At most10001 authorized rows, never global/other-owner cardinalities."""
    from app.source_lifecycle import access_clause
    business,parameters=compile_filter(filters,start_parameter=4)
    row=await conn.fetchrow(f'''WITH observed AS MATERIALIZED (
        SELECT ({business}) AS matches FROM documents d LEFT JOIN document_sources s ON s.id=d.source_id
        LEFT JOIN source_index_heads h ON h.source_id=d.source_id AND h.owner_id=d.owner_id
        WHERE d.owner_id=$1::uuid
          AND ($2::text IS NULL OR s.group_name=$2::text OR (d.source_id IS NULL AND
            (d.metadata->>'group'=$2::text OR d.metadata->>'source_group'=$2::text OR d.metadata->>'knowledge_group'=$2::text)))
          AND (d.source_id IS NULL OR (s.owner_id=$1::uuid AND s.status='active'))
          AND ((d.source_id IS NULL AND $2::text IS NOT NULL) OR (d.source_id IS NOT NULL AND {access_clause('s','$3','$2')}))
          AND {current_document_clause()}
        ORDER BY d.id LIMIT 10001)
        SELECT count(*) AS observed,count(*) FILTER(WHERE matches) AS retained FROM observed''',
        str(owner_id),group,str(session_id) if session_id else None,*parameters)
    total=int(row['observed']);retained=int(row['retained'])
    return {'observed_authorized_chunks':total,'retained_in_observed':retained,
        'retained_ratio_in_observed':retained/total if total else None,
        'scope_complete':total<10001,'observation_limit':10001,
        'meaning':'smaller_retained_ratio_is_more_selective_not_relevance_or_global_coverage'}
