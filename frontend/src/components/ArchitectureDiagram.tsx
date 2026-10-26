import {useCallback,useEffect,useId,useMemo,useRef,useState} from 'react'
import type {CSSProperties,ReactNode} from 'react'
import {Icon} from './Interface'
import AgentAvatar from './AgentAvatar'
import type {ArchitectureNode,ArchitectureRegion,ArchitectureScene,NodeKind} from './researchArchitecture'
import {orthogonalRoutes} from './orthogonalRouting'

const kindNames:Record<NodeKind,string>={action:'处理',agent:'Agent',tool:'工具',store:'留存',decision:'判断',control:'控制',extension:'扩展位'}
const dimensions=(node:ArchitectureNode)=>({width:node.width||190,height:node.height||88})
export default function ArchitectureDiagram({scene}:{scene:ArchitectureScene}) {
  const routes=useMemo(()=>orthogonalRoutes(scene),[scene])
  const viewport=useRef<HTMLDivElement>(null),drag=useRef<{x:number;y:number;left:number;top:number}|null>(null),initialized=useRef(false)
  const [camera,setCamera]=useState({zoom:.8,x:20,y:20}),[selected,setSelected]=useState(scene.tour[0]),[step,setStep]=useState(0)
  const [reduced,setReduced]=useState(()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  const [playing,setPlaying]=useState(()=>!reduced),[channel,setChannel]=useState('all')
  const marker=useId().replace(/:/g,''),current=scene.nodes.find(node=>node.id===selected)||scene.nodes[0]
  const fit=useCallback((readable=false)=>{const el=viewport.current;if(!el)return
    const fitted=Math.min(1,(el.clientWidth-36)/scene.width,(el.clientHeight-32)/scene.height),zoom=Math.max(readable && el.clientWidth<700 ? .8 : .25,fitted)
    const first=scene.nodes.find(node=>node.id===scene.tour[0])!,focused=readable&&fitted<zoom
    setCamera({zoom,x:focused?Math.min(24,el.clientWidth/2-(first.x+95)*zoom):Math.max(16,(el.clientWidth-scene.width*zoom)/2),y:focused?Math.min(24,el.clientHeight/2-(first.y+44)*zoom):16});initialized.current=true
  },[scene.width,scene.height])
  useEffect(()=>{const el=viewport.current;if(!el)return;const observer=new ResizeObserver(()=>{if(!initialized.current)fit(true)});observer.observe(el);return()=>observer.disconnect()},[fit])
  useEffect(()=>{const media=window.matchMedia('(prefers-reduced-motion: reduce)');const change=()=>{setReduced(media.matches);if(media.matches)setPlaying(false)};media.addEventListener('change',change);return()=>media.removeEventListener('change',change)},[])
  useEffect(()=>setSelected(scene.tour[step]),[step,scene.tour])
  useEffect(()=>{if(!playing||reduced)return;const timer=window.setInterval(()=>{if(!document.hidden)setStep(previous=>(previous+1)%scene.tour.length)},2400);return()=>window.clearInterval(timer)},[playing,reduced,scene.tour])
  const focus=(node:ArchitectureNode)=>{const el=viewport.current;if(!el)return;const {width,height}=dimensions(node),zoom=Math.max(.9,camera.zoom)
    setCamera({zoom,x:Math.min(24,Math.max(el.clientWidth-scene.width*zoom-24,el.clientWidth/2-(node.x+width/2)*zoom)),y:Math.min(24,Math.max(el.clientHeight-scene.height*zoom-24,el.clientHeight/2-(node.y+height/2)*zoom))})}
  const choose=(id:string,locate=false)=>{setSelected(id);setPlaying(false);const index=scene.tour.indexOf(id);if(index>=0)setStep(index);if(locate){const node=scene.nodes.find(item=>item.id===id);if(node)focus(node)}}
  const next=()=>{setPlaying(false);const index=(step+1)%scene.tour.length;setStep(index);setSelected(scene.tour[index])}
  const zoomBy=(factor:number)=>{const el=viewport.current;if(!el)return;setCamera(previous=>{const zoom=Math.max(.3,Math.min(1.6,previous.zoom*factor));return {zoom,x:el.clientWidth/2-(el.clientWidth/2-previous.x)*zoom/previous.zoom,y:el.clientHeight/2-(el.clientHeight/2-previous.y)*zoom/previous.zoom}})}
  const renderNode=(node:ArchitectureNode,region?:ArchitectureRegion)=>{
    const {width,height}=dimensions(node),compact=height<65
    return <button key={node.id} type="button" className={`architecture-node architecture-node--${node.kind} ${compact?'is-compact':''} ${selected===node.id?'is-selected':''}`} aria-label={`架构节点：${node.title}`} aria-pressed={selected===node.id}
      style={{left:node.x-(region?.x||0),top:node.y-(region?.y||0),width,height}} onClick={()=>choose(node.id)}>
      {node.kind==='agent'?<AgentAvatar name={node.title} role={node.role||'report'} expression={scene.tour[step]===node.id?'working':'waiting'}/>:<span className="architecture-node-icon"><Icon name={node.kind==='tool'?'settings':node.kind==='store'?'database':node.kind==='control'?'target':node.kind==='decision'?'network':'layers'} size={19}/></span>}
      <span className="architecture-node-copy"><strong>{node.title}</strong>{!compact&&<span>{kindNames[node.kind]}</span>}</span>
      {selected===node.id&&<span className="architecture-node-dot"/>}
    </button>
  }
  const renderRegion=(region:ArchitectureRegion):ReactNode=>{const parent=scene.regions.find(item=>item.id===region.parent)
    return <section key={region.id} role="group" aria-label={region.title} className={`architecture-region architecture-region--${region.tone||'default'}`} style={{left:region.x-(parent?.x||0),top:region.y-(parent?.y||0),width:region.width,height:region.height}}>
      <header hidden={region.hideHeader}>{region.agentRole&&<AgentAvatar name="阶段 Agent" role={region.agentRole} expression="working"/>}<strong>{region.title}</strong><span>{region.subtitle}</span></header>
      {scene.regions.filter(item=>item.parent===region.id).map(renderRegion)}
      {scene.nodes.filter(node=>node.region===region.id).map(node=>renderNode(node,region))}
    </section>
  }
  return <section className="architecture-figure" aria-label={`${scene.title}架构图`}>
    <div className="architecture-toolbar"><div className="architecture-demo-controls"><span className="architecture-demo-label">原理演示</span>
      <button type="button" className="icon-button" disabled={reduced} aria-label={playing?'暂停架构演示':'播放架构演示'} onClick={()=>setPlaying(value=>!value)}><Icon name={playing?'pause':'play'} size={17}/></button>
      <button type="button" className="icon-button" aria-label="下一步架构演示" onClick={next}><Icon name="step" size={17}/></button><span>{step+1} / {scene.tour.length}</span>
    </div><div className="architecture-view-controls"><label>连线<select aria-label="架构连线类型" value={channel} onChange={event=>setChannel(event.target.value)}><option value="all">全部</option><option value="data">数据流</option><option value="control">控制流</option></select></label>
      <label className="architecture-node-picker">定位<select aria-label="定位架构节点" value={selected} onChange={event=>choose(event.target.value,true)}>{scene.nodes.map(node=><option key={node.id} value={node.id}>{node.title}</option>)}</select></label>
      <button type="button" className="icon-button" aria-label="缩小架构图" onClick={()=>zoomBy(1/1.2)}><Icon name="minus" size={16}/></button><span>{Math.round(camera.zoom*100)}%</span>
      <button type="button" className="icon-button" aria-label="放大架构图" onClick={()=>zoomBy(1.2)}><Icon name="plus" size={16}/></button>
      <button type="button" className="icon-button" aria-label="适应架构画布" onClick={()=>fit()}><Icon name="fit" size={17}/></button>
      <button type="button" className="icon-button" aria-label="定位当前架构节点" onClick={()=>focus(current)}><Icon name="target" size={17}/></button>
    </div></div>
    <div className="architecture-viewport" ref={viewport} role="region" aria-label="架构画布，方向键平移，加减号缩放" tabIndex={0}
      onKeyDown={event=>{if(event.target!==event.currentTarget)return;const moves:Record<string,[number,number]>={ArrowLeft:[40,0],ArrowRight:[-40,0],ArrowUp:[0,40],ArrowDown:[0,-40]};if(moves[event.key]){event.preventDefault();const [x,y]=moves[event.key];setCamera(value=>({...value,x:value.x+x,y:value.y+y}))}else if(['+','=','-'].includes(event.key)){event.preventDefault();zoomBy(event.key==='-'?1/1.2:1.2)}else if(event.key==='Home'){event.preventDefault();fit()}}}
      onPointerDown={event=>{if((event.target as Element).closest('button,select'))return;drag.current={x:event.clientX,y:event.clientY,left:camera.x,top:camera.y};event.currentTarget.setPointerCapture(event.pointerId)}}
      onPointerMove={event=>{const previous=drag.current;if(previous)setCamera(value=>({...value,x:previous.left+event.clientX-previous.x,y:previous.top+event.clientY-previous.y}))}}
      onPointerUp={()=>{drag.current=null}} onPointerCancel={()=>{drag.current=null}}>
      <div className="architecture-world" data-playing={playing&&!reduced} style={{width:scene.width,height:scene.height,transform:`translate(${camera.x}px,${camera.y}px) scale(${camera.zoom})`} as CSSProperties}>
        {scene.regions.filter(region=>!region.parent).map(renderRegion)}
        <svg className="architecture-edges" width={scene.width} height={scene.height} aria-hidden="true"><defs>{['data','control','return'].map(kind=><marker key={kind} id={`${marker}-${kind}`} markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0 0L7 3.5L0 7" className={`architecture-arrow architecture-arrow--${kind}`}/></marker>)}</defs>
          {scene.edges.map((edge,index)=>{const {path,x,y,labelVisible}=routes[index],kind=edge.kind||'data',related=edge.from===selected||edge.to===selected
            const active=playing&&!reduced&&edge.to===scene.tour[step],visible=channel==='all'||(channel==='control'?kind==='control':kind!=='control')
            return <g key={index} className={`architecture-edge architecture-edge--${kind} ${related?'is-related':''} ${!visible?'is-muted':''}`}>
              <path d={path} markerEnd={`url(#${marker}-${kind})`}/>{edge.label&&labelVisible&&<text x={x} y={y} textAnchor="middle">{edge.label}</text>}
              {active&&visible&&<path className="architecture-packet" d={path} pathLength="100"/>}
            </g>
          })}
        </svg>
        {scene.nodes.filter(node=>!node.region).map(node=>renderNode(node))}
      </div>
    </div>
    <div className="architecture-legend"><span><i/>数据流</span><span><i className="is-control"/>控制流</span><span><i className="is-return"/>返回／续轮</span><span>点击节点查看交接</span></div>
    <section className="architecture-inspector" aria-label="架构节点详情"><div className="architecture-detail-heading"><span>{kindNames[current.kind]}</span><h3>{current.title}</h3><button type="button" className="btn-ghost" onClick={()=>focus(current)}>定位节点<Icon name="target" size={15}/></button></div><p>{current.detail}</p>
      <div className="architecture-contract"><div><h4>输入</h4><ul>{current.inputs.length?current.inputs.map(item=><li key={item}>{item}</li>):<li>用户或阶段输入</li>}</ul></div>
        <div><h4>输出</h4><ul>{current.outputs.length?current.outputs.map(item=><li key={item}>{item}</li>):<li>阶段记录</li>}</ul></div>
        <div><h4>实现位置</h4>{current.source.map(path=><code key={path}>{path}</code>)}</div></div>
      <div className="architecture-neighbors">{scene.edges.filter(edge=>edge.from===selected||edge.to===selected).map((edge,index)=>{const incoming=edge.to===selected,id=incoming?edge.from:edge.to,node=scene.nodes.find(item=>item.id===id)!;return <button key={index} type="button" onClick={()=>choose(id,true)}>{incoming?'来自':'流向'} · {node.title}{edge.label&&<span>{edge.label}</span>}<Icon name="arrow" size={13}/></button>})}</div>
    </section>
  </section>
}
