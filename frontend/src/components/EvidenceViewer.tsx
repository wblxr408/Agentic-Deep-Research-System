import { useEffect, useState } from 'react'
import type { RetainedCitation } from './RetainedCitations'
import { Icon, Modal, safeExternalUrl, TraceLoader } from './Interface'

function sourceName(citation:RetainedCitation):string {
  if(citation.source_title&&!/^https?:/.test(citation.source_title))return citation.source_title
  const value=safeExternalUrl(citation.source_url)
  if(value)try {const url=new URL(value),file=decodeURIComponent(url.pathname.split('/').filter(Boolean).pop()||'');return /\.pdf$/i.test(file)?file.replace(/^OSDI\d+_/,''):url.hostname} catch { /* Keep source text. */ }
  return citation.source_title||'研究来源'
}
interface Quote { text:string; start:number; end:number; coverage?:string; upstream_locator?:unknown }
export function EvidenceDialog({citation,sessionId,onClose}:{citation:RetainedCitation|null;sessionId?:string|null;onClose:()=>void}) {
  const [quote,setQuote]=useState<Quote|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false),[expanded,setExpanded]=useState(false)
  useEffect(()=>setExpanded(false),[citation?.citation_id])
  useEffect(()=>{
    setQuote(null);setError('');setLoading(false)
    if(!citation?.locator||!sessionId)return
    const controller=new AbortController();let active=true
    const locator=citation.locator,parameters=new URLSearchParams({start:String(expanded?Math.max(0,locator.start-400):locator.start)})
    if(!expanded)parameters.set('end',String(locator.end))
    setLoading(true)
    void fetch(`/api/v1/research/${encodeURIComponent(sessionId)}/evidence/${encodeURIComponent(locator.evidence_id)}?${parameters}`,{signal:controller.signal})
      .then(async response=>{if(!response.ok)throw new Error(response.status===404?'原文当前不可访问。':'原文读取失败，请重试。');return response.json() as Promise<Quote>})
      .then(value=>{if(active)setQuote(value)}).catch(reason=>{if(active&&!controller.signal.aborted)setError(reason instanceof Error?reason.message:'原文读取失败。')})
      .finally(()=>{if(active)setLoading(false)})
    return()=>{active=false;controller.abort()}
  },[citation,sessionId,expanded])
  const url=safeExternalUrl(citation?.source_url)
  return <Modal open={Boolean(citation)} onClose={onClose} title="来源原文" wide>{citation&&<div className="evidence-dialog">
    <span className="eyebrow">SOURCE {citation.citation_id.replace('citation:','')}</span><h3>{sourceName(citation)}</h3>
    {url&&<a className="evidence-external" href={url} target="_blank" rel="noopener noreferrer">{new URL(url).hostname}<Icon name="external" size={15}/></a>}
    {citation.extracted_evidence&&<blockquote className="source-excerpt">{citation.extracted_evidence}</blockquote>}
    {loading&&<p role="status" className="source-loading"><TraceLoader/>读取原文</p>}{error&&<p role="alert" className="composer-error">{error}</p>}
    {quote&&<section className="retained-quote"><span>保留原文 · 字符 {quote.start}–{quote.end}</span><blockquote>{quote.text}</blockquote></section>}
    {citation.locator&&sessionId&&<button type="button" className="btn-secondary" disabled={loading||expanded} onClick={()=>setExpanded(true)}>{expanded?'已展开上下文':'展开上下文'}</button>}
  </div>}</Modal>
}

export function EvidenceCards({citations,onSelect}:{citations:RetainedCitation[];onSelect:(citation:RetainedCitation)=>void}) {
  const [all,setAll]=useState(false)
  if(!citations.length)return null
  return <section className="evidence-cards" aria-label="引用来源"><div className="evidence-section-heading"><h2>引用与来源</h2><span>{citations.length} 处引用</span></div><div className="evidence-card-grid">
    {(all?citations:citations.slice(0,6)).map((citation,index)=>{const url=safeExternalUrl(citation.source_url);return <button type="button" key={citation.citation_id} className="evidence-card" onClick={()=>onSelect(citation)}>
      <span className="evidence-card-top"><span>{String(index+1).padStart(2,'0')}</span><Icon name="source" size={17}/></span><strong>{sourceName(citation)}</strong>
      {citation.extracted_evidence&&<p>{citation.extracted_evidence}</p>}<span className="evidence-card-domain">{url?new URL(url).hostname:'资料'}<Icon name="arrow" size={15}/></span>
    </button>})}
  </div>{citations.length>6&&<button type="button" className="btn-ghost" onClick={()=>setAll(value=>!value)}>{all?'收起来源':`查看全部 ${citations.length} 项来源`}</button>}</section>
}
