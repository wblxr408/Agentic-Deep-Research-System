import {t,uiDefinition,useLocale} from '../i18n'

export interface BudgetAllocationEvent {
  phase:string;stage?:string;depth?:string;deep_reading_selected?:boolean;complexity?:string;specific_gap?:boolean
  root_remaining?:number;audit_hold?:number;report_hold?:number;stage_limit?:number;writing_available?:number|null
  version?:string;forecast_shortfall_tokens?:number;remaining_seconds?:number;remaining_tool_calls?:number
  previous_audit_hold?:number;previous_report_hold?:number
  demand?:{units:{analysis:number;writing:number;audit:number};estimated:boolean}
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
      {event.demand&&<>
        <p className="mt-1 text-xs">{t('按剩余工作调整：分析 {0}、写作或修订 {1}、审核 {2} 个预计批次',event.demand.units.analysis,event.demand.units.writing,event.demand.units.audit)}</p>
        {typeof event.previous_audit_hold==='number'&&<p className="mt-1 text-xs">{t('审核预留由 {0} 调整为 {1}，写作预留由 {2} 调整为 {3}',amount(event.previous_audit_hold),amount(event.audit_hold),amount(event.previous_report_hold),amount(event.report_hold))}</p>}
        <p className="mt-1 text-xs">{t('剩余 {0} 秒，工具调用余量 {1}',Math.floor(event.remaining_seconds??0),amount(event.remaining_tool_calls))}</p>
        <p className="mt-1 text-xs text-xmgray-500">{event.forecast_shortfall_tokens?t('预计交付资源缺口 {0} Token；保留已完成成果，需减少重复工作或明确调整范围、额度。审核要求不变。',amount(event.forecast_shortfall_tokens)):t('当前估算可容纳剩余必需工作；实际请求仍受总额度和期限限制，估算不代表质量通过。')}</p>
      </>}
    </article>)}</div>
  </details>
}
