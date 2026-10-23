interface TechnicalAnchor { evidence_id:string;source_url:string;start:number;end:number;quote:string;pages:number[];source_coverage:string }
export interface TechnicalReading {
  schema_version:string;selection_basis:string;gaps:string[]
  cards:Array<{output_id:string;title:string;reading_depth:string;full_text_available:boolean;model_read_entire_document:boolean;interpretation:string;unknown_fields:string[];
    fields:Record<string,{label:string;text:string|null;status:string;reason:string|null;proofs:TechnicalAnchor[]}>;
    figure_references:Array<{label:string;page:number|null;source_url:string;asset_status:string;proof:TechnicalAnchor}>}>
  pending_records:Array<{reason:string;output_id?:string}>
}
const reasonLabels:Record<string,string>={full_text_required_for_this_field:'只有摘要／元数据，当前字段需要全文',full_text_unavailable_not_inferred_from_abstract:'未取得全文，保留未知',not_extracted_from_available_source:'未从可用材料抽取',numeric_summary_value_missing_from_literal_proofs:'数值未能对应所引原文'}
function sourceUrl(value:string) { try { const url=new URL(value);return ['http:','https:'].includes(url.protocol)?url.href:undefined } catch {return undefined} }
function Source({proof}:{proof:TechnicalAnchor}) {
  return <li className="mt-2 break-words text-xs"><a className="underline" href={sourceUrl(proof.source_url)} target="_blank" rel="noopener noreferrer">{proof.evidence_id}</a> · 字符 {proof.start}–{proof.end}{!!proof.pages.length && ` · PDF页 ${proof.pages.join('、')}`}<blockquote className="mt-1 border-l-2 border-orange-200 pl-2">{proof.quote}</blockquote></li>
}
export default function TechnicalReadingSummary({reading}:{reading:TechnicalReading}) {
  return <section aria-label="代表成果深读" className="mt-5 space-y-3 rounded-xl border border-xmgray-200 p-4 text-sm">
    <h3 className="font-semibold">代表成果深读与来源定位</h3><p className="text-xs text-xmgray-500">{reading.schema_version} · {reading.selection_basis}。逐字段区分来源摘要与未知，原文图表定位不等于取得图像或独立复现。</p>
    {reading.cards.map(card=><article key={card.output_id} className="space-y-2 rounded-lg bg-white p-3">
      <h4 className="font-medium">{card.title}</h4><p className="text-xs">{card.full_text_available?'已保留全文来源，模型使用有界片段':'仅摘要／元数据来源，深读细节未知'} · {card.unknown_fields.length} 个字段待补</p><p className="text-xs text-xmgray-600">{card.interpretation}</p>
      {Object.entries(card.fields).map(([key,field])=><details key={key} className="rounded border border-xmgray-100 p-2">
        <summary className="cursor-pointer">{field.label} · {field.text?'来源摘要（待语义审核）':'未知'}</summary><p className="mt-2">{field.text || reasonLabels[field.reason||''] || field.reason || '未取得依据'}</p><ul>{field.proofs.map((proof,index)=><Source key={index} proof={proof}/>)}</ul>
      </details>)}
      {!!card.figure_references.length && <details><summary className="cursor-pointer">原文图表／公式定位</summary><ul>{card.figure_references.map((figure,index)=><li key={index} className="mt-2"><a className="underline" href={sourceUrl(figure.source_url)} target="_blank" rel="noopener noreferrer">{figure.label}{figure.page?` · 页 ${figure.page}`:''}</a><p className="text-xs">原文引用，未自动取得图片；与系统生成图表分开。</p><ul><Source proof={figure.proof}/></ul></li>)}</ul></details>}
    </article>)}
    {!reading.cards.length && <p>尚无可关联的采纳成果，不以网站背景材料代替论文深读。</p>}
    <ul className="text-xs text-amber-800">{reading.gaps.map(gap=><li key={gap}>{gap}</li>)}{reading.pending_records.map((item,index)=><li key={index}>待核：{item.reason}</li>)}</ul>
  </section>
}
