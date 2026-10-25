import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import type { SSEvent } from '../hooks/useSSE'
import type { PlanSummaryProps } from './ResearchPlanSummary'
import type { PersistedToolCall } from './ToolTrace'
import { Icon, Modal, StatusPill, statusLabels } from './Interface'

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
interface FlowNode {id:string;type:string;label:string;query:string;status:string;dependencies:string[];x:number;y:number;error?:string|null;root?:boolean}
function currentFlowNode(nodes:FlowNode[]):FlowNode|undefined {
  return nodes.find(node=>node.status==='running')||nodes.find(node=>node.status==='paused')||nodes.find(node=>node.status==='failed')||nodes[nodes.length-1]
}
function evidenceLabel(type:string,purpose:string,query:string):string {
  if(type==='browser')try { const url=new URL(query),file=decodeURIComponent(url.pathname.split('/').filter(Boolean).pop()||'');return /\.pdf$/i.test(file)?file.replace(/^OSDI\d+_/,''):url.hostname.replace(/^www\./,'')+' · '+file.slice(0,28) } catch { /* Use the public plan label. */ }
  return purpose||labels[type]||'取证'
}
interface Props {
  plan:PlanSummaryProps['plan'];dag?:{nodes:DagNode[]};events:SSEvent[];status:string;tools?:PersistedToolCall[]
  analysis?:{status:string;phase:string|null;completed_steps:number}|null;history?:PlanSummaryProps['history']
}
function nodesFor(p:Props):FlowNode[] {
  const persisted=new Map((p.dag?.nodes||[]).map(node=>[node.node_id,node]))
  const steps=p.plan?.steps||p.dag?.nodes.map(node=>({node_id:node.node_id,node_type:node.node_type,purpose:labels[node.node_type||'']||'取证步骤',query:node.query||'',depends_on:node.depends_on||[]}))||[]
  const terminal=['completed','paused','canceled','failed'].includes(p.status)
  let analysisStart=-1
  p.events.forEach((event,index)=>{if(event.type==='agent_start'&&event.data.agent==='analyst')analysisStart=index})
  const eventState=(agent:string)=>{
    const relevant=agent==='analyst'?p.events:p.events.slice(Math.max(0,analysisStart))
    const event=[...relevant].reverse().find(e=>String(e.data.agent||'')===agent&&['agent_start','agent_complete','agent_end'].includes(e.type))
    if(!event)return p.status==='completed'?'unknown':'pending'
    if(event.type==='agent_start')return terminal?(p.status==='completed'?'unknown':p.status):'running'
    return String(event.data.status||'done')
  }
  const nodes:FlowNode[]=steps.filter(s=>!['analyst','report','reflection'].includes(s.node_type||'')).map(step=>{
    const current=persisted.get(step.node_id)
    let status=current?.status||'pending'
    if(status==='running'&&terminal)status=p.status==='completed'?'unknown':p.status
    const type=step.node_type||current?.node_type||'search'
    return {id:step.node_id,type,label:evidenceLabel(type,step.purpose,step.query),query:step.query,status,dependencies:step.depends_on||[],x:0,y:0,error:current?.last_error}
  })
  if(!nodes.length&&!p.events.length&&!p.analysis)return []
  const used=new Set(nodes.flatMap(n=>n.dependencies)),leaves=nodes.filter(n=>!used.has(n.id)).map(n=>n.id)
  const analysisStatus=p.analysis?.status==='completed'?'done':p.analysis?.status==='paused'?'paused':p.analysis?.status==='running'?(terminal?(p.status==='completed'?'unknown':p.status):'running'):eventState('analyst')
  nodes.push({id:'$analysis',type:'analyst',label:'问题分析',query:p.analysis?.phase?`当前问题阶段 · 已保存 ${p.analysis.completed_steps} 步`:'按问题阅读与分析来源',status:analysisStatus,dependencies:leaves,x:0,y:0,root:true})
  const analysisDone=['done','completed','success'].includes(analysisStatus)
  nodes.push({id:'$reflection',type:'reflection',label:'来源核对',query:'核对结论、原文与实验条件',status:analysisDone||p.status==='completed'?eventState('reflection'):'pending',dependencies:['$analysis'],x:0,y:0,root:true})
  nodes.push({id:'$report',type:'report',label:'图文报告',query:'组织正文、图表和引用',status:p.status==='completed'?'done':analysisDone?eventState('report'):'pending',dependencies:['$reflection'],x:0,y:0,root:true})
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
  const maxRows=Math.max(1,...counts.values())
  for(const node of nodes){const level=levels.get(node.id)||0,row=indices.get(level)||0;node.x=50+level*305;node.y=55+row*150+(maxRows-(counts.get(level)||1))*75;indices.set(level,row+1)}
  return nodes
}
function readableTool(name:string) {
  if(/search/i.test(name))return '搜索'
  if(/rag|retriev/i.test(name))return '资料检索'
  if(/browser|browse|web|fetch|read/i.test(name))return '网页读取'
  return name
}

export default function ResearchFlow(p:Props) {
  const nodes=useMemo(()=>nodesFor(p),[p.plan,p.dag,p.events,p.status,p.analysis])
  const viewport=useRef<HTMLDivElement>(null),drag=useRef<{x:number;y:number;left:number;top:number}|null>(null),initialized=useRef(false)
  const [camera,setCamera]=useState({x:24,y:24,zoom:.8}),[selected,setSelected]=useState<string|null>(null)
  const marker=useId().replace(/:/g,'')
  const width=Math.max(800,...nodes.map(n=>n.x+265)),height=Math.max(420,...nodes.map(n=>n.y+145))
  const fit=useCallback((readable=false)=>{const el=viewport.current;if(!el||el.clientWidth<100)return;const fitted=Math.min(1,(el.clientWidth-48)/width,(el.clientHeight-48)/height),zoom=Math.max(readable ? .65 : .25,fitted);const current=readable?currentFlowNode(nodes):undefined;setCamera(current&&fitted<zoom?{zoom,x:el.clientWidth/2-(current.x+112)*zoom,y:el.clientHeight/2-(current.y+54)*zoom}:{x:(el.clientWidth-width*zoom)/2,y:(el.clientHeight-height*zoom)/2,zoom});initialized.current=true},[width,height,nodes])
  useEffect(()=>{const el=viewport.current;if(!el)return;const observer=new ResizeObserver(()=>{if(!initialized.current&&nodes.length)fit(true)});observer.observe(el);return()=>observer.disconnect()},[fit,nodes.length])
  const changeZoom=(factor:number)=>{const el=viewport.current;if(!el)return;setCamera(c=>{const zoom=Math.min(1.7,Math.max(.25,c.zoom*factor)),x=el.clientWidth/2,y=el.clientHeight/2;return{zoom,x:x-(x-c.x)*zoom/c.zoom,y:y-(y-c.y)*zoom/c.zoom}})}
  const focusCurrent=()=>{const node=currentFlowNode(nodes)||nodes[nodes.length-1],el=viewport.current;if(node&&el)setCamera({zoom:1,x:el.clientWidth/2-node.x-112,y:el.clientHeight/2-node.y-54})}
  const current=nodes.find(n=>n.id===selected)
  const related=current?(p.tools||[]).filter(tool=>tool.args_json?.node_id===current.id||Boolean(current.query&&(tool.args_json?.query===current.query||tool.args_json?.url===current.query))||(current.root&&tool.agent_type===current.type)):[]
  if(!nodes.length)return <div className="flow-empty"><Icon name="network" size={36}/><p>正在取得研究计划</p></div>
  return <section className="flow-panel" aria-label="研究工作流">
    <div className="flow-heading"><div><Icon name="network"/><strong>研究工作流</strong><StatusPill status={p.status}/></div><div className="canvas-toolbar" role="group" aria-label="画布操作">
      <button type="button" className="icon-button" title="缩小" aria-label="缩小流程图" onClick={()=>changeZoom(1/1.2)}><Icon name="minus" size={17}/></button><span>{Math.round(camera.zoom*100)}%</span><button type="button" className="icon-button" title="放大" aria-label="放大流程图" onClick={()=>changeZoom(1.2)}><Icon name="plus" size={17}/></button>
      <button type="button" className="icon-button" title="适应画布" aria-label="适应画布" onClick={()=>fit()}><Icon name="fit" size={18}/></button><button type="button" className="icon-button" title="定位当前步骤" aria-label="定位当前步骤" onClick={focusCurrent}><Icon name="target" size={18}/></button>
    </div></div>
    <div ref={viewport} className="flow-viewport" tabIndex={0} role="region" aria-label="可拖动研究流程图，方向键平移，加减号缩放，Home 适应画布"
      onKeyDown={event=>{if(event.target!==event.currentTarget)return;const moves:Record<string,[number,number]>={ArrowLeft:[40,0],ArrowRight:[-40,0],ArrowUp:[0,40],ArrowDown:[0,-40]};if(moves[event.key]){event.preventDefault();const [x,y]=moves[event.key];setCamera(c=>({...c,x:c.x+x,y:c.y+y}))}else if(['+','=','-'].includes(event.key)){event.preventDefault();changeZoom(event.key==='-'?1/1.2:1.2)}else if(event.key==='Home'){event.preventDefault();fit()}}}
      onPointerDown={event=>{if((event.target as Element).closest('button'))return;drag.current={x:event.clientX,y:event.clientY,left:camera.x,top:camera.y};event.currentTarget.setPointerCapture(event.pointerId)}}
      onPointerMove={event=>{const d=drag.current;if(d)setCamera(c=>({...c,x:d.left+event.clientX-d.x,y:d.top+event.clientY-d.y}))}}
      onPointerUp={()=>{drag.current=null}} onPointerCancel={()=>{drag.current=null}}>
      <div className="flow-world" style={{width,height,transform:`translate(${camera.x}px,${camera.y}px) scale(${camera.zoom})`}}>
        <svg width={width} height={height} className="flow-connections" aria-hidden="true"><defs><marker id={marker} markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0L7 3.5L0 7" fill="var(--accent)"/></marker></defs>
          {nodes.flatMap(node=>node.dependencies.map(id=>{const from=nodes.find(n=>n.id===id);if(!from)return null;const a=from.x+225,b=node.x,mid=(a+b)/2;return <path key={`${id}-${node.id}`} d={`M${a},${from.y+54} C${mid},${from.y+54} ${mid},${node.y+54} ${b},${node.y+54}`} markerEnd={`url(#${marker})`} className={`flow-edge ${node.status==='running'?'is-running':''}`} /> }))}
          {(p.plan?.revision||0)>0&&<path className="flow-edge flow-replan" d={`M${nodes.find(n=>n.id==='$reflection')!.x+110},${height-30} C${width/2},${height+70} 0,${height+70} 35,${height/2}`}><title>计划已调整 {p.plan?.revision} 次，原因见研究记录</title></path>}
        </svg>
        {nodes.map((node,index)=><button key={node.id} className="flow-node" data-status={node.status} style={{left:node.x,top:node.y}} type="button" onClick={()=>setSelected(node.id)} aria-label={`${node.label}，${statusLabels[node.status]||node.status}`}>
          <span className="flow-node-top"><span className="flow-node-icon"><Icon name={node.type==='analyst'?'layers':node.type==='report'?'chart':node.type==='reflection'?'target':node.type==='browser'?'book':'search'} size={18}/></span><span className="flow-node-kind">{labels[node.type]||node.type}</span><span className="flow-node-sequence">{String(index+1).padStart(2,'0')}</span></span>
          <strong>{node.label}</strong><span className="flow-node-status"><StatusPill status={node.status}/></span>
        </button>)}
      </div>
    </div>
    <div className="flow-bottom"><span>{nodes.filter(n=>['done','completed','success'].includes(n.status)).length} / {nodes.length} 步完成</span><div>{(p.tools||[]).slice(-4).map(tool=><span key={tool.call_id} className="tool-chip"><Icon name="source" size={12}/>{readableTool(tool.tool_name)}<StatusPill status={tool.status}/></span>)}</div></div>
    <Modal open={Boolean(current)} onClose={()=>setSelected(null)} title={current?.label||'步骤详情'}>
      {current&&<div className="node-detail"><StatusPill status={current.status}/><h3>研究问题</h3><p>{current.query||current.label}</p>
        {!!current.dependencies.length&&<><h3>前置步骤</h3><div className="node-dependencies">{current.dependencies.map(id=><span className="tool-chip" key={id}>{nodes.find(n=>n.id===id)?.label||id}</span>)}</div></>}
        {current.error&&<p role="alert" className="composer-error">{current.error}</p>}
        {!!related.length&&<><h3>相关调用</h3>{related.map(tool=><div className="task-row" key={tool.call_id}><span>{readableTool(tool.tool_name)}</span><StatusPill status={tool.status}/></div>)}</>}
      </div>}
    </Modal>
  </section>
}
