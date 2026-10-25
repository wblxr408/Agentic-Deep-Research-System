import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import type { SSEvent } from '../hooks/useSSE'
import type { PlanSummaryProps } from './ResearchPlanSummary'
import type { PersistedToolCall } from './ToolTrace'
import { Icon, Modal, StatusPill, statusLabels } from './Interface'
import {agentNames,briefFeedback,executionItems,flowActions,phaseName} from './researchExecution'
import type {FlowAction} from './researchExecution'

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
function currentFlowNode(nodes:FlowNode[]):FlowNode|undefined {
  return nodes.find(node=>node.status==='running')||nodes.find(node=>node.status==='paused')||nodes.find(node=>node.status==='failed')||nodes[nodes.length-1]
}
function evidenceLabel(type:string,purpose:string,query:string):string {
  if(type==='browser')try { const url=new URL(query),file=decodeURIComponent(url.pathname.split('/').filter(Boolean).pop()||'');return /\.pdf$/i.test(file)?file.replace(/^OSDI\d+_/,''):url.hostname.replace(/^www\./,'')+(file?' · '+file.slice(0,28):'') } catch { /* Use the public plan label. */ }
  return query||purpose||labels[type]||'取证'
}
interface Props {
  plan:PlanSummaryProps['plan'];dag?:{nodes:DagNode[]};events:SSEvent[];status:string;tools?:PersistedToolCall[]
  analysis?:{status:string;phase:string|null;completed_steps:number;phases?:Array<{phase:string;status:string;summary:string;attempts:number}>}|null;history?:PlanSummaryProps['history']
  connection?:string
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

export default function ResearchFlow(p:Props) {
  const nodes=useMemo(()=>nodesFor(p),[p.plan,p.dag,p.events,p.status,p.analysis,p.tools])
  const viewport=useRef<HTMLDivElement>(null),drag=useRef<{x:number;y:number;left:number;top:number}|null>(null),initialized=useRef(false)
  const [camera,setCamera]=useState({x:24,y:24,zoom:.8}),[selected,setSelected]=useState<string|null>(null)
  const [following,setFollowing]=useState(true),[role,setRole]=useState('all'),[expanded,setExpanded]=useState<Record<string,boolean>>({})
  const followed=useRef('')
  const marker=useId().replace(/:/g,'')
  const shownActions=(node:FlowNode)=>(expanded[node.id]?node.actions:node.actions?.slice(-3))||[]
  const nodeHeight=(node:FlowNode)=>node.root?Math.max(165,110+shownActions(node).length*118+(node.actions&&node.actions.length>3?34:0)):165
  const width=Math.max(800,...nodes.map(n=>n.x+285)),height=Math.max(420,...nodes.map(n=>n.y+nodeHeight(n)+45))
  const fit=useCallback((readable=false)=>{const el=viewport.current;if(!el||el.clientWidth<100)return;const fitted=Math.min(1,(el.clientWidth-48)/width,(el.clientHeight-48)/height),zoom=Math.max(readable ? .65 : .25,fitted);const current=readable?currentFlowNode(nodes):undefined;setCamera(current&&fitted<zoom?{zoom,x:el.clientWidth/2-(current.x+125)*zoom,y:el.clientHeight/2-(current.y+(current.root?210:80))*zoom}:{x:(el.clientWidth-width*zoom)/2,y:(el.clientHeight-height*zoom)/2,zoom});initialized.current=true},[width,height,nodes])
  useEffect(()=>{const el=viewport.current;if(!el)return;const observer=new ResizeObserver(()=>{if(!initialized.current&&nodes.length)fit(true)});observer.observe(el);return()=>observer.disconnect()},[fit,nodes.length])
  const changeZoom=(factor:number)=>{const el=viewport.current;if(!el)return;setCamera(c=>{const zoom=Math.min(1.7,Math.max(.25,c.zoom*factor)),x=el.clientWidth/2,y=el.clientHeight/2;return{zoom,x:x-(x-c.x)*zoom/c.zoom,y:y-(y-c.y)*zoom/c.zoom}})}
  const focusNode=useCallback((node:FlowNode)=>{const el=viewport.current;if(node&&el)setCamera({zoom:.9,x:el.clientWidth/2-(node.x+125)*.9,y:el.clientHeight/2-(node.y+(node.root?210:80))*.9})},[])
  const focusCurrent=()=>{const candidates=role==='all'?nodes:nodes.filter(node=>node.type===role),node=currentFlowNode(candidates);if(node)focusNode(node);setFollowing(true)}
  const lastEvent=p.events[p.events.length-1],lastKey=String(lastEvent?.data.event_id||lastEvent?.timestamp||p.events.length)
  useEffect(()=>{if(!following||!['running','pending'].includes(p.status)||followed.current===lastKey)return;followed.current=lastKey;const node=currentFlowNode(role==='all'?nodes:nodes.filter(item=>item.type===role));if(node)focusNode(node)},[following,p.status,lastKey,nodes,focusNode,role])
  const current=nodes.find(n=>n.id===selected||n.actions?.some(action=>action.id===selected))
  const action=current?.actions?.find(item=>item.id===selected)
  const related=current?(p.tools||[]).filter(tool=>{if(current.root)return tool.agent_type===current.type;const nodeId=tool.node_id||tool.args_json?.node_id;return nodeId?nodeId===current.id:Boolean(current.query&&(tool.args_json?.query===current.query||tool.args_json?.url===current.query))}):[]
  if(!nodes.length)return <div className="flow-empty"><Icon name="network" size={36}/><p>正在取得研究计划</p></div>
  return <section className="flow-panel" aria-label="研究工作流">
    <div className="flow-heading"><div><Icon name="network"/><strong>研究工作流</strong><StatusPill status={p.status}/><span className="flow-stream-status">{['running','pending'].includes(p.status)?p.connection==='connected'?'SSE 实时推送':p.connection==='error'?'正在重连':'连接中':'执行记录'}</span></div><div className="canvas-toolbar" role="group" aria-label="画布操作">
      <label className="flow-role-filter">角色<select aria-label="画布角色" value={role} onChange={event=>{setRole(event.target.value);const node=nodes.find(item=>item.type===event.target.value);if(node)focusNode(node)}}><option value="all">全部</option>{[...new Set(nodes.map(node=>node.type))].map(type=><option value={type} key={type}>{agentNames[type]||labels[type]||type}</option>)}</select></label>
      <button type="button" className="btn-ghost" aria-pressed={following} onClick={()=>setFollowing(value=>!value)}>{following?'停止跟随':'跟随当前'}</button>
      <button type="button" className="icon-button" title="缩小" aria-label="缩小流程图" onClick={()=>changeZoom(1/1.2)}><Icon name="minus" size={17}/></button><span>{Math.round(camera.zoom*100)}%</span><button type="button" className="icon-button" title="放大" aria-label="放大流程图" onClick={()=>changeZoom(1.2)}><Icon name="plus" size={17}/></button>
      <button type="button" className="icon-button" title="适应画布" aria-label="适应画布" onClick={()=>fit()}><Icon name="fit" size={18}/></button><button type="button" className="icon-button" title="定位当前步骤" aria-label="定位当前步骤" onClick={focusCurrent}><Icon name="target" size={18}/></button>
    </div></div>
    <div ref={viewport} className="flow-viewport" tabIndex={0} role="region" aria-label="可拖动研究流程图，方向键平移，加减号缩放，Home 适应画布"
      onKeyDown={event=>{if(event.target!==event.currentTarget)return;const moves:Record<string,[number,number]>={ArrowLeft:[40,0],ArrowRight:[-40,0],ArrowUp:[0,40],ArrowDown:[0,-40]};if(moves[event.key]){event.preventDefault();const [x,y]=moves[event.key];setCamera(c=>({...c,x:c.x+x,y:c.y+y}))}else if(['+','=','-'].includes(event.key)){event.preventDefault();changeZoom(event.key==='-'?1/1.2:1.2)}else if(event.key==='Home'){event.preventDefault();fit()}}}
      onPointerDown={event=>{if((event.target as Element).closest('button'))return;setFollowing(false);drag.current={x:event.clientX,y:event.clientY,left:camera.x,top:camera.y};event.currentTarget.setPointerCapture(event.pointerId)}}
      onPointerMove={event=>{const d=drag.current;if(d)setCamera(c=>({...c,x:d.left+event.clientX-d.x,y:d.top+event.clientY-d.y}))}}
      onPointerUp={()=>{drag.current=null}} onPointerCancel={()=>{drag.current=null}}>
      <div className="flow-world" style={{width,height,transform:`translate(${camera.x}px,${camera.y}px) scale(${camera.zoom})`}}>
        <svg width={width} height={height} className="flow-connections" aria-hidden="true"><defs><marker id={marker} markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0L7 3.5L0 7" fill="var(--accent)"/></marker></defs>
          {nodes.flatMap(node=>node.dependencies.map(id=>{const from=nodes.find(n=>n.id===id);if(!from)return null;const a=from.x+250,b=node.x,mid=(a+b)/2,ay=from.y+(from.root?36:74),by=node.y+(node.root?36:74);return <path key={`${id}-${node.id}`} d={`M${a},${ay} C${mid},${ay} ${mid},${by} ${b},${by}`} markerEnd={`url(#${marker})`} className={`flow-edge ${node.status==='running'?'is-running':''}`} /> }))}
          {nodes.filter(node=>node.root&&shownActions(node).length>0).map(node=><path key={`actions-${node.id}`} className="flow-association" d={`M${node.x+22},${node.y+72} V${node.y+100+(shownActions(node).length-1)*118+50}`}/>)}
          {(p.plan?.revision||0)>0&&<path className="flow-edge flow-replan" d={`M${nodes.find(n=>n.id==='$reflection')!.x+110},${height-30} C${width/2},${height+70} 0,${height+70} 35,${height/2}`}><title>计划已调整 {p.plan?.revision} 次，原因见研究记录</title></path>}
        </svg>
        {nodes.map((node,index)=><div key={node.id} className={`flow-node-group ${role!=='all'&&role!==node.type?'is-dimmed':''}`}>
        {node.root?<>
          <button className="flow-agent" data-status={node.status} style={{left:node.x,top:node.y}} type="button" onClick={()=>setSelected(node.id)} aria-label={`${agentNames[node.type]||node.label}，${statusLabels[node.status]||node.status}`}>
            <span className="flow-agent-avatar"><Icon name={node.type==='analyst'?'layers':node.type==='report'?'chart':node.type==='reflection'?'target':'network'} size={23}/></span><span><strong>{agentNames[node.type]||node.label}</strong><StatusPill status={node.status}/></span>
          </button>
          {!node.actions?.length&&<div className="flow-awaiting" style={{left:node.x+42,top:node.y+100}}>{node.status==='pending'?'等待执行':'暂无动作记录'}</div>}
          {shownActions(node).map((item,actionIndex)=><button key={item.id} className={`flow-action ${item.query&&item.detail?'has-summary':''}`} data-status={item.state} style={{left:node.x+42,top:node.y+100+actionIndex*118}} type="button" onClick={()=>setSelected(item.id)} aria-label={`动作：${item.label}，${statusLabels[item.state]||item.state}`}>
            <span className="flow-action-heading"><Icon name={item.label.includes('修复')?'settings':item.label.includes('核对')?'target':'source'} size={15}/><span>{item.label}</span><StatusPill status={item.state}/></span><strong>{briefFeedback(item.query||item.detail)||node.label}</strong>
            {item.query&&item.detail&&<span className="flow-action-summary">{briefFeedback(item.detail)}</span>}
          </button>)}
          {(node.actions?.length||0)>3&&<button type="button" className="flow-actions-more" aria-expanded={Boolean(expanded[node.id])} style={{left:node.x+42,top:node.y+100+shownActions(node).length*118}} onClick={()=>setExpanded(value=>({...value,[node.id]:!value[node.id]}))}>{expanded[node.id]?'收起较早动作':`展开 ${node.actions!.length-3} 项较早动作`}</button>}
        </>:<button className="flow-node flow-tool-action" data-status={node.status} style={{left:node.x,top:node.y}} type="button" onClick={()=>setSelected(node.id)} aria-label={`${node.label}，${statusLabels[node.status]||node.status}`}>
          <span className="flow-node-top"><span className="flow-node-icon"><Icon name={node.type==='analyst'?'layers':node.type==='report'?'chart':node.type==='reflection'?'target':node.type==='browser'?'book':'search'} size={18}/></span><span className="flow-node-kind">{labels[node.type]||node.type}</span><span className="flow-node-sequence">{String(index+1).padStart(2,'0')}</span></span>
          <strong title={node.label}>{node.label}</strong><span className="flow-node-status"><StatusPill status={node.status}/></span>
          {node.actions?.length?<span className="flow-action-summary">{briefFeedback(node.actions[node.actions.length-1].detail)}</span>:null}
        </button>}
        </div>)}
      </div>
    </div>
    <div className="flow-bottom"><span className="flow-legend"><i className="legend-agent"/>角色<i className="legend-action"/>动作</span><span>{nodes.reduce((count,node)=>count+(node.actions?.length||0),0)} 项动作 · {nodes.filter(n=>['done','completed','success'].includes(n.status)).length} / {nodes.length} 步完成</span></div>
    <Modal open={Boolean(current)} onClose={()=>setSelected(null)} title={action?.label||(current?.root?agentNames[current.type]:current?.label)||'步骤详情'}>
      {current&&<div className="node-detail"><div className="node-detail-role"><Icon name="network" size={17}/>{agentNames[current.type]||current.type}<StatusPill status={action?.state||current.status}/></div>
        {action?<><h3>执行反馈</h3><p className="action-detail-text">{action.detail}</p>{action.query&&<><h3>输入</h3><p className="action-detail-text">{action.query}</p></>}
          {action.items.length>1&&<details><summary>{action.items.length} 条过程记录</summary>{action.items.map(item=><div className="action-retained-event" key={item.id}><span>{item.label}</span><p>{item.detail}</p></div>)}</details>}</>:<><h3>研究问题</h3><p>{current.query||current.label}</p>
          {!!current.actions?.length&&<><h3>执行动作</h3><div className="node-action-list">{current.actions.map(item=><button type="button" key={item.id} onClick={()=>setSelected(item.id)}><span><strong>{item.label}</strong><span>{briefFeedback(item.query||item.detail)}</span></span><StatusPill status={item.state}/></button>)}</div></>}
        </>}
        {!!current.dependencies.length&&<><h3>前置步骤</h3><div className="node-dependencies">{current.dependencies.map(id=><span className="tool-chip" key={id}>{nodes.find(n=>n.id===id)?.label||id}</span>)}</div></>}
        {current.error&&!action&&<p role="alert" className="composer-error">{current.error}</p>}
        {!!related.length&&<><h3>相关调用</h3>{related.map(tool=><div className="task-row" key={tool.call_id}><span>{readableTool(tool.tool_name)}</span><StatusPill status={tool.status}/></div>)}</>}
      </div>}
    </Modal>
  </section>
}
