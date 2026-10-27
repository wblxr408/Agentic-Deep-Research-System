import {useEffect,useRef,useState} from 'react'
import {useQuery,useQueryClient} from '@tanstack/react-query'
import {t,uiDefinition,uiMessage,useLocale} from '../i18n'
import {collectionRequest,jsonOptions} from './CollectionUI'
import {Icon} from './Interface'

interface Endpoint {id:string;label:string}
interface Run {run_id:string;status:string;error_category:string|null;fetched:number;applied:number;acknowledged:number}
interface Connection {connection_id:string;endpoint_id:string;name:string;group_name:string;enabled:boolean;revision:number;interval_seconds:number;
  snapshot_status:string;snapshot_rows:number|null;snapshot_pending:number|null;last_status:string|null;last_error:string|null;latest_run:Run|null;blocked_events:number}
interface Event {event_id:string;document_key:string;revision:number;status:string;error_category:string|null;acknowledged:boolean}

const errors:Record<string,string>=uiDefinition({
  cdc_endpoint_not_authorized:'数据库未向当前账号开放',cdc_encryption_unavailable:'请先配置服务端密钥加密',
  cdc_endpoint_changed_reauthorize:'数据库授权已变化，请重新添加连接',cdc_already_running:'这个连接正在同步',
  cdc_revision_conflict:'连接设置已变化，请刷新后重试',cdc_request_conflict:'操作内容已变化，请重新提交',
  cdc_connection_not_found:'连接已移除',cdc_connection_limit:'已达到连接数量上限',cdc_source_timeout:'数据库响应超时',
  cdc_source_busy:'数据库正忙，稍后重试',cdc_authentication_rejected:'数据库账号或密码不正确',
  cdc_source_permission_denied:'数据库账号缺少读取或确认权限',cdc_source_schema_missing:'数据库未安装所需事件结构',
  cdc_endpoint_address_not_authorized:'数据库地址不在授权范围内',cdc_tls_validation_failed:'数据库证书校验未通过',
  cdc_libpq_capability_unavailable:'数据库客户端缺少所需安全能力',cdc_source_connection_or_query_failed:'无法连接或读取数据库',
  cdc_source_worker_failed:'数据库读取进程未完成',cdc_run_deadline_expired:'本次同步时间已到',
  cdc_worker_interrupted:'同步被中断，下次可继续',cdc_connection_changed:'连接设置已变化',cdc_credentials_unavailable:'连接凭据无法读取',
  cdc_event_content_invalid_or_too_large:'内容为空或超过大小限制',cdc_event_parse_incomplete:'资料解析不完整',
  cdc_event_key_invalid:'资料标识无效',cdc_event_revision_invalid:'资料版本无效',cdc_event_operation_invalid:'事件类型无效',
  cdc_target_changed_or_unavailable:'对应资料已变更或不可用',cdc_entity_revision_conflict:'同一版本的内容不一致',
  cdc_event_identity_conflict:'事件标识对应的内容已变化',cdc_document_ingest_rejected:'资料未能保存',
  cdc_dense_configuration_requires_manual_update:'资料的编码设置已变化',cdc_blocked_event_limit:'待处理事件过多',
  cdc_sparse_configuration_requires_manual_update:'资料的编码设置已变化',
  cdc_multivector_configuration_requires_manual_update:'资料的编码设置已变化',
  cdc_event_history_limit:'同步记录已达到上限',cdc_ack_unconfirmed:'源数据库确认结果尚未确定',cdc_processing_failed:'资料处理未完成',
  cdc_blocked_events:'有事件需要处理',cdc_event_not_blocked:'事件状态已变化',
})
const statuses:Record<string,string>=uiDefinition({queued:'等待同步',running:'正在同步',completed:'同步完成',failed:'同步未完成',canceled:'已停止'})
const snapshots:Record<string,string>=uiDefinition({not_observed:'尚未收到初始快照',in_progress:'正在同步初始快照',complete:'初始快照已同步',source_incomplete:'初始快照不完整'})
const errorText=(code:string|null|undefined)=>code?(errors[code]||t('同步未完成')):''

export default function SourceCdcPanel({group,groups,onChanged}:{group:string;groups:string[];onChanged:()=>Promise<void>}){
  useLocale()
  const client=useQueryClient(),[adding,setAdding]=useState(false),[endpoint,setEndpoint]=useState(''),[name,setName]=useState(''),
    [groupName,setGroupName]=useState(group||t('我的资料')),[username,setUsername]=useState(''),[password,setPassword]=useState(''),
    [interval,setInterval]=useState(60),[enabled,setEnabled]=useState(false),[busy,setBusy]=useState(''),[error,setError]=useState(''),
    [eventConnection,setEventConnection]=useState<string|null>(null),[credentialConnection,setCredentialConnection]=useState<string|null>(null),
    [nextUser,setNextUser]=useState(''),[nextPassword,setNextPassword]=useState('')
  const guard=useRef(false),ids=useRef<Record<string,string>>({}),seen=useRef<Record<string,string>>({})
  const endpoints=useQuery<{items:Endpoint[];encryption_available:boolean}>({queryKey:['cdc-endpoints'],queryFn:({signal})=>collectionRequest('/api/v1/source-cdc/endpoints',{signal})})
  const connections=useQuery<{items:Connection[]}>({queryKey:['cdc-connections'],queryFn:({signal})=>collectionRequest('/api/v1/source-cdc/connections',{signal}),
    refetchInterval:value=>value.state.data?.items.some(item=>['queued','running'].includes(item.latest_run?.status||''))?2500:30000})
  const events=useQuery<{items:Event[];has_more:boolean}>({queryKey:['cdc-events',eventConnection],enabled:!!eventConnection,
    queryFn:({signal})=>collectionRequest(`/api/v1/source-cdc/connections/${eventConnection}/events`,{signal}),refetchInterval:5000})
  useEffect(()=>{
    let updated=false
    for(const item of connections.data?.items||[]){const run=item.latest_run
      if(run?.status==='completed'&&seen.current[item.connection_id]!==run.run_id){
        if(seen.current[item.connection_id]!==undefined&&run.applied>0)updated=true
        seen.current[item.connection_id]=run.run_id
      }else if(seen.current[item.connection_id]===undefined)seen.current[item.connection_id]=''
    }
    if(updated)void onChanged()
  },[connections.data,onChanged])
  const reset=(key:string)=>{delete ids.current[key]}
  async function perform(key:string,work:(requestId:string)=>Promise<unknown>){
    if(guard.current)return false
    guard.current=true;setBusy(key);setError('');ids.current[key]??=crypto.randomUUID()
    try{await work(ids.current[key]);reset(key);await client.invalidateQueries({queryKey:['cdc-connections']});await client.invalidateQueries({queryKey:['cdc-events']});return true}
    catch(problem){const code=problem instanceof Error?problem.message:'';setError(errorText(code)||t('暂时无法完成，请重试'));return false}
    finally{guard.current=false;setBusy('')}
  }
  async function create(){
    if(!endpoint||!name.trim()||!groupName.trim()||!username.trim()||!password){setError(t('请填写连接信息'));return}
    const ok=await perform('create',request_id=>collectionRequest('/api/v1/source-cdc/connections',jsonOptions({request_id,endpoint_id:endpoint,name,group_name:groupName,username,password,interval_seconds:interval,enabled})))
    if(ok){setAdding(false);setPassword('');setUsername('');setName('')}
  }
  async function action(item:Connection,kind:'enable'|'pause'|'delete'|'interval',seconds?:number){
    const key=`${item.connection_id}:${kind}:${item.revision}:${seconds||''}`
    await perform(key,request_id=>collectionRequest(`/api/v1/source-cdc/connections/${item.connection_id}/actions`,jsonOptions({request_id,expected_revision:item.revision,action:kind,...(seconds?{interval_seconds:seconds}:{})})))
  }
  async function run(item:Connection){await perform(`${item.connection_id}:run`,request_id=>collectionRequest(`/api/v1/source-cdc/connections/${item.connection_id}/runs`,jsonOptions({request_id})))}
  async function saveCredentials(item:Connection){
    if(!nextUser.trim()||!nextPassword){setError(t('请填写数据库账号和密码'));return}
    const key=`${item.connection_id}:credentials:${item.revision}`
    if(await perform(key,request_id=>collectionRequest(`/api/v1/source-cdc/connections/${item.connection_id}/credentials`,jsonOptions({request_id,expected_revision:item.revision,username:nextUser,password:nextPassword})))){
      setCredentialConnection(null);setNextUser('');setNextPassword('')
    }
  }
  async function resolve(item:Connection,event:Event,kind:'retry'|'skip'){
    if(kind==='skip'&&!window.confirm(t('跳过此事件后，这次变更不会更新资料。确定跳过吗？')))return
    await perform(`${item.connection_id}:${event.event_id}:${kind}`,request_id=>collectionRequest(`/api/v1/source-cdc/connections/${item.connection_id}/events/${event.event_id}/actions`,jsonOptions({request_id,action:kind})))
  }
  async function prune(item:Connection){
    if(!window.confirm(t('清理 90 天前已确认的同步记录？资料和跳过记录会保留。')))return
    await perform(`${item.connection_id}:prune`,request_id=>collectionRequest(`/api/v1/source-cdc/connections/${item.connection_id}/history/prune`,jsonOptions({request_id})))
  }
  return <div className="source-sync-panel">
    <div className="source-sync-intro"><p>{t('同步已授权数据库中的资料变更。')}</p><button type="button" className="btn-secondary" disabled={!endpoints.data?.items.length||!endpoints.data.encryption_available} onClick={()=>{setAdding(!adding);setError('')}}><Icon name="plus" size={16}/>{adding?t('收起'):t('添加数据库')}</button></div>
    {endpoints.isLoading?<p>{t('正在读取数据库…')}</p>:endpoints.isError?<p role="alert">{t('数据库列表暂时无法读取')}</p>:!endpoints.data?.items.length?<p className="source-sync-empty">{t('暂无分配给你的数据库')}</p>:!endpoints.data.encryption_available&&<p role="alert">{t('请先配置服务端密钥加密')}</p>}
    {adding&&<div className="collection-form source-sync-form">
      <label className="collection-field">{t('选择数据库')}<select value={endpoint} onChange={event=>{setEndpoint(event.target.value);reset('create')}}><option value="">{t('请选择')}</option>{endpoints.data?.items.map(item=><option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
      <div className="collection-columns"><label className="collection-field">{t('连接名称')}<input value={name} maxLength={200} onChange={event=>{setName(event.target.value);reset('create')}}/></label><label className="collection-field">{t('保存到分组')}<input list="cdc-source-groups" value={groupName} maxLength={100} onChange={event=>{setGroupName(event.target.value);reset('create')}}/><datalist id="cdc-source-groups">{groups.map(item=><option key={item} value={item}/>)}</datalist></label></div>
      <div className="collection-columns"><label className="collection-field">{t('数据库账号')}<input autoComplete="off" value={username} maxLength={128} onChange={event=>{setUsername(event.target.value);reset('create')}}/></label><label className="collection-field">{t('数据库密码')}<input type="password" autoComplete="new-password" value={password} maxLength={1024} onChange={event=>{setPassword(event.target.value);reset('create')}}/></label></div>
      <label className="collection-field">{t('同步频率')}<select value={interval} onChange={event=>{setInterval(Number(event.target.value));reset('create')}}><option value={30}>{t('每 30 秒')}</option><option value={60}>{t('每分钟')}</option><option value={300}>{t('每 5 分钟')}</option><option value={900}>{t('每 15 分钟')}</option><option value={3600}>{t('每小时')}</option></select></label>
      <label className="collection-checks"><input type="checkbox" checked={enabled} onChange={event=>{setEnabled(event.target.checked);reset('create')}}/>{t('启用定时同步')}</label>
      <div className="source-sync-form-footer"><span>{t('保存后可立即同步。')}</span><button type="button" className="btn-primary" disabled={!!busy} onClick={()=>void create()}>{busy==='create'?t('保存中…'):t('保存连接')}</button></div>
    </div>}
    {error&&<p role="alert" className="collection-feedback">{uiMessage(error)}</p>}
    {connections.isLoading?<p>{t('正在读取连接…')}</p>:connections.isError?<p role="alert">{t('连接暂时无法读取')}</p>:!connections.data?.items.length?<p className="source-sync-empty">{t('还没有数据库连接')}</p>:<div className="source-sync-list">{connections.data.items.map(item=><article className="source-sync-item" key={item.connection_id}>
      <div className="source-sync-item-head"><div><strong>{item.name}</strong><small>{item.group_name} · {endpoints.data?.items.find(endpointItem=>endpointItem.id===item.endpoint_id)?.label||t('数据库连接')}</small></div><span className="collection-status">{item.enabled?t('定时同步中'):t('已暂停')}</span></div>
      <p>{item.latest_run?statuses[item.latest_run.status]||t('同步记录'):t('尚未同步')}{item.latest_run?.error_category?' · '+errorText(item.latest_run.error_category):''}{item.last_error?' · '+errorText(item.last_error):''}</p>
      <small>{snapshots[item.snapshot_status]||t('尚未收到初始快照')}{item.snapshot_rows!==null?' · '+t('{0} 条资料',item.snapshot_rows):''}{item.snapshot_pending? ' · '+t('剩余 {0} 条',item.snapshot_pending):''}</small>
      <div className="source-sync-actions"><button type="button" className="btn-secondary" disabled={!!busy||['queued','running'].includes(item.latest_run?.status||'')} onClick={()=>void run(item)}>{t('立即同步')}</button>
        <select aria-label={t('调整同步频率')} value={item.interval_seconds} disabled={!!busy} onChange={event=>void action(item,'interval',Number(event.target.value))}>{![30,60,300,900,3600].includes(item.interval_seconds)&&<option value={item.interval_seconds}>{t('每 {0} 秒',item.interval_seconds)}</option>}<option value={30}>{t('每 30 秒')}</option><option value={60}>{t('每分钟')}</option><option value={300}>{t('每 5 分钟')}</option><option value={900}>{t('每 15 分钟')}</option><option value={3600}>{t('每小时')}</option></select>
        <button type="button" className="btn-ghost" disabled={!!busy} onClick={()=>void action(item,item.enabled?'pause':'enable')}>{item.enabled?t('暂停连接'):t('启用定时')}</button>
        <button type="button" className="btn-ghost" onClick={()=>{setCredentialConnection(credentialConnection===item.connection_id?null:item.connection_id);setNextUser('');setNextPassword('')}}>{t('更新凭据')}</button>
        <button type="button" className="btn-ghost" onClick={()=>setEventConnection(eventConnection===item.connection_id?null:item.connection_id)}>{t('待处理事件')}{item.blocked_events?` (${item.blocked_events})`:''}</button>
        <button type="button" className="btn-ghost" disabled={!!busy} onClick={()=>void action(item,'delete')}>{t('移除连接')}</button></div>
      {credentialConnection===item.connection_id&&<div className="source-sync-history"><p>{t('连接 ID')} · {item.connection_id}</p><div className="collection-columns"><label className="collection-field">{t('数据库账号')}<input autoComplete="off" value={nextUser} onChange={event=>{setNextUser(event.target.value);reset(`${item.connection_id}:credentials:${item.revision}`)}}/></label><label className="collection-field">{t('数据库密码')}<input type="password" autoComplete="new-password" value={nextPassword} onChange={event=>{setNextPassword(event.target.value);reset(`${item.connection_id}:credentials:${item.revision}`)}}/></label></div><button type="button" className="btn-secondary" disabled={!!busy} onClick={()=>void saveCredentials(item)}>{t('保存凭据')}</button></div>}
      {eventConnection===item.connection_id&&<div className="source-sync-history">{events.isLoading?<p>{t('正在读取事件…')}</p>:events.isError?<p>{t('事件暂时无法读取')}</p>:!events.data?.items.length?<p>{t('没有待处理事件')}</p>:events.data.items.map(event=><div key={event.event_id}><p>{event.document_key||t('未知资料')} · {t('版本 {0}',event.revision)} · {event.status==='blocked'?errorText(event.error_category):event.status==='skipped'?t('已跳过'):t('等待重新处理')}</p>{event.status==='blocked'&&<div className="source-sync-actions"><button type="button" className="btn-secondary" disabled={!!busy} onClick={()=>void resolve(item,event,'retry')}>{t('重新处理')}</button><button type="button" className="btn-ghost" disabled={!!busy} onClick={()=>void resolve(item,event,'skip')}>{t('跳过事件')}</button></div>}</div>)}{events.data?.has_more&&<p>{t('还有更多事件')}</p>}<button type="button" className="btn-ghost" disabled={!!busy} onClick={()=>void prune(item)}>{t('清理旧同步记录')}</button></div>}
    </article>)}</div>}
  </div>
}
