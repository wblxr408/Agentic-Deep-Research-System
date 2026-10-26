import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import type { SSEvent } from '../hooks/useSSE'
import type { PlanSummaryProps } from './ResearchPlanSummary'
import type { PersistedToolCall } from './ToolTrace'
import { Icon, Modal, StatusPill, statusLabels } from './Interface'
import {agentNames,briefFeedback,executionItems,flowActions,phaseName} from './researchExecution'
import type {FlowAction} from './researchExecution'
import AgentAvatar from './AgentAvatar'
import type {AgentExpression} from './AgentAvatar'

const labels:Record<string,string>={planner:'研究规划',search:'搜索取证',browser:'网页读取',rag:'资料检索',mcp:'扩展工具',analyst:'问题分析',reflection:'来源核对',report:'图文报告',replan:'调整计划',dag_executor:'计划执行'}
export function mergeResearchEvents(history:SSEvent[],live:SSEvent[],execution?:string|null):SSEvent[] {
  const seen=new Set<string>()
  return [...history,...live].filter(event=>{
    if(event.type==='connected')return false
    const id=event.data.execution_id
    if(execution&&typeof id==='string'&&id!==execution)return false
    const identity=String(event.data.event_id||event.data.trace_id||`${event.type}|${event.timestamp||''}|${event.data.node_id||''}|${event.data.agent||''}|${event.data.call_id||''}|${event.data.status||''}|${event.data.summary||event.data.content||''}`)
    if(seen.has(identity))return false
    seen.add(identity);return true
  }).sort((a,b)=>{const left=Date.parse(a.timestamp||''),right=Date.parse(b.timestamp||'');return Number.isFinite(left)&&Number.isFinite(right)?left-right:0})
}
interface DagNode {node_id:string;node_type?:string;query?:string;status:string;depends_on?:string[];last_error?:string|null}
interface FlowNode {id:string;type:string;label:string;query:string;status:string;dependencies:string[];x:number;y:number;error?:string|null;root?:boolean;actions?:FlowAction[]}
function evidenceLabel(type:string,purpose:string,query:string):string {
  if(type==='browser')try { const url=new URL(query),file=decodeURIComponent(url.pathname.split('/').filter(Boolean).pop()||'');return /\.pdf$/i.test(file)?file.replace(/^OSDI\d+_/,''):url.hostname.replace(/^www\./,'')+(file?' · '+file.slice(0,28):'') } catch { /* Use the public plan label. */ }
  return query||purpose||labels[type]||'取证'
}
interface Props {
  plan:PlanSummaryProps['plan'];dag?:{nodes:DagNode[]};events:SSEvent[];status:string;tools?:PersistedToolCall[]
  analysis?:{status:string;phase:string|null;completed_steps:number;phases?:Array<{phase:string;status:string;summary:string;attempts:number}>}|null;history?:PlanSummaryProps['history']
  connection?:string
  runtimeStatus?:string
}
function nodesFor(p:Props):FlowNode[] {
  const persisted=new Map((p.dag?.nodes||[]).map(node=>[node.node_id,node]))
  const steps=p.plan?.steps||p.dag?.nodes?.map(node=>({node_id:node.node_id,node_type:node.node_type,purpose:labels[node.node_type||'']||'取证步骤',query:node.query||'',depends_on:node.depends_on||[]}))||[]
  const terminal=['completed','paused','canceled','failed'].includes(p.status)
  let analysisStart=-1
  p.events.forEach((event,index)=>{if(event.type==='agent_start'&&event.data.agent==='analyst')analysisStart=index})
  const eventState=(agent:string)=>{
    const relevant=['analyst','planner'].includes(agent)?p.events:p.events.slice(Math.max(0,analysisStart))
    const event=[...relevant].reverse().find(e=>String(e.data.agent||'')===agent&&['agent_start','agent_complete','agent_end','agent_error'].includes(e.type))
    if(!event)return p.status==='completed'?'unknown':'pending'
    if(event.type==='agent_start')return terminal?(p.status==='completed'?'unknown':p.status):'running'
    if(event.type==='agent_error')return p.status==='paused'?'paused':'failed'
    if(String(event.data.content||'').includes('未执行本轮反思'))return 'skipped'
    return String(event.data.status||'done')
  }
  const nodes:FlowNode[]=steps.filter(s=>!['analyst','report','reflection'].includes(s.node_type||'')).map(step=>{
    const current=persisted.get(step.node_id)
    let status=current?.status||'pending'
    const activity=[...p.events].reverse().find(event=>{
      const args=event.data.args as Record<string,unknown>|undefined
      return ['tool_start','tool_call','tool_complete','tool_result','tool_error'].includes(event.type)&&(
        event.data.node_id===step.node_id||Boolean(step.query&&(args?.query===step.query||args?.url===step.query)))
    })
    if(activity&&!['done','completed','skipped'].includes(status)){
      status=['tool_start','tool_call'].includes(activity.type)?'running':activity.type==='tool_error'||activity.data.status==='error'?'failed':'done'
    }
    if(status==='running'&&terminal)status=p.status==='completed'?'unknown':p.status
    const type=step.node_type||current?.node_type||'search'
    return {id:step.node_id,type,label:evidenceLabel(type,step.purpose,step.query),query:step.query,status,dependencies:step.depends_on||[],x:0,y:0,error:current?.last_error}
  })
  if(!nodes.length&&!p.events.length&&!p.analysis)return []
  const used=new Set(nodes.flatMap(n=>n.dependencies)),leaves=nodes.filter(n=>!used.has(n.id)).map(n=>n.id)
  const lastAnalysis=[...p.events].reverse().find(event=>event.data.agent==='analyst'&&(
    ['agent_start','agent_complete','agent_error'].includes(event.type)||Boolean(event.data.recovery)))
  const recovering=p.status==='running'&&(lastAnalysis?.data.recovery as {status?:string}|undefined)?.status==='running'
  const analysisStatus=p.analysis?.status==='completed'?'done':recovering?'running':p.analysis?.status==='paused'?'paused':p.analysis?.status==='running'?(terminal?(p.status==='completed'?'unknown':p.status):'running'):eventState('analyst')
  nodes.push({id:'$analysis',type:'analyst',label:'问题分析',query:p.analysis?.phase?`当前问题阶段 · 已保存 ${p.analysis.completed_steps} 步`:'按问题阅读与分析来源',status:analysisStatus,dependencies:leaves,x:0,y:0,root:true})
  const analysisDone=['done','completed','success'].includes(analysisStatus)
  nodes.push({id:'$reflection',type:'reflection',label:'来源核对',query:'核对结论、原文与实验条件',status:analysisDone||p.status==='completed'?eventState('reflection'):'pending',dependencies:['$analysis'],x:0,y:0,root:true})
  nodes.push({id:'$report',type:'report',label:'图文报告',query:'组织正文、图表和引用',status:p.status==='completed'?'done':analysisDone?eventState('report'):'pending',dependencies:['$reflection'],x:0,y:0,root:true})
  if(p.events.some(event=>event.data.agent==='planner')){
    const planner:FlowNode={id:'$planner',type:'planner',label:'研究规划',query:'形成研究计划',status:eventState('planner'),dependencies:[],x:0,y:0,root:true}
    for(const node of nodes)if(!node.dependencies.length)node.dependencies=[planner.id]
    nodes.unshift(planner)
  }
  const items=executionItems(p.events)
  for(const node of nodes){
    const matching=items.filter(item=>{
      if(node.root)return item.role===node.type
      if(item.nodeId)return item.nodeId===node.id
      if(item.query&&node.query)return item.query===node.query
      return item.role===node.type&&nodes.filter(other=>other.type===node.type).length===1
    })
    node.actions=flowActions(matching,node.status)
    if(node.type==='analyst')for(const phase of p.analysis?.phases||[]){
      const existing=node.actions.find(action=>action.items.some(item=>item.phase===phase.phase))
      if(existing){if(phase.status==='completed'){existing.state='done';existing.detail=phase.summary||existing.detail}}
      else node.actions.push({id:`phase:${phase.phase}`,label:phaseName(phase.phase),detail:phase.summary||`已尝试 ${phase.attempts} 次`,
        query:'',state:phase.status==='completed'?'done':terminal?p.status:phase.status,time:'',items:[]})
    }
    if(!node.root)for(const tool of p.tools||[]){
      const query=String(tool.args_json?.query||tool.args_json?.url||'')
      const nodeId=tool.node_id||tool.args_json?.node_id
      if(nodeId?nodeId!==node.id:!query||query!==node.query)continue
      if(node.actions.some(action=>action.items.some(item=>item.callId===tool.call_id)))continue
      node.actions.push({id:`call:${tool.call_id}`,label:readableTool(tool.tool_name),detail:tool.error_message||tool.result_summary||'调用结果已保存',
        query,state:tool.status==='running'&&terminal?p.status:tool.status,time:tool.completed_at||tool.started_at||'',items:[]})
    }
  }
  const levels=new Map<string,number>(),remaining=new Set(nodes.map(n=>n.id)),ids=new Set(remaining)
  for(let pass=0;pass<nodes.length&&remaining.size;pass++){
    let changed=false
    for(const node of nodes){if(!remaining.has(node.id))continue;const dependencies=node.dependencies.filter(id=>ids.has(id));if(dependencies.every(id=>levels.has(id))){levels.set(node.id,dependencies.length?Math.max(...dependencies.map(id=>levels.get(id)!))+1:0);remaining.delete(node.id);changed=true}}
    if(!changed)break
  }
  let next=Math.max(0,...levels.values())+1
  for(const id of remaining)levels.set(id,next++)
  const counts=new Map<number,number>(),indices=new Map<number,number>()
  for(const node of nodes){const level=levels.get(node.id)||0;counts.set(level,(counts.get(level)||0)+1)}
  for(const node of nodes){const level=levels.get(node.id)||0,row=indices.get(level)||0;node.x=50+level*320;node.y=55+row*205;indices.set(level,row+1)}
  return nodes
}
function readableTool(name:string) {
  if(/search/i.test(name))return '搜索'
  if(/rag|retriev/i.test(name))return '资料检索'
  if(/browser|browse|web|fetch|read/i.test(name))return '网页读取'
  return name
}

interface StationAction extends FlowAction {nodeId?:string}
interface FlowStation {id:string;type:string;label:string;status:string;actor:boolean;nodes:FlowNode[];actions:StationAction[];x:number;y:number}
function stationsFor(nodes:FlowNode[]):FlowStation[] {
  const result:FlowStation[]=[]
  const addActor=(node:FlowNode)=>{
    const hasPhases=node.actions?.some(action=>action.id.startsWith('phase:')||action.items.some(item=>item.phase))
    const actions=(node.actions||[]).filter(action=>!hasPhases||action.state==='failed'||!action.items.length||
      !action.items.every(item=>['agent_start','agent_complete','agent_end'].includes(item.type)))
    result.push({id:node.id,type:node.type,label:agentNames[node.type]||node.label,status:node.status,actor:true,nodes:[node],
      actions:actions.map(action=>({...action,nodeId:node.id})),x:0,y:20})
  }
  const planner=nodes.find(node=>node.type==='planner'&&node.root)
  if(planner)addActor(planner)
  const tools=nodes.filter(node=>!node.root)
  if(tools.length){
    const active=tools.some(node=>node.status==='running'),failed=tools.some(node=>['failed','error'].includes(node.status))
    const complete=tools.every(node=>['done','completed','success','skipped'].includes(node.status))
    result.push({id:'$tools',type:'tools',label:'取证工具',status:active?'running':complete?'done':failed?'failed':
      tools.some(node=>node.status==='paused')?'paused':'pending',actor:false,nodes:tools,x:0,y:20,
      actions:tools.flatMap(node=>(node.actions?.length?node.actions:[{id:`planned:${node.id}`,label:labels[node.type]||node.type,
        detail:node.error||'',query:node.query,state:node.status,time:'',items:[]}]).map(action=>({
          ...action,label:readableTool(action.label),query:action.query||node.query,nodeId:node.id})))})
  }
  for(const node of nodes)if(node.root&&node!==planner)addActor(node)
  return result.map((station,index)=>({...station,x:40+index*364}))
}
function primaryAction(station:FlowStation):StationAction|undefined {
  const active=[...station.actions].reverse().filter(action=>action.state==='running')
  return active.find(action=>action.id.startsWith('phase:'))||active[0]||station.actions[station.actions.length-1]
}
function stationExpression(station:FlowStation,p:Props):AgentExpression {
  if(['done','success','completed'].includes(station.status))return 'completed'
  if(p.runtimeStatus==='user_paused'&&['pending','waiting','paused','running'].includes(station.status))return 'paused'
  if(station.status==='running'){
    const recent=executionItems(p.events).filter(item=>item.role===station.type),latest=recent[recent.length-1]
    return latest?.state==='running'&&latest.label==='自动修复'?'recovering':'working'
  }
  if(['failed','error'].includes(station.status))return 'failed'
  if(station.status==='paused')return 'failed'
  if(['canceled','skipped'].includes(station.status))return 'resting'
  return ['pending','waiting'].includes(station.status)?'waiting':'unknown'
}

export default function ResearchFlow(p:Props) {
  const nodes=useMemo(()=>nodesFor(p),[p.plan,p.dag,p.events,p.status,p.analysis,p.tools])
  const stations=useMemo(()=>stationsFor(nodes),[nodes])
  const viewport=useRef<HTMLDivElement>(null),drag=useRef<{x:number;y:number;left:number;top:number}|null>(null),initialized=useRef(false)
  const [camera,setCamera]=useState({x:24,y:24,zoom:.9})
  const [selected,setSelected]=useState<{station:string;action?:string}|null>(null)
  const [following,setFollowing]=useState(true),[role,setRole]=useState('all'),[expanded,setExpanded]=useState<Record<string,boolean>>({})
  const followed=useRef(''),marker=useId().replace(/:/g,'')
  const width=Math.max(780,stations.length*364+16)
  const height=Math.max(450,...stations.map(station=>460+(expanded[station.id]?Math.max(0,station.actions.length-1)*84:0)))
  const currentStation=useCallback(()=>{
    const candidates=role==='all'?stations:stations.filter(station=>station.type===role)
    return candidates.find(station=>station.status==='running')||candidates.find(station=>station.status==='paused')||
      candidates.find(station=>station.status==='failed')||candidates[candidates.length-1]
  },[stations,role])
  const focusStation=useCallback((station:FlowStation)=>{const el=viewport.current;if(!el)return
    const zoom=.95,renderedWidth=width*zoom,target=el.clientWidth/2-(station.x+150)*zoom
    setCamera({zoom,x:renderedWidth<=el.clientWidth-48?(el.clientWidth-renderedWidth)/2:
      Math.max(el.clientWidth-renderedWidth-24,Math.min(24,target)),y:Math.max(12,el.clientHeight/2-225*zoom)})
  },[width])
  const fit=useCallback((readable=false)=>{const el=viewport.current;if(!el||el.clientWidth<100)return
    const fitted=Math.min(1,(el.clientWidth-40)/width,(el.clientHeight-32)/height),zoom=Math.max(readable ? .78 : .25,fitted)
    const current=readable&&fitted<zoom?currentStation():undefined
    setCamera(current?{zoom,x:el.clientWidth/2-(current.x+150)*zoom,y:el.clientHeight/2-225*zoom}:
      {zoom,x:(el.clientWidth-width*zoom)/2,y:Math.max(12,(el.clientHeight-height*zoom)/2)})
    initialized.current=true
  },[width,height,currentStation])
  useEffect(()=>{const el=viewport.current;if(!el)return;const observer=new ResizeObserver(()=>{if(!initialized.current&&stations.length)fit(true)});observer.observe(el);return()=>observer.disconnect()},[fit,stations.length])
  const lastEvent=p.events[p.events.length-1],lastKey=String(lastEvent?.data.event_id||lastEvent?.timestamp||p.events.length)
  useEffect(()=>{if(!following||!['running','pending'].includes(p.status)||followed.current===lastKey)return;followed.current=lastKey;const station=currentStation();if(station)focusStation(station)},[following,p.status,lastKey,currentStation,focusStation])
  const zoomBy=(factor:number)=>{const el=viewport.current;if(!el)return;setFollowing(false);setCamera(c=>{const zoom=Math.min(1.6,Math.max(.25,c.zoom*factor));return{zoom,x:el.clientWidth/2-(el.clientWidth/2-c.x)*zoom/c.zoom,y:el.clientHeight/2-(el.clientHeight/2-c.y)*zoom/c.zoom}})}
  const owner=stations.find(station=>station.id===selected?.station),action=owner?.actions.find(item=>item.id===selected?.action)
  const node=owner?.nodes.find(item=>item.id===action?.nodeId)||owner?.nodes[0]
  const related=node?(p.tools||[]).filter(tool=>{if(node.root)return tool.agent_type===node.type;const nodeId=tool.node_id||tool.args_json?.node_id;return nodeId?nodeId===node.id:Boolean(node.query&&(tool.args_json?.query===node.query||tool.args_json?.url===node.query))}):[]
  const openAction=(station:FlowStation,item:StationAction)=>setSelected({station:station.id,action:item.id})
  const actionButton=(station:FlowStation,item:StationAction,compact=false)=><button key={item.id} type="button"
    className={`station-action ${compact?'station-action--compact':''}`} data-status={item.state}
    aria-label={`动作：${item.label}，${statusLabels[item.state]||item.state}`} onClick={()=>openAction(station,item)}>
      <span className="station-action-heading"><Icon name={item.label.includes('修复')?'settings':item.label.includes('核对')?'target':'source'} size={15}/><strong>{item.label}</strong><StatusPill status={item.state}/></span>
      <span className="station-action-content">{briefFeedback(item.query||item.detail)||'等待执行'}</span>
      {!compact&&item.query&&item.detail&&<span className="station-action-result">{briefFeedback(item.detail)}</span>}
    </button>
  if(!stations.length)return <div className="flow-empty"><Icon name="network" size={36}/><p>正在取得研究计划</p></div>
  return <section className="flow-panel station-flow-panel" aria-label="研究工作流">
    <div className="flow-heading"><div><Icon name="network"/><strong>研究工作流</strong><StatusPill status={p.status}/><span className="flow-stream-status">{['running','pending'].includes(p.status)?p.connection==='connected'?'SSE 实时推送':p.connection==='error'?'正在重连':'连接中':'执行记录'}</span></div>
      <div className="canvas-toolbar" role="group" aria-label="画布操作">
        <label className="flow-role-filter">角色<select aria-label="画布角色" value={role} onChange={event=>{setRole(event.target.value);setFollowing(false);const station=stations.find(item=>item.type===event.target.value);if(station)focusStation(station)}}><option value="all">全部</option>{stations.map(station=><option key={station.id} value={station.type}>{station.label}</option>)}</select></label>
        <button type="button" className="btn-ghost" aria-pressed={following} onClick={()=>{setFollowing(value=>!value);if(!following){const station=currentStation();if(station)focusStation(station)}}}>{following?'停止跟随':'跟随当前'}</button>
        <button type="button" className="icon-button" aria-label="缩小流程图" onClick={()=>zoomBy(1/1.2)}><Icon name="minus" size={17}/></button><span>{Math.round(camera.zoom*100)}%</span>
        <button type="button" className="icon-button" aria-label="放大流程图" onClick={()=>zoomBy(1.2)}><Icon name="plus" size={17}/></button>
        <button type="button" className="icon-button" aria-label="适应画布" onClick={()=>{setFollowing(false);fit()}}><Icon name="fit" size={18}/></button>
        <button type="button" className="icon-button" aria-label="定位当前步骤" onClick={()=>{const station=currentStation();if(station)focusStation(station);setFollowing(true)}}><Icon name="target" size={18}/></button>
      </div>
    </div>
    <div ref={viewport} className="flow-viewport station-viewport" tabIndex={0} role="region" aria-label="可拖动研究流程图，方向键平移，加减号缩放，Home 适应画布"
      onKeyDown={event=>{if(event.target!==event.currentTarget)return;const moves:Record<string,[number,number]>={ArrowLeft:[40,0],ArrowRight:[-40,0],ArrowUp:[0,40],ArrowDown:[0,-40]};if(moves[event.key]){event.preventDefault();setFollowing(false);const [x,y]=moves[event.key];setCamera(c=>({...c,x:c.x+x,y:c.y+y}))}else if(['+','=','-'].includes(event.key)){event.preventDefault();zoomBy(event.key==='-'?1/1.2:1.2)}else if(event.key==='Home'){event.preventDefault();fit()}}}
      onPointerDown={event=>{if((event.target as Element).closest('button,summary,details'))return;setFollowing(false);drag.current={x:event.clientX,y:event.clientY,left:camera.x,top:camera.y};event.currentTarget.setPointerCapture(event.pointerId)}}
      onPointerMove={event=>{const d=drag.current;if(d)setCamera(c=>({...c,x:d.left+event.clientX-d.x,y:d.top+event.clientY-d.y}))}} onPointerUp={()=>{drag.current=null}} onPointerCancel={()=>{drag.current=null}}>
      <div className="flow-world" style={{width,height,transform:`translate(${camera.x}px,${camera.y}px) scale(${camera.zoom})`}}>
        <svg className="flow-connections station-handoffs" width={width} height={height} aria-hidden="true"><defs><marker id={marker} markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0L7 3.5L0 7" fill="var(--accent)"/></marker></defs>
          {stations.slice(1).map((station,index)=>{const from=stations[index],d=`M${from.x+204},${from.y+58} H${station.x+96}`;const active=p.status==='running'&&station.status==='running';return <g key={station.id}>
            <path d={d} className={`flow-edge station-handoff ${active?'is-running':''}`} markerEnd={`url(#${marker})`}/>
            {active&&<circle className="station-handoff-dot" r="3" fill="var(--accent)"><animateMotion dur="1.8s" repeatCount="indefinite" path={d}/></circle>}
          </g>})}
        </svg>
        {stations.map(station=>{const primary=primaryAction(station),history=station.actions.filter(item=>item.id!==primary?.id),expression=stationExpression(station,p)
          return <section key={station.id} role="group" aria-label={`${station.label} 工作区`} className={`agent-station ${role!=='all'&&role!==station.type?'is-dimmed':''}`} data-state={station.status} data-expression={expression} style={{left:station.x,top:station.y}}>
            <header className="station-owner"><button type="button" className="station-owner-button" aria-label={`${station.label}，${statusLabels[station.status]||station.status}`} onClick={()=>setSelected({station:station.id})}>
              {station.actor?<AgentAvatar name={station.label} role={station.type} expression={expression}/>:<span className="station-tools-avatar"><Icon name="network" size={35}/></span>}
              <strong>{station.label}</strong><StatusPill status={station.status}/>
            </button></header>
            <div className="station-ownership-line" aria-hidden="true"><span/></div>
            <div className="station-task-area" role="group" aria-label={`${station.label} 的动作`}>
              <div className="station-task-label"><span>{!primary?'所属动作':['pending','waiting'].includes(primary.state)?'待执行动作':primary.state==='running'?'当前动作':primary.state==='paused'?'暂停动作':'最近结果'}</span><span>{station.actions.length} 项</span></div>
              {primary?actionButton(station,primary):<div className="station-empty">{station.status==='pending'?'等待前序阶段':'暂无保留动作'}</div>}
              {history.length>0&&<details className="station-history" open={Boolean(expanded[station.id])} onToggle={event=>{const open=event.currentTarget.open;setExpanded(value=>value[station.id]===open?value:{...value,[station.id]:open})}}>
                <summary>动作记录 <span>{history.length}</span><Icon name="arrow" size={13}/></summary>
                <div className="station-history-items">{history.map(item=>actionButton(station,item,true))}</div>
              </details>}
            </div>
          </section>
        })}
      </div>
    </div>
    <div className="flow-bottom"><span className="station-layer-legend">上层角色交接<span>↓</span>下层所属动作</span><span>{stations.reduce((count,station)=>count+station.actions.length,0)} 项动作</span></div>
    <Modal open={Boolean(owner)} onClose={()=>setSelected(null)} title={action?.label||owner?.label||'执行详情'}>
      {owner&&<div className="node-detail"><div className="node-detail-role"><Icon name="network" size={17}/>{owner.label}<StatusPill status={action?.state||owner.status}/></div>
        {action?<><h3>执行反馈</h3><p className="action-detail-text">{action.detail||'当前动作尚未返回结果'}</p>{action.query&&<><h3>输入</h3><p className="action-detail-text">{action.query}</p></>}
          {action.items.length>1&&<details><summary>{action.items.length} 条过程记录</summary>{action.items.map(item=><div className="action-retained-event" key={item.id}><span>{item.label}</span><p>{item.detail}</p></div>)}</details>}</>:
          <><h3>所属动作</h3><div className="node-action-list">{owner.actions.map(item=><button type="button" key={item.id} onClick={()=>openAction(owner,item)}><span><strong>{item.label}</strong><span>{briefFeedback(item.query||item.detail)}</span></span><StatusPill status={item.state}/></button>)}</div></>}
        {!!node?.dependencies.length&&<><h3>前置步骤</h3><div className="node-dependencies">{node.dependencies.map(id=><span className="tool-chip" key={id}>{nodes.find(item=>item.id===id)?.label||id}</span>)}</div></>}
        {!!related.length&&<><h3>相关调用</h3>{related.map(tool=><div className="task-row" key={tool.call_id}><span>{readableTool(tool.tool_name)}</span><StatusPill status={tool.status}/></div>)}</>}
      </div>}
    </Modal>
  </section>
}
