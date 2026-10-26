import {uiDefinition,useLocale,t} from '../i18n'
export interface CorpusSnapshot {
  schema_version: string; coverage: string; request_frozen_at: string; evaluated_at: string; counting_unit: string
  declaration: { collection_mode: string; effective_seed_urls: string[]; search_terms: string[]; effective_search_terms: string[]
    source_policy: { groups: string[]; domains_by_group: Record<string, string[]> } | null
    inclusion: { start_date: string; end_date: string; disciplines: string[]; topic: string; output_types: string[] } }
  counts: { source_candidates: number; accepted_source_records?: number; accepted_publications: number; accepted_research_families: number; excluded_candidates: number
    pending_candidates: number; accepted_without_full_text: number; duplicate_seed_urls: number }
  records: Array<{ source_url: string; title: string | null; admission_status: 'candidate' | 'accepted' | 'excluded'
    record_kind: string; full_text_status: string; reason_code: string; reason?: string; acquisition_error?: string
    stages: Array<{ status: string; at?: string; reason_code?: string }> }>
  limits: string[]
}
const statuses = uiDefinition({ candidate: '候选待核', accepted: '已采纳', excluded: '已排除' })
const reasons: Record<string, string> = uiDefinition({
  not_evaluated: '尚未完成成果核实', source_supported_in_scope: '符合本次原文、日期和归属条件',
  source_out_of_scope: '线索来源不在允许范围内', publication_date_out_of_scope: '发表日期明确不在所选范围内',
  date_precision_overlaps_scope: '日期精度不足，无法确定是否落在所选区间',
  output_type_out_of_scope: '成果类型不符合本次选择', unverified_publication_record: '成果原文或归属仍待核实',
})
function publicUrl(url: string) {
  try { const value = new URL(url); return value.protocol === 'https:' ? value.href : undefined } catch { return undefined }
}
export default function CorpusSummary({ corpus }: { corpus: CorpusSnapshot }) {
  useLocale()

  const { declaration, counts } = corpus
  return <section aria-label={t("样本基线与流转")} className="mt-4 space-y-3 rounded-xl border border-xmgray-200 bg-white p-4 text-sm">
    <h3 className="font-semibold">{t("样本基线与流转")}</h3>
    <p className="text-xs text-xmgray-600">{t("仅声明及实际取得的样本，不是现实成果全集。候选网页数量与论文数量分别计数。")}</p>
    <p>{t("来源候选 ")}{counts.source_candidates}{counts.accepted_source_records !== undefined && <> {t(" · 采纳来源 ")}{counts.accepted_source_records}</>} {t(" · 采纳发表 ")}{counts.accepted_publications} {t(" · 家族／未链接发表单元 ")}{counts.accepted_research_families} {t(" · 排除候选 ")}{counts.excluded_candidates} {t(" · 待核 ")}{counts.pending_candidates}</p>
    <p className="text-xs">{t("采纳但未取得全文 ")}{counts.accepted_without_full_text} {t(" · 重复种子合并 ")}{counts.duplicate_seed_urls}</p>
    <details><summary>{t("本次声明与覆盖")}</summary><div className="mt-2 space-y-2 text-xs">
      <p>{t("范围：")}{declaration.inclusion.start_date} {t(" 至 ")}{declaration.inclusion.end_date} · {declaration.inclusion.disciplines.join('、')} · {declaration.inclusion.topic}</p>
      <p>{t("采集：")}{declaration.collection_mode === 'seeds_only' ? t("只读声明种子，不扩展检索") : t("检索与种子")}{t("；成果类型：")}{declaration.inclusion.output_types.join('、') || t("未额外限定")}</p>
      <p>{t("检索式：")}{declaration.effective_search_terms.join('；')}{t("（声明；只读种子时不执行检索）")}</p>
      <p>{t("域名范围：")}{declaration.source_policy ? Object.values(declaration.source_policy.domains_by_group).flat().join('、') : t("未额外限定，沿用原工具出站边界")}</p>
      <p>{t("冻结：")}{corpus.request_frozen_at}{t("；评估：")}{corpus.evaluated_at}{t("；单位：")}{corpus.counting_unit}</p>
      <ul>{declaration.effective_seed_urls.map(url => <li key={url}><a href={publicUrl(url)} target="_blank" rel="noopener noreferrer">{url}</a></li>)}</ul>
    </div></details>
    <table aria-label={t("样本流转记录")} className="w-full table-fixed text-left text-xs">
      <colgroup><col style={{ width: '40%' }} /><col style={{ width: '13%' }} /><col style={{ width: '15%' }} /><col style={{ width: '32%' }} /></colgroup>
      <thead><tr><th>{t("来源候选")}</th><th>{t("状态")}</th><th>{t("全文")}</th><th>{t("依据／缺口")}</th></tr></thead><tbody>
      {corpus.records.map(item => <tr key={item.source_url}>
        <td className="break-words align-top pr-3"><a href={publicUrl(item.source_url)} target="_blank" rel="noopener noreferrer">{item.title || item.source_url}</a></td>
        <td className="whitespace-nowrap align-top"><span>{statuses[item.admission_status]}</span></td>
        <td className="whitespace-nowrap align-top"><span>{item.full_text_status === 'acquired' ? t("已取得全文") : t("未取得全文")}</span></td>
        <td className="break-words align-top"><p>{reasons[item.reason_code] || t("尚待进一步核实")}</p>{item.acquisition_error && <p>{item.acquisition_error}</p>}
          <details><summary>{t("流转与原始依据")}</summary><p>{item.reason_code} · {item.reason || ''}</p><ol>{item.stages.map((stage, index) => <li key={index}>{statuses[stage.status as keyof typeof statuses] || (stage.status === 'source_acquired' ? t("已取得来源文字") : stage.status)} {stage.at || ''}</li>)}</ol></details></td>
      </tr>)}
    </tbody></table>
    <ul className="text-xs text-xmgray-500">{corpus.limits.map(note => <li key={note}>{note}</li>)}</ul>
  </section>
}
