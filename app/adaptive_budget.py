"""Stage shares within an existing root allowance; no new grants or calls."""
from __future__ import annotations


VERSION = 'adrs-adaptive-stage-budget-v1'
POLICY_VERSION = 3


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
    return {'depth': depth, 'complexity': complexity if complexity in {'simple', 'moderate', 'complex'} else 'unknown',
            'module_count': len(modules), 'deep_reading_selected': 'deep_dive' in modules,
            'specific_gap': specific_gap,
            'gap_reasons': list(control.get('gap_reasons') or [])[:8] if specific_gap else []}


def stage_allocation(state, root, stage):
    """Calculate a local stage ceiling and future holds from current root use.

    Holds are admission ceilings, never money spent. Base audit and report
    reservations are the existing frozen minimums, with a limited extra share
    for demanding tasks. A concrete reflection gap releases only extra shares
    to bounded acquisition/replanning. A prior report's audit cannot cover a
    newly generated report, so its base hold is not erased on resume.
    """
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
    if stage == 'replan' and signals['specific_gap']:
        audit_extra //= 2
        report_extra = 0
    audit_hold = min(remaining, base_audit + audit_extra)
    report_hold = min(max(0, remaining - audit_hold), base_report + report_extra)
    is_report = stage == 'report'
    local_limit = remaining if is_report else max(0, remaining - audit_hold - report_hold)
    return {'version': VERSION, 'stage': stage, **signals,
            'root_limit': total, 'root_used': used, 'root_inflight': inflight, 'root_remaining': remaining,
            'audit_base': base_audit, 'audit_extra': audit_extra, 'audit_hold': audit_hold,
            'report_base': base_report, 'report_extra': report_extra, 'report_hold': report_hold,
            'writing_available': max(0, remaining - audit_hold) if is_report else None,
            'stage_limit': local_limit, 'unchanged_root_limit': True,
            'semantics': 'bounded_holds_not_spend_or_quality_guarantee'}


def tool_allocation(state, node_type, share):
    """Cap one handoff; unused calls remain available to later steps."""
    root = state.get('budget_state') or {}
    if root.get('budget_policy_version') != POLICY_VERSION: return None
    signals = _signals(state)
    share = _nonnegative(share)
    cap = {'brief': 2, 'standard': 4, 'deep': 8}[signals['depth']]
    if signals['deep_reading_selected'] and node_type == 'browser': cap = max(cap, 8)
    if signals['specific_gap']: cap += min(2, len(signals['gap_reasons']))
    if node_type == 'search':
        followup=((state.get('query_understanding') or {}).get('research_strategy') or {}).get('source_followup') or {}
        if followup.get('version') in {'adrs-discovery-handoff-v1','adrs-discovery-handoff-v2','adrs-discovery-handoff-v3','adrs-discovery-handoff-v4'}:
            cap=3
        channels = list(dict.fromkeys((state.get('session') or {}).get('channels') or []))
        options = (state.get('query_understanding') or {}).get('query_rewriting') or {}
        variants = max(1, min(4, _nonnegative(options.get('max_variants')) or 1))
        # Explicitly selected channels and variants may require distinct calls;
        # the existing route still validates transport and source scope.
        cap = max(cap, len(channels) * variants)
    return {'version': VERSION, 'node_type': node_type, **signals,
            'root_share': share, 'per_step_cap': cap, 'call_allowance': min(share, cap),
            'semantics': 'unused_calls_remain_in_original_root'}
