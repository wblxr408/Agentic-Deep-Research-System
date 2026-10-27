import {t,useLocale} from '../i18n'
import {stageNames} from './CollectionUI'
import {omissionReason,skillSelectionReason} from './SkillStagePlan'
import type {StageSkillPlan,StageSkillItem} from './SkillStagePlan'
import '../skill-stages.css'

type MethodEntry=StageSkillItem&{usage:string}
type MethodStage=Omit<StageSkillPlan,'entries'>&{entries:MethodEntry[]}
export interface MethodUsage {availability:string;stages:MethodStage[]}
function usageLabel(value:string){
 const labels:Record<string,string>={sent:'已随模型请求发送',delivery_unknown:'发送结果待确认',pending:'请求处理中',waiting:'尚未发送',not_sent:'本次未发送',
  no_model_content:'无需加载文字',legacy_unknown:'历史记录未保存',tool_policy_applied:'工具规则已应用',tool_without_model:'确定性工具'}
 return t(labels[value]||'暂无记录')
}
export default function SkillStageUsage({value}:{value:MethodUsage}){
 useLocale()
 return <details className="card p-5 skill-stage-usage"><summary>{t('阶段方法与工具')}</summary>
  {value.availability==='legacy_unknown'?<p>{t('这项研究没有保存阶段方法记录。')}</p>:!value.stages.length?<p>{t('本次没有选用阶段方法。')}</p>:<><p>{t('显示本次研究各次执行的记录。')}</p><div className="skill-stage-usage-grid">{value.stages.map(stage=><section key={stage.stage}>
   <h4>{stageNames[stage.stage]||stage.stage}</h4>{stage.entries.map(item=><div className="skill-stage-item" key={item.skill_id}><span>{item.name}</span><small>{skillSelectionReason(item)} · {usageLabel(item.usage)}</small></div>)}
   {stage.omitted.map(item=><div className="skill-stage-item is-omitted" key={`${item.skill_id}-${item.reason}`}><span>{item.name}</span><small>{omissionReason(item.reason)}</small></div>)}
  </section>)}</div></>}
 </details>
}
