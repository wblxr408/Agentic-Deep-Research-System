"""Owner-bound observations and explicit human judgments; never a model judge."""
from __future__ import annotations

import math
from collections import Counter,defaultdict
from decimal import Decimal,ROUND_HALF_UP
from typing import Annotated,Literal
from uuid import UUID

from pydantic import Field,model_validator
from app.research_scope import ScopeRecord
from app.query_understanding import identity

VERSION='adrs-research-quality-v1'
Grade=Annotated[int,Field(strict=True,ge=0,le=3)]


class RankingJudgments(ScopeRecord):
    run_id:str=Field(min_length=1,max_length=120)
    grades:dict[str,Grade]=Field(min_length=1,max_length=1000)
    top_k:int=Field(default=10,ge=1,le=100)


class AnswerJudgments(ScopeRecord):
    correctness:Literal['yes','no','unknown']='unknown'
    faithfulness:Literal['yes','no','unknown']='unknown'
    citation_accuracy:Literal['yes','no','unknown']='unknown'


class QualityFeedback(ScopeRecord):
    request_id:UUID
    binding_id:str=Field(min_length=8,max_length=80)
    kind:Literal['opened','adopted','corrected','task_complete','ranking_assessment','answer_assessment']
    target_id:str=Field(default='report',min_length=1,max_length=180)
    note:str=Field(default='',max_length=4000)
    ranking:RankingJudgments|None=None
    answer:AnswerJudgments|None=None

    @model_validator(mode='after')
    def explicit_judgment(self):
        if (self.kind=='ranking_assessment')!=(self.ranking is not None):raise ValueError('ranking_judgment_kind_mismatch')
        if (self.kind=='answer_assessment')!=(self.answer is not None):raise ValueError('answer_judgment_kind_mismatch')
        if self.kind=='corrected' and not self.note.strip():raise ValueError('correction_requires_description')
        if self.kind in {'ranking_assessment','answer_assessment','task_complete'} and self.target_id!='report':
            raise ValueError('assessment_targets_current_report')
        return self


def ranking_runs(state):
    """Only actual returned order; parallel evidence arrival is not a ranking."""
    runs=[]
    for node in (state.get('dag') or {}).get('nodes',[]):
        if node.get('node_type') not in {'search','rag'}:continue
        result=node.get('result') or {};rows=result.get('results')
        if not isinstance(rows,list):continue
        candidates=[];seen=set();membership=defaultdict(set)
        for row in rows:
            internal=node['node_type']=='rag';meta=row.get('metadata') or {}
            raw=str(row.get('chunk_id') or '') if internal else row.get('url','')
            if not raw:continue
            key=raw if internal else 'candidate:'+identity(raw)
            if key in seen:continue
            seen.add(key)
            fusion=meta.get('candidate_fusion') if internal else row.get('candidate_fusion')
            routes=[item.get('channel') for item in meta.get('retrieval_routes',[])] if internal else (fusion or {}).get('memberships',[])
            routes=list(dict.fromkeys(route for route in routes if isinstance(route,str)))
            for route in routes:membership[route].add(key)
            candidates.append({'candidate_id':key,'rank':len(candidates)+1,'title':meta.get('title','') if internal else row.get('title',''),
                'routes':routes})
        channels=result.get('retrieval_channels') or []
        observations=channels if isinstance(channels,list) else [channels]
        selectivity=(observations[0].get('filter_selectivity') or {}) if len(observations)==1 else {}
        ratio=selectivity.get('retained_ratio_in_observed')
        bucket='unknown' if ratio is None else '0_to_1pct' if ratio<=.01 else '1_to_10pct' if ratio<=.1 else '10_to_50pct' if ratio<=.5 else '50_to_100pct'
        contributions=[]
        for route,ids in membership.items():
            others=set().union(*(values for name,values in membership.items() if name!=route))
            contributions.append({'route':route,'returned_candidates':len(ids),'unique_returned':len(ids-others),
                'returned_share':len(ids)/len(candidates) if candidates else None,
                'meaning':'membership_of_returned_candidates_not_proof_of_useful_evidence'})
        run_id=str(node.get('node_id'))+':'+identity({'query':node.get('query'),'candidates':candidates})[:20]
        runs.append({'run_id':run_id,'node_id':node.get('node_id'),'tool':node['node_type'],'query':node.get('query'),
            'candidates':candidates,'channel_contributions':contributions,'filter_observation':selectivity,
            'filter_bucket':bucket,'channel_status':channels,'fusion':result.get('candidate_fusion'),
            'metric_scope':'returned_candidates_of_this_bound_node_not_global_recall'})
    return runs


def quality_binding(state,runs=None):
    from app.db.report_delivery import report_binding
    return identity({'version':VERSION,'task_id':state.get('task_id'),'binding':report_binding(state),
        'report':state.get('final_report'),'runs':runs if runs is not None else ranking_runs(state),
        'audit':(state.get('review_status') or {}).get('final_report_audit')})


def ranking_metrics(run,judgment):
    ids=[item['candidate_id'] for item in run['candidates']];grades=judgment['grades'];k=judgment['top_k']
    if not set(grades)<=set(ids):raise ValueError('ranking_labels_outside_bound_candidate_pool')
    complete=bool(ids) and set(ids)<=set(grades)
    ranked=ids[:k];positive={key for key,grade in grades.items() if grade>0}
    hits=sum(key in positive for key in ranked)
    dcg=lambda values:sum((2**grade-1)/math.log2(position+2) for position,grade in enumerate(values))
    ideal=dcg(sorted(grades.values(),reverse=True)[:k]) if complete else None
    pairs=[(grades[left],grades[right]) for i,left in enumerate(ids) if left in grades for right in ids[i+1:]
        if right in grades and grades[left]!=grades[right]]
    return {'run_id':run['run_id'],'top_k':k,'pool_size':len(ids),'judged_count':len(grades),'complete_pool_labels':complete,
        'recall_at_k':hits/len(positive) if complete and positive else None,
        'precision_at_k':hits/len(ranked) if ranked and all(key in grades for key in ranked) else None,
        'mrr':next((1/(i+1) for i,key in enumerate(ids) if key in positive),0.) if complete and positive else None,
        'ndcg_at_k':dcg([grades[key] for key in ranked])/ideal if complete and ideal else None,
        'pairwise_accuracy':sum(left>right for left,right in pairs)/len(pairs) if pairs else None,
        'pairwise_n':len(pairs),'relevant_in_pool':len(positive),'relevant_in_top_k':hits,
        'scope':run['metric_scope'],'filter_bucket':run['filter_bucket'],
        'filtered_recall_at_k':hits/len(positive) if complete and positive and run['tool']=='rag' else None,
        'unavailable_reason':None if complete and positive else 'incomplete_labels_or_no_positive_reference',
        'judgment_source':'explicit_owner_judgment_not_model_or_click_inference'}


def statistics_review(snapshot):
    """Independent arithmetic from frozen member sets; never alters the report."""
    if not snapshot:return {'available':False,'reason':'no_statistics_snapshot','issues':[]}
    from app.organization_statistics import VERSION as STATISTICS_VERSION
    if snapshot.get('schema_version')!=STATISTICS_VERSION:
        return {'available':False,'reason':'historical_statistics_contract_not_supported','issues':[]}
    issues=[]
    for key,metric in (snapshot.get('metric_registry') or {}).items():
        if metric.get('kind')=='count' and metric.get('value') is not None:
            members=metric.get('member_ids',[])
            if len(set(members))!=len(members) or metric.get('value')!=len(set(members)):
                issues.append({'metric_id':key,'reason':'count_differs_from_distinct_members'})
        elif metric.get('kind')=='percentage':
            top=metric.get('numerator_ids',[]);bottom=metric.get('denominator_ids',[])
            expected=float((Decimal(len(set(top)))*100/Decimal(len(set(bottom)))).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)) if bottom else None
            if len(set(top))!=len(top) or len(set(bottom))!=len(bottom) or not set(top)<=set(bottom) or metric.get('numerator')!=len(set(top)) or metric.get('denominator')!=len(set(bottom)) or metric.get('value')!=expected:
                issues.append({'metric_id':key,'reason':'ratio_differs_from_declared_member_sets'})
    family_members=[member for members in (snapshot.get('family_units') or {}).values() for member in members]
    if len(set(family_members))!=len(family_members):issues.append({'reason':'publication_in_multiple_research_families'})
    if set(family_members)!=set(snapshot.get('publication_ids',[])):issues.append({'reason':'family_population_differs_from_publication_population'})
    years=snapshot.get('publication_years') or {}
    unknown={key for key,value in years.items() if value is None}
    if unknown!=set(snapshot.get('unknown_year_ids',[])):issues.append({'reason':'unknown_year_population_differs'})
    for row in snapshot.get('annual',[]):
        if row.get('publication_count') is not None and row['publication_count']!=sum(value==row['year'] for value in years.values()):
            issues.append({'year':row['year'],'reason':'annual_count_differs_from_recorded_years'})
    registry=snapshot.get('metric_registry') or {}
    for series,rows in (snapshot.get('series') or {}).items():
        for row in rows:
            metric=registry.get(row.get('metric_id'))
            if metric is None or row.get('y')!=metric.get('value'):
                issues.append({'series':series,'metric_id':row.get('metric_id'),'reason':'chart_series_differs_from_metric_registry'})
    for row in snapshot.get('label_rows',[]):
        metric=registry.get(row.get('count_metric_id'))
        if metric is None or row.get('publication_count')!=metric.get('value'):
            issues.append({'node_id':row.get('node_id'),'reason':'label_count_differs_from_metric_registry'})
    return {'available':True,'snapshot_id':snapshot.get('snapshot_id'),'issues':issues,
        'input_conflicts':snapshot.get('conflicts',[]),'multi_label_rule':'each_label_over_all_admitted_publications_sum_may_exceed_100pct',
        'unknown_year_count':len(unknown),'semantic_accuracy':None,'scope':'frozen_members_and_arithmetic_not_real_world_corpus_completeness'}


def validate_feedback(state,request):
    runs=ranking_runs(state)
    if request.binding_id!=quality_binding(state,runs):raise ValueError('quality_snapshot_changed_reload_before_feedback')
    review=state.get('review_status') or {};audit=review.get('final_report_audit') or {}
    targets={'report',*[item.get('evidence_id') for item in state.get('collected_evidence',[])],
        *[item.get('citation_id') for item in state.get('citations',[])],*[item.get('claim_id') for item in audit.get('claims',[])]}
    if request.target_id not in targets:raise ValueError('feedback_target_not_in_this_task_snapshot')
    if request.ranking:
        run=next((run for run in runs if run['run_id']==request.ranking.run_id),None)
        if run is None:raise ValueError('ranking_run_not_in_this_task_snapshot')
        ranking_metrics(run,request.ranking.model_dump(mode='json'))


def quality_view(state,feedback):
    evidence=state.get('collected_evidence') or [];review=state.get('review_status') or {}
    result=state.get('organization_result') or {};audit=review.get('final_report_audit') or {}
    runs=ranking_runs(state);binding=quality_binding(state,runs)
    current=[item for item in feedback if item['binding_id']==binding]
    from app.external_evidence import freshness
    coverage=Counter((item.get('acquisition') or {}).get('coverage','unknown') for item in evidence)
    freshness_counts=Counter(freshness(item,state.get('query_understanding'))['status'] for item in evidence if item.get('source_type')=='web')
    calls=[call for history in state.get('tool_histories',[]) for call in history.get('tool_calls',[])]
    failed=[call for call in calls if call.get('status') not in {'success','completed'}]
    judgments=[]
    by_run={run['run_id']:run for run in runs}
    # Latest explicit assessment per run is visible; old versions remain events.
    latest={}
    for item in current:
        if item['kind']=='ranking_assessment':latest[item['payload']['ranking']['run_id']]=item
    for run_id,event in latest.items():
        if run_id in by_run:
            run=by_run[run_id];grades=event['payload']['ranking']['grades'];useful=defaultdict(set)
            for candidate in run['candidates']:
                if grades.get(candidate['candidate_id'],0)>0:
                    for route in candidate['routes']:useful[route].add(candidate['candidate_id'])
            contributions=[]
            for route,ids in useful.items():
                others=set().union(*(values for name,values in useful.items() if name!=route))
                contributions.append({'route':route,'judged_relevant_count':len(ids),'unique_judged_relevant':len(ids-others),
                    'scope':'returned_pool_explicit_positive_judgments_not_full_channel_recall'})
            judgments.append({**ranking_metrics(run,event['payload']['ranking']),'request_id':event['request_id'],
                'judged_channel_contributions':contributions})
    supported=audit.get('supported_claims');total=audit.get('total_claims')
    complete_audit=bool(audit and not audit.get('audit_incomplete') and not audit.get('budget_incomplete'))
    statistics=statistics_review(result.get('statistics'))
    from app.runtime_accounting import runtime_ledger
    suggestions=[]
    if audit.get('needs_review') or not complete_audit:suggestions.append({'kind':'evidence_or_writing','basis':'saved_claim_audit_incomplete_or_requests_revision','action':'按具体主张补读或修订后重新审核'})
    if statistics['issues']:suggestions.append({'kind':'statistics','basis':'frozen_arithmetic_discrepancies','action':'先修正来源集合和统计口径，再生成同一快照的正文与图表'})
    if any(item['kind']=='corrected' for item in current):suggestions.append({'kind':'human_correction','basis':'explicit_owner_correction','action':'查看纠错原文及引用，人工确认后形成新研究或新修订，不自动改写事实'})
    return {'schema_version':VERSION,'binding_id':binding,'session_id':state.get('task_id'),
        'data':{'retained_evidence':len(evidence),'coverage':dict(coverage),'freshness_observations':dict(freshness_counts),
            'parsing_accuracy':None,'reason':'no_independently_labeled_parse_reference'},
        'retrieval_runs':runs,'ranking_judgments':judgments,
        'answer':{'model_audit_supported_claims':supported,'model_audit_total_claims':total,
            'model_audit_source_supported_claims':audit.get('source_supported_claims'),
            'model_audit_method_supported_claims':audit.get('method_supported_claims'),
            'model_audit_supported_ratio':supported/total if complete_audit and isinstance(supported,int) and total else None,
            'audit_complete':complete_audit,'answer_correctness':None,'citation_accuracy':None,
            'human_assessments':[item for item in current if item['kind']=='answer_assessment'],
            'meaning':'model_support_audit_human_judgment_and_factual_correctness_are_distinct'},
        'agent':{'status':state.get('status'),'tool_calls':len(calls),'failed_or_stopped_calls':len(failed),
            'failed_or_stopped_ratio':len(failed)/len(calls) if calls else None,'invalid_tool_call_ratio':None,
            'user_confirmed_task_complete':any(item['kind']=='task_complete' for item in current)},
        'statistics_review':statistics,'feedback':current,'historical_feedback_count':len(feedback)-len(current),
        'feedback_counts':dict(Counter(item['kind'] for item in current)),
        'improvement_candidates':suggestions,'automatic_configuration_changes':False,
        'experiment_policy':{'selected':'explicit_human_judgments_on_retained_results','automatic_runs':False,
            'offline_replay':'requires_separate_dataset_scope_current_access_budget_and_execution_authorization',
            'ab_and_canary':'not_configured_no_traffic_split_or_deployment_effect',
            'minimum_comparison':'compare_tasks_only_with_explicit_same_scope_and_question_no_causal_claim'},
        'cost':state.get('budget_state') or review.get('budget_state'),'runtime_ledger':runtime_ledger(state),
        'effects':{'model_calls':0,'network_collection':0,'fact_ingestion':False,'retuning':False}}


def compare_quality(states):
    def contract(state):
        understanding=state.get('query_understanding') or {};org=state.get('organization_research') or {}
        return identity({'query':state.get('user_query','').strip(),'slots':understanding.get('slots'),
            'scope':org.get('scope'),'purpose':org.get('purpose'),'modules':org.get('modules'),
            'internal_filter':understanding.get('internal_filter'),'temporal':understanding.get('temporal'),
            'delivery':understanding.get('delivery')})
    keys={contract(state) for state in states};rows=[]
    for state in states:
        view=quality_view(state,[]);understanding=state.get('query_understanding') or {}
        audit=(state.get('review_status') or {}).get('final_report_audit') or {}
        rows.append({'session_id':state['task_id'],'binding_id':view['binding_id'],
            'delivery_satisfies_saved_audit':bool(state.get('status')=='completed' and audit and not audit.get('needs_review',True)
                and not audit.get('audit_incomplete') and not audit.get('budget_incomplete')),
            'source_coverage':view['data'],'answer':view['answer'],'cost':view['cost'],'runtime_ledger':view['runtime_ledger'],
            'retrieval_policy':understanding.get('internal_retrieval'),'fusion_policy':understanding.get('candidate_fusion'),
            'ranked_return_count':sum(len(run['candidates']) for run in view['retrieval_runs']),
            'limitations':'different_source_outcomes_and_provider_conditions_are_not_controlled'})
    delivered=sum(row['delivery_satisfies_saved_audit'] for row in rows)
    return {'schema_version':VERSION,'scope_compatible':len(keys)==1,'rows':rows,
        'selected_task_count':len(rows),'saved_audit_delivery_count':delivered,
        'saved_audit_delivery_rate':delivered/len(rows) if rows else None,
        'effects':{'model_calls':0,'network_collection':0,'retuning':False},'causal_improvement':None,
        'reason':'observational_same_request_comparison' if len(keys)==1 else 'different_questions_scopes_or_delivery_no_ranked_comparison'}
