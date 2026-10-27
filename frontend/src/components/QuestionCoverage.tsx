import {t,uiDefinition,useLocale} from '../i18n'
import {safeExternalUrl} from './Interface'

type Anchor={evidence_id:string;source_title:string;source_url:string;quote:string;quote_truncated:boolean;pages:number[];start:number;end:number}
type Claim={claim_id:string;text:string;assessment:string;source_anchors:Anchor[]}
type Paragraph={text:string;kind:string;claims:Claim[];assessment:string}
type TechnicalCard={output_id:string;title:string;full_text_available:boolean|null;fields:Array<{field:string;label:string;text:string|null;status:string;source_anchors:Anchor[]}>;figure_references:Array<{label:string;page:number|null;source_anchor:Anchor}>}
type Trend={trend_id:string;kind:string;statement:string;source_status:string;source_anchors:Anchor[];opposing_status:string;opposing_anchors:Anchor[];alternative_explanations:string[];conditions:string[];horizon_start:string|null;horizon_end:string|null}
type Action={action_id:string;entity_name:string;mode:string;status:string;question:string|null;steps:string[];source_status:string;source_anchors:Anchor[];missing_requirements:string[];public_contacts:Array<{url:string}>}
type Module={module_id:string;module_label:string;status:string;paragraphs:Paragraph[];unmapped_paragraphs:number;materials:null|{available:boolean;cards?:TechnicalCard[]|Action[];records?:Trend[];pending_count?:number}}
export interface QuestionCoverageData {research_question:string;question_structure:string;report_binding_current:boolean;summary:{paragraphs:Paragraph[];unmapped_paragraphs:number};modules:Module[];unassigned_trends:Trend[]}

const assessments:Record<string,string>=uiDefinition({model_source_supported:'模型认为原文支持',model_task_method_supported:'依据本次任务设置',contradicted:'与来源存在冲突',unverifiable:'尚未能确认',missing_citation:'缺少引用',invalid_citation:'引用无效',not_checked:'尚未核对',unavailable:'审核记录不可用'})
const moduleStates:Record<string,string>=uiDefinition({recorded:'已有报告内容',unknown:'尚无可关联的报告',missing:'尚无报告内容',unmapped:'段落无法唯一关联'})
const trendKinds:Record<string,string>=uiDefinition({observation:'观察',inference:'推断',scenario:'情景'})
const requirements:Record<string,string>=uiDefinition({cooperation_goal:'合作目标',offering:'可提供资源',time_window:'时间要求',research_goal:'研究目标'})
const actionStates:Record<string,string>=uiDefinition({needs_requirements:'需求待补',hard_conditions_not_established:'条件尚未确认',needs_source_grounded_action:'议题缺少依据',conditional_research_route:'研究路线',needs_feasibility_and_contact_review:'待确认合作可行性'})

function Sources({anchors}:{anchors:Anchor[]}) {
  if(!anchors.length)return null
  return <ul className="mt-2 space-y-2">{anchors.map((anchor,index)=>{
    const link=safeExternalUrl(anchor.source_url)
    return <li key={`${anchor.evidence_id}-${anchor.start}-${index}`} className="break-words text-xs text-xmgray-500">
      {link?<a className="underline" href={link} target="_blank" rel="noopener noreferrer">{anchor.source_title||t('查看来源')}</a>:<span>{anchor.source_title||t('资料')}</span>}
      {!!anchor.pages.length&&<> · {t('第 {0} 页',anchor.pages.join(', '))}</>}
      <blockquote className="mt-1 border-l-2 border-xmgray-200 pl-2">{anchor.quote}{anchor.quote_truncated?'…':''}</blockquote>
    </li>
  })}</ul>
}

function Paragraphs({items}:{items:Paragraph[]}) {
  return <div className="space-y-3">{items.map((paragraph,index)=><article key={index}>
    <p className="whitespace-pre-wrap">{paragraph.text}</p>
    {!!paragraph.claims.length&&<details className="mt-2 text-xs"><summary className="cursor-pointer">{t('查看判断与依据')}</summary>
      <div className="space-y-3 pt-2">{paragraph.claims.map((claim,position)=><div key={claim.claim_id||position}>
        <p>{claim.text}</p><p className="mt-1 text-xmgray-500">{assessments[claim.assessment]||t('审核记录不可用')}</p>
        <Sources anchors={claim.source_anchors}/>
      </div>)}</div></details>}
    {!paragraph.claims.length&&<p className="mt-1 text-xs text-xmgray-500">{t('尚无对应的逐句核对记录')}</p>}
  </article>)}</div>
}

function Technical({cards}:{cards:TechnicalCard[]}) {
  if(!cards.length)return <p className="text-xs text-xmgray-500">{t('尚无可关联的成果深读')}</p>
  return <div className="space-y-3">{cards.map((card,index)=><details key={card.output_id||index} className="rounded-lg border border-xmgray-200 p-3">
    <summary className="cursor-pointer font-medium">{card.title||t('未命名成果')} · {card.full_text_available===true?t('已取得全文'):card.full_text_available===false?t('全文未取得'):t('全文状态未知')}</summary>
    <div className="space-y-2 pt-3">{card.fields.filter(field=>field.text).map(field=><div key={field.field}>
      <p className="text-xs font-medium">{t(field.label)} · {field.status==='located'?t('已定位原文'):t('原文位置不可用')}</p>
      <p className="mt-1">{field.text}</p><Sources anchors={field.source_anchors}/>
    </div>)}</div>
    {card.fields.some(field=>field.text&&field.status!=='located')&&<p className="mt-3 text-xs text-xmgray-500">{t('待补依据：')}{card.fields.filter(field=>field.text&&field.status!=='located').map(field=>t(field.label)).join('、')}</p>}
    {card.fields.some(field=>!field.text)&&<details className="mt-2 text-xs text-xmgray-500"><summary className="cursor-pointer">{t('未记录的项目')}</summary><p className="mt-1">{card.fields.filter(field=>!field.text).map(field=>t(field.label)).join('、')}</p></details>}
    {!!card.figure_references.length&&<details className="mt-3 text-xs"><summary className="cursor-pointer">{t('原文图表位置')}</summary>{card.figure_references.map((figure,i)=><div className="mt-2" key={i}><p>{figure.label}</p><Sources anchors={[figure.source_anchor]}/></div>)}</details>}
  </details>)}</div>
}

function Trends({records}:{records:Trend[]}) {
  if(!records.length)return <p className="text-xs text-xmgray-500">{t('尚无可关联的演进材料')}</p>
  return <div className="space-y-3">{records.map((record,index)=><article key={record.trend_id||index} className="rounded-lg border border-xmgray-200 p-3">
    <p className="text-xs text-xmgray-500">{trendKinds[record.kind]||t('研究材料')} · {record.source_status==='located'?t('已定位原文'):t('原文位置不可用')}</p>
    <p className="mt-1">{record.statement}</p><Sources anchors={record.source_anchors}/>
    {record.opposing_anchors.length>0&&<div className="mt-2"><p className="text-xs font-medium">{t('反向材料')}</p><Sources anchors={record.opposing_anchors}/></div>}
    {record.opposing_status==='not_recorded'&&<p className="mt-2 text-xs text-xmgray-500">{t('未记录反向材料')}</p>}
    {record.opposing_status==='unknown'&&<p className="mt-2 text-xs text-xmgray-500">{t('反向材料位置不可用')}</p>}
    {!!record.alternative_explanations.length&&<p className="mt-2 text-xs">{t('其他可能解释：')}{record.alternative_explanations.join('；')}</p>}
    {!!record.conditions.length&&<p className="mt-1 text-xs">{t('条件：')}{record.conditions.join('；')}</p>}
    {record.horizon_start&&record.horizon_end&&<p className="mt-1 text-xs">{t('时间范围：')}{record.horizon_start}–{record.horizon_end}</p>}
  </article>)}</div>
}

function Actions({cards}:{cards:Action[]}) {
  if(!cards.length)return <p className="text-xs text-xmgray-500">{t('尚无可关联的行动建议')}</p>
  return <div className="space-y-3">{cards.map((card,index)=><article key={card.action_id||index} className="rounded-lg border border-xmgray-200 p-3">
    <p className="font-medium">{card.entity_name} · {card.mode==='cooperation'?t('合作机会'):t('研究验证')}</p>
    {actionStates[card.status]&&<p className="mt-1 text-xs text-xmgray-500">{actionStates[card.status]}</p>}
    <p className="mt-1">{card.question||t('尚无具体议题')}</p>
    {!!card.steps.length&&<ol className="mt-2 list-decimal space-y-1 pl-5">{card.steps.map((step,i)=><li key={i}>{step}</li>)}</ol>}
    {card.question&&!card.steps.length&&<p className="mt-2 text-xs text-xmgray-500">{t('尚无具体步骤')}</p>}
    {!!card.missing_requirements.length&&<p className="mt-2 text-xs text-xmgray-500">{t('待补条件：')}{card.missing_requirements.map(key=>requirements[key]||key).join('、')}</p>}
    <p className="mt-2 text-xs text-xmgray-500">{card.source_status==='located'?t('建议依据已定位'):t('建议依据尚未定位')}</p><Sources anchors={card.source_anchors}/>
    {card.public_contacts.map((contact,i)=>{const link=safeExternalUrl(contact.url);return link?<p className="mt-2 text-xs" key={i}><a className="underline" href={link} target="_blank" rel="noopener noreferrer">{t('公开联系入口')}</a></p>:null})}
  </article>)}</div>
}

export default function QuestionCoverage({value}:{value:QuestionCoverageData}) {
  useLocale()
  return <section className="my-4 space-y-4 rounded-xl border border-xmgray-200 p-4" aria-label={t('按问题查看研究依据')}>
    <div><h3 className="font-semibold">{t('按问题查看研究依据')}</h3><p className="mt-1 whitespace-pre-wrap">{value.research_question}</p></div>
    {value.summary.paragraphs.length>0&&<details><summary className="cursor-pointer font-medium">{t('核心判断')}</summary><div className="pt-3"><Paragraphs items={value.summary.paragraphs}/></div></details>}
    {value.question_structure==='unavailable_for_legacy_or_general_task'&&<p className="text-xs text-xmgray-500">{t('这项研究没有保存可关联的问题模块。')}</p>}
    {value.modules.map(module=><details key={module.module_id} className="rounded-lg border border-xmgray-200 p-3">
      <summary className="cursor-pointer font-medium">{t(module.module_label)} <span className="ml-2 text-xs font-normal text-xmgray-500">{moduleStates[module.status]||t('暂无记录')}</span></summary>
      <div className="space-y-4 pt-3">
        {module.paragraphs.length>0&&<Paragraphs items={module.paragraphs}/>}
        {module.unmapped_paragraphs>0&&<p className="text-xs text-xmgray-500">{t('{0} 段内容无法唯一关联',module.unmapped_paragraphs)}</p>}
        {module.module_id==='deep_dive'&&<div><h4 className="mb-2 text-xs font-medium">{t('成果深读')}</h4><Technical cards={(module.materials?.cards||[]) as TechnicalCard[]}/></div>}
        {(module.module_id==='evolution'||module.module_id==='validation')&&<div><h4 className="mb-2 text-xs font-medium">{t('演进与交叉材料')}</h4><Trends records={module.materials?.records||[]}/></div>}
        {module.module_id==='actions'&&<div><h4 className="mb-2 text-xs font-medium">{t('具体行动')}</h4><Actions cards={(module.materials?.cards||[]) as Action[]}/></div>}
      </div>
    </details>)}
    {!!value.unassigned_trends.length&&<details><summary className="cursor-pointer">{t('其他演进材料')}</summary><div className="pt-3"><Trends records={value.unassigned_trends}/></div></details>}
  </section>
}
