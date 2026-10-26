import {uiDefinition,useLocale,t,uiMessage} from '../i18n'
import { useRef,useState } from 'react'
import ReportPreview from './ReportPreview'
import type { RetainedCitation } from './RetainedCitations'

interface Version {report_id:string;sequence:number;created_at:string;status:string;kind:string;supported_claims?:string|null;total_claims?:string|null}
interface Snapshot extends Version {report:string;reader_report?:string;citations:RetainedCitation[];audit?:{needs_review?:boolean;audit_incomplete?:boolean;total_claims?:number;supported_claims?:number};
  source_versions:Array<{evidence_id:string;version_id:string;coverage?:string}>}
const labels:Record<string,string>=uiDefinition({supported_report:'完成稿',saved_draft:'已保存草稿',incomplete_response:'中断响应'})
export default function ReportHistory({sessionId}:{sessionId:string}) {
  useLocale()

  const [versions,setVersions]=useState<Version[]>([]),[selected,setSelected]=useState<Snapshot|null>(null)
  const [loaded,setLoaded]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('')
  const pending=useRef(false)
  async function load(id?:string) {
    if(pending.current)return
    pending.current=true;setBusy(true);setError('')
    try {
      const response=await fetch(`/api/v1/research/${encodeURIComponent(sessionId)}/reports${id?'/'+encodeURIComponent(id):''}`)
      const value=await response.json()
      if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:t("无法读取历史报告。"))
      if(id)setSelected(value)
      else {setVersions(value.items);setLoaded(true)}
    }catch(error){setError(error instanceof Error?uiMessage(error.message):t("报告历史读取未完成。"))}
    finally{pending.current=false;setBusy(false)}
  }
  function download() {
    if(selected?.status!=='supported_report'||selected.kind!=='report')return
    const url=URL.createObjectURL(new Blob([selected.reader_report||selected.report],{type:'text/markdown;charset=utf-8'}))
    const anchor=document.createElement('a');anchor.href=url;anchor.download=t("研究报告-第{0}版.md", selected.sequence);anchor.click()
    URL.revokeObjectURL(url)
  }
  return <details data-app-only className="mb-4 rounded-lg border p-3 text-sm" aria-label={t("历史报告")}>
    <summary className="cursor-pointer font-medium">{t("历史报告")}</summary>
    <p className="my-2 text-xs text-xmgray-500">{t("选择保存稿查看正文与来源。")}</p>
    <button type="button" className="btn-ghost text-xs" disabled={busy} onClick={()=>load()}>{t("读取历史报告")}</button>
    {busy&&<p role="status" className="text-xs">{t("正在读取…")}</p>}
    {error&&<p role="alert" className="text-xs text-red-700">{uiMessage(error)}</p>}
    {loaded&&!versions.length&&<p className="text-xs">{t("此任务尚无保存的报告版本；旧任务的当前报告仍在主阅读区。")}</p>}
    {!!versions.length&&<ul className="my-2 space-y-1">{versions.map(version=><li key={version.report_id}>
      <button type="button" className="btn-ghost text-xs" disabled={busy} onClick={()=>load(version.report_id)}>{t("第")}{version.sequence}{t("版 · ")}{labels[version.status]||version.status} · {new Date(version.created_at).toLocaleString()}</button>
    </li>)}</ul>}
    {selected&&<section className="mt-3 border-t pt-3">
      <div className="mb-2 flex flex-wrap items-center gap-3"><h3>{t("第")}{selected.sequence}{t("版 · ")}{labels[selected.status]||selected.status}</h3>
        <button type="button" className="btn-ghost text-xs" onClick={()=>setSelected(null)}>{t("关闭历史稿")}</button>
        {selected.status==='supported_report'&&<button type="button" className="btn-ghost text-xs" onClick={download}>{t("下载该版Markdown")}</button>}
      </div>
      {selected.kind==='partial_response'?<pre className="whitespace-pre-wrap break-words text-xs">{selected.report}</pre>:
        <ReportPreview key={selected.report_id} report={selected.reader_report||selected.report} citations={selected.citations} reportAudit={selected.audit} sessionId={sessionId}/>}
      <details className="my-2 text-xs"><summary className="cursor-pointer">{t("该版来源关联")}</summary>
        <p>{t("该次保存的来源关联。")}</p>
        <ul className="list-disc space-y-1 break-all pl-5">{selected.source_versions.map(source=><li key={source.evidence_id}>{source.evidence_id} · {source.version_id} · {source.coverage}</li>)}</ul>
      </details>
    </section>}
  </details>
}
