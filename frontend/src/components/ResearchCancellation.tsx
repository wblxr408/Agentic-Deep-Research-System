import {useRef,useState} from 'react'

export default function ResearchCancellation({sessionId,executionId,status,inflight,onRefresh}:{
  sessionId:string;executionId:string|null;status:string;inflight?:number;onRefresh:()=>Promise<void>
}) {
  const [busy,setBusy]=useState(false),[error,setError]=useState('')
  const pending=useRef(false),requestId=useRef(crypto.randomUUID())
  async function cancel() {
    if(pending.current)return
    pending.current=true;setBusy(true);setError('')
    try {
      const response=await fetch(`/api/v1/research/${encodeURIComponent(sessionId)}/cancel`,{
        method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({request_id:requestId.current,execution_id:executionId})})
      const result=await response.json()
      if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'取消结果尚未确认，请刷新任务状态。')
      try{await onRefresh()}catch{setError('取消已保存，任务状态刷新未完成；可重新读取。')}
    }catch(problem){setError(problem instanceof Error?problem.message:'取消结果尚未确认，可使用同一请求重试。')}
    finally{pending.current=false;setBusy(false)}
  }
  const canceled=status==='canceled',allowed=['pending','running','paused'].includes(status)
  if(!canceled&&!allowed)return null
  return <section data-app-only className="card p-4 text-sm" aria-label="任务取消">
    {canceled?<>
      <p className="font-medium">研究已取消</p>
      <p className="my-2 text-xs text-xmgray-500">已停止后续调度。已发出的服务请求可能继续结算，已取得的资料和用量仍保留；取消不生成完成报告。</p>
      {!!inflight&&<p className="text-xs">尚有{inflight}条模型收据未结算，不能据此判断服务仍在执行；缺少结算时保留未知用量。</p>}
      <button type="button" className="btn-ghost mt-2 text-xs" disabled={busy} onClick={async()=>{
        setBusy(true);setError('');try{await onRefresh()}catch{setError('刷新未完成，请稍后重试。')}finally{setBusy(false)}}}>刷新状态与用量</button>
    </>:<>
      <button type="button" className="btn-ghost text-sm text-red-700" disabled={busy} onClick={cancel}>{busy?'正在取消…':'取消本次研究'}</button>
      <p className="mt-2 text-xs text-xmgray-500">保留当前资料和已用额度，停止新的研究步骤；已经发出的调用仍按实际或保守用量结算。</p>
    </>}
    {error&&<p role="alert" className="mt-2 text-xs text-red-700">{error}</p>}
  </section>
}
