import {useEffect,useRef,useState} from 'react'
import {useQuery,useQueryClient} from '@tanstack/react-query'
import {localeCode,t,uiDefinition,uiMessage,useLocale} from '../i18n'
import {collectionRequest,jsonOptions} from './CollectionUI'
import {Icon} from './Interface'
import SourceWebhookPanel from './SourceWebhookPanel'

interface SyncRun {run_id:string;status:string;outcome:string|null;error_category:string|null;network_calls:number;network_calls_unknown:boolean;updated_at:string}
interface Subscription {subscription_id:string;name:string;group_name:string;url:string;interval_seconds:number;enabled:boolean;revision:number;source_id:string|null;next_run_at:string|null;last_outcome:string|null;last_error:string|null;latest_run:SyncRun|null}
const outcomes:Record<string,string>=uiDefinition({created:'已添加资料',updated:'已更新资料',unchanged:'内容未变化',failed:'同步未完成'})
const states:Record<string,string>=uiDefinition({queued:'等待同步',running:'正在同步',completed:'同步完成',failed:'同步未完成',canceled:'已停止'})
const errors:Record<string,string>=uiDefinition({
  source_sync_already_running:'这个来源正在同步',source_sync_revision_conflict:'设置已变化，请刷新后重试',
  source_sync_request_conflict:'操作内容已变化，请重新提交',source_sync_not_found:'这个来源已不存在',
  source_sync_limit:'已达到可添加来源的数量上限',network:'网络连接未完成',timeout:'读取来源超时',
  rate_limited:'来源暂时限制访问',upstream_error:'来源暂时不可用',access_denied:'来源拒绝访问',
  auth_required:'来源需要登录',not_found:'来源页面不存在',source_sync_redirect_out_of_scope:'来源跳转超出登记范围',
  source_sync_target_changed_or_unavailable:'目标资料已变更或不可用',source_sync_processing_failed:'资料处理未完成',
  source_sync_run_expired_before_commit:'同步时间已到',original_deadline_expired:'同步时间已到',
  lease_receipt_unknown:'上次读取的结果未能确认',network_allowance_exhausted:'本次读取次数已用完',
  unsupported_content_type:'来源格式暂不支持',empty_content:'来源没有可读取的正文',
  source_sync_dense_configuration_requires_manual_update:'该资料的编码设置已变化，请手动更新',
  source_sync_sparse_configuration_requires_manual_update:'该资料的编码设置已变化，请手动更新',
  source_sync_partial_replacement_blocked:'新内容读取不完整，已保留原版本',
  subscription_changed:'来源设置已变化',subscription_unavailable:'来源或账号已不可用',
  webhook_revoked:'事件通知已撤销',source_webhook_revoked:'事件通知已撤销',
})
const showTime=(value:string)=>new Date(value).toLocaleString(localeCode(),{year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})

export default function SourceSyncPanel({group,groups,onChanged}:{group:string;groups:string[];onChanged:()=>Promise<void>}){
  useLocale()
  const client=useQueryClient(),[adding,setAdding]=useState(false),[name,setName]=useState(''),[url,setUrl]=useState(''),
    [groupName,setGroupName]=useState(group||'我的资料'),[interval,setInterval]=useState(86400),[enabled,setEnabled]=useState(false),
    [busy,setBusy]=useState(''),[error,setError]=useState(''),[history,setHistory]=useState<string|null>(null)
  const [webhook,setWebhook]=useState<string|null>(null)
  const guard=useRef(false),createId=useRef<string|null>(null),attemptIds=useRef<Record<string,string>>({}),seen=useRef<Record<string,string>>({})
  const query=useQuery<{items:Subscription[]}>({queryKey:['source-sync'],queryFn:({signal})=>collectionRequest('/api/v1/source-sync/subscriptions',{signal}),
    refetchInterval:value=>value.state.data?.items.some(item=>['queued','running'].includes(item.latest_run?.status||''))?2500:30000})
  const runs=useQuery<{items:SyncRun[]}>({queryKey:['source-sync-runs',history],enabled:!!history,
    queryFn:({signal})=>collectionRequest(`/api/v1/source-sync/subscriptions/${history}/runs`,{signal}),
    refetchInterval:value=>value.state.data?.items.some(item=>['queued','running'].includes(item.status))?2500:false})
  useEffect(()=>{
    let updated=false
    for(const item of query.data?.items||[]){const run=item.latest_run;if(run&&run.status==='completed'&&seen.current[item.subscription_id]!==run.run_id){
      if(seen.current[item.subscription_id]!==undefined)updated=true
      seen.current[item.subscription_id]=run.run_id
    }else if(seen.current[item.subscription_id]===undefined)seen.current[item.subscription_id]=''}
    if(updated)void onChanged()
  },[query.data,onChanged])
  async function perform(key:string,work:()=>Promise<unknown>){
    if(guard.current)return false
    guard.current=true;setBusy(key);setError('')
    try{await work();await client.invalidateQueries({queryKey:['source-sync']});await client.invalidateQueries({queryKey:['source-sync-runs']});return true}
    catch(problem){const code=problem instanceof Error?problem.message:'';setError(errors[code]||t("暂时无法完成，请重试"));return false}
    finally{guard.current=false;setBusy('')}
  }
  const clearCreateId=()=>{createId.current=null}
  async function create(){
    if(!name.trim()||!url.trim()||!groupName.trim()){setError(t("请填写来源名称、链接和分组"));return}
    createId.current??=crypto.randomUUID()
    await perform('create',async()=>{
      await collectionRequest('/api/v1/source-sync/subscriptions',jsonOptions({request_id:createId.current,name:name.trim(),url:url.trim(),
        group_name:groupName.trim(),interval_seconds:interval,enabled}))
      createId.current=null;setName('');setUrl('');setEnabled(false);setAdding(false)
    })
  }
  async function act(item:Subscription,action:'enable'|'pause'|'delete'|'interval',intervalSeconds?:number){
    const key=`${item.subscription_id}:${item.revision}:${action}:${intervalSeconds||''}`;attemptIds.current[key]??=crypto.randomUUID()
    if(await perform(item.subscription_id,()=>collectionRequest(`/api/v1/source-sync/subscriptions/${item.subscription_id}/actions`,
      jsonOptions({request_id:attemptIds.current[key],expected_revision:item.revision,action,...(action==='interval'?{interval_seconds:intervalSeconds}:{})}))))delete attemptIds.current[key]
  }
  async function run(item:Subscription){
    const key=`${item.subscription_id}:run`;attemptIds.current[key]??=crypto.randomUUID()
    if(await perform(item.subscription_id,()=>collectionRequest(`/api/v1/source-sync/subscriptions/${item.subscription_id}/runs`,jsonOptions({request_id:attemptIds.current[key]}))))delete attemptIds.current[key]
  }
  return <div className="source-sync-panel">
    <div className="source-sync-intro"><p>{t("为常用公开来源设置同步，资料更新时保留原有版本。")}</p>
      <button type="button" className="btn-secondary" onClick={()=>{setAdding(!adding);setError('')}}><Icon name="plus" size={16}/>{adding?t("收起"):t("添加来源")}</button></div>
    {adding&&<div className="collection-form source-sync-form">
      <label className="collection-field">{t("来源名称")}<input value={name} onChange={event=>{setName(event.target.value);clearCreateId()}} maxLength={200}/></label>
      <label className="collection-field">{t("公开来源链接")}<input type="url" value={url} onChange={event=>{setUrl(event.target.value);clearCreateId()}} placeholder="https://" maxLength={2048}/></label>
      <div className="collection-columns"><label className="collection-field">{t("保存到分组")}<input list="source-sync-groups" value={groupName} onChange={event=>{setGroupName(event.target.value);clearCreateId()}} maxLength={100}/><datalist id="source-sync-groups">{groups.map(item=><option key={item} value={item}/>)}</datalist></label>
        <label className="collection-field">{t("同步频率")}<select value={interval} onChange={event=>{setInterval(Number(event.target.value));clearCreateId()}}><option value={900}>{t("每 15 分钟")}</option><option value={3600}>{t("每小时")}</option><option value={86400}>{t("每天")}</option><option value={604800}>{t("每周")}</option><option value={2592000}>{t("每 30 天")}</option></select></label></div>
      <label className="collection-checks"><input type="checkbox" checked={enabled} onChange={event=>{setEnabled(event.target.checked);clearCreateId()}}/>{t("启用定时同步")}</label>
      <div className="source-sync-form-footer"><span>{t("保存后可手动同步；定时同步从下一个周期开始。")}</span><button type="button" className="btn-primary" disabled={!!busy} onClick={()=>void create()}>{busy==='create'?t("保存中…"):t("保存来源")}</button></div>
    </div>}
    {error&&<p role="alert" className="collection-feedback">{uiMessage(error)}</p>}
    {query.isLoading?<p>{t("正在读取来源…")}</p>:query.isError?<p role="alert">{t("来源暂时无法读取")}</p>:!query.data?.items.length?<p className="source-sync-empty">{t("还没有同步来源")}</p>:<div className="source-sync-list">{query.data.items.map(item=><article className="source-sync-item" key={item.subscription_id}>
      <div className="source-sync-item-head"><div><strong>{item.name}</strong><small>{item.group_name} · {item.url}</small></div><span className="collection-status">{item.enabled?t("定时同步中"):t("仅手动")}</span></div>
      <p>{item.latest_run?states[item.latest_run.status]||t("同步记录"):t("尚未同步")}{item.latest_run?.outcome&&outcomes[item.latest_run.outcome]?' · '+outcomes[item.latest_run.outcome]:''}{item.latest_run?.error_category?' · '+(errors[item.latest_run.error_category]||t("请查看同步记录")):''}{item.latest_run?.network_calls_unknown?' · '+t("读取次数未完全确认"):''}</p>
      {item.next_run_at&&<small>{t("下次同步")} · {showTime(item.next_run_at)}</small>}
      <div className="source-sync-actions"><button type="button" className="btn-secondary" disabled={!!busy||['queued','running'].includes(item.latest_run?.status||'')} onClick={()=>void run(item)}>{t("立即同步")}</button>
        <select aria-label={t("调整同步频率")} value={item.interval_seconds} disabled={!!busy} onChange={event=>void act(item,'interval',Number(event.target.value))}>{![900,3600,86400,604800,2592000].includes(item.interval_seconds)&&<option value={item.interval_seconds}>{t("每 {0} 秒",item.interval_seconds)}</option>}<option value={900}>{t("每 15 分钟")}</option><option value={3600}>{t("每小时")}</option><option value={86400}>{t("每天")}</option><option value={604800}>{t("每周")}</option><option value={2592000}>{t("每 30 天")}</option></select>
        <button type="button" className="btn-ghost" disabled={!!busy} onClick={()=>void act(item,item.enabled?'pause':'enable')}>{item.enabled?t("暂停定时"):t("启用定时")}</button>
        <button type="button" className="btn-ghost" onClick={()=>setHistory(history===item.subscription_id?null:item.subscription_id)}>{t("同步记录")}</button>
        <button type="button" className="btn-ghost" onClick={()=>setWebhook(webhook===item.subscription_id?null:item.subscription_id)}>{t("事件通知")}</button>
        <button type="button" className="btn-ghost" disabled={!!busy} onClick={()=>void act(item,'delete')}>{t("移除同步")}</button></div>
      {webhook===item.subscription_id&&<SourceWebhookPanel key={item.subscription_id} subscriptionId={item.subscription_id}/>}
      {history===item.subscription_id&&<div className="source-sync-history">{runs.isLoading?<p>{t("正在读取记录…")}</p>:runs.isError?<p>{t("记录暂时无法读取")}</p>:!runs.data?.items.length?<p>{t("尚无同步记录")}</p>:runs.data.items.map(run=><p key={run.run_id}>{showTime(run.updated_at)} · {states[run.status]||t("同步记录")}{run.outcome&&outcomes[run.outcome]?' · '+outcomes[run.outcome]:''}{run.error_category?' · '+(errors[run.error_category]||t("请查看同步记录")):''}{run.network_calls_unknown?' · '+t("读取次数未完全确认"):''}</p>)}</div>}
    </article>)}</div>}
  </div>
}
