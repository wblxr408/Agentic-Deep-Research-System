import {createElement, useEffect, useRef, useState} from 'react'
import type {CSSProperties, KeyboardEvent, ReactNode} from 'react'
import {t, useLocale} from '../i18n'
import {safeExternalUrl} from './Interface'
import {Chart, deliveryStyles} from './ReportDeliveryView'
import type {DeliveryChart, DeliveryView} from './ReportDeliveryView'
import {layoutRole} from './reportLayouts'
import type {ReportLayout} from './reportLayouts'

interface Citation {citation_id:string;source_title?:string;source_url:string;extracted_evidence?:string}
interface Metric {label:string;display:string;unit?:string}
interface Edge {source:string;target:string;label:string;citation_ids?:string[]}
interface Comparison {values:string[];citation_ids?:string[]}
interface BlockData {
  kind:string; markdown?:string; text?:string; metric?:Metric
  reference?:{chart_id:string;kind:string;drawing_skill_id?:string}
  items?:Array<Citation|Metric|Edge|Comparison>;nodes?:Array<{id:string;label:string}>;columns?:string[]
}
interface BoundBlock {block_id:string;kind:string;level:number|null;span:number;aspect:string;status:string;data?:BlockData|null}
interface BoundSection {section_id:string;title:string;title_origin?:string;role:string;blocks:BoundBlock[]}
export interface LayoutBinding {
  schema_version:'adrs-report-layout-binding-v1';layout:ReportLayout;sections:BoundSection[]
  unplaced_sections:Array<{title:string;markdown:string}>
  missing?:Array<{section_index:number;block_index:number;status:string}>
}
type TableRow={cells:string[];citations?:string[]}
type Section = {id:string;title:string;blocks?:BoundBlock[];markdown?:string}

/* The CSS is application-owned so the same presentation can be embedded in an
   offline report without importing the sample's CSS or any external resource. */
const layoutStyles = `
.layout-report{--layout-line:rgba(120,120,120,.35);--layout-soft:rgba(120,120,120,.08);color:var(--ink);background:var(--paper);font-family:var(--layout-font);font-size:var(--layout-body);line-height:1.85;padding:clamp(20px,4vw,60px);border:1px solid var(--layout-line);border-radius:16px;overflow-wrap:anywhere}
@supports (color:color-mix(in srgb,black,white)){.layout-report{--layout-line:color-mix(in srgb,var(--ink) 20%,var(--paper));--layout-soft:color-mix(in srgb,var(--accent) 9%,var(--paper))}}
.layout-report *{box-sizing:border-box}.layout-report :focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.layout-report .layout-paper{max-width:var(--layout-width);margin:0 auto}.layout-report .layout-running-header,.layout-report .layout-running-footer{color:var(--ink);opacity:.65;font-size:.76em;letter-spacing:.08em;padding:12px 0;border-bottom:1px solid var(--layout-line)}
.layout-report .layout-running-footer{border:0;border-top:1px solid var(--layout-line);margin-top:var(--layout-gap)}
.layout-report .layout-cover{padding:clamp(32px,5vw,80px) 0;border-bottom:1px solid var(--layout-line)}.layout-report .layout-cover h1{margin:0;max-width:20ch;font-family:var(--layout-font);font-size:clamp(24px,6vw,var(--layout-title));line-height:1.16;letter-spacing:-.025em;color:var(--ink)}
.layout-report .layout-contents,.layout-report .layout-tabs{display:flex;flex-wrap:wrap;gap:10px 18px;margin:24px 0}.layout-report .layout-contents a{border:0;padding:0;color:var(--ink);font-size:.84em;text-decoration:none}.layout-report .layout-contents a:hover{text-decoration:underline;text-decoration-color:var(--accent)}
.layout-report .layout-tabs{border-bottom:1px solid var(--layout-line)}.layout-report .layout-tabs button{border:0;border-bottom:2px solid transparent;border-radius:0;padding:10px 4px;background:transparent;color:var(--ink);font:inherit;cursor:pointer}.layout-report .layout-tabs button[aria-selected=true]{border-color:var(--accent);font-weight:650}
.layout-report .layout-section{padding:var(--layout-gap) 0;border-top:1px solid var(--layout-line);scroll-margin-top:24px}.layout-report .layout-section[hidden]{display:none}
.layout-report .layout-section-heading{display:flex;align-items:baseline;gap:18px;margin:0 0 calc(var(--layout-gap) * .8);font-size:clamp(24px,2.5vw,34px);line-height:1.35;font-weight:600}.layout-report .layout-section-heading span{font:500 .45em var(--layout-font);color:var(--accent);letter-spacing:.08em}
.layout-report details.layout-section{border-radius:0;border-left:0;border-right:0;border-bottom:0;margin:0}.layout-report details.layout-section>summary{cursor:pointer;list-style:none}.layout-report details.layout-section>summary::-webkit-details-marker{display:none}.layout-report details.layout-section>summary::after{content:'+';float:right;color:var(--accent);font-size:22px}.layout-report details.layout-section[open]>summary::after{content:'−'}
.layout-report .layout-grid{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:var(--layout-gap);align-items:start}.layout-report .layout-block{min-width:0}.layout-report .layout-block p,.layout-report .layout-block li{font-size:var(--layout-body);line-height:1.9}.layout-report .layout-block p{margin:0 0 1em}.layout-report .layout-block h3,.layout-report .layout-block h4{margin:0 0 .7em;line-height:1.35}.layout-report .layout-block--callout{padding:20px 24px;background:var(--layout-soft);border-left:3px solid var(--accent)}
.layout-report .layout-metric{border-top:3px solid var(--accent);padding:18px 0}.layout-report .layout-metric strong{display:block;font-size:clamp(30px,4vw,54px);line-height:1.1;letter-spacing:-.04em}.layout-report .layout-metric span{display:block;margin-top:10px;font-size:.85em;opacity:.78}
.layout-report figure.report-chart{margin:0;padding:20px;border:1px solid var(--layout-line);background:transparent}.layout-report figure.report-chart figcaption{font-size:1em}.layout-report .chart-frame{overflow:auto}.layout-report .chart-frame>svg{display:block;width:100%;min-width:460px}.layout-report .chart-frame>svg text{fill:var(--ink);font:12px system-ui,sans-serif}
.layout-report .layout-block[data-aspect=wide] figure img,.layout-report .layout-block[data-aspect=wide] .chart-frame>svg{aspect-ratio:16/9;object-fit:contain}.layout-report .layout-block[data-aspect=square] figure img,.layout-report .layout-block[data-aspect=square] .chart-frame>svg{aspect-ratio:1;object-fit:contain}.layout-report .layout-block[data-aspect=portrait] figure img,.layout-report .layout-block[data-aspect=portrait] .chart-frame>svg{aspect-ratio:3/4;object-fit:contain}
.layout-report .layout-table-wrap{overflow-x:auto}.layout-report table{border-collapse:collapse;width:100%;font-size:.86em}.layout-report th,.layout-report td{border:0;border-bottom:1px solid var(--layout-line);padding:11px 9px;text-align:left;vertical-align:top;overflow-wrap:anywhere}.layout-report th{font-weight:650;background:transparent;color:var(--ink)}.layout-report th button{padding:0;border:0;background:none;color:inherit;font:inherit;cursor:pointer}.layout-report .layout-filter{display:flex;align-items:center;gap:10px;margin:0 0 12px;font-size:.82em}.layout-report .layout-filter input{min-width:0;max-width:240px;background:var(--paper);color:var(--ink);border:1px solid var(--layout-line);border-radius:6px;padding:7px 9px;font:inherit}.layout-report tr[hidden]{display:none}
.layout-report .layout-source-list{padding-left:1.5em}.layout-report .layout-source-list li{margin:.6em 0}.layout-report .layout-source-list a,.layout-report a{color:var(--accent)}.layout-report .citation-button{border:0;background:transparent;color:var(--accent);font:inherit;cursor:pointer;text-decoration:underline;padding:0 2px}.layout-report .layout-references,.layout-report .layout-appendix{margin-top:var(--layout-gap);border-top:1px solid var(--layout-line);padding-top:18px}.layout-report .layout-references summary,.layout-report .layout-appendix summary{cursor:pointer;font-weight:600}
.layout-report[data-density=compact]{--layout-density:.75}.layout-report[data-density=spacious]{--layout-density:1.25}.layout-report[data-density=standard]{--layout-density:1}.layout-report .layout-grid{gap:calc(var(--layout-gap) * var(--layout-density))}
@media(max-width:680px){.layout-report{padding:20px 16px;border-radius:0}.layout-report .layout-grid>div{grid-column:1/-1!important}.layout-report .layout-cover h1{font-size:clamp(24px,10vw,var(--layout-title))}.layout-report .layout-tabs{overflow-x:auto;flex-wrap:nowrap}.layout-report .layout-tabs button{white-space:nowrap}.layout-report .chart-frame>svg{min-width:360px}}
@media print{.layout-report{padding:0;border:0;border-radius:0}.layout-report .layout-contents,.layout-report .layout-tabs,.layout-report .layout-filter,.layout-report [data-app-only]{display:none!important}.layout-report .layout-section[hidden]{display:block!important}.layout-report [data-report-page]{break-before:auto!important}.layout-report .layout-grid{gap:12px}.layout-report .layout-metric,.layout-report figure,.layout-report tr{break-inside:avoid}.layout-report .layout-section-heading{break-after:avoid}.layout-report table{font-size:10pt}.layout-report th,.layout-report td{padding:5px}.layout-report .chart-frame{overflow:visible}.layout-report .chart-frame>svg{min-width:0}.layout-report .layout-cover{padding:18pt 0}.layout-report .layout-cover h1{font-size:min(var(--layout-title),38pt)}.layout-report .layout-section{break-inside:auto}}
`

const color=(value:unknown,fallback:string)=>typeof value==='string'&&/^#[0-9a-f]{6}$/i.test(value)?value:fallback
const bounded=(value:unknown,lo:number,hi:number,fallback:number)=>typeof value==='number'&&Number.isFinite(value)?Math.max(lo,Math.min(hi,value)):fallback
const sourceId=(id:string)=>`report-source-${id.replace(/[^a-zA-Z0-9-]/g,'-')}`
const metricValue=(metric:Metric)=>metric.display+(metric.unit==='publication'?` ${t('篇')}`:metric.unit==='research_family_or_unlinked_publication'?` ${t('项')}`:'')

function LayoutTable({columns,rows,interactions,renderCitation}:{columns:string[];rows:TableRow[];interactions:string[];renderCitation:(id:string)=>ReactNode}) {
  const [filter,setFilter]=useState(''),[sort,setSort]=useState<{column:number;direction:1|-1}|null>(null)
  const order=rows.map((row,index)=>({row,index}))
  if(sort)order.sort((a,b)=>String(a.row.cells[sort.column]||'').localeCompare(String(b.row.cells[sort.column]||''),undefined,{numeric:true,sensitivity:'base'})*sort.direction||a.index-b.index)
  const search=filter.trim().toLocaleLowerCase()
  return <div className="layout-table" data-layout-table>
    {interactions.includes('filter')&&<label className="layout-filter" data-report-offline><span>{t('筛选表格')}</span><input type="search" data-layout-filter value={filter} onChange={event=>setFilter(event.target.value)}/></label>}
    <div className="layout-table-wrap"><table><thead><tr>{columns.map((column,index)=><th key={index} scope="col" aria-sort={sort?.column===index?(sort.direction===1?'ascending':'descending'):undefined}>{interactions.includes('sort')?<button type="button" data-report-offline data-layout-sort={index} onClick={()=>setSort(current=>({column:index,direction:current?.column===index&&current.direction===1?-1:1}))}>{column} <span aria-hidden="true">{sort?.column===index?(sort.direction===1?'↑':'↓'):'↕'}</span></button>:column}</th>)}{rows.some(row=>row.citations?.length)&&<th scope="col">{t('来源')}</th>}</tr></thead>
      <tbody>{order.map(({row,index})=><tr key={index} data-layout-search={row.cells.join(' ')} hidden={!!search&&!row.cells.some(cell=>cell.toLocaleLowerCase().includes(search))}>{row.cells.map((value,i)=><td key={i} title={interactions.includes('tooltip')?value:undefined}>{value}</td>)}{rows.some(item=>item.citations?.length)&&<td>{row.citations?.map(id=><span key={id}>{renderCitation(id)} </span>)}</td>}</tr>)}</tbody>
    </table></div>
  </div>
}

function sourceList(items:Citation[],renderCitation:(id:string)=>ReactNode,anchors=true){
  return <ol className="layout-source-list">{items.map(item=>{const url=safeExternalUrl(item.source_url);return <li key={item.citation_id} id={anchors?sourceId(item.citation_id):undefined}>{renderCitation(item.citation_id)} {' '}{item.source_title||item.citation_id}{url&&<> · <a href={url} target="_blank" rel="noopener noreferrer">{t('查看来源')}</a></>}{item.extracted_evidence&&<details><summary>{t('来源摘录')}</summary><p>{item.extracted_evidence}</p></details>}</li>})}</ol>
}

function chartTable(chart:DeliveryChart,interactions:string[],renderCitation:(id:string)=>ReactNode){
  if(chart.rows)return <LayoutTable columns={chart.columns||[]} rows={chart.rows.map(row=>({cells:row.values,citations:row.citation_ids}))} interactions={interactions} renderCitation={renderCitation}/>
  if(chart.points?.length)return <LayoutTable columns={[t('条目'),chart.unit_label]} rows={chart.points.map(point=>({cells:[point.label,point.value===null?t('未覆盖'):String(point.value)]}))} interactions={interactions} renderCitation={renderCitation}/>
  const names=new Map((chart.nodes||[]).map(node=>[node.id,node.label]))
  return <LayoutTable columns={[t('参与方'),t('参与方'),t('关系')]} rows={(chart.edges||[]).map(edge=>({cells:[names.get(edge.source)||edge.source,names.get(edge.target)||edge.target,edge.label||''],citations:edge.citation_ids}))} interactions={interactions} renderCitation={renderCitation}/>
}

function Block({block,sectionTitle,charts,citations,interactions,renderMarkdown,renderCitation,canDraw,sourceAnchors}:{block:BoundBlock;sectionTitle:string;charts:Map<string,DeliveryChart>;citations:Map<string,Citation>;interactions:string[];renderMarkdown:(text:string)=>ReactNode;renderCitation:(id:string)=>ReactNode;canDraw:boolean;sourceAnchors:boolean}) {
  const data=block.data
  if(!data||!['bound','text_fallback'].includes(block.status))return null
  let content:ReactNode=null
  if(data.kind==='narrative'&&data.markdown)content=renderMarkdown(data.markdown)
  else if(data.kind==='heading'&&data.text&&data.text!==sectionTitle)content=createElement(`h${bounded(block.level,3,6,3)}`,null,data.text)
  else if(data.kind==='metric'&&data.metric)content=<div className="layout-metric"><strong>{metricValue(data.metric)}</strong><span>{data.metric.label}</span></div>
  else if(data.kind==='metrics'&&data.items){const metrics=data.items as Metric[];content=<LayoutTable columns={[t('指标'),t('数值')]} rows={metrics.map(item=>({cells:[item.label,metricValue(item)]}))} interactions={interactions} renderCitation={renderCitation}/>}
  else if(data.kind==='sources'&&data.items)content=sourceList((data.items as Citation[]).map(item=>({...item,...citations.get(item.citation_id)})),renderCitation,sourceAnchors)
  else if(data.kind==='relationships'&&data.items){const names=new Map((data.nodes||[]).map(node=>[node.id,node.label]));content=<LayoutTable columns={[t('参与方'),t('参与方'),t('关系')]} rows={(data.items as Edge[]).map(edge=>({cells:[names.get(edge.source)||edge.source,names.get(edge.target)||edge.target,edge.label||''],citations:edge.citation_ids}))} interactions={interactions} renderCitation={renderCitation}/>}
  else if(data.kind==='technical_comparison'&&data.items)content=<LayoutTable columns={data.columns||[]} rows={(data.items as Comparison[]).map(row=>({cells:row.values,citations:row.citation_ids}))} interactions={interactions} renderCitation={renderCitation}/>
  else if(data.kind==='chart'&&data.reference&&canDraw){const chart=charts.get(data.reference.chart_id);if(chart)content=<Chart chart={chart} kind={data.reference.kind} skillId={data.reference.drawing_skill_id} renderTable={item=>chartTable(item,interactions,renderCitation)}/>}
  if(!content)return null
  return <div className={`layout-block layout-block--${block.kind}`} data-layout-block={block.block_id} data-aspect={block.aspect} style={{gridColumn:`span ${bounded(block.span,4,12,12)}`}}>{content}</div>
}

/** The report reads only the layout and evidence already frozen for this task. */
export default function ReportLayoutView({view,renderMarkdown,renderCitation}:{view:DeliveryView;renderMarkdown:(text:string)=>ReactNode;renderCitation:(id:string)=>ReactNode}) {
  useLocale()
  const binding=view.layout_binding!,layout=binding.layout,interactions=layout.interactions||[]
  const sections:Section[]=[...binding.sections.map(section=>({id:section.section_id,title:section.title_origin==='role_default'?layoutRole(section.role):section.title,blocks:section.blocks})),
    ...binding.unplaced_sections.map((section,index)=>({id:`extra-${index+1}`,title:section.title||t('研究内容'),markdown:section.markdown}))]
  const [current,setCurrent]=useState(0),tabs=interactions.includes('tabs'),root=useRef<HTMLDivElement>(null)
  useEffect(()=>{
    let details:Array<[HTMLDetailsElement,boolean]>=[],hidden:Array<[HTMLElement,boolean]>=[]
    const before=()=>{
      if(!root.current)return
      details=Array.from(root.current.querySelectorAll('details')).map(item=>[item,item.open])
      hidden=Array.from(root.current.querySelectorAll<HTMLElement>('[data-layout-panel],tbody tr')).map(item=>[item,item.hidden])
      details.forEach(([item])=>{item.open=true});hidden.forEach(([item])=>{item.hidden=false})
    }
    const after=()=>{details.forEach(([item,open])=>{item.open=open});hidden.forEach(([item,wasHidden])=>{item.hidden=wasHidden});details=[];hidden=[]}
    window.addEventListener('beforeprint',before);window.addEventListener('afterprint',after)
    return ()=>{window.removeEventListener('beforeprint',before);window.removeEventListener('afterprint',after)}
  },[])
  const prefix=`layout-${view.artifact_id.slice(0,12).replace(/[^a-zA-Z0-9-]/g,'')}`
  const charts=new Map<string,DeliveryChart>(view.charts.map(chart=>[chart.chart_id,chart]))
  const citations=new Map<string,Citation>((view.citations||[]).map(item=>[item.citation_id,item]))
  const firstSource=binding.sections.flatMap(section=>section.blocks).find(block=>block.data?.kind==='sources')
  const listed=new Set((firstSource?.data?.items as Citation[]||[]).map(item=>item.citation_id))
  const remaining=(view.citations||[]).filter(item=>!listed.has(item.citation_id))
  const values=layout.tokens
  const style={'--paper':color(values.background,'#f8fafb'),'--ink':color(values.foreground,'#183039'),'--accent':color(values.accent,'#36867c'),
    '--layout-font':values.font==='serif'?"Georgia,'Songti SC',serif":values.font==='mono'?"Consolas,monospace":"'Segoe UI','Microsoft YaHei',sans-serif",
    '--layout-title':`${bounded(values.title_px,24,96,56)}px`,'--layout-body':`${bounded(values.body_px,14,24,16)}px`,
    '--layout-gap':`${bounded(values.spacing,8,48,24)}px`,'--layout-width':values.width==='wide'?'1320px':'1000px'} as CSSProperties
  function tabKey(event:KeyboardEvent<HTMLButtonElement>,index:number){
    if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return
    event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?sections.length-1:(index+(event.key==='ArrowRight'?1:-1)+sections.length)%sections.length
    setCurrent(next);root.current?.querySelectorAll<HTMLButtonElement>('[data-layout-tab]')[next]?.focus()
  }
  return <div ref={root} className="adrs-delivery layout-report" data-density={layout.density} style={style} aria-label={t('图文研究报告')}>
    <style>{deliveryStyles+layoutStyles}</style><div className="layout-paper">
      {layout.running_header&&<header className="layout-running-header">{view.title}</header>}
      <header className="layout-cover"><h1>{view.title}</h1></header>
      {interactions.includes('contents')&&<nav className="layout-contents" aria-label={t('报告目录')}>{sections.map((section,index)=><a key={section.id} data-layout-nav={index} href={`#${prefix}-${section.id}`} onClick={event=>{event.preventDefault();setCurrent(index);requestAnimationFrame(()=>{const panel=document.getElementById(`${prefix}-${section.id}`);if(panel instanceof HTMLDetailsElement)panel.open=true;panel?.scrollIntoView()})}}>{String(index+1).padStart(2,'0')} · {section.title}</a>)}</nav>}
      {tabs&&<div className="layout-tabs" role="tablist" aria-label={t('报告章节')}>{sections.map((section,index)=><button key={section.id} type="button" role="tab" data-report-offline data-layout-tab={index} id={`${prefix}-tab-${index}`} aria-selected={current===index} aria-controls={`${prefix}-${section.id}`} tabIndex={current===index?0:-1} onClick={()=>setCurrent(index)} onKeyDown={event=>tabKey(event,index)}>{section.title}</button>)}</div>}
      {sections.map((section,index)=>{const title=<h2 className="layout-section-heading"><span>{String(index+1).padStart(2,'0')}</span>{section.title}</h2>
        const content=<div className="layout-grid">{section.markdown?<div className="layout-block" style={{gridColumn:'span 12'}}>{renderMarkdown(section.markdown)}</div>:section.blocks?.map(block=><Block key={block.block_id} block={block} sectionTitle={section.title} charts={charts} citations={citations} interactions={interactions} renderMarkdown={renderMarkdown} renderCitation={renderCitation} canDraw={['ready','rendered'].includes(view.drawing.status)} sourceAnchors={block.block_id===firstSource?.block_id}/>)}</div>
        const props={id:`${prefix}-${section.id}`,'data-report-page':true,'data-layout-panel':index,hidden:tabs&&current!==index,role:tabs?'tabpanel':undefined,'aria-labelledby':tabs?`${prefix}-tab-${index}`:undefined}
        return interactions.includes('expand')?<details key={section.id} {...props} className="layout-section" open><summary>{title}</summary>{content}</details>:<section key={section.id} {...props} className="layout-section">{title}{content}</section>
      })}
      {view.appendix_markdown&&<details className="layout-appendix" data-report-appendix><summary>{t('技术附录：方法、实验与资源')}</summary>{renderMarkdown(view.appendix_markdown)}</details>}
      {!!remaining.length&&<details className="layout-references" data-report-references><summary>{t('参考资料')}</summary>{sourceList(remaining,renderCitation)}</details>}
      {layout.running_footer&&<footer className="layout-running-footer">{view.title}</footer>}
    </div>
  </div>
}
