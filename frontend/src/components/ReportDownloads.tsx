import { useState } from 'react'

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
body{margin:0;background:#fafafa;color:#252525;font:16px/1.8 system-ui,sans-serif}
main{max-width:1000px;margin:32px auto;padding:36px;background:white;border:1px solid #e5e5e5;border-radius:16px}
h1,h2,h3{line-height:1.4;margin:1.6em 0 .6em}h1{font-size:2em}h2{font-size:1.45em}h3{font-size:1.15em}
a{color:#b44c00;overflow-wrap:anywhere}p,li{overflow-wrap:anywhere}table{border-collapse:collapse;width:100%;margin:1em 0}
th,td{border:1px solid #ddd;text-align:left;padding:8px}th{background:#f6f6f6}details{padding:12px;border:1px solid #ddd;border-radius:10px;margin:12px 0}
summary{cursor:pointer;font-weight:600}pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:14px;background:#f6f6f6;overflow:auto}
blockquote{margin-left:0;padding-left:16px;border-left:3px solid #e87924}section[aria-label="报告口径与冻结配置"]{padding:20px;background:#fff9f4;border:1px solid #e6d7cb;border-radius:12px}
@media(max-width:600px){main{margin:0;padding:18px}table{display:block;overflow:auto}}
@media print{body{background:white}main{border:0;margin:0;padding:0}details{break-inside:avoid}a{color:inherit}[data-print-duplicate="true"]{display:none}}
`

export default function ReportDownloads({ result, reportElement }: { result: ReportArtifact; reportElement: HTMLDivElement | null }) {
  const [error, setError] = useState('')
  const canDownload = result.status === 'completed' && !!result.report && result.delivery_view?.delivery_complete !== false
  function download(format: 'md' | 'json' | 'html' | 'print' | 'main-md' | 'appendix-md' | 'print-main' | 'print-appendix') {
    try {
      setError('')
      if (!canDownload || !result.report) throw new Error('研究完成并取得有效报告后才能下载。')
      let content: string
      const readerReport = result.delivery_view?.report_markdown ?? result.report
      const printing = format === 'print' || format.startsWith('print-')
      if (format === 'main-md') content = result.delivery_view?.main_report_markdown || readerReport
      else if (format === 'appendix-md') {
        content = result.delivery_view?.appendix_markdown || ''
        if (!content) throw new Error('本报告没有单独的技术附录。')
      }
      else if (format === 'md') content = readerReport
      else if (format === 'json') {
        if (!result.export_view) throw new Error('尚未取得服务端生成的导出视图，请重新读取报告。')
        content = JSON.stringify(result.export_view, null, 2)
      }
      else {
        if (!reportElement) throw new Error('报告预览尚未就绪，请稍后重试。')
        // Reuse the actual rendered report. Native details remain usable without
        // React, hydration, CDN scripts or network access in the downloaded file.
        const clone = reportElement.cloneNode(true) as HTMLDivElement
        if (format === 'print-main') clone.querySelectorAll('[data-report-appendix],[data-full-report]').forEach(element=>element.remove())
        if (format === 'print-appendix') {
          const appendix = clone.querySelector('[data-report-appendix]')
          if (!appendix) throw new Error('本报告没有单独的技术附录。')
          const sources = clone.querySelector('section[aria-label="参考资料"]')
          const styles = Array.from(clone.querySelectorAll('style'))
          clone.replaceChildren(...styles, appendix, ...(sources ? [sources] : []))
        }
        clone.querySelectorAll('[data-app-only],button,script,iframe,object,embed').forEach(element => element.remove())
        clone.querySelectorAll('[data-report-page]').forEach(element => element.removeAttribute('hidden'))
        clone.querySelectorAll('[role="button"]').forEach(element => {
          element.removeAttribute('role'); element.removeAttribute('tabindex'); element.removeAttribute('aria-pressed')
        })
        clone.querySelectorAll('details').forEach(element => element.removeAttribute('open'))
        // The full text remains in a native disclosure; avoid duplicating the
        // whole report beneath the visual pages on first offline opening.
        // Keep offline export self-contained. Paper images remain explicit
        // outbound links; generated SVG charts are embedded in the document.
        clone.querySelectorAll('img').forEach(element => {
          if (!element.src.startsWith('data:image/')) {
            const label = document.createElement('p'); label.textContent = `外部图片未打包：${element.alt || element.src}`
            element.replaceWith(label)
          }
        })
        const doc = document.implementation.createHTMLDocument(result.delivery_view?.title || result.query)
        doc.documentElement.lang = 'zh-CN'
        const charset = doc.createElement('meta'); charset.setAttribute('charset', 'utf-8'); doc.head.prepend(charset)
        const viewport = doc.createElement('meta'); viewport.name = 'viewport'; viewport.content = 'width=device-width,initial-scale=1'; doc.head.append(viewport)
        const style = doc.createElement('style'); style.textContent = css; doc.head.append(style)
        const main = doc.createElement('main'); main.append(...Array.from(clone.childNodes)); doc.body.append(main)
        content = '<!doctype html>\n' + doc.documentElement.outerHTML
      }
      if (printing) {
        const frame = document.createElement('iframe')
        frame.title = '报告打印'; frame.setAttribute('sandbox', 'allow-same-origin allow-modals')
        frame.style.cssText = 'position:fixed;width:1px;height:1px;left:-10000px;border:0'
        frame.onload = () => {
          try {
            const target = frame.contentWindow
            if (!target) throw new Error('无法打开打印视图。')
            frame.contentDocument?.querySelectorAll('details').forEach(element=>element.setAttribute('open',''))
            target.addEventListener('afterprint', ()=>frame.remove(), { once: true })
            target.focus(); target.print()
          } catch { frame.remove(); setError('浏览器未允许打印；请下载HTML后在浏览器中打印。') }
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
    } catch (failure) { setError(failure instanceof Error ? failure.message : '报告导出失败，请重试。') }
  }
  return <div className="flex flex-wrap items-center gap-2" aria-label="报告下载">
    {(['md', 'json', 'html', 'print'] as const).map((format, index) => <button type="button" className="btn-ghost text-xs" key={format}
      disabled={!canDownload} onClick={() => download(format)}>
      {['下载 Markdown', '下载研究数据', '下载 HTML', '打印 / 另存 PDF'][index]}
    </button>)}
    {result.delivery_view?.appendix_markdown && <>
      <button type="button" className="btn-ghost text-xs" disabled={!canDownload} onClick={()=>download('main-md')}>下载主文 Markdown</button>
      <button type="button" className="btn-ghost text-xs" disabled={!canDownload} onClick={()=>download('appendix-md')}>下载技术附录 Markdown</button>
      <button type="button" className="btn-ghost text-xs" disabled={!canDownload} onClick={()=>download('print-main')}>打印主文</button>
      <button type="button" className="btn-ghost text-xs" disabled={!canDownload} onClick={()=>download('print-appendix')}>打印技术附录</button>
    </>}
    {error && <p role="alert" className="text-xs text-red-700">{error}</p>}
  </div>
}
