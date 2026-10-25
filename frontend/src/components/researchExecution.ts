import type {SSEvent} from '../hooks/useSSE'

export const agentNames:Record<string,string>={planner:'规划 Agent',dag_executor:'执行调度',search:'搜索取证',
  browser:'网页读取',rag:'资料检索',mcp:'扩展工具',analyst:'分析 Agent',reflection:'核对 Agent',
  report:'报告 Agent',replan:'调整计划',approval_reviewer:'授权确认',retry_scheduler:'重试调度'}
const verbs:Record<string,string>={agent_start:'开始执行',agent_complete:'执行结束',agent_end:'执行结束',agent_error:'阶段停止',
  tool_start:'调用工具',tool_call:'调用工具',tool_complete:'工具返回',tool_result:'工具返回',tool_error:'调用失败',
  workflow_error:'执行错误',thought:'执行反馈',reflection:'核对结果',report_citation:'添加引用',control_update:'执行控制',workflow_start:'研究开始'}
const phases:Record<string,string>={extract_publications:'整理成果与署名',landscape:'研究布局',evolution:'研究演进',
  relationships:'组织与学者关系',deep_dive:'成果深读',validation:'来源核对',actions:'研究与合作行动'}
export function phaseName(phase:string):string {const parts=phase.split(':'),name=parts[0]==='question'?parts[1]:parts[0];return (phases[name]||name)+(parts.includes('conditions')?' · 条件补读':'')}
export const asObject=(value:unknown):Record<string,unknown>=>value&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,unknown>:{}
const text=(value:unknown):string=>typeof value==='string'?value:typeof value==='number'?String(value):''
export interface ExecutionItem {id:string;role:string;tool:string;query:string;label:string;detail:string;error:boolean;time:string;
  type:string;nodeId:string;callId:string;phase:string;state:string}
export function executionItems(events:SSEvent[]):ExecutionItem[] {
  const calls=new Map<string,Record<string,unknown>>()
  return events.flatMap((event,index)=>{
    const data={...asObject(event.data.metadata),...event.data},args=asObject(data.args)
    const id=text(data.call_id),previous=calls.get(id)||{}
    if(id&&['tool_start','tool_call'].includes(event.type))calls.set(id,data)
    const role=text(data.agent||data.agent_type||previous.agent||previous.agent_type),tool=text(data.tool_name||data.tool||previous.tool_name||previous.tool)
    const progress=asObject(data.analysis_progress),recovery=asObject(data.recovery),diagnosis=asObject(data.pause_diagnosis)
    let label=verbs[event.type],detail=text(data.content||data.message||data.error||data.summary||data.result_summary||data.details)
    let state=event.type.includes('error')||data.status==='error'?'failed':event.type.endsWith('start')||event.type==='tool_call'?'running':
      ['agent_complete','agent_end','tool_complete','tool_result'].includes(event.type)?text(data.status)||'done':'unknown'
    if(event.type==='done'){label=({paused:'研究已暂停',canceled:'研究已终止',failed:'研究失败',completed:'研究完成'} as Record<string,string>)[text(data.status)]||'执行结束';state=text(data.status);detail=''}
    if(event.type==='report_chunk')return []
    if(event.type==='state_update'){
      if(diagnosis.summary){label='自动诊断';detail=text(diagnosis.summary);state='paused'}
      else if(recovery.message){label=recovery.status==='resolved'?'修复完成':'自动修复';detail=text(recovery.message);state=recovery.status==='running'?'running':recovery.status==='resolved'?'done':'paused'}
      else if(progress.phase){const parts=text(progress.phase).split(':'),name=parts[0]==='question'?parts[1]:parts[0];label=phases[name]||name;detail=`${text(progress.completed_steps)} 步已保存`;state=text(progress.status)||'running'}
      else return []
    }
    if(!label)return []
    if(detail.includes('未执行本轮反思'))state='skipped'
    const priorArgs=asObject(previous.args),query=text(args.query||args.url||data.query||data.url||priorArgs.query||priorArgs.url)
    if(event.type==='control_update')detail=asObject(data.user_control).state==='requested'?'当前步骤结束后暂停':detail
    return [{id:text(data.event_id)||`${index}-${event.timestamp}`,role,tool,query,label,detail,error:state==='failed',
      time:event.timestamp||text(data.timestamp),type:event.type,nodeId:text(data.node_id||previous.node_id),callId:id,
      phase:text(progress.phase),state}]
  })
}
export interface FlowAction {id:string;label:string;detail:string;query:string;state:string;time:string;items:ExecutionItem[]}
export function flowActions(items:ExecutionItem[],rootStatus:string):FlowAction[] {
  const actions=new Map<string,FlowAction>();let run=0
  for(const item of items){
    if(['done','report_citation','control_update'].includes(item.type))continue
    if(item.type==='agent_start')run++
    const key=item.callId?`call:${item.callId}`:item.phase?`phase:${item.phase}`:
      ['agent_start','agent_complete','agent_end','agent_error'].includes(item.type)?`run:${item.role}:${run}`:`event:${item.id}`
    const previous=actions.get(key)
    const title=item.callId?(item.tool||'工具调用'):item.phase?phaseName(item.phase):
      item.type.startsWith('agent_')?({analyst:'综合分析',reflection:'核对来源',report:'生成报告',planner:'制定研究计划'} as Record<string,string>)[item.role]||'执行当前任务':item.label
    actions.set(key,{id:item.phase||item.callId?key:previous?.id||item.id,label:title,detail:item.detail,query:item.query||previous?.query||'',
      state:item.state,time:item.time||previous?.time||'',items:[...(previous?.items||[]),item]})
  }
  const list=[...actions.values()]
  const finished=['completed','done','success','skipped'].includes(rootStatus)
  const stopped=['paused','failed','canceled','unknown'].includes(rootStatus)
  return list.map(action=>({...action,state:action.state==='running'?(finished?(rootStatus==='skipped'?'skipped':'done'):stopped?rootStatus:'running'):action.state}))
}
export function briefFeedback(value:string):string {
  return value.replace(/^Analyzing (\d+) evidence items$/,'阅读 $1 份资料')
    .replace(/^Generated \d+ chars of analysis from (\d+) evidence items$/,'已分析 $1 份资料')
    .replace(/^Validating analysis with (\d+) evidence items$/,'核对结论与 $1 份资料')
    .replace(/^Generating final report$/,'编排正文、图表和引用')
    .replace(/^Analysis complete.*$/,'当前分析已完成')
    .replace(/^Verification: confidence=([\d.]+), needs_revision=False$/,'核对完成，无需重做分析')
    .replace(/^Verification passed:.*$/,'结论与来源核对完成')
}
