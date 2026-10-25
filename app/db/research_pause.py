"""Owner-bound cooperative pause at a durable graph boundary."""
from __future__ import annotations

from datetime import UTC, datetime
from app.db.json import dumps_json
from app.db.execution_control import decoded, receipt_budget, task_budget

RESUME_NODES = {'planner', 'dag_executor', 'dag_aggregator', 'analyst',
                'reflection', 'replan', 'report', 'approval_reviewer'}


async def request_pause(conn, session_id, owner_id, request):
    await conn.execute("SELECT set_config('lock_timeout','3000',true)")
    await conn.execute("SELECT set_config('statement_timeout','10000',true)")
    row = await conn.fetchrow('''SELECT status,execution_id,review_status FROM research_sessions
        WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE''', str(session_id), str(owner_id))
    if not row:
        raise ValueError('pause_task_not_found')
    if not row['execution_id'] or str(row['execution_id']) != str(request.execution_id):
        raise ValueError('pause_execution_changed_reload')
    review = decoded(row['review_status'])
    prior = review.get('user_control') or {}
    if prior.get('request_id') == str(request.request_id) and row['status'] in {'running', 'paused'}:
        return {'session_id': str(session_id), 'execution_id': str(row['execution_id']),
                'status': row['status'], 'user_control': prior, 'replayed': True}
    if row['status'] != 'running':
        raise ValueError('pause_task_not_running')
    control = {'action': 'pause', 'state': 'requested', 'request_id': str(request.request_id),
               'execution_id': str(row['execution_id']), 'requested_at': datetime.now(UTC).isoformat()}
    await conn.execute('''UPDATE research_sessions SET review_status=
        jsonb_set(COALESCE(review_status,'{}'::jsonb),'{user_control}',$3::jsonb,true),updated_at=NOW()
        WHERE id=$1::uuid AND owner_id=$2::uuid''', str(session_id), str(owner_id), dumps_json(control))
    return {'session_id': str(session_id), 'execution_id': str(row['execution_id']),
            'status': 'running', 'user_control': control, 'replayed': False}


async def pause_at_boundary(conn, binding, next_nodes):
    """Read the just-persisted snapshot, never replace newer model checkpoints."""
    session, owner, execution = (binding[k] for k in ('session_id', 'owner_id', 'execution_id'))
    row = await conn.fetchrow('''SELECT s.status,s.execution_id,s.review_status,s.total_tokens,
        s.total_cost_usd,r.state_snapshot_json FROM research_sessions s
        JOIN session_runtime_state r ON r.session_id=s.id
        WHERE s.id=$1::uuid AND s.owner_id=$2::uuid FOR UPDATE OF s,r''', session, owner)
    if not row or row['status'] != 'running' or str(row['execution_id']) != execution:
        return None
    review = decoded(row['review_status'])
    requested = review.get('user_control') or {}
    if requested.get('state') != 'requested' or requested.get('execution_id') != execution:
        return None
    next_nodes = list(next_nodes)
    if not next_nodes:
        return None  # Natural completion wins at the final boundary.
    if set(next_nodes) <= {'search', 'browser', 'rag', 'mcp'}:
        resume_node = 'dag_executor'
    elif len(next_nodes) == 1 and next_nodes[0] in RESUME_NODES:
        resume_node = next_nodes[0]
    else:
        return None
    state = decoded(row['state_snapshot_json'])
    if state.get('status') != 'running':
        return None  # A system stop is not a user pause.
    budget = await receipt_budget(conn, session, owner, task_budget(row))
    control = {**requested, 'state': 'paused', 'resume_node': resume_node,
               'paused_at': datetime.now(UTC).isoformat()}
    review.update(runtime_status='user_paused', reason='user_requested_pause',
                  user_control=control, budget_state=budget)
    state.update(status='paused', runtime_status='user_paused', review_status=review, budget_state=budget)
    state['session'] = {**state.get('session', {}), 'status': 'paused', 'user_resume_node': resume_node}
    await conn.execute('''UPDATE research_sessions SET status='paused',review_status=$3::jsonb,
        updated_at=NOW() WHERE id=$1::uuid AND owner_id=$2::uuid''', session, owner, dumps_json(review))
    await conn.execute('''UPDATE session_runtime_state SET state_snapshot_json=$2::jsonb,
        public_status='paused',runtime_status='user_paused',checkpoint_seq=checkpoint_seq+1,
        last_heartbeat_at=NOW() WHERE session_id=$1::uuid''', session, dumps_json(state))
    return {'session_id': session, 'execution_id': execution, 'status': 'paused',
            'runtime_status': 'user_paused', 'user_control': control}
