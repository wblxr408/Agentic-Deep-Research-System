"""Explain retained stop evidence; never ask a model to guess the cause."""
from __future__ import annotations

from datetime import UTC, datetime
from app.recovery_policy import recovery_plan, ROOT_RECOVERY_LIMIT

TRANSIENT = {'APIConnectionError', 'APITimeoutError', 'InternalServerError', 'RateLimitError'}
PHASES = {'planner':'研究规划','analyst':'研究分析','report':'报告生成','reflection':'来源核对',
          'extract_publications':'成果整理','landscape':'研究布局','evolution':'研究演进',
          'deep_dive':'成果深读','relationships':'组织与学者关系','actions':'合作建议','validation':'来源核对',
          'discovery':'研究成果发现'}


def diagnose_stop(state,*,active_execution=False):
    if state.get('status') not in {'paused','failed'}:return None
    review=state.get('review_status') or {};budget=state.get('budget_state') or review.get('budget_state') or {}
    root=state.get('session') or {};workflow=state.get('analysis_workflow') or {}
    failure=review.get('workflow_failure') or {}
    # A completed analysis may retain its earlier stop reason for history. It
    # must not override the error from a later report or other active stage.
    reason=review.get('reason') or failure.get('category') or review.get('last_error_category')
    if not reason and workflow.get('status')=='paused':reason=workflow.get('stop_reason')
    reason=reason or budget.get('model_stop_reason') or budget.get('hard_stop_reason') or state.get('runtime_status') or 'unknown'
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
        'automatic_recovery':{'attempts':attempts,'limit':ROOT_RECOVERY_LIMIT,'eligible':False,'status':'exhausted' if attempts else 'not_applicable'}}
    if state.get('runtime_status')=='user_paused':
        result.update(summary='研究已按你的要求暂停',next_step='由你决定何时继续。',action='resume')
        return result
    audit=review.get('final_report_audit') or {}
    revisions=audit.get('revision_requests') or []
    if reason=='source_media_incomplete':
        result.update(summary='原文图示未能完成',next_step='报告与原件已保留，当前未发布图文交付。',action='restart')
        code=review.get('source_media_reason')
        detail={'source_media_current_access_changed':'原文访问条件已变化。',
            'source_media_original_deadline_exhausted':'原图页处理达到本次执行期限。',
            'source_asset_current_evidence_changed':'原件与当前正文版本不一致。',
            'source_page_renderer_failed':'当前 PDF 未能生成原文页预览。',
            'source_media_execution_binding_unavailable':'当前执行绑定不可用。'}.get(code,'原图页暂时未能生成，原始资料已保留。')
        result['findings']=[{'text':'原图页处理停止','detail':detail}]
    elif reason=='report_contract_invalid':
        module_report=((state.get('organization_result') or review.get('organization_result') or {}).get('module_report') or {})
        labels={'unbound_sample_aggregate':'正文中的样本数量没有关联已计算统计。',
                'unbound_source_aggregate':'正文中的来源数量没有关联已计算统计。',
                'unbound_sample_ratio':'正文中的样本比例没有关联已计算统计。'}
        result.update(summary='报告结构校验未通过',next_step='已保留草稿，可在原任务剩余额度内继续生成报告。',action='restart')
        result['findings']=[{'text':str((item.get('paragraph') or {}).get('text') or '')[:240],
            'detail':labels.get(item.get('reason'),'报告内容未满足当前交付结构。')}
            for item in (module_report.get('rejected_paragraphs') or [])[:100]]
    elif reason=='layout_required_data_missing':
        result.update(summary='报告版式有组件缺少所需资料',next_step='可补充相关资料，或调整这些组件的缺失处理方式。',action='restart')
        labels={'statistics':'缺少可核对的统计数据。','relationships':'缺少有来源的关系数据。',
            'technical_comparison':'缺少有来源的技术对照。','sources':'缺少可引用的来源。',
            'narrative':'缺少相应的报告文字。','auto':'缺少与组件匹配的资料。'}
        result['findings']=[{'text':f"第 {item.get('section_index','?')} 章 · 第 {item.get('block_index','?')} 个组件",
            'detail':labels.get(item.get('binding'),labels['auto'])} for item in (review.get('layout_missing') or [])[:96]]
    elif reason=='final_report_needs_revision':
        result['summary']=f'报告核对发现 {len(revisions)} 项内容需要修订' if revisions else '报告核对发现需要修订的内容'
        for item in revisions[:100]:
            result['findings'].append({'text':str(item.get('text') or '')[:240],
                'detail':str(item.get('requested_action') or item.get('reason') or '需要补充依据或调整结论')[:240]})
        revision=audit.get('revision_attempt') or {}
        rounds=audit.get('repair_rounds') or []
        if rounds:
            result['findings'].append({'text':f'已自动修改并核对 {len(rounds)} 轮',
                'detail':f"问题数量从 {rounds[0]['before']} 项变为 {rounds[-1]['after']} 项。"})
            outcome=audit.get('repair_outcome')
            result['next_step']=('本轮修订没有进一步减少问题，已停止重复请求。' if outcome=='no_progress' else
                '已达到本类问题的修订轮数，具体未解决问题已列出。' if outcome=='round_limit' else
                '剩余问题受原资料、修订契约或额度约束，未继续派发。')
        elif revision.get('attempted'):
            result['next_step']='系统已尝试修订，当前仍有未解决的问题；需补充对应资料后继续。'
        elif revision.get('status')=='unmapped_paragraphs':
            result['next_step']='核对问题无法定位到可自动修改的正文段落，已保留具体主张。'
        else:result['next_step']='需补充对应来源并修订正文。'
        result['revision_count']=len(revisions)
    elif reason=='research_discovery_incomplete':
        gap=workflow.get('discovery_gap') or {}
        result.update(summary='本轮取证尚未确认可深读的研究成果',action='sources',
            next_step='系统已保留搜索线索和已读页面；后续需沿成果来源补取正文，未继续生成空泛章节。')
        result['findings']=[{'text':'可深读成果 0 项',
            'detail':f"已取得 {gap.get('acquired_sources',0)} 份来源正文；来源页面不等于已确认的目标成果。"}]
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
    elif reason=='analysis_checkpoint_unavailable':
        failed=(workflow.get('failed_attempts') or {}).get(workflow.get('active_phase')) or []
        admission=(failed[-1].get('admission') or {}) if failed else {}
        steps={'current_source_access':'当前资料权限读取','database_checkpoint':'数据库保存',
            'committed_progress_stream':'已保存进度的实时推送','committed':'已完成进度保存'}
        step=steps.get(admission.get('operation'))
        result.update(summary='研究进度的保存反馈未完成',action='analysis',
            next_step='系统会在原额度和期限内从已保存阶段继续。')
        result['findings']=[{'text':'已保留的分析阶段','detail':str(len(workflow.get('completed') or {}))+' 步'},
            {'text':'停止位置','detail':step or '原记录没有分段错误信息，不能据此认定数据库保存失败。'}]
        result['diagnosis_complete']=bool(step)
    elif reason in {'analysis_output_incomplete','model_output_limit'}:
        result.update(summary='当前问题的响应结构不完整' if reason=='analysis_output_incomplete' else '当前问题的模型输出被截断',
            next_step='已保留具体阶段及响应，系统将按错误类型检查修复条件。',action='restart')
    elif reason=='analysis_provider_unavailable':
        failures=(workflow.get('failed_attempts') or {}).get(active) or []
        error_type=(failures[-1].get('provider_error_type') if failures else None)
        transient=error_type in TRANSIENT
        result.update(summary='模型服务连接或响应暂时失败' if transient else '模型服务未能完成本阶段请求',
            next_step='模型服务仍未恢复。' if attempts else '系统未取得可分类的服务错误，可选择另一已授权模型。',action='settings')
        if error_type in {'AuthenticationError','PermissionDeniedError'}:
            result.update(summary='模型服务拒绝当前凭证或访问权限',next_step='需要更新本账号的模型凭证或授权。',action='settings')
    elif reason=='final_audit_incomplete' and any(
            batch.get('status') in {'response_unavailable_or_invalid','response_received'}
            and batch.get('reason') in {'JSONDecodeError','AuditBatchOutputTruncated','AuditBatchStructureError','missing_or_invalid_verdicts'}
            and bool(set(batch.get('claim_ids') or []) & set(audit.get('unfinished_claim_ids') or []))
            for batch in (audit.get('batching') or {}).get('batches',[])):
        unfinished=len(audit.get('unfinished_claim_ids') or [])
        result.update(summary='报告核对结果格式不完整',next_step='已保留正文和已完成的核对结果。')
        result['findings']=[{'text':f'仍有 {unfinished} 项未完成核对','detail':'模型返回的审核结果无法完整解析。'}]
    elif reason=='final_audit_incomplete':
        unfinished=len(audit.get('unfinished_claim_ids') or [])
        result.update(summary='报告来源核对未完成',next_step='已保留正文和已完成的核对结果。')
        result['findings']=[{'text':f'仍有 {unfinished} 项未完成核对','detail':'未取得完整的审核判断。'}]
    elif reason in {'final_audit_budget_exhausted','final_audit_reservation_not_released'}:
        result.update(summary='报告来源核对未完成',next_step='需要保留足够的核对额度后再生成报告。')
        result['findings']=[{'text':'停止发生在报告核对阶段','detail':'总 Token 剩余不代表核对阶段还有可用份额。'}]
    elif state.get('pending_approvals') or state.get('runtime_status')=='awaiting_approval':
        result.update(summary='下一步操作需要你的授权',next_step='请选择是否允许已列出的操作。',action='approval')
    elif any(part in reason for part in ('authorization','sources_changed','data_governance','data_class','access_credentials')):
        result.update(summary='当前资料或操作权限不满足执行要求',next_step='需要你选择可访问的资料或授予所需权限。',action='sources')
    elif reason=='model_routing_configuration_changed' and review.get('model_configuration_change'):
        change=review['model_configuration_change'];previous=change.get('expected') or {};current=change.get('current') or {}
        result.update(summary='账号模型配置与任务创建时不同',
            next_step='原任务保留创建时的模型约束；新研究使用当前账号模型。',action='restart')
        result['findings']=[{'text':'任务模型','detail':str(previous.get('model') or previous.get('provider') or '')},
            {'text':'当前账号模型','detail':str(current.get('model') or current.get('provider') or '')}]
        for field,label in (('endpoint_changed','模型服务已变更'),('policy_changed','模型选择规则已变更'),
                            ('fallback_changed','备用模型配置已变更')):
            if change.get(field):result['findings'].append({'text':label,'detail':label})
    elif any(part in reason for part in ('model_rout','no_eligible_model','model_endpoint','configuration')):
        result.update(summary='没有满足本阶段要求的模型配置',next_step='需要为本账号选择符合资料权限和上下文要求的模型。',action='settings')
    elif any(part in reason for part in ('budget','token_limit','cost_limit','wall_clock','tool_call_limit')):
        result.update(summary='本阶段已达到配置的执行额度',next_step='需要你决定是否调整额度或缩小研究范围。')
    else:
        result.update(summary=f"{result['phase']}未能完成，系统已保留停止位置",next_step='系统尚未取得足以确定根因的结构化记录。',action='restart')
        if failure.get('message'):result['findings']=[{'text':'实际执行错误','detail':str(failure['message'])[:360]}]
        result['diagnosis_complete']=bool(failure.get('message'))
    plan=recovery_plan(state)
    if plan['kind']:
        eligible=bool(plan['candidate'] and not blockers and seconds is not None and seconds>plan['delay_seconds']+5
            and remaining>=1024 and workflow.get('schema_version')=='adrs-analysis-questions-v2'
            and workflow.get('status')=='paused' and not state.get('pending_approvals')
            and (review.get('user_control') or {}).get('state') not in {'requested','paused'})
        result['automatic_recovery'].update(policy=plan['kind'],policy_attempts=plan['attempts'],policy_limit=plan['limit'],
            action=plan['action'],delay_seconds=plan['delay_seconds'],eligible=eligible and active_execution,
            status=('planned' if active_execution else 'available') if eligible else 'blocked' if blockers else 'exhausted')
        if eligible:
            result.update(next_step=f"系统将{plan['action']}（本类第 {plan['attempts']+1}/{plan['limit']} 次）。" if active_execution
                else f"已保留可修复检查点：{plan['action']}。",action='none')
        elif plan['blocked']:
            result['next_step']=plan['blocked']+'。'
        elif not blockers:
            result['next_step']='原期限、检查点、剩余额度或操作授权不满足自动修复条件。'
    if blockers:
        if review.get('automatic_recovery_blocked'):
            result['next_step']='系统已检查自动恢复条件，没有派发新的模型请求。'
        result['next_step']+=' '+ '；'.join(blockers)+'，需要你决定新的范围或额度。'
        result['automatic_recovery'].update(eligible=False,status='blocked')
        if result['action']=='none':result['action']='restart'
    result['action_label']={'restart':'调整研究方案','settings':'设置模型','sources':'选择资料','approval':'查看待确认操作',
                            'none':'','resume':'继续研究'}[result['action']]
    return result
