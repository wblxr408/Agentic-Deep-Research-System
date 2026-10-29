import {t,useLocale,uiMessage} from '../i18n'
import { useState } from 'react'
import {safeExternalUrl} from './Interface'

export interface ReportArtifact {
  session_id: string; query: string; status: string; report: string | null
  created_at: string; completed_at: string | null
  citations: unknown
  organization_research?: unknown
  organization_result?: unknown
  classification_versions?: unknown
  delivery_view?: { title?: string; report_markdown?: string; main_report_markdown?: string; appendix_markdown?: string; delivery_complete?: boolean } | null
  report_audit?: unknown
  report_editorial?: unknown
  budget_state?: unknown
  query_understanding?: unknown
  plan_manifest?: unknown
  plan_history?: unknown
  iteration_control?: unknown
  export_view?: unknown
}

const css = `
:root{--neutral-900:37 37 37;--neutral-200:220 220 220;--accent-500:52 125 116;--surface:#fff;--accent-soft:#edf3f2}
body{margin:0;background:#fafafa;color:#252525;font:16px/1.8 system-ui,sans-serif}
main{max-width:1400px;margin:32px auto;padding:36px;background:white;border:1px solid #e5e5e5;border-radius:16px}
h1,h2,h3{line-height:1.4;margin:1.6em 0 .6em}h1{font-size:2em}h2{font-size:1.45em}h3{font-size:1.15em}
a{color:#b44c00;overflow-wrap:anywhere}p,li{overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;margin:1em 0}
th,td{border:1px solid #ddd;text-align:left;padding:8px}th{background:#f6f6f6}details{padding:12px;border:1px solid #ddd;border-radius:10px;margin:12px 0}
summary{cursor:pointer;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:14px;background:#f6f6f6;overflow:auto}
blockquote{margin-left:0;padding-left:16px;border-left:3px solid #e87924}
@media(max-width:600px){main{margin:0;padding:0;border:0}table{max-width:100%}}
@media print{body{background:white}main{border:0;margin:0;padding:0;max-width:none}[data-full-report],[data-print-duplicate="true"]{display:none!important}a{color:inherit}}
`

// This fixed application script operates only on exported report controls.
// No script, handler, HTML, CSS or URL is taken from an imported sample.
const offlineScript = `
(()=>{
  const activate=(root,index)=>{
    const tabs=Array.from(root.querySelectorAll('[data-layout-tab]'));
    if(!tabs.length||index<0||index>=tabs.length)return;
    tabs.forEach((tab,i)=>{tab.setAttribute('aria-selected',String(i===index));tab.tabIndex=i===index?0:-1});
    root.querySelectorAll('[data-layout-panel]').forEach(panel=>{panel.hidden=Number(panel.dataset.layoutPanel)!==index});
  };
  document.querySelectorAll('.layout-report').forEach(root=>{const tab=root.querySelector('[data-layout-tab][aria-selected="true"]');if(tab)activate(root,Number(tab.dataset.layoutTab))});
  document.addEventListener('click',event=>{
    const target=event.target;if(!(target instanceof Element))return;
    const tab=target.closest('[data-layout-tab]'),nav=target.closest('[data-layout-nav]'),sort=target.closest('[data-layout-sort]');
    if(tab){const root=tab.closest('.layout-report');if(root)activate(root,Number(tab.dataset.layoutTab))}
    if(nav){const root=nav.closest('.layout-report');if(root)activate(root,Number(nav.dataset.layoutNav));const panel=document.getElementById(nav.getAttribute('href').slice(1));if(panel&&panel.tagName==='DETAILS')panel.open=true}
    if(sort){
      const box=sort.closest('[data-layout-table]'),table=box&&box.querySelector('table'),body=table&&table.tBodies[0];
      if(!body)return;
      const column=Number(sort.dataset.layoutSort),head=sort.closest('th'),previous=head&&head.getAttribute('aria-sort'),direction=previous==='ascending'?-1:1;
      table.querySelectorAll('th[aria-sort]').forEach(item=>item.removeAttribute('aria-sort'));
      if(head)head.setAttribute('aria-sort',direction===1?'ascending':'descending');
      Array.from(body.rows).map((row,index)=>({row,index})).sort((a,b)=>{
        const left=a.row.cells[column]?.textContent||'',right=b.row.cells[column]?.textContent||'';
        return left.localeCompare(right,undefined,{numeric:true,sensitivity:'base'})*direction||a.index-b.index;
      }).forEach(item=>body.append(item.row));
    }
    const link=target.closest('a[href^="#report-source-"]');
    if(link){const destination=document.getElementById(link.getAttribute('href').slice(1));const panel=destination&&destination.closest('[data-layout-panel]'),root=panel&&panel.closest('.layout-report');if(root&&panel)activate(root,Number(panel.dataset.layoutPanel));for(let item=destination;item;item=item.parentElement)if(item.tagName==='DETAILS')item.open=true}
  });
  document.addEventListener('input',event=>{
    const field=event.target;if(!(field instanceof HTMLInputElement)||!field.matches('[data-layout-filter]'))return;
    const box=field.closest('[data-layout-table]'),term=field.value.trim().toLocaleLowerCase();
    if(box)box.querySelectorAll('tbody tr').forEach(row=>{row.hidden=!!term&&!(row.dataset.layoutSearch||row.textContent).toLocaleLowerCase().includes(term)});
  });
  document.addEventListener('keydown',event=>{
    const tab=event.target;if(!(tab instanceof HTMLButtonElement)||!tab.matches('[data-layout-tab]')||!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;
    const root=tab.closest('.layout-report'),tabs=root&&Array.from(root.querySelectorAll('[data-layout-tab]'));if(!root||!tabs||!tabs.length)return;
    const i=tabs.indexOf(tab),next=event.key==='Home'?0:event.key==='End'?tabs.length-1:(i+(event.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;
    event.preventDefault();activate(root,next);tabs[next].focus();
  });
  let details=[],hidden=[];
  window.addEventListener('beforeprint',()=>{
    details=Array.from(document.querySelectorAll('details')).map(item=>[item,item.open]);
    hidden=Array.from(document.querySelectorAll('[data-layout-panel],tbody tr')).map(item=>[item,item.hidden]);
    details.forEach(([item])=>{item.open=true});hidden.forEach(([item])=>{item.hidden=false});
  });
  window.addEventListener('afterprint',()=>{
    details.forEach(([item,open])=>{item.open=open});hidden.forEach(([item,wasHidden])=>{item.hidden=wasHidden});details=[];hidden=[];
  });
})();
`

export default function ReportDownloads({ result, reportElement }: { result: ReportArtifact; reportElement: HTMLDivElement | null }) {
  useLocale()

  const [error, setError] = useState('')
  const [packaging,setPackaging]=useState(false)
  const canDownload = result.status === 'completed' && !!result.report && result.delivery_view?.delivery_complete !== false
  async function downloadPackage() {
    if(packaging||!canDownload)return
    setPackaging(true);setError('')
    try {
      const response=await fetch(`/api/v1/research/${encodeURIComponent(result.session_id)}/source-package`)
      if(!response.ok)throw new Error(t('资料包暂时无法下载，请重新读取报告后重试。'))
      const blob=await response.blob(),url=URL.createObjectURL(blob)
      const link=document.createElement('a');link.href=url;link.download=`research-${result.session_id}-sources.zip`
      document.body.append(link);link.click();link.remove();window.setTimeout(()=>URL.revokeObjectURL(url),1000)
    }catch(failure){setError(failure instanceof Error?uiMessage(failure.message):t('资料包暂时无法下载，请重新读取报告后重试。'))}
    finally{setPackaging(false)}
  }
  function download(format: 'md' | 'json' | 'html' | 'print' | 'main-md' | 'appendix-md' | 'print-main' | 'print-appendix') {
    try {
      setError('')
      if (!canDownload || !result.report) throw new Error(t("研究完成并取得有效报告后才能下载。"))
      let content: string
      const readerReport = result.delivery_view?.report_markdown ?? result.report
      const printing = format === 'print' || format.startsWith('print-')
      if (format === 'main-md') content = result.delivery_view?.main_report_markdown || readerReport
      else if (format === 'appendix-md') {
        content = result.delivery_view?.appendix_markdown || ''
        if (!content) throw new Error(t("本报告没有单独的技术附录。"))
      }
      else if (format === 'md') content = readerReport
      else if (format === 'json') {
        if (!result.export_view) throw new Error(t("尚未取得服务端生成的导出视图，请重新读取报告。"))
        content = JSON.stringify(result.export_view, null, 2)
      }
      else {
        if (!reportElement) throw new Error(t("报告预览尚未就绪，请稍后重试。"))
        // Export the already-rendered current report; the standalone controls
        // are backed by the fixed application script above, never sample code.
        const clone = reportElement.cloneNode(true) as HTMLDivElement
        if (format === 'print-main') clone.querySelectorAll('[data-report-appendix],[data-full-report]').forEach(element=>element.remove())
        if (format === 'print-appendix') {
          const appendix = clone.querySelector('[data-report-appendix]')
          if (!appendix) throw new Error(t("本报告没有单独的技术附录。"))
          const sources = clone.querySelector('[data-report-references]')
          const styles = Array.from(clone.querySelectorAll('style'))
          clone.replaceChildren(...styles, appendix, ...(sources ? [sources] : []))
        }
        // The online evidence buttons become links to the same retained
        // citations in the offline document before other React controls leave.
        const citationRows=Array.isArray(result.citations)?result.citations:[]
        const missing=citationRows.filter((citation:unknown)=>{
          if(!citation||typeof citation!=='object'||!('citation_id' in citation))return false
          const id=String(citation.citation_id).replace(/[^a-zA-Z0-9-]/g,'-')
          return !clone.querySelector(`[id="report-source-${id}"]`)
        }) as Array<{citation_id:string;source_title?:string;source_url?:string;extracted_evidence?:string}>
        if(missing.length){
          const references=document.createElement('details'),heading=document.createElement('summary'),list=document.createElement('ol')
          references.setAttribute('data-report-references','');heading.textContent=t('参考资料');references.append(heading,list)
          missing.forEach(citation=>{const item=document.createElement('li');item.id='report-source-'+citation.citation_id.replace(/[^a-zA-Z0-9-]/g,'-');item.textContent=`[${citation.citation_id.replace('citation:','')}] ${citation.source_title||''}`
            const url=safeExternalUrl(citation.source_url);if(url){const link=document.createElement('a');link.href=url;link.textContent=' · '+t('查看来源');link.target='_blank';link.rel='noopener noreferrer';item.append(link)}
            if(citation.extracted_evidence){const quote=document.createElement('p');quote.textContent=citation.extracted_evidence;item.append(quote)}list.append(item)})
          clone.append(references)
        }
        clone.querySelectorAll<HTMLElement>('.citation-button[data-citation-id]').forEach(element=>{
          const id=element.dataset.citationId||'',link=document.createElement('a')
          link.href='#report-source-'+id.replace(/[^a-zA-Z0-9-]/g,'-');link.textContent=element.textContent;link.className='citation-button';element.replaceWith(link)
        })
        clone.querySelectorAll('[data-app-only],button:not([data-report-offline]),script,iframe,object,embed,.evidence-cards').forEach(element => element.remove())
        clone.querySelectorAll('[data-report-page],tbody tr').forEach(element => element.removeAttribute('hidden'))
        clone.querySelectorAll<HTMLInputElement>('[data-layout-filter]').forEach(element=>{element.value='';element.removeAttribute('value')})
        clone.querySelectorAll('[data-chart-edge]').forEach(element=>element.setAttribute('stroke','var(--accent)'))
        clone.querySelectorAll('[data-chart-radius]').forEach(element=>element.setAttribute('r',element.getAttribute('data-chart-radius')||'4'))
        clone.querySelectorAll('[data-chart-bar]').forEach(element=>{element.setAttribute('opacity','1');element.removeAttribute('stroke')})
        clone.querySelectorAll('[data-chart-selection]').forEach(element=>element.remove())
        clone.querySelectorAll('[role="button"]').forEach(element => {
          element.removeAttribute('role'); element.removeAttribute('tabindex'); element.removeAttribute('aria-pressed')
        })
        clone.querySelectorAll('details').forEach(element => element.classList.contains('layout-section')||element.hasAttribute('data-chart-table')?element.setAttribute('open',''):element.removeAttribute('open'))
        // The full text remains in a native disclosure; avoid duplicating the
        // whole report beneath the visual pages on first offline opening.
        // Original PDF page pixels and generated charts are embedded. Online
        // authenticated file controls leave with data-app-only above.
        clone.querySelectorAll<HTMLElement>('.source-page-offline').forEach(element=>{element.style.display='block'})
        clone.querySelectorAll('img').forEach(element => {
          if (!element.src.startsWith('data:image/')) {
            const label = document.createElement('p'); label.textContent = t("外部图片未打包：{0}", element.alt || element.src)
            element.replaceWith(label)
          }
        })
        const doc = document.implementation.createHTMLDocument(result.delivery_view?.title || result.query)
        doc.documentElement.lang = document.documentElement.lang || 'zh-CN'
        const charset = doc.createElement('meta'); charset.setAttribute('charset', 'utf-8'); doc.head.prepend(charset)
        const viewport = doc.createElement('meta'); viewport.name = 'viewport'; viewport.content = 'width=device-width,initial-scale=1'; doc.head.append(viewport)
        const csp=doc.createElement('meta');csp.httpEquiv='Content-Security-Policy';csp.content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'";doc.head.append(csp)
        const style = doc.createElement('style'); style.textContent = css; doc.head.append(style)
        const main = doc.createElement('main'); main.append(...Array.from(clone.childNodes)); doc.body.append(main)
        const script=doc.createElement('script');script.textContent=offlineScript;doc.body.append(script)
        content = '<!doctype html>\n' + doc.documentElement.outerHTML
      }
      if (printing) {
        const frame = document.createElement('iframe')
        frame.title = t("报告打印"); frame.setAttribute('sandbox', 'allow-same-origin allow-modals')
        frame.style.cssText = 'position:fixed;width:1px;height:1px;left:-10000px;border:0'
        frame.onload = () => {
          try {
            const target = frame.contentWindow
            if (!target) throw new Error(t("无法打开打印视图。"))
            frame.contentDocument?.querySelectorAll('details').forEach(element=>element.setAttribute('open',''))
            target.addEventListener('afterprint', ()=>frame.remove(), { once: true })
            target.focus(); target.print()
          } catch { frame.remove(); setError(t("浏览器未允许打印；请下载HTML后在浏览器中打印。")) }
        }
        frame.srcdoc = content; document.body.append(frame)
        return
      }
      const mime = format === 'html' ? 'text/html' : format === 'json' ? 'application/json' : 'text/markdown'
      const objectUrl = URL.createObjectURL(new Blob([content], { type: mime + ';charset=utf-8' }))
      const extension = format.endsWith('-md') ? 'md' : format
      const suffix = format.endsWith('-md') ? '-' + format.replace('-md','') : ''
      const anchor = document.createElement('a'); anchor.href = objectUrl; anchor.download = `research-${result.session_id}${suffix}.${extension}`
      document.body.append(anchor); anchor.click(); anchor.remove()
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
    } catch (failure) { setError(failure instanceof Error ? uiMessage(failure.message) : t("报告导出失败，请重试。")) }
  }
  return <div className="flex flex-wrap items-center gap-2" aria-label={t("报告下载")}>
    <button type="button" className="btn-ghost text-xs" disabled={!canDownload||packaging} onClick={()=>void downloadPackage()}>{packaging?t('正在打包…'):t('下载资料包')}</button>
    {(['md', 'json', 'html', 'print'] as const).map((format, index) => <button type="button" className="btn-ghost text-xs" key={format}
      disabled={!canDownload} onClick={() => download(format)}>
      {[t("下载 Markdown"), t("下载研究数据"), t("下载 HTML"), t("打印 / 另存 PDF")][index]}
    </button>)}
    {result.delivery_view?.appendix_markdown && <>
      <button type="button" className="btn-ghost text-xs" disabled={!canDownload} onClick={()=>download('main-md')}>{t("下载主文 Markdown")}</button>
      <button type="button" className="btn-ghost text-xs" disabled={!canDownload} onClick={()=>download('appendix-md')}>{t("下载技术附录 Markdown")}</button>
      <button type="button" className="btn-ghost text-xs" disabled={!canDownload} onClick={()=>download('print-main')}>{t("打印主文")}</button>
      <button type="button" className="btn-ghost text-xs" disabled={!canDownload} onClick={()=>download('print-appendix')}>{t("打印技术附录")}</button>
    </>}
    {error && <p role="alert" className="text-xs text-red-700">{uiMessage(error)}</p>}
  </div>
}
