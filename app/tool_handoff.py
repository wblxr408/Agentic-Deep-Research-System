"""Trusted root -> one bounded tool -> root acceptance, within the existing graph."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from app.db.connection import get_db_pool
from app.graph.state import serialize_dag
from app.planning_control import PlanningError, make_handoff, result_binding_error,tool_query_context
from app.query_understanding import identity
from app.external_evidence import matches_request


def prepare_handoffs(state, dag, node_ids, remaining_calls, remaining_seconds):
    nodes = sorted((node for node in dag.nodes if node.node_id in node_ids), key=lambda node: node.node_type == 'rag')
    quotient, remainder = divmod(max(0, remaining_calls), max(1, len(nodes)))
    result = {node.node_id: make_handoff(state, node, call_allowance=quotient+(index < remainder),
        seconds=min(node.timeout_seconds, remaining_seconds)) for index, node in enumerate(nodes)}
    for node in nodes:
        result[node.node_id]['evidence_refs'] = list(dict.fromkeys([*node.evidence_ids,
            *[item['evidence_id'] for item in state.get('collected_evidence', [])
                if node.node_type == 'browser' and matches_request(item,node.query) and item.get('evidence_id')]]))
    return result


def tool_payload(state, dag, node):
    """No report, analyses, weights, other skills, full histories or sibling DAGs."""
    handoff = state['tool_handoffs'][node.node_id]
    compilation = (state.get('skill_context') or {}).get('stage_compilation')
    if compilation is not None:
        profile = (compilation.get('profiles') or {}).get(node.node_type)
        skill = {'effective_tool_allowlist': [node.node_type], 'stage_compilation': {
            'schema_version': compilation['schema_version'], 'ready': compilation['ready'],
            'compilation_id': compilation['compilation_id'], 'dispatch_tools': [node.node_type],
            'profiles': {node.node_type: profile}}}
    else:
        # Legacy restores use the frozen legacy instructions, never today's registry.
        old = state.get('skill_context') or {}
        skill = {key: deepcopy(old[key]) for key in ('effective_tool_allowlist', 'effective_prompt_sections', 'effective_agent_hints') if key in old}
    scope = state.get('organization_research')
    session = state.get('session') or {}
    payload = {key: deepcopy(state.get(key)) for key in ('task_id','user_query','guardrail_decision',
        'use_internal_docs','rag_group','retrieval_policy','budget_state','output_length','created_at',
        'user_confirmed','revision_count')}
    projected = dag.model_copy(deep=True)
    projected.nodes, projected.edges = [node.model_copy(deep=True)], []
    payload.update(dag=serialize_dag(projected), tool_handoff=deepcopy(handoff),
        plan_manifest={key: state['plan_manifest'][key] for key in ('plan_version','execution_id')},
        session={key: deepcopy(session[key]) for key in ('session_id','owner_id','execution_id','channels','output_length','created_at') if key in session},
        organization_research={key: deepcopy(scope[key]) for key in ('schema_version','scope','corpus') if key in scope} if scope else None,
        query_understanding=tool_query_context(state,node.node_type),
        skill_context=deepcopy(skill), tool_histories=[], agent_trace=[],
        collected_evidence=[deepcopy(item) for item in state.get('collected_evidence', []) if node.node_type == 'browser' and matches_request(item,node.query)],
        channel_call_allowance=handoff['call_allowance'], executing_nodes=[node.node_id], current_executing_nodes=[node.node_id],
        approval_decisions=[deepcopy(item) for item in state.get('approval_decisions', []) if item.get('node_id') == node.node_id])
    return payload


async def current_execution(binding):
    from app.config import get_settings
    local=not get_settings().security.auth_enabled and binding['owner_id']=='00000000-0000-0000-0000-000000000000'
    pool = await get_db_pool()
    async with pool.acquire() as connection:
        return bool(await connection.fetchval('''SELECT EXISTS(SELECT 1 FROM research_sessions s
            LEFT JOIN auth_principals p ON p.id=s.owner_id
            WHERE s.id=$1::uuid AND s.owner_id=$2::uuid AND s.execution_id=$3::uuid AND s.status='running'
                AND (p.is_active=TRUE OR $4::boolean))''',
            binding['task_id'], binding['owner_id'], binding['execution_id'],local))


def bound_tool_node(function):
    async def execute(state):
        from app.execution_control import current_control
        control=current_control()
        binding = deepcopy(state.get('tool_handoff') or {})
        if not binding.get('operation_id'):
            raise PlanningError('trusted_tool_handoff_required')
        error = result_binding_error(binding, binding, state.get('plan_manifest') or {})
        if (binding.get('query_context_identity') and
                identity(state.get('query_understanding') or {})!=binding['query_context_identity']):
            error=error or 'tool_query_context_binding_conflict'
        started, payload = False, {}
        if not error and not await current_execution(binding):
            error = 'execution_no_longer_current'
        if not error and binding['call_allowance'] <= 0:
            error = 'tool_budget_not_reserved'
        admitted=False
        if not error and control:
            admitted=await control.tool_receipt(binding,admission=True)
            if not admitted:error='tool_operation_already_started_or_budget_unavailable'
        if not error:
            try:
                started = True
                seconds = max(0.001, (datetime.fromisoformat(binding['expires_at'])-datetime.now(UTC)).total_seconds())
                work = function(state) if asyncio.iscoroutinefunction(function) else asyncio.to_thread(function, state)
                payload = await asyncio.wait_for(work, timeout=seconds)
            except TimeoutError:
                error = 'tool_result_timeout_unknown'
            except asyncio.CancelledError:
                if admitted:
                    await asyncio.shield(control.tool_receipt(binding,payload,'tool_execution_interrupted_unknown'))
                raise
            except (OSError, RuntimeError, TypeError, ValueError, KeyError) as exc:
                error = 'tool_result_unknown:' + type(exc).__name__
            error = error or result_binding_error(binding, binding, state.get('plan_manifest') or {})
            if not error and not await current_execution(binding):
                error = 'execution_no_longer_current'
        if admitted:
            await control.tool_receipt(binding,payload,error)
        # Rejected raw data never enters the root evidence/model context. A timed
        # out thread cannot be forcibly killed; its existing transport deadlines
        # remain active, and its reserved calls are conservatively consumed.
        envelope = {'binding': binding, 'payload': payload if not error else {},
            'rejection': error, 'started': started, 'completed_at': datetime.now(UTC).isoformat()}
        return {'tool_result_envelopes': {binding['operation_id']: envelope}}
    return execute


def accept_results(state):
    """The single root writer admits a result once, before evidence synthesis."""
    accepted = dict(state.get('accepted_tool_operations') or {})
    updates: dict[str, Any] = {key: [] for key in ('collected_evidence','tool_histories','node_outcomes','agent_trace','pending_approvals')}
    acknowledgements, decisions = {}, []
    for operation, envelope in (state.get('tool_result_envelopes') or {}).items():
        if 'payload' not in envelope:
            continue
        binding = envelope.get('binding') or {}
        acknowledgements[operation] = {'binding': binding, 'consumed': True}
        if operation in accepted:
            decisions.append({'operation_id': operation, 'status': 'duplicate_ignored'})
            continue
        expected = (state.get('tool_handoffs') or {}).get(binding.get('node_id'))
        error = 'unrequested_tool_result' if not expected else result_binding_error(expected, binding, state.get('plan_manifest') or {})
        error = error or envelope.get('rejection')
        payload = envelope.get('payload') or {}
        histories = payload.get('tool_histories') or []
        call_count = sum(max(1,sum(int(item.get('call_count') or 0) for item in (call.get('safety_json') or {}).get('channel_attempts',[])))
            for history in histories for call in history.get('tool_calls',[]))
        if expected and call_count > expected['call_allowance']:
            error = error or 'tool_call_allowance_exceeded'
        if error:
            # No evidence from stale/unknown work; only an accounting tombstone.
            reserved = binding.get('call_allowance', 0) if envelope.get('started') else 0
            if reserved:
                updates['tool_histories'].append({'agent_type': binding.get('node_type'), 'tool_calls': [{
                    'call_id': 'unknown-'+operation, 'agent_type': binding.get('node_type'), 'tool_name': 'bound_tool_result',
                    'status': 'error', 'error': error, 'tokens_used': 0, 'cost_usd': 0,
                    'safety_json': {'operation_id': operation, 'result_unknown': True, 'cost_status': 'unknown_not_free',
                        'channel_attempts': [{'call_count': reserved}]}}]})
            # An old operation must not change a new plan's node with the same ID.
            if expected and expected.get('operation_id') == operation:
                updates['node_outcomes'].append({'node_id':binding['node_id'], 'status':'terminal_error',
                    'error_category':error, 'error_message':'工具结果未获接纳，已保留缺口和预算记录。',
                    'retry_count':binding.get('attempt',0), 'result_count':0, 'operation_id':operation})
        else:
            for history in histories:
                for call in history.get('tool_calls',[]):
                    call.setdefault('safety_json', {})['operation_id'] = operation
            for key in updates:
                updates[key].extend(deepcopy(payload.get(key) or []))
            for row in updates['node_outcomes']:
                if row.get('node_id') == binding['node_id']:
                    row['operation_id'], row['plan_version'] = operation, binding['plan_version']
        accepted[operation] = {'status': 'rejected' if error else 'accepted', 'reason': error,
            'node_id':binding.get('node_id'), 'plan_version':binding.get('plan_version')}
        decisions.append({'operation_id': operation, **accepted[operation]})
    updates.update(accepted_tool_operations=accepted, tool_result_envelopes=acknowledgements)
    if decisions:
        updates['agent_trace'].append({'agent':'tool_handoff','event_type':'result_acceptance',
            'content':'根流程已校验工具结果归属、版本、期限与重复交付。', 'decisions':decisions})
    return updates
