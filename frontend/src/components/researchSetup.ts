import {uiDefinition,t,joinLabels} from '../i18n'
import {defaultQueryDraft,deliveryDraftRequest,queryDraftRequest} from './QueryUnderstandingPanel'
import type {QueryDraft} from './QueryUnderstandingPanel'
import type {ReportLayout} from './reportLayouts'
import {defaultOrganizationDraft,organizationRequest} from './OrganizationResearchPanel'
import type {OrganizationDraft,OrganizationType} from './OrganizationResearchPanel'
import type {WeightSelection} from './OrganizationWeightsPanel'
import type {ResearchLimits} from './ResearchBudgetPicker'

export interface ResearchSetup {
  budgetLimits?:ResearchLimits
  query:string;queryDraft:QueryDraft;organizationDraft:OrganizationDraft;weights?:WeightSelection
  outputLength:'short'|'medium'|'long';useInternal:boolean;group:string;channels:string[];enabled:string[];disabled:string[]
  previewSessionId?:string
  ownerId?:string
  operationScopeId?:string
  original?:Record<string,unknown>
}
export const disciplineNames:Record<string,string>=uiDefinition({computer_science:'计算机科学',materials_science:'材料科学',electrical_engineering:'电子与电气',mechanical_engineering:'机械工程',physics:'物理学',chemistry:'化学',biology:'生命科学',medicine:'医学',mathematics:'数学',environmental_science:'环境科学',business:'商科',economics:'经济学',multidisciplinary:'跨学科'})
export const moduleNames:Record<string,string>=uiDefinition({landscape:'研究全景',evolution:'近年演进',relationships:'团队与合作',deep_dive:'关键技术',validation:'来源核对',actions:'合作建议'})
export const purposeNames:Record<string,string>=uiDefinition({research_development:'了解布局与演进',cooperation_discovery:'寻找合作机会',comprehensive:'综合研究'})
export const depthNames:Record<string,string>=uiDefinition({auto:'按问题选择',brief:'快速了解',standard:'标准研究',deep:'深入研究'})
export const templateChoices=uiDefinition([
  {id:'markdown-v1',name:'简洁长文',description:'结论与分析，清楚展开',kind:'text'},
  {id:'visual-brief-v1',name:'图文简报',description:'重点图表与简短判断',kind:'brief'},
  {id:'technology-comparison-v1',name:'技术对比',description:'方案、条件和差异',kind:'comparison'},
  {id:'research-map-v1',name:'研究脉络',description:'团队关系与技术演进',kind:'network'},
  {id:'organization-development-v1',name:'机构研究',description:'布局、成果与重点团队',kind:'organization'},
  {id:'cooperation-matching-v1',name:'合作资源',description:'团队、课题与合作切入点',kind:'network'},
  {id:'field-trends-v1',name:'领域趋势',description:'研究方向与时间变化',kind:'trend'},
  {id:'custom',name:'自定义',description:'自己安排章节与配图',kind:'custom'},
])
export const templateName=(id:string)=>templateChoices.find(item=>item.id===id)?.name||t("已保存的样式")
export const splitValues=(value:string)=>value.split(/[,，\n]/).map(item=>item.trim()).filter(Boolean)
export function setupSummary(value:ResearchSetup) {
  const organization=value.organizationDraft,draft=value.queryDraft
  const types=organization.enabled?joinLabels(organization.types.map(type=>({company:t("企业"),university:t("高校"),laboratory:t("实验室")})[type])):t("围绕问题")
  const from=organization.enabled?organization.startDate:draft.startDate,to=organization.enabled?organization.endDate:draft.endDate
  return {focus:purposeNames[organization.enabled?organization.purpose||'research_development':draft.purpose]||t("按问题研究"),
    scope:types,time:from&&to?`${from.slice(0,4)}—${to.slice(0,4)}`:t("按问题确定"),
    depth:depthNames[draft.depth]||t("按问题选择"),report:templateName(draft.template),sources:value.useInternal?t("公开网络 + 我的资料"):t("公开网络"),
    methods:value.enabled.length||value.disabled.length?t("已调整研究方法"):t("自动匹配")}
}
export function chooseDepth(value:ResearchSetup,depth:string):ResearchSetup {
  return {...value,queryDraft:{...value.queryDraft,depth},outputLength:depth==='brief'?'short':depth==='deep'?'long':'medium'}
}
export function choosePeriod(value:ResearchSetup,years:number|'question'):ResearchSetup {
  if(years==='question')return {...value,queryDraft:{...value.queryDraft,startDate:'',endDate:'',timeMode:'auto',preferStructuredTime:false}}
  const today=new Date(),end=today.toISOString().slice(0,10),start=new Date(Date.UTC(today.getUTCFullYear()-years,today.getUTCMonth(),today.getUTCDate())).toISOString().slice(0,10)
  return {...value,organizationDraft:{...value.organizationDraft,startDate:start,endDate:end},
    queryDraft:{...value.queryDraft,startDate:start,endDate:end,preferStructuredTime:true}}
}
const object=(value:unknown):Record<string,any>=>value&&typeof value==='object'&&!Array.isArray(value)?value as Record<string,any>:{}
const strings=(value:unknown):string[]=>Array.isArray(value)?value.filter((item):item is string=>typeof item==='string'):[]
export function setupFromRequest(parameters:Record<string,unknown>={},query='',previewSessionId?:string,ownerId?:string,operationScopeId?:string):ResearchSetup {
  const q=object(parameters.query_options),delivery=object(parameters.delivery),policy=object(parameters.planning_policy)
  const org=object(parameters.organization_research),scope=object(org.scope),data=object(q.data_policy),corpus=object(org.corpus),taxonomy=object(org.taxonomy),action=object(org.action_requirements)
  const queryDraft:QueryDraft={...structuredClone(defaultQueryDraft),
    queryType:q.query_type||'',entityText:(q.entities||[]).map((item:any)=>`${item.name}${item.aliases?.length?' | '+item.aliases.join(', '):''}`).join('\n'),
    disciplines:strings(q.disciplines).join(','),contextSessionId:q.context_session_id||'',referenceIds:strings(q.reference_entity_ids),constraints:q.additional_constraints||'',
    timeMode:q.time_mode||'auto',referenceDate:q.reference_date||'',asOfDate:q.as_of_date||'',startDate:q.start_date||'',endDate:q.end_date||'',preferStructuredTime:!!q.prefer_structured_time,
    depth:q.depth||'auto',purpose:q.purpose||'',modules:q.modules??null,template:delivery.template||'markdown-v1',theme:delivery.theme||'plain-v1',
    pages:(delivery.pages||[]).map((page:any)=>({title:page.title||'',module:page.module||'',question:page.question||'',chart:page.chart_kind||'auto'})),
    drawingMode:delivery.drawing_mode||'builtin',drawingSkillIds:strings(delivery.drawing_skill_ids),chartSkillIds:delivery.chart_skill_ids||{},formats:delivery.formats||['markdown'],
    outputKind:delivery.output_kind||'auto',copiedFromTemplate:delivery.copied_from_template||null,
    layout:delivery.layout?structuredClone(delivery.layout) as ReportLayout:null,layoutMode:delivery.layout?'layout':'chapters',layoutSample:null,layoutSourceId:null,layoutName:'',layoutImportBusy:false,
    planningStrategy:policy.strategy||'hybrid',autonomy:policy.autonomy||'bounded',maxParallel:policy.max_parallel??3,maxReplans:policy.max_replans??1,
    termAliases:Object.entries(object(q.term_aliases)).map(([term,aliases])=>[term,...strings(aliases)].join(' | ')).join('\n'),maxQueryVariants:q.max_query_variants??2,
    internalFilter:JSON.stringify(q.internal_filter||{any_of:[]}),internalRetrievalMode:q.internal_retrieval_mode||'hybrid',internalChannels:strings(q.internal_channels),candidateFusion:JSON.stringify(q.candidate_fusion||{}),
    webCacheHours:q.web_cache_hours??24,maxAgeHours:q.max_age_hours??72,webReadMode:q.web_read_mode||'auto',
    dataClass:data.input_class||'public',modelDataCeiling:data.max_model_class||'internal',publicSearchQueries:strings(data.public_search_queries).join('\n')}
  const organizationDraft:OrganizationDraft={...structuredClone(defaultOrganizationDraft),enabled:!!parameters.organization_research,
    purpose:org.purpose||'research_development',modules:org.modules??null,types:scope.organization_types||[...defaultOrganizationDraft.types],
    disciplines:scope.disciplines?strings(scope.disciplines).join(','):defaultOrganizationDraft.disciplines,startDate:scope.start_date||defaultOrganizationDraft.startDate,endDate:scope.end_date||defaultOrganizationDraft.endDate,
    entities:(scope.entities||[]).map((entity:any)=>({name:entity.name,type:entity.type as OrganizationType,source:entity.source_urls?.[0]||''})),
    ...(org.corpus?{corpus:{enabled:!!(corpus.seed_urls?.length||corpus.search_terms?.length||corpus.output_types?.length||corpus.source_scope||corpus.allow_ocr||corpus.collection_mode==='seeds_only'),mode:corpus.collection_mode||'search_and_seeds',group:corpus.source_scope?.official_domains?.length?'official':'publishers',domains:(corpus.source_scope?.official_domains||corpus.source_scope?.publisher_domains||[]).join(','),seeds:strings(corpus.seed_urls).join('\n'),terms:strings(corpus.search_terms).join('\n'),outputTypes:strings(corpus.output_types).join(','),allowOcr:!!corpus.allow_ocr}}:{}),
    ...(org.taxonomy?{taxonomy:{preset:taxonomy.preset||'auto',version:taxonomy.version||'topic-policy-v1',customText:JSON.stringify(taxonomy.nodes||[])}}:{}),
    ...(org.action_requirements?{actionRequirements:{research_goal:action.research_goal||'',cooperation_goal:action.cooperation_goal||'',offering:action.offering||'',time_window:action.time_window||'',constraints:strings(action.constraints).join('\n'),required_relations:action.required_relations||[],metricConditions:JSON.stringify(action.required_metrics||[])}}:{})}
  return {query:typeof parameters.query==='string'?parameters.query:query,queryDraft,organizationDraft,budgetLimits:parameters.budget_limits||undefined,
    weights:org.weight_preset?{reference:org.weight_preset}:org.weights?{configuration:org.weights}:undefined,
    outputLength:parameters.output_length==='short'?'short':parameters.output_length==='long'?'long':'medium',useInternal:!!parameters.use_internal_docs,group:String(parameters.rag_group||''),
    channels:strings(parameters.channels),enabled:strings(parameters.enabled_skill_ids),disabled:strings(parameters.disabled_skill_ids),previewSessionId,ownerId,operationScopeId,original:structuredClone(parameters)}
}
export function setupRequest(value:ResearchSetup) {
  const draft=value.queryDraft,drawingIds=draft.drawingMode==='builtin'?[]:[...(draft.drawingMode==='manual_skill'?draft.drawingSkillIds:[]),...Object.values(deliveryDraftRequest(draft).chart_skill_ids).filter(Boolean)]
  if(drawingIds.some(id=>value.disabled.includes(id)))throw new Error(t("所选绘图方法已设为不使用，请重新选择。"))
  const old=value.original||{},parts=queryDraftRequest(draft,value.organizationDraft.enabled)
  const org=organizationRequest(value.organizationDraft,value.query.trim(),value.weights),previous=object(old.organization_research)
  let organization:Record<string,any>|null=org?{...previous,...org,scope:{...object(previous.scope),...org.scope}}:null
  if(organization){
    if(org&&'weight_preset' in org)delete organization.weights
    else if(value.weights?.configuration)delete organization.weight_preset
    if(!value.weights&&previous.weights)organization.weights=previous.weights
    if(org?.corpus){
      const prior=object(previous.corpus),before=setupFromRequest(old).organizationDraft.corpus,after=value.organizationDraft.corpus
      organization.corpus={...prior,...org.corpus}
      if(prior.source_scope&&before?.group===after?.group&&before?.domains===after?.domains)organization.corpus.source_scope=prior.source_scope
    }
    organization.scope.entities=organization.scope.entities.map((entity:any)=>{
      const existing=(object(previous.scope).entities||[]).find((item:any)=>item.name===entity.name&&item.type===entity.type)
      return existing?{...existing,...entity,entity_id:existing.entity_id,aliases:existing.aliases||entity.aliases,source_urls:entity.source_urls[0]===existing.source_urls?.[0]?existing.source_urls:entity.source_urls}:entity
    })
  }
  parts.query_options.entities=parts.query_options.entities.map(entity=>{const existing=(object(old.query_options).entities||[]).find((item:any)=>item.name===entity.name);return existing?{...existing,...entity,entity_id:existing.entity_id}:entity})
  const body:Record<string,unknown>={...old,query:value.query.trim(),budget_limits:value.budgetLimits||null,use_internal_docs:value.useInternal,rag_group:value.useInternal?value.group.trim()||null:null,
    output_length:value.outputLength,enabled_skill_ids:[...new Set([...value.enabled,...drawingIds])],disabled_skill_ids:value.disabled,channels:value.channels,organization_research:organization,
    planning_policy:{...object(old.planning_policy),...parts.planning_policy},query_options:{...object(old.query_options),...parts.query_options,
      ...(!value.useInternal?{internal_filter:{any_of:[]},internal_retrieval_mode:'hybrid',internal_channels:[]}:{})},delivery:{...object(old.delivery),...parts.delivery}}
  if(!('layout' in parts.delivery))delete (body.delivery as Record<string,unknown>).layout
  delete body.query_preview_id;delete body.user_confirmed
  return body
}
