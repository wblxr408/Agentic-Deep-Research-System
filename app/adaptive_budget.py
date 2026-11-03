"""Stage shares within an existing root allowance; no new grants or calls."""
from __future__ import annotations


VERSION = 'adrs-adaptive-stage-budget-v1'
POLICY_VERSION = 3
DYNAMIC_POLICY_VERSION = 4


def remaining_work(state, root, stage):
    """Forecast work, not facts or permission to skip a required phase."""
    from math import ceil
    config=state.get('organization_research') or {}
    modules=config.get('modules') or ['report']
    workflow=state.get('analysis_workflow') or {}
    completed=workflow.get('completed') or {}
    plan=workflow.get('reading_plan') or []
    selected=[row for row in plan if row.get('role') in {'core','supporting'}]
    findings=state.get('organization_result') or {}
    works=(findings.get('scope_result') or {}).get('outputs') or []
    work_count=len(selected) or len(works)
    corpus=workflow.get('corpus_progress') or {}
    progress_items=list((corpus.get('items') or {}).values()) if (
        corpus.get('version')=='adrs-task-corpus-progress-v1'
        and corpus.get('analysis_binding')==workflow.get('binding')) else None
    if progress_items is not None and not work_count:work_count=len(progress_items)
    analysis_units=0
    for module in modules:
        if module=='report':continue
        if module=='deep_dive' and progress_items is not None and workflow.get('representative_reading'):
            pending=sum(item.get('reading_status')=='pending' for item in progress_items)
            supplements={item['supplementation']['phase_id'] for item in progress_items
                if (item.get('supplementation') or {}).get('status')=='pending'
                and item.get('missing_fields')}
            # One shared follow-up phase may serve two works. It is not a
            # second completed initial batch, nor a new opportunity on resume.
            analysis_units+=ceil(pending/2)+len(supplements)
            continue
        expected=max(1,ceil(work_count/2)) if module=='deep_dive' else 1
        done=sum(key=='question:'+module or key.startswith('question:'+module+':') for key in completed)
        analysis_units+=max(0,expected-done)
    if config.get('research_handoff_policy')=='adrs-complete-evidence-handoff-v2':
        analysis_units+=int('question:post_reading_synthesis' not in completed)
    active=workflow.get('active_phase')
    if active and active not in completed:analysis_units=max(1,analysis_units)
    if stage=='report':analysis_units=0  # This route has already accepted analysis.
    # A raw section can still need parsing/repair; only a bound, assembled
    # candidate removes drafting demand. Existing recovery validates it again.
    from app.db.report_delivery import retained_report_candidate
    candidate=retained_report_candidate(state) if stage=='report' and findings.get('report_candidate_draft') else None
    writing_units=1 if candidate else len(modules)+1  # Retain room for a required editorial repair.
    from app.organization_purpose import EDITORIAL_PARTITION_POLICY
    if (root.get('remaining_writing_units') is not None and
            (not candidate or config.get('editorial_partition_policy')==EDITORIAL_PARTITION_POLICY)):
        writing_units=max(1,_nonnegative(root['remaining_writing_units']))
    editor_work=None
    if stage=='report' and root.get('editor_work_active') is True:
        writing_units=_nonnegative(root.get('remaining_writing_units'))
        editor_work={'pending_writing_units':writing_units,
            'current_request_bound':_nonnegative(root.get('editor_request_bound')),
            'current_request_purpose':root.get('editor_request_purpose'),
            'semantics':'live_editor_demand_not_quality_approval_or_new_allowance'}
    if candidate:
        draft=candidate.get('module_report') or {}
        paragraph_count=sum(len(row.get('paragraphs') or [])+len(row.get('appendix') or [])
            for row in draft.get('modules') or [])+len(draft.get('summary') or [])
    else:paragraph_count=max(6,len(modules)*6+work_count*2)
    # Claim batches, reader review and surface review remain required even if
    # an earlier report passed: its audit cannot approve a new candidate.
    if candidate and candidate.get('content'):
        from app.claim_verification import extract_claims
        claim_count=len(extract_claims(candidate['content']))
        required_audit_units=ceil(claim_count/20)+2
    else:
        claim_count=None
        required_audit_units=ceil(paragraph_count/8)+2
    saved_audit=(state.get('review_status') or {}).get('final_report_audit') or {}
    session=state.get('session') or {}
    if (stage=='report' and session.get('audit_resume_mode')
            and not session.get('reader_revision_mode') and not session.get('supported_finalization_mode')
            and saved_audit and not saved_audit.get('needs_review',True)
            and not saved_audit.get('audit_incomplete') and not saved_audit.get('budget_incomplete')):
        from app.report_quality import reader_quality_satisfied
        if reader_quality_satisfied(findings.get('module_report'),saved_audit):
            # Unchanged reviewed text needs the remaining surface-review phase,
            # not another forecast of all paragraph and reader audit batches.
            # This only reallocates the original allowance; it approves no surface.
            required_audit_units=1
    audit_units=max(1,required_audit_units-_nonnegative(root.get('current_stage_audit_calls')))
    reader_work=None;document_work=None
    from app.report_material_packets import SUPPORTED_POLICIES as MATERIAL_POLICIES
    reader=findings.get('reader_quality') or saved_audit.get('reader_quality') or {}
    plan=reader.get('material_packet_plan') or {}
    module=(candidate or {}).get('module_report') or findings.get('module_report') or {}
    from app.query_understanding import identity
    if (config.get('reader_material_policy') in MATERIAL_POLICIES and plan.get('policy')==config.get('reader_material_policy')
            and reader.get('report_content_id')==plan.get('report_content_id')==identity(module.get('reading_structure'))
            and isinstance(plan.get('required_packet_bindings'),dict)):
        parts=reader.get('material_reviews') or {}
        pending=sum((parts.get(key) or {}).get('binding')!=binding or (parts.get(key) or {}).get('validated') is not True
            for key,binding in plan['required_packet_bindings'].items())
        reader_work={'required_packets':len(plan['required_packet_bindings']),'pending_packets':pending,
            'blocked_packets':len(plan.get('blocked_packets') or []),'semantics':'remaining_work_floor_not_new_grant'}
        # These are already remaining units: never subtract earlier audit calls again.
        audit_units=max(audit_units,pending+1)
    from app.report_material_packets import DOCUMENT_POLICY
    document=reader.get('document_review') or {};document_plan=document.get('plan') or {}
    if (config.get('reader_document_policy')==DOCUMENT_POLICY and document.get('policy')==DOCUMENT_POLICY
            and document.get('report_content_id')==identity(module.get('reading_structure'))
            and isinstance(document_plan.get('required_bindings'),dict)):
        parts=document.get('passes') or {}
        pending=sum((parts.get(key) or {}).get('binding')!=binding or (parts.get(key) or {}).get('validated') is not True
            for key,binding in document_plan['required_bindings'].items())
        document_work={'required_passes':len(document_plan['required_bindings']),'pending_passes':pending,
            'semantics':'remaining_work_floor_not_new_grant'}
        audit_units=max(audit_units,pending+1)
    samples={'analysis':[],'writing':[],'audit':[]}
    seen=set()
    for row in root.get('model_requests') or []:
        call=row.get('call_id')
        if not call or call in seen:continue
        seen.add(call)
        if row.get('status')!='settled' or not row.get('response_received'):continue
        category='audit' if row.get('purpose')=='audit' else 'writing' if row.get('agent')=='report' else 'analysis'
        value=_nonnegative(row.get('total_tokens'))
        if value:samples[category].append(value)
    defaults={'analysis':8000,'writing':6000,'audit':6000}
    costs={}
    for key,values in samples.items():
        ordered=sorted(values)
        # Upper quartile plus headroom avoids treating the cheapest call as
        # representative. Provider admission still uses the exact request bound.
        costs[key]=max(2048,ceil((ordered[min(len(ordered)-1,ceil(len(ordered)*.75)-1)]
            if ordered else defaults[key])*1.25))
    units={'analysis':analysis_units,'writing':writing_units,'audit':audit_units}
    tokens={key:units[key]*costs[key] for key in units}
    if editor_work and writing_units and editor_work['current_request_purpose']!='audit':
        # The current complete request is known; observed per-call samples
        # estimate only the other unfinished steps, not this request again.
        tokens['writing']=max(tokens['writing'],editor_work['current_request_bound']+
            max(0,writing_units-1)*costs['writing'])
    if editor_work and editor_work['current_request_purpose']=='audit':
        tokens['audit']=max(tokens['audit'],editor_work['current_request_bound'])
    return {'units':units,'unit_tokens':costs,'assembled_claim_count':claim_count,
        **({'editor_work':editor_work} if editor_work is not None else {}),
        **({'reader_material_work':reader_work} if reader_work is not None else {}),
        **({'reader_document_work':document_work} if document_work is not None else {}),
        'tokens':tokens,
        'sample_counts':{key:len(value) for key,value in samples.items()},
        'basis':'remaining_phases_and_bound_candidate_with_observed_usage',
        'reading_work':{'members':len(progress_items),
            'works_with_unresolved_fields':sum(bool(item.get('missing_fields')) for item in progress_items),
            'fulltext_gap_works':sum(any(gap.get('kind')=='fulltext_unavailable' for gap in item.get('gaps',[])) for item in progress_items),
            'basis':'current_phase_checkpoint_not_indexed_count_or_completed_call_count'} if progress_items is not None else None,
        'estimated':True,'quality_approval':False}


def dynamic_allocation(state, root, stage):
    remaining=max(0,_nonnegative(root.get('max_total_tokens'))-
        _nonnegative(root.get('used_total_tokens'))-_nonnegative(root.get('reserved_inflight_tokens')))
    demand=remaining_work(state,root,stage)
    needs=demand['tokens']
    # The current stage needs room even before a reading plan exists.
    current=needs['analysis'] if stage!='report' else needs['writing']
    if stage!='report':current=max(current,demand['unit_tokens']['analysis'])
    future=needs['audit']+(needs['writing'] if stage!='report' else 0)
    total=current+future
    shortfall=max(0,total-remaining)
    # When the forecast cannot fit, retain proportional room for all mandatory
    # work rather than reserve 100% for downstream stages. This is a warning,
    # never permission to omit review, refund unknown use or enlarge the root.
    scale=min(1,remaining/max(1,total))
    audit=min(remaining,int(needs['audit']*scale))
    report=min(remaining-audit,int(needs['writing']*scale)) if stage!='report' else 0
    seconds=max(0,float(root.get('max_wall_clock_seconds') or 0)-float(root.get('elapsed_wall_clock_seconds') or 0))
    cost_limit=float(root.get('max_cost_usd') or 0)
    cost_used=float(root.get('used_cost_usd') or 0)
    return {'version':'adrs-dynamic-resource-budget-v1','stage':stage,**_signals(state),
        'root_limit':_nonnegative(root.get('max_total_tokens')),
        'root_used':_nonnegative(root.get('used_total_tokens')),
        'root_inflight':_nonnegative(root.get('reserved_inflight_tokens')),'root_remaining':remaining,
        'audit_hold':audit,'report_hold':report,
        'stage_limit':remaining if stage=='report' else remaining-audit-report,
        'writing_available':remaining-audit if stage=='report' else None,
        'audit_seconds_hold':min(seconds,seconds*needs['audit']/max(1,total)),
        'remaining_seconds':seconds,
        'known_cost_remaining_usd':max(0,cost_limit-cost_used) if cost_limit else None,
        'cost_forecast':'not_estimated_without_complete_provider_prices',
        'remaining_tool_calls':max(0,_nonnegative(root.get('max_tool_calls'))-_nonnegative(root.get('used_tool_calls'))),
        'demand':demand,'forecast_shortfall_tokens':shortfall,
        'status':'forecast_shortfall' if shortfall else 'forecast_fits',
        'reason':'remaining_required_work_exceeds_allowance' if shortfall else 'reallocated_for_remaining_required_work',
        'unchanged_root_limit':True,'semantics':'estimate_not_completion_guarantee_or_quality_approval'}


def _nonnegative(value):
    try: return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError): return 0


def _signals(state):
    understanding = state.get('query_understanding') or {}
    slots = understanding.get('slots') or {}
    depth = slots.get('depth') if slots.get('depth') in {'brief', 'standard', 'deep'} else 'standard'
    config = state.get('organization_research') or {}
    modules = config.get('modules') or slots.get('modules') or []
    complexity = (understanding.get('complexity') or {}).get('level')
    control = state.get('iteration_control') or {}
    specific_gap = bool(control.get('action') == 'replan' and control.get('gap_reasons'))
    reasons=list(control.get('gap_reasons') or [])[:8] if specific_gap else []
    retained_gap=(state.get('session') or {}).get('retained_identity_coverage_repair') or {}
    if (config.get('research_handoff_policy')=='adrs-complete-evidence-handoff-v2'
            and retained_gap.get('reason')=='acquired_article_omitted_from_identity_reading'
            and retained_gap.get('missing_batches')):
        specific_gap=True
        reasons.append('retained_article_identity_coverage')
    return {'depth': depth, 'complexity': complexity if complexity in {'simple', 'moderate', 'complex'} else 'unknown',
            'module_count': len(modules), 'deep_reading_selected': 'deep_dive' in modules,
            'specific_gap': specific_gap,
            'gap_reasons': reasons}


def stage_allocation(state, root, stage):
    """Calculate a local stage ceiling and future holds from current root use.

    Holds are admission ceilings, never money spent. Base audit and report
    reservations are the existing frozen minimums, with a limited extra share
    for demanding tasks. A concrete reflection gap releases only extra shares
    to bounded acquisition/replanning. A prior report's audit cannot cover a
    newly generated report, so its base hold is not erased on resume.
    """
    if root.get('budget_policy_version') == DYNAMIC_POLICY_VERSION:
        return dynamic_allocation(state,root,stage)
    if root.get('budget_policy_version') != POLICY_VERSION: return None
    signals = _signals(state)
    total = _nonnegative(root.get('max_total_tokens'))
    used = _nonnegative(root.get('used_total_tokens'))
    inflight = _nonnegative(root.get('reserved_inflight_tokens'))
    remaining = max(0, total - used - inflight)
    base_audit = min(total, _nonnegative(root.get('audit_token_reserve')))
    base_report = min(total - base_audit, _nonnegative(root.get('report_token_reserve')))
    flexible = max(0, remaining - base_audit - base_report)
    demanding = signals['depth'] == 'deep' or signals['deep_reading_selected']
    broad = signals['complexity'] == 'complex' or signals['module_count'] > 3
    audit_extra = min(total // 10, flexible // 4) if demanding else 0
    report_extra = min(total // 20, max(0, flexible - audit_extra) // 5) if broad else 0
    if stage in {'replan','analyst','reflection'} and signals['specific_gap']:
        # The corrective analysis belongs to the same revision as its planner.
        # Reinstating the extras here strands the work after acquisition.
        audit_extra = 0
        report_extra = 0
    audit_hold = min(remaining, base_audit + audit_extra)
    report_hold = min(max(0, remaining - audit_hold), base_report + report_extra)
    is_report = stage == 'report'
    # Unknown dispatched usage remains charged. A recovery cannot simultaneously
    # retain that charge and reserve almost all remaining tokens for an audit
    # of a draft which cannot be written. Share the remaining root, explicitly;
    # incomplete auditing still blocks delivery. No grant/refund is introduced.
    recovery_share=bool(is_report and any(item.get('status')=='unknown'
        and item.get('purpose')=='report' for item in root.get('model_requests') or []))
    if recovery_share:audit_hold=min(audit_hold,remaining*3//5)
    local_limit = remaining if is_report else max(0, remaining - audit_hold - report_hold)
    return {'version': VERSION, 'stage': stage, **signals,
            'root_limit': total, 'root_used': used, 'root_inflight': inflight, 'root_remaining': remaining,
            'audit_base': base_audit, 'audit_extra': audit_extra, 'audit_hold': audit_hold,
            'report_base': base_report, 'report_extra': report_extra, 'report_hold': report_hold,
            'writing_available': max(0, remaining - audit_hold) if is_report else None,
            'stage_limit': local_limit, 'unchanged_root_limit': True,
            'unknown_report_usage_remaining_share':recovery_share,
            'semantics': 'bounded_holds_not_spend_or_quality_guarantee'}


def tool_allocation(state, node_type, share):
    """Cap one handoff; unused calls remain available to later steps."""
    root = state.get('budget_state') or {}
    if root.get('budget_policy_version') not in {POLICY_VERSION,DYNAMIC_POLICY_VERSION}: return None
    signals = _signals(state)
    share = _nonnegative(share)
    cap = {'brief': 2, 'standard': 4, 'deep': 8}[signals['depth']]
    if signals['deep_reading_selected'] and node_type == 'browser': cap = max(cap, 8)
    if signals['specific_gap']: cap += min(2, len(signals['gap_reasons']))
    if node_type == 'search':
        followup=((state.get('query_understanding') or {}).get('research_strategy') or {}).get('source_followup') or {}
        if followup.get('version') in {'adrs-discovery-handoff-v1','adrs-discovery-handoff-v2','adrs-discovery-handoff-v3','adrs-discovery-handoff-v4','adrs-discovery-handoff-v5'}:
            cap=3
        channels = list(dict.fromkeys((state.get('session') or {}).get('channels') or []))
        options = (state.get('query_understanding') or {}).get('query_rewriting') or {}
        variants = max(1, min(4, _nonnegative(options.get('max_variants')) or 1))
        # Explicitly selected channels and variants may require distinct calls;
        # the existing route still validates transport and source scope.
        cap = max(cap, len(channels) * variants)
    pending_count=None
    if root.get('budget_policy_version')==DYNAMIC_POLICY_VERSION:
        dag=state.get('dag') or {}
        if hasattr(dag,'model_dump'):dag=dag.model_dump()
        done=set(state.get('completed_nodes') or [])
        pending_count=sum(row.get('node_type') in {'search','browser','rag'} and row.get('node_id') not in done
            for row in dag.get('nodes',[]) if isinstance(row,dict))
        remaining=max(0,_nonnegative(root.get('max_tool_calls'))-_nonnegative(root.get('used_tool_calls')))
        # Fair-share the remaining requests across actual unfinished tool nodes.
        # A targeted gap uses the existing bounded extra allowance instead.
        if pending_count and not signals['specific_gap']:
            from math import ceil
            cap=min(cap,max(1,ceil(remaining/pending_count)))
        cap=min(cap,remaining)
    return {'version': 'adrs-dynamic-resource-budget-v1' if pending_count is not None else VERSION,
            'node_type': node_type, **signals,'pending_tool_nodes':pending_count,
            'root_share': share, 'per_step_cap': cap, 'call_allowance': min(share, cap),
            'semantics': 'unused_calls_remain_in_original_root'}
