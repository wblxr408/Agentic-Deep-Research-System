import {useState,type FormEvent} from 'react'
import {useQuery,useQueryClient} from '@tanstack/react-query'
import {t,uiMessage,useLocale} from '../i18n'

type Connection={configured:boolean;enabled:boolean;updated_at?:string;encryption_available:boolean;verified:boolean}

async function connection<T>(method:string,body?:unknown,signal?:AbortSignal):Promise<T> {
  const response=await fetch('/api/v1/connections/github',{method,credentials:'include',signal,
    ...(body?{headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{})})
  const value=await response.json().catch(()=>({})) as {detail?:string}
  if(!response.ok){
    if(response.status===401)window.dispatchEvent(new Event('deepintel:session-expired'))
    const messages:Record<string,string>={personal_connection_not_configured:'请先保存访问令牌。',
      personal_connection_encryption_unavailable:'服务端尚未配置凭据加密。',personal_connection_unavailable:'个人连接暂不可用。',
      invalid_personal_credential:'令牌格式不正确。',state_unavailable:'个人连接暂不可用。'}
    throw new Error(t(messages[String(value.detail)]||'操作未完成，请重试。'))
  }
  return value as T
}

export default function PersonalConnections({ownerId}:{ownerId:string}) {
  useLocale()
  const client=useQueryClient(),[editing,setEditing]=useState(false),[token,setToken]=useState(''),[enable,setEnable]=useState(false)
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('')
  const state=useQuery({queryKey:['personal-connection',ownerId,'github'],queryFn:({signal})=>connection<Connection>('GET',undefined,signal),retry:false})
  async function change(method:string,body?:unknown){
    if(busy)return false
    setBusy(true);setError('');setMessage('')
    try {await connection(method,body);await client.invalidateQueries({queryKey:['personal-connection',ownerId,'github']});return true}
    catch(cause){setError(cause instanceof Error?cause.message:t('操作未完成，请重试。'));return false}
    finally{setBusy(false)}
  }
  async function save(event:FormEvent){
    event.preventDefault()
    if(await change('PUT',{token,enabled:enable})){setToken('');setEditing(false);setMessage(t('令牌已保存。'))}
  }
  async function revoke(){if(await change('DELETE')){setToken('');setEditing(false);setMessage(t('连接已撤销。'))}}
  return <section className="account-card personal-connection"><div className="account-list-heading"><h2>{t('个人平台连接')}</h2></div>
    <p className="field-hint">{t('使用自己的账号读取 GitHub 仓库与 README。')}</p>
    {state.isPending&&<p className="field-hint mt-3">{t('正在读取…')}</p>}
    {state.error&&<p role="alert" className="mt-3">{uiMessage(state.error.message)}</p>}
    {state.data&&<div className="personal-connection-row"><div><strong>GitHub</strong><p className="field-hint">
      {!state.data.encryption_available?t('服务端尚未配置凭据加密。'):state.data.configured
        ?state.data.enabled?t('已启用 · 令牌尚未验证'):t('已保存 · 未启用'):t('尚未连接')}</p></div>
      {!editing&&<div className="account-actions"><button type="button" className="btn-secondary" disabled={busy||!state.data.encryption_available} onClick={()=>{setEditing(true);setEnable(state.data?.enabled||false);setError('');setMessage('')}}>
        {state.data.configured?t('替换令牌'):t('添加令牌')}</button>
        {state.data.configured&&<><button type="button" className="btn-ghost" disabled={busy||(!state.data.encryption_available&&!state.data.enabled)}
          onClick={()=>void change('PATCH',{enabled:!state.data?.enabled})}>{state.data.enabled?t('暂停使用'):t('启用')}</button>
          <button type="button" className="btn-ghost" disabled={busy} onClick={()=>void revoke()}>{t('撤销连接')}</button></>}</div>}
    </div>}
    {editing&&<form className="account-form mt-4" onSubmit={save}>
      <label>{t('GitHub 访问令牌')}<input className="input-xm" type="password" autoComplete="new-password" spellCheck={false} minLength={20} maxLength={512} required value={token} onChange={event=>setToken(event.target.value)}/></label>
      <p className="field-hint">{t('仅需仓库元数据和内容读取权限。')}</p>
      <label className="personal-connection-check"><input type="checkbox" checked={enable} onChange={event=>setEnable(event.target.checked)}/>{t('保存后启用')}</label>
      <div className="account-actions"><button type="submit" className="btn-primary" disabled={busy}>{t('保存')}</button>
        <button type="button" className="btn-ghost" disabled={busy} onClick={()=>{setToken('');setEditing(false);setError('')}}>{t('取消')}</button></div>
    </form>}
    {message&&<p role="status" className="field-hint mt-3">{uiMessage(message)}</p>}{error&&<p role="alert" className="mt-3">{uiMessage(error)}</p>}
  </section>
}
