import {useLocale,t,uiMessage} from '../i18n'
import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'

export type ResearchPurpose = 'research_development' | 'cooperation_discovery' | 'comprehensive'
export type ResearchModule = 'landscape' | 'evolution' | 'relationships' | 'deep_dive' | 'validation' | 'actions'
interface Catalogue {
  rule_version: string
  purposes: Array<{ id: ResearchPurpose; label: string; default_modules: ResearchModule[] }>
  modules: Array<{ id: ResearchModule; label: string; question: string }>
  capability_note: string
}
export default function AnalysisPurposePanel({ purpose = 'research_development', modules, onChange }: {
  purpose?: ResearchPurpose; modules?: ResearchModule[] | null
  onChange: (purpose: ResearchPurpose, modules: ResearchModule[]) => void
}) {
  useLocale()

  const catalogue = useQuery<Catalogue>({ queryKey: ['organization-analysis-catalogue'], queryFn: async () => {
    const response = await fetch('/api/v1/research/analysis/catalog')
    if (!response.ok) throw new Error(t("研究模块暂时无法加载，请稍后再试。"))
    return response.json()
  } })
  useEffect(() => {
    if (modules == null && catalogue.data) {
      const defaults = catalogue.data.purposes.find(item => item.id === purpose)
      if (defaults) onChange(purpose, defaults.default_modules)
    }
  }, [catalogue.data, purpose, modules, onChange])
  if (catalogue.error) return <p role="alert" className="text-sm text-red-700">{uiMessage(catalogue.error.message)}</p>
  if (!catalogue.data) return <p role="status" className="text-xs">{t("正在加载研究目的与模块…")}</p>
  const data = catalogue.data
  return <div className="space-y-3 rounded-xl bg-xmgray-50 p-3">
    <label className="block text-xs text-xmgray-600">{t("研究目的")}<select aria-label={t("研究目的")} className="input-xm mt-1 text-sm" value={purpose} onChange={event => {
        const next = data.purposes.find(item => item.id === event.target.value)
        if (next) onChange(next.id, next.default_modules)
      }}>{data.purposes.map(item => <option key={item.id} value={item.id}>{t(item.label)}</option>)}</select>
    </label>
    <fieldset><legend className="text-xs text-xmgray-600">{t("研究模块")}</legend>
      <div className="mt-2 grid gap-3 sm:grid-cols-2">{data.modules.map(item => <label key={item.id} className="text-sm text-xmgray-700">
        <span className="flex items-center gap-2"><input type="checkbox" aria-label={t("研究模块 {0}", t(item.label))} className="accent-orange-500" checked={!!modules?.includes(item.id)} onChange={event => onChange(purpose, event.target.checked ? [...(modules || []), item.id] : (modules || []).filter(key => key !== item.id))} />{t(item.label)}</span>
        <span className="mt-1 block text-xs leading-5 text-xmgray-500">{t(item.question)}</span>
      </label>)}</div>
    </fieldset>
    <p className="text-xs leading-5 text-xmgray-500">{t("更改目的会选用对应推荐模块，仍可逐项调整；至少选择一个。目的与模块独立于匹配权重和报告模板。")}</p>
    <p className="text-xs leading-5 text-xmgray-500">{t(data.capability_note)}</p>
  </div>
}
