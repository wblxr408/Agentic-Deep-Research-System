"""Comparable date-declared source cohorts, never inferred publication counts."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
import math
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field,model_validator

from app.db.connection import get_db_pool
from app.research_scope import ScopeRecord
from app.retrieval_features import normalize_term
from app.source_lifecycle import access_clause


class TemporalTrendRequest(ScopeRecord):
    as_of:date
    window_start:date|None=None
    window_end:date|None=None
    half_life_days:int=Field(default=730,ge=30,le=3650)
    group_name:str|None=Field(default=None,min_length=1,max_length=100)
    task_id:UUID|None=None
    term:str|None=Field(default=None,min_length=1,max_length=128)

    @model_validator(mode='after')
    def valid_window(self):
        if self.window_start and self.window_end and self.window_start>self.window_end:raise ValueError('trend_window_reversed')
        if self.window_start and self.window_end and self.window_end.year-self.window_start.year>50:raise ValueError('trend_window_too_large')
        return self


async def source_temporal_trend(owner,request):
    group=request.group_name.strip() if request.group_name else None
    if request.group_name and not group:raise HTTPException(422,'trend_group_invalid')
    term=normalize_term(request.term.strip()) if request.term else None
    if request.term and not term:raise HTTPException(422,'trend_term_invalid')
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        if request.task_id and not await conn.fetchval('SELECT id FROM research_sessions WHERE id=$1::uuid AND owner_id=$2::uuid',str(request.task_id),str(owner)):
            raise HTTPException(404,'trend_task_unavailable')
        rows=await conn.fetch(f'''SELECT s.id,s.name,s.group_name,s.metadata->'feature_plan'->'temporal'->>'source_date' AS source_date,
            s.metadata->'feature_plan'->'statistics'->>'token_coverage' AS token_coverage,
            CASE WHEN $4::text IS NULL THEN TRUE ELSE EXISTS (
              SELECT 1 FROM jsonb_array_elements(CASE WHEN jsonb_typeof(s.metadata->'feature_plan'->'children')='array'
                THEN s.metadata->'feature_plan'->'children' ELSE '[]'::jsonb END) child
              WHERE (child->'lexical'->'terms') ? $4::text) END AS term_matched
            FROM document_sources s WHERE s.owner_id=$1::uuid AND s.status='active'
            AND ($2::text IS NULL OR s.group_name=$2::text) AND {access_clause(task_parameter='$3',group_parameter='$2')}
            ORDER BY s.created_at,s.id LIMIT 5001''',str(owner),group,str(request.task_id) if request.task_id else None,term)
    partial=len(rows)>5000;rows=rows[:5000];buckets=defaultdict(lambda:{'count':0,'weighted_count':0.0,'sources':[]})
    unknown_date=0;future_date=0;unknown_term=0;partial_matches=0;outside_window=0
    for row in rows:
        if term and not row['term_matched']:
            if row['token_coverage']!='complete_selected_lexical_policy':unknown_term+=1
            continue
        if term and row['token_coverage']!='complete_selected_lexical_policy':partial_matches+=1
        try:source_date=date.fromisoformat(row['source_date']) if isinstance(row['source_date'],str) else None
        except ValueError:source_date=None
        if source_date is None:unknown_date+=1;continue
        if source_date>request.as_of:future_date+=1;continue
        if request.window_start and source_date<request.window_start or request.window_end and source_date>request.window_end:
            outside_window+=1;continue
        bucket=buckets[source_date.year];bucket['count']+=1
        bucket['weighted_count']+=math.exp2(-(request.as_of-source_date).days/request.half_life_days)
        if len(bucket['sources'])<20:bucket['sources'].append({'source_id':str(row['id']),'name':row['name'],'date':source_date.isoformat()})
    timeline=[]
    if buckets:
        first=min(buckets);last=max(buckets)
        years=sorted(buckets) if last-first>50 else range(first,last+1)
        previous=None;previous_year=None
        for year in years:
            bucket=buckets[year];count=bucket['count']
            timeline.append({'year':year,'source_count':count,'decayed_source_weight':round(bucket['weighted_count'],6),
                'change_from_previous_year':count-previous if previous is not None and previous_year==year-1 else None,
                'source_references':bucket['sources'],'references_truncated':count>len(bucket['sources'])})
            previous=count;previous_year=year
    return {'scope':{'group_name':group,'task_id':str(request.task_id) if request.task_id else None,'term':term,
        'as_of':request.as_of.isoformat(),'window_start':request.window_start.isoformat() if request.window_start else None,
        'window_end':request.window_end.isoformat() if request.window_end else None,'half_life_days':request.half_life_days},
        'semantics':'distinct_current_authorized_sources_by_user_declared_source_date_not_research_or_publication_totals',
        'scanned_sources':len(rows),'scope_truncated':partial,'unknown_date_sources':unknown_date,'future_date_sources':future_date,
        'outside_window_sources':outside_window,'unknown_term_coverage_sources':unknown_term,'partial_term_match_sources':partial_matches,
        'timeline':timeline,'effects':{'model_calls':0,'network_requests':0,'source_mutations':0}}
