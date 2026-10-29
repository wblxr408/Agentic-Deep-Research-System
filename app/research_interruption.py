"""Owner-requested recovery at a committed acquisition boundary."""
from datetime import UTC,datetime


def heartbeat_expired(value):
    if not isinstance(value,datetime):return False
    if value.tzinfo is None:value=value.replace(tzinfo=UTC)
    return (datetime.now(UTC)-value).total_seconds()>=120


def acquisition_resume_node(record,state,budget):
    from app.execution_control import execution_is_active
    if (record['status']!='running' or not heartbeat_expired(record.get('last_heartbeat_at'))
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
