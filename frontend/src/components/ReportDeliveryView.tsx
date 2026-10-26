import {useLocale,t,uiMessage} from '../i18n'
import { useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Icon, Modal } from './Interface'

interface Point { label: string; value: number | null; metric_id?: string | null }
interface RelationEdge {
  source: string; target: string; label: string; kind?: string; status?: string
  proofs?: Array<{ evidence_id: string; source_url: string; start?: number; end?: number; quote?: string }>
}
export interface DeliveryChart {
  rendered_assets?: Array<{kind:string;presentation:string;drawing_skill_id?:string;svg:string;png:string;pdf?:string;notes:string[];
    rendered_subset?:Record<string,number>;dpi:number;size_inches:{width:number;height:number}}
  >
  chart_id: string; title: string; kind: string; module?: string; unit_label: string
  snapshot_id?: string | null; points?: Point[]; total_points?: number; total_edges?: number; truncated?: boolean
  nodes?: Array<{ id: string; label: string }>; edges?: RelationEdge[]; note: string
  citation_ids?: string[]
  columns?: string[]; rows?: Array<{ values: string[]; citation_ids: string[] }>
}
export interface DeliveryView {
  schema_version: string; artifact_id: string; title: string; template: string; theme: string
  report_markdown?: string
  delivery_complete?: boolean
  main_report_markdown?: string; appendix_markdown?: string
  citations?: Array<{ citation_id: string; source_title?: string; source_url: string }>
  configuration_origin: string; pages: Array<{
    page_id: string; title: string; question: string; module: string | null; markdown: string
    content_match: string; citation_ids: string[]; charts: Array<{ chart_id: string; kind: string; drawing_skill_id?:string }>; gaps: string[]
  }>
  charts: DeliveryChart[]; drawing: { requested_mode: string; requested_skill_ids: string[]; status: string; reason?: string | null }
  formats: Array<{ format: string; status: string; alternative?: string | null }>
  audit?: { total_claims?: number; supported_claims?: number; checked_claims?: number; needs_review?: boolean
    claims?: Array<{ claim_id: string; text: string; status: string; reason: string; citation_ids?: string[] }> } | null
  gaps: string[]; statistics?: unknown; sources?: unknown
  module_results: Record<string, unknown>
}

const styles = `
.adrs-delivery{--paper:var(--surface);--ink:rgb(var(--neutral-900));--soft:var(--accent-soft);--line:rgb(var(--neutral-200));--accent:rgb(var(--accent-500));color:var(--ink);background:var(--paper);padding:0;font:16px/1.9 'Segoe UI','Microsoft YaHei',sans-serif}


.adrs-delivery h2{font-size:24px;line-height:1.4;margin:0 0 12px}.adrs-delivery h3{font-size:18px;margin:16px 0 10px}
.adrs-delivery nav{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.adrs-delivery a{color:var(--accent)}
.adrs-delivery nav a,.adrs-delivery button{border:1px solid var(--line);border-radius:8px;padding:5px 10px;color:var(--ink);background:var(--paper);cursor:pointer}
.adrs-delivery nav [aria-current="page"]{background:var(--soft);border-color:var(--accent)}
.adrs-delivery article{scroll-margin-top:24px;border-top:1px solid var(--line);padding-top:20px}
.adrs-delivery figure,.adrs-delivery details{padding:12px;border:1px solid var(--line);border-radius:10px;margin:14px 0}
.adrs-delivery figcaption{font-weight:600}.adrs-delivery p{margin:8px 0}.adrs-delivery summary{cursor:pointer;font-weight:600}
.adrs-delivery table{border-collapse:collapse;width:100%;font-size:12px}.adrs-delivery th,.adrs-delivery td{padding:7px;border:1px solid var(--line);text-align:left;overflow-wrap:anywhere}
.adrs-delivery pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;max-height:480px;overflow:auto}
.adrs-delivery .gap{padding:8px 12px;background:var(--soft);border-left:3px solid var(--accent)}
.adrs-delivery .chart-frame{overflow:auto}.adrs-delivery .chart-frame>svg{width:100%;min-width:460px;display:block}.adrs-delivery .chart-frame>svg text{fill:var(--ink);font:12px system-ui,sans-serif}
.adrs-delivery:fullscreen{overflow:auto;border-radius:0;padding:32px}.adrs-delivery [hidden]{display:none}
@media(max-width:600px){.adrs-delivery{padding:12px}.adrs-delivery h2{font-size:20px}}
@media print{.adrs-delivery{--paper:#fff!important;--ink:#111!important;--soft:#eee!important;--line:#aaa!important;--accent:#333!important}
.adrs-delivery [data-app-only]{display:none!important}.adrs-delivery [data-report-page]{display:block!important;break-before:page}
.adrs-delivery pre{max-height:none;overflow:visible}.adrs-delivery figure{break-inside:avoid}}
`

function Chart({ chart, kind,skillId,expanded=false }: { chart: DeliveryChart; kind: string;skillId?:string;expanded?:boolean }) {
  useLocale()

  const [selected, setSelected] = useState('')
  const [enlarged,setEnlarged]=useState(false)
  const points = chart.points || [], nodes = chart.nodes || [], edges = chart.edges || []
  const width = 760, plotLeft = 190, plotRight = 725
  const max = Math.max(1, ...points.map(point => point.value || 0))
  const positions = new Map(nodes.map((node, index) => [node.id, {
    x: 380 + 255 * Math.cos(index * Math.PI * 2 / Math.max(1, nodes.length)),
    y: 225 + 160 * Math.sin(index * Math.PI * 2 / Math.max(1, nodes.length)),
  }]))
  const choose = (value: string) => setSelected(current => current === value ? '' : value)
  const selectedPoint = points.find(point => point.label === selected)
  const asset=chart.rendered_assets?.find(item=>item.presentation===kind&&item.drawing_skill_id===skillId)
  function downloadData() {
    const rows:unknown[][]=chart.rows
      ? [[...(chart.columns||[]),t("来源")],...chart.rows.map(row=>[...row.values,row.citation_ids.join(' ')])]
      : points.length ? [[t("条目"),chart.unit_label],...points.map(point=>[point.label,point.value])]
      : [[t("起点"),t("终点"),t("关系"),t("来源")],...edges.map(edge=>[nodes.find(node=>node.id===edge.source)?.label||edge.source,nodes.find(node=>node.id===edge.target)?.label||edge.target,edge.label,(edge.proofs||[]).map(proof=>proof.source_url).join(' ')])]
    const cell=(value:unknown)=>{let text=value===null||value===undefined?'':String(value);if(typeof value==='string'&&/^[=+@\-\t\r]/.test(text))text="'"+text;return '"'+text.replace(/"/g,'""')+'"'}
    const url=URL.createObjectURL(new Blob(['\ufeff'+rows.map(row=>row.map(cell).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'}))
    const anchor=document.createElement('a');anchor.href=url;anchor.download=chart.chart_id+'.csv';anchor.click();window.setTimeout(()=>URL.revokeObjectURL(url),1000)
  }
  return <figure className="report-chart">
    <figcaption>{chart.title}{chart.unit_label&&<> · {chart.unit_label}</>}</figcaption>
    {!expanded&&<div data-app-only className="chart-actions"><button type="button" onClick={()=>setEnlarged(true)}><Icon name="fit" size={16}/>{t("放大")}</button><button type="button" onClick={downloadData}><Icon name="download" size={16}/>{t("数据 CSV")}</button></div>}
    {chart.note&&<details className="chart-method"><summary>{t("统计口径")}</summary><p>{chart.note}</p></details>}
    {!expanded&&<Modal open={enlarged} onClose={()=>setEnlarged(false)} title={chart.title} wide><Chart chart={chart} kind={kind} skillId={skillId} expanded/></Modal>}
    {asset && <>
      <img src={asset.svg} alt={chart.title} style={{width:'100%',height:'auto'}} />
      {!!asset.notes?.length&&<details data-app-only><summary>{t("绘图记录")}</summary>{asset.notes.map((note,index)=><p key={index}>{note}</p>)}</details>}
      <div data-app-only className="flex gap-3 text-sm">
        <a href={asset.svg} download={`${chart.chart_id}-${kind}.svg`}>{t("下载SVG")}</a>
        <a href={asset.png} download={`${chart.chart_id}-${kind}.png`}>{t("下载PNG")}</a>
        {asset.pdf && <a href={asset.pdf} download={`${chart.chart_id}-${kind}.pdf`}>{t("下载图表PDF")}</a>}
      </div>
    </>}
    {chart.rows && <div className="chart-frame"><table>
      <thead><tr>{chart.columns?.map(column=><th key={column}>{column}</th>)}<th>{t("来源")}</th></tr></thead>
      <tbody>{chart.rows.map((row,index)=><tr key={index}>{row.values.map((value,column)=><td key={column}>{value}</td>)}
        <td>{row.citation_ids.map(id=>`[${id.replace('citation:','')}]`).join(' ')}</td></tr>)}</tbody>
    </table></div>}
    {chart.truncated && <p>{t("图中展示前")}{points.length || edges.length}{t("项，共")}{chart.total_points || chart.total_edges}{t("项。")}</p>}
    {!asset && kind !== 'table' && !chart.rows && <div className="chart-frame">
      {kind === 'network' ? <svg viewBox="0 0 760 450" role="img" aria-label={chart.title}>
        {edges.map((edge, index) => {
          const from = positions.get(edge.source), to = positions.get(edge.target)
          return from && to ? <line key={index} x1={from.x} y1={from.y} x2={to.x} y2={to.y}
            stroke={selected && ![edge.source, edge.target].includes(selected) ? '#a0a0a0' : 'var(--accent)'} strokeWidth="1.5" opacity=".7"><title>{edge.label} · {edge.status}</title></line> : null
        })}
        {nodes.map(node => {
          const position = positions.get(node.id)!
          return <g key={node.id} role="button" tabIndex={0} aria-label={node.label} aria-pressed={selected === node.id}
            onClick={() => choose(node.id)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(node.id) } }}>
            <circle cx={position.x} cy={position.y} r={selected === node.id ? 9 : 6} fill="var(--accent)" />
            <text x={position.x + 10} y={position.y + 4}>{node.label.slice(0, 18)}{node.label.length > 18 ? '…' : ''}</text><title>{node.label}</title>
          </g>
        })}
      </svg> : kind === 'line' || kind === 'timeline' ? <svg viewBox="0 0 760 350" role="img" aria-label={chart.title}>
        <line x1="60" x2="730" y1="280" y2="280" stroke="#999" />
        {[0, .5, 1].map(ratio => <g key={ratio}><line x1="60" x2="730" y1={280-ratio*220} y2={280-ratio*220} stroke="#bbb" opacity=".4" /><text x="5" y={284-ratio*220}>{(max*ratio).toLocaleString()}</text></g>)}
        {points.map((point, index) => {
          const x = 60 + index * 670 / Math.max(1, points.length-1), y = 280 - (point.value || 0) / max * 220
          const previous = points[index-1], previousX = 60 + (index-1)*670/Math.max(1,points.length-1)
          return <g key={`${point.label}-${index}`}>
            {point.value !== null && previous && previous.value !== null && <line x1={previousX} y1={280-previous.value/max*220} x2={x} y2={y} stroke="var(--accent)" strokeWidth="2" />}
            {point.value !== null ? <circle cx={x} cy={y} r={selected === point.label ? 6 : 4} fill="var(--accent)" role="button" tabIndex={0} aria-label={`${point.label}: ${point.value}`}
              onClick={() => choose(point.label)} onKeyDown={event => { if (event.key === 'Enter') choose(point.label) }}><title>{point.label}: {point.value}</title></circle>
              : <text x={x} y="266" textAnchor="middle">?</text>}
            {(index % Math.max(1, Math.ceil(points.length/10)) === 0 || index === points.length-1) && <text x={x} y="310" textAnchor="middle">{point.label}</text>}
          </g>
        })}
      </svg> : <svg viewBox={`0 0 ${width} ${Math.max(90,Math.min(points.length,30)*30+35)}`} role="img" aria-label={chart.title}>
        <line x1={plotLeft} x2={plotLeft} y1="5" y2={Math.min(points.length,30)*30+10} stroke="#999" />
        {points.slice(0,30).map((point, index) => <g key={`${point.label}-${index}`} role="button" tabIndex={0}
          aria-label={`${point.label}: ${point.value === null ? t("未覆盖") : point.value}`} onClick={() => choose(point.label)}
          onKeyDown={event => { if (event.key === 'Enter') choose(point.label) }}>
          <text x={plotLeft-8} y={index*30+23} textAnchor="end">{point.label.slice(0,23)}{point.label.length>23?'…':''}</text>
          <rect x={plotLeft} y={index*30+8} width={(point.value || 0)/max*(plotRight-plotLeft-50)} height="20" fill={selected===point.label?'rgb(var(--accent-700))':'var(--accent)'} />
          <text x={plotLeft+(point.value||0)/max*(plotRight-plotLeft-50)+6} y={index*30+23}>{point.value === null ? t("未覆盖") : point.value}</text>
          <title>{point.label}: {point.value === null ? t("未覆盖") : point.value}</title>
        </g>)}
      </svg>}
    </div>}
    {points.length > 30 && kind === 'bar' && <p>{t("条形图展示前30项，数据表保留本视图全部条目。")}</p>}
    {selected && <p role="status">{nodes.find(node => node.id === selected)?.label || selected}
      {selectedPoint && `：${selectedPoint.value === null ? t("未覆盖") : selectedPoint.value}`}</p>}
    {!chart.rows && <details open={kind === 'table'}><summary>{t("查看图表数据")}</summary>
      {points.length > 0 && <div style={{overflowX:'auto'}}><table><thead><tr><th>{t("条目")}</th><th>{chart.unit_label}</th></tr></thead><tbody>
        {points.map((point,index) => <tr key={index}><td>{point.label}</td><td>{point.value === null ? t("未覆盖") : point.value}</td></tr>)}
      </tbody></table></div>}
      {edges.length > 0 && <table><thead><tr><th>{t("关系观察")}</th><th>{t("参与方")}</th><th>{t("状态与依据")}</th></tr></thead><tbody>{edges.map((edge,index)=><tr key={index}>
        <td>{edge.label}<br />{edge.kind}</td><td>{nodes.find(node=>node.id===edge.source)?.label} → {nodes.find(node=>node.id===edge.target)?.label}</td>
        <td>{edge.proofs?.map((proof, i)=><p key={i}>{proof.quote}<br /><SafeSource url={proof.source_url} /></p>)}</td>
      </tr>)}</tbody></table>}
    </details>}
  </figure>
}

function SafeSource({url}:{url:string}) {
  useLocale()

  try { const link = new URL(url); if (['http:','https:'].includes(link.protocol)) return <a href={link.href} target="_blank" rel="noopener noreferrer">{t("查看来源")}</a> } catch { /* retained label only */ }
  return <span>{url}</span>
}

export default function ReportDeliveryView({view,renderMarkdown}:{view:DeliveryView;renderMarkdown:(text:string)=>ReactNode}) {
  useLocale()

  const [current,setCurrent]=useState(0), [all,setAll]=useState(false), [error,setError]=useState('')
  const root=useRef<HTMLDivElement>(null)
  const idPrefix=`delivery-${view.artifact_id.slice(0,12)}`
  const chartById=new Map(view.charts.map(chart=>[chart.chart_id,chart]))
  async function fullscreen() {
    try { if (document.fullscreenElement) await document.exitFullscreen(); else await root.current?.requestFullscreen(); setError('') }
    catch { setError(t("当前浏览器未允许全屏；可使用全部页面阅读或下载HTML。")) }
  }
  return <div ref={root} className="adrs-delivery" data-theme={view.theme} aria-label={t("图文研究报告")}>
    <style>{styles}</style>
    <h2>{view.title}</h2>
    <div data-app-only className="flex flex-wrap gap-2"><button type="button" onClick={()=>setAll(value=>!value)}>{all?t("逐页阅读"):t("显示全部页面")}</button><button type="button" onClick={()=>void fullscreen()}>{t("全屏 / 退出")}</button></div>
    {error&&<p role="alert">{uiMessage(error)}</p>}
    <nav aria-label={t("报告目录")}>{view.pages.map((page,index)=><a key={page.page_id} href={`#${idPrefix}-${page.page_id}`} aria-current={current===index?'page':undefined}
      onClick={()=>setCurrent(index)}>{index+1}. {page.title}</a>)}</nav>
    {view.pages.map((page,index)=><article key={page.page_id} id={`${idPrefix}-${page.page_id}`} data-report-page hidden={!all&&current!==index}>
      <p className="text-xs">{index+1} / {view.pages.length}</p><h2>{page.title}</h2>
      {page.question&&<p><strong>{t("本页问题：")}</strong>{page.question}</p>}
      {page.markdown&&<div>{renderMarkdown(page.markdown)}</div>}
      {['ready','rendered'].includes(view.drawing.status)&&page.charts.map(reference=>{
        const chart=chartById.get(reference.chart_id)
        return chart?<Chart key={`${reference.chart_id}-${reference.kind}-${reference.drawing_skill_id||'default'}`}
          chart={chart} kind={reference.kind} skillId={reference.drawing_skill_id}/>:null
      })}
    </article>)}
    {!all&&view.pages.length>1&&<div data-app-only className="mt-4 flex items-center gap-3"><button type="button" disabled={current===0} onClick={()=>setCurrent(value=>Math.max(0,value-1))}>{t("上一页")}</button>
      <span>{current+1} / {view.pages.length}</span><button type="button" disabled={current>=view.pages.length-1} onClick={()=>setCurrent(value=>Math.min(view.pages.length-1,value+1))}>{t("下一页")}</button></div>}
    {view.appendix_markdown && <details data-report-appendix><summary>{t("技术附录：方法、实验与资源")}</summary>
      {renderMarkdown(view.appendix_markdown)}
    </details>}
    {!!view.citations?.length && <details aria-label={t("参考资料")}><summary>{t("参考资料")}</summary>
      {view.citations.map(citation=><p key={citation.citation_id}>[{citation.citation_id.replace('citation:','')}] {citation.source_title}<br /><SafeSource url={citation.source_url}/></p>)}
    </details>}
  </div>
}
