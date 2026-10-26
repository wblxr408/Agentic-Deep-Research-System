import {uiDefinition,t,useLocale,uiMessage} from '../i18n'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

type Weight = number | { weight: number; enabled: boolean }
type Mapping = { scheme_id: string; version: string; scores: Record<string, number> }
export interface WeightConfiguration {
  preset: string
  config_version: string
  weights: Record<string, Weight>
  performance_groups: Record<string, Weight>
  metric_weights: Record<string, Weight>
  mappings: Mapping[]
}
export interface WeightPreview {
  raw_config: Omit<WeightConfiguration, 'mappings' | 'config_version'>
  effective_weights: Record<string, number>
  effective_groups: Record<string, number>
  effective_metric_weights: Record<string, number>
  mappings: Mapping[]
  rule_version: string
  preset_version: string
  config_version: string
}
interface PersonalPreset { preset_id: string; version: number; name: string; configuration: WeightConfiguration; effective_configuration: WeightPreview }
const personalKey = (record: PersonalPreset) => `personal:${record.preset_id}:${record.version}`
export interface WeightSelection { configuration?: WeightConfiguration; reference?: { preset_id: string; version: number }; effective?: WeightPreview; error?: string }
interface Row { weight: string; enabled: boolean }
interface Draft {
  preset: string; version: string; roots: Record<string, Row>; groups: Record<string, Row>; metrics: Record<string, Row>
  mappings: Array<{ scheme_id: string; version: string; scores: Record<string, string> }>
}
interface Scheme {
  scheme_id: string; applicable: boolean; reason: string; source_access: string; source_url: string
  source_versions: Array<{ edition: string; metric_year: number; provider: string; source_url: string }>
}
interface Evaluation {
  evaluations: Array<{ scheme_id: string; availability: string; reason: string; records: Array<{ raw_value: string | number | boolean | null; edition: string; category: string; source_url: string }> }>
}
export const dimensionLabels: Record<string, string> = uiDefinition({
  topic_relevance: '主题相关性', research_alignment: '研究路线契合', output_performance: '成果表现',
  evidence_completeness: '证据完整度', recency: '时效性', cooperation_complementarity: '合作互补性',
})
const groupLabels: Record<string, string> = uiDefinition({ venue: '载体指标组', paper: '论文指标组' })
const schemeLabels: Record<string, string> = uiDefinition({
  ccf: 'CCF', icore: 'ICORE', wos_scie: 'WoS SCIE', wos_ssci: 'WoS SSCI', wos_ahci: 'WoS AHCI', wos_esci: 'WoS ESCI',
  scopus: 'Scopus 收录', jcr_jif: 'JCR JIF', jcr_quartile: 'JCR 分区', jcr_jci: 'JCR JCI', cas_partition: '中科院分区',
  citescore: 'CiteScore', citescore_percentile: 'CiteScore 百分位', sjr: 'SJR', snip: 'SNIP', abdc: 'ABDC', ajg: 'AJG',
  citation_percentile: '论文引用百分位', cnci: 'CNCI', fwci: 'FWCI',
})
const availability: Record<string, string> = uiDefinition({ available: '有匹配记录', not_applicable: '不适用', data_missing: '样本未覆盖',
  source_unavailable: '来源不可用', conflict: '记录冲突', not_indexed: '明确未收录' })
const percent = (value?: number) => value === undefined ? t("待校验") : `${(value * 100).toFixed(2)}%`
async function api<T>(url: string, body?: unknown, signal?: AbortSignal, method?: string): Promise<T> {
  const response = await fetch('/api/v1/research' + url, { signal, method: method || (body === undefined ? 'GET' : 'POST'),
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) })
  const value = await response.json()
  if (!response.ok) {
    const reason = Array.isArray(value.detail) ? value.detail.map((item: { msg: string }) => item.msg).join('；') : value.detail
    throw new Error(response.status === 409 ? t("预设已有新版本，请重新选择后再保存。") : reason || t("配置读取失败，请重试。"))
  }
  return value
}
function rows(values: Record<string, Weight>) {
  return Object.fromEntries(Object.entries(values).map(([key, value]) => [key, typeof value === 'number'
    ? { weight: String(value), enabled: true } : { weight: String(value.weight), enabled: value.enabled }]))
}
function draftFrom(preview: WeightPreview): Draft {
  return { preset: preview.raw_config.preset, version: preview.config_version,
    roots: rows({ ...Object.fromEntries(Object.keys(dimensionLabels).map(key => [key, 0])), ...preview.raw_config.weights }),
    groups: rows(preview.raw_config.performance_groups), metrics: rows(preview.raw_config.metric_weights),
    mappings: preview.mappings.map(mapping => ({ ...mapping, scores: Object.fromEntries(Object.entries(mapping.scores).map(([key, value]) => [key, String(value)])) })) }
}
function configuration(draft: Draft): WeightConfiguration {
  function number(value: string) {
    if (!value.trim() || !Number.isFinite(Number(value)) || Number(value) < 0) throw new Error(t("权重必须是有限的非负数，不能留空。"))
    return Number(value)
  }
  function values(items: Record<string, Row>) { return Object.fromEntries(Object.entries(items).map(([key, value]) => [key, { weight: number(value.weight), enabled: value.enabled }])) }
  const roots = values(draft.roots), groups = values(draft.groups), metrics = values(draft.metrics)
  if (!Object.values(roots).some(item => item.enabled && item.weight > 0)) throw new Error(t("每个活动层级至少一项正权重。"))
  if (roots.output_performance?.enabled && roots.output_performance.weight > 0) {
    if (!Object.values(groups).some(item => item.enabled && item.weight > 0)) throw new Error(t("成果表现组至少一项正权重。"))
    for (const [group, enabled] of Object.entries(groups)) {
      const members = Object.entries(metrics).filter(([key]) => (['citation_percentile','cnci','fwci'].includes(key) ? 'paper' : 'venue') === group)
      if (enabled.enabled && enabled.weight > 0 && members.length && !members.some(([, row]) => row.enabled && row.weight > 0)) throw new Error(t("每个已配置的活动指标组至少一项正权重；可关闭父级或清空指标配置。"))
    }
  }
  if (!draft.version.trim()) throw new Error(t("请填写配置版本。"))
  const mappings = draft.mappings.map(mapping => {
    const scores = Object.fromEntries(Object.entries(mapping.scores).map(([key, value]) => [key, number(value)]))
    if (Object.values(scores).some(value => value > 1)) throw new Error(t("等级偏好分值须介于 0 和 1，顺序由服务端校验。"))
    return { ...mapping, scores }
  })
  return { preset: draft.preset, config_version: draft.version, weights: roots, performance_groups: groups, metric_weights: metrics, mappings }
}

export function configurationFromPreview(preview: WeightPreview): WeightConfiguration {
  return { ...preview.raw_config, config_version: preview.config_version, mappings: preview.mappings }
}

export default function OrganizationWeightsPanel({ disciplines, onChange, initialPreview, deferInitial=false }: { disciplines: string; onChange: (selection: WeightSelection) => void; initialPreview?: WeightPreview;deferInitial?:boolean }) {
  useLocale()

  const interacted=useRef(!deferInitial)
  const markDirty=()=>{interacted.current=true;setDirty(true)}
  const client = useQueryClient()
  const [draft, setDraft] = useState<Draft | null>(() => initialPreview ? draftFrom(initialPreview) : null)
  const [selected, setSelected] = useState(initialPreview ? 'saved_configuration' : 'research_development')
  const [base, setBase] = useState<PersonalPreset | null>(null)
  const [dirty, setDirty] = useState(false)
  const [name, setName] = useState('')
  const [outputType, setOutputType] = useState('conference_paper')
  const [target, setTarget] = useState(''), [work, setWork] = useState('')
  const [publicationYear, setPublicationYear] = useState(String(new Date().getFullYear()))
  const [metricYear, setMetricYear] = useState(String(new Date().getFullYear()))
  const [ready, setReady] = useState<WeightConfiguration | null>(null)
  const catalogue = useQuery<{ version: string; presets: Record<string, WeightPreview> }>({ queryKey: ['organization-weight-catalogue'], queryFn: ({ signal }) => api('/weights/catalog', undefined, signal) })
  const presets = useQuery<{ items: PersonalPreset[] }>({ queryKey: ['organization-personal-presets'], queryFn: ({ signal }) => api('/presets', undefined, signal) })
  const savedOptions = [...(presets.data?.items || [])]
  if (base && !savedOptions.some(record => personalKey(record) === personalKey(base))) savedOptions.push(base)
  useEffect(() => { if (!draft && catalogue.data) setDraft(draftFrom(catalogue.data.presets.research_development)) }, [catalogue.data, draft])
  const parsed = useMemo(() => { try { return draft ? { config: configuration(draft) } : { error: t("权重配置加载中。") } } catch (error) { return { error: uiMessage((error as Error).message) } } }, [draft])
  const configKey = JSON.stringify(parsed.config)
  useEffect(() => { const timer = setTimeout(() => setReady(parsed.config || null), 250); return () => clearTimeout(timer) }, [parsed.config])
  const directPersonal = !!base && !dirty
  const preview = useQuery<WeightPreview>({ queryKey: ['organization-weight-preview', ready], queryFn: ({ signal }) => api('/weights/preview', ready, signal), enabled: !!ready && !directPersonal })
  const effective = directPersonal ? base?.effective_configuration : JSON.stringify(ready) === configKey && !preview.isFetching && !preview.error ? preview.data : undefined
  const error = uiMessage(catalogue.error?.message) || parsed.error || (!directPersonal && uiMessage(preview.error?.message)) || (!effective ? t("正在校验当前权重，请稍候。") : undefined)
  useEffect(() => {
    if(!interacted.current)return
    onChange(error ? { error } : directPersonal && base ? { reference: { preset_id: base.preset_id, version: base.version }, effective }
      : { configuration: parsed.config, effective })
  }, [error, directPersonal, base, effective, parsed.config, onChange])
  const context = useMemo(() => ({ disciplines: disciplines.split(/[,，]/).map(item => item.trim()).filter(Boolean), output_type: outputType }), [disciplines, outputType])
  const schemes = useQuery<{ items: Scheme[] }>({ queryKey: ['organization-evaluation-context', context], queryFn: ({ signal }) => api('/evaluation/applicability', context, signal), enabled: context.disciplines.length > 0 })
  const evaluation = useMutation<Evaluation, Error, { context: typeof context; target: string; work: string; publication: string; metric: string }>({
    mutationFn: async input => {
      if (!input.target.trim()) throw new Error(t("请填写核定的载体规范 ID。"))
      if (![input.publication,input.metric].every(value => /^\d{4}$/.test(value) && Number(value) >= 1800 && Number(value) <= 2200)) throw new Error(t("请填写 1800–2200 之间的评价和发表年份。"))
      return api('/evaluation/preview', { ...input.context, target_id: input.target.trim(), ...(input.work.trim() ? { work_id: input.work.trim() } : {}), publication_year: Number(input.publication), metric_year: Number(input.metric) })
    },
  })
  // Results are tied to the exact visible form, so changing context never shows an old lookup as current.
  const evaluationInput = { context, target, work, publication: publicationYear, metric: metricYear }
  const currentEvaluation = JSON.stringify(evaluation.variables) === JSON.stringify(evaluationInput) ? evaluation.data : undefined
  const selectPersonal = (record: PersonalPreset) => { interacted.current=true; setSelected(personalKey(record)); setBase(record); setName(record.name); setDraft(draftFrom(record.effective_configuration)); setDirty(false) }
  const restore = () => { interacted.current=true; const source = base?.effective_configuration || (selected === 'saved_configuration' ? initialPreview : catalogue.data?.presets[selected]); if (source) { setDraft(draftFrom(source)); setDirty(false) } }
  const select = (value: string) => {
    interacted.current=true
    if (value === 'saved_configuration' && initialPreview) { setSelected(value); setBase(null); setDraft(draftFrom(initialPreview)); setDirty(false); return }
    if (value.startsWith('personal:')) { const record = savedOptions.find(item => personalKey(item) === value); if (record) selectPersonal(record) }
    else if (catalogue.data?.presets[value]) { setSelected(value); setBase(null); setDraft(draftFrom(catalogue.data.presets[value])); setDirty(false) }
  }
  const save = useMutation<PersonalPreset, Error, boolean>({ mutationFn: async update => {
    if (error || !parsed.config || !name.trim()) throw new Error(error || t("请填写个人预设名称。"))
    if (update && !base) throw new Error(t("请先选择一个个人预设。"))
    return api(update ? '/presets/' + base!.preset_id : '/presets', { name: name.trim(), configuration: parsed.config,
      ...(update ? { expected_version: base!.version } : {}) }, undefined, update ? 'PUT' : 'POST')
  }, onSuccess: record => { selectPersonal(record); client.invalidateQueries({ queryKey: ['organization-personal-presets'] }) } })
  const changeRow = (level: 'roots' | 'groups' | 'metrics', key: string, patch: Partial<Row>) => {
    markDirty()
    setDraft(current => current && ({ ...current, [level]: { ...current[level], [key]: { ...(current[level][key] ?? { weight: '1', enabled: false }), ...patch } } }))
  }
  function weightRow(level: 'roots' | 'groups', key: string, label: string, value?: number) {
    const row = draft?.[level][key]
    return row && <div key={key} className="grid grid-cols-[minmax(0,1fr)_6rem_5rem] items-center gap-2 py-2">
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" aria-label={t("{0} 启用", label)} checked={row.enabled} onChange={e => changeRow(level,key,{ enabled: e.target.checked })} />{label}</label>
      <input className="input-xm text-sm" aria-label={t("{0} 权重", label)} type="number" min="0" step="any" value={row.weight} onChange={e => changeRow(level,key,{ weight: e.target.value })} />
      <output className="text-right text-xs text-xmgray-600" aria-label={t("{0} 生效权重", label)}>{percent(value)}</output>
    </div>
  }
  return <section className="mt-4 rounded-2xl border border-xmgray-200 bg-white p-4 text-left" aria-label={t("研究偏好与评价")}>
    <h3 className="text-sm font-medium text-xmgray-800">{t("研究偏好与评价")}</h3>

    {catalogue.isPending && <p role="status">{t("正在读取权重预设…")}</p>}
    {catalogue.error && <p role="alert">{uiMessage(catalogue.error.message)} <button type="button" onClick={() => catalogue.refetch()}>{t("重试读取预设")}</button></p>}
    {draft && <div className="mt-4 space-y-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="min-w-48 flex-1 text-xs text-xmgray-600">{t("权重预设")}<select aria-label={t("权重预设")} className="input-xm mt-1 text-sm" value={selected} onChange={e => select(e.target.value)}>
          {initialPreview && <option value="saved_configuration">{t("沿用本次选择")}</option>}
          <option value="research_development">{t("研究发展")}</option><option value="cooperation_discovery">{t("合作发现")}</option>
          {savedOptions.map(record => <option key={personalKey(record)} value={personalKey(record)}>{record.name} {t(" · 第 ")}{record.version} {t(" 次保存")}</option>)}
        </select></label>
        <button type="button" className="btn-ghost text-sm" onClick={restore}>{t("恢复所选预设")}</button>
      </div>
      {base && <p className="text-xs text-xmgray-600">{t("已选：")}{base.name}</p>}
      {dirty && <p className="text-xs text-orange-700">{t("本次使用调整后的权重。")}</p>}
      {presets.error && <p role="alert">{t("个人预设读取失败：")}{uiMessage(presets.error.message)} <button type="button" onClick={() => presets.refetch()}>{t("重试个人预设")}</button></p>}
      <fieldset><legend className="text-xs font-medium text-xmgray-700">{t("匹配重点 · 右侧为实际占比")}</legend>
        {Object.entries(dimensionLabels).map(([key,label]) => weightRow('roots',key,label,effective?.effective_weights[key]))}
      </fieldset>
      <fieldset><legend className="text-xs font-medium text-xmgray-700">{t("成果评价的组成")}</legend>
        {Object.entries(groupLabels).map(([key,label]) => weightRow('groups',key,label,effective?.effective_groups[key]))}
      </fieldset>

      {error && <p role="alert" className="rounded-lg bg-orange-50 p-3 text-sm text-orange-800">{uiMessage(error)}</p>}

      <div className="border-t border-xmgray-100 pt-4">
        <label className="block text-xs text-xmgray-600">{t("个人预设名称")}<input className="input-xm mt-1 text-sm" value={name} maxLength={300} onChange={e => setName(e.target.value)} /></label>
        <div className="mt-3 flex flex-wrap gap-2"><button type="button" className="btn-ghost text-sm" disabled={!!error || !name.trim() || save.isPending} onClick={() => save.mutate(false)}>{t("保存为新预设")}</button>
          <button type="button" className="btn-ghost text-sm" disabled={!base || !!error || !name.trim() || save.isPending} onClick={() => save.mutate(true)}>{t("保存新版本")}</button></div>
        {save.error && <p role="alert" className="mt-2 text-sm text-red-700">{uiMessage(save.error.message)}</p>}
      </div>
      <div className="border-t border-xmgray-100 pt-4">
        <h4 className="text-sm font-medium">{t("评价适用性与指标权重")}</h4>

        <label className="mt-3 block text-xs text-xmgray-600">{t("评价成果类型")}<select aria-label={t("评价成果类型")} className="input-xm mt-1 text-sm" value={outputType} onChange={e => setOutputType(e.target.value)}>
          {Object.entries({ conference_paper: t("会议论文"), journal_article: t("期刊论文"), preprint: t("预印本"), book: t("专著"), software: t("软件"), dataset: t("数据集") }).map(([key,label]) => <option key={key} value={key}>{label}</option>)}
        </select></label>
        <details className="mt-3 rounded-xl bg-xmgray-50 p-3"><summary className="cursor-pointer text-sm">{t("查询精确载体／论文的目录样本")}</summary>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">{[
            [t("载体规范 ID"),target,setTarget,t("例如 dblp:conf/nsdi 或 issn:0047-2506")], [t("论文规范 ID（可选）"),work,setWork,t("例如 openalex:W…")],
            [t("成果发表年"),publicationYear,setPublicationYear,''], [t("评价年份"),metricYear,setMetricYear,''],
          ].map(([label,value,setValue,placeholder]) => <label key={String(label)} className="text-xs text-xmgray-600">{String(label)}<input className="input-xm mt-1 text-sm" value={String(value)} onChange={e => (setValue as (value: string) => void)(e.target.value)} placeholder={String(placeholder)} maxLength={300} /></label>)}</div>
          <button type="button" className="btn-ghost mt-3 text-sm" disabled={evaluation.isPending || !context.disciplines.length} onClick={() => evaluation.mutate(evaluationInput)}>{t("查询指定成果评价")}</button>
          <p className="mt-2 text-xs text-xmgray-500">{t("只查已保存目录样本，不联网；此查询未应用于本次研究成果。更改输入后旧结果不再作为当前查询显示。")}</p>
          {evaluation.error && <p role="alert" className="mt-2 text-sm text-red-700">{uiMessage(evaluation.error.message)}</p>}
        </details>
        {schemes.isPending && <p role="status" className="mt-3 text-xs">{t("正在判断学科适用性…")}</p>}
        {schemes.error && <p role="alert">{uiMessage(schemes.error.message)} <button type="button" onClick={() => schemes.refetch()}>{t("重试评价适用性")}</button></p>}
        <div className="mt-3 grid gap-3 sm:grid-cols-2">{schemes.data?.items.map(scheme => {
          const label = schemeLabels[scheme.scheme_id] || scheme.scheme_id
          const metric = draft.metrics[scheme.scheme_id]
          const evaluated = currentEvaluation?.evaluations.find(item => item.scheme_id === scheme.scheme_id)
          return <article key={scheme.scheme_id} className="rounded-xl border border-xmgray-100 p-3" aria-label={t("{0} 评价状态", label)}>
            <div className="flex items-center justify-between gap-2"><span className="text-sm font-medium">{label}</span><span className="text-xs text-xmgray-600">{!scheme.applicable ? t("不适用") : scheme.source_access === 'public_sample' ? t("公开部分样本") : t("需授权导入")}</span></div>
            <p className="mt-1 text-xs text-xmgray-500">{scheme.reason}</p>
            <div className="mt-2 flex flex-wrap items-center gap-2"><label className="text-xs"><input type="checkbox" aria-label={t("{0} 指标启用", label)} checked={!!metric?.enabled} onChange={e => changeRow('metrics',scheme.scheme_id,{ enabled: e.target.checked })} /> {t(" 配置偏好")}</label>
              <input className="input-xm max-w-24 text-xs" type="number" min="0" step="any" aria-label={t("{0} 指标权重", label)} disabled={!metric?.enabled} value={metric?.weight ?? '1'} onChange={e => changeRow('metrics',scheme.scheme_id,{ weight: e.target.value })} />
              <output className="text-xs" aria-label={t("{0} 组内比例", label)}>{percent(effective?.effective_metric_weights[scheme.scheme_id] ?? (effective ? 0 : undefined))}</output></div>
            {!scheme.applicable && metric?.enabled && <p className="mt-1 text-xs text-orange-700">{t("当前学科不使用该指标。")}</p>}
            {evaluated && <div className="mt-2 text-xs"><p>{availability[evaluated.availability]}</p><p className="text-xmgray-500">{evaluated.reason}</p>
              {evaluated.records.map((record,index) => <p key={index}><a className="text-xm-600 underline" href={record.source_url} target="_blank" rel="noreferrer">{String(record.raw_value)} · {record.edition}</a> · {record.category}</p>)}</div>}
            <a href={scheme.source_url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-xs text-xm-600 underline">{t("体系来源")}</a>
            {scheme.source_versions.length > 0 && <details className="mt-1 text-xs text-xmgray-500"><summary className="cursor-pointer">{t("部分样本版本")}</summary>{scheme.source_versions.map((source,index) => <p key={index}>{source.edition} · {source.metric_year} · {source.provider}</p>)}</details>}
          </article>
        })}</div>
        <button type="button" className="btn-ghost mt-3 text-xs" onClick={() => { markDirty(); setDraft({ ...draft, metrics: {} }) }}>{t("清空指标配置")}</button>
      </div>
      <details className="border-t border-xmgray-100 pt-3"><summary className="cursor-pointer text-sm">{t("等级对应的偏好分值")}</summary>
        {draft.mappings.map((mapping,index) => <fieldset key={mapping.scheme_id} className="mt-3 rounded-xl bg-xmgray-50 p-3"><legend className="text-xs">{schemeLabels[mapping.scheme_id]}</legend>

          <div className="mt-2 flex flex-wrap gap-3">{Object.entries(mapping.scores).map(([grade,value]) => <label key={grade} className="w-20 text-xs">{grade}<input className="input-xm mt-1 text-xs" type="number" min="0" max="1" step="any" aria-label={t("{0} {1} 偏好分值", schemeLabels[mapping.scheme_id], grade)} value={value} onChange={e => { markDirty(); setDraft({ ...draft, mappings: draft.mappings.map((item,i) => i === index ? { ...item, scores: { ...item.scores, [grade]: e.target.value } } : item) }) }} /></label>)}</div>
        </fieldset>)}
      </details>
    </div>}
  </section>
}
