import {uiDefinition,useLocale,t,uiMessage} from '../i18n'
export interface PlanSummaryProps {
  status?: string
  plan?: { revision: number; strategy: string; reason: string; plan_version: string
    steps: Array<{ node_id: string; node_type?: string; purpose: string; query: string; depends_on: string[]; condition: string; parallel: boolean }>
    adjustments?: Array<{ node_id?: string; reason: string }> } | null
  dag?: { nodes: Array<{ node_id: string; status: string; last_error?: string | null; last_error_category?: string | null; waiting_approval?: boolean }> }
  history?: Array<{ plan_version: string; revision: number; reason: string; strategy: string }>
  control?: { action: string; reason: string; no_gain_rounds: number; revision_count: number; revision_limit: number; gap_reasons: string[] } | null
  failure?: {category:string;error_type:string;message:string;at:string;checkpoint_seq:number;interrupted_batch?:string[];analysis_status?:string|null}|null
  operationalEvents?: Array<{message:string;error_type:string;at:string;effect:string}>
}
const reasons:Record<string,string>=uiDefinition({single_pass_selected:'按选择完成单轮研究',revision_limit:'已到补证轮次上限',no_new_retained_material:'连续补证未保留新材料',
  initial_discovery_then_source_reading:'先检索原问题、成果与团队，再沿来源读取正文',read_retained_public_sources_before_analysis:'沿已保留线索读取正文',
  no_requested_revision_not_a_truth_certificate:'本轮核对结束',specific_evidence_gap:'有具体证据缺口，继续有限补证',
  no_structured_evidence_gap_manual_review_available:'没有可执行的结构化补证问题，保留人工复核入口',human_authorization_required:'等待所需操作审批',
  no_accessible_evidence:'没有可用于报告的授权证据',tool_not_allowed:'当前工具未获许可',condition_not_met:'分支条件不满足',dependency_failed:'前置步骤失败',
  mcp_serial_until_trusted_resource_independence_is_declared:'该工具请求按串行执行',synthesis_review_and_rendering_owned_by_root_workflow:'综合、审核与交付由根流程执行'})
export default function ResearchPlanSummary({plan,dag,history,control,status,failure,operationalEvents}:PlanSummaryProps) {
  useLocale()

  if(!plan&&!dag?.nodes?.length&&!control&&!failure&&!operationalEvents?.length)return null
  const live=new Map((dag?.nodes||[]).map(node=>[node.node_id,node]))
  const labels:Record<string,string>={pending:t("等待"),running:t("执行中"),done:t("完成"),failed:t("失败"),skipped:t("跳过")}
  return <section className="card p-4 text-sm space-y-2" aria-label={t("研究计划与执行状态")}>
    <h3 className="font-medium">{t("研究计划 · ")}{({fixed:t("固定"),hybrid:t("混合"),dynamic:t("动态")} as Record<string,string>)[plan?.strategy||'']||t("历史任务")}</h3>
    {failure&&status==='failed'&&<div role="alert" className="rounded bg-amber-50 p-3">
      <p>{t("研究执行中断：")}{uiMessage(failure.message)||failure.category}</p>
      {!!failure.interrupted_batch?.length&&<p>{t("中断步骤：")}{failure.interrupted_batch.join('、')}</p>}
      <p className="text-xs">{t("最后保存进度：")}{failure.checkpoint_seq} · {failure.at} · {failure.error_type}</p>
      <p className="text-xs">{t("材料、分析与用量已保存。")}</p>
    </div>}
    {!!operationalEvents?.length&&<details><summary>{t("运行通知（")}{operationalEvents.length}）</summary>
      <p className="text-xs">{t("研究结果已保存，以下事件保留在运行记录中。")}</p>
      {operationalEvents.map((event,index)=><p key={index} className="text-xs break-words">{event.at} · {event.error_type} · {event.message}</p>)}
    </details>}
    {plan&&<p className="text-xs break-all">{t("第")}{plan.revision}{t("版：")}{plan.reason} · {plan.plan_version}</p>}
    <ol className="space-y-2">{(plan?.steps||dag?.nodes?.map(node=>({node_id:node.node_id,purpose:node.node_id,query:'',depends_on:[],condition:'always',parallel:false}))||[]).map(step=>{
      const current=live.get(step.node_id)
      const rootStage='node_type' in step&&step.node_type==='analyst'
      return <li key={step.node_id} className="rounded border border-xmgray-100 p-2"><p>{step.purpose} · {['canceled','failed'].includes(status||'')&&(!current||['pending','running'].includes(current.status))?(status==='canceled'?t("任务已取消，保留最后步骤记录"):t("执行已中断，保留最后步骤记录")):rootStage?(status==='completed'?t("根流程已交付报告"):t("由根流程在取证后执行")):current?labels[current.status]||current.status:t("未取得实时状态")}</p>
        <p className="break-words text-xs">{step.query}</p>
        <p className="text-xs text-xmgray-500">{step.depends_on.length?t("前置：{0}", step.depends_on.join('、')):t("无前置步骤")} · {step.parallel?t("允许有界并行"):t("串行")}{step.condition!=='always'&&t(" · 条件：{0}", step.condition)}</p>
        {current?.last_error_category&&<p className="text-xs text-amber-800">{reasons[current.last_error_category]||current.last_error_category}：{current.last_error}</p>}
      </li>
    })}</ol>
    {!!plan?.adjustments?.length&&<details><summary>{t("计划调整及约束原因")}</summary>{plan.adjustments.map((item,index)=><p key={index}>{item.node_id} · {reasons[item.reason]||item.reason}</p>)}</details>}
    {control&&<p className="rounded bg-xmgray-50 p-3">{control.action==='replan'?t("继续补证"):control.action==='pause'?t("等待处理"):t("本轮停止")}：{reasons[control.reason]||control.reason}{t("。已补证")}{control.revision_count}/{control.revision_limit}{t("轮；无新材料")}{control.no_gain_rounds}{t("轮。")}</p>}
    {!!history?.length&&<details><summary>{t("计划历史（")}{history.length}{t("版）")}</summary>{history.map(item=><p key={item.plan_version}>{t("第")}{item.revision}{t("版 · ")}{item.strategy} · {item.reason}</p>)}</details>}
  </section>
}
