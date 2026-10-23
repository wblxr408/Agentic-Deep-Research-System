import {useRef,useState} from 'react'
import {UnderstandingSummary} from './QueryUnderstandingPanel'
import type {UnderstandingSnapshot} from './QueryUnderstandingPanel'

async function post(path:string,body:unknown) {
  const response=await fetch(`/api/v1/research${path}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
  const value=await response.json().catch(()=>({detail:'服务返回内容不完整，请保留配置后重试。'}))
  if(!response.ok) {
    const detail=value.detail
    throw new Error(typeof detail==='string'?detail:Array.isArray(detail)?detail.map((item:{loc?:unknown[];msg?:string})=>
      `${item.loc?.join('.')||'配置'}：${item.msg||'字段无效'}`).join('；'):'配置已变化或尚需澄清，请重新预览。')
  }
  return value
}

export default function ResearchConfigurationEditor({query,parameters,onStarted}:{
  query:string;parameters?:Record<string,unknown>;onStarted:(sessionId:string)=>void
}) {
  const [text,setText]=useState(()=>JSON.stringify({...parameters,query},null,2))
  const [preview,setPreview]=useState<{body:string;value:UnderstandingSnapshot}|null>(null)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const pending=useRef(false)
  async function perform(start:boolean) {
    if(pending.current)return
    pending.current=true;setBusy(true);setError('')
    try {
      const body=JSON.parse(text)
      if(!body||Array.isArray(body)||typeof body!=='object'||typeof body.query!=='string'||!body.query.trim())
        throw new Error('请填写包含非空query的配置对象。')
      // A new request does not inherit the old root's approvals or preview.
      delete body.query_preview_id;delete body.user_confirmed
      if(start) {
        if(!preview||preview.body!==text||!preview.value.ready)throw new Error('请先预览当前配置并处理待澄清项。')
        const created=await post('',{...body,query_preview_id:preview.value.interpretation_id})
        if(typeof created.session_id!=='string')throw new Error('未取得新任务身份，请保留当前配置。')
        onStarted(created.session_id)
      } else {
        const value=await post('/understanding',body) as UnderstandingSnapshot
        setPreview({body:text,value})
      }
    } catch(problem) {
      if(start)setPreview(null)
      setError(problem instanceof Error?problem.message:'配置未能提交，请检查内容。')
    } finally {pending.current=false;setBusy(false)}
  }
  return <details className="card p-4 text-sm" aria-label="修改配置创建新研究">
    <summary className="cursor-pointer font-medium">修改配置并创建新研究</summary>
    <p className="my-3 text-xs text-xmgray-500">可调整问题、来源、对象、计划策略、补证轮次和交付方案。预览使用当前本人可用配置；开始后创建独立任务，旧任务及其已消耗预算继续保留在历史中。</p>
    <label className="block text-xs">研究请求 JSON<textarea className="input-xm mt-2 w-full font-mono text-xs" rows={12}
      maxLength={200000} disabled={busy} value={text} onChange={event=>{setText(event.target.value);setPreview(null);setError('')}}/></label>
    <div className="my-3 flex flex-wrap gap-3">
      <button className="btn-ghost text-sm" type="button" disabled={busy} onClick={()=>perform(false)}>{busy?'正在处理…':'预览修改后的配置'}</button>
      <button className="btn-primary text-sm" type="button" disabled={busy||!preview?.value.ready||preview.body!==text}
        onClick={()=>perform(true)}>按此配置开始新研究</button>
    </div>
    {error&&<p role="alert" className="text-xs text-red-700">{error}</p>}
    {preview&&<UnderstandingSummary value={preview.value}/>}
  </details>
}
