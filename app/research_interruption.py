"""Owner-requested recovery at a committed acquisition boundary."""
from datetime import UTC,datetime


def temporary_planner_throttling(body):
    if not isinstance(body,dict):return False
    error=body.get('error',body)
    if not isinstance(error,dict):return False
    return (error.get('type') in {'throttling_error','rate_limit_exceeded'}
        and str(error.get('code') or '') in {'429','rate_limit_exceeded'})


def planner_throttling_repair(record,state):
    """Recognize only a retained pre-plan throttling failure, never arbitrary 429 text."""
    failure=(state.get('review_status') or {}).get('workflow_failure') or {}
    if (record['status']!='failed' or failure.get('error_type')!='RateLimitError'
            or failure.get('execution_id')!=str(record['execution_id'])
            or failure.get('interrupted_batch') or state.get('dag') or state.get('plan_manifest')
            or state.get('analysis_workflow') or state.get('collected_evidence')
            or (state.get('planning_policy') or {}).get('strategy','hybrid')!='hybrid'):return False
    message=failure.get('message')
    prefix='Error code: 429 - '
    if not isinstance(message,str) or not message.startswith(prefix) or len(message)>4096:return False
    # Older retained failures contain the SDK's literal body, not a new user field.
    import ast
    try:body=ast.literal_eval(message[len(prefix):])
    except (SyntaxError,ValueError,TypeError,RecursionError):return False
    return temporary_planner_throttling(body)


def heartbeat_expired(value):
    if not isinstance(value,datetime):return False
    if value.tzinfo is None:value=value.replace(tzinfo=UTC)
    return (datetime.now(UTC)-value).total_seconds()>=120


def binding_repair(record,state):
    review=state.get('review_status') or {}
    failure=review.get('workflow_failure') or {}
    recovery=review.get('execution_recovery') or {}
    return (record['status']=='failed' and failure.get('error_type')=='PlanningError'
        and failure.get('message')=='plan_execution_binding_conflict'
        and failure.get('execution_id')==str(record['execution_id'])
        and recovery.get('reason')=='worker_interrupted'
        and recovery.get('execution_id')==str(record['execution_id']))


def acquisition_resume_node(record,state,budget):
    from app.execution_control import execution_is_active
    if ((record['status']!='running' and not binding_repair(record,state) and not planner_throttling_repair(record,state)) or not heartbeat_expired(record.get('last_heartbeat_at'))
            or execution_is_active(state.get('task_id'),record['execution_id'])
            or state.get('analysis_workflow') or state.get('pending_approvals')
            or int((state.get('session') or {}).get('execution_recovery_attempts') or 0)>=2
            or budget.get('inflight_model_requests') or budget.get('reserved_inflight_tokens')
            or budget.get('reserved_inflight_tool_calls')):return None
    start=record.get('created_at')
    if not isinstance(start,datetime):return None
    if start.tzinfo is None:start=start.replace(tzinfo=UTC)
    if ((datetime.now(UTC)-start).total_seconds()>=int(budget.get('max_wall_clock_seconds') or 0)
            or int(budget.get('used_total_tokens') or 0)>=int(budget.get('max_total_tokens') or 0)
            or int(budget.get('used_tool_calls') or 0)>=int(budget.get('max_tool_calls') or 0)):return None
    if any(row.get('status')=='running' for row in (state.get('dag') or {}).get('nodes',[])):return None
    if any(row.get('node_type')=='mcp' or (row.get('node_type') not in {'search','browser','rag'} and row.get('node_id')!='root_synthesis')
            for row in (state.get('dag') or {}).get('nodes',[])):return None
    if any('payload' in row for row in (state.get('tool_result_envelopes') or {}).values()):return None
    return 'dag_executor' if state.get('dag') else 'planner'
