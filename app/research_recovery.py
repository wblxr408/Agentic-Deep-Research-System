"""One deterministic recovery step, within the existing research graph."""
from __future__ import annotations

from app.research_diagnostics import diagnose_stop


def recovery_eligible(state):
    return bool((diagnose_stop(state,active_execution=True) or {}).get('automatic_recovery',{}).get('eligible'))


async def automatic_recovery_node(state):
    from copy import deepcopy
    import time
    from app.graph.compiler import _build_budget_state,_stage_model_budget,_synthesis_question,_skill_prompt,_agent_skill_hints
    from app.research_context import analysis_input_matches
    from app.graph.state import deserialize_evidence
    from app.source_lifecycle import current_synthesis_state
    from app.db.connection import get_db_pool
    from app.db.execution_control import decoded,receipt_budget,task_budget
    from app.db.json import dumps_json
    from app.execution_control import current_control,check_execution
    from app.observability.sse_manager import get_sse_manager
    check_execution()
    if not recovery_eligible(state):return {}
    review=dict(state.get('review_status') or {})
    def blocked(message):
        review['automatic_recovery_blocked']=message
        review['pause_diagnosis']=diagnose_stop({**state,'review_status':review})
        return {'review_status':review}
    current=await current_synthesis_state(state)
    if current.get('collected_evidence')!=state.get('collected_evidence'):
        return blocked('当前资料访问已变化，系统没有继续派发')
    if not analysis_input_matches(state,_synthesis_question(state),_skill_prompt(state,'analyst') or None,
            _agent_skill_hints(state,'analyst'),[deserialize_evidence(item) for item in state.get('collected_evidence',[])]):
        return blocked('当前输入与保存的分析检查点不匹配')
    binding=current_control().binding;sid,owner,execution=(binding[k] for k in ('session_id','owner_id','execution_id'))
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        row=await conn.fetchrow('''SELECT s.status,s.execution_id,s.review_status,s.total_tokens,s.total_cost_usd,
            r.state_snapshot_json FROM research_sessions s JOIN session_runtime_state r ON r.session_id=s.id
            WHERE s.id=$1::uuid AND s.owner_id=$2::uuid FOR UPDATE OF s,r''',sid,owner)
        if not row or str(row['execution_id'])!=execution or row['status']!='paused':return {}
        saved=decoded(row['state_snapshot_json']);review=decoded(row['review_status'])
        if (review.get('user_control') or {}).get('state')=='requested':return blocked('已收到你的暂停请求，系统没有自动继续')
        if not recovery_eligible({**saved,'review_status':review}):return {}
        budget=await receipt_budget(conn,sid,owner,task_budget(row))
        restored={**deepcopy(saved),'budget_state':budget}
        budget=_build_budget_state(restored)
        allowance=_stage_model_budget({**restored,'budget_state':budget},'analyst')
        workflow=restored.get('analysis_workflow') or {}
        failures=(workflow.get('failed_attempts') or {}).get(workflow.get('active_phase')) or []
        context=(failures[-1].get('context') if failures else None) or {}
        required=max(1024,int(context.get('prompt_bound') or 0)+8192)
        if allowance.available()<required:
            return blocked(f'自动恢复需要约 {required:,} Token，原分析份额只剩 {allowance.available():,} Token')
        if (budget.get('hard_stop_reason') not in {None,'tool_call_limit'}
                or allowance.deadline is None or time.monotonic()>=allowance.deadline
                or int(budget.get('inflight_model_requests') or 0)):
            return blocked('原分析份额、执行期限或在途用量尚不允许自动恢复')
        root={**restored['session'],'status':'running','automatic_recovery_attempts':1}
        review.update(runtime_status='running',reason=None,
            automatic_recovery={'status':'running','attempts':1,'limit':1,'cause':'analysis_provider_unavailable'})
        review.pop('automatic_recovery_blocked',None)
        budget['model_stop_reason']=None
        restored.update(session=root,budget_state=budget,status='running',runtime_status='running',review_status=review)
        await conn.execute('''UPDATE research_sessions SET status='running',review_status=$3::jsonb,
            completed_at=NULL,updated_at=NOW() WHERE id=$1::uuid AND owner_id=$2::uuid''',sid,owner,dumps_json(review))
        await conn.execute('''UPDATE session_runtime_state SET state_snapshot_json=$2::jsonb,
            public_status='running',runtime_status='running',checkpoint_seq=checkpoint_seq+1,last_heartbeat_at=NOW()
            WHERE session_id=$1::uuid''',sid,dumps_json(restored))
    await get_sse_manager().publish(sid,'state_update',{'agent':'analyst','recovery':{
        'status':'running','attempts':1,'limit':1,'message':'已定位到模型连接故障，正在原额度内自动恢复一次。'}})
    return {'session':root,'budget_state':budget,'status':'running','runtime_status':'running','review_status':review}
