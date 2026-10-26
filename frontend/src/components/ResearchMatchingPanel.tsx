import {t,useLocale,uiMessage} from '../i18n'
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import OrganizationWeightsPanel, { configurationFromPreview, dimensionLabels } from './OrganizationWeightsPanel'
import type { WeightConfiguration, WeightPreview, WeightSelection } from './OrganizationWeightsPanel'

interface Evidence { evidence_id: string; source_url: string; retrieved_on: string; verification_status: string }
interface Snapshot {
  snapshot_id: string
  initial_configuration: WeightPreview
  snapshot: { schema_version: string; evidence_cutoff: string; bridge_version: string; source_execution_id: string; bridge_notes: string[]; evidence: Evidence[] }
}
interface Contribution {
  weight: number; lower_contribution: number; upper_contribution: number; coverage: number
  rule_version: string; evidence_ids: string[]; reasons?: string[]
}
interface Candidate {
  entity_id: string; name: string; score: number | null; lower_bound: number | null; upper_bound: number | null
  coverage: number; family_count: number; contributions: Record<string, Contribution>; missing_dimensions: string[]
}
interface Preview {
  snapshot_id: string; evidence_cutoff: string; rule_version: string; evaluation_versions: Record<string, string>
  configuration: WeightPreview
  groups: Array<{ group_id: string; context: { discipline: string; output_type: string; category: string }
    complete: Candidate[]; pending_evidence: Candidate[]; definitely_better: Array<{ better: string; worse: string }> }>
  excluded: Array<{ entity_id: string; reasons: string[] }>
  excluded_observations: Array<{ entity_id: string; family_id: string; reason: string }>
}
async function post<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch('/api/v1/research' + path, { method: 'POST',
    headers: body ? { 'Content-Type': 'application/json' } : undefined, body: body ? JSON.stringify(body) : undefined })
  const value = await response.json().catch(() => ({ detail: t("服务暂时不可用；原报告仍保留，请稍后重试。") }))
  if (!response.ok) throw new Error(typeof value.detail === 'string' ? value.detail : t("本次操作未完成，请保留原报告并检查配置。"))
  return value
}
const percentage = (value: number) => `${(value * 100).toFixed(2)}%`
const interval = (lower: number | null, upper: number | null) => lower === null || upper === null ? t("无适用分项") : `${lower.toFixed(2)}–${upper.toFixed(2)}`
function versioned(configuration: WeightConfiguration, operation: 'preview' | 'research'): WeightConfiguration {
  return { ...configuration, config_version: `${configuration.config_version.slice(0,200)}:${operation}:${crypto.randomUUID()}` }
}

export default function ResearchMatchingPanel({ sessionId, query, scope, disciplines, purpose, modules, corpus, taxonomy, actionRequirements, restartParameters, onStarted }: {
  sessionId: string; query: string; scope: unknown; disciplines: string[]
  purpose?: string; modules?: string[]
  corpus?: Record<string, unknown>
  taxonomy?: unknown
  actionRequirements?: unknown
  restartParameters?: Record<string, unknown>; onStarted: (sessionId: string) => void
}) {
  useLocale()

  const [snapshot, setSnapshot] = useState<Snapshot>()
  const [selection, setSelection] = useState<WeightSelection>()
  const prepare = useMutation<Snapshot, Error>({ mutationFn: () => post(`/${sessionId}/matching/snapshot`), onSuccess: setSnapshot })
  const configuration = selection?.configuration || (selection?.effective ? configurationFromPreview(selection.effective) : undefined)
  const rerank = useMutation<Preview, Error, WeightConfiguration>({ mutationFn: configuration => {
    if (!snapshot) throw new Error(t("请先准备本次证据快照。"))
    return post('/matching/preview', { snapshot_id: snapshot.snapshot_id, configuration: versioned(configuration,'preview') })
  } })
  const fresh = useMutation<{ session_id: string }, Error, WeightConfiguration>({ mutationFn: configuration => post('', {
    ...restartParameters, query, organization_research: { scope,
      ...(purpose ? { purpose } : {}), ...(modules ? { modules } : {}),
      ...(taxonomy ? { taxonomy } : {}),
      ...(actionRequirements ? { action_requirements:actionRequirements } : {}),
      ...(corpus ? { corpus: Object.fromEntries(['source_scope','collection_mode','seed_urls','search_terms','output_types','allow_ocr'].map(key => [key, corpus[key]])) } : {}),
      ...(selection?.reference ? { weight_preset: selection.reference } : { weights: versioned(configuration,'research') }) },
  }), onSuccess: result => onStarted(result.session_id) })
  const stale = !!rerank.data && JSON.stringify(rerank.variables) !== JSON.stringify(configuration)
  const blocked = !!selection?.error || !configuration
  const preview = rerank.data
  const refs = new Map(snapshot?.snapshot.evidence.map(item => [item.evidence_id, item]) || [])
  return <section className="card p-5 text-sm text-xmgray-700" aria-label={t("固定证据重排")}>
    <h3 className="font-medium">{t("固定证据重排")}</h3>
    <p className="mt-2 text-xs leading-5 text-xmgray-500">{t("使用本次保存的成果和来源调整偏好。原报告、原配置与已核事实保持不变；缺失分项保留区间，不按零分或虚假确定总分排序。")}</p>
    {!snapshot && <button type="button" className="btn-ghost mt-3 text-sm" disabled={prepare.isPending} onClick={() => prepare.mutate()}>{t("准备本次证据快照")}</button>}
    {prepare.isPending && <p role="status" className="mt-2 text-xs">{t("正在封存已有样本，不新增取证…")}</p>}
    {prepare.error && <p role="alert" className="mt-2 text-red-700">{uiMessage(prepare.error.message)}</p>}
    {snapshot && <div className="mt-3 space-y-3">
      <p className="text-xs">{t("仅重算，不重新取证")}</p>
      <p className="break-all text-xs">{t("来源快照：")}{snapshot.snapshot_id}</p>
      <p className="text-xs text-xmgray-500">{t("封存日：")}{snapshot.snapshot.evidence_cutoff}{t("；结构：")}{snapshot.snapshot.schema_version}{t("；转换规则：")}{snapshot.snapshot.bridge_version}</p>
      <p className="text-xs text-xmgray-500">{t("每次显式重排或新研究会生成独立配置版本，编辑标签作为前缀保留；原研究版本不变。")}</p>
      <details className="rounded-xl bg-xmgray-50 p-3 text-xs"><summary className="cursor-pointer">{t("来源、计算口径与限制")}</summary>
        <ul className="mt-2 list-disc space-y-1 pl-4">{snapshot.snapshot.bridge_notes.map(note => <li key={note}>{note}</li>)}</ul>
        <p className="mt-2 break-all">{t("来源执行：")}{snapshot.snapshot.source_execution_id}</p>
        {snapshot.snapshot.evidence.map(item => <p key={item.evidence_id} className="mt-1 break-all"><a href={item.source_url} target="_blank" rel="noreferrer" className="text-xm-600 underline">{item.evidence_id} · {item.retrieved_on}</a> {t(" · 原文定位已保存，语义未独立复核")}</p>)}
      </details>
      <details className="rounded-xl border border-xmgray-100 p-3" open><summary className="cursor-pointer text-sm">{t("调整本次重排偏好")}</summary>
        <OrganizationWeightsPanel disciplines={disciplines.join(', ')} initialPreview={snapshot.initial_configuration} onChange={setSelection} />
      </details>
      <div className="flex flex-wrap gap-3">
        <button type="button" className="btn-primary text-sm" disabled={blocked || rerank.isPending || fresh.isPending} onClick={() => configuration && rerank.mutate(configuration)}>{t("重排当前证据")}</button>
        <button type="button" className="btn-ghost text-sm" disabled={blocked || fresh.isPending || rerank.isPending} onClick={() => configuration && fresh.mutate(configuration)}>{t("重新取证并研究")}</button>
      </div>
      <p className="text-xs text-xmgray-500">{t("“重新取证并研究”将联网采集并生成独立研究及报告，使用原范围和当前偏好，按原任务预算执行。它与固定证据重排是两个动作。")}</p>
      {rerank.isPending && <p role="status">{t("正在重算固定证据…")}</p>}
      {fresh.isPending && <p role="status">{t("正在创建独立的新研究…")}</p>}
      {(rerank.error || fresh.error) && <p role="alert" className="text-red-700">{uiMessage(rerank.error?.message) || uiMessage(fresh.error?.message)}</p>}
      {stale && <p role="status" className="rounded-lg bg-orange-50 p-3 text-orange-800">{t("偏好已修改，下表仍对应上一次重排；点击“重排当前证据”更新。")}</p>}
      {preview && <div className="space-y-4" aria-label={t("重排结果")}>
        <p className="text-xs text-xmgray-500">{t("计算规则：")}{preview.rule_version}{t("；配置：")}{preview.configuration.config_version}{t("；映射：")}{preview.configuration.mappings.map(item => item.version).filter((value,index,list) => list.indexOf(value) === index).join('、')}</p>
        <p className="text-xs text-xmgray-500">{t("已应用评价版本：")}{Object.entries(preview.evaluation_versions).map(([key,value]) => key + ' ' + value).join('、') || t("无；未自动给成果赋指标或等级")}</p>
        {preview.groups.map(group => {
          const rows = [...group.complete,...group.pending_evidence]
          const names = new Map(rows.map(row => [row.entity_id,row.name]))
          return <div key={group.group_id} className="rounded-xl border border-xmgray-100 p-3">
            <h4 className="text-sm font-medium">{group.context.discipline} · {group.context.output_type}</h4>
            <p className="mt-1 text-xs text-xmgray-500">{t("学科标签来自研究范围；同组研究单元等权，不跨组建立质量榜。覆盖率与日期精度区间分别解释。")}</p>
            {rows.map(row => <article key={row.entity_id} className="mt-3 rounded-xl bg-xmgray-50 p-3" aria-label={t("{0} 重排结果", row.name)}>
              <h5 className="font-medium">{row.name}</h5>
              <div className="mt-2 flex flex-wrap gap-4 text-xs"><p>{t("分数区间：")}<output aria-label={t("{0} 分数区间", row.name)}>{interval(row.lower_bound,row.upper_bound)}</output></p>
                <p>{t("有效权重覆盖率：")}<output aria-label={t("{0} 有效权重覆盖率", row.name)}>{percentage(row.coverage)}</output></p>
                <p>{t("研究单元：")}{row.family_count}</p></div>
              <p className="mt-1 text-xs">{row.score === null ? t("保留不确定区间；没有确定总分。") : t("完整偏好分：{0}；不是质量或合作成功率。", row.score.toFixed(2))}</p>
              <div className="mt-2 overflow-x-auto"><table className="w-full text-left text-xs"><thead><tr><th>{t("分项")}</th><th>{t("权重")}</th><th>{t("贡献区间")}</th><th>{t("覆盖率")}</th></tr></thead><tbody>
                {Object.entries(row.contributions).map(([key,value]) => <tr key={key}><td>{dimensionLabels[key] || key}</td><td>{percentage(value.weight)}</td><td>{interval(value.lower_contribution,value.upper_contribution)}</td><td>{percentage(value.coverage)}</td></tr>)}
              </tbody></table></div>
              {row.missing_dimensions.length > 0 && <p className="mt-2 text-xs text-orange-700">{t("待补证：")}{row.missing_dimensions.map(key => dimensionLabels[key] || key).join('、')}</p>}
              <details className="mt-2 text-xs"><summary className="cursor-pointer">{t("分项规则与原来源")}</summary>{Object.entries(row.contributions).map(([key,value]) => <div key={key} className="mt-2">
                <p>{dimensionLabels[key] || key} · {value.rule_version}</p>
                {value.evidence_ids.map(ref => <a key={ref} className="mr-2 text-xm-600 underline" href={refs.get(ref)?.source_url} target="_blank" rel="noreferrer">{ref}</a>)}
              </div>)}</details>
            </article>)}
            {group.definitely_better.map(pair => <p key={pair.better + pair.worse} className="mt-3 text-xs">{t("确定优先：")}{names.get(pair.better) || pair.better} → {names.get(pair.worse) || pair.worse}</p>)}
            {!group.definitely_better.length && <p className="mt-3 text-xs">{t("当前区间重叠或相同，不宣称确定优劣。")}</p>}
          </div>
        })}
        {preview.excluded.map(row => <p key={row.entity_id} className="text-xs">{t("排除对象 ")}{row.entity_id}：{row.reasons.join('、')}</p>)}
        {preview.excluded_observations.map(row => <p key={row.entity_id + row.family_id} className="text-xs">{t("排除研究单元 ")}{row.family_id}：{row.reason}</p>)}
        {!preview.groups.length && <p className="text-xs">{t("没有可比较的有界样本；请查看排除原因，重排不会补造证据。")}</p>}
      </div>}
    </div>}
  </section>
}
