import {t,uiDefinition,useLocale} from '../i18n'

export interface BudgetAllocationEvent {
  phase:string;stage?:string;depth?:string;deep_reading_selected?:boolean;complexity?:string;specific_gap?:boolean
  root_remaining?:number;audit_hold?:number;report_hold?:number;stage_limit?:number;writing_available?:number|null
}
const stages:Record<string,string>=uiDefinition({planner:'规划',analyst:'分析',reflection:'核对',replan:'补证规划',report:'写作与审核'})
const depths:Record<string,string>=uiDefinition({brief:'简要',standard:'标准',deep:'深入'})
const amount=(value:number|undefined)=>typeof value==='number'?value.toLocaleString():'—'

export default function BudgetAllocation({events}:{events:BudgetAllocationEvent[]}) {
  useLocale()
  const allocations=events.filter(event=>event.phase==='stage_allocation')
  if(!allocations.length)return null
  return <details className="card p-5 text-sm"><summary className="cursor-pointer font-medium">{t('阶段额度安排')}</summary>
    <div className="mt-3 space-y-3">{allocations.map((event,index)=><article key={index} className="rounded-lg border border-xmgray-200 p-3">
      <p className="font-medium">{stages[event.stage||'']||t('研究阶段')} · {depths[event.depth||'']||t('标准')}</p>
      <p className="mt-1 text-xs text-xmgray-500">{t('当时剩余 {0} Token',amount(event.root_remaining))} · {t('审核预留 {0}',amount(event.audit_hold))} · {event.stage==='report'?t('写作可用 {0}',amount(event.writing_available??undefined)):t('报告预留 {0}',amount(event.report_hold))}</p>
      {event.stage!=='report'&&<p className="mt-1 text-xs text-xmgray-500">{t('本阶段上限 {0}',amount(event.stage_limit))}</p>}
      {event.stage==='replan'&&event.specific_gap&&<p className="mt-1 text-xs text-xmgray-500">{t('根据具体缺口调整额外预留')}</p>}
    </article>)}</div>
  </details>
}
