import {t,uiMessage,useLocale,messageSource} from '../i18n'
import {useState} from 'react'
import type {ChoiceFieldsProps} from './ResearchChoiceFields'
import {FocusFields,ReportFields,ScopeFields,WeightChoices} from './ResearchChoiceFields'
import {SourceFields,ExtraFields} from './ResearchExtraFields'
import {setupRequest,setupSummary} from './researchSetup'
import type {ResearchSetup} from './researchSetup'
import {Icon} from './Interface'
import {layoutProblem} from './reportLayouts'

export type ChoiceSection='focus'|'scope'|'sources'|'report'|'more'
export function choiceProblem(value:ResearchSetup):{section:ChoiceSection;message:string}|null {
  const draft=value.queryDraft,org=value.organizationDraft
  const from=org.enabled?org.startDate:draft.startDate,to=org.enabled?org.endDate:draft.endDate
  if((from&&!to)||(!from&&to)||from&&to&&from>to)return {section:'scope',message:t("请填写完整的起止日期，开始日期应早于结束日期。")}
  if(org.enabled&&(!org.types.length||!org.disciplines.trim()))return {section:'scope',message:t("请选择对象类型和至少一个学科。")}
  if(org.enabled&&org.entities.some(entity=>!org.types.includes(entity.type)))return {section:'scope',message:t("有具体对象不在当前类型中，请调整类型或移除该对象。")}
  if(!draft.formats.length)return {section:'report',message:t("请至少选择一种下载形式。")}
  if(draft.layoutImportBusy)return {section:'report',message:t('请等待样例读取完成。')}
  if(draft.template==='custom'&&draft.layoutMode==='layout') {const problem=layoutProblem(draft.layout);if(problem)return {section:'report',message:problem}}
  else if(draft.template==='custom'&&(!draft.pages.length||draft.pages.some(page=>!page.title.trim())))return {section:'report',message:t("请为自定义报告填写章节标题。")}
  if(draft.drawingMode==='manual_skill'&&!draft.drawingSkillIds.length)return {section:'report',message:t("请选择一种绘图方法，或改用常规图表。")}
  const ranks=['public','internal','confidential','regulated']
  if(ranks.indexOf(draft.dataClass)>ranks.indexOf(draft.modelDataCeiling))return {section:'sources',message:t("模型可使用的资料类别应涵盖本次输入资料。")}
  let filter:Record<string,unknown>
  try{filter=JSON.parse(draft.internalFilter||'{"any_of":[]}');if(!filter||Array.isArray(filter))throw new Error()}catch{return {section:'sources',message:t("请重新选择资料筛选条件。")}}
  if(!value.useInternal&&(draft.internalRetrievalMode!=='hybrid'||(filter.any_of as unknown[])?.length))return {section:'sources',message:t("请打开“网络 + 我的资料”，或移除资料筛选。")}
  if(Array.isArray(filter.any_of)&&filter.any_of.some((group:any)=>!group.all_of?.length||group.all_of.some((rule:any)=>!['exists','missing'].includes(rule.op)&&(!rule.value||Array.isArray(rule.value)&&!rule.value.length))))return {section:'sources',message:t("请补全资料筛选条件，或移除这条条件。")}
  try{
    const fusion=JSON.parse(draft.candidateFusion||'{}')
    if(['per_route_top_k','global_top_k'].some(key=>fusion[key]!==undefined&&(!Number.isInteger(fusion[key])||fusion[key]<1||fusion[key]>100)))return {section:'more',message:t("资料保留数量应在 1—100 之间。")}
    if(Object.values(fusion.weights||{}).some(weight=>typeof weight!=='number'||weight<=0||weight>10))return {section:'more',message:t("各类资料的比重应大于 0，且不超过 10。")}
  }catch{return {section:'more',message:t("请重新选择检索结果的排列方式。")}}
  if(org.enabled&&org.taxonomy?.preset==='custom'){
    try{const nodes=JSON.parse(org.taxonomy.customText);if(!nodes.length||nodes.some((node:any)=>!node.label?.trim()||!node.terms?.length&&!nodes.some((child:any)=>child.parent_id===node.node_id)||node.terms?.some((term:string)=>term.trim().length<2)))return {section:'more',message:t("请填写类别名称；最细的类别至少需要一个两字以上的关键词。")}}catch{return {section:'more',message:t("请重新选择技术分类。")}}
  }
  for(const [number,min,max,label] of [[draft.maxParallel,1,8,t("同时查找的步骤数")],[draft.maxReplans,0,5,t("补充轮数")],[draft.maxQueryVariants,1,4,t("检索问法数量")],[draft.webCacheHours,0,8760,t("网页重新读取时间")],[draft.maxAgeHours,1,8760,t("资料更新时间")]] as Array<[number,number,number,string]>)if(!Number.isInteger(number)||number<min||number>max)return {section:'more',message:t("{0}应在 {1}—{2} 之间。", label, min, max)}
  if(org.enabled&&org.actionRequirements){
    try{const conditions=JSON.parse(org.actionRequirements.metricConditions||'[]');if(!Array.isArray(conditions)||conditions.some((item:any)=>!item.scheme_id||(!item.allowed_values?.length&&item.minimum==null)))return {section:'more',message:t("请补全成果要求的范围或最低数值，也可以移除这条要求。")}}catch{return {section:'more',message:t("请重新选择成果要求。")}}
  }
  try{setupRequest(value)}catch(error){const message=error instanceof Error?uiMessage(error.message):t("请检查当前选择。"),reason=messageSource(message);return {section:/分析模块|研究目标/.test(reason)?'focus':/对象|学科|日期|权重|评价|评分/.test(reason)?'scope':/资料|网站|域名|网址|文档/.test(reason)?'sources':/绘图|页面|章节|格式|下载|报告/.test(reason)?'report':'more',message}}
  return null
}
export default function ResearchOptionsEditor({value,onChange,skills,initial='focus',onApply,onCancel}:{value:ResearchSetup;onChange:(value:ResearchSetup)=>void;skills:ChoiceFieldsProps['skills'];initial?:ChoiceSection;onApply:()=>void;onCancel:()=>void}) {
  useLocale()

  const [active,setActive]=useState<ChoiceSection>(initial),[error,setError]=useState(''),summary=setupSummary(value)
  const sections:Array<{id:ChoiceSection;name:string;summary:string;icon:string}>=
    [{id:'focus',name:t("研究重点"),summary:summary.focus+' · '+summary.depth,icon:'target'},
      {id:'scope',name:t("研究范围"),summary:summary.scope+' · '+summary.time,icon:'search'},
      {id:'sources',name:t("资料与方法"),summary:summary.sources,icon:'book'},
      {id:'report',name:t("报告样式"),summary:summary.report,icon:'chart'},
      {id:'more',name:t("更多选择"),summary:t("检索、分类与研究安排"),icon:'settings'}]
  const fields={value,onChange:(next:ResearchSetup)=>{setError('');onChange(next)},skills}
  return <div className="research-choice-editor"><div className="choice-accordion">{sections.map(section=><section key={section.id} className={`choice-section ${active===section.id?'is-open':''}`} aria-label={t("{0}设置", section.name)}>
    <button type="button" className="choice-section-heading" disabled={!!value.queryDraft.layoutImportBusy&&section.id!=='report'} aria-expanded={active===section.id} onClick={()=>setActive(section.id)}><span className="choice-section-icon"><Icon name={section.icon} size={19}/></span><span><strong>{section.name}</strong><small>{section.summary}</small></span><Icon name={active===section.id?'minus':'plus'} size={15}/></button>
    {active===section.id&&<>{section.id==='focus'?<FocusFields {...fields}/>:section.id==='scope'?<><ScopeFields {...fields}/>{value.organizationDraft.enabled&&<details className="choice-weight-section"><summary>{t("调整匹配重点")}</summary><WeightChoices {...fields}/></details>}</>:section.id==='sources'?<SourceFields {...fields}/>:section.id==='report'?<ReportFields {...fields}/>:<ExtraFields {...fields}/>}</>}
  </section>)}</div>{error&&<p role="alert" className="choice-error">{uiMessage(error)}</p>}<div className="choice-footer"><span>{summary.depth} · {summary.report}</span><div><button type="button" className="btn-ghost" onClick={onCancel}>{t("取消")}</button><button type="button" className="btn-primary" disabled={!!value.queryDraft.layoutImportBusy} onClick={()=>{const problem=choiceProblem(value);if(problem){setActive(problem.section);setError(uiMessage(problem.message));return}onApply()}}>{t("应用选择")}<Icon name="check" size={16}/></button></div></div></div>
}
