import RetainedCitations from './RetainedCitations'
import type { RetainedCitation } from './RetainedCitations'

const record=(value:unknown):value is Record<string,unknown>=>Boolean(value&&typeof value==='object'&&!Array.isArray(value))
const objects=(value:unknown):Record<string,unknown>[]=>Array.isArray(value)?value.filter(record):[]
const text=(value:unknown)=>typeof value==='string'?value:''
const number=(value:unknown)=>typeof value==='number'&&Number.isFinite(value)?value:0
const facetNames:Record<string,string>={experimental_design:'实验设计',baselines:'比较基线',conditions:'实验条件',results:'结果'}
function gapLabel(value:unknown) {
  const gap=text(value)
  if(gap.startsWith('no_selected_window_for:'))return `尚未选到${facetNames[gap.split(':')[1]]||'指定问题'}的原文窗口`
  return ({no_source_excerpt_fits_current_context_allowance:'当前上下文额度未容纳原文片段',
    no_literal_query_match_in_selected_sources:'所选来源没有直接的查询词匹配，需结合语义分析判断',
    selected_context_has_no_declared_full_text_source:'所选片段没有声明完整全文的来源'} as Record<string,string>)[gap]||gap
}

export default function ContextEvidenceSummary({analyst,report,sessionId}:{analyst?:unknown;report?:unknown;sessionId?:string|null}) {
  const phases:Array<Record<string,unknown>>=[]
  if(record(analyst)) {
    if(Array.isArray(analyst.phases))phases.push(...objects(analyst.phases))
    else if(Array.isArray(analyst.sources))phases.push({phase_id:'分析',...analyst})
  }
  if(record(report)&&Array.isArray(report.sources))phases.push({phase_id:'写作',...report})
  if(!phases.length)return null
  return <details className="my-3 rounded-lg border p-3 text-sm" aria-label="各阶段的问题与证据片段">
    <summary className="cursor-pointer font-medium">各问题实际使用的原文与缺口</summary>
    <p className="my-2 text-xs text-xmgray-500">这里记录选段及遗漏情况；报告主张的支持情况见内容核对。位置对应本次保留的文字版本。</p>
    {phases.map((phase,index)=>{
      const coverage=record(phase.question_evidence)?phase.question_evidence:{}
      const sources=objects(phase.sources)
      const citations:RetainedCitation[]=sources.flatMap(source=>{
        const excerpt=objects(source.excerpts)[0]
        if(!excerpt||!text(source.evidence_id))return []
        return [{citation_id:`citation:${number(source.citation_id)}`,source_url:text(source.url),source_title:text(source.title),
          extracted_evidence:text(excerpt.quote),locator:{evidence_id:text(source.evidence_id),start:number(excerpt.start),end:number(excerpt.end),
            offset_unit:'task_retained_evidence_character',parse_version_id:text(source.parse_version_id)||null}}]
      })
      return <details key={`${text(phase.phase_id)}-${index}`} className="my-2 rounded border p-2">
        <summary className="cursor-pointer">{text(phase.module)||text(phase.phase_id)||`问题 ${index+1}`} · {sources.length} 个来源</summary>
        {!!text(coverage.question)&&<p className="my-2">{text(coverage.question)}</p>}
        {Array.isArray(coverage.gaps)&&coverage.gaps.length>0&&<ul className="my-2 list-disc pl-5 text-xs">{coverage.gaps.map((gap,i)=><li key={i}>{gapLabel(gap)}</li>)}</ul>}
        {Array.isArray(phase.omitted_evidence_ids)&&phase.omitted_evidence_ids.length>0&&<p className="text-xs">本阶段未纳入 {phase.omitted_evidence_ids.length} 个来源，保留资料仍可查看。</p>}
        <RetainedCitations sessionId={sessionId} citations={citations}/>
        {sources.map(source=><details key={text(source.evidence_id)} className="my-2 text-xs">
          <summary className="cursor-pointer">{text(source.title)||text(source.evidence_id)} · 全部选段及位置</summary>
          <p className="my-1 break-all">文字版本：{text(source.retained_version_id)||'旧记录未保存版本锚点'}</p>
          {objects(source.excerpts).map((excerpt,i)=><div key={i} className="my-2">
            <p>字符 {number(excerpt.start)}–{number(excerpt.end)}{Array.isArray(excerpt.pages)&&excerpt.pages.length>0?`；页码 ${excerpt.pages.join('、')}`:''}</p>
            <blockquote className="whitespace-pre-wrap break-words bg-xmgray-50 p-2">{text(excerpt.quote)}</blockquote>
          </div>)}
          {record(source.compression)&&<p>原文保留 {number(source.compression.retained_source_characters)} 字符，本阶段选入 {number(source.compression.selected_unique_characters)} 字符。</p>}
        </details>)}
      </details>
    })}
  </details>
}
