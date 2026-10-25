import {useEffect,useMemo,useRef,useState} from 'react'
import type {SSEvent} from '../hooks/useSSE'
import {Icon} from './Interface'

import {agentNames,executionItems} from './researchExecution'
export {agentNames} from './researchExecution'

export default function ExecutionFeed({events,connection,status}:{events:SSEvent[];connection:string;status:string}) {
  const [agent,setAgent]=useState('all'),[following,setFollowing]=useState(true),[limit,setLimit]=useState(100)
  const scroller=useRef<HTMLDivElement>(null)
  const items=useMemo(()=>executionItems(events),[events])
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
