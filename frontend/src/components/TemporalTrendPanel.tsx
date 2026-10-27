import {useEffect,useState} from 'react'
import {t,useLocale} from '../i18n'
import {collectionRequest,jsonOptions} from './CollectionUI'

interface TrendRow {year:number;source_count:number;decayed_source_weight:number;change_from_previous_year:number|null;
  source_references:Array<{source_id:string;name:string;date:string}>;references_truncated:boolean}
interface Trend {timeline:TrendRow[];unknown_date_sources:number;unknown_term_coverage_sources:number;future_date_sources:number;scope_truncated:boolean;
  scope:{group_name:string;term:string|null;as_of:string}}

export default function TemporalTrendPanel({groups,selectedGroup,onOpen}:{groups:string[];selectedGroup:string;onOpen:(id:string)=>void}){
  useLocale()
  const localDate=()=>{const now=new Date();return new Date(now.valueOf()-now.getTimezoneOffset()*60000).toISOString().slice(0,10)}
  const [group,setGroup]=useState(selectedGroup||groups[0]||''),[term,setTerm]=useState(''),[asOf,setAsOf]=useState(localDate),
    [start,setStart]=useState(''),[end,setEnd]=useState(''),[halfLife,setHalfLife]=useState(730),
    [result,setResult]=useState<Trend|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('')
  useEffect(()=>{if(selectedGroup)setGroup(selectedGroup)},[selectedGroup])
  useEffect(()=>{if(!group&&groups.length)setGroup(groups[0])},[group,groups])
  async function calculate(){
    if(busy||!group||!asOf)return
    if(start&&end&&start>end){setError(t('起始日期不能晚于结束日期'));return}
    if(!Number.isInteger(halfLife)||halfLife<30||halfLife>3650){setError(t('时间半衰期须为30–3650天的整数。'));return}
    setBusy(true);setError('')
    try{const data=await collectionRequest('/api/v1/documents/temporal-trends',jsonOptions({group_name:group,term:term.trim()||null,as_of:asOf,
      window_start:start||null,window_end:end||null,half_life_days:halfLife})) as Trend;setResult(data)}
    catch{setError(t('时间分布暂时无法读取'))}finally{setBusy(false)}
  }
  const largest=Math.max(1,...(result?.timeline.map(item=>item.source_count)||[]))
  return <section className="document-visual-panel" aria-label={t('资料时间分布')}>
    <div className="document-visual-form"><label className="collection-field">{t('资料分组')}<select value={group} onChange={event=>setGroup(event.target.value)}><option value="">{t('请选择')}</option>{groups.map(name=><option key={name} value={name}>{name}</option>)}</select></label>
      <label className="collection-field">{t('词项（可选）')}<input maxLength={128} value={term} onChange={event=>setTerm(event.target.value)}/></label>
      <label className="collection-field">{t('计算时点')}<input type="date" value={asOf} onChange={event=>setAsOf(event.target.value)}/></label>
      <label className="collection-field">{t('时间窗口起点')}<input type="date" value={start} onChange={event=>setStart(event.target.value)}/></label>
      <label className="collection-field">{t('时间窗口终点')}<input type="date" value={end} onChange={event=>setEnd(event.target.value)}/></label>
      <label className="collection-field">{t('时间半衰期（天）')}<input type="number" min={30} max={3650} value={halfLife} onChange={event=>setHalfLife(Number(event.target.value))}/></label>
      <button type="button" className="btn-secondary" disabled={busy||!group||!asOf} onClick={()=>void calculate()}>{busy?t('正在计算…'):t('查看变化')}</button></div>
    {error&&<p role="alert">{error}</p>}
    {result&&<div className="document-visual-result"><p>{result.scope.group_name}{result.scope.term?` · ${result.scope.term}`:''} · {result.scope.as_of}</p>
      {!result.timeline.length?<p>{t('所选范围没有带日期的资料')}</p>:<div className="space-y-2">{result.timeline.map(row=><details key={row.year}><summary className="flex items-center gap-3"><span>{row.year}</span><span className="h-2 flex-1 overflow-hidden rounded" style={{background:'var(--accent-soft)'}}><span className="block h-full rounded" style={{width:`${100*row.source_count/largest}%`,background:'var(--accent)'}}/></span><strong>{row.source_count}</strong><span className="text-xs">{row.change_from_previous_year===null?'—':`${row.change_from_previous_year>0?'+':''}${row.change_from_previous_year}`}</span></summary>
        <p className="text-xs">{t('衰减权重 {0}',row.decayed_source_weight)}</p>{row.source_references.map(source=><button type="button" className="btn-ghost text-xs" key={source.source_id} onClick={()=>onOpen(source.source_id)}>{source.name} · {source.date}</button>)}{row.references_truncated&&<span>{t('仅显示前 20 份资料')}</span>}</details>)}</div>}
      <p className="text-xs">{t('日期未填 {0} · 词项覆盖不完整 {1}',result.unknown_date_sources,result.unknown_term_coverage_sources)}{result.future_date_sources?` · ${t('未来日期 {0}',result.future_date_sources)}`:''}{result.scope_truncated?` · ${t('资料范围已截取')}`:''}</p>
    </div>}
  </section>
}
