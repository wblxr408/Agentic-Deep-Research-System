import {useEffect,useMemo,useRef,useState} from 'react'
import type {SSEvent} from '../hooks/useSSE'
import {Icon} from './Interface'

export const agentNames:Record<string,string>={planner:'规划 Agent',dag_executor:'执行调度',search:'搜索取证',
  browser:'网页读取',rag:'资料检索',mcp:'扩展工具',analyst:'分析 Agent',reflection:'核对 Agent',
  report:'报告 Agent',replan:'重规划',approval_reviewer:'授权确认',retry_scheduler:'重试调度'}
const verbs:Record<string,string>={agent_start:'开始执行',agent_complete:'执行结束',agent_end:'执行结束',agent_error:'阶段停止',
  tool_start:'调用工具',tool_call:'调用工具',tool_complete:'工具返回',tool_result:'工具返回',
  tool_error:'调用失败',workflow_error:'执行错误',thought:'执行反馈',reflection:'核对结果',
  report_citation:'添加引用',control_update:'执行控制',workflow_start:'研究开始'}
const phases:Record<string,string>={extract_publications:'整理成果与署名',landscape:'研究布局',evolution:'研究演进',
  relationships:'组织与学者关系',deep_dive:'成果深读',validation:'来源核对',actions:'研究与合作行动'}
function text(value:unknown):string {return typeof value==='string'?value:typeof value==='number'?String(value):''}
function object(value:unknown):Record<string,unknown> {return value&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,unknown>:{}}
function terminal(status:unknown):string {return ({paused:'研究已暂停',canceled:'研究已终止',failed:'研究失败',completed:'研究完成'} as Record<string,string>)[text(status)]||'本轮执行已结束'}
export default function ExecutionFeed({events,connection,status}:{events:SSEvent[];connection:string;status:string}) {
  const [agent,setAgent]=useState('all'),[following,setFollowing]=useState(true),[limit,setLimit]=useState(100)
  const scroller=useRef<HTMLDivElement>(null)
  const items=useMemo(()=>{
    const calls=new Map<string,Record<string,unknown>>()
    return events.flatMap((event,index)=>{
      const data={...object(event.data.metadata),...event.data},args=object(data.args)
      const id=text(data.call_id),previous=calls.get(id)||{}
      if(id&&['tool_start','tool_call'].includes(event.type))calls.set(id,data)
      const role=text(data.agent||data.agent_type||previous.agent),tool=text(data.tool_name||data.tool||previous.tool_name||previous.tool)
      let label=verbs[event.type],detail=text(data.content||data.message||data.error||data.summary||data.result_summary||data.details)
      if(event.type==='done'){label=terminal(data.status);detail=''}
      if(event.type==='report_chunk')return [] // The report reader owns the streamed body.
      if(event.type==='state_update'){
        const progress=object(data.analysis_progress)
        const diagnosis=object(data.pause_diagnosis),recovery=object(data.recovery)
        if(diagnosis.summary){label='自动诊断';detail=text(diagnosis.summary)}
        else if(recovery.message){label='自动恢复';detail=text(recovery.message)}
        else if(progress.phase){
          const parts=text(progress.phase).split(':'),name=parts[0]==='question'?parts[1]:parts[0]
          label='分析进度';detail=`${phases[name]||name} · ${text(progress.completed_steps)} 步已保存`
        }else return []
      }
      if(!label)return []
      const query=text(args.query||args.url||data.query||data.url)
      if(event.type==='control_update')detail=object(data.user_control).state==='requested'?'收到暂停请求，当前步骤完成后停止':detail
      return [{id:text(data.event_id)||`${index}-${event.timestamp}`,role,tool,query,label,detail,
        error:event.type.includes('error')||data.status==='error',time:event.timestamp||text(data.timestamp)}]
    })
  },[events])
  const roles=[...new Set(items.map(item=>item.role).filter(Boolean))]
  const filtered=items.filter(item=>agent==='all'||item.role===agent),shown=filtered.slice(-limit)
  useEffect(()=>{if(following&&scroller.current)scroller.current.scrollTop=scroller.current.scrollHeight},[items,following,agent])
  const live=['running','pending'].includes(status)
  return <section className="execution-feed" aria-label="SSE 实时执行反馈">
    <header className="execution-feed-heading"><div><Icon name="network" size={18}/><h2>执行反馈</h2><span className={`feed-connection ${live&&connection==='connected'?'is-live':''}`}>{live?(connection==='connected'?'SSE 实时推送':connection==='error'?'正在重连':'连接中'):'执行记录'}</span></div>
      <div><label>角色<select aria-label="筛选执行角色" value={agent} onChange={event=>{setAgent(event.target.value);setLimit(100)}}><option value="all">全部</option>{roles.map(role=><option key={role} value={role}>{agentNames[role]||role}</option>)}</select></label>
      <button type="button" className="btn-ghost" aria-pressed={following} onClick={()=>setFollowing(value=>!value)}>{following?'停止跟随':'跟随最新'}</button></div>
    </header>
    <div className="execution-feed-scroll" ref={scroller} tabIndex={0} aria-label="执行事件列表">
      {filtered.length>limit&&<button type="button" className="btn-ghost" onClick={()=>{setFollowing(false);setLimit(value=>value+100)}}>显示更早事件</button>}
      {!shown.length&&<p className="feed-empty">{live?'等待执行事件':'暂无保留事件'}</p>}
      <ol>{shown.map(item=><li key={item.id} className={item.error?'is-error':''}>
        <time>{item.time&&Number.isFinite(Date.parse(item.time))?new Date(item.time).toLocaleTimeString('zh-CN',{hour12:false}):'—'}</time>
        <div><div className="feed-event-heading"><strong>{agentNames[item.role]||item.role||'研究流程'}</strong><span>{item.label}</span>{item.tool&&<code>{item.tool}</code>}</div>
          {item.query&&<p className="feed-query">{item.query}</p>}
          {item.detail&&<p className="feed-detail">{item.detail}</p>}
        </div>
      </li>)}</ol>
    </div>
  </section>
}
