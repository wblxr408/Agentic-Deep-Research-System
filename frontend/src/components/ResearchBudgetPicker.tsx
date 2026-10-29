import {useEffect,useRef,useState} from 'react'
import {useMutation,useQuery} from '@tanstack/react-query'
import {t,useLocale} from '../i18n'
import {Modal} from './Interface'
import {setupRequest} from './researchSetup'
import type {ResearchSetup} from './researchSetup'
import './researchBudget.css'

export interface ResearchLimits {max_total_tokens:number;max_tool_calls:number;max_wall_clock_seconds:number}
interface Advice {
  complexity:string;headroom_percent:number;estimated:ResearchLimits;recommended:ResearchLimits;defaults:ResearchLimits
  basis:{entity_count:number;module_count:number;depth:string;illustrated:boolean;
    workload?:{source_read_capacity:number;collection_seconds:number;analysis_seconds:number;delivery_seconds:number}}
}
interface BudgetView {
  session_id:string;execution_id:string;status:string;revision:number;limits:ResearchLimits;advice:Advice
  usage:{tokens:number;tool_calls:number;elapsed_seconds:number};adjustments:unknown[]
}
const names:Record<string,string>={
  budget_task_not_found:'这项研究暂时无法调整额度',budget_pause_required:'先暂停研究，再调整额度',
  budget_execution_changed:'任务已进入另一轮执行，请刷新后再调整',budget_revision_changed:'额度已被修改，请刷新后再调整',
  budget_request_conflict:'这次保存请求已变化，请刷新后再调整',budget_requests_inflight:'仍有调用正在结算，请稍后再保存',
  budget_below_used_allowance:'新上限需覆盖已用额度与已过时长',
  budget_new_research_required:'本轮已达可调上限，请新建研究。',
}
async function budgetRequest(path:string,options?:RequestInit) {
  let response:Response
  try {response=await fetch(path,options)}catch{throw new Error(t('连接中断，请重试。'))}
  let value:any
  try {value=await response.json()}catch{throw new Error(t('暂时无法处理额度，请重试。'))}
  if(!response.ok)throw new Error(typeof value.detail==='string'&&names[value.detail]?t(names[value.detail]):t('请检查额度数值'))
  return value
}
function Summary({limits}:{limits:ResearchLimits}) {
  return <span className="budget-inline">{limits.max_total_tokens.toLocaleString()} Token <span>·</span> {t('{0} 次工具请求',limits.max_tool_calls)} <span>·</span> {t('{0} 分钟',Math.round(limits.max_wall_clock_seconds/60))}</span>
}
function AdviceView({value,onAdopt,disabled=false}:{value:Advice;onAdopt:()=>void;disabled?:boolean}) {
  return <div className="budget-advice"><div className="budget-advice-heading"><strong>{t('建议额度')}</strong><span>{t(({simple:'简单',moderate:'适中',complex:'复杂'} as Record<string,string>)[value.complexity]||'适中')}</span></div>
    <Summary limits={value.recommended}/><p>{t('基础估算另加 {0}%，用于补证、重试与核对。',value.headroom_percent)}</p>
    <details><summary>{t('估算依据')}</summary>
      <p>{t('{0} 个对象 · {1} 个分析模块',value.basis.entity_count,value.basis.module_count)}</p>
      <p>{t('基础估算')}</p><Summary limits={value.estimated}/>
      {value.basis.workload&&<>
        <p>{t('取证')} · {t('{0} 分钟',Math.ceil(value.basis.workload.collection_seconds/60))}</p>
        <p>{t('分析')} · {t('{0} 分钟',Math.ceil(value.basis.workload.analysis_seconds/60))}</p>
        <p>{t('报告与核对')} · {t('{0} 分钟',Math.ceil(value.basis.workload.delivery_seconds/60))}</p>
      </>}
    </details>
    <button type="button" className="btn-secondary" disabled={disabled} onClick={onAdopt}>{t('采用建议')}</button>
  </div>
}
function LimitFields({value={max_total_tokens:0,max_tool_calls:0,max_wall_clock_seconds:0},onChange,disabled=false}:{value?:ResearchLimits;onChange:(limits:ResearchLimits)=>void;disabled?:boolean}) {
  return <div className="budget-fields">
    <label>{t('总 Token')}<input aria-label={t('总 Token')} type="number" min={4000} max={2000000} step={1000} disabled={disabled} value={value.max_total_tokens||''} onChange={event=>onChange({...value,max_total_tokens:Number(event.target.value)})}/></label>
    <label>{t('工具请求次数')}<input aria-label={t('工具请求次数')} type="number" min={1} max={256} step={1} disabled={disabled} value={value.max_tool_calls||''} onChange={event=>onChange({...value,max_tool_calls:Number(event.target.value)})}/></label>
    <label>{t('总时长（分钟）')}<input aria-label={t('总时长（分钟）')} type="number" min={1} max={360} step={1} disabled={disabled} value={value.max_wall_clock_seconds?Math.round(value.max_wall_clock_seconds/60):''} onChange={event=>onChange({...value,max_wall_clock_seconds:Number(event.target.value)*60})}/></label>
  </div>
}
export function validLimits(value:ResearchLimits) {
  return Number.isInteger(value.max_total_tokens)&&value.max_total_tokens>=4000&&value.max_total_tokens<=2000000&&
    Number.isInteger(value.max_tool_calls)&&value.max_tool_calls>=1&&value.max_tool_calls<=256&&
    Number.isInteger(value.max_wall_clock_seconds)&&value.max_wall_clock_seconds>=60&&value.max_wall_clock_seconds<=21600
}
export default function ResearchBudgetPicker({value,onChange,disabled=false}:{value:ResearchSetup;onChange:(value:ResearchSetup)=>void;disabled?:boolean}) {
  useLocale()
  const [open,setOpen]=useState(false),[request,setRequest]=useState<Record<string,unknown>|null>(null)
  let serialized=''
  try {const body=setupRequest(value);delete body.budget_limits;serialized=JSON.stringify(body)}catch{}
  useEffect(()=>{if(value.query.trim().length<5||!serialized){setRequest(null);return}
    const timer=setTimeout(()=>setRequest(JSON.parse(serialized)),400);return()=>clearTimeout(timer)
  },[serialized,value.query])
  const advice=useQuery<Advice>({queryKey:['research-budget-advice',request],enabled:!!request,
    queryFn:async({signal})=>budgetRequest('/api/v1/research/budget/recommendation',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request),signal}),
    staleTime:60000,refetchOnWindowFocus:false,retry:false})
  const adviceIsCurrent=!!request&&serialized===JSON.stringify(request)
  const currentAdvice=adviceIsCurrent?advice.data:undefined
  const limits=value.budgetLimits||currentAdvice?.defaults
  return <section className="research-budget-picker" aria-label={t('研究额度')}>
    <div className="budget-picker-heading"><span>{t('本次额度')}</span>{limits?<Summary limits={limits}/>:<span>{t('默认额度')}</span>}<button type="button" className="choice-text-button" disabled={disabled} aria-expanded={open} onClick={()=>setOpen(!open)}>{open?t('收起'):t('调整额度')}</button></div>
    {!open&&currentAdvice&&<p>{t('建议 {0} Token · 额外预留 {1}%',currentAdvice.recommended.max_total_tokens.toLocaleString(),currentAdvice.headroom_percent)}</p>}
    {open&&<div className="budget-editor-body">{currentAdvice&&<AdviceView value={currentAdvice} disabled={disabled} onAdopt={()=>onChange({...value,budgetLimits:currentAdvice!.recommended})}/>}
      <LimitFields value={limits} disabled={disabled} onChange={budgetLimits=>onChange({...value,budgetLimits})}/>
      {limits&&!validLimits(limits)&&<p role="alert">{t('请检查额度数值')}</p>}
      {value.budgetLimits&&<button type="button" className="choice-text-button" disabled={disabled} onClick={()=>onChange({...value,budgetLimits:undefined})}>{t('恢复默认额度')}</button>}
      {adviceIsCurrent&&advice.isFetching&&!currentAdvice&&<p role="status">{t('正在估算额度…')}</p>}
      {adviceIsCurrent&&advice.error&&<p role="alert">{t('暂时无法取得建议')} <button type="button" className="choice-text-button" disabled={disabled} onClick={()=>void advice.refetch()}>{t('重试')}</button></p>}
    </div>}
  </section>
}

function RevisionForm({view,onSaved}:{view:BudgetView;onSaved:()=>Promise<void>}) {
  const [limits,setLimits]=useState(view.limits),[saved,setSaved]=useState(false)
  const request=useRef<{signature:string;id:string}|null>(null)
  const save=useMutation({mutationFn:async()=>{
    const signature=JSON.stringify(limits)
    if(request.current?.signature!==signature)request.current={signature,id:crypto.randomUUID()}
    return budgetRequest(`/api/v1/research/${view.session_id}/budget`,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({limits,expected_revision:view.revision,execution_id:view.execution_id,request_id:request.current!.id})})
  },onSuccess:async()=>{setSaved(true);await onSaved()}})
  const paused=view.status==='paused'
  const exhausted=view.usage.tokens>=2000000||view.usage.tool_calls>256||view.usage.elapsed_seconds>=21600
  return <div className="budget-editor-body">
    <p className="budget-usage">{t('已用 {0} Token · {1} 次工具请求',view.usage.tokens.toLocaleString(),view.usage.tool_calls)}</p>
    {!paused&&<p>{t('先暂停研究，再调整额度')}</p>}
    {exhausted&&<p>{t('本轮已达可调上限，请新建研究。')}</p>}
    <AdviceView value={view.advice} disabled={!paused||save.isPending} onAdopt={()=>{setLimits(view.advice.recommended);setSaved(false)}}/>
    <LimitFields value={limits} disabled={!paused||save.isPending} onChange={next=>{setLimits(next);setSaved(false)}}/>
    <p>{t('总时长从研究最初开始计算。')}</p>
    {!!view.adjustments.length&&<p>{t('已保存 {0} 次额度调整',view.adjustments.length)}</p>}
    {save.error&&<p role="alert">{save.error.message}</p>}
    {saved&&<p role="status">{t('额度已保存，累计用量保留。')}</p>}
    <button type="button" className="btn-primary" disabled={!paused||exhausted||!validLimits(limits)||save.isPending} onClick={()=>save.mutate()}>{save.isPending?t('保存中…'):t('保存额度')}</button>
  </div>
}
export function TaskBudgetEditor({sessionId,status,onSaved}:{sessionId:string;status:string;onSaved:()=>Promise<void>}) {
  useLocale()
  const [open,setOpen]=useState(false),[saved,setSaved]=useState(false)
  const current=useQuery<BudgetView>({queryKey:['research-budget',sessionId,status],enabled:open,
    queryFn:async()=>budgetRequest(`/api/v1/research/${sessionId}/budget`),retry:false,refetchOnWindowFocus:false})
  if(['completed','failed','canceled'].includes(status))return null
  return <><button type="button" className="choice-text-button" onClick={()=>{setSaved(false);setOpen(true)}}>{t('调整额度')}</button>
    {saved&&<p role="status">{t('额度已保存，累计用量保留。')}</p>}
    <Modal open={open} onClose={()=>setOpen(false)} title={t('研究额度')}>
      {current.data&&<RevisionForm key={`${current.data.execution_id}-${current.data.revision}`} view={current.data}
        onSaved={async()=>{await onSaved();await current.refetch();setSaved(true);setOpen(false)}}/>}
      {current.isFetching&&!current.data&&<p role="status">{t('正在读取额度…')}</p>}
      {current.error&&<p role="alert">{current.error.message}<button type="button" className="choice-text-button" onClick={()=>void current.refetch()}>{t('重试')}</button></p>}
    </Modal>
  </>
}
