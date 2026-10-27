import {uiDefinition,t,useLocale} from '../i18n'
import { cloneElement, isValidElement } from 'react'
import type { ReactNode } from 'react'
import DeliveryTemplateManager from './DeliveryTemplateManager'
import type {ReportLayout,LayoutSample} from './reportLayouts'
import SkillStagePlan from './SkillStagePlan'
import type {StageSkillPlan} from './SkillStagePlan'

export interface QueryDraft {
  queryType: string; entityText: string; disciplines: string; contextSessionId: string; referenceIds: string[]
  constraints: string; timeMode: string; referenceDate: string; asOfDate: string
  startDate: string; endDate: string; preferStructuredTime: boolean; depth: string
  purpose: string; modules: string[] | null; template: string; theme: string
  pages: Array<{ title: string; module: string; question: string; chart: string }>
  drawingMode: string; drawingSkillIds: string[]; formats: string[]
  planningStrategy: string; autonomy: string; maxParallel: number; maxReplans: number
  termAliases: string; maxQueryVariants: number
  chartSkillIds:Record<string,string>
  internalFilter:string
  internalRetrievalMode:string
  internalChannels:string[]
  webCacheHours:number; maxAgeHours:number
  webReadMode:string
  candidateFusion:string
  outputKind:string
  copiedFromTemplate:{template_id:string;version:number}|null
  dataClass:string;modelDataCeiling:string;publicSearchQueries:string
  layout?:ReportLayout|null;layoutSample?:LayoutSample|null;layoutSourceId?:string|null;layoutName?:string;layoutMode?:'chapters'|'layout';layoutImportBusy?:boolean
}
export const defaultQueryDraft: QueryDraft = {
  queryType: '', entityText: '', disciplines: '', contextSessionId: '', referenceIds: [], constraints: '',
  timeMode: 'auto', referenceDate: '', asOfDate: '', startDate: '', endDate: '',
  preferStructuredTime: false, depth: 'auto', purpose: '', modules: null,
  template: 'markdown-v1', theme: 'plain-v1', pages: [], drawingMode: 'builtin', drawingSkillIds: [], formats: ['markdown'],
  planningStrategy: 'hybrid', autonomy: 'bounded', maxParallel: 3, maxReplans: 1,
  termAliases: '', maxQueryVariants: 2,
  chartSkillIds:{},
  internalFilter:'{"any_of":[]}',
  internalRetrievalMode:'hybrid',
  internalChannels:[],
  webCacheHours:24,maxAgeHours:72,
  webReadMode:'auto',
  candidateFusion:'{}',
  outputKind:'auto',copiedFromTemplate:null,
  dataClass:'public',modelDataCeiling:'internal',publicSearchQueries:'',
  layout:null,layoutSample:null,layoutSourceId:null,layoutName:'',layoutMode:'chapters',layoutImportBusy:false,
}

const queryTypes: Record<string, string> = uiDefinition({ fact: '事实查询', aggregate: '统计聚合', comparison: '比较', multi_hop: '多跳关联', exploration: '探索研究' })
const purposes: Record<string, string> = uiDefinition({ research_development: '布局与演进', cooperation_discovery: '合作发现', comprehensive: '综合研究' })
const modules: Record<string, string> = uiDefinition({ landscape: '全景', evolution: '演进', relationships: '关系', deep_dive: '深读', validation: '交叉验证', actions: '后续行动' })

export interface UnderstandingSnapshot {
  schema_version: string; interpretation_id: string; ready: boolean; query_type: string
  query_rewriting?:{max_variants:number;term_aliases:Record<string,string[]>;method:string}
  internal_filter?:{filter_id:string;strategy:string;policy:{any_of:unknown[]}}
  candidate_fusion?:{version:string;policy_id:string;policy:Record<string,unknown>}
  writing_plan?:{output_kind:string;depth:string;structure_owner:string}
  data_governance?:{initial_class:string;policy:{input_class:string;max_model_class:string;public_search_queries:string[]}}
  slots: { question: string; entities: Array<{ entity_id: string; name: string }>; disciplines: string[]
    time_window: { start_date: string; end_date: string } | null; purpose: string; modules: string[]; depth: string; additional_constraints: string }
  temporal: { mode: string; reference_date: string; as_of_date: string | null; max_age_hours: number | null }
  complexity: { level: string; decomposition_suggested: boolean; additional_llm_calls: number; predicted_cost_usd: number | null }
  clarifications: Array<{ id: string; message: string; candidate_ids?: string[] }>; notes: string[]
  context_candidates?: Array<{ entity_id: string; name: string }>
  delivery: { template: string; theme: string; formats: string[]; renderer_status: string; drawing_mode: string }
  execution_preparation?:{stages?:StageSkillPlan[]}
}

export function deliveryDraftRequest(draft:QueryDraft) {
  const layoutActive=draft.template==='custom'&&draft.layoutMode==='layout'&&draft.layout
  const figureSlots=new Set(layoutActive?draft.layout!.sections.flatMap(section=>section.blocks.filter(block=>['chart','table','image'].includes(block.kind)).map(block=>block.block_id)):[])
  return {template:draft.template,theme:draft.theme,output_kind:draft.outputKind||'auto',copied_from_template:draft.copiedFromTemplate||null,
    pages:draft.template==='custom'&&!layoutActive?draft.pages.map((page,index)=>({page_id:`page-${index+1}`,title:page.title,module:page.module||null,question:page.question,chart_kind:page.chart})):[],
    ...(layoutActive?{layout:draft.layout}:{}),
    drawing_mode:draft.drawingMode,drawing_skill_ids:draft.drawingMode==='manual_skill'?draft.drawingSkillIds:[],
    chart_skill_ids:draft.drawingMode==='builtin'?{}:Object.fromEntries(Object.entries(draft.chartSkillIds||{}).filter(([key,id])=>id&&(!key.startsWith('block-')||figureSlots.has(key)))),formats:draft.formats}
}

export function queryDraftRequest(draft: QueryDraft, organizationEnabled: boolean) {
  let internalFilter:unknown
  try {internalFilter=JSON.parse(draft.internalFilter||'{"any_of":[]}')}
  catch {throw new Error(t("内部资料筛选须使用有效JSON；可清空输入恢复不加业务条件。"))}
  let candidateFusion:unknown
  try {candidateFusion=JSON.parse(draft.candidateFusion||'{}')}
  catch {throw new Error(t("候选融合配置须使用有效JSON。"))}
  const termAliases:Record<string,string[]>=Object.create(null)
  for (const line of (draft.termAliases||'').split('\n').map(item=>item.trim()).filter(Boolean)) {
    const [term,...aliases]=line.split('|').map(item=>item.trim())
    if (!term||!aliases.length||aliases.some(item=>!item)||Object.prototype.hasOwnProperty.call(termAliases,term))
      throw new Error(t("请补全术语和其他叫法，术语不能重复。"))
    termAliases[term]=aliases
  }
  const entities = organizationEnabled ? [] : draft.entityText.split('\n').map(line => line.trim()).filter(Boolean).map((line, index) => {
    const [name, ...aliases] = line.split('|')
    return { entity_id: `query-${index + 1}`, name: name.trim(), aliases: aliases.join(',').split(/[,，]/).map(item => item.trim()).filter(Boolean) }
  })
  if (entities.length > 40) throw new Error(t("查询对象最多40个；组织研究可在组织面板选择。"))
  if (!draft.formats.length) throw new Error(t("至少选择一种交付格式。"))
  if (draft.template === 'custom' && !(draft.layoutMode==='layout'&&draft.layout) && !draft.pages.length) throw new Error(t("请为自定义报告添加页面。"))
  if (draft.drawingMode === 'manual_skill' && !draft.drawingSkillIds.length) throw new Error(t("请选择绘图Skill。"))
  return {
    planning_policy: { strategy: draft.planningStrategy, autonomy: draft.autonomy,
      max_parallel: draft.maxParallel, max_replans: draft.maxReplans },
    query_options: {
      query_type: draft.queryType || null, entities, context_session_id: draft.contextSessionId.trim() || null,
      disciplines: organizationEnabled ? [] : draft.disciplines.split(/[,，]/).map(item => item.trim()).filter(Boolean),
      reference_entity_ids: draft.referenceIds, additional_constraints: draft.constraints,
      time_mode: draft.timeMode, reference_date: draft.referenceDate || null, as_of_date: draft.asOfDate || null,
      start_date: organizationEnabled ? null : draft.startDate || null, end_date: organizationEnabled ? null : draft.endDate || null,
      prefer_structured_time: draft.preferStructuredTime, depth: draft.depth,
      purpose: organizationEnabled ? null : draft.purpose || null, modules: organizationEnabled ? null : draft.modules,
      term_aliases:termAliases,max_query_variants:draft.maxQueryVariants??2,
      internal_filter:internalFilter,
      internal_retrieval_mode:draft.internalRetrievalMode||'hybrid',
      internal_channels:draft.internalChannels||[],
      web_cache_hours:draft.webCacheHours??24,max_age_hours:draft.maxAgeHours??72,
      web_read_mode:draft.webReadMode||'auto',
      candidate_fusion:candidateFusion,
      data_policy:{input_class:draft.dataClass||'public',max_model_class:draft.modelDataCeiling||'internal',
        public_search_queries:(draft.publicSearchQueries||'').split('\n').map(value=>value.trim()).filter(Boolean)},
    },
    delivery:deliveryDraftRequest(draft),
  }
}

export function UnderstandingSummary({value}:{value:UnderstandingSnapshot|null|undefined}) {
  useLocale()

  if(!value)return null
  const templates:Record<string,string>={'markdown-v1':t("简洁长文"),'visual-brief-v1':t("图文简报"),'research-map-v1':t("研究脉络"),'organization-development-v1':t("机构研究"),'technology-comparison-v1':t("技术对比"),'cooperation-matching-v1':t("合作资源"),'field-trends-v1':t("领域趋势"),custom:t("自定义")}
  const formats:Record<string,string>={markdown:t("可编辑文字"),html:t("网页报告"),json:t("数据文件"),pdf:'PDF',pptx:t("幻灯片")}
  return <section className="understanding-summary" aria-label={t("研究计划预览")}><div className="understanding-heading"><h3>{t("研究计划")}</h3><span>{value.ready?t("可开始"):t("补充选择")}</span></div><dl>
    <div><dt>{t("对象")}</dt><dd>{value.slots.entities.map(item=>item.name).join('、')||t("围绕问题发现")}</dd></div>
    <div><dt>{t("重点")}</dt><dd>{purposes[value.slots.purpose]||queryTypes[value.query_type]||t("围绕问题研究")}</dd></div>
    {value.slots.time_window&&<div><dt>{t("时间")}</dt><dd>{value.slots.time_window.start_date} {t(" 至 ")}{value.slots.time_window.end_date}</dd></div>}
    {value.temporal.as_of_date&&<div><dt>{t("观察截止")}</dt><dd>{value.temporal.as_of_date}</dd></div>}
    {!!value.slots.modules.length&&<div><dt>{t("展开")}</dt><dd>{value.slots.modules.map(key=>modules[key]||key).join(' · ')}</dd></div>}
    <div><dt>{t("报告")}</dt><dd>{templates[value.delivery.template]||t("已保存的样式")} · {value.delivery.formats.map(format=>formats[format]||format).join(' / ')}</dd></div>
  </dl>{!!value.clarifications.length&&<ul className="understanding-clarifications" aria-label={t("需要补充的选择")}>{value.clarifications.map((item,index)=><li key={`${item.id}-${index}`}>{item.message}</li>)}</ul>}<SkillStagePlan stages={value.execution_preparation?.stages||[]}/></section>
}

function FieldLabel({ title, children }: { title: string; children: ReactNode }) {
  useLocale()

  const control = isValidElement<{ 'aria-label'?: string }>(children)
    ? cloneElement(children, { 'aria-label': children.props['aria-label'] || title }) : children
  return <label className="block space-y-1"><span className="text-xs text-xmgray-600">{title}</span>{control}</label>
}

export default function QueryUnderstandingPanel({ value, onChange, organizationEnabled, skills, preview, onPreview, busy, canPreview }: {
  value: QueryDraft; onChange: (draft: QueryDraft) => void; organizationEnabled: boolean
  skills: Array<{ id: string; name: string }>; preview: UnderstandingSnapshot | null; onPreview: () => void; busy: boolean; canPreview: boolean
}) {
  useLocale()

  const update = (patch: Partial<QueryDraft>) => onChange({ ...value, ...patch })
  const candidates = Array.from(new Map([...(preview?.slots.entities || []), ...(preview?.context_candidates || [])].map(item => [item.entity_id, item])).values())
  const toggle = (items: string[], key: string) => items.includes(key) ? items.filter(item => item !== key) : [...items, key]
  return <div className="mt-4 space-y-3 text-left">
    <details className="rounded-2xl border border-xmgray-100 bg-white p-4">
      <summary className="cursor-pointer text-sm font-medium">{t("研究问题、上下文与交付方案")}</summary>
      <div className="mt-4 space-y-4">
        <FieldLabel title={t("补充约束（重点问题、排除内容、口径与资料要求）")}><textarea className="input-xm w-full" rows={3} maxLength={1500} value={value.constraints} onChange={event => update({ constraints: event.target.value })} /></FieldLabel>
        <details className="rounded-lg border p-3"><summary className="cursor-pointer text-sm">{t("资料与模型外传范围")}</summary>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <FieldLabel title={t("本次输入资料级别")}><select className="input-xm w-full" value={value.dataClass||'public'} onChange={event=>{
              const rank=['public','internal','confidential','regulated'];const next=event.target.value
              update({dataClass:next,modelDataCeiling:rank.indexOf(next)>rank.indexOf(value.modelDataCeiling||'internal')?next:value.modelDataCeiling||'internal'})
            }}>{Object.entries({public:t("公开"),internal:t("内部"),confidential:t("机密"),regulated:t("受监管")}).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></FieldLabel>
            <FieldLabel title={t("允许传给模型的资料上限")}><select className="input-xm w-full" value={value.modelDataCeiling||'internal'} onChange={event=>update({modelDataCeiling:event.target.value})}>
              {Object.entries({public:t("公开"),internal:t("内部"),confidential:t("机密"),regulated:t("受监管")}).map(([key,label])=><option key={key} value={key}>{label}</option>)}
            </select></FieldLabel>
          </div>
          <FieldLabel title={t("允许公开搜索的查询（可选，每行一条，最多16条）")}><textarea className="input-xm mt-2 w-full" rows={3} maxLength={28800}
            value={value.publicSearchQueries||''} onChange={event=>update({publicSearchQueries:event.target.value})}/></FieldLabel>
          <p className="mt-2 text-xs text-xmgray-500">{t("内部来源和认证渠道会提高实际限制级别；输入声明不会放宽服务端模型许可。包含非公开材料后，外网查询使用已声明的公开查询及公开来源链接，私有材料不能自动成为搜索词。公开输入的原问题默认纳入公开查询范围。")}</p>
        </details>
        <details className="rounded-lg border p-3"><summary className="cursor-pointer text-sm">{t("检索术语与查询数量")}</summary>
          <div className="mt-3 space-y-2">
            <FieldLabel title={t("明确术语别称（每行：原词 | 别称1 | 别称2）")}><textarea className="input-xm w-full" rows={3} maxLength={8000}
              value={value.termAliases||''} onChange={event=>update({termAliases:event.target.value})}/></FieldLabel>
            <FieldLabel title={t("每步骤查询变体上限（含原查询，1—4）")}><input className="input-xm" type="number" min={1} max={4}
              value={value.maxQueryVariants??2} onChange={event=>update({maxQueryVariants:Number(event.target.value)})}/></FieldLabel>
            <p className="text-xs text-xmgray-500">{t("原查询优先，再尝试明确别称及当前对象／时间补全；实际数量受本次预算约束。别称不是实体身份的证明。")}</p>
          </div>
        </details>
        <details className="rounded-lg border p-3"><summary className="cursor-pointer text-sm">{t("候选融合与多样性")}</summary>
          <p className="my-2 text-xs text-xmgray-500">{t("分别整理内部资料与联网线索，保留来源、原始排名及实际权重。融合排名用于选择候选，事实支持度由后续原文核验决定。")}</p>
          <FieldLabel title={t("融合配置 JSON")}><textarea className="input-xm w-full font-mono text-xs" rows={5} maxLength={6000}
            value={value.candidateFusion||'{}'} onChange={event=>update({candidateFusion:event.target.value})}/></FieldLabel>
          <p className="my-2 text-xs text-xmgray-500">{t("method：rrf、borda、min_max、z_score；set_mode：union、intersection；per_route_top_k与global_top_k为1—100。 weights可按literal、bm25、fts、dense、structure、web、platform设置0—10之间的正权重。diversity为none或mmr（词面去冗余）。联网无可比分数时使用排名融合。学习式融合尚无标注数据及模型。")}</p>
          <button type="button" className="btn-ghost text-xs" onClick={()=>update({candidateFusion:JSON.stringify({method:'rrf',set_mode:'union',per_route_top_k:40,global_top_k:30,query_aware:true,diversity:'mmr',relevance_weight:.8},null,2)})}>{t("填入默认配置")}</button>
          <button type="button" className="btn-ghost text-xs" onClick={()=>update({candidateFusion:'{}'})}>{t("恢复默认")}</button>
        </details>
        <details className="rounded-lg border p-3"><summary className="cursor-pointer text-sm">{t("内部资料筛选（可选）")}</summary>
          <p className="my-2 text-xs text-xmgray-500">{t("需要启用内部资料。any_of组之间为“或”，组内all_of为“且”；所有组都受到本人权限和有效版本约束。")}</p>
          <FieldLabel title={t("内部资料召回方式")}><select className="input-xm w-full" value={value.internalRetrievalMode||'hybrid'}
            onChange={event=>update({internalRetrievalMode:event.target.value,...(event.target.value==='structured'?{internalChannels:[]}:{})})}>
            <option value="hybrid">{t("混合查询（词汇及已启用的稠密表示）")}</option><option value="structured">{t("只按筛选条件取资料（不按相关性排名）")}</option>
          </select></FieldLabel>
          {value.internalRetrievalMode!=='structured'&&<div className="choice-checks">{Object.entries({stem:t('英文词形'),sparse:t('学习稀疏语义'),paired:t('整体语义'),late:t('细粒度语义'),image:t('图文匹配')}).map(([id,label])=><label key={id}><input type="checkbox" checked={(value.internalChannels||[]).includes(id)} onChange={event=>update({internalChannels:event.target.checked?[...(value.internalChannels||[]),id]:(value.internalChannels||[]).filter(item=>item!==id)})}/>{label}</label>)}</div>}
          <p className="my-2 text-xs text-xmgray-500">{t("内部检索子问题可使用chunk:块UUID、source:来源UUID、phrase:完整短语或entity:已登记词面实体ID。 entity仅查词面提及与同源父子结构，不能证明真实身份或合作关系。")}</p>
          <FieldLabel title={t("业务筛选 JSON")}><textarea className="input-xm w-full font-mono text-xs" rows={5} maxLength={16000}
            value={value.internalFilter||''} onChange={event=>update({internalFilter:event.target.value})}/></FieldLabel>
          <p className="my-2 text-xs text-xmgray-500">{t("字段：source_id、group_name、source_name、source_type、format（如.pdf）、chunk_kind、chunk_index、created_at（入库时间，含时区）。 操作：eq、ne、in、not_in、gte、lte、exists、missing。比较排除缺失字段；要查缺失请明确使用missing。")}</p>
          <button type="button" className="btn-ghost text-xs" onClick={()=>update({internalFilter:JSON.stringify({any_of:[{all_of:[{field:'format',op:'eq',value:'.pdf'}]}]},null,2)})}>{t("填入PDF格式示例")}</button>
          <button type="button" className="btn-ghost text-xs" onClick={()=>update({internalFilter:'{"any_of":[]}'})}>{t("清空筛选")}</button>
        </details>
        <div className="grid gap-3 sm:grid-cols-2">
          <FieldLabel title={t("查询类型")}><select className="input-xm w-full" value={value.queryType} onChange={event => update({ queryType: event.target.value })}>
            <option value="">{t("按问题识别")}</option>{Object.entries(queryTypes).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select></FieldLabel>
          <FieldLabel title={t("分析深度")}><select className="input-xm w-full" value={value.depth} onChange={event => update({ depth: event.target.value })}>
            <option value="auto">{t("按问题选择")}</option><option value="brief">{t("简报")}</option><option value="standard">{t("标准分析")}</option><option value="deep">{t("深入分析")}</option>
          </select></FieldLabel>
          <FieldLabel title={t("回答形式")}><select className="input-xm w-full" value={value.outputKind||'auto'} onChange={event=>update({outputKind:event.target.value})}>
            {Object.entries({auto:t("按问题选择"),answer:t("直接回答"),summary:t("研究总结"),comparison:t("对比分析"),report:t("完整研究报告"),data_analysis:t("数据分析")}).map(([key,label])=><option key={key} value={key}>{label}</option>)}
          </select></FieldLabel>
        </div>
        {!organizationEnabled && <>
          <FieldLabel title={t("研究学科（可选，逗号分隔；用于学科 Skill 匹配）")}><input className="input-xm w-full" value={value.disciplines} maxLength={3000} onChange={event => update({ disciplines: event.target.value })} /></FieldLabel>
          <FieldLabel title={t("明确研究对象（每行一个；可用 名称 | 别名1,别名2）")}><textarea className="input-xm w-full" rows={3} maxLength={8000} value={value.entityText} onChange={event => update({ entityText: event.target.value })} /></FieldLabel>
          <FieldLabel title={t("研究目的")}><select className="input-xm w-full" value={value.purpose} onChange={event => update({ purpose: event.target.value, modules: null })}>
            <option value="">{t("通用研究")}</option>{Object.entries(purposes).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
          </select></FieldLabel>
          {value.purpose && <fieldset><legend className="text-xs text-xmgray-600">{t("内容模块")}</legend>
            <label className="mr-3 text-xs"><input type="checkbox" checked={value.modules === null} onChange={event => update({ modules: event.target.checked ? null : ['landscape'] })} /> {t(" 按目的选择默认模块")}</label>
            {value.modules !== null && <div className="mt-2 flex flex-wrap gap-3">{Object.entries(modules).map(([key, label]) => <label key={key} className="text-xs"><input type="checkbox" checked={value.modules?.includes(key) || false} onChange={() => update({ modules: toggle(value.modules || [], key) })} /> {label}</label>)}</div>}
          </fieldset>}
        </>}
        <FieldLabel title={t("显式引用历史会话 ID（可选，只读取本人对象信息）")}><input className="input-xm w-full" value={value.contextSessionId} maxLength={36} onChange={event => update({ contextSessionId: event.target.value, referenceIds: [] })} /></FieldLabel>
        <p className="text-xs text-xmgray-500">{t("填好后预览以显示候选；历史资料、来源权限和预算不会自动沿用。组织模式仍以当前组织选择为准。")}</p>
        {!!candidates.length && <fieldset><legend className="text-xs text-xmgray-600">{t("明确指代对象（单选或多选）")}</legend>
          <div className="mt-2 flex flex-wrap gap-3">{candidates.map(item => <label key={item.entity_id} className="text-xs"><input type="checkbox" checked={value.referenceIds.includes(item.entity_id)} onChange={() => update({ referenceIds: toggle(value.referenceIds, item.entity_id) })} /> {item.name} <span className="text-xmgray-400">{item.entity_id}</span></label>)}</div>
        </fieldset>}
        <div className="grid gap-3 sm:grid-cols-2">
          <FieldLabel title={t("时间需求")}><select className="input-xm w-full" value={value.timeMode} onChange={event => update({ timeMode: event.target.value })}>
            <option value="auto">{t("按问题识别")}</option><option value="static">{t("静态知识")}</option><option value="realtime">{t("实时资料")}</option><option value="historical">{t("历史时点")}</option>
          </select></FieldLabel>
          <FieldLabel title={t("实时资料抓取年龄上限（小时，1—8760）")}><input className="input-xm w-full" type="number" min={1} max={8760}
            value={value.maxAgeHours??72} onChange={event=>update({maxAgeHours:Number(event.target.value)})}/></FieldLabel>
          <FieldLabel title={t("同任务网页缓存上限（小时，0表示重新读取）")}><input className="input-xm w-full" type="number" min={0} max={8760}
            value={value.webCacheHours??24} onChange={event=>update({webCacheHours:Number(event.target.value)})}/></FieldLabel>
          <FieldLabel title={t("网页读取方式")}><select className="input-xm w-full" value={value.webReadMode||'auto'} onChange={event=>update({webReadMode:event.target.value})}>
            <option value="auto">{t("原文优先，必要时有界渲染")}</option><option value="source">{t("只读取原文")}</option><option value="rendered">{t("使用受控浏览器渲染")}</option>
          </select></FieldLabel>
          <FieldLabel title={t("分析参考日期（留空使用服务器 UTC 日期）")}><input type="date" className="input-xm w-full" value={value.referenceDate} onChange={event => update({ referenceDate: event.target.value })} /></FieldLabel>
          <FieldLabel title={t("历史观察截止日期（可选）")}><input type="date" className="input-xm w-full" value={value.asOfDate} onChange={event => update({ asOfDate: event.target.value })} /></FieldLabel>
          {!organizationEnabled && <>
            <FieldLabel title={t("研究起始日期（与结束日期成对填写）")}><input type="date" className="input-xm w-full" value={value.startDate} onChange={event => update({ startDate: event.target.value })} /></FieldLabel>
            <FieldLabel title={t("研究结束日期")}><input type="date" className="input-xm w-full" value={value.endDate} onChange={event => update({ endDate: event.target.value })} /></FieldLabel>
          </>}
        </div>
        <label className="block text-xs"><input type="checkbox" checked={value.preferStructuredTime} onChange={event => update({ preferStructuredTime: event.target.checked })} /> {t(" 日期冲突时，明确以日期字段或组织范围为准")}</label>
        <div className="grid gap-3 sm:grid-cols-2">
          <FieldLabel title={t("规划方式")}><select className="input-xm w-full" value={value.planningStrategy} onChange={event => update({ planningStrategy: event.target.value })}>
            <option value="hybrid">{t("混合：简单问题直接取证")}</option><option value="fixed">{t("固定：按对象直接取证")}</option><option value="dynamic">{t("动态：模型分解子问题")}</option>
          </select></FieldLabel>
          <FieldLabel title={t("研究轮次")}><select className="input-xm w-full" value={value.autonomy} onChange={event => update({ autonomy: event.target.value })}>
            <option value="bounded">{t("有具体缺口时有限补证")}</option><option value="single_pass">{t("单轮取证后出报告")}</option>
          </select></FieldLabel>
          <FieldLabel title={t("同时执行的取证步骤上限（1–8）")}><input type="number" min={1} max={8} className="input-xm w-full" value={value.maxParallel} onChange={event => update({ maxParallel: Number(event.target.value) })} /></FieldLabel>
          <FieldLabel title={t("补证上限（0–5；同时受任务预算限制）")}><input type="number" min={0} max={5} className="input-xm w-full" value={value.maxReplans} onChange={event => update({ maxReplans: Number(event.target.value) })} /></FieldLabel>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <FieldLabel title={t("报告模板")}><select className="input-xm w-full" value={value.template} onChange={event => update({ template: event.target.value })}>
            <option value="markdown-v1">{t("标准报告")}</option><option value="visual-brief-v1">{t("图像简报")}</option><option value="research-map-v1">{t("研究脉络图谱")}</option>
            <option value="organization-development-v1">{t("组织研究发展")}</option><option value="technology-comparison-v1">{t("技术比较")}</option><option value="cooperation-matching-v1">{t("合作匹配")}</option><option value="field-trends-v1">{t("领域趋势")}</option><option value="custom">{t("自定义页面")}</option>
          </select></FieldLabel>
          <FieldLabel title={t("主题")}><select className="input-xm w-full" value={value.theme} onChange={event => update({ theme: event.target.value })}>
            <option value="plain-v1">{t("简洁")}</option><option value="light-v1">{t("浅色")}</option><option value="dark-v1">{t("深色")}</option>
          </select></FieldLabel>
        </div>
        {value.template!=='custom'&&<button type="button" className="btn-ghost text-sm" onClick={()=>{
          const order:Record<string,string[]>={ 'research-map-v1':['relationships','evolution','landscape','deep_dive','validation','actions'],
            'cooperation-matching-v1':['relationships','landscape','deep_dive','validation','actions'],
            'technology-comparison-v1':['landscape','deep_dive','evolution','validation','actions'] }
          const selected=preview?.slots.modules?.length?preview.slots.modules:value.modules||Object.keys(modules)
          const preferred=order[value.template]||['landscape','evolution','relationships','deep_dive','validation','actions']
          const ordered=[...preferred.filter(module=>selected.includes(module)),...selected.filter(module=>!preferred.includes(module))]
          update({template:'custom',pages:ordered.map(module=>({title:modules[module]||module,module,question:'',chart:'auto'}))})
        }}>{t("从当前预设复制为自定义页面")}</button>}
        {value.template === 'custom' && <div className="space-y-3">
          {value.pages.map((page, index) => <div key={index} className="space-y-2 rounded-xl border p-3">
            <FieldLabel title={t("第 {0} 页标题", index + 1)}><input className="input-xm w-full" value={page.title} maxLength={300} onChange={event => update({ pages: value.pages.map((item, i) => i === index ? { ...item, title: event.target.value } : item) })} /></FieldLabel>
            <FieldLabel title={t("本页回答的问题")}><input className="input-xm w-full" maxLength={500} value={page.question} onChange={event => update({ pages: value.pages.map((item, i) => i === index ? { ...item, question: event.target.value } : item) })} /></FieldLabel>
            <div className="grid gap-2 sm:grid-cols-2"><FieldLabel title={t("内容模块")}><select className="input-xm w-full" value={page.module} onChange={event => update({ pages: value.pages.map((item, i) => i === index ? { ...item, module: event.target.value } : item) })}><option value="">{t("按页面问题选择")}</option>{Object.entries(modules).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></FieldLabel>
              <FieldLabel title={t("图表偏好")}><select className="input-xm w-full" value={page.chart} onChange={event => update({ pages: value.pages.map((item, i) => i === index ? { ...item, chart: event.target.value } : item) })}>{Object.entries({ auto: t("按数据选择"), none: t("文字"), line: t("折线"), bar: t("条形"), scatter: t("散点"), network: t("关系网络"), timeline: t("时间线"), heatmap: t("热力图"), table: t("表格") }).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></FieldLabel></div>
            <button type="button" className="btn-ghost text-xs" onClick={() => update({ pages: value.pages.filter((_, i) => i !== index) })}>{t("移除此页")}</button>
            <button type="button" className="btn-ghost text-xs" disabled={index===0} onClick={()=>{const pages=[...value.pages]; [pages[index-1],pages[index]]=[pages[index],pages[index-1]]; update({pages})}}>{t("上移")}</button>
            <button type="button" className="btn-ghost text-xs" disabled={index===value.pages.length-1} onClick={()=>{const pages=[...value.pages]; [pages[index+1],pages[index]]=[pages[index],pages[index+1]]; update({pages})}}>{t("下移")}</button>
          </div>)}
          <button type="button" className="btn-ghost text-sm" disabled={value.pages.length >= 24} onClick={() => update({ pages: [...value.pages, { title: '', module: '', question: '', chart: 'auto' }] })}>{t("添加页面")}</button>
        </div>}
        <FieldLabel title={t("绘图方案")}><select className="input-xm w-full" value={value.drawingMode} onChange={event => update({ drawingMode: event.target.value, drawingSkillIds: [],chartSkillIds:{} })}>
          <option value="builtin">{t("内置绘图")}</option><option value="manual_skill">{t("手选绘图 Skill")}</option><option value="auto_skill">{t("允许自动匹配绘图 Skill")}</option>
        </select></FieldLabel>
        {value.drawingMode === 'manual_skill' && <fieldset><legend className="text-xs text-xmgray-600">{t("选择绘图 Skill")}</legend>
          <div className="mt-2 flex flex-wrap gap-3">{skills.map(skill => <label className="text-xs" key={skill.id}><input type="checkbox" checked={value.drawingSkillIds.includes(skill.id)} onChange={() => update({ drawingSkillIds: toggle(value.drawingSkillIds, skill.id) })} /> {skill.name}</label>)}</div>
          {!skills.length && <p className="text-xs text-amber-800">{t("目前没有可选的已注册 Skill。")}</p>}
        </fieldset>}
        {value.drawingMode!=='builtin'&&<details className="rounded-lg border p-3"><summary className="cursor-pointer text-sm">{t("单图 Skill 覆盖（可选）")}</summary>
          <p className="my-2 text-xs text-xmgray-500">{t("为指定图表选择独立绘图方法。")}</p>
          <div className="grid gap-2 sm:grid-cols-2">{Object.entries({annual_publications:t("年度发表"),classification_publications:t("技术分类"),
            object_publications:t("对象样本"),source_relationships:t("来源关系"),technical_comparison:t("技术条件比较"),citation_sources:t("引用来源")}).map(([key,label])=><FieldLabel key={key} title={label}>
              <select className="input-xm w-full" value={value.chartSkillIds?.[key]||''}
                onChange={event=>update({chartSkillIds:{...(value.chartSkillIds||{}),[key]:event.target.value}})}>
                <option value="">{t("沿用默认方案")}</option>{skills.map(skill=><option key={skill.id} value={skill.id}>{skill.name}</option>)}
              </select></FieldLabel>)}</div>
        </details>}
        <DeliveryTemplateManager configuration={deliveryDraftRequest(value)} layoutSourceId={value.layoutSourceId} onApply={(configuration,origin,meta)=>{
          update({template:String(configuration.template||'markdown-v1'),theme:String(configuration.theme||'plain-v1'),
            outputKind:String(configuration.output_kind||'auto'),copiedFromTemplate:origin,
            layout:configuration.layout?structuredClone(configuration.layout) as ReportLayout:null,layoutMode:configuration.layout?'layout':'chapters',layoutSample:null,layoutSourceId:meta?.sourceId||null,layoutName:meta?.name||'',layoutImportBusy:false,
            pages:Array.isArray(configuration.pages)?configuration.pages.map((page:Record<string,unknown>)=>({title:String(page.title||''),module:String(page.module||''),question:String(page.question||''),chart:String(page.chart_kind||'auto')})):[],
            drawingMode:String(configuration.drawing_mode||'builtin'),drawingSkillIds:Array.isArray(configuration.drawing_skill_ids)?configuration.drawing_skill_ids as string[]:[],
            chartSkillIds:(configuration.chart_skill_ids||{}) as Record<string,string>,formats:configuration.formats as string[]||['markdown']})
        }}/>
        <fieldset><legend className="text-xs text-xmgray-600">{t("交付格式")}</legend><div className="mt-2 flex flex-wrap gap-3">{['markdown', 'html', 'json', 'pdf', 'pptx'].map(format => <label className="text-xs" key={format}><input type="checkbox" checked={value.formats.includes(format)} onChange={() => update({ formats: toggle(value.formats, format) })} /> {format.toUpperCase()}</label>)}</div></fieldset>
        <p className="text-xs text-xmgray-500">{t("正文支持 Markdown、HTML 和 JSON，PDF 使用打印导出；图表提供 SVG、PNG 与 PDF。")}</p>
      </div>
    </details>
    <button type="button" className="btn-ghost text-sm" disabled={busy || !canPreview} onClick={onPreview}>{busy ? t("正在解释查询…") : t("预览问题理解与约束")}</button>
    {preview && <UnderstandingSummary value={preview} />}
  </div>
}
