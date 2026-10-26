import {useLocale,t,uiDefinition} from '../i18n'
interface TrendAnchor {evidence_id:string;source_url:string;start:number;end:number;quote:string;source_role:string}
export interface TrendView {
  schema_version:string;boundaries:string[];pending_records:Array<{reason:string}>
  coverage_snapshot:{sample_years:number[];multiple_sample_years_present:boolean;longitudinal_trend_established:boolean;sufficiency_note:string;source_count:number;taxonomy_version:string|null}
  records:Array<{trend_id:string;kind:string;claim_domain:string;statement:string;status:string;supporting:TrendAnchor[];opposing:TrendAnchor[];alternative_explanations:string[];conditions:string[];horizon_start:string|null;horizon_end:string|null;gaps:string[]}>
}
function Source({anchor}:{anchor:TrendAnchor}) {
  useLocale()

  let url:string|undefined
  try { const parsed=new URL(anchor.source_url);if(['http:','https:'].includes(parsed.protocol))url=parsed.href } catch { /* retain source text */ }
  return <li className="mt-2 break-words text-xs"><a className="underline" href={url} target="_blank" rel="noopener noreferrer">{anchor.evidence_id}</a> · {anchor.source_role} {t(" · 字符 ")}{anchor.start}–{anchor.end}<blockquote className="mt-1 border-l-2 border-orange-200 pl-2">{anchor.quote}</blockquote></li>
}
const kinds:Record<string,string>=uiDefinition({observation:'来源观察（待语义审核）',inference:'有界推断（待复核）',scenario:'带条件的未来情景'})
export default function TrendSummary({view}:{view:TrendView}) {
  useLocale()

  const coverage=view.coverage_snapshot
  return <section aria-label={t("演进与交叉材料")} className="mt-5 space-y-3 rounded-xl border border-xmgray-200 p-4 text-sm">
    <h3 className="font-semibold">{t("演进、交叉材料与条件情景")}</h3><p className="text-xs text-xmgray-500">{view.schema_version} {t(" · 分类 ")}{coverage.taxonomy_version||t("旧快照未保存")} {t(" · 已有样本年 ")}{coverage.sample_years.join('、')||t("未知")} · {coverage.source_count} {t(" 个保留来源")}</p>
    <ul className="space-y-1 text-xs text-xmgray-600">{view.boundaries.map(text=><li key={text}>{text}</li>)}</ul>
    <p className="text-xs">{coverage.sufficiency_note}{!coverage.multiple_sample_years_present && t(" 当前不足两个已知样本年，不能确立多年演进。")}</p>
    {view.records.map(record=><details key={record.trend_id} className="rounded border border-xmgray-200 p-3"><summary className="cursor-pointer">{kinds[record.kind]||record.kind} · {record.trend_id}</summary>
      <p className="mt-2">{record.statement}</p>{record.horizon_start && <p className="mt-2 text-xs">{t("情景期限：")}{record.horizon_start} {t(" 至 ")}{record.horizon_end}{t("；不是内部已知计划。")}</p>}
      <ul className="mt-2 text-xs">{record.conditions.map((text,index)=><li key={index}>{t("待验证条件：")}{text}</li>)}{record.alternative_explanations.map((text,index)=><li key={'alternative-'+index}>{t("替代解释（假设）：")}{text}</li>)}</ul>
      <h4 className="mt-3 text-xs font-medium">{t("支持片段")}</h4><ul>{record.supporting.map((anchor,index)=><Source key={index} anchor={anchor}/>)}</ul>
      <h4 className="mt-3 text-xs font-medium">{t("反向材料")}</h4>{record.opposing.length?<ul>{record.opposing.map((anchor,index)=><Source key={index} anchor={anchor}/>)}</ul>:<p className="text-xs">{t("未取得，不代表不存在反例。")}</p>}
      <ul className="mt-2 text-xs text-amber-800">{record.gaps.map((gap,index)=><li key={index}>{gap}</li>)}</ul>
    </details>)}
    {!view.records.length && <p>{t("未建立有原文依据的趋势或情景，不从论文量、相似专利或产品词汇补造结论。")}</p>}
    {!!view.pending_records.length && <details><summary className="cursor-pointer">{t("未采纳的趋势陈述")}</summary><ul className="mt-2 text-xs">{view.pending_records.map((item,index)=><li key={index}>{item.reason}</li>)}</ul></details>}
  </section>
}
