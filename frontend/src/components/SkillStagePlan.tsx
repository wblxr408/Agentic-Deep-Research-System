import {t,useLocale} from '../i18n'
import {stageNames} from './CollectionUI'
import '../skill-stages.css'

export interface StageSkillItem {skill_id:string;name:string;version:number;activation:string;matched_reason?:string|null}
export interface StageSkillOmission {skill_id:string;name:string;version?:number;reason:string}
export interface StageSkillPlan {stage:string;entries:StageSkillItem[];omitted:StageSkillOmission[];ready:boolean}

export function skillSelectionReason(item:StageSkillItem){
 if(item.activation==='explicit_user_selection')return t('你选择的方法')
 const reason=item.matched_reason||''
 if(reason.startsWith('keyword:'))return t('匹配话题：{0}',reason.slice(8))
 if(reason.startsWith('term:'))return t('匹配 {0} 个话题',reason.slice(5))
 return t('匹配研究问题')
}
export function omissionReason(reason:string){
 const labels:Record<string,string>={different_template:'与所选报告样式不符',discipline_not_matched:'与研究领域不符',discipline_not_declared:'缺少适用领域',
  automatic_skill_invalid:'方法内容需要修正',automatic_reference_missing:'缺少方法参考内容',automatic_conflicts_with_required_tools:'与已选方法所需工具冲突',
  automatic_disables_stage_tool:'会限制当前步骤所需工具',automatic_context_budget:'本阶段方法空间不足'}
 return t(labels[reason]||'不适用于当前步骤')
}
export default function SkillStagePlan({stages}:{stages:StageSkillPlan[]}){
 useLocale()
 if(!stages.length)return null
 return <details className="skill-stage-plan"><summary>{t('研究方法安排')}</summary><p>{t('以下是各步骤的准备情况。')}</p><div>{stages.map(stage=><section key={stage.stage}>
  <h4>{stageNames[stage.stage]||stage.stage}</h4>
  {stage.entries.map(item=><div className="skill-stage-item" key={item.skill_id}><span>{item.name}</span><small>{skillSelectionReason(item)}</small></div>)}
  {stage.omitted.map(item=><div className="skill-stage-item is-omitted" key={`${item.skill_id}-${item.reason}`}><span>{item.name}</span><small>{omissionReason(item.reason)}</small></div>)}
 </section>)}</div></details>
}
