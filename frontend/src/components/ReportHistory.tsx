import { useRef,useState } from 'react'
import ReportPreview from './ReportPreview'
import type { RetainedCitation } from './RetainedCitations'

interface Version {report_id:string;sequence:number;created_at:string;status:string;kind:string;supported_claims?:string|null;total_claims?:string|null}
interface Snapshot extends Version {report:string;reader_report?:string;citations:RetainedCitation[];audit?:{needs_review?:boolean;audit_incomplete?:boolean;total_claims?:number;supported_claims?:number};
  source_versions:Array<{evidence_id:string;version_id:string;coverage?:string}>}
const labels:Record<string,string>={supported_report:'审核完成稿',saved_draft:'已保存草稿',incomplete_response:'中断响应'}
export default function ReportHistory({sessionId}:{sessionId:string}) {
  const [versions,setVersions]=useState<Version[]>([]),[selected,setSelected]=useState<Snapshot|null>(null)
  const [loaded,setLoaded]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('')
  const pending=useRef(false)
  async function load(id?:string) {
    if(pending.current)return
    pending.current=true;setBusy(true);setError('')
    try {
      const response=await fetch(`/api/v1/research/${encodeURIComponent(sessionId)}/reports${id?'/'+encodeURIComponent(id):''}`)
      const value=await response.json()
      if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:'无法读取报告版本。')
      if(id)setSelected(value)
      else {setVersions(value.items);setLoaded(true)}
    }catch(error){setError(error instanceof Error?error.message:'报告历史读取未完成。')}
    finally{pending.current=false;setBusy(false)}
  }
  function download() {
    if(selected?.status!=='supported_report'||selected.kind!=='report')return
    const url=URL.createObjectURL(new Blob([selected.reader_report||selected.report],{type:'text/markdown;charset=utf-8'}))
    const anchor=document.createElement('a');anchor.href=url;anchor.download=`研究报告-第${selected.sequence}版.md`;anchor.click()
    URL.revokeObjectURL(url)
  }
  return <details data-app-only className="mb-4 rounded-lg border p-3 text-sm" aria-label="报告版本历史">
    <summary className="cursor-pointer font-medium">报告版本历史</summary>
    <p className="my-2 text-xs text-xmgray-500">查看原任务保留的正文、审核和来源版本。历史文本视图不重绘图表，不恢复额度，也不把生成结论作为新事实。</p>
    <button type="button" className="btn-ghost text-xs" disabled={busy} onClick={()=>load()}>读取报告版本</button>
    {busy&&<p role="status" className="text-xs">正在读取…</p>}
    {error&&<p role="alert" className="text-xs text-red-700">{error}</p>}
    {loaded&&!versions.length&&<p className="text-xs">此任务尚无保存的报告版本；旧任务的当前报告仍在主阅读区。</p>}
    {!!versions.length&&<ul className="my-2 space-y-1">{versions.map(version=><li key={version.report_id}>
      <button type="button" className="btn-ghost text-xs" disabled={busy} onClick={()=>load(version.report_id)}>第{version.sequence}版 · {labels[version.status]||version.status} · {new Date(version.created_at).toLocaleString()}</button>
    </li>)}</ul>}
    {selected&&<section className="mt-3 border-t pt-3">
      <div className="mb-2 flex flex-wrap items-center gap-3"><h3>第{selected.sequence}版 · {labels[selected.status]||selected.status}</h3>
        <button type="button" className="btn-ghost text-xs" onClick={()=>setSelected(null)}>关闭历史稿</button>
        {selected.status==='supported_report'&&<button type="button" className="btn-ghost text-xs" onClick={download}>下载该版Markdown</button>}
      </div>
      {selected.kind==='partial_response'?<pre className="whitespace-pre-wrap break-words text-xs">{selected.report}</pre>:
        <ReportPreview report={selected.reader_report||selected.report} citations={selected.citations} reportAudit={selected.audit} sessionId={sessionId}/>}
      <details className="my-2 text-xs"><summary className="cursor-pointer">该版来源关联</summary>
        <p>以下是该次提供的资料映射；具体主张的支持情况见原审核。</p>
        <ul className="list-disc space-y-1 break-all pl-5">{selected.source_versions.map(source=><li key={source.evidence_id}>{source.evidence_id} · {source.version_id} · {source.coverage}</li>)}</ul>
      </details>
    </section>}
  </details>
}
