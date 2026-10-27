"""
LangGraph StateGraph compiler for the research workflow.

===============================================================
五大核心主题在编译器中的映射
===============================================================

主题 1 - Autonomous Research Workflow:
    - compile_research_graph() 构建完整工作流
    - 从 START → Planner → DAG执行 → Analyst → Reflection → Report → END
    - 整个工作流由 LangGraph 编排，无需人工干预

主题 2 - Research DAG Generation:
    - planner_node 调用 PlannerAgent 生成 DAG
    - dag_node 执行 DAG（按拓扑序执行可并行节点）
    - after_planner 分发 DAG 节点到对应的工具 Agent
    - DAG 执行顺序由 get_executable_order() 计算

主题 3 - Tool-driven Multi-Agent Collaboration:
    - 每个节点执行前/后记录 ToolCallRecord
    - tool_histories 存储每个 Agent 的工具调用历史
    - send_node() 工具调用封装器

主题 4 - Long-running Stateful Agent:
    - PostgresSaver checkpointer 保存状态快照
    - session 字段存储会话元数据
    - revision_count 追踪重规划次数

主题 5 - Self-Reflection & Verification:
    - reflection_node 调用 ReflectionAgent
    - verification_result 决定是否需要重规划
    - 重规划循环最多 3 次

===============================================================
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any

from langgraph.constants import END, START, Send
from langgraph.graph import StateGraph

from app.config import get_settings
from app.llm_budget import ModelTokenBudget, TokenBudgetExceeded
from app.organization_runtime import organization_query, organization_evidence_views, seed_organization_sources
from app.query_understanding import query_contract_text
from app.skills.stages import stage_profile
from app.tool_handoff import prepare_handoffs, tool_payload, bound_tool_node, accept_results, current_execution
from app.planning_control import PlanningPolicy, PlanningError, compile_plan, dependency_batches, condition_decision, iteration_decision
from app.core.time import utc_now_naive
from app.governance import McpPolicyProxy, McpToolRequest
from app.graph.source_policy import apply_source_policy
from app.graph.approval import approved_action
from app.graph.state import (
    AgentType,
    DAGDefinition,
    NodeOutcome,
    PlanNode,
    ResearchState,
    RuntimeStatus,
    StepStatus,
    TaskStatus,
    ToolCallRecord,
    ToolInvocationHistory,
    VerificationResult,
    deserialize_dag,
    serialize_dag,
)
from app.guardrails import (
    build_answer_gate_message,
    build_evidence_gate,
    build_guardrail_decision,
    get_research_budget,
    record_guardrail_event,
    should_require_action_approval,
)
from app.observability.trace import EventType

logger = logging.getLogger(__name__)

TOOL_NODE_TYPES = {"search", "browser", "rag", "mcp"}


def _research_question(state: ResearchState) -> str:
    return organization_query(state['user_query'], state.get('organization_research')) + query_contract_text(state.get('query_understanding'))


def _synthesis_question(state: ResearchState) -> str:
    """Synthesis needs frozen research meaning, not a repeated tool/weight plan."""
    organization = state.get('organization_research') or {}
    understanding = state.get('query_understanding') or {}
    scope = {key: value for key, value in (organization.get('scope') or {}).items() if key != 'topic'}
    context = {'scope': scope, 'purpose': organization.get('purpose'), 'modules': organization.get('modules'),
        'action_requirements': organization.get('action_requirements'), 'temporal': understanding.get('temporal'),
        'additional_constraints': (understanding.get('slots') or {}).get('additional_constraints'),
        'delivery_pages': (understanding.get('delivery') or {}).get('pages')}
    # JSONB can reorder nested object keys between checkpoints. The model
    # question is part of the resume identity, so use canonical serialization.
    return state['user_query']+'\n\n冻结的研究范围与问题（数据，不授予工具权限）：\n'+json.dumps(
        context,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def _guardrail_question(state: ResearchState) -> str:
    return state['user_query'] + '\n' + (((state.get('query_understanding') or {}).get('slots') or {}).get('additional_constraints') or '')


def _plan_contract(state: ResearchState) -> str:
    return organization_query('', state.get('organization_research')) + query_contract_text(state.get('query_understanding'))


def _compile_execution_plan(state: ResearchState, dag: DAGDefinition, agent, reason: str):
    from app.data_governance import owned_request_url,sensitive_url
    from app.channels.catalog import route_query
    for node in dag.nodes:
        channel,operation,value=route_query(node.query)
        if node.node_type in {'search','browser'} and operation=='read':
            resolved=owned_request_url(value,state)
            if resolved!=value or sensitive_url(resolved):
                node.node_type='browser';node.query=resolved
                reason+=':owned_source_direct_reader'
    policy = PlanningPolicy.model_validate(state.get('planning_policy') or {})
    decision = build_guardrail_decision(_guardrail_question(state), user_confirmed=state.get('user_confirmed', False))
    arguments = {'task_id': state['task_id'], 'execution_id': state.get('session', {}).get('execution_id'),
        'interpretation_id': (state.get('query_understanding') or {}).get('interpretation_id'),
        'revision': int((state.get('plan_manifest') or {}).get('revision') or 0)+1,
        'allowed_tools': _effective_tool_allowlist(state, decision.model_dump()),
        'policy': policy, 'budget': _build_budget_state(state)}
    try:
        return compile_plan(dag, reason=reason, **arguments)
    except PlanningError as error:
        if policy.strategy == 'fixed' or 'declared_seed_only_fixed_workflow' in reason:
            raise
        fallback = agent._fixed_research_dag(state['user_query'], state.get('organization_research'))
        fallback = apply_source_policy(fallback, state['user_query'], use_internal_docs=bool(state.get('use_internal_docs')))
        fallback = seed_organization_sources(fallback, state.get('organization_research'))
        return compile_plan(fallback, reason='fixed_after_invalid_plan:'+error.category, **arguments)


def _skill_context(state: ResearchState) -> dict[str, Any]:
    return dict(state.get("skill_context") or state.get("session", {}).get("skill_context") or {})


def _skill_prompt(state: ResearchState, stage: str) -> str:
    context = _skill_context(state)
    profile = stage_profile(context.get('stage_compilation'), stage)
    if profile is not None:
        return profile['prompt']
    parts: list[str] = []
    prompt_sections = context.get("effective_prompt_sections") or {}
    for key in ("overview", "prompt", "constraints"):
        value = prompt_sections.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(f"{key.capitalize()}:\n{value.strip()}")
    return "\n\n".join(parts).strip()


def _agent_skill_hints(state: ResearchState, agent_name: str) -> list[str]:
    context = _skill_context(state)
    profile = stage_profile(context.get('stage_compilation'), agent_name)
    if profile is not None:
        return profile['agent_hints']
    hints = (context.get("effective_agent_hints") or {}).get(agent_name) or []
    return [item for item in hints if isinstance(item, str) and item.strip()]


def _effective_tool_allowlist(state: ResearchState, decision: dict[str, Any]) -> set[str]:
    skill_tools = set(_skill_context(state).get("effective_tool_allowlist") or [])
    decision_tools = set(decision.get("enabled_tools", ["search", "browser", "rag"]))
    if not state.get("use_internal_docs", False):
        decision_tools.discard("rag")
    compilation = _skill_context(state).get('stage_compilation')
    if compilation is not None:
        return decision_tools & set(compilation.get('dispatch_tools', [])) if compilation.get('ready') else set()
    if skill_tools:
        return decision_tools.intersection(skill_tools)
    return decision_tools


def _research_budget(state: ResearchState) -> dict[str, int | float]:
    return get_research_budget(state.get("output_length") or state.get("session", {}).get("output_length"))


def _build_budget_state(state: ResearchState) -> dict[str, Any]:
    """Compute session-level budget usage and breaker status from runtime state."""
    configured = dict(_research_budget(state))
    existing_budget = state.get("budget_state") or {}
    for key in (
        "max_total_tokens",
        "max_cost_usd",
        "max_tool_calls",
        "max_wall_clock_seconds",
        "budget_profile",
        "estimated",
        "budget_policy_version",
        "audit_token_reserve",
        "report_token_reserve",
        "audit_seconds_reserve",
    ):
        if key in existing_budget and existing_budget[key] is not None:
            configured[key] = existing_budget[key]
    configured['max_retries_per_tool'] = _tool_retry_limit(
        existing_budget, configured, state.get('failure_memory'))
    if 'max_total_tokens' in existing_budget and existing_budget.get('budget_policy_version',1)==1:
        # Old roots retain their original envelope and reservation policy.
        # A new profile must never enlarge or re-time an existing task.
        configured.update(budget_policy_version=1,
            audit_token_reserve=min(12000,int(configured['max_total_tokens'])//5),
            report_token_reserve=min(12000,int(configured['max_total_tokens'])//5),
            audit_seconds_reserve=min(90,float(configured['max_wall_clock_seconds'])*.2))
    tool_histories = [
        history for history in state.get("tool_histories", [])
        if isinstance(history, dict)
    ]
    tool_calls = [
        call
        for history in tool_histories
        for call in history.get("tool_calls", [])
        if isinstance(call, dict)
    ]
    model_usage = existing_budget.get('llm_usage') or []
    model_tokens = sum(int(row.get('total_tokens') or 0) for row in model_usage)
    legacy_tokens = int(existing_budget.get('legacy_unattributed_tokens',max(0,int(existing_budget.get('used_total_tokens') or 0)-model_tokens)))
    used_total_tokens = sum(int(call.get("tokens_used") or 0) for call in tool_calls) + model_tokens + legacy_tokens
    used_cost_usd = round(sum(float(call.get("cost_usd") or 0.0) for call in tool_calls) + sum(float(row.get('cost_usd') or 0) for row in model_usage), 6)
    raw_tool_counts={call['call_id']:max(1,sum(int(a.get('call_count',0)) for a in (call.get('safety_json') or {}).get('channel_attempts',[])))
        for call in tool_calls if call.get('call_id')}
    previous_tool_counts=dict(existing_budget.get('tool_call_counts') or raw_tool_counts)
    tool_call_counts=dict(previous_tool_counts)
    for key,count in raw_tool_counts.items():tool_call_counts[key]=max(tool_call_counts.get(key,0),count)
    legacy_tool_calls=max(0,int(existing_budget.get('used_tool_calls') or 0)-sum(previous_tool_counts.values()))
    used_tool_calls=legacy_tool_calls+sum(tool_call_counts.values())
    if existing_budget.get("used_total_tokens"):
        used_total_tokens = max(used_total_tokens, int(existing_budget.get("used_total_tokens") or 0))
    if existing_budget.get("used_cost_usd"):
        used_cost_usd = max(used_cost_usd, float(existing_budget.get("used_cost_usd") or 0.0))
    started_at = state.get("created_at") or state.get("session", {}).get("created_at")
    elapsed_wall_clock_seconds = 0
    if started_at:
        try:
            elapsed_wall_clock_seconds = max(
                0,
                int((utc_now_naive() - datetime.fromisoformat(started_at)).total_seconds()),
            )
        except ValueError:
            elapsed_wall_clock_seconds = 0

    hard_stop_reason = None
    for key, reason in (
        ("max_tool_calls", "tool_call_limit"),
        ("max_total_tokens", "token_limit"),
        ("max_cost_usd", "cost_limit"),
        ("max_wall_clock_seconds", "wall_clock_limit"),
    ):
        limit = configured.get(key)
        if limit is None:
            continue
        current = {
            "max_tool_calls": used_tool_calls,
            "max_total_tokens": used_total_tokens,
            "max_cost_usd": used_cost_usd,
            "max_wall_clock_seconds": elapsed_wall_clock_seconds,
        }[key]
        if current >= limit:
            hard_stop_reason = reason
            break

    warning = False
    if not hard_stop_reason:
        warning_checks = (
            configured.get("max_tool_calls") and used_tool_calls >= int(configured["max_tool_calls"] * 0.8),
            configured.get("max_total_tokens") and used_total_tokens >= int(configured["max_total_tokens"] * 0.8),
            configured.get("max_cost_usd") and used_cost_usd >= float(configured["max_cost_usd"]) * 0.8,
            configured.get("max_wall_clock_seconds") and elapsed_wall_clock_seconds >= int(configured["max_wall_clock_seconds"] * 0.8),
        )
        warning = any(bool(check) for check in warning_checks)

    return {
        **existing_budget,
        **configured,
        "used_total_tokens": used_total_tokens,
        'legacy_unattributed_tokens':legacy_tokens,
        'audit_token_reserve':configured['audit_token_reserve'],
        'report_token_reserve':configured['report_token_reserve'],
        'token_usage_estimated':bool(existing_budget.get('token_usage_estimated')) or legacy_tokens > 0
            or any(row.get('estimated') for row in model_usage)
            or any(row.get('estimated') or row.get('status')=='inflight' for row in existing_budget.get('model_requests') or []),
        "used_cost_usd": used_cost_usd,
        "used_tool_calls": used_tool_calls,
        'tool_call_counts':tool_call_counts,
        "elapsed_wall_clock_seconds": elapsed_wall_clock_seconds,
        "hard_stop_reason": hard_stop_reason,
        "warning": warning,
    }


def _apply_budget_breaker(
    dag: DAGDefinition,
    budget_state: dict[str, Any],
) -> tuple[DAGDefinition, list[str]]:
    """Skip remaining retrievable nodes once hard budget limits are reached."""
    if not budget_state.get("hard_stop_reason"):
        return dag, []
    skipped_nodes: list[str] = []
    for node in dag.nodes:
        if node.node_type not in TOOL_NODE_TYPES:
            continue
        if node.status == StepStatus.PENDING:
            node.status = StepStatus.SKIPPED
            node.last_error = budget_state["hard_stop_reason"]
            node.last_error_category = "budget_exceeded"
            skipped_nodes.append(node.node_id)
    return dag, skipped_nodes


def _channel_budget(state: ResearchState, local_histories: list[dict]) -> tuple[int, float]:
    usage = _build_budget_state({**state, "tool_histories": [*state.get("tool_histories", []), *local_histories]})
    local_usage = sum(max(1, sum(int(a.get("call_count", 0)) for a in (call.get("safety_json") or {}).get("channel_attempts", []))) for history in local_histories for call in history.get("tool_calls", []))
    remaining = max(0, int(usage["max_tool_calls"])-int(usage["used_tool_calls"]))
    if "channel_call_allowance" in state:
        remaining = min(remaining, max(0, int(state["channel_call_allowance"])-local_usage))
    return (remaining,
            max(0, min(90, float(usage["max_wall_clock_seconds"])-float(usage["elapsed_wall_clock_seconds"]))))


def _apply_llm_usage_to_state(
    state: ResearchState,
    agent_name: str,
    usage: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Merge LLM usage into session + budget state and emit a traceable summary."""
    session = dict(state.get("session", {}))
    budget_state = _build_budget_state(state)
    if not usage:
        session['total_tokens'] = budget_state['used_total_tokens']
        return session, budget_state

    session["total_tokens"] = int(budget_state.get("used_total_tokens", 0) or 0) + int(usage.get("total_tokens", 0) or 0)
    session["total_cost_usd"] = round(
        float(session.get("total_cost_usd", 0.0) or 0.0) + float(usage.get("cost_usd", 0.0) or 0.0),
        6,
    )
    budget_state["used_total_tokens"] = int(budget_state.get("used_total_tokens", 0) or 0) + int(usage.get("total_tokens", 0) or 0)
    budget_state["used_cost_usd"] = round(
        float(budget_state.get("used_cost_usd", 0.0) or 0.0) + float(usage.get("cost_usd", 0.0) or 0.0),
        6,
    )
    has_model_activity = bool(usage.get('model_requests')) or int(usage.get('total_tokens') or 0) > 0
    if has_model_activity:
        budget_state['llm_usage'] = [*(budget_state.get('llm_usage') or []), {
            "agent": agent_name,
            **usage,
        }]
    if usage.get('model_requests'):
        budget_state['model_requests'] = [*(budget_state.get('model_requests') or []),
            *[{**row,'agent':agent_name} for row in usage['model_requests']]]
    if usage.get('capability_upgrades'):
        upgrades=[*(budget_state.get('capability_upgrades') or []),*usage['capability_upgrades']]
        budget_state['capability_upgrades']=list({item['upgrade_id']:item for item in upgrades}.values())
    if usage.get('routing_decisions'):
        budget_state['routing_decisions']=[*(budget_state.get('routing_decisions') or []),
            *usage['routing_decisions']][-64:]
    if usage.get('phase_events'):
        budget_state['phase_events']=[*(budget_state.get('phase_events') or []),*usage['phase_events']][-64:]
    if usage.get('data_governance_events'):
        budget_state['data_governance_events']=[*(budget_state.get('data_governance_events') or []),*usage['data_governance_events']][-64:]
    if has_model_activity and usage.get('cost_known') is False:
        budget_state['cost_status'] = 'unknown_price_or_usage'
    budget_state = _build_budget_state({**state,'budget_state':budget_state})
    return session, budget_state


def _stage_model_budget(state: ResearchState, stage: str) -> ModelTokenBudget:
    root = _build_budget_state(state)
    from app.adaptive_budget import stage_allocation
    allocation = stage_allocation(state,root,stage)
    remaining = allocation['root_remaining'] if allocation else max(0,int(root['max_total_tokens'])-int(root['used_total_tokens']))
    audit = allocation['audit_hold'] if allocation else min(int(root['max_total_tokens']),max(0,int(root['audit_token_reserve'])))
    report = allocation['report_hold'] if allocation else min(max(0,int(root['max_total_tokens'])-audit),max(0,int(root['report_token_reserve'])))
    seconds = max(0,float(root['max_wall_clock_seconds'])-float(root['elapsed_wall_clock_seconds']))
    audit_seconds = min(float(root['max_wall_clock_seconds']),max(0,float(root['audit_seconds_reserve'])))
    meter=ModelTokenBudget(remaining if stage == 'report' else max(0,remaining-audit-report),
        audit_reserve=audit if stage == 'report' else 0,
        deadline=time.monotonic()+max(0,seconds-(0 if stage == 'report' else audit_seconds)),
        audit_seconds=audit_seconds if stage == 'report' else 0)
    if allocation:
        meter.phase_events.append({'phase':'stage_allocation',**allocation})
    meter.upgrade_history=list(root.get('capability_upgrades') or [])
    from app.data_governance import effective_context
    meter.data_governance=effective_context(state)
    meter.stage=stage
    meter.skill_tracking=True
    compilation=_skill_context(state).get('stage_compilation') or {}
    profile_stage='planner' if stage=='replan' else stage
    profile=(compilation.get('profiles') or {}).get(profile_stage) or {}
    if compilation.get('ready') and profile.get('ready') and profile.get('prompt') and compilation.get('arbitration_policy'):
        from app.security.prompt_security import research_method_context
        methods=[{key:entry.get(key) for key in ('skill_id','version')}
                 for entry in profile.get('entries',[]) if entry.get('has_model_content')]
        if methods:
            meter.skill_guidance=True
            meter.skill_packet={'stage':profile_stage,'compilation_id':compilation.get('compilation_id'),
                'methods':methods,'marker':research_method_context(profile['prompt'],guidance=True)}
    return meter


def _agent_model_usage(agent):
    meter = getattr(agent,'request_budget',None)
    return meter.usage() if meter is not None and (meter.calls or meter.routing_decisions or meter.phase_events or meter.data_events) else agent.last_usage


def _model_budget_pause(state, agent, stage, error, *, report=None, citations=None):
    from app.db.report_delivery import report_binding
    from app.disclosure import projection,redact_text,VERSION as disclosure_version
    session,budget = _apply_llm_usage_to_state(state,stage,_agent_model_usage(agent))
    budget['model_stop_reason'] = error.reason
    budget_stop=error.reason in {'token_budget_exhausted','model_time_reservation_exhausted',
        'provider_usage_exceeded_reservation','final_audit_budget_exhausted','root_model_admission_denied'}
    if budget_stop:budget['hard_stop_reason'] = budget.get('hard_stop_reason') or error.reason
    session.update(status='paused',updated_at=utc_now_naive().isoformat())
    recoverable=stage=='analyst' and error.reason in {'analysis_output_incomplete','analysis_provider_unavailable','model_output_limit','insufficient_context_budget'}
    route_error=error.reason.startswith('model_rout') or error.reason in {'no_eligible_model_route',
        'model_endpoint_changed','model_context_capability_exceeded'}
    data_error=any(value in error.reason for value in ('data_class','access_credentials','data_governance','report_disclosure'))
    result = {'session':session,'budget_state':budget,'status':'paused',
        'runtime_status':'analysis_paused' if recoverable else 'budget_exhausted' if budget_stop
            else 'report_paused' if stage=='report' else 'analysis_paused',
        'review_status':{**(state.get('review_status') or {}),'blocked':True,'reason':error.reason,
            'output_stage':stage,'report_binding':report_binding(state) if stage=='report' else None,
            'report_payload_kind':('report' if report is not None else 'partial_response') if stage=='report' else None,
            'last_error_category':'data_governance' if data_error else 'model_routing' if route_error else 'budget_exceeded' if budget_stop else 'report_quality' if stage=='report' else 'analysis_incomplete',
            'final_report_audit':getattr(agent,'last_audit',None),
            'partial_model_response':redact_text(getattr(agent,'last_partial_response',None))},
        'agent_trace':[*getattr(agent,'recovery_events',[]),{'agent':stage,'event_type':'agent_error',
            'content':'资料外传范围或访问凭据校验未满足，原材料和用量已保留；请查看研究记录。' if data_error
                else '当前阶段没有满足配置与资料许可的模型，已保留任务；请查看模型配置及研究记录。' if route_error
                else '分析响应未完成，已保留阶段结果，可在原额度与期限内继续。' if recoverable
                else '研究已暂停；已取得资料、阶段结果和用量记录保留。'}]}
    if getattr(agent,'last_workflow',None):result['analysis_workflow']=agent.last_workflow
    result['evidence_access_gaps']=state.get('evidence_access_gaps',[])
    if getattr(agent,'last_context_manifest',None):
        result['organization_result']={**(state.get('organization_result') or {}),
            stage+'_context':agent.last_context_manifest,
            **({'module_report':agent.last_module_report} if getattr(agent,'last_module_report',None) else {})}
    if report is not None:
        safe_report=redact_text(report)
        result.update(final_report=safe_report,citations=projection([item.model_dump() for item in citations or []]))
        if safe_report!=report:
            result['review_status']['disclosure']={'version':disclosure_version,'blocked':True,'requires_reaudit':True}
            result['review_status']['final_report_audit']={**projection(getattr(agent,'last_audit',None) or {}),
                'needs_review':True,'disclosure_requires_revision':True}
    if getattr(agent,'last_writing_plan',None):
        result['organization_result']={**(result.get('organization_result') or state.get('organization_result') or {}),
            'writing_plan':agent.last_writing_plan}
    from app.research_diagnostics import diagnose_stop
    diagnosis=diagnose_stop({**state,**result})
    result['review_status']['pause_diagnosis']=diagnosis
    if diagnosis:result['agent_trace'][-1]['content']=diagnosis['summary']
    return result


def _node_identifier(node: PlanNode) -> str:
    return f"{node.node_type}:{node.query.strip().lower()}"


def _tool_retry_limit(budget: dict, defaults: dict, failure_memory: dict | None = None) -> int:
    """Retain an explicit zero and any known original-root retry envelope."""
    for source in (budget, failure_memory or {}, defaults):
        value = source.get('max_retries_per_tool')
        if value is not None:
            return max(0, int(value))
    return 2


def _build_failure_memory(state: ResearchState, dag: DAGDefinition) -> dict[str, Any]:
    """Summarize failures so retries and replanning can avoid repeating mistakes."""
    budget = dict(_research_budget(state))
    max_retries = _tool_retry_limit(state.get('budget_state') or {}, budget, state.get('failure_memory'))
    records: dict[str, dict[str, Any]] = {}
    repeated_terminal_nodes: list[str] = []

    for node in dag.nodes:
        if node.node_type not in TOOL_NODE_TYPES:
            continue
        key = _node_identifier(node)
        record = records.setdefault(key, {
            "node_type": node.node_type,
            "query": node.query,
            "last_error_category": None,
            "last_error": None,
            "retry_count": 0,
            "terminal_failure": False,
            "repeat_blocked": False,
            "next_retry_at": None,
            "backoff_seconds": 0,
        })
        previous_retry_count = int(record.get("retry_count") or 0)
        record["last_error_category"] = node.last_error_category or record["last_error_category"]
        record["last_error"] = node.last_error or record["last_error"]
        record["retry_count"] = max(previous_retry_count, int(node.retry_count or 0))
        record["terminal_failure"] = bool(record["terminal_failure"] or node.terminal_failure)
        attempted = node.status == StepStatus.FAILED or record['retry_count'] > 0
        exhausted = attempted and record['retry_count'] >= min(max_retries, max(0, int(node.max_retries)))
        if record['terminal_failure'] or exhausted:
            record['repeat_blocked'] = True
            record['next_retry_at'] = None
            record['backoff_seconds'] = 0
            repeated_terminal_nodes.append(node.node_id)
        elif not record['repeat_blocked'] and node.status == StepStatus.FAILED and node.last_error_category:
            existing_next_retry_at = record.get("next_retry_at")
            if not existing_next_retry_at or previous_retry_count != int(node.retry_count or 0):
                next_retry_at, backoff_seconds = _compute_next_retry_at(
                    node.last_error_category,
                    int(node.retry_count or 0),
                )
                record["next_retry_at"] = next_retry_at
                record["backoff_seconds"] = backoff_seconds

    return {
        "records": list(records.values()),
        "max_retries_per_tool": max_retries,
        "repeat_blocked_nodes": sorted(set(repeated_terminal_nodes)),
    }


def _format_failure_memory_notes(failure_memory: dict[str, Any] | None) -> str:
    """Convert failure memory into concise planner hints."""
    if not failure_memory:
        return ""
    records = failure_memory.get("records") or []
    notable = [
        record for record in records
        if record.get("repeat_blocked") or record.get("retry_count", 0) > 0
    ]
    if not notable:
        return ""
    lines = [
        "Avoid repeating known failed tool patterns from this session.",
        "Known failures:",
    ]
    for record in notable[:8]:
        lines.append(
            f"- {record.get('node_type')} | {record.get('query')} | "
            f"error={record.get('last_error_category') or 'unknown'} | "
            f"retries={record.get('retry_count', 0)} | "
            f"repeat_blocked={bool(record.get('repeat_blocked'))} | "
            f"next_retry_at={record.get('next_retry_at')}"
        )
    lines.append("Prefer alternative tools or narrower queries when a pattern is repeat_blocked.")
    return "\n".join(lines)


def _should_retry_node(
    node: PlanNode,
    budget_state: dict[str, Any],
    failure_memory: dict[str, Any] | None,
) -> tuple[bool, str | None]:
    """Decide whether a failed node should be retried automatically."""
    if node.terminal_failure:
        return False, "terminal_failure"
    if node.status != StepStatus.FAILED:
        return False, "not_failed"
    if node.last_error_category is None:
        return False, "missing_error_category"

    max_retries = _tool_retry_limit(budget_state, _research_budget({'output_length': None}), failure_memory)
    max_retries = min(max_retries, max(0, int(node.max_retries)))
    if int(node.retry_count or 0) >= max_retries:
        return False, "max_retries_reached"

    record = None
    for item in (failure_memory or {}).get("records", []):
        if item.get("node_type") == node.node_type and item.get("query") == node.query:
            record = item
            break
    if record and record.get("repeat_blocked"):
        return False, "repeat_blocked"

    retryable_categories = {"timeout", "upstream_429", "upstream_5xx", "network", "temporary_db"}
    if node.last_error_category not in retryable_categories:
        return False, "non_retryable_category"
    if record and record.get("next_retry_at"):
        try:
            if utc_now_naive() < datetime.fromisoformat(str(record["next_retry_at"])):
                return False, "backoff_active"
        except ValueError:
            pass
    return True, None


def _base_backoff_seconds(error_category: str | None) -> int:
    mapping = {
        "timeout": 2,
        "network": 2,
        "temporary_db": 2,
        "upstream_5xx": 3,
        "upstream_429": 5,
    }
    return mapping.get(error_category or "", 2)


def _compute_next_retry_at(error_category: str | None, retry_count: int) -> tuple[str, int]:
    """Return ISO timestamp + seconds for exponential backoff."""
    base = _base_backoff_seconds(error_category)
    exponent = max(0, retry_count - 1)
    backoff_seconds = min(base * (2 ** exponent), 60)
    next_retry_at = utc_now_naive() + timedelta(seconds=backoff_seconds)
    return next_retry_at.isoformat(), backoff_seconds


def _result_count(node: PlanNode) -> int:
    if not node.result:
        return 0
    results = node.result.get("results")
    return len(results) if isinstance(results, list) else int(node.result.get('result_count') or 0)


def _classify_error_category(error: str | None) -> str:
    """Map runtime failures into retryable/terminal governance buckets."""
    message = (error or "").lower()
    if any(value in message for value in ('data_class','access_credentials','credential_url_requires','private_context_network_query','data_governance')):
        return 'data_governance'
    if message in {'source_out_of_scope', 'unsupported_source_transport', 'discovery_only'}:
        return message
    if message in {"auth_required", "account_risk", "rate_limited", "disabled", "configuration_required", "dependency_missing", "empty_content", "budget_exceeded", "output_limit", "domain_blocked", "unsupported_input", "unsupported_operation", "invalid_output"}:
        return message
    if any(token in message for token in ("timeout", "timed out")):
        return "timeout"
    if any(token in message for token in ("429", "rate limit")):
        return "upstream_429"
    if any(token in message for token in ("503", "502", "500", "service unavailable", "bad gateway")):
        return "upstream_5xx"
    if any(token in message for token in ("connection", "network", "dns")):
        return "network"
    if any(token in message for token in ("database", "db")):
        return "temporary_db"
    return "temporary_db"


def _is_terminal_error_category(category: str | None) -> bool:
    return category in {
        'data_governance',
        'source_out_of_scope', 'unsupported_source_transport', 'discovery_only',
        "schema_validation",
        "permission_denied",
        "approval_denied",
        "untrusted_mcp_server",
        "tool_not_allowed",
        "domain_blocked",
        "unsupported_input",
        "auth_required", "account_risk", "rate_limited", "disabled", "configuration_required",
        "dependency_missing", "unsupported_operation", "budget_exceeded", "output_limit", "invalid_output",
    }


def _make_node_outcome(
    *,
    node_id: str,
    tool_history: dict[str, Any],
    tool_name: str,
    status: str,
    retry_count: int = 0,
    error_category: str | None = None,
    error_message: str | None = None,
    result_count: int = 0,
    approval_request_id: str | None = None,
) -> dict[str, Any]:
    tool_call = (tool_history.get("tool_calls") or [{}])[-1]
    outcome = NodeOutcome(
        node_id=node_id,
        tool_call_id=tool_call.get("call_id"),
        tool_name=tool_name,
        status=status,
        error_category=error_category,
        error_message=error_message,
        retry_count=retry_count,
        tokens_used=int(tool_call.get("tokens_used") or 0),
        cost_usd=float(tool_call.get("cost_usd") or 0.0),
        result_count=result_count,
        approval_request_id=approval_request_id,
    )
    return outcome.model_dump()


def _make_approval_request(
    *,
    node_id: str,
    tool_name: str,
    reason: str,
    request_payload: dict[str, Any],
    risk_level: str = "high",
) -> dict[str, Any]:
    return {
        "approval_id": f"ap-{node_id}-{tool_name}-{int(time.time() * 1000)}",
        "node_id": node_id,
        "tool_name": tool_name,
        "risk_level": risk_level,
        "reason": reason,
        "request_payload": request_payload,
        "status": "pending",
        "requested_at": utc_now_naive().isoformat(),
    }


# ==============================================================
# 主题 2 & 3: 工具调用追踪装饰器
# ==============================================================

def track_tool_call(agent_type: AgentType, tool_name: str):
    """
    装饰器：追踪工具调用（主题 3）。

    在节点函数执行时记录 ToolCallRecord，
    方便后续分析和优化工具使用效率。
    """
    def decorator(func):
        async def async_wrapper(state: ResearchState, *args, **kwargs) -> dict:
            agent_str = agent_type.value
            call_record = ToolCallRecord(
                agent_type=agent_type,
                tool_name=tool_name,
                args={"task_id": state.get("task_id"), "query": state.get("user_query")},
                status="running",
            )

            # 记录开始
            state.setdefault("tool_histories", [])
            history = ToolInvocationHistory(
                agent_type=agent_type,
                tool_calls=[call_record],
            )
            state["tool_histories"].append(history.model_dump())

            try:
                start_time = time.perf_counter()
                result = await func(state, *args, **kwargs)
                if (state["tool_histories"]
                        and state["tool_histories"][-1].get("agent_type") == agent_str):
                    state["tool_histories"][-1]["tool_calls"][-1]["status"] = "success"
                    state["tool_histories"][-1]["tool_calls"][-1]["completed_at"] = utc_now_naive().isoformat()
                    state["tool_histories"][-1]["tool_calls"][-1]["duration_ms"] = int((time.perf_counter() - start_time) * 1000)
                    state["tool_histories"][-1]["tool_calls"][-1]["result_summary"] = str(result)[:200]
                return result
            except (OSError, RuntimeError, TypeError, ValueError, KeyError) as e:
                if (state["tool_histories"]
                        and state["tool_histories"][-1].get("agent_type") == agent_str):
                    state["tool_histories"][-1]["tool_calls"][-1]["status"] = "error"
                    state["tool_histories"][-1]["tool_calls"][-1]["completed_at"] = utc_now_naive().isoformat()
                    state["tool_histories"][-1]["tool_calls"][-1]["error"] = str(e)
                raise

        def sync_wrapper(state: ResearchState, *args, **kwargs) -> dict:
            agent_str = agent_type.value
            call_record = ToolCallRecord(
                agent_type=agent_type,
                tool_name=tool_name,
                args={"task_id": state.get("task_id"), "query": state.get("user_query")},
                status="running",
            )

            state.setdefault("tool_histories", [])
            history = ToolInvocationHistory(
                agent_type=agent_type,
                tool_calls=[call_record],
            )
            state["tool_histories"].append(history.model_dump())
            try:
                start_time = time.perf_counter()
                result = func(state, *args, **kwargs)
                if (state["tool_histories"]
                        and state["tool_histories"][-1].get("agent_type") == agent_str):
                    state["tool_histories"][-1]["tool_calls"][-1]["status"] = "success"
                    state["tool_histories"][-1]["tool_calls"][-1]["completed_at"] = utc_now_naive().isoformat()
                    state["tool_histories"][-1]["tool_calls"][-1]["duration_ms"] = int((time.perf_counter() - start_time) * 1000)
                    state["tool_histories"][-1]["tool_calls"][-1]["result_summary"] = str(result)[:200]
                return result
            except (OSError, RuntimeError, TypeError, ValueError, KeyError) as e:
                if (state["tool_histories"]
                        and state["tool_histories"][-1].get("agent_type") == agent_str):
                    state["tool_histories"][-1]["tool_calls"][-1]["status"] = "error"
                    state["tool_histories"][-1]["tool_calls"][-1]["completed_at"] = utc_now_naive().isoformat()
                    state["tool_histories"][-1]["tool_calls"][-1]["error"] = str(e)
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def _make_tool_history(
    *,
    agent_type: AgentType,
    tool_name: str,
    task_id: str | None,
    query: str,
) -> dict[str, Any]:
    """Create a structured tool history entry for a single tool invocation."""
    history = ToolInvocationHistory(
        agent_type=agent_type,
        tool_calls=[ToolCallRecord(
            agent_type=agent_type,
            tool_name=tool_name,
            args={
                "task_id": task_id,
                "query": query,
            },
            safety_json={
                "source": "harness_tool_layer",
                "audited": True,
            },
            status="running",
        )],
    )
    return history.model_dump()


def _append_trace_event(
    state: ResearchState,
    event_type: EventType,
    agent: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Emit both agent trace and SSE-friendly state updates for the UI."""
    from app.graph.state import AgentEvent

    event = AgentEvent(agent=agent, event_type=event_type.value, content=content).model_dump()
    if metadata:
        event.update(metadata)
    handoff=state.get('tool_handoff') or {}
    if handoff.get('node_id'):
        event.setdefault('node_id',handoff['node_id'])
    from app.disclosure import projection
    event=projection(event)
    state.setdefault("agent_trace", []).append(event)
    from app.observability.trace import publish_live_event
    publish_live_event(state,event)
    return event


def _finish_tool_history(
    history: dict[str, Any],
    *,
    status: str,
    result_summary: str | None = None,
    error: str | None = None,
) -> None:
    """Finalize a structured tool history entry."""
    tool_call = history["tool_calls"][-1]
    tool_call["status"] = status
    tool_call["completed_at"] = utc_now_naive().isoformat()
    started_at = datetime.fromisoformat(tool_call["started_at"])
    tool_call["duration_ms"] = int((utc_now_naive() - started_at).total_seconds() * 1000)
    from app.disclosure import redact_text
    if result_summary is not None:
        tool_call["result_summary"] = redact_text(result_summary)[:200]
    if error is not None:
        tool_call["error"] = redact_text(error)


def _update_tool_safety(history: dict[str, Any], **metadata: Any) -> None:
    """Merge structured safety metadata into the current tool call audit record."""
    tool_call = history["tool_calls"][-1]
    safety = dict(tool_call.get("safety_json") or {})
    for key, value in metadata.items():
        if value is not None:
            safety[key] = value
    tool_call["safety_json"] = safety


# ==============================================================
# 主题 1 & 2: Planner Node - DAG 生成
# ==============================================================

def planner_node(state: ResearchState) -> dict:
    """
    Planner Agent: 将用户查询转换为可执行的 DAG（主题 1 & 2）。

    主题 1: 这是自主研究工作流的起点
    主题 2: Planner 生成研究计划的 DAG 结构

    输入: user_query
    输出: dag（序列化的 DAGDefinition）, agent_trace
    """
    from app.agents.planner import PlannerAgent
    from app.observability.trace import EventType, emit_event

    # 追踪事件
    emit_event(state, EventType.AGENT_START, "planner", f"Planning research for: {state['user_query']}")

    # 调用 Planner Agent 生成 DAG
    agent = PlannerAgent()
    agent.request_budget = _stage_model_budget(state,'planner')
    agent.model_routing=state.get('model_routing')
    planning_hints = _format_failure_memory_notes(state.get("failure_memory"))
    try:
        dag: DAGDefinition = agent.create_dag(
            state['user_query'], query_contract=_plan_contract(state),
            planning_strategy=PlanningPolicy.model_validate(state.get('planning_policy') or {}).strategy,
            query_type=(state.get('query_understanding') or {}).get('query_type'),
            analysis_depth=((state.get('query_understanding') or {}).get('slots') or {}).get('depth', 'auto'),
            planning_hints=planning_hints or None, skill_prompt=_skill_prompt(state, 'planner') or None,
            planner_hints=_agent_skill_hints(state, "planner"),use_internal_docs=bool(state.get("use_internal_docs", False)),
            rag_group=state.get("rag_group"),organization_research=state.get("organization_research"))
    except TokenBudgetExceeded as error:
        return _model_budget_pause(state,agent,'planner',error)
    dag = apply_source_policy(dag, state["user_query"], use_internal_docs=bool(state.get("use_internal_docs", False)))
    dag = seed_organization_sources(dag, state.get("organization_research"))
    dag, manifest = _compile_execution_plan(state, dag, agent, agent.last_plan_reason)
    decision = build_guardrail_decision(_guardrail_question(state), user_confirmed=state.get("user_confirmed", False))
    record_guardrail_event(
        state,
        agent="planner",
        event_type="guardrail_decision",
        content="planner routed",
        metadata=decision.model_dump(),
    )

    # 追踪 DAG 生成
    emit_event(
        state, EventType.AGENT_COMPLETE, "planner",
        f"Generated DAG '{dag.dag_name}' with {len(dag.nodes)} nodes, "
        f"execution order: {dag.get_executable_order()}"
    )

    # 更新会话元数据
    session = state.get("session", {})
    session["updated_at"] = utc_now_naive().isoformat()
    session, budget_state = _apply_llm_usage_to_state(state, "planner", _agent_model_usage(agent))

    return {
        "dag": serialize_dag(dag),
        'plan_manifest': manifest,
        'plan_history': [*(state.get('plan_history') or []), {key: manifest[key] for key in ('plan_version','revision','reason','strategy','adjustments')}][-32:],
        'agent_trace': [_append_trace_event(state, EventType.AGENT_COMPLETE, 'planner',
            '研究计划已编译；步骤与调整原因可查看。', {'plan_manifest':manifest,'kind':'plan_ready'})],
        "status": TaskStatus.RUNNING.value,
        "session": session,
        "budget_state": budget_state,
        "guardrail_decision": decision.model_dump(),
        "failure_memory": state.get("failure_memory"),
        "skill_context": _skill_context(state),
    }


# ==============================================================
# 主题 1 & 2: DAG 执行 Node - 按拓扑序执行
# ==============================================================

def dag_executor_node(state: ResearchState) -> dict:
    """
    DAG 执行器：按拓扑序分发 DAG 节点（主题 1 & 2）。

    主题 2: 根据 DAG 的节点依赖关系，分发到对应的工具 Agent
    主题 3: 使用 Send API 实现并行执行

    输入: dag（DAGDefinition）
    输出: current_executing_nodes, agent_trace
    """
    from app.observability.trace import EventType, emit_event

    dag = apply_source_policy(
        deserialize_dag(state["dag"]), state["user_query"],
        use_internal_docs=bool(state.get("use_internal_docs", False)), ensure_sources=False,
    )
    execution_order = dependency_batches(dag.nodes)
    budget_state = _build_budget_state(state)
    failure_memory = state.get("failure_memory")

    # 当前批次节点
    all_completed = set(state.get("completed_nodes", []))
    all_completed.update(node.node_id for node in dag.nodes if node.status in (StepStatus.DONE, StepStatus.SKIPPED))
    enabled_tools = _effective_tool_allowlist(state, state.get("guardrail_decision") or {})
    for node in dag.nodes:
        if node.node_type in TOOL_NODE_TYPES and node.node_type not in enabled_tools:
            node.status = StepStatus.SKIPPED
            all_completed.add(node.node_id)
    current_batch = []
    deferred_retries: list[dict[str, Any]] = []
    scheduling_trace = []
    policy = PlanningPolicy.model_validate(state.get('planning_policy') or {})
    remaining_calls, remaining_seconds = _channel_budget(state, [])
    parallel_limit = min(policy.max_parallel, max(0, remaining_calls))
    latest_outcomes = {item['node_id']: item for item in state.get('node_outcomes', [])
        if isinstance(item, dict) and item.get('node_id')}

    for node in dag.nodes:
        if node.node_type not in TOOL_NODE_TYPES:
            continue
        should_retry, reason = _should_retry_node(node, budget_state, failure_memory)
        if should_retry:
            node.status = StepStatus.PENDING
        elif reason == "backoff_active":
            for item in (failure_memory or {}).get("records", []):
                if item.get("node_type") == node.node_type and item.get("query") == node.query:
                    deferred_retries.append({
                        "node_id": node.node_id,
                        "next_retry_at": item.get("next_retry_at"),
                        "backoff_seconds": item.get("backoff_seconds", 0),
                    })
                    break

    nodes_by_id = {node.node_id: node for node in dag.nodes}
    for batch in execution_order:
        for node_id in batch:
            node = nodes_by_id[node_id]
            if node_id in all_completed or node.node_type not in TOOL_NODE_TYPES:
                continue
            if node.status not in (StepStatus.PENDING, StepStatus.RUNNING):
                continue
            failed_dependencies = []
            for dependency_id in node.depends_on:
                dependency = nodes_by_id[dependency_id]
                if dependency.status == StepStatus.SKIPPED and dependency.last_error_category in {
                        'dependency_failed','tool_not_allowed','budget_exceeded','unsupported_condition'}:
                    failed_dependencies.append(dependency_id)
                if dependency.status == StepStatus.FAILED:
                    retry, retry_reason = _should_retry_node(dependency, budget_state, failure_memory)
                    if not retry and retry_reason != 'backoff_active':
                        failed_dependencies.append(dependency_id)
            decision = 'dependency_failed' if failed_dependencies else condition_decision(node, all_completed, latest_outcomes)
            if decision in {'dependency_failed', 'condition_not_met', 'unsupported_condition'}:
                node.status, node.last_error_category = StepStatus.SKIPPED, decision
                all_completed.add(node_id)
                scheduling_trace.append(_append_trace_event(state, EventType.AGENT_COMPLETE, 'dag_executor',
                    '当前步骤未执行，原因已记录。', {'node_id':node_id,'reason':decision,
                        'failed_dependencies':failed_dependencies,'condition':node.condition,'kind':'step_skipped'}))
                continue
            if decision != 'run' or parallel_limit == 0:
                continue
            if not node.parallel and current_batch:
                break
            current_batch.append(node_id)
            if not node.parallel or len(current_batch) >= parallel_limit:
                break
        if current_batch:
            break

    if not current_batch:
        # 所有节点都已执行完成
        if deferred_retries:
            next_retry_at = min(
                (
                    datetime.fromisoformat(item["next_retry_at"])
                    for item in deferred_retries
                    if item.get("next_retry_at")
                ),
                default=None,
            )
            if next_retry_at is not None:
                delay_seconds = max(0.0, min((next_retry_at - utc_now_naive()).total_seconds(), 5.0))
                if delay_seconds > 0:
                    from app.execution_control import current_control
                    control=current_control()
                    if control:control.event.wait(delay_seconds);control.check()
                    else:time.sleep(delay_seconds)
        emit_event(state, EventType.AGENT_COMPLETE, "dag_executor", "本轮暂无可执行取证步骤；等待或跳过原因分别记录。")
        trace = list(scheduling_trace)
        if deferred_retries:
            trace.append(_append_trace_event(
                state,
                EventType.AGENT_COMPLETE,
                "retry_scheduler",
                f"Deferred {len(deferred_retries)} retryable node(s) by exponential backoff.",
                {"deferred_retries": deferred_retries},
            ))
        return {"dag": serialize_dag(dag), "completed_nodes": list(all_completed), "current_executing_nodes": [], "agent_trace": trace}

    emit_event(
        state, EventType.AGENT_START, "dag_executor",
        f"Executing bounded batch: {current_batch}"
    )

    manifest = state.get('plan_manifest')
    if not manifest:
        from app.query_understanding import identity
        manifest = {'schema_version':'adrs-planning-control-v1', 'task_id':state['task_id'],
            'execution_id':state.get('session',{}).get('execution_id'), 'revision':state.get('revision_count',0)+1,
            'legacy_compatibility':'restored_dag_statuses_preserved_not_replanned'}
        manifest['plan_version'] = identity({'binding':manifest,'dag':serialize_dag(dag)})
    handoffs = prepare_handoffs({**state,'plan_manifest':manifest}, dag, current_batch, remaining_calls, remaining_seconds)
    return {
        "dag": serialize_dag(dag),
        'plan_manifest':manifest, 'tool_handoffs':handoffs,
        "current_executing_nodes": current_batch,
        "completed_nodes": list(all_completed),
        "agent_trace": scheduling_trace + ([
            _append_trace_event(
                state,
                EventType.AGENT_COMPLETE,
                "retry_scheduler",
                f"Deferred {len(deferred_retries)} retryable node(s) by exponential backoff.",
                {"deferred_retries": deferred_retries},
            ),
        ] if deferred_retries else []) + [_append_trace_event(state, EventType.AGENT_COMPLETE, 'dag_executor',
            '已按依赖、条件和并发限制选择取证步骤。', {'kind':'batch_scheduled','node_ids':current_batch,
                'parallel_limit':parallel_limit,'parallel_reason':'bounded_tool_requests_with_completed_declared_dependencies',
                'budget_allocations':{key:value['budget_allocation'] for key,value in handoffs.items() if value.get('budget_allocation')},
                'autonomous_research_subagents_created':0})],
    }


async def dag_results_aggregator(state: ResearchState) -> dict:
    """
    DAG 结果聚合器：收集工具 Agent 的结果，更新 DAG 状态（主题 2）。

    当一批并行节点执行完成后，调用此函数更新 DAG 状态。
    """
    from app.observability.trace import EventType

    if state.get('tool_handoffs') and not await current_execution({
            'task_id':state['task_id'], 'owner_id':state['session']['owner_id'],
            'execution_id':state['session']['execution_id']}):
        raise PlanningError('execution_no_longer_current')
    admitted = accept_results(state)
    # Graph list reducers append deltas; work on a local combined view and return
    # only newly accepted records, rather than rebroadcasting all prior data.
    state = {**state, **{key: [*state.get(key,[]), *admitted[key]] for key in
        ('collected_evidence','tool_histories','node_outcomes','agent_trace','pending_approvals')}}
    dag = deserialize_dag(state["dag"])
    current_nodes = set(state.get("current_executing_nodes", []))
    latest_outcomes = {
        outcome["node_id"]: outcome
        for outcome in state.get("node_outcomes", [])
        if isinstance(outcome, dict) and outcome.get("node_id") in current_nodes
        and (not state.get('tool_handoffs') or outcome.get('operation_id') ==
            (state['tool_handoffs'].get(outcome['node_id']) or {}).get('operation_id'))
    }

    completed = set(state.get("completed_nodes", []))
    runtime_status = state.get("runtime_status", RuntimeStatus.RUNNING.value)

    for node in dag.nodes:
        if node.node_id not in current_nodes:
            continue
        outcome = latest_outcomes.get(node.node_id)
        if not outcome and node.status == StepStatus.DONE:
            completed.add(node.node_id)
            continue
        if not outcome and node.result is not None and node.status != StepStatus.FAILED and not node.waiting_approval:
            node.status = StepStatus.DONE
            completed.add(node.node_id)
            continue
        if not outcome:
            continue
        outcome_status = outcome.get("status")
        node.last_error = outcome.get("error_message")
        node.last_error_category = outcome.get("error_category")
        node.waiting_approval = outcome_status == "awaiting_approval"
        node.terminal_failure = outcome_status == "terminal_error"
        node.retry_count = max(node.retry_count, int(outcome.get("retry_count") or 0))

        if outcome_status == "success":
            node.status = StepStatus.DONE
            node.result = {'result_count':int(outcome.get('result_count') or 0)}
            completed.add(node.node_id)
        elif outcome_status == "skipped":
            node.status = StepStatus.SKIPPED
            completed.add(node.node_id)
        elif outcome_status == "awaiting_approval":
            node.status = StepStatus.PENDING
            runtime_status = RuntimeStatus.AWAITING_APPROVAL.value
        elif outcome_status == "terminal_error":
            node.status = StepStatus.FAILED
            runtime_status = RuntimeStatus.TERMINAL_FAILED.value
        elif outcome_status == "retryable_error":
            node.status = StepStatus.FAILED
            if runtime_status not in (RuntimeStatus.AWAITING_APPROVAL.value, RuntimeStatus.TERMINAL_FAILED.value):
                runtime_status = RuntimeStatus.RETRYABLE_FAILED.value

    completed_list = list(completed)
    retrieval_policy = {
        "mode": "web_with_internal_docs" if state.get("use_internal_docs", False) else "public_web",
        "use_internal_docs": bool(state.get("use_internal_docs", False)),
        "rag_group": state.get("rag_group") if state.get("use_internal_docs", False) else None,
    }
    budget_state = _build_budget_state(state)

    rag_hit_count = sum(
        _result_count(node)
        for node in dag.nodes
        if node.node_type == "rag" and node.status == StepStatus.DONE
    )
    retrieval_policy["rag_hit_count"] = rag_hit_count

    trace = []
    if current_nodes and any(node.node_type == "rag" for node in dag.nodes if node.node_id in current_nodes):
        trace.append(_append_trace_event(
            state,
            EventType.AGENT_COMPLETE,
            "retrieval_policy",
            f"Internal documents returned {rag_hit_count} chunks as supplementary evidence.",
            {"retrieval_policy": retrieval_policy},
        ))

    breaker_skipped_nodes: list[str] = []
    if budget_state.get("warning"):
        trace.append(_append_trace_event(
            state,
            EventType.AGENT_COMPLETE,
            "budget_guardrail",
            f"Budget warning: tool_calls={budget_state['used_tool_calls']}, "
            f"tokens={budget_state['used_total_tokens']}, cost={budget_state['used_cost_usd']}, "
            f"wall_clock={budget_state['elapsed_wall_clock_seconds']}s",
            {"budget_state": budget_state},
        ))
    if budget_state.get("hard_stop_reason"):
        dag, breaker_skipped_nodes = _apply_budget_breaker(dag, budget_state)
        if breaker_skipped_nodes:
            completed_list = list(set(completed_list) | set(breaker_skipped_nodes))
        runtime_status = RuntimeStatus.TERMINAL_FAILED.value
        trace.append(_append_trace_event(
            state,
            EventType.AGENT_COMPLETE,
            "budget_guardrail",
            f"Budget breaker triggered: {budget_state['hard_stop_reason']}. "
            f"Skipped {len(breaker_skipped_nodes)} pending tool nodes.",
            {
                "budget_state": budget_state,
                "skipped_nodes": breaker_skipped_nodes,
            },
        ))

    failure_memory = _build_failure_memory(state, dag)
    if failure_memory.get("records"):
        trace.append(_append_trace_event(
            state,
            EventType.AGENT_COMPLETE,
            "failure_memory",
            f"Captured {len(failure_memory['records'])} failure memory records",
            {"failure_memory": failure_memory},
        ))

    return {
        "dag": serialize_dag(dag),
        "completed_nodes": completed_list,
        "retrieval_policy": retrieval_policy,
        "runtime_status": runtime_status,
        "budget_state": budget_state,
        "failure_memory": failure_memory,
        **{key:value for key,value in admitted.items() if key != 'agent_trace'},
        "agent_trace": [*admitted['agent_trace'], *trace],
    }


def should_continue_dag(state: ResearchState) -> str:
    """
    判断 DAG 是否还有未执行的节点（主题 1 & 2）。

    返回:
    - "continue": 还有节点需要执行
    - "analyst": 所有节点都已执行，进入分析阶段
    """
    dag = deserialize_dag(state["dag"])
    completed = set(state.get("completed_nodes", []))
    if state.get("pending_approvals"):
        return "approval_reviewer"
    budget_state = state.get("budget_state") or {}
    if budget_state.get("hard_stop_reason"):
        return "analyst"

    pending = [
        n for n in dag.nodes
        if n.node_type in TOOL_NODE_TYPES
        and n.node_id not in completed
        and n.status != StepStatus.SKIPPED
        and not getattr(n, "waiting_approval", False)
    ]

    deferred_retry_exists = False
    failure_memory = state.get("failure_memory") or {}
    if pending:
        for node in pending:
            if node.status in (StepStatus.PENDING, StepStatus.RUNNING):
                deferred_retry_exists = True
                break
            retry, retry_reason = _should_retry_node(node, budget_state, failure_memory)
            deferred_retry_exists = retry or retry_reason == 'backoff_active'
            if deferred_retry_exists:
                break

    if deferred_retry_exists:
        return "continue"
    return "analyst"


def approval_reviewer_node(state: ResearchState) -> dict:
    """Independent reviewer branch for action-level approvals."""
    from app.graph.state import AgentEvent

    pending = [
        approval for approval in state.get("pending_approvals", [])
        if isinstance(approval, dict) and approval.get("status", "pending") == "pending"
    ]
    trace = [AgentEvent(
        agent="approval_reviewer",
        event_type="agent_complete",
        content=f"Paused for {len(pending)} approval request(s)",
    ).model_dump()]
    return {
        "runtime_status": RuntimeStatus.AWAITING_APPROVAL.value,
        "status": TaskStatus.PAUSED.value,
        "agent_trace": trace,
    }


# ==============================================================
# 主题 3: 工具 Agent Nodes - Search / Browser / RAG
# ==============================================================

def search_node(state: ResearchState) -> dict:
    """
    Search Agent: 执行搜索工具（主题 3）。

    主题 3: 工具驱动多 Agent
    - 从 DAG 获取当前批次中类型为 search 的节点
    - 执行搜索工具
    - 记录工具调用历史

    输入: dag, current_executing_nodes
    输出: collected_evidence, tool_histories, agent_trace
    """
    from app.agents.search import SearchAgent
    from app.graph.state import AgentEvent, Evidence
    from app.guardrails import record_guardrail_event, validate_tool_invocation
    from app.observability.trace import EventType

    dag = deserialize_dag(state["dag"])
    executing_nodes = state.get("executing_nodes", state.get("current_executing_nodes", []))

    # 找出当前批次中分配给 search 的节点
    search_nodes = [
        n for n in dag.nodes
        if n.node_id in executing_nodes and n.node_type == "search"
    ]

    if not search_nodes:
        return {"collected_evidence": [], "tool_histories": [], "agent_trace": [], "node_outcomes": []}

    trace = [
        _append_trace_event(state, EventType.AGENT_START, "search", f"Executing {len(search_nodes)} search nodes")
    ]

    agent = SearchAgent()
    all_evidence = []
    tool_histories = []
    node_outcomes = []
    budget = _research_budget(state)
    max_queries = budget.get("search_max_queries", 4)
    max_results = budget.get("search_max_results", 10)

    for node in search_nodes[max_queries:]:
        node_outcomes.append(_make_node_outcome(node_id=node.node_id,tool_history={},tool_name='execute_search',
            status='skipped',error_category='search_node_limit'))

    for position,node in enumerate(search_nodes[:max_queries]):
        remaining_calls, remaining_seconds = _channel_budget(state, tool_histories)
        if not remaining_calls or not remaining_seconds:
            node_outcomes.append(_make_node_outcome(node_id=node.node_id, tool_history={}, tool_name="execute_search", status="skipped", error_category="budget_exceeded"))
            continue
        trace.append(_append_trace_event(
            state,
            EventType.TOOL_START,
            "search",
            f"Searching: {node.query}",
            {"tool_name": "duckduckgo_search", "args": {"query": node.query}},
        ))
        tool_history = _make_tool_history(
            agent_type=AgentType.SEARCH,
            tool_name="execute_search",
            task_id=state.get("task_id"),
            query=node.query,
        )
        valid, reason = validate_tool_invocation("duckduckgo_search", {"query": node.query})
        if not valid:
            node.status = StepStatus.FAILED
            node.terminal_failure = True
            node.last_error = reason or "invalid_args"
            node.last_error_category = "schema_validation"
            _update_tool_safety(tool_history, schema_validated=False, sanitized_error=True)
            _finish_tool_history(tool_history, status="error", error=reason or "invalid_args")
            record_guardrail_event(
                state,
                agent="search",
                event_type="tool_blocked",
                content=reason or "invalid_args",
                metadata={"tool": "duckduckgo_search", "query": node.query},
            )
            tool_histories.append(tool_history)
            node_outcomes.append(_make_node_outcome(
                node_id=node.node_id,
                tool_history=tool_history,
                tool_name="duckduckgo_search",
                status="terminal_error",
                retry_count=node.retry_count,
                error_category="schema_validation",
                error_message=reason or "invalid_args",
            ))
            continue
        require_approval, approval_reason = should_require_action_approval(
            tool_name="duckduckgo_search",
            decision=state.get("guardrail_decision") and build_guardrail_decision(
                _guardrail_question(state),
                user_confirmed=state.get("user_confirmed", False),
            ),
            readonly=True,
        )
        if require_approval and not approved_action(state, node, "duckduckgo_search", {"query": node.query}):
            approval = _make_approval_request(
                node_id=node.node_id,
                tool_name="duckduckgo_search",
                reason=approval_reason or "action_requires_approval",
                request_payload={"query": node.query},
            )
            node.waiting_approval = True
            _update_tool_safety(
                tool_history,
                schema_validated=True,
                approval_required=True,
                sanitized_error=True,
            )
            _finish_tool_history(tool_history, status="error", error=approval["reason"])
            tool_histories.append(tool_history)
            node_outcomes.append(_make_node_outcome(
                node_id=node.node_id,
                tool_history=tool_history,
                tool_name="duckduckgo_search",
                status="awaiting_approval",
                retry_count=node.retry_count,
                error_category="approval_required",
                error_message=approval["reason"],
                approval_request_id=approval["approval_id"],
            ))
            return {
                "collected_evidence": [e.model_dump() for e in all_evidence],
                "tool_histories": tool_histories,
                "node_outcomes": node_outcomes,
                "pending_approvals": [approval],
                "agent_trace": trace,
            }
        # 更新节点状态为 RUNNING
        node.status = StepStatus.RUNNING

        try:
            from app.organization_corpus import source_scope
            policy = source_scope(state.get('organization_research'))
            if ((state.get('organization_research') or {}).get('corpus') or {}).get('collection_mode') == 'seeds_only':
                from app.channels.models import ChannelError
                raise ChannelError('source_out_of_scope')
            from app.query_rewriting import search_route
            route=search_route(node.query,state.get('query_understanding'),channels=state.get('session',{}).get('channels'),
                remaining_calls=remaining_calls,remaining_seconds=remaining_seconds,
                remaining_nodes=len(search_nodes[:max_queries])-position,max_results=max_results,web_only=bool(policy))
            _update_tool_safety(tool_history,query_route=route)
            trace.append(_append_trace_event(state,EventType.TOOL_COMPLETE,'search',
                f"检索分配：{len(route['variants'])}个查询、{len(route['channels'])}个渠道，最多{route['max_calls']}次调用",
                {'query_route':route,'tool_name':'query_routing','node_id':node.node_id}))
            if not route['variants'] or not route['channels']:
                from app.channels.models import ChannelError
                raise ChannelError('query_route_has_no_admitted_request')
            search_queries=[item['query'] for item in route['variants']]
            from app.data_governance import authorize_network
            from app.channels.catalog import route_query
            for query in search_queries:
                _,operation,value=route_query(query)
                authorize_network(value,(state.get('query_understanding') or {}).get('network_context'),operation=operation)
            if policy:
                from app.channels.catalog import route_query
                from app.channels.models import ChannelError
                admitted=[]
                for query in search_queries:
                    channel, operation, value = route_query(query)
                    if channel != 'web' or operation != 'search':
                        raise ChannelError('unsupported_source_transport')
                    admitted.append(policy.search_query(value))
                search_queries=admitted
            _update_tool_safety(tool_history,admitted_queries=search_queries)
            search_query=search_queries[0]
            from app.candidate_fusion import frozen_policy
            results = agent.execute_search(search_query, channels=route['channels'],
                                           owner_id=state.get("session", {}).get("owner_id"), limit=route['top_k'],
                                           max_calls=route['max_calls'], timeout_seconds=route['timeout_seconds'],
                                           query_variants=list(dict.fromkeys(search_queries)),
                                           fusion=frozen_policy((state.get('query_understanding') or {}).get('candidate_fusion')),
                                           query_type=(state.get('query_understanding') or {}).get('query_type'),source_policy=policy)[:max_results]
            if policy:
                accepted, rejected = policy.filter_leads(results)
                allowed = {item['url'] for item in accepted}
                results = [result for result in results if result.url in allowed]
                _update_tool_safety(tool_history, source_query=search_query, rejected_sources=rejected)
            attempts = getattr(agent, "last_channel_attempts", [])
            if attempts:
                trace.append(_append_trace_event(state, EventType.TOOL_COMPLETE if results else EventType.TOOL_ERROR,
                                                "search", "渠道采集结果", {"channel_attempts": attempts,"candidate_fusion":agent.last_fusion}))
                _update_tool_safety(tool_history, channel_attempts=attempts,candidate_fusion=agent.last_fusion)
                if not results:
                    category = attempts[-1].get("error_category")
                    if not policy or category not in {None, 'empty_content'}:
                        raise RuntimeError(category or 'empty_content')
                    _update_tool_safety(tool_history, empty_discovery=True,
                        discovery_status='provider_empty_or_no_in_scope_leads', in_scope_lead_count=0)
            node.result = {"results": [r.model_dump() for r in results],"candidate_fusion":agent.last_fusion}
            node.confidence = 0.9 if results else 0.0
            _finish_tool_history(
                tool_history,
                status="success",
                result_summary=f"{len(results)} search results",
            )
            _update_tool_safety(tool_history, schema_validated=True)
            node.status = StepStatus.DONE
            node.last_error = None
            node.last_error_category = None
            node.terminal_failure = False

            # 转换为 Evidence
            for r in results:
                evidence = Evidence(
                    content=f"{r.title}: {r.snippet}",
                    acquisition={'format': 'search_snippet', 'coverage': 'discovery_only', 'truncated': False,
                        'candidate_fusion':r.candidate_fusion,'data_governance':r.data_governance},
                    source_url=r.url,
                    source_title=r.title,
                    source_type="web",
                    collected_by=AgentType.SEARCH,
                    source_channel=r.channel,
                    source_backend=r.backend,
                    **({"collected_at": r.collected_at} if r.collected_at else {}),
                )
                all_evidence.append(evidence)

            trace.append(_append_trace_event(
                state,
                EventType.TOOL_COMPLETE if results or policy else EventType.TOOL_ERROR,
                "search",
                f"Found {len(results)} results for: {node.query}" if results else f"No in-scope discovery leads; preserve sample gaps: {node.query}",
                {
                    "tool_name": "duckduckgo_search",
                    "status": "success" if results else ('empty' if policy else 'error'),
                    "result_summary": f"{len(results)} search results",
                    "error": None if results or policy else "no_search_results",
                },
            ))
            node_outcomes.append(_make_node_outcome(
                node_id=node.node_id,
                tool_history=tool_history,
                tool_name="duckduckgo_search",
                status="success",
                retry_count=node.retry_count,
                result_count=len(results),
            ))
        except (OSError, RuntimeError, TypeError, ValueError, KeyError) as e:
            node.status = StepStatus.FAILED
            node.retry_count += 1
            category = _classify_error_category(str(e))
            node.last_error = str(e)
            node.last_error_category = category
            node.terminal_failure = _is_terminal_error_category(category)
            trace.append(_append_trace_event(
                state,
                EventType.TOOL_ERROR,
                "search",
                f"Search failed: {e!s}",
                {"tool_name": "duckduckgo_search", "status": "error", "error": str(e)},
            ))
            _finish_tool_history(tool_history, status="error", error=str(e))
            node_outcomes.append(_make_node_outcome(
                node_id=node.node_id,
                tool_history=tool_history,
                tool_name="duckduckgo_search",
                status="terminal_error" if node.terminal_failure else "retryable_error",
                retry_count=node.retry_count,
                error_category=category,
                error_message=str(e),
            ))
        tool_histories.append(tool_history)

    trace.append(AgentEvent(
        agent="search",
        event_type="agent_complete",
        content=f"Collected {len(all_evidence)} evidence from search"
    ).model_dump())

    return {
        "collected_evidence": [e.model_dump() for e in all_evidence],
        "tool_histories": tool_histories,
        "node_outcomes": node_outcomes,
        "agent_trace": trace,
    }


def browser_node(state: ResearchState) -> dict:
    """
    Browser Agent: 执行浏览器工具（主题 3）。

    主题 3: 工具驱动多 Agent
    - 从 DAG 获取当前批次中类型为 browser 的节点
    - 执行 Playwright 浏览器工具
    - 支持深度页面提取

    输入: dag, current_executing_nodes
    输出: collected_evidence, tool_histories, agent_trace
    """
    from app.agents.browser import BrowserAgent
    from app.graph.state import AgentEvent, Evidence
    from app.guardrails import record_guardrail_event, validate_tool_invocation
    from app.observability.trace import EventType

    dag = deserialize_dag(state["dag"])
    executing_nodes = state.get("executing_nodes", state.get("current_executing_nodes", []))

    browser_nodes = [
        n for n in dag.nodes
        if n.node_id in executing_nodes and n.node_type == "browser"
    ]

    if not browser_nodes:
        return {"collected_evidence": [], "tool_histories": [], "agent_trace": [], "node_outcomes": []}

    trace = [
        _append_trace_event(state, EventType.AGENT_START, "browser", f"Executing {len(browser_nodes)} browser nodes")
    ]

    agent = BrowserAgent()
    all_evidence = []
    tool_histories = []
    node_outcomes = []
    budget = _research_budget(state)
    max_results = budget.get("browser_max_results", 2)

    for node in browser_nodes[:max_results]:
        remaining_calls, remaining_seconds = _channel_budget(state, tool_histories)
        if not remaining_calls or not remaining_seconds:
            node_outcomes.append(_make_node_outcome(node_id=node.node_id, tool_history={}, tool_name="execute_browse", status="skipped", error_category="budget_exceeded"))
            continue
        trace.append(_append_trace_event(
            state,
            EventType.TOOL_START,
            "browser",
            f"Browsing: {node.query}",
            {"tool_name": "browse_webpage", "args": {"query": node.query, "url": node.query}},
        ))
        tool_history = _make_tool_history(
            agent_type=AgentType.BROWSER,
            tool_name="execute_browse",
            task_id=state.get("task_id"),
            query=node.query,
        )
        valid, reason = validate_tool_invocation("browse_webpage", {"url": node.query, "max_chars": 2000})
        if not valid:
            node.status = StepStatus.FAILED
            node.terminal_failure = True
            node.last_error = reason or "invalid_args"
            node.last_error_category = "schema_validation"
            _update_tool_safety(tool_history, schema_validated=False, sanitized_error=True)
            _finish_tool_history(tool_history, status="error", error=reason or "invalid_args")
            record_guardrail_event(
                state,
                agent="browser",
                event_type="tool_blocked",
                content=reason or "invalid_args",
                metadata={"tool": "browse_webpage", "url": node.query},
            )
            tool_histories.append(tool_history)
            node_outcomes.append(_make_node_outcome(
                node_id=node.node_id,
                tool_history=tool_history,
                tool_name="browse_webpage",
                status="terminal_error",
                retry_count=node.retry_count,
                error_category="schema_validation",
                error_message=reason or "invalid_args",
            ))
            continue
        require_approval, approval_reason = should_require_action_approval(
            tool_name="browse_webpage",
            decision=state.get("guardrail_decision") and build_guardrail_decision(
                _guardrail_question(state),
                user_confirmed=state.get("user_confirmed", False),
            ),
            readonly=True,
        )
        if require_approval and not approved_action(state, node, "browse_webpage", {"url": node.query, "max_chars": 2000}):
            approval = _make_approval_request(
                node_id=node.node_id,
                tool_name="browse_webpage",
                reason=approval_reason or "action_requires_approval",
                request_payload={"url": node.query, "max_chars": 2000},
            )
            node.waiting_approval = True
            _update_tool_safety(
                tool_history,
                schema_validated=True,
                approval_required=True,
                sanitized_error=True,
            )
            _finish_tool_history(tool_history, status="error", error=approval["reason"])
            tool_histories.append(tool_history)
            node_outcomes.append(_make_node_outcome(
                node_id=node.node_id,
                tool_history=tool_history,
                tool_name="browse_webpage",
                status="awaiting_approval",
                retry_count=node.retry_count,
                error_category="approval_required",
                error_message=approval["reason"],
                approval_request_id=approval["approval_id"],
            ))
            return {
                "collected_evidence": [e.model_dump() for e in all_evidence],
                "tool_histories": tool_histories,
                "node_outcomes": node_outcomes,
                "pending_approvals": [approval],
                "agent_trace": trace,
            }
        node.status = StepStatus.RUNNING

        try:
            from app.organization_corpus import admit_corpus_request
            from app.external_evidence import reusable_task_source,observed_instant,freshness
            from app.data_governance import authorize_network,classify_source
            authorize_network(node.query,(state.get('query_understanding') or {}).get('network_context'),operation='read')
            org_config = state.get('organization_research')
            validator=admit_corpus_request(node.query,org_config)
            candidates=[item for item in state.get('collected_evidence',[]) if reusable_task_source(item,node.query,state.get('query_understanding'))]
            # Freshness uses the observed fetch instant. Legacy collection labels
            # may be naive or absent even when transport metadata is trustworthy.
            cached=max(candidates,key=lambda item:observed_instant(
                (item.get('acquisition') or {}).get('source_fetched_at') or item.get('collected_at'))) if candidates else None
            if cached:
                validator(cached['source_url'])
                from app.graph.state import BrowserResult
                results = [BrowserResult(url=cached['source_url'], title=cached.get('source_title') or cached['source_url'],
                    extracted_content=cached['content'], acquisition=cached.get('acquisition'),
                    collected_at=cached.get('collected_at'), backend=cached['source_backend'], channel='web')]
                agent.last_channel_attempts=[{'channel':'web','backend':'task-cache','status':'success','call_count':0,'result_count':1}]
                _update_tool_safety(tool_history, reused_task_evidence=True, evidence_id=cached['evidence_id'],
                    freshness=freshness(cached,state.get('query_understanding'),for_cache=True))
            else:
                from app.external_evidence import collect_public_source
                results=collect_public_source(node.query,org_config,state.get('query_understanding'),agent,
                    owner_id=state.get('session',{}).get('owner_id'),max_calls=remaining_calls,timeout_seconds=remaining_seconds)
            attempts = getattr(agent, "last_channel_attempts", [])
            if attempts:
                trace.append(_append_trace_event(state, EventType.TOOL_COMPLETE if any(r.extracted_content for r in results) else EventType.TOOL_ERROR,
                                                "browser", "渠道读取结果", {"channel_attempts": attempts}))
                _update_tool_safety(tool_history, channel_attempts=attempts)
            browser_error = next(
                (result.error_message for result in results if getattr(result, "error_message", None)),
                None,
            )
            has_content = any((result.extracted_content or "").strip() for result in results)
            if browser_error and not has_content:
                raise RuntimeError(browser_error)
            node.result = {"results": [r.model_dump() for r in results]}
            node.confidence = 0.85 if results else 0.0
            _finish_tool_history(
                tool_history,
                status="success",
                result_summary=f"{len(results)} browser pages",
            )
            _update_tool_safety(tool_history, schema_validated=True)
            node.status = StepStatus.DONE
            node.last_error = None
            node.last_error_category = None
            node.terminal_failure = False

            for r in results:
                if cached:
                    continue
                if not r.extracted_content.strip():
                    continue
                evidence = Evidence(
                    content=r.extracted_content,
                    acquisition={**(r.acquisition or {}),'data_governance':classify_source(
                        backend=r.backend,channel=r.channel,url=node.query,content=r.extracted_content,
                        declared=((r.acquisition or {}).get('data_governance') or {}).get('data_class'))},
                    source_url=r.url,
                    source_title=r.title,
                    source_type="web",
                    collected_by=AgentType.BROWSER,
                    source_channel=r.channel,
                    source_backend=r.backend,
                    **({"collected_at": r.collected_at} if r.collected_at else {}),
                )
                all_evidence.append(evidence)

            trace.append(_append_trace_event(
                state, EventType.TOOL_COMPLETE, "browser",
                f"Extracted {len(results)} pages for: {node.query}",
                {"tool_name": "browse_webpage", "status": "success", "result_summary": f"{len(results)} browser pages"},
            ))
            node_outcomes.append(_make_node_outcome(
                node_id=node.node_id,
                tool_history=tool_history,
                tool_name="browse_webpage",
                status="success",
                retry_count=node.retry_count,
                result_count=len(results),
            ))
        except (OSError, RuntimeError, TypeError, ValueError, KeyError) as e:
            node.status = StepStatus.FAILED
            node.retry_count += 1
            category = _classify_error_category(str(e))
            node.last_error = str(e)
            node.last_error_category = category
            node.terminal_failure = _is_terminal_error_category(category)
            trace.append(_append_trace_event(
                state,
                EventType.TOOL_ERROR,
                "browser",
                f"Browse failed: {e!s}",
                {"tool_name": "browse_webpage", "status": "error", "error": str(e)},
            ))
            attempts=getattr(agent,'last_channel_attempts',[])
            if getattr(e,'channel_attempts',None) is not None:attempts=e.channel_attempts
            elif getattr(e,'network_call_count',None) is not None:
                attempts=[{'channel':'web','backend':'pinned-http','status':'failed',
                    'call_count':e.network_call_count,'result_count':0,'error_category':category}]
            if attempts:_update_tool_safety(tool_history,channel_attempts=attempts)
            _finish_tool_history(tool_history, status="error", error=str(e))
            node_outcomes.append(_make_node_outcome(
                node_id=node.node_id,
                tool_history=tool_history,
                tool_name="browse_webpage",
                status="terminal_error" if node.terminal_failure else "retryable_error",
                retry_count=node.retry_count,
                error_category=category,
                error_message=str(e),
            ))
        tool_histories.append(tool_history)

    trace.append(AgentEvent(
        agent="browser",
        event_type="agent_complete",
        content=f"Collected {len(all_evidence)} evidence from browser"
    ).model_dump())

    return {
        "collected_evidence": [e.model_dump() for e in all_evidence],
        "tool_histories": tool_histories,
        "node_outcomes": node_outcomes,
        "agent_trace": trace,
    }


def rag_node(state: ResearchState) -> dict:
    """
    内部资料检索工具：用户启用后补充研究证据（主题 3）。

    主题 3: 工具驱动多 Agent
    - 从 DAG 获取当前批次中类型为 rag 的节点
    - 执行混合检索（Rerank + Citation）
    - 使用 pgvector 向量检索

    输入: dag, current_executing_nodes
    输出: collected_evidence, tool_histories, agent_trace
    """
    from app.graph.state import AgentEvent, Evidence
    from app.guardrails import record_guardrail_event, validate_tool_invocation
    from app.observability.trace import EventType

    dag = deserialize_dag(state["dag"])
    executing_nodes = state.get("executing_nodes", state.get("current_executing_nodes", []))

    rag_nodes = [
        n for n in dag.nodes
        if n.node_id in executing_nodes and n.node_type == "rag"
    ]

    if not rag_nodes:
        return {"collected_evidence": [], "tool_histories": [], "agent_trace": [], "node_outcomes": []}

    if "rag" not in _effective_tool_allowlist(state, state.get("guardrail_decision") or {}):
        return {
            "collected_evidence": [], "tool_histories": [], "agent_trace": [],
            "node_outcomes": [
                _make_node_outcome(node_id=node.node_id, tool_history={}, tool_name="knowledge_base_search", status="skipped", error_category="internal_docs_not_allowed")
                for node in rag_nodes
            ],
        }

    from app.agents.rag import RAGAgent

    trace = [
        _append_trace_event(state, EventType.AGENT_START, "rag", f"Executing {len(rag_nodes)} RAG nodes")
    ]

    agent = RAGAgent()
    all_evidence = []
    tool_histories = []
    node_outcomes = []
    budget = _research_budget(state)
    max_results = budget.get("rag_max_results", 8)

    for node in rag_nodes:
        remaining_calls,remaining_seconds=_channel_budget(state, tool_histories)
        if not remaining_calls or not remaining_seconds:
            node_outcomes.append(_make_node_outcome(node_id=node.node_id, tool_history={}, tool_name="execute_rag", status="skipped", error_category="budget_exceeded"))
            continue
        trace.append(_append_trace_event(
            state,
            EventType.TOOL_START,
            "rag",
            f"Retrieving: {node.query}",
            {"tool_name": "knowledge_base_search", "args": {"query": node.query}},
        ))
        tool_history = _make_tool_history(
            agent_type=AgentType.RAG,
            tool_name="execute_retrieval",
            task_id=state.get("task_id"),
            query=node.query,
        )
        valid, reason = validate_tool_invocation("knowledge_base_search", {"query": node.query, "top_k": 10})
        if not valid:
            node.status = StepStatus.FAILED
            node.terminal_failure = True
            node.last_error = reason or "invalid_args"
            node.last_error_category = "schema_validation"
            _update_tool_safety(tool_history, schema_validated=False, sanitized_error=True)
            _finish_tool_history(tool_history, status="error", error=reason or "invalid_args")
            record_guardrail_event(
                state,
                agent="rag",
                event_type="tool_blocked",
                content=reason or "invalid_args",
                metadata={"tool": "knowledge_base_search", "query": node.query},
            )
            tool_histories.append(tool_history)
            node_outcomes.append(_make_node_outcome(
                node_id=node.node_id,
                tool_history=tool_history,
                tool_name="knowledge_base_search",
                status="terminal_error",
                retry_count=node.retry_count,
                error_category="schema_validation",
                error_message=reason or "invalid_args",
            ))
            continue
        require_approval, approval_reason = should_require_action_approval(
            tool_name="knowledge_base_search",
            decision=state.get("guardrail_decision") and build_guardrail_decision(
                _guardrail_question(state),
                user_confirmed=state.get("user_confirmed", False),
            ),
            readonly=True,
        )
        if require_approval and not approved_action(state, node, "knowledge_base_search", {"query": node.query, "top_k": 10}):
            approval = _make_approval_request(
                node_id=node.node_id,
                tool_name="knowledge_base_search",
                reason=approval_reason or "action_requires_approval",
                request_payload={"query": node.query, "top_k": 10},
            )
            node.waiting_approval = True
            _update_tool_safety(
                tool_history,
                schema_validated=True,
                approval_required=True,
                sanitized_error=True,
            )
            _finish_tool_history(tool_history, status="error", error=approval["reason"])
            tool_histories.append(tool_history)
            node_outcomes.append(_make_node_outcome(
                node_id=node.node_id,
                tool_history=tool_history,
                tool_name="knowledge_base_search",
                status="awaiting_approval",
                retry_count=node.retry_count,
                error_category="approval_required",
                error_message=approval["reason"],
                approval_request_id=approval["approval_id"],
            ))
            return {
                "collected_evidence": [e.model_dump() for e in all_evidence],
                "tool_histories": tool_histories,
                "node_outcomes": node_outcomes,
                "pending_approvals": [approval],
                "agent_trace": trace,
            }
        node.status = StepStatus.RUNNING

        try:
            from app.retrieval_filters import frozen_filter_policy
            business_filter=frozen_filter_policy((state.get('query_understanding') or {}).get('internal_filter'))
            from app.retrieval_candidates import VERSION as CANDIDATE_VERSION
            retrieval_policy=(state.get('query_understanding') or {}).get('internal_retrieval') or {}
            if retrieval_policy and retrieval_policy.get('version')!=CANDIDATE_VERSION:
                raise ValueError('frozen_internal_retrieval_contract_invalid')
            from app.candidate_fusion import frozen_policy
            results = agent.execute_retrieval(
                node.query,
                state["user_query"],
                group=state.get("rag_group"),
                owner_id=state.get("session", {}).get("owner_id"),
                session_id=state.get("session", {}).get("session_id"),
                filters=business_filter,
                timeout_seconds=remaining_seconds,
                mode=retrieval_policy.get('mode','hybrid'),
                fusion=frozen_policy((state.get('query_understanding') or {}).get('candidate_fusion')),
                query_type=(state.get('query_understanding') or {}).get('query_type'),
            )[:max_results]
            node.result = {"results": [r.model_dump() for r in results],"retrieval_channels":agent.last_channel_status}
            node.confidence = 0.88 if results else 0.0
            _finish_tool_history(
                tool_history,
                status="success",
                result_summary=f"{len(results)} rag chunks",
            )
            _update_tool_safety(tool_history, schema_validated=True,retrieval_channels=agent.last_channel_status)
            node.status = StepStatus.DONE
            node.last_error = None
            node.last_error_category = None
            node.terminal_failure = False

            for r in results:
                evidence = Evidence(
                    content=r.content,
                    source_url=r.metadata.get("url") if r.metadata else None,
                    source_title=(r.metadata.get("title") or r.metadata.get('source_name') or r.metadata.get('file_name')) if r.metadata else None,
                    source_type="knowledge_base",
                    collected_by=AgentType.RAG,
                    acquisition={'format':'internal_chunk','coverage':'retrieved_internal_chunk','chunk_id':r.chunk_id,
                        'source_document_id':r.metadata.get('source_id'),'source_content_version':r.metadata.get('content_hash'),
                        'parse_version_id':r.metadata.get('parse_version_id'),'document_structure_reference':r.metadata.get('document_structure_reference'),
                        'chunk_reference':r.metadata.get('chunk_reference'),'chunk_profile_id':r.metadata.get('chunk_profile_id'),
                        'returned_span':r.metadata.get('returned_span'),'parent_context_gap':r.metadata.get('parent_context_gap'),
                        'source_lead_excerpt':r.metadata.get('source_lead_excerpt'),
                        'feature_profile_id':r.metadata.get('feature_profile_id'),
                        'dense_profile':r.metadata.get('dense_profile'),'dense_input_coverage':r.metadata.get('dense_input_coverage'),
                        'retrieval_channel_status':r.metadata.get('retrieval_channel_status'),'temporal_view':r.metadata.get('temporal_view'),
                        'retrieval_routes':r.metadata.get('retrieval_routes'),'retrieval_selector':r.metadata.get('retrieval_selector'),
                        'structure_path':r.metadata.get('structure_path'),
                        'candidate_fusion':r.metadata.get('candidate_fusion'),
                        'index_generation_id':r.metadata.get('index_generation_id'),'lexical_statistics':r.metadata.get('lexical_statistics'),
                        'source_access_revision':r.metadata.get('source_access_revision'),
                        'source_access_snapshot':r.metadata.get('source_access_snapshot'),
                        'retrieval_score_scope':r.metadata.get('retrieval_score_scope'),
                        'chunk_index':r.metadata.get('chunk_index'),'chunk_count':r.metadata.get('chunk_count')},
                )
                all_evidence.append(evidence)

            trace.append(_append_trace_event(
                state, EventType.TOOL_COMPLETE, "rag",
                f"Retrieved {len(results)} chunks for: {node.query}",
                {"tool_name": "knowledge_base_search", "status": "success", "result_summary": f"{len(results)} rag chunks",
                    'retrieval_channels':agent.last_channel_status},
            ))
            node_outcomes.append(_make_node_outcome(
                node_id=node.node_id,
                tool_history=tool_history,
                tool_name="knowledge_base_search",
                status="success",
                retry_count=node.retry_count,
                result_count=len(results),
            ))
        except (OSError, RuntimeError, TypeError, ValueError, KeyError) as e:
            node.status = StepStatus.FAILED
            node.retry_count += 1
            category = _classify_error_category(str(e))
            node.last_error = str(e)
            node.last_error_category = category
            node.terminal_failure = _is_terminal_error_category(category)
            trace.append(_append_trace_event(
                state,
                EventType.TOOL_ERROR,
                "rag",
                f"RAG retrieval failed: {e!s}",
                {"tool_name": "knowledge_base_search", "status": "error", "error": str(e),
                    'retrieval_channels':agent.last_channel_status},
            ))
            _update_tool_safety(tool_history,retrieval_channels=agent.last_channel_status)
            _finish_tool_history(tool_history, status="error", error=str(e))
            node_outcomes.append(_make_node_outcome(
                node_id=node.node_id,
                tool_history=tool_history,
                tool_name="knowledge_base_search",
                status="terminal_error" if node.terminal_failure else "retryable_error",
                retry_count=node.retry_count,
                error_category=category,
                error_message=str(e),
            ))
        tool_histories.append(tool_history)

    trace.append(AgentEvent(
        agent="rag",
        event_type="agent_complete",
        content=f"Collected {len(all_evidence)} evidence from RAG"
    ).model_dump())

    return {
        "collected_evidence": [e.model_dump() for e in all_evidence],
        "tool_histories": tool_histories,
        "node_outcomes": node_outcomes,
        "agent_trace": trace,
    }


# ==============================================================
# 主题 1 & 3: 批量执行 - Fan-out / Fan-in
# ==============================================================

def execute_tool_batch(state: ResearchState) -> list[Send]:
    """
    批量执行工具（主题 1 & 3）。

    主题 1: 自主工作流的并行执行
    主题 3: 工具驱动的多 Agent 协作

    从当前批次节点中，根据节点类型分发到对应的工具 Agent。
    返回 Send 列表，实现并行执行。
    """
    executing_nodes = state.get("current_executing_nodes", [])

    if not executing_nodes:
        return [Send("dag_aggregator", state)]

    dag = deserialize_dag(state["dag"])
    decision = state.get("guardrail_decision") or {}
    enabled_tools = _effective_tool_allowlist(state, decision)
    sends = []

    for node_id in executing_nodes:
        node = next((n for n in dag.nodes if n.node_id == node_id), None)
        if not node:
            continue

        # 根据节点类型分发
        if node.node_type in ("search", "browser", "rag", "mcp") and node.node_type in enabled_tools:
            sends.append(Send(node.node_type, tool_payload(state, dag, node)))

    return sends or [Send("dag_aggregator", state)]


# ==============================================================
# 主题 1 & 5: Analyst / Reflection / Report Nodes
# ==============================================================

async def analyst_node(state: ResearchState) -> dict:
    """
    Analyst Agent: 综合证据生成分析（主题 1）。

    主题 1: 自主工作流中的分析阶段
    输入所有收集到的证据，生成结构化分析

    输入: collected_evidence
    输出: analysis, agent_trace
    """
    from app.agents.analyst import AnalystAgent
    from app.source_lifecycle import current_synthesis_state
    state=await current_synthesis_state(state)
    # A failed acquisition remains a failed step, while the root is actively
    # synthesizing the retained material. Do not mirror it as a failed root.
    state={**state,'runtime_status':RuntimeStatus.RUNNING.value}
    from app.organization_findings import build_organization_findings
    from app.graph.state import AgentEvent, deserialize_evidence
    from app.observability.trace import EventType

    from app.research_context import reuse_retained_synthesis
    reused=reuse_retained_synthesis(state,_synthesis_question(state),
        _skill_prompt(state,'analyst') or None,_agent_skill_hints(state,'analyst'))
    if reused is not None:
        control={**(state.get('iteration_control') or {}),'action':'report',
            'reason':'unchanged_material_analysis_reused',
            'no_gain_rounds':int((state.get('iteration_control') or {}).get('no_gain_rounds') or 0)+1,
            'semantic_review':'final_report_claim_audit_still_required'}
        return {**reused,'runtime_status':RuntimeStatus.RUNNING.value,
            'evidence_access_gaps':state.get('evidence_access_gaps',[]),
            'revision_needed':False,'iteration_control':control,
            'agent_trace':[_append_trace_event(state,EventType.AGENT_COMPLETE,'analyst',
                '补证未增加正文或资料版本，保留已完成分析并进入正文审核；不代表原结论已核实。',
                {'reason':control['reason'],'model_calls':0})]}

    evidence_list = [deserialize_evidence(e) for e in state.get("collected_evidence", [])]
    organization_result = build_organization_findings(state.get("organization_research"), state.get("collected_evidence", []), None)
    evidence_gate = build_evidence_gate(evidence_list)
    decision = state.get("guardrail_decision") or {}
    reject_if_no_evidence = bool(decision.get("reject_if_no_evidence", True))

    start_event = _append_trace_event(
        state, EventType.AGENT_START, "analyst",
        f"Analyzing {len(evidence_list)} evidence items"
    )

    if not evidence_gate.allowed and reject_if_no_evidence:
        message = build_answer_gate_message(evidence_gate)
        record_guardrail_event(
            state,
            agent="analyst",
            event_type="answer_gate",
            content=message,
            metadata=evidence_gate.model_dump(),
        )
        trace = [start_event, AgentEvent(
            agent="analyst",
            event_type="agent_complete",
            content=message,
        ).model_dump()]
        return {
            "analysis": message,
            "runtime_status": RuntimeStatus.RUNNING.value,
            'evidence_access_gaps':state.get('evidence_access_gaps',[]),
            "organization_result": organization_result,
            "evidence_status": evidence_gate.model_dump(),
            "revision_needed": False,
            "agent_trace": trace,
        }

    agent = AnalystAgent()
    agent.request_budget = _stage_model_budget(state,'analyst')
    agent.model_routing=state.get('model_routing')
    loop=asyncio.get_running_loop()
    checkpoint_sequence=int(state.get('session',{}).get('checkpoint_seq') or 0)
    async def save_question(progress):
        nonlocal checkpoint_sequence
        from app.governance.runtime import RuntimePersistence
        from app.observability.sse_manager import get_sse_manager
        if progress.get('status')=='running' and progress.get('active_phase') not in progress.get('completed',{}):
            current=await current_synthesis_state(state)
            retained={item.get('evidence_id') for item in current.get('collected_evidence',[])}
            if retained!={item.evidence_id for item in evidence_list}:
                state['evidence_access_gaps']=current.get('evidence_access_gaps',[])
                raise TokenBudgetExceeded('analysis_sources_changed')
        session,budget=_apply_llm_usage_to_state(state,'analyst',_agent_model_usage(agent))
        checkpoint={**state,'analysis_workflow':progress,'session':session,'budget_state':budget}
        sequence=await RuntimePersistence().persist_analysis_checkpoint(str(state['task_id']),checkpoint)
        if sequence is None:raise TokenBudgetExceeded('analysis_checkpoint_unavailable')
        checkpoint_sequence=sequence
        state['session']['checkpoint_seq']=sequence
        state['analysis_workflow']=progress
        from app.execution_control import current_control
        control=current_control()
        if control:await control.mirror_runtime()
        recovered=progress.get('active_phase') in progress.get('completed',{}) and bool(
            (progress.get('recovery_counts') or {}).get(progress.get('active_phase')))
        await get_sse_manager().publish(str(state['task_id']),EventType.STATE_UPDATE.value,{
            'agent':'analyst','status':'running','analysis_progress':{'phase':progress.get('active_phase'),
                'status':progress['status'],'completed_steps':len(progress['completed'])},
            **({'recovery':{'status':'resolved','message':'自动修复后，当前分析问题已完成。'}} if recovered else {})})
    def on_question(progress):
        future=asyncio.run_coroutine_threadsafe(save_question(progress),loop)
        try:future.result(timeout=30)
        except TokenBudgetExceeded:raise
        except Exception as error:
            future.cancel()
            raise TokenBudgetExceeded('analysis_checkpoint_unavailable') from error
    agent.on_capability_upgrade=lambda decision:on_question(agent.last_workflow)
    try:
        analysis_text = await asyncio.to_thread(agent.analyze,_synthesis_question(state),evidence_list,
            skill_prompt=_skill_prompt(state, 'analyst') or None,
            analyst_hints=_agent_skill_hints(state, "analyst"),organization_research=state.get("organization_research"),
            resume_state=state.get('analysis_workflow'),on_progress=on_question)
    except TokenBudgetExceeded as error:
        return _model_budget_pause(state,agent,'analyst',error)
    organization_result = build_organization_findings(
        state.get("organization_research"), state.get("collected_evidence", []), agent.last_organization_data,
    )
    if organization_result:
        organization_result['source_checks']['analyst_excerpt_evidence_ids'] = agent.last_evidence_ids
        organization_result['extraction'] = agent.last_extraction_status
        organization_result['analyst_context'] = agent.last_context_manifest
    elif agent.last_context_manifest:
        organization_result={'analyst_context':agent.last_context_manifest}
    previous_drawing=(state.get('organization_result') or {}).get('chart_rendering')
    if isinstance(previous_drawing,dict) and previous_drawing.get('cache_id'):
        # Carry only a prior trusted result as a cache candidate. The renderer
        # still compares current data/policy/owner/evidence before any reuse.
        organization_result={**(organization_result or {}),'chart_rendering':previous_drawing}
    session, budget_state = _apply_llm_usage_to_state(state, "analyst", _agent_model_usage(agent))
    session['checkpoint_seq']=checkpoint_sequence

    complete_content = (
        "Analysis complete without external evidence"
        if not evidence_gate.allowed
        else "Analysis complete"
    )
    complete_event = _append_trace_event(state, EventType.AGENT_COMPLETE, "analyst", complete_content)

    trace = [start_event, complete_event, AgentEvent(
        agent="analyst",
        event_type="agent_complete",
        content=f"Generated {len(analysis_text)} chars of analysis from {len(evidence_list)} evidence items"
    ).model_dump()]

    return {
        "analysis": analysis_text,
        "runtime_status": RuntimeStatus.RUNNING.value,
        'analysis_workflow':agent.last_workflow or None,
        'evidence_access_gaps':state.get('evidence_access_gaps',[]),
        "organization_result": organization_result,
        "evidence_status": evidence_gate.model_dump(),
        "session": session,
        "budget_state": budget_state,
        "agent_trace": trace,
    }


async def reflection_node(state: ResearchState) -> dict:
    """
    Reflection Agent: 自校验与验证（主题 1 & 5）。

    主题 5: Self-Reflection & Verification
    - 校验分析的事实性、一致性、完整性
    - 检测幻觉声明
    - 决定是否需要重规划

    输入: analysis, collected_evidence
    输出: verification, revision_needed, agent_trace
    """
    from app.agents.reflection import ReflectionAgent
    from app.source_lifecycle import current_synthesis_state
    state=await current_synthesis_state(state)
    from app.graph.state import AgentEvent, deserialize_evidence
    from app.observability.trace import EventType, emit_event

    evidence_list = [deserialize_evidence(e) for e in state.get("collected_evidence", [])]
    if not evidence_list and (state.get("guardrail_decision") or {}).get("reject_if_no_evidence", True):
        verification = VerificationResult(needs_revision=False).model_dump()
        control = iteration_decision({**state, 'verification': verification, 'revision_needed': False},
            PlanningPolicy.model_validate(state.get('planning_policy') or {}))
        control.update(action='report', reason='no_accessible_evidence')
        return {"verification": verification, "revision_needed": False, 'iteration_control': control,
            'evidence_access_gaps':state.get('evidence_access_gaps',[]),'analysis':state.get('analysis',''),'organization_result':state.get('organization_result')}

    emit_event(
        state, EventType.AGENT_START, "reflection",
        f"Validating analysis with {len(evidence_list)} evidence items"
    )

    agent = ReflectionAgent()
    agent.request_budget = _stage_model_budget(state,'reflection')
    agent.model_routing=state.get('model_routing')
    try:
        verification: VerificationResult = await asyncio.to_thread(agent.reflect,
            _research_question(state),state["analysis"],evidence_list,
            skill_prompt=_skill_prompt(state, 'reflection') or None,
            reflection_hints=_agent_skill_hints(state, "reflection"),organization_research=state.get('organization_research'))
    except TokenBudgetExceeded as error:
        if (not agent.request_budget.calls and state.get('analysis') and error.reason in {
                'token_budget_exhausted','insufficient_context_budget','model_time_reservation_exhausted'}):
            session,budget_state = _apply_llm_usage_to_state(state,'reflection',_agent_model_usage(agent))
            return {'session':session,'budget_state':budget_state,'revision_needed':False,
                'verification':VerificationResult(needs_revision=False).model_dump(),
                'iteration_control':{'action':'report','reason':'preserve_final_report_and_audit_allowance'},
                'agent_trace':[{'agent':'reflection','event_type':'agent_complete',
                    'content':'反思阶段余量不足，保留报告及最终审核额度；未执行本轮反思。'}]}
        return _model_budget_pause(state,agent,'reflection',error)
    session, budget_state = _apply_llm_usage_to_state(state, "reflection", _agent_model_usage(agent))

    # 追踪校验结果
    if verification.needs_revision:
        emit_event(
            state, EventType.AGENT_COMPLETE, "reflection",
            f"Verification failed: confidence={verification.overall_confidence:.2f}, "
            f"hallucination_rate={verification.hallucination_rate:.2%}, "
            f"needs_revision=True"
        )
    else:
        emit_event(
            state, EventType.AGENT_COMPLETE, "reflection",
            f"Verification passed: confidence={verification.overall_confidence:.2f}, "
            f"citation_coverage={verification.citation_coverage:.2%}"
        )

    trace = [AgentEvent(
        agent="reflection",
        event_type="agent_complete",
        content=f"Verification: confidence={verification.overall_confidence:.2f}, "
                f"needs_revision={verification.needs_revision}"
    ).model_dump()]

    control = iteration_decision({**state, 'verification': verification.model_dump(),
        'revision_needed': verification.needs_revision, 'budget_state': budget_state},
        PlanningPolicy.model_validate(state.get('planning_policy') or {}))
    trace.append(AgentEvent(agent='reflection', event_type='iteration_decision',
        content=f"{control['action']}: {control['reason']}").model_dump())
    return {
        "verification": verification.model_dump(),
        'iteration_control': control,
        'evidence_access_gaps':state.get('evidence_access_gaps',[]),
        'analysis':state.get('analysis',''),'organization_result':state.get('organization_result'),
        "revision_needed": verification.needs_revision,
        "session": session,
        "budget_state": budget_state,
        "agent_trace": trace,
    }


def should_revise(state: ResearchState) -> str:
    """
    条件路由：判断是否需要重规划（主题 5）。

    主题 5: 自校验失败 → 重规划循环
    - 检查 verification.needs_revision
    - 检查 revision_count < max_revisions
    """
    if state.get('status') == 'paused':
        return 'budget_stop'
    control = state.get('iteration_control') or iteration_decision(state,
        PlanningPolicy.model_validate(state.get('planning_policy') or {}))
    return {'replan': 'replan', 'pause': 'approval_reviewer'}.get(control['action'], 'generate_report')


def replan_node(state: ResearchState) -> dict:
    """
    重规划节点：增加重规划计数，重置 DAG（主题 1 & 5）。

    主题 5: 重新调用 Planner Agent 生成新的 DAG
    主题 1: 自主工作流的迭代循环
    """
    from app.research_context import capture_retained_synthesis
    retained=capture_retained_synthesis(state,_synthesis_question(state),
        _skill_prompt(state,'analyst') or None,_agent_skill_hints(state,'analyst'))
    revision_count = state.get("revision_count", 0) + 1

    session = state.get("session", {})
    session["revision_count"] = revision_count
    session["updated_at"] = utc_now_naive().isoformat()

    from app.agents.planner import PlannerAgent

    failure_memory = state.get("failure_memory")
    planning_hints = _format_failure_memory_notes(failure_memory)
    agent = PlannerAgent()
    agent.request_budget = _stage_model_budget(state,'replan')
    agent.model_routing=state.get('model_routing')
    try:
        dag = agent.create_dag(state['user_query'],query_contract=_plan_contract(state),
            planning_strategy=PlanningPolicy.model_validate(state.get('planning_policy') or {}).strategy,
            query_type=(state.get('query_understanding') or {}).get('query_type'),
            analysis_depth=((state.get('query_understanding') or {}).get('slots') or {}).get('depth', 'auto'),
            planning_hints=planning_hints or None,skill_prompt=_skill_prompt(state, 'planner') or None,
            planner_hints=_agent_skill_hints(state, "planner"),use_internal_docs=bool(state.get("use_internal_docs", False)),
            rag_group=state.get("rag_group"),organization_research=state.get("organization_research"))
    except TokenBudgetExceeded as error:
        return {**_model_budget_pause(state,agent,'replan',error),'retained_synthesis':retained}
    dag = apply_source_policy(dag, state["user_query"], use_internal_docs=bool(state.get("use_internal_docs", False)))
    session, budget_state = _apply_llm_usage_to_state(state, "replan", _agent_model_usage(agent))
    dag = seed_organization_sources(dag, state.get("organization_research"))
    dag, manifest = _compile_execution_plan(state, dag, agent, 'revision_request:'+agent.last_plan_reason)

    from app.observability.trace import EventType, emit_event
    emit_event(
        state, EventType.AGENT_START, "replan",
        f"Replanning (attempt {revision_count})"
    )

    return {
        "revision_count": revision_count,
        'retained_synthesis':retained,
        'plan_manifest': manifest,
        'plan_history': [*(state.get('plan_history') or []), {key: manifest[key] for key in ('plan_version','revision','reason','strategy','adjustments')}][-32:],
        'agent_trace': [_append_trace_event(state, EventType.AGENT_COMPLETE, 'replan',
            '根据本轮修订请求更新研究计划。', {'plan_manifest':manifest,'kind':'plan_changed'})],
        "session": session,
        "dag": serialize_dag(dag),
        "completed_nodes": [],
        "current_executing_nodes": [],
        "collected_evidence": [],
        "analysis": "",
        "node_outcomes": [],
        "failure_memory": failure_memory,
        "budget_state": budget_state,
    }


async def report_node(state: ResearchState) -> dict:
    """
    Report Generator: 生成最终报告（主题 1）。

    主题 1: 自主工作流的输出阶段
    - 基于分析、证据、引用生成 Markdown 报告
    - 添加置信度和来源信息

    输入: analysis, collected_evidence, verification
    输出: final_report, status
    """
    from app.agents.report import ReportAgent, ReportContractError
    from app.db.report_delivery import report_binding
    from app.disclosure import ensure_report_disclosure,redact_text
    from app.source_lifecycle import current_synthesis_state
    state=await current_synthesis_state(state)
    from app.organization_findings import findings_context
    from app.organization_report import build_report_summary
    from app.organization_corpus import build_corpus
    from app.organization_actions import build_action_view
    from app.organization_statistics import build_statistics, apply_statistics
    from app.graph.state import AgentEvent, deserialize_evidence
    from app.llm_client import StreamInterruptedError
    from app.observability.sse_manager import get_sse_manager
    from app.observability.trace import EventType

    evidence_list = [deserialize_evidence(e) for e in state.get("collected_evidence", [])]
    evidence_gate = build_evidence_gate(evidence_list)
    decision = state.get("guardrail_decision") or {}
    reject_if_no_evidence = bool(decision.get("reject_if_no_evidence", True))
    verification = state.get("verification")
    session_id = state.get("task_id")
    sse = get_sse_manager()

    start_event = _append_trace_event(state, EventType.AGENT_START, "report", "Generating final report")
    organization_result = state.get('organization_result')
    from app.organization_taxonomy import classify_publications
    org_config = state.get('organization_research') or {}
    if org_config.get('taxonomy'):
        organization_result = {**(organization_result or {}), 'classification': classify_publications(
            org_config['taxonomy'], organization_result or {}, state.get('collected_evidence', []), org_config['scope'])}
    corpus = build_corpus(state.get('organization_research'), organization_result,
        state.get('collected_evidence', []), state.get('tool_histories', []))
    if corpus:
        organization_result = {**(organization_result or {}), 'corpus': corpus}
    if org_config:
        source_id=str(state['task_id'])+':'+str(state.get('session',{}).get('execution_id') or 'execution-not-recorded')
        statistics=build_statistics(org_config,organization_result,state.get('collected_evidence',[]),source_id=source_id)
        organization_result=apply_statistics(organization_result or {},statistics)
    if (organization_result or {}).get('trend_view'):
        trend = {**organization_result['trend_view']}
        trend['coverage_snapshot']={**trend['coverage_snapshot'],'corpus_counts':(corpus or {}).get('counts'),
            'taxonomy_version':(org_config.get('taxonomy') or {}).get('version')}
        organization_result={**organization_result,'trend_view':trend}
    if org_config and 'actions' in org_config.get('modules',[]):
        organization_result={**(organization_result or {}),'actions':build_action_view(org_config,organization_result,
            state.get('collected_evidence',[]),(organization_result or {}).get('action_proposals'),state=state)}

    if not evidence_gate.allowed and reject_if_no_evidence:
        message = build_answer_gate_message(evidence_gate)
        record_guardrail_event(
            state,
            agent="report",
            event_type="answer_gate",
            content=message,
            metadata=evidence_gate.model_dump(),
        )
        trace = [start_event, AgentEvent(
            agent="report",
            event_type="agent_complete",
            content=message,
        ).model_dump()]
        session = dict(state.get("session", {}))
        session["status"] = TaskStatus.PAUSED.value
        session["completed_at"] = None
        from app.organization_purpose import analysis_snapshot, assemble_module_report
        empty_report = '# 研究报告\n\n现有资料不足以形成研究结论。\n'
        if analysis_snapshot(state.get('organization_research')):
            empty_report, delivery = assemble_module_report('', state['organization_research'], 0,
                statistics=(organization_result or {}).get('statistics'))
            organization_result = {**(organization_result or {}), 'module_report': delivery}
            summary = build_report_summary(state['organization_research'], organization_result, state.get('collected_evidence', []))
            organization_result['report_summary'] = summary
        return {
            "final_report": empty_report,
            'evidence_access_gaps':state.get('evidence_access_gaps',[]),
            "organization_result": organization_result,
            "citations": [],
            "status": TaskStatus.PAUSED.value,
            "runtime_status": RuntimeStatus.REPORT_PAUSED.value,
            "session": session,
            "review_status": {
                "blocked": True,
                "reason": "insufficient_evidence_for_report",
                **evidence_gate.model_dump(),
            },
            "agent_trace": trace,
        }

    agent = ReportAgent()
    agent.request_budget = _stage_model_budget(state,'report')
    agent.model_routing=state.get('model_routing')

    loop=asyncio.get_running_loop()

    async def save_report_upgrade(decision):
        from app.governance.runtime import RuntimePersistence
        current=await current_synthesis_state(state)
        if current.get('collected_evidence')!=state.get('collected_evidence'):
            state['evidence_access_gaps']=current.get('evidence_access_gaps',[])
            raise TokenBudgetExceeded('model_upgrade_sources_changed')
        session,budget=_apply_llm_usage_to_state(state,'report',_agent_model_usage(agent))
        record={**(organization_result or {})}
        if agent.last_module_report is not None:record['module_report']=agent.last_module_report
        if agent.last_audit is not None:record['audit_before_upgrade']=agent.last_audit
        sequence=await RuntimePersistence().persist_model_checkpoint(str(session_id),{
            **state,'organization_result':record,'session':session,'budget_state':budget,
            'agent_trace':[*state.get('agent_trace',[]),*agent.recovery_events]})
        if sequence is None:raise TokenBudgetExceeded('model_upgrade_checkpoint_unavailable')
        state['session']['checkpoint_seq']=sequence
        await sse.publish(session_id,EventType.STATE_UPDATE.value,{'model_upgrade':decision,'status':'running'})

    def on_report_upgrade(decision):
        future=asyncio.run_coroutine_threadsafe(save_report_upgrade(decision),loop)
        try:future.result(timeout=30)
        except TokenBudgetExceeded:raise
        except Exception as error:
            future.cancel()
            raise TokenBudgetExceeded('model_upgrade_checkpoint_unavailable') from error
    agent.on_capability_upgrade=on_report_upgrade

    report_budget = _build_budget_state(state)
    remaining_report_tokens = max(0, int(report_budget.get("max_total_tokens") or 0)
                                  - int(report_budget.get("used_total_tokens") or 0))
    remaining_report_seconds = max(0, float(report_budget.get("max_wall_clock_seconds") or 0)
                                   - float(report_budget.get("elapsed_wall_clock_seconds") or 0))
    try:
        report, citations = await asyncio.to_thread(agent.generate_stream,
            user_query=_synthesis_question(state),
            analysis=state["analysis"] + findings_context(organization_result),
            evidence_list=evidence_list,
            reflection=verification,
            output_length=state.get("output_length") or state.get("session", {}).get("output_length"),
            skill_prompt=_skill_prompt(state, 'report') or None,
            report_hints=_agent_skill_hints(state, "report"),
            # Provider streaming still settles actual usage. Reader publication
            # waits for the complete output, evidence audit and disclosure gate.
            on_chunk=None,
            on_citation=None,
            verification_token_budget=remaining_report_tokens,
            verification_timeout_seconds=remaining_report_seconds,
            organization_research=state.get("organization_research"),
            organization_statistics=(organization_result or {}).get('statistics'),
            technical_reading=(organization_result or {}).get('technical_reading'),
            analysis_workflow=state.get('analysis_workflow'),
            query_understanding=state.get('query_understanding'),
        )
    except TokenBudgetExceeded as error:
        return _model_budget_pause(state,agent,'report',error,
            report=agent.last_draft,citations=agent.last_citations)
    except ReportContractError:
        session, budget_state = _apply_llm_usage_to_state(state, 'report', _agent_model_usage(agent))
        session['status'] = TaskStatus.FAILED.value
        return {'status': TaskStatus.FAILED.value, 'runtime_status': RuntimeStatus.RETRYABLE_FAILED.value,
            'session': session, 'budget_state': budget_state,
            'organization_result': {**(organization_result or {}), 'module_report': agent.last_module_report,
                'report_context': agent.last_context_manifest},
            'review_status': {'blocked': True, 'retryable': True, 'last_error_category': 'report_contract_invalid',
                'output_stage':'report','report_binding':report_binding(state),
                'report_payload_kind':'partial_response',
                'partial_model_response': redact_text(agent.last_partial_response)},
            'agent_trace': [{'agent': 'report', 'event_type': 'agent_error',
                'content': '报告结构未通过校验；原始输出与用量已保留，可在剩余额度内修订。'}]}
    except StreamInterruptedError:
        session,budget_state = _apply_llm_usage_to_state(state,'report',_agent_model_usage(agent))
        session["status"] = TaskStatus.FAILED.value
        return {
            "status": TaskStatus.FAILED.value,
            "runtime_status": RuntimeStatus.RETRYABLE_FAILED.value,
            "session": session,
            'budget_state':budget_state,
            "review_status": {
                "blocked": False,
                "last_error_category": "llm_stream_interrupted",
                'output_stage':'report','report_binding':report_binding(state),
                'report_payload_kind':'partial_response',
                'partial_model_response':redact_text(agent.last_partial_response),
                "retryable": True,
            },
            "errors": ["llm_stream_interrupted_after_output"],
            "agent_trace": [start_event, AgentEvent(
                agent="report",
                event_type="agent_error",
                content="LLM stream interrupted after output; retry requires a new report request.",
            ).model_dump()],
        }
    if agent.last_module_report is not None:
        organization_result = {**(organization_result or {}), 'module_report': agent.last_module_report}
    if agent.last_context_manifest:
        organization_result = {**(organization_result or {}), 'report_context': agent.last_context_manifest}
    if agent.last_writing_plan:
        organization_result={**(organization_result or {}),'writing_plan':agent.last_writing_plan}
    report_summary = build_report_summary(state.get('organization_research'), organization_result,
                                         state.get('collected_evidence', []))
    if report_summary:
        organization_result = {**(organization_result or {}), 'report_summary': report_summary}
    # Statistics, provenance, configuration and audit belong to the saved
    # research record. The reader's report ends with its research and sources.
    if (agent.last_audit or {}).get('budget_incomplete') or (agent.last_audit or {}).get('audit_incomplete'):
        audit_reason='final_audit_budget_exhausted' if (agent.last_audit or {}).get('budget_incomplete') else 'final_audit_incomplete'
        paused = _model_budget_pause(state,agent,'report',TokenBudgetExceeded(audit_reason),
            report=report,citations=citations)
        paused['organization_result'] = organization_result
        return paused
    if not agent.last_audit or (agent.last_audit or {}).get('needs_review',True):
        paused=_model_budget_pause(state,agent,'report',TokenBudgetExceeded('final_report_needs_revision'),
            report=report,citations=citations)
        paused['organization_result']=organization_result
        return paused
    if not agent.request_budget.complete_audit(agent.last_audit):
        paused=_model_budget_pause(state,agent,'report',TokenBudgetExceeded('final_audit_reservation_not_released'),report=report,citations=citations)
        paused['organization_result']=organization_result
        return paused
    try:
        ensure_report_disclosure(report)
    except TokenBudgetExceeded as error:
        paused=_model_budget_pause(state,agent,'report',error,report=report,citations=citations)
        paused['organization_result']=organization_result
        return paused
    delivery_snapshot=((state.get('query_understanding') or {}).get('delivery') or {})
    drawing_mode=delivery_snapshot.get('drawing_mode','builtin')
    layout_view=None
    if delivery_snapshot.get('layout') is not None:
        from app.research_delivery import build_delivery_view
        current=await current_synthesis_state(state)
        if current.get('collected_evidence')!=state.get('collected_evidence'):
            state['evidence_access_gaps']=current.get('evidence_access_gaps',[])
            return _model_budget_pause(state,agent,'report',TokenBudgetExceeded('report_sources_changed_before_publication'),report=report,citations=citations)
        layout_view=build_delivery_view(task_id=str(state['task_id']),execution_id=state.get('session',{}).get('execution_id'),
            query=state['user_query'],report=report,citations=[item.model_dump() for item in citations],
            understanding=state.get('query_understanding'),organization_result=organization_result,audit=agent.last_audit)
        binding=layout_view['layout_binding']
        organization_result={**(organization_result or {}),'layout_binding_status':{
            'schema_version':binding['schema_version'],'status':binding['status'],'missing':binding['missing']}}
        if binding['required_missing']:
            paused=_model_budget_pause(state,agent,'report',TokenBudgetExceeded('layout_required_data_missing'),report=report,citations=citations)
            paused['organization_result']=organization_result
            paused['review_status']['layout_missing']=binding['required_missing']
            from app.research_diagnostics import diagnose_stop
            paused['review_status']['pause_diagnosis']=diagnose_stop({**state,**paused})
            paused['agent_trace'][-1]['content']=paused['review_status']['pause_diagnosis']['summary']
            return paused
    rendering_trace=[]
    layout_without_figures=layout_view is not None and not any(page.get('charts') for page in layout_view['pages'])
    if drawing_mode!='builtin' and not layout_without_figures:
        from app.research_delivery import build_delivery_view
        from app.research_figures import execute_drawing
        # The next model phase must not receive newly revoked private data.
        current=await current_synthesis_state(state)
        if current.get('collected_evidence')!=state.get('collected_evidence'):
            state['evidence_access_gaps']=current.get('evidence_access_gaps',[])
            return _model_budget_pause(state,agent,'report',TokenBudgetExceeded('drawing_sources_changed'),report=report,citations=citations)
        view=layout_view or build_delivery_view(task_id=str(state['task_id']),execution_id=state.get('session',{}).get('execution_id'),
            query=state['user_query'],report=report,citations=[item.model_dump() for item in citations],
            understanding=state.get('query_understanding'),organization_result=organization_result,audit=agent.last_audit)
        policy=((state.get('query_understanding') or {}).get('delivery') or {}).get('drawing_policy') or {}
        from app.llm_budget import budgeted_client
        drawing_client,drawing_model=budgeted_client(agent.client,agent.request_budget,'render'),agent.model
        if state.get('model_routing'):
            from app.model_routing import routed_binding,data_bound_snapshot
            from app.llm_budget import budgeted_client
            try:
                raw,drawing_model,_=routed_binding('render',data_bound_snapshot(state['model_routing'],agent.request_budget.data_governance))
                drawing_client=budgeted_client(raw,agent.request_budget,'render')
            except TokenBudgetExceeded as error:
                paused=_model_budget_pause(state,agent,'report',error,report=report,citations=citations)
                paused['organization_result']=organization_result
                return paused
        from app.planning_control import retained_evidence_version
        drawing=await asyncio.to_thread(execute_drawing,view,policy,client=drawing_client,model=drawing_model,budget=agent.request_budget,
            previous=(organization_result or {}).get('chart_rendering'),
            cache_context={'owner_id':state.get('session',{}).get('owner_id'),'evidence_version':retained_evidence_version(state)})
        organization_result={**(organization_result or {}),'chart_rendering':drawing}
        if drawing['status']!='rendered':
            paused=_model_budget_pause(state,agent,'report',TokenBudgetExceeded('drawing_skill_incomplete'),report=report,citations=citations)
            paused['organization_result']=organization_result
            paused['review_status']['drawing_reason']=drawing.get('reason')
            return paused
        rendering_trace.append(_append_trace_event(state,EventType.AGENT_COMPLETE,'report',
            f"{'复用有效图表' if drawing.get('cache_status')=='hit' else '绘图Skill已生成'}{len(drawing['assets'])}组SVG/PNG/PDF；图像人工复核尚未进行。"))
    session, budget_state = _apply_llm_usage_to_state(state, "report", _agent_model_usage(agent))
    if budget_state.get('hard_stop_reason') in {'token_limit','cost_limit','wall_clock_limit'}:
        reason='model_time_reservation_exhausted' if budget_state['hard_stop_reason']=='wall_clock_limit' else 'token_budget_exhausted'
        paused=_model_budget_pause(state,agent,'report',TokenBudgetExceeded(reason),report=report,citations=citations)
        paused['organization_result']=organization_result
        return paused

    current=await current_synthesis_state(state)
    if current.get('collected_evidence')!=state.get('collected_evidence'):
        state['evidence_access_gaps']=current.get('evidence_access_gaps',[])
        paused=_model_budget_pause(state,agent,'report',TokenBudgetExceeded('report_sources_changed_before_publication'),report=report,citations=citations)
        paused['organization_result']=organization_result
        return paused
    if session_id:
        await sse.publish(session_id,EventType.REPORT_CHUNK.value,
            {'agent':'report','chunk':report,'is_partial':False,'reviewed':True})
        for citation in citations:
            await sse.publish(session_id,EventType.REPORT_CITATION.value,{
                'agent':'report','citation_id':citation.citation_id,
                'source':citation.source_title or citation.source_url or '',
                'source_url':citation.source_url,'source_title':citation.source_title})

    # 更新会话状态
    session["status"] = TaskStatus.COMPLETED.value
    session["completed_at"] = utc_now_naive().isoformat()

    complete_event = _append_trace_event(state, EventType.AGENT_COMPLETE, "report", f"Report generated: {len(report)} chars")

    trace = [start_event, *agent.recovery_events, *rendering_trace, complete_event, AgentEvent(
        agent="report",
        event_type="agent_complete",
        content=f"Report: {len(report)} chars, {len(citations)} citations"
    ).model_dump()]

    return {
        "final_report": report,
        'evidence_access_gaps':state.get('evidence_access_gaps',[]),
        "organization_result": organization_result,
        "runtime_status": RuntimeStatus.COMPLETED.value,
        "citations": [c.model_dump() for c in citations],
        "status": TaskStatus.COMPLETED.value,
        "session": session,
        "budget_state": budget_state,
        "review_status": {
            "blocked": False,
            **evidence_gate.model_dump(),
            "verification": verification,
            "final_report_audit": agent.last_audit,
            'output_stage':'report','report_binding':report_binding(state),
            'report_payload_kind':'report',
        },
        "agent_trace": trace,
    }


# ==============================================================
# 主题 1: Graph 编译
# ==============================================================

def compile_research_graph() -> StateGraph:
    """
    编译并返回完整的研究 StateGraph（主题 1）。

    架构（5 大主题的整合）：

    START → planner (生成 DAG)
           ↓ (主题 2: DAG 生成)
      dag_executor (分发节点批次)
           ↓ (Send API: 主题 1 & 3 并行执行)
      search / browser / rag (工具调用)
           ↓ (主题 2: 结果聚合)
      should_continue_dag (条件路由)
           ↓ continue / analyst
      analyst (综合分析)
           ↓ (主题 5: 自校验)
      reflection (验证)
           ↓ (主题 5: 条件分支)
      replan ← (重规划循环，最多 3 次)
           ↓ generate_report
      report (报告生成)
           ↓
          END
    """
    settings = get_settings()

    # 构建图
    builder = StateGraph(ResearchState)

    # === 节点定义 ===
    builder.add_node("planner", planner_node)
    builder.add_node("dag_executor", dag_executor_node)
    builder.add_node("dag_aggregator", dag_results_aggregator)
    builder.add_node("approval_reviewer", approval_reviewer_node)
    builder.add_node("approval_resume", lambda state: {"runtime_status": RuntimeStatus.RUNNING.value, "status": TaskStatus.RUNNING.value})
    builder.add_node("analysis_resume", lambda state: {"runtime_status": RuntimeStatus.RUNNING.value, "status": TaskStatus.RUNNING.value})
    builder.add_node("report_resume", lambda state: {"runtime_status": RuntimeStatus.RUNNING.value, "status": TaskStatus.RUNNING.value})
    builder.add_node("user_resume", lambda state: {"runtime_status": RuntimeStatus.RUNNING.value, "status": TaskStatus.RUNNING.value})
    builder.add_node("analyst", analyst_node)
    from app.research_recovery import automatic_recovery_node,recovery_eligible
    builder.add_node('automatic_recovery',automatic_recovery_node)
    builder.add_node("reflection", reflection_node)
    builder.add_node("replan", replan_node)
    builder.add_node("report", report_node)

    # 工具节点（通过 Send API 调用）
    builder.add_node("search", bound_tool_node(search_node))
    builder.add_node("browser", bound_tool_node(browser_node))
    builder.add_node("rag", bound_tool_node(rag_node))
    builder.add_node("mcp", bound_tool_node(mcp_node))

    # === 边定义 ===
    # 入口
    builder.add_edge(START, "planner")

    # Planner → DAG 执行器
    builder.add_conditional_edges('planner',lambda state:'stop' if state.get('status') == 'paused' else 'continue',
        {'stop':END,'continue':'dag_executor'})

    # DAG 执行器 → 工具节点（并行）
    builder.add_conditional_edges(
        "dag_executor",
        execute_tool_batch,
        ["search", "browser", "rag", "mcp", "dag_aggregator"],
    )

    # 工具节点 → 结果聚合
    builder.add_edge("search", "dag_aggregator")
    builder.add_edge("browser", "dag_aggregator")
    builder.add_edge("rag", "dag_aggregator")
    builder.add_edge("mcp", "dag_aggregator")

    # 结果聚合 → 判断是否继续 DAG 或进入分析
    builder.add_conditional_edges(
        "dag_aggregator",
        should_continue_dag,
        {
            "continue": "dag_executor",  # 继续执行下一批节点
            "approval_reviewer": "approval_reviewer",
            "analyst": "analyst",         # DAG 全部完成，进入分析
        },
    )

    builder.add_edge("approval_reviewer", END)
    builder.add_edge("approval_resume", "dag_executor")
    builder.add_edge("analysis_resume", "analyst")
    builder.add_edge("report_resume", "report")
    from app.db.research_pause import RESUME_NODES
    builder.add_conditional_edges('user_resume',lambda state:state['session']['user_resume_node'],
        {node:node for node in RESUME_NODES})

    # 分析 → 反思
    builder.add_conditional_edges('analyst',lambda state:('recover' if recovery_eligible(state) else 'stop') if state.get('status') == 'paused'
        else 'report' if (state.get('iteration_control') or {}).get('reason')=='unchanged_material_analysis_reused'
        else 'continue', {'stop':END,'continue':'reflection','report':'report','recover':'automatic_recovery'})
    builder.add_conditional_edges('automatic_recovery',lambda state:'analyst' if state.get('status')=='running' else 'stop',
        {'analyst':'analyst','stop':END})

    # 反思 → 重规划或报告（条件分支）
    builder.add_conditional_edges(
        "reflection",
        should_revise,
        {
            "replan": "replan",
            "generate_report": "report",
            "approval_reviewer": "approval_reviewer",
            'budget_stop':END,
        },
    )

    # 重规划 → DAG 执行器（重新开始）
    builder.add_conditional_edges('replan',lambda state:'stop' if state.get('status') == 'paused' else 'continue',
        {'stop':END,'continue':'dag_executor'})

    # 报告 → 结束
    builder.add_edge("report", END)

    # === 检查点配置（主题 4）===
    checkpointer = None

    if settings.redis.url:
        try:
            import redis as sync_redis
            from langgraph.checkpoint.redis import RedisSaver
            r = sync_redis.from_url(settings.redis.url)
            checkpointer = RedisSaver(r)
        except (ImportError, OSError, RuntimeError, TypeError, ValueError, KeyError):
            logger.warning("Redis checkpointer is unavailable; using in-memory checkpoints")

    if not checkpointer:
        from langgraph.checkpoint.memory import MemorySaver
        checkpointer = MemorySaver()

    return builder.compile(checkpointer=checkpointer)
async def mcp_node(state: ResearchState) -> dict:
    """MCP tool node guarded by McpPolicyProxy."""
    from app.graph.state import AgentEvent
    from app.observability.trace import EventType

    dag = deserialize_dag(state["dag"])
    executing_nodes = state.get("executing_nodes", state.get("current_executing_nodes", []))
    mcp_nodes = [n for n in dag.nodes if n.node_id in executing_nodes and n.node_type == "mcp"]
    if not mcp_nodes:
        return {"collected_evidence": [], "tool_histories": [], "agent_trace": [], "node_outcomes": []}

    proxy = McpPolicyProxy()
    trace = [
        _append_trace_event(state, EventType.AGENT_START, "mcp", f"Executing {len(mcp_nodes)} MCP nodes")
    ]
    tool_histories = []
    node_outcomes = []
    for node in mcp_nodes:
        if not _channel_budget(state, tool_histories)[0]:
            node_outcomes.append(_make_node_outcome(node_id=node.node_id, tool_history={}, tool_name="mcp_proxy", status="skipped", error_category="budget_exceeded"))
            continue
        tool_history = _make_tool_history(
            agent_type=AgentType.BROWSER,
            tool_name="mcp_proxy",
            task_id=state.get("task_id"),
            query=node.query,
        )
        from app.organization_corpus import source_scope
        org_config = state.get('organization_research')
        if source_scope(org_config) or ((org_config or {}).get('corpus') or {}).get('collection_mode') == 'seeds_only':
            _finish_tool_history(tool_history, status='error', error='unsupported_source_transport')
            tool_histories.append(tool_history)
            node_outcomes.append(_make_node_outcome(node_id=node.node_id, tool_history=tool_history,
                tool_name='mcp_proxy', status='terminal_error', error_category='unsupported_source_transport'))
            continue
        request = McpToolRequest(
            session_id=state.get("task_id"),
            decision_id=None,
            tool_name=node.query.split(":", 1)[-1] if ":" in node.query else node.query,
            requested_args={"query": node.query},
            server_id=node.query.split(":", 1)[0] if ":" in node.query else "default",
            owner_id=state.get("session", {}).get("owner_id"),
            node_id=node.node_id,
            revision_count=state.get("revision_count", 0),
            data_class=((state.get('query_understanding') or {}).get('network_context') or {}).get('data_class','internal'),
            data_policy_id=((state.get('query_understanding') or {}).get('network_context') or {}).get('policy_id'),
        )
        _update_tool_safety(tool_history,data_class=request.data_class,data_policy_id=request.data_policy_id)
        for approval in state.get("approval_decisions", []):
            if (approval.get("status") == "approved" and approval.get("node_id") == node.node_id
                    and approval.get("bound_query") == node.query
                    and approval.get("revision_count") == state.get("revision_count", 0)):
                request.approval_id = approval["approval_id"]
                break
        result = await proxy.invoke(request)
        if result.status == "awaiting_approval":
            approval = result.approval_request or _make_approval_request(
                node_id=node.node_id,
                tool_name=request.tool_name,
                reason="mcp_write_requires_approval",
                request_payload={"server_id": request.server_id, "args": request.requested_args},
            )
            approval["node_id"] = node.node_id
            approval["bound_query"] = node.query
            _update_tool_safety(
                tool_history,
                approval_required=True,
                sanitized_error=True,
                read_only_default=False,
            )
            _finish_tool_history(tool_history, status="error", error=approval["reason"])
            tool_histories.append(tool_history)
            node_outcomes.append(_make_node_outcome(
                node_id=node.node_id,
                tool_history=tool_history,
                tool_name=request.tool_name,
                status="awaiting_approval",
                retry_count=node.retry_count,
                error_category="approval_required",
                error_message=approval["reason"],
                approval_request_id=approval["approval_id"],
            ))
            return {
                "tool_histories": tool_histories,
                "node_outcomes": node_outcomes,
                "pending_approvals": [approval],
                "agent_trace": trace,
            }
        if result.status == "terminal_error":
            _update_tool_safety(
                tool_history,
                sanitized_error=True,
                redaction_applied=result.redaction_applied,
            )
            _finish_tool_history(tool_history, status="error", error=result.error_message or result.error_category or "mcp_error")
            tool_histories.append(tool_history)
            node_outcomes.append(_make_node_outcome(
                node_id=node.node_id,
                tool_history=tool_history,
                tool_name=request.tool_name,
                status="terminal_error",
                retry_count=node.retry_count,
                error_category=result.error_category,
                error_message=result.error_message,
            ))
            continue
        _finish_tool_history(tool_history, status="success", result_summary=result.result_summary or "mcp success")
        _update_tool_safety(
            tool_history,
            schema_validated=True,
            redaction_applied=result.redaction_applied,
            server_trusted=True,
        )
        tool_history["tool_calls"][-1]["server_fingerprint"] = result.server_fingerprint
        tool_histories.append(tool_history)
        node_outcomes.append(_make_node_outcome(
            node_id=node.node_id,
            tool_history=tool_history,
            tool_name=request.tool_name,
            status="success",
            retry_count=node.retry_count,
            result_count=1 if result.payload is not None else 0,
        ))
        trace.append(AgentEvent(
            agent="mcp",
            event_type="tool_complete",
            content=f"MCP tool {request.tool_name} succeeded",
        ).model_dump())
    return {
        "collected_evidence": [],
        "tool_histories": tool_histories,
        "node_outcomes": node_outcomes,
        "agent_trace": trace,
    }
