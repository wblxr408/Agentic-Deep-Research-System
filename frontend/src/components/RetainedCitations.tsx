import { useState } from 'react'

export interface RetainedCitation {
  citation_id:string;source_url:string;source_title:string;extracted_evidence?:string
  locator?:{evidence_id:string;start:number;end:number;offset_unit?:string;parse_version_id?:string|null;chunk_reference?:unknown;returned_span?:unknown}|null
}
interface Quote {text:string;start:number;end:number;evidence_id:string;version_id:string;coverage:string;upstream_locator:unknown}
export default function RetainedCitations({sessionId,citations}:{sessionId?:string|null;citations:RetainedCitation[]}) {
  const [selected,setSelected]=useState(''),[quote,setQuote]=useState<Quote|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false)
  const located=citations.filter(citation=>citation.locator?.evidence_id)
  async function read(citation:RetainedCitation,expand=false) {
    if (!sessionId||!citation.locator)return
    setSelected(citation.citation_id);setLoading(true);setError('');setQuote(null)
    const locator=citation.locator
    const parameters=new URLSearchParams({start:String(expand?Math.max(0,locator.start-400):locator.start)})
    if (!expand)parameters.set('end',String(locator.end))
    try {
      const response=await fetch(`/api/v1/research/${encodeURIComponent(sessionId)}/evidence/${encodeURIComponent(locator.evidence_id)}?${parameters}`)
      if (!response.ok)throw new Error(response.status===404?'该任务未保留此原文，或当前无权访问。':'无法读取该版本的原文范围。')
      setQuote(await response.json())
    }catch(error){setError(error instanceof Error?error.message:'原文读取失败。')}
    finally{setLoading(false)}
  }
  if (!located.length)return null
  return <details className="mt-6 rounded-xl border border-xmgray-200 p-4 text-sm" aria-label="本次报告的保留依据定位">
    <summary className="cursor-pointer font-medium">本次保留的依据与原文位置</summary>
    <p className="my-2 text-xs text-xmgray-500">保留摘录和位置不等于主张已核实。在线可读取本人任务原文；离线文件显示已保存摘录，原文入口需要连接当前应用。</p>
    <ol className="space-y-4">{located.map(citation=><li key={citation.citation_id}>
      <p>{citation.citation_id} · {citation.source_title}</p>
      <blockquote className="my-1 whitespace-pre-wrap break-words rounded bg-xmgray-50 p-2 text-xs">{citation.extracted_evidence||'该旧记录未保留展示摘录。'}</blockquote>
      <p className="break-all text-xs">{citation.locator!.evidence_id} · 保留文字字符 {citation.locator!.start}–{citation.locator!.end}</p>
      <div className="mt-1 flex gap-2"><button type="button" className="btn-ghost text-xs" disabled={!sessionId||loading} onClick={()=>void read(citation)}>查看本次原文</button><button type="button" className="btn-ghost text-xs" disabled={!sessionId||loading} onClick={()=>void read(citation,true)}>展开有限上下文</button></div>
      {selected===citation.citation_id&&<div className="mt-2">{loading&&<p role="status">正在读取本任务保留版本…</p>}{error&&<p role="alert" className="text-red-700">{error}</p>}{quote&&<><p className="break-all text-xs">{quote.version_id} · {quote.coverage} · 字符{quote.start}–{quote.end}</p><blockquote className="whitespace-pre-wrap break-words rounded border p-3">{quote.text}</blockquote><details><summary>原资料与片段定位</summary><pre className="whitespace-pre-wrap break-words text-xs">{JSON.stringify(quote.upstream_locator,null,2)}</pre></details></>}</div>}
    </li>)}</ol>
  </details>
}
