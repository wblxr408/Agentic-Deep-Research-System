import {uiDefinition,t,useLocale} from '../i18n'
import type { WeightSelection } from './OrganizationWeightsPanel'
import AnalysisPurposePanel from './AnalysisPurposePanel'
import type { ResearchPurpose, ResearchModule } from './AnalysisPurposePanel'
import CorpusPanel, { corpusRequest } from './CorpusPanel'
import type { CorpusDraft } from './CorpusPanel'
import TaxonomyEditor, { taxonomyRequest } from './TaxonomyEditor'
import type { TaxonomyDraft } from './TaxonomyEditor'
import ActionRequirementsPanel, { actionRequirementsRequest } from './ActionRequirementsPanel'
import type { ActionRequirementsDraft } from './ActionRequirementsPanel'

export type OrganizationType = 'university' | 'laboratory' | 'company'
export interface OrganizationDraft {
  enabled: boolean
  purpose?: ResearchPurpose
  modules?: ResearchModule[] | null
  corpus?: CorpusDraft
  taxonomy?: TaxonomyDraft
  actionRequirements?: ActionRequirementsDraft
  types: OrganizationType[]
  disciplines: string
  startDate: string
  endDate: string
  entities: Array<{ name: string; type: OrganizationType; source: string }>
}

export const defaultOrganizationDraft: OrganizationDraft = {
  enabled: false, types: ['university', 'laboratory', 'company'],
  purpose: 'research_development', modules: null,
  disciplines: 'computer_science', startDate: '2020-01-01',
  endDate: new Date().toISOString().slice(0, 10), entities: [],
}
const labels: Record<OrganizationType, string> = uiDefinition({ university: '高校', laboratory: '科研实验室', company: '企业' })

export function organizationRequest(draft: OrganizationDraft, topic: string, preference?: WeightSelection) {
  if (!draft.enabled) return null
  if (!draft.types.length) throw new Error(t("请至少选择一种研究对象类型。"))
  if (draft.modules && !draft.modules.length) throw new Error(t("请至少选择一个研究模块。"))
  const disciplines = draft.disciplines.split(/[,，]/).map(s => s.trim()).filter(Boolean)
  if (!disciplines.length) throw new Error(t("请填写至少一个学科。"))
  if (!draft.startDate || !draft.endDate || draft.startDate > draft.endDate) throw new Error(t("请填写有效的研究起止日期。"))
  const entities = draft.entities.map((entity, index) => {
    if (!entity.name.trim()) throw new Error(t("请填写对象 {0} 的名称。", index + 1))
    if (!draft.types.includes(entity.type)) throw new Error(t("对象 {0} 的类型不在当前选择范围内。", index + 1))
    let source: URL
    try { source = new URL(entity.source) } catch { throw new Error(t("请填写对象 {0} 的完整来源网址。", index + 1)) }
    if (!['http:', 'https:'].includes(source.protocol)) throw new Error(t("来源网址须使用 HTTP 或 HTTPS。"))
    return { entity_id: `selected-${index + 1}`, name: entity.name.trim(), type: entity.type,
      aliases: [], source_urls: [source.href], resolution_status: 'pending' }
  })
  if (preference?.error) throw new Error(preference.error)
  const corpus = corpusRequest(draft.corpus)
  return { action_requirements:actionRequirementsRequest(draft.actionRequirements), taxonomy: taxonomyRequest(draft.taxonomy), purpose: draft.purpose || 'research_development', ...(draft.modules ? { modules: draft.modules } : {}), ...(corpus ? { corpus } : {}), scope: { organization_types: draft.types, entities, disciplines, topic,
    start_date: draft.startDate, end_date: draft.endDate }, ...(preference?.reference ? { weight_preset: preference.reference } : preference?.configuration?{ weights: preference.configuration }:{}) }
}

export default function OrganizationResearchPanel({ value, onChange }: { value: OrganizationDraft; onChange: (value: OrganizationDraft) => void }) {
  useLocale()

  const updateEntity = (index: number, patch: Partial<OrganizationDraft['entities'][number]>) =>
    onChange({ ...value, entities: value.entities.map((entity, i) => i === index ? { ...entity, ...patch } : entity) })
  return <section className="mt-4 rounded-2xl border border-xmgray-200 bg-white p-4 text-left">
    <label className="flex items-center gap-2 text-sm font-medium text-xmgray-800">
      <input type="checkbox" className="accent-orange-500" checked={value.enabled} onChange={e => onChange({ ...value, enabled: e.target.checked })} />{t("组织研究模式")}</label>
    <p className="mt-2 text-xs leading-5 text-xmgray-500">{t("按对象分别研究、比较与汇总。信息渠道在下方独立选择。")}</p>
    {value.enabled && <div className="mt-4 space-y-4">
      <AnalysisPurposePanel purpose={value.purpose} modules={value.modules} onChange={(purpose, modules) => onChange({ ...value, purpose, modules })} />
      <CorpusPanel value={value.corpus} onChange={corpus => onChange({ ...value, corpus })} />
      <TaxonomyEditor value={value.taxonomy} onChange={taxonomy => onChange({ ...value, taxonomy })} />
      {value.modules?.includes('actions') && <ActionRequirementsPanel value={value.actionRequirements} onChange={actionRequirements=>onChange({...value,actionRequirements})}/>}
      <fieldset><legend className="mb-2 text-xs text-xmgray-600">{t("研究对象类型（可多选）")}</legend>
        <div className="flex flex-wrap gap-5">{(Object.keys(labels) as OrganizationType[]).map(type =>
          <label key={type} className="flex items-center gap-2 text-sm text-xmgray-700"><input type="checkbox" className="accent-orange-500" checked={value.types.includes(type)} onChange={e => onChange({ ...value, types: e.target.checked ? [...value.types, type] : value.types.filter(item => item !== type) })} />{labels[type]}</label>)}</div>
      </fieldset>
      <label className="block text-xs text-xmgray-600">{t("学科（逗号分隔）")}<input className="input-xm mt-1 text-sm" value={value.disciplines} onChange={e => onChange({ ...value, disciplines: e.target.value })} placeholder={t("例如：computer_science, materials_science")} /></label>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="text-xs text-xmgray-600">{t("研究开始日期")}<input className="input-xm mt-1 text-sm" type="date" value={value.startDate} onChange={e => onChange({ ...value, startDate: e.target.value })} /></label>
        <label className="text-xs text-xmgray-600">{t("研究截止日期")}<input className="input-xm mt-1 text-sm" type="date" value={value.endDate} onChange={e => onChange({ ...value, endDate: e.target.value })} /></label>
      </div>
      <div className="space-y-3">{value.entities.map((entity, index) => <fieldset key={index} className="rounded-xl bg-xmgray-50 p-3">
        <legend className="text-xs text-xmgray-600">{t("对象 ")}{index + 1}</legend>
        <div className="grid gap-2 sm:grid-cols-2">
          <label className="text-xs text-xmgray-600">{t("名称")}<input aria-label={t("对象 {0} 名称", index + 1)} className="input-xm mt-1 text-sm" value={entity.name} onChange={e => updateEntity(index, { name: e.target.value })} maxLength={300} /></label>
          <label className="text-xs text-xmgray-600">{t("类型")}<select aria-label={t("对象 {0} 类型", index + 1)} className="input-xm mt-1 text-sm" value={entity.type} onChange={e => updateEntity(index, { type: e.target.value as OrganizationType })}>{(Object.keys(labels) as OrganizationType[]).map(type => <option key={type} value={type}>{labels[type]}</option>)}</select></label>
        </div>
        <label className="mt-2 block text-xs text-xmgray-600">{t("来源网址")}<input aria-label={t("对象 {0} 来源", index + 1)} className="input-xm mt-1 text-sm" value={entity.source} onChange={e => updateEntity(index, { source: e.target.value })} placeholder="https://…" /></label>
        <button type="button" className="mt-2 text-xs text-xmgray-600 underline" onClick={() => onChange({ ...value, entities: value.entities.filter((_, i) => i !== index) })}>{t("移除对象 ")}{index + 1}</button>
      </fieldset>)}</div>
      <button type="button" className="btn-ghost text-sm" disabled={value.entities.length >= 200} onClick={() => onChange({ ...value, entities: [...value.entities, { name: '', type: value.types[0] || 'university', source: '' }] })}>{t("添加研究对象")}</button>
      <p className="text-xs leading-5 text-xmgray-500">{t("可添加一个或多个对象；留空按所选类型检索，候选实体仍需核实。名称及来源不自动证明成果归属。")}</p>
    </div>}
  </section>
}

