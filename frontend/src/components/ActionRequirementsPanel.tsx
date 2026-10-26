import {t,uiDefinition,useLocale} from '../i18n'
export interface ActionRequirementsDraft {
  research_goal:string;cooperation_goal:string;offering:string;time_window:string
  constraints:string;required_relations:string[];metricConditions:string
}
export const defaultActionRequirements:ActionRequirementsDraft={research_goal:'',cooperation_goal:'',offering:'',time_window:'',constraints:'',required_relations:[],metricConditions:'[]'}
export function actionRequirementsRequest(value=defaultActionRequirements) {
  const text=(input:string)=>{const s=input.trim();if(s && s.length<3)throw new Error(t("行动需求请至少填写三个字符，或留空并保留待补状态。"));return s||null}
  let metrics:unknown[]
  try {metrics=JSON.parse(value.metricConditions)} catch {throw new Error(t("硬指标条件须为有效 JSON 数组。"))}
  if(!Array.isArray(metrics))throw new Error(t("硬指标条件须为 JSON 数组。"))
  return {research_goal:text(value.research_goal),cooperation_goal:text(value.cooperation_goal),offering:text(value.offering),time_window:text(value.time_window),
    constraints:value.constraints.split('\n').map(s=>s.trim()).filter(Boolean),required_relations:value.required_relations,required_metrics:metrics}
}
const relations:Record<string,string>=uiDefinition({coauthorship:'共著',funding:'资助',project:'项目',joint_lab:'联合实验室'})
export default function ActionRequirementsPanel({value=defaultActionRequirements,onChange}:{value?:ActionRequirementsDraft;onChange:(value:ActionRequirementsDraft)=>void}) {
  useLocale()

  return <fieldset className="mt-3 space-y-3 rounded-xl border border-xmgray-200 p-3"><legend className="text-sm font-medium">{t("行动需求与硬条件")}</legend>
    <p className="text-xs text-xmgray-500">{t("研究验证与合作需求分别填写。留空会显示待补条件；不能靠提高分数把未核关系变成已核实。")}</p>
    {([['research_goal',t("后续研究目标")],['cooperation_goal',t("合作需求")],['offering',t("可提供资源／互补能力")],['time_window',t("时间与可行性要求")]] as const).map(([key,label])=><label key={key} className="block text-xs">{label}<textarea aria-label={label} className="input-xm mt-1 min-h-16" value={value[key]} maxLength={1200} onChange={e=>onChange({...value,[key]:e.target.value})}/></label>)}
    <label className="block text-xs">{t("其他约束（逐行；可行性仍需核实）")}<textarea aria-label={t("行动其他约束")} className="input-xm mt-1 min-h-20" value={value.constraints} onChange={e=>onChange({...value,constraints:e.target.value})}/></label>
    <div><p className="text-xs">{t("要求已核实的关系（硬筛选）")}</p><div className="mt-2 flex flex-wrap gap-4">{Object.entries(relations).map(([id,label])=><label className="flex items-center gap-2 text-xs" key={id}><input type="checkbox" aria-label={t("要求已核实{0}", label)} checked={value.required_relations.includes(id)} onChange={e=>onChange({...value,required_relations:e.target.checked?[...value.required_relations,id]:value.required_relations.filter(key=>key!==id)})}/>{label}</label>)}</div></div>
    <details><summary className="cursor-pointer text-xs">{t("高级：硬指标条件")}</summary><p className="mt-2 text-xs text-xmgray-500">{t("复用评价条件 scheme_id，加 allowed_values 或 minimum；资料未核实则不能满足硬条件。")}</p><textarea aria-label={t("行动硬指标条件")} className="input-xm mt-2 min-h-24 font-mono text-xs" value={value.metricConditions} onChange={e=>onChange({...value,metricConditions:e.target.value})}/></details>
  </fieldset>
}
