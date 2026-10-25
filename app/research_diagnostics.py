"""Explain retained stop evidence; never ask a model to guess the cause."""
from __future__ import annotations

from datetime import UTC, datetime

TRANSIENT = {'APIConnectionError', 'APITimeoutError', 'InternalServerError', 'RateLimitError'}
PHASES = {'planner':'研究规划','analyst':'研究分析','report':'报告生成','reflection':'来源核对',
          'extract_publications':'成果整理','landscape':'研究布局','evolution':'研究演进',
          'deep_dive':'成果深读','relationships':'组织与学者关系','actions':'合作建议','validation':'来源核对'}


def diagnose_stop(state,*,active_execution=False):
    if state.get('status') not in {'paused','failed'}:return None
    review=state.get('review_status') or {};budget=state.get('budget_state') or review.get('budget_state') or {}
    root=state.get('session') or {};workflow=state.get('analysis_workflow') or {}
    reason=review.get('reason') or workflow.get('stop_reason') or budget.get('model_stop_reason') or budget.get('hard_stop_reason')
    failure=review.get('workflow_failure') or {}
    reason=reason or failure.get('category') or review.get('last_error_category') or state.get('runtime_status') or 'unknown'
    reason=str(reason)
    phase=review.get('output_stage') or failure.get('stage') or ('report' if reason.startswith('final_') else 'analyst')
    active=workflow.get('active_phase') or ''
    if active and phase=='analyst':phase=active.split(':')[1] if active.startswith('question:') else active.split(':')[0]
    attempts=int(root.get('automatic_recovery_attempts') or 0)
    used=int(budget.get('used_total_tokens') or 0);maximum=int(budget.get('max_total_tokens') or 0)
    remaining=max(0,maximum-used);seconds=None
    try:
        start=datetime.fromisoformat(state.get('created_at') or root['created_at'])
        if start.tzinfo is None:start=start.replace(tzinfo=UTC)
        seconds=max(0,int(float(budget['max_wall_clock_seconds'])-(datetime.now(UTC)-start).total_seconds()))
    except (ValueError,TypeError,KeyError):pass
    blockers=[]
    if review.get('automatic_recovery_blocked'):blockers.append(review['automatic_recovery_blocked'])
    if maximum and remaining==0:blockers.append('本次 Token 额度已用完')
    if seconds==0:blockers.append('本次执行期限已到')
    if budget.get('max_cost_usd') is not None and float(budget.get('used_cost_usd') or 0)>=float(budget['max_cost_usd']):
        blockers.append('本次费用额度已用完')
    result={'schema_version':'adrs-stop-diagnosis-v1','reason':reason,'phase':PHASES.get(phase,'研究执行'),
        'summary':'','findings':[],'blockers':blockers,'next_step':'','action':'restart',
        'remaining_tokens':remaining,'remaining_seconds':seconds,
        'automatic_recovery':{'attempts':attempts,'limit':1,'eligible':False,'status':'exhausted' if attempts else 'not_applicable'}}
    if state.get('runtime_status')=='user_paused':
        result.update(summary='研究已按你的要求暂停',next_step='由你决定何时继续。',action='resume')
        return result
    audit=review.get('final_report_audit') or {}
    revisions=audit.get('revision_requests') or []
    if reason=='final_report_needs_revision':
        result['summary']=f'报告核对发现 {len(revisions)} 项内容需要修订' if revisions else '报告核对发现需要修订的内容'
        for item in revisions[:100]:
            result['findings'].append({'text':str(item.get('text') or '')[:240],
                'detail':str(item.get('requested_action') or item.get('reason') or '需要补充依据或调整结论')[:240]})
        revision=audit.get('revision_attempt') or {}
        if revision.get('attempted'):
            result['next_step']='系统已尝试修订，当前仍有未解决的问题；需补充对应资料后继续。'
        elif revision.get('status')=='unmapped_paragraphs':
            result['next_step']='核对问题无法定位到可自动修改的正文段落，已保留具体主张。'
        else:result['next_step']='需补充对应来源并修订正文。'
        result['revision_count']=len(revisions)
    elif reason in {'insufficient_context_budget','model_context_capability_exceeded'}:
        failures=(workflow.get('failed_attempts') or {}).get(active) or []
        admission=(failures[-1].get('admission') if failures else None) or {}
        result.update(summary='当前问题的原文与输出超出本阶段可用上下文',next_step='缩小本轮研究范围，或选择更大上下文的已授权模型。',action='settings')
        if admission:result['findings']=[{'text':'已核对本次输入额度','detail':f"输入预估 {admission.get('prompt_bound','未知')} Token，可用 {admission.get('available_tokens','未知')} Token。"}]
        if admission.get('reason')=='no_acquired_source_fits' and admission.get('selected_sources')==0:
            result.update(summary='当前问题没有选入可分析的原文片段',
                next_step='系统未找到符合本问题选取条件的原文；需要补充原文或调整研究范围。',action='sources')
            result['findings']=[{'text':'本问题选入原文 0 份','detail':f'本次仍剩余 {remaining:,} Token；停止原因不是总额度用完。'}]
        if all(isinstance(admission.get(key),(int,float)) for key in ('prompt_bound','requested_output_tokens','available_tokens')):
            required=int(admission['prompt_bound'])+int(admission['requested_output_tokens'])
            if required>int(admission['available_tokens']):
                result.update(summary='原分析份额不足以同时容纳输入和输出',action='restart',
                    next_step='需要选择更大的研究额度或缩小当前问题；更换大上下文模型不会增加本阶段份额。')
                result['findings']=[{'text':f"本次输入与预留输出共需 {required:,} Token",
                    'detail':f"本阶段可用 {int(admission['available_tokens']):,} Token，总任务仍剩余 {remaining:,} Token。"}]
    elif reason=='analysis_provider_unavailable':
        failures=(workflow.get('failed_attempts') or {}).get(active) or []
        error_type=(failures[-1].get('provider_error_type') if failures else None)
        transient=error_type in TRANSIENT
        result.update(summary='模型服务连接或响应暂时失败' if transient else '模型服务未能完成本阶段请求',
            next_step='系统将使用原配置尝试恢复一次。' if transient and attempts==0 else '系统已尝试自动恢复，模型服务仍未恢复。' if attempts else '系统未取得可分类的服务错误，已停止重试；可选择另一已授权模型。',
            action='none' if transient and attempts==0 else 'settings')
        eligible=bool(transient and attempts==0 and not blockers and seconds is not None and seconds>5 and remaining>=1024
            and workflow.get('schema_version')=='adrs-analysis-questions-v2' and workflow.get('status')=='paused'
            and int((workflow.get('attempts') or {}).get(active,0))<2
            and not state.get('pending_approvals') and (review.get('user_control') or {}).get('state')!='requested')
        if eligible and not active_execution:
            result.update(next_step='已定位到临时模型连接故障，原分析检查点已保留。',action='none')
        result['automatic_recovery'].update(eligible=eligible and active_execution,
            status=('planned' if active_execution else 'available') if eligible else 'exhausted' if attempts else 'blocked')
        if not eligible and not attempts and transient and not blockers:
            if int((workflow.get('attempts') or {}).get(active,0))>=2:detail='当前问题已尝试两次，达到本阶段上限。'
            elif (review.get('user_control') or {}).get('state')=='requested':detail='已收到你的暂停请求，系统没有自动继续。'
            elif state.get('pending_approvals'):detail='下一步仍需要你的操作授权。'
            elif seconds is None:detail='原任务的期限记录不完整，系统没有派发新请求。'
            elif seconds<=5:detail='原任务的执行期限即将结束，系统没有派发新请求。'
            elif remaining<1024:detail='原任务剩余额度不足以完成一次分析恢复。'
            else:detail='当前任务没有兼容的分析恢复检查点。'
            result.update(next_step=detail,action='restart')
        if error_type in {'AuthenticationError','PermissionDeniedError'}:
            result.update(summary='模型服务拒绝当前凭证或访问权限',next_step='需要更新本账号的模型凭证或授权。',action='settings')
    elif reason in {'final_audit_budget_exhausted','final_audit_incomplete','final_audit_reservation_not_released'}:
        result.update(summary='报告来源核对未完成',next_step='需要保留足够的核对额度后再生成报告。')
        result['findings']=[{'text':'停止发生在报告核对阶段','detail':'总 Token 剩余不代表核对阶段还有可用份额。'}]
    elif state.get('pending_approvals') or state.get('runtime_status')=='awaiting_approval':
        result.update(summary='下一步操作需要你的授权',next_step='请选择是否允许已列出的操作。',action='approval')
    elif any(part in reason for part in ('authorization','sources_changed','data_governance','data_class','access_credentials')):
        result.update(summary='当前资料或操作权限不满足执行要求',next_step='需要你选择可访问的资料或授予所需权限。',action='sources')
    elif any(part in reason for part in ('model_rout','no_eligible_model','model_endpoint','configuration')):
        result.update(summary='没有满足本阶段要求的模型配置',next_step='需要为本账号选择符合资料权限和上下文要求的模型。',action='settings')
    elif any(part in reason for part in ('budget','token_limit','cost_limit','wall_clock','tool_call_limit')):
        result.update(summary='本阶段已达到配置的执行额度',next_step='需要你决定是否调整额度或缩小研究范围。')
    else:
        result.update(summary=f"{result['phase']}未能完成，系统已保留停止位置",next_step='系统尚未取得足以确定根因的结构化记录。',action='restart')
        if failure.get('message'):result['findings']=[{'text':'实际执行错误','detail':str(failure['message'])[:360]}]
        result['diagnosis_complete']=bool(failure.get('message'))
    if blockers:
        if review.get('automatic_recovery_blocked'):
            result['next_step']='系统已检查自动恢复条件，没有派发新的模型请求。'
        result['next_step']+=' '+ '；'.join(blockers)+'，需要你决定新的范围或额度。'
        result['automatic_recovery'].update(eligible=False,status='blocked')
        if result['action']=='none':result['action']='restart'
    result['action_label']={'restart':'调整研究方案','settings':'设置模型','sources':'选择资料','approval':'查看待确认操作',
                            'none':'','resume':'继续研究'}[result['action']]
    return result
