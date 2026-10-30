"""Deterministic plan structure, handoff and bounded-iteration contracts.

No agent, scheduler, network client, persistence owner or permission issuer lives
here. The existing root graph must enforce and persist the returned decisions.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field
from app.research_scope import ScopeRecord
from app.query_understanding import identity
from app.graph.state import DAGDefinition, PlanEdge, PlanNode, StepStatus

VERSION = 'adrs-planning-control-v1'
TOOLS = frozenset({'search', 'browser', 'rag', 'mcp'})
ROOT_STAGES = frozenset({'analyst', 'reflection', 'report'})
CONDITIONS = frozenset({'always', 'evidence_found', 'no_evidence'})


class PlanningPolicy(ScopeRecord):
    strategy: Literal['hybrid', 'fixed', 'dynamic'] = 'hybrid'
    max_plan_nodes: int = Field(default=64, ge=2, le=128)
    max_parallel: int = Field(default=3, ge=1, le=8)
    max_replans: int | None = Field(default=None, ge=0, le=5)
    no_gain_rounds: int = Field(default=2, ge=1, le=5)
    autonomy: Literal['bounded', 'single_pass'] = 'bounded'
    stage_context_chars: int = Field(default=16000, ge=2000, le=32000)


class PlanningError(ValueError):
    def __init__(self, category: str, detail: str = ''):
        super().__init__(category)
        self.category, self.detail = category, detail


def rebind_checkpoint_plan(state,execution_id,previous_execution_id,*,recovery_predecessor=None):
    """Move a trusted restored plan to a new execution without resetting its DAG."""
    manifest=deepcopy(state.get('plan_manifest') or {})
    if not manifest:return
    allowed={str(previous_execution_id)}
    if recovery_predecessor:allowed.add(str(recovery_predecessor))
    if manifest.get('task_id')!=state.get('task_id') or manifest.get('execution_id') not in allowed:
        raise PlanningError('resume_plan_binding_unavailable')
    previous=manifest.pop('plan_version',None)
    manifest.update(execution_id=str(execution_id),parent_plan_version=previous,
        revision=int(manifest.get('revision') or 0)+1,reason='execution_resumed_dag_preserved',
        adjustments=[{'reason':'execution_resumed_dag_preserved','previous_execution_id':manifest['execution_id'],
            'execution_id':str(execution_id),'root_budget_changed':False}])
    manifest['plan_version']=identity(manifest)
    state['plan_manifest']=manifest
    state['plan_history']=[*(state.get('plan_history') or []),deepcopy(manifest)]
    frame=state.get('retained_synthesis')
    if isinstance(frame,dict) and frame:
        root=state.get('session') or {}
        if (frame.get('execution_id') not in allowed or frame.get('task_id')!=str(state.get('task_id'))
                or frame.get('owner_id')!=str(root.get('owner_id'))):
            raise PlanningError('resume_retained_analysis_binding_unavailable')
        frame['execution_id']=str(execution_id)


def dependency_batches(nodes: list[PlanNode]) -> list[list[str]]:
    """One authority for topological order; fail on unknown/duplicate/cyclic IDs."""
    ids = [node.node_id for node in nodes]
    if len(set(ids)) != len(ids):
        raise PlanningError('plan_duplicate_node')
    known = set(ids)
    for node in nodes:
        if node.node_id in node.depends_on:
            raise PlanningError('plan_dependency_cycle', node.node_id)
        if len(set(node.depends_on)) != len(node.depends_on):
            raise PlanningError('plan_duplicate_dependency', node.node_id)
        if not set(node.depends_on) <= known:
            raise PlanningError('plan_unknown_dependency', node.node_id)
    visited, batches = set(), []
    while len(visited) < len(nodes):
        batch = [node.node_id for node in nodes if node.node_id not in visited and set(node.depends_on) <= visited]
        if not batch:
            raise PlanningError('plan_dependency_cycle')
        batches.append(batch)
        visited.update(batch)
    return batches


def compile_plan(dag: DAGDefinition, *, task_id: str, execution_id: str | None,
        interpretation_id: str | None, revision: int, allowed_tools: set[str],
        policy: PlanningPolicy, budget: dict, reason: str) -> tuple[DAGDefinition, dict]:
    """Compile a *new* plan. Restored node statuses must not use this reset path."""
    dag = dag.model_copy(deep=True)
    if not dag.nodes or len(dag.nodes) > policy.max_plan_nodes:
        raise PlanningError('plan_node_limit')
    ids = [node.node_id for node in dag.nodes]
    if len(ids) != len(set(ids)):
        raise PlanningError('plan_duplicate_node')
    nodes = {node.node_id: node for node in dag.nodes}
    changes = []
    for edge in dag.edges:
        if edge.from_node not in nodes or edge.to_node not in nodes:
            raise PlanningError('plan_unknown_edge')
        if edge.condition and edge.condition not in CONDITIONS:
            raise PlanningError('plan_unsupported_condition')
        if edge.edge_type == 'conditional' and not edge.condition:
            raise PlanningError('plan_missing_condition')
        node = nodes[edge.to_node]
        if edge.from_node not in node.depends_on:
            node.depends_on.append(edge.from_node)
            changes.append({'node_id': node.node_id, 'reason': 'dependency_retained_from_explicit_edge'})
        if edge.condition:
            previous = getattr(node, 'condition', 'always')
            if previous not in {'always', edge.condition}:
                raise PlanningError('plan_condition_conflict', node.node_id)
            node.condition = edge.condition
    dependency_batches(dag.nodes)
    if len(dag.edges) > policy.max_plan_nodes * 8:
        raise PlanningError('plan_edge_limit')
    for node in dag.nodes:
        if not node.node_id or len(node.node_id) > 160 or not node.query.strip() or len(node.query) > 3000:
            raise PlanningError('plan_invalid_node_input', node.node_id)
        if node.node_type not in TOOLS | ROOT_STAGES:
            raise PlanningError('plan_unknown_node_type', node.node_id)
        if node.node_type in TOOLS and any(nodes[key].node_type in ROOT_STAGES for key in node.depends_on):
            raise PlanningError('plan_backward_stage_dependency', node.node_id)
        condition = getattr(node, 'condition', 'always')
        if condition not in CONDITIONS or condition != 'always' and not node.depends_on:
            raise PlanningError('plan_unsupported_condition', node.node_id)
        if node.node_type == 'browser':
            try:
                parsed = urlsplit(node.query.strip())
            except ValueError:
                raise PlanningError('plan_unsupported_browser_url', node.node_id) from None
            if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
                if parsed.scheme or node.query.lstrip().startswith(('/', '\\')):
                    raise PlanningError('plan_unsupported_browser_url', node.node_id)
                node.node_type = 'search'
                changes.append({'node_id': node.node_id, 'reason': 'text_discovery_request_requires_search_before_url_read'})
        node.status, node.result, node.retry_count = StepStatus.PENDING, None, 0
        node.waiting_approval, node.terminal_failure = False, False
        node.last_error, node.last_error_category = None, None
        node.max_retries = max(0, min(int(node.max_retries), 2))
        if node.node_type == 'mcp' and node.parallel:
            node.parallel = False
            changes.append({'node_id':node.node_id,'reason':'mcp_serial_until_trusted_resource_independence_is_declared'})
        remaining_seconds = max(0, float(budget.get('max_wall_clock_seconds', 300)) - float(budget.get('elapsed_wall_clock_seconds') or 0))
        node.timeout_seconds = max(1, int(min(max(1, node.timeout_seconds), remaining_seconds or 1)))
        if node.node_type in TOOLS and node.node_type not in allowed_tools:
            node.status, node.last_error_category = StepStatus.SKIPPED, 'tool_not_allowed'
            changes.append({'node_id': node.node_id, 'reason': 'task_and_skill_permission_intersection'})
        if node.node_type in TOOLS and (budget.get('hard_stop_reason') or remaining_seconds <= 0):
            node.status, node.last_error_category = StepStatus.SKIPPED, 'budget_exceeded'
            changes.append({'node_id': node.node_id, 'reason': budget.get('hard_stop_reason') or 'wall_clock_limit'})
    # Synthesis/review/rendering are root stages, not extra model-dispatched agents.
    tool_nodes = [node for node in dag.nodes if node.node_type in TOOLS]
    if not tool_nodes:
        raise PlanningError('plan_has_no_evidence_steps')
    if any(node.node_type in ROOT_STAGES for node in dag.nodes):
        changes.append({'reason': 'synthesis_review_and_rendering_owned_by_root_workflow'})
    sentinel_id = 'root_synthesis'
    while sentinel_id in nodes:
        sentinel_id += '_next'
    if len(tool_nodes) + 1 > policy.max_plan_nodes:
        raise PlanningError('plan_node_limit')
    dag.nodes = tool_nodes + [PlanNode(node_id=sentinel_id, node_type='analyst',
        query='按冻结问题综合已取得证据并保留缺口', depends_on=[node.node_id for node in tool_nodes], parallel=False)]
    dag.edges = [PlanEdge(from_node=dep, to_node=node.node_id) for node in dag.nodes for dep in node.depends_on]
    batches = dependency_batches(dag.nodes)
    rows = [{'node_id': node.node_id, 'node_type': node.node_type, 'query': node.query,
        'depends_on': list(node.depends_on), 'parallel': node.parallel,
        'condition': getattr(node, 'condition', 'always'), 'status': node.status.value,
        'purpose': {'search': '发现可核查线索', 'browser': '读取明确来源', 'rag': '补充当前授权资料',
            'mcp': '受控外部工具', 'analyst': '根流程综合、审核与交付'}[node.node_type]}
        for node in dag.nodes]
    manifest = {'schema_version': VERSION, 'task_id': task_id, 'execution_id': execution_id,
        'interpretation_id': interpretation_id, 'revision': revision, 'reason': reason,
        'strategy': policy.strategy, 'policy': policy.model_dump(mode='json'), 'steps': rows,
        'dependency_batches': batches, 'adjustments': changes,
        'state_owner': 'existing_root_graph_and_owner_bound_runtime_persistence',
        'budget_owner': 'same_root_task_budget_not_per_agent_refill',
        'sdk_boundary': 'standalone_cli_is_separate_run_not_nested_shared_orchestrator'}
    manifest['plan_version'] = identity(manifest)
    return dag, manifest


def condition_decision(node: PlanNode, completed: set[str], latest_outcomes: dict[str, dict]) -> str:
    if not set(node.depends_on) <= completed:
        return 'wait_for_dependencies'
    condition = getattr(node, 'condition', 'always')
    if condition == 'always':
        return 'run'
    if condition not in CONDITIONS or not node.depends_on:
        return 'unsupported_condition'
    found = any(int((latest_outcomes.get(key) or {}).get('result_count') or 0) > 0 for key in node.depends_on)
    return 'run' if found == (condition == 'evidence_found') else 'condition_not_met'


def tool_query_context(state:dict,node_type:str) -> dict:
    """Only frozen query data this tool consumes, never report/model context."""
    original=state.get('query_understanding') or {}
    slots=original.get('slots') or {}
    view={key:deepcopy(original[key]) for key in ('schema_version','interpretation_id') if key in original}
    view['slots']={'additional_constraints':slots.get('additional_constraints','')}
    if node_type=='search':
        followup=(original.get('research_strategy') or {}).get('source_followup')
        if followup:view['source_followup']=deepcopy(followup)
        view['slots'].update({key:deepcopy(slots[key]) for key in ('entities','time_window') if key in slots})
        if 'query_rewriting' in original:view['query_rewriting']=deepcopy(original['query_rewriting'])
    if node_type=='rag':
        view.update({key:deepcopy(original[key]) for key in ('internal_filter','internal_retrieval') if key in original})
    if node_type in {'search','rag'}:
        view.update({key:deepcopy(original[key]) for key in ('candidate_fusion','query_type') if key in original})
    if node_type in {'search','browser'} and 'temporal' in original:
        view['temporal']=deepcopy(original['temporal'])
    if node_type in {'search','browser'} and 'external_evidence' in original:
        view['external_evidence']=deepcopy(original['external_evidence'])
    if 'data_governance' in original:view['data_governance']=deepcopy(original['data_governance'])
    if node_type in {'search','browser','mcp'}:
        from app.data_governance import network_context
        view['network_context']=deepcopy(original.get('network_context') or network_context(state))
    return view


def make_handoff(state: dict, node: PlanNode, *, call_allowance: int, seconds: float) -> dict:
    manifest = state.get('plan_manifest') or {}
    if not manifest.get('plan_version'):
        raise PlanningError('plan_manifest_required')
    owner = state.get('session', {}).get('owner_id')
    if not owner or manifest.get('execution_id') != state.get('session', {}).get('execution_id'):
        raise PlanningError('plan_execution_binding_conflict')
    binding = {'task_id': state['task_id'], 'owner_id': owner,
        'execution_id': manifest['execution_id'], 'plan_version': manifest['plan_version'],
        'plan_revision': manifest['revision'], 'node_id': node.node_id, 'node_type': node.node_type,
        'query_context_identity':identity(tool_query_context(state,node.node_type)),
        'request_identity': identity({'query': node.query, 'depends_on': node.depends_on,
            'condition': getattr(node, 'condition', 'always')}), 'attempt': node.retry_count}
    binding['authorization_identity'] = identity([{key: item.get(key) for key in
        ('approval_id','status','node_id','bound_query','revision_count')} for item in state.get('approval_decisions', [])
        if item.get('node_id') == node.node_id])
    operation_id = identity(binding)
    return {**binding, 'operation_id': operation_id, 'schema_version': VERSION,
        'call_allowance': max(0, call_allowance), 'expires_at': (datetime.now(UTC) + timedelta(seconds=max(0, seconds))).isoformat(),
        'evidence_refs': list(node.evidence_ids), 'authority': 'trusted_root_dispatch_only'}


def result_binding_error(handoff: dict, result: dict, manifest: dict) -> str | None:
    if manifest.get('plan_version') != handoff.get('plan_version') or manifest.get('execution_id') != handoff.get('execution_id'):
        return 'stale_plan_result'
    for key in ('schema_version', 'task_id', 'owner_id', 'execution_id', 'plan_version', 'plan_revision',
            'node_id', 'node_type', 'request_identity', 'query_context_identity', 'authorization_identity', 'operation_id', 'attempt'):
        if result.get(key) != handoff.get(key):
            return 'result_binding_conflict'
    try:
        expires = datetime.fromisoformat(handoff['expires_at'])
        if expires.tzinfo is None or expires <= datetime.now(UTC):
            return 'result_lease_expired'
    except (KeyError, ValueError, TypeError):
        return 'invalid_result_lease'
    return None


def retained_evidence_version(state: dict) -> str:
    # Content/version identity measures newly retained material, not truth or
    # relevance. A new random evidence UUID alone must not reset no-gain state.
    records = []
    for item in state.get('collected_evidence', []):
        metadata = item.get('metadata') or {}
        acquisition = item.get('acquisition') or {}
        records.append({'source_url': item.get('source_url'), 'source_type':item.get('source_type'),
            'source_document_id': acquisition.get('source_document_id',metadata.get('source_document_id')),
            'parse_version_id': acquisition.get('parse_version_id',metadata.get('parse_version_id')),
            'source_access_revision':acquisition.get('source_access_revision'),
            'source_content_version':acquisition.get('source_content_version'),
            'index_generation_id':acquisition.get('index_generation_id'),
            'source_etag':acquisition.get('source_etag'),
            'source_last_modified':acquisition.get('source_last_modified'),
            'parse_profile':acquisition.get('parse_profile'),
            'data_class':(acquisition.get('data_governance') or {}).get('data_class'),
            'coverage':acquisition.get('coverage'), 'content': item.get('content', '')})
    return identity({'version':'adrs-retained-material-v2','records':sorted({identity(record) for record in records})})


def iteration_decision(state: dict, policy: PlanningPolicy) -> dict:
    budget, verification = state.get('budget_state') or {}, state.get('verification') or {}
    prior = deepcopy(state.get('iteration_control') or {})
    observed = retained_evidence_version(state)
    count = int(state.get('revision_count') or 0)
    no_gain = int(prior.get('no_gain_rounds') or 0)
    if prior.get('evidence_version') != observed:
        no_gain = 0
    elif prior.get('revision_count') != count:
        no_gain += 1
    limit = int(state.get('session', {}).get('max_revisions', 3))
    if policy.max_replans is not None:
        limit = min(limit, policy.max_replans)
    gaps = []
    if verification.get('hallucinated_claims'):
        gaps.append('unsupported_claims')
    if verification.get('conflicts'):
        gaps.append('evidence_conflicts')
    if (int(verification.get('total_claims') or 0) > int(verification.get('verified_claims') or 0)
            and str(verification.get('revision_focus') or '').strip()):
        gaps.append('unverified_claims_with_revision_focus')
    # Locator/census caveats remain visible, but cannot by themselves request
    # another full acquisition/analysis cycle. Reflection must identify an
    # actual unsupported/conflicting claim or a specific unfinished claim focus.
    coverage_notes=list((state.get('organization_result') or {}).get('gaps') or [])
    context=(state.get('organization_result') or {}).get('analyst_context') or {}
    phase_contexts=context.get('phases') or [context]
    context_gaps=[{'phase_id':item.get('phase_id'),'question':(item.get('question_evidence') or {}).get('question'),
        'gaps':(item.get('question_evidence') or {}).get('gaps',[]),
        'next_action':(item.get('question_evidence') or {}).get('next_action')}
        for item in phase_contexts if isinstance(item,dict) and (item.get('question_evidence') or {}).get('gaps')]
    if budget.get('hard_stop_reason'):
        action, reason = 'report', budget['hard_stop_reason']
    elif state.get('pending_approvals'):
        action, reason = 'pause', 'human_authorization_required'
    elif policy.autonomy == 'single_pass':
        action, reason = 'report', 'single_pass_selected'
    elif count >= limit:
        action, reason = 'report', 'revision_limit'
    elif no_gain >= policy.no_gain_rounds:
        action, reason = 'report', 'no_new_retained_material'
    elif not state.get('revision_needed'):
        action, reason = 'report', 'no_requested_revision_not_a_truth_certificate'
    elif gaps:
        action, reason = 'replan', 'specific_evidence_gap'
    else:
        action, reason = 'report', 'no_structured_evidence_gap_manual_review_available'
    return {'schema_version': VERSION, 'action': action, 'reason': reason, 'gap_reasons': gaps,
        'coverage_notes':coverage_notes,
        'context_gaps':context_gaps,'context_gap_semantics':'selection_gaps_require_retained_text_rereading_not_automatic_external_replan_or_truth_verdict',
        'evidence_version': observed, 'no_gain_rounds': no_gain, 'revision_count': count, 'revision_limit': limit,
        'semantics': 'retained-material novelty is not semantic correctness; no confidence-only loop'}
