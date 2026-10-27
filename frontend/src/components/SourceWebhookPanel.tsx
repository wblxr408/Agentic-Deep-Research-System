import {useRef,useState} from 'react'
import {useQuery,useQueryClient} from '@tanstack/react-query'
import {t,uiMessage,useLocale} from '../i18n'
import {collectionRequest,jsonOptions} from './CollectionUI'

interface Settings {supported:boolean;encryption_available:boolean;webhook:{webhook_id:string;callback_path:string}|null;
  latest_event:{received_at:string;status:string}|null;retained_events:number;removable_events:number;reception_status:string}

function newSecret(){
  const bytes=crypto.getRandomValues(new Uint8Array(32))
  return [...bytes].map(value=>value.toString(16).padStart(2,'0')).join('')
}

export default function SourceWebhookPanel({subscriptionId}:{subscriptionId:string}){
  useLocale()
  const client=useQueryClient(),[busy,setBusy]=useState(false),[error,setError]=useState(''),[secret,setSecret]=useState(''),[copied,setCopied]=useState('')
  const guard=useRef(false),operation=useRef<{request_id:string;secret:string}|null>(null),pruneId=useRef<string|null>(null)
  const query=useQuery<Settings>({queryKey:['source-webhook',subscriptionId],
    queryFn:({signal})=>collectionRequest(`/api/v1/source-sync/subscriptions/${subscriptionId}/webhook`,{signal})})
  async function enable(){
    if(guard.current)return
    guard.current=true;setBusy(true);setError('')
    try{
      operation.current??={request_id:crypto.randomUUID(),secret:newSecret()}
      const value=operation.current
      await collectionRequest(`/api/v1/source-sync/subscriptions/${subscriptionId}/webhook`,jsonOptions(value))
      setSecret(value.secret);operation.current=null;await client.invalidateQueries({queryKey:['source-webhook',subscriptionId]})
    }catch(problem){const code=problem instanceof Error?problem.message:''
      setError(code==='source_webhook_encryption_unavailable'?t("请先配置服务端密钥加密"):
        code==='source_webhook_already_enabled'?t("事件通知已启用，请重新读取设置"):t("暂时无法完成，请重试"))}
    finally{guard.current=false;setBusy(false)}
  }
  async function revoke(){
    if(guard.current||!query.data?.webhook)return
    guard.current=true;setBusy(true);setError('')
    try{await collectionRequest(`/api/v1/source-sync/subscriptions/${subscriptionId}/webhook/${query.data.webhook.webhook_id}`,{method:'DELETE'})
      setSecret('');operation.current=null;await client.invalidateQueries({queryKey:['source-webhook',subscriptionId]})
    }catch{setError(t("暂时无法完成，请重试"))}finally{guard.current=false;setBusy(false)}
  }
  async function copy(value:string,which:string){
    try{await navigator.clipboard.writeText(value);setCopied(which)}catch{setError(t("无法复制，请手动选择内容"))}
  }
  async function prune(){
    if(guard.current)return
    guard.current=true;setBusy(true);setError('');pruneId.current??=crypto.randomUUID()
    try{await collectionRequest(`/api/v1/source-sync/subscriptions/${subscriptionId}/webhook/events/prune`,jsonOptions({request_id:pruneId.current}))
      pruneId.current=null;await client.invalidateQueries({queryKey:['source-webhook',subscriptionId]})
    }catch{setError(t("暂时无法完成，请重试"))}finally{guard.current=false;setBusy(false)}
  }
  if(query.isPending)return <p>{t("正在读取设置…")}</p>
  if(query.isError||!query.data)return <p role="alert">{t("设置暂时无法读取")}</p>
  if(!query.data.supported)return <p>{t("GitHub 通知适用于 GitHub 仓库来源。")}</p>
  const callback=query.data.webhook?window.location.origin+query.data.webhook.callback_path:''
  return <div className="source-webhook">
    {query.data.webhook?<><p>{t("在 GitHub 仓库的 Webhooks 设置中填入地址和密钥，选择 JSON 与 push 事件。")}</p>
      <label className="collection-field">{t("回调地址")}<span className="source-webhook-copy"><input value={callback} readOnly/><button type="button" className="btn-ghost" onClick={()=>void copy(callback,'url')}>{copied==='url'?t("已复制"):t("复制")}</button></span></label>
      {secret?<label className="collection-field">{t("本次密钥")}<span className="source-webhook-copy"><input type="text" value={secret} readOnly autoComplete="off"/><button type="button" className="btn-ghost" onClick={()=>void copy(secret,'secret')}>{copied==='secret'?t("已复制"):t("复制")}</button></span><small>{t("密钥仅在本次显示；丢失后可撤销并重新启用。")}</small></label>:<p>{t("密钥已保存；如需更换，请撤销后重新启用。")}</p>}
      <p>{t("外部推送需要可访问的 HTTPS 地址。")}</p><button type="button" className="btn-ghost collection-danger" disabled={busy} onClick={()=>void revoke()}>{t("撤销事件通知")}</button></>:
      <><p>{t("仓库收到 push 时，自动同步这条已登记的来源。")}</p>
        {!query.data.encryption_available&&<p>{t("请先配置服务端密钥加密")}</p>}
        <button type="button" className="btn-secondary" disabled={busy||!query.data.encryption_available} onClick={()=>void enable()}>{busy?t("保存中…"):t("启用 GitHub 通知")}</button></>}
    {!!query.data.retained_events&&<p>{t("已保存 {0} 条通知记录",query.data.retained_events)}</p>}
    {query.data.reception_status==='history_limit'&&<p role="status">{t("通知记录已满，可清理 90 天前的记录。")}</p>}
    {query.data.reception_status==='rate_limit'&&<p role="status">{t("通知过于频繁，请稍后再试。")}</p>}
    {query.data.removable_events>0&&<><p>{t("清理后，旧通知可能再次触发同步。")}</p><button type="button" className="btn-ghost" disabled={busy} onClick={()=>void prune()}>{t("清理 90 天前的通知记录")}</button></>}
    {error&&<p role="alert">{uiMessage(error)}</p>}
  </div>
}
