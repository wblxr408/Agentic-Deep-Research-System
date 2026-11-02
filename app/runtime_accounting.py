"""Read existing receipts once, without new quota owners or paid evaluations."""
from __future__ import annotations

from collections import Counter
import math

VERSION='adrs-runtime-ledger-v2'


def observed_latency(rows):
    values=sorted(row['duration_ms'] for row in rows if isinstance(row.get('duration_ms'),(int,float))
        and not isinstance(row.get('duration_ms'),bool) and math.isfinite(row['duration_ms']) and row['duration_ms']>=0)
    return {'n':len(values),'missing':len(rows)-len(values),
        **{name:values[max(0,math.ceil(len(values)*fraction)-1)] if values else None
            for name,fraction in (('p50_ms',.5),('p95_ms',.95),('p99_ms',.99))},
        'method':'nearest_rank_on_observed_receipts_not_population_SLA'}


def application_reuse(state):
    """Project saved reuse observations, without inventing skipped provider usage."""
    result=state.get('organization_result') or {}
    audit=(state.get('review_status') or {}).get('final_report_audit') or {}
    context=result.get('report_context') or {}
    units=[dict(item) for item in context.get('application_response_reuse') or []]
    for claim in audit.get('claims') or []:
        if claim.get('verification_reused'):
            units.append({'operation':'claim_judgment','content_unit_id':claim.get('claim_id'),
                'reused_from_unit_id':claim.get('reused_from_claim_id'),
                'basis':'saved_claim_dependency_checks','status':claim.get('status'),
                'effect':'judgment_reused_for_this_unit_not_one_avoided_request_per_claim'})
    reader=audit.get('reader_quality') or result.get('reader_quality') or {}
    parts=[('reader_review',reader),('reader_repetition_impact',reader.get('reading_impact_review') or {}),
        *[('reader_document:'+name,item) for name,item in ((reader.get('document_review') or {}).get('passes') or {}).items()],
        *[('reader_material:'+name,item) for name,item in (reader.get('material_reviews') or {}).items()]]
    observations=[]
    for operation,part in parts:
        if part.get('response_reuse'):observations.append({'operation':operation,**part['response_reuse']})
        if part.get('reused_response'):
            units.append({'operation':operation,'input_binding':part.get('binding'),
                'basis':'saved_response_current_input_model_and_contract',
                'effect':'response_reused_not_independent_quality_approval'})
    drawing=result.get('chart_rendering') or {}
    if drawing.get('cache_status')=='hit':
        units.append({'operation':'figure_rendering','content_unit_id':drawing.get('descriptor_id'),
            'basis':drawing.get('reuse_semantics'),'reused_from':drawing.get('reused_from'),
            'effect':'retained_frozen_asset_reused_original_cost_not_refunded'})
    return {'scope':'current_saved_artifact_observations_not_root_event_history',
        'reused_units':units,'reuse_observations':observations,
        'unit_counts':dict(Counter(item['operation'] for item in units)),
        'saved_tokens':None,'saved_cost_usd':None,
        'meaning':'application_reuse_is_separate_from_provider_prefix_cache_no_counterfactual_savings_inferred'}


def runtime_ledger(state):
    budget=state.get('budget_state') or (state.get('review_status') or {}).get('budget_state') or {}
    model=[];seen=set()
    for index,row in enumerate(budget.get('model_requests') or []):
        key=row.get('call_id') or 'legacy-position:'+str(index)
        if key in seen:continue
        seen.add(key);route=row.get('routing') or {}
        known=row.get('cost_known') is True and row.get('status') in {'settled','blocked_before_dispatch'}
        model.append({'receipt_id':key,'kind':'model_request','stage':'render' if row.get('purpose')=='render' else route.get('stage') or row.get('agent'),
            'purpose':row.get('purpose'),'operation':row.get('operation'),
            'content_unit_id':row.get('content_unit_id'),'model':row.get('model'),'status':row.get('status'),
            'tokens':row.get('total_tokens'),'reported_tokens':row.get('reported_tokens'),
            'tokens_estimated':row.get('estimated',True),'duration_ms':row.get('duration_ms'),
            'cost_usd':row.get('cost_usd') if known else None,'cost_basis':row.get('cost_basis','unknown'),
            'price':route.get('price'),'route_id':route.get('route_id'),
            'capability_upgrade':route.get('capability_upgrade')})
        model[-1].update(admission_expires_at=row.get('admission_expires_at'),reserved_tokens=row.get('reserved_tokens'),
            dispatch_status=row.get('dispatch_status'))
        model[-1].update(provider_usage=row.get('provider_usage'),
            provider_cache_request=row.get('provider_cache_request'),
            token_cost_components=row.get('token_cost_components'),
            known_token_cost_subtotal_usd=row.get('known_token_cost_subtotal_usd',row.get('cost_usd') if known else None),
            cost_scope=row.get('cost_scope'))
    tools=[];resources=[];tool_ids=set()
    for history in state.get('tool_histories') or []:
        for call in history.get('tool_calls') or []:
            key=call.get('call_id')
            if key and key in tool_ids:continue
            if key:tool_ids.add(key)
            safe=call.get('safety_json') or {};observations=safe.get('retrieval_channels') or []
            if isinstance(observations,dict):observations=[observations]
            for i,observation in enumerate(observations):
                for j,event in enumerate(observation.get('resource_usage') or []):
                    resources.append({'receipt_id':str(key or len(tools))+':'+str(i)+':'+str(j),
                        'tool_call_id':key,**event})
            tools.append({'receipt_id':key,'kind':'collection_or_retrieval','tool_name':call.get('tool_name'),
                'status':call.get('status'),'duration_ms':call.get('duration_ms'),
                'usage_source':call.get('usage_source'),'estimated':call.get('estimated',True),
                'cost_usd':call.get('cost_usd') if call.get('usage_source') in {'provider_reported','configured_price'} and not call.get('estimated',True) else None,
                'channel_attempts':[{field:item.get(field) for field in ('channel','backend','status','call_count','duration_ms')}
                    for item in safe.get('channel_attempts',[])],
                'error_category':call.get('error_category')})
    operations=budget.get('tool_operation_receipts') or []
    for operation in operations:
        for call in operation.get('calls') or []:
            key=call['call_id']
            if key in tool_ids:continue
            tool_ids.add(key)
            tools.append({'receipt_id':key,'operation_id':operation['operation_id'],'kind':'collection_or_retrieval',
                'tool_name':call.get('tool_name'),'status':call.get('status'),'duration_ms':call.get('duration_ms'),
                'cost_usd':call.get('cost_usd'),'cost_basis':call.get('cost_basis'),'accounted_calls':call.get('accounted_calls'),
                'network_calls':call.get('network_calls'),'error_category':operation.get('error_category'),
                'origin':'durable_tool_receipt_may_arrive_after_root_cancellation'})
            for index,event in enumerate(call.get('resource_usage') or []):
                resources.append({'receipt_id':key+':late:'+str(index),'tool_call_id':key,**event})
    drawing=(state.get('organization_result') or {}).get('chart_rendering') or {}
    if drawing:
        resources.append({'receipt_id':'drawing:'+str(drawing.get('descriptor_id')),'kind':'figure_rendering',
            'execution':'shipped_local_renderer','status':drawing.get('status'),
            'duration_ms':drawing.get('duration_ms'),'renderer_duration_ms':drawing.get('renderer_duration_ms'),
            'asset_count':len(drawing.get('assets') or []),'model_calls':drawing.get('model_calls'),
            'cache_status':drawing.get('cache_status','not_recorded'),'cost_basis':'drawing_model_in_model_receipts_local_compute_not_priced',
            'provider_charge_usd':None})
    known_model=sum(item['known_token_cost_subtotal_usd'] for item in model
        if item['known_token_cost_subtotal_usd'] is not None)
    unknown_model=sum(item['cost_usd'] is None for item in model)
    known_tools=sum(item['cost_usd'] for item in tools if item['cost_usd'] is not None)
    unknown_tools=sum(item['cost_usd'] is None for item in tools)
    observed_model=[item for item in model if item['status'] in {'settled','unknown'}]
    return {'schema_version':VERSION,'model_requests':model,'tool_requests':tools,'tool_operations':operations,'local_resources':resources,
        'application_reuse':application_reuse(state),
        'known_model_cost_subtotal_usd':round(known_model,6),'known_tool_cost_subtotal_usd':round(known_tools,6),
        'unknown_model_cost_requests':unknown_model,'unknown_tool_cost_requests':unknown_tools,
        'monetary_total_usd':None if unknown_model or unknown_tools or resources else round(known_model+known_tools,6) if model or tools else None,
        'cost_status':'unknown_components_present' if unknown_model or unknown_tools or resources else 'reference_estimate_not_invoice' if model or tools else 'no_receipts',
        'model_stage_counts':dict(Counter(item['stage'] or 'unattributed' for item in model)),
        'model_operation_counts':dict(Counter(item['operation'] or item['purpose'] or 'unattributed' for item in model)),
        'model_request_status_counts':dict(Counter(item['status'] or 'unattributed' for item in model)),
        'provider_cache_usage':{
            'requests_with_complete_input_breakdown':sum(bool((item['provider_usage'] or {}).get('input_breakdown_complete')) for item in observed_model),
            'requests_with_incomplete_or_legacy_breakdown':sum(not bool((item['provider_usage'] or {}).get('input_breakdown_complete')) for item in observed_model),
            'reported_cache_read_tokens_subtotal':sum(((item['provider_usage'] or {}).get('input_tokens') or {}).get('cache_read') or 0 for item in observed_model),
            'reported_cache_write_tokens_subtotal':sum(((item['provider_usage'] or {}).get('input_tokens') or {}).get('cache_write') or 0 for item in observed_model),
            'meaning':'provider_prefix_usage_not_application_response_reuse_or_root_refund'},
        'observed_latency':{'model':observed_latency(model),'tool':observed_latency(tools),'local':observed_latency(resources)},
        'legacy_aggregate':{'charged_token_counter':budget.get('used_total_tokens'),'recorded_cost_counter_usd':budget.get('used_cost_usd'),
            'counter_is_not_full_invoice':True},
        'accounting_rule':'model_tool_and_local_resource_receipts_are_separate_not_summed_twice',
        'limitations':['local_compute_unpriced','historical_receipts_may_lack_timing_or_call_identity','not_energy_or_memory_usage_measurement']}
