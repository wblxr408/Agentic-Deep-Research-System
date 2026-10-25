import {useRef,useState} from 'react'
import {Icon} from './Interface'

export interface RunControlState {
  session_id:string;execution_id?:string|null;status:string;runtime_status?:string|null;stop_reason?:string|null
  user_control?:{state?:string}|null
  analysis_recovery_available?:boolean;report_recovery_available?:boolean
  budget_state?:{hard_stop_reason?:string|null;model_stop_reason?:string|null}|null
}
const reasons:Record<string,string>={
  final_report_needs_revision:'报告内容需要修订',final_audit_budget_exhausted:'报告核对额度已用完',
  insufficient_context_budget:'当前分析的上下文额度不足',analysis_output_incomplete:'当前问题尚未分析完整',
  analysis_provider_unavailable:'模型服务暂时不可用',model_output_limit:'本次模型输出达到长度上限',
  token_limit:'Token 额度已用完',cost_limit:'费用额度已用完',wall_clock_limit:'任务执行期限已到',
  tool_call_limit:'工具调用次数已用完',user_requested_pause:'由你暂停',
  final_audit_reservation_not_released:'报告核对尚未完成',awaiting_approval:'等待你的确认',
  llm_stream_interrupted:'模型输出连接中断',workflow_error:'执行遇到错误',
}
const errors:Record<string,string>={
  pause_execution_changed_reload:'任务已变化，请刷新。',pause_task_not_running:'任务当前不在运行。',
  resume_execution_changed_reload:'任务已变化，请刷新。',resume_checkpoint_changed:'进度已变化，请刷新。',
  resume_checkpoint_not_recoverable:'当前进度无法直接继续，请调整后重新开始。',
  resume_original_allowance_exhausted:'原任务额度或期限已用完，请调整后重新开始。',
  resume_receipts_pending:'上一步的用量仍在结算，请稍后继续。',
  resume_sources_changed:'资料访问已变化，请调整后重新开始。',
  resume_original_deadline_unavailable:'原任务的期限记录不完整，请重新开始。',
}
export default function ResearchRunControls({value,onRefresh,onResumed,onRestart,onSynthesis,synthesisBusy}:{
  value:RunControlState;onRefresh:()=>Promise<void>;onResumed:(execution:string)=>Promise<void>
  onRestart:()=>void;onSynthesis:(stage:'analysis'|'report')=>void;synthesisBusy:boolean
}) {
  const [busy,setBusy]=useState(''),[error,setError]=useState('')
  const pending=useRef(false),ids=useRef<Record<string,string>>({})
  const pausing=value.status==='running'&&value.user_control?.state==='requested'
  const userPaused=value.status==='paused'&&value.runtime_status==='user_paused'
  const reason=value.stop_reason||value.budget_state?.model_stop_reason||value.budget_state?.hard_stop_reason||value.runtime_status||''
  async function act(action:'pause'|'resume'|'cancel') {
    if(pending.current)return
    pending.current=true;setBusy(action);setError('')
    ids.current[action]??=crypto.randomUUID()
    try {
      const response=await fetch(`/api/v1/research/${value.session_id}/${action}`,{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({request_id:ids.current[action],execution_id:value.execution_id})})
      const data=await response.json()
      if(!response.ok)throw new Error(errors[String(data.detail)]||'操作未完成，请刷新后重试。')
      if(action==='resume')await onResumed(data.execution_id)
      else await onRefresh()
    }catch(problem){setError(problem instanceof Error?problem.message:'操作未完成，请重试。')}
    finally{pending.current=false;setBusy('')}
  }
  const stopped=['paused','failed'].includes(value.status)
  return <section className="run-controls" aria-label="研究执行控制">
    <div className="run-control-status" role="status">
      <Icon name={stopped?'pause':'network'} size={18}/>
      <span>{pausing?'暂停中 · 当前步骤完成后停止':userPaused?'由你暂停':stopped?`系统停止 · ${reasons[reason]||'查看执行反馈了解原因'}`:value.status==='running'?'研究正在执行':value.status==='completed'?'研究已完成':value.status==='canceled'?'研究已终止':'等待执行'}</span>
    </div>
    <div className="run-control-actions">
      {value.status==='running'&&<button type="button" className="btn-secondary" disabled={!!busy||pausing} onClick={()=>void act('pause')}><Icon name="pause" size={16}/>{busy==='pause'?'正在暂停…':pausing?'暂停中':'暂停'}</button>}
      {userPaused&&<button type="button" className="btn-primary" disabled={!!busy} onClick={()=>void act('resume')}><Icon name="play" size={16}/>{busy==='resume'?'正在继续…':'继续研究'}</button>}
      {!userPaused&&value.analysis_recovery_available&&<button type="button" className="btn-primary" disabled={synthesisBusy||!!busy} onClick={()=>onSynthesis('analysis')}>继续分析</button>}
      {!userPaused&&value.report_recovery_available&&<button type="button" className="btn-primary" disabled={synthesisBusy||!!busy} onClick={()=>onSynthesis('report')}>继续生成报告</button>}
      {['pending','running','paused'].includes(value.status)&&<button type="button" className="btn-ghost" disabled={!!busy} onClick={()=>void act('cancel')}>{busy==='cancel'?'正在终止…':'终止'}</button>}
      {['paused','failed','canceled','completed'].includes(value.status)&&<button type="button" className="btn-secondary" onClick={onRestart}>调整后重新开始<Icon name="arrow" size={15}/></button>}
    </div>
    {error&&<p role="alert" className="composer-error">{error}</p>}
  </section>
}
