import {useState,type FormEvent} from 'react'
import {useQuery,useQueryClient} from '@tanstack/react-query'
import {t,uiMessage,useLocale} from '../i18n'

async function post(path:string,body:unknown) {
  const response=await fetch('/api/v1/auth'+path,{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
  const value=await response.json().catch(()=>({}))
  if(!response.ok) {
    const messages:Record<string,string>={invalid_credentials:t('当前密码不正确。'),email_authentication_required:t('请重新登录后再试。'),
      email_invalid:t('请输入有效邮箱。'),email_unavailable:t('该邮箱无法绑定。'),email_challenge_invalid:t('验证码无效或已过期。'),
      email_rate_limited:t('操作较频繁，请稍后再试。'),email_service_unavailable:t('邮箱服务尚未配置。'),email_delivery_unavailable:t('邮件发送失败，请稍后重试。')}
    throw new Error(messages[String(value.detail)]||t('操作未完成，请重试。'))
  }
  return value
}

export function PasswordRecovery({available,onBack}:{available:boolean;onBack:()=>void}) {
  useLocale()
  const [step,setStep]=useState<'email'|'reset'|'done'>('email')
  const [email,setEmail]=useState(''),[token,setToken]=useState(''),[password,setPassword]=useState(''),[confirm,setConfirm]=useState('')
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[sent,setSent]=useState(false)
  async function submit(event:FormEvent) {
    event.preventDefault();setError('')
    if(step==='reset'&&(password!==confirm||new TextEncoder().encode(password).length>72)) {
      setError(password!==confirm?t('两次输入的新密码不一致。'):t('密码请控制在 72 字节以内。'));return
    }
    setBusy(true)
    try {
      if(step==='email') {await post('/password/forgot',{email:email.trim()});setSent(true);setStep('reset')}
      else {await post('/password/reset',{token:token.trim(),new_password:password});setToken('');setPassword('');setConfirm('');setStep('done')}
    } catch(cause) {setError(cause instanceof Error?uiMessage(cause.message):t('操作未完成，请重试。'))}
    finally {setBusy(false)}
  }
  return <div className="space-y-4">
    {step==='done'?<p role="status">{t('密码已更新，请重新登录。')}</p>:<>
      {!available&&step==='email'&&<p>{t('邮箱服务尚未配置。')}</p>}
      {step==='reset'&&sent&&<p role="status" className="field-hint">{t('如果该邮箱已绑定账号，邮件将发送至该邮箱。')}</p>}
      {(available||step==='reset')&&<form className="account-form" onSubmit={submit}>
        {step==='email'?<label>{t('已绑定邮箱')}<input className="input-xm" type="email" autoComplete="email" value={email} onChange={event=>setEmail(event.target.value)} maxLength={254} required/></label>:<>
          <label>{t('邮件验证码')}<input className="input-xm" autoComplete="one-time-code" spellCheck={false} value={token} onChange={event=>setToken(event.target.value)} maxLength={256} required/></label>
          <label>{t('新密码')}<input className="input-xm" type="password" autoComplete="new-password" value={password} onChange={event=>setPassword(event.target.value)} minLength={12} required/></label>
          <label>{t('确认新密码')}<input className="input-xm" type="password" autoComplete="new-password" value={confirm} onChange={event=>setConfirm(event.target.value)} minLength={12} required/></label>
        </>}
        {error&&<p role="alert">{uiMessage(error)}</p>}
        <button type="submit" className="btn-primary" disabled={busy}>{busy?t('正在提交…'):step==='email'?t('发送验证码'):t('重置密码')}</button>
      </form>}
      <button type="button" className="btn-ghost text-sm" onClick={()=>{setError('');setStep(step==='email'?'reset':'email')}}>{step==='email'?t('我已有验证码'):t('重新发送验证码')}</button>
    </>}
    <button type="button" className="btn-ghost text-sm" onClick={onBack}>{t('返回登录')}</button>
  </div>
}

export function EmailSettings({ownerId}:{ownerId:string}) {
  useLocale()
  const client=useQueryClient()
  const state=useQuery<{email:{address:string;verified_at:string}|null;available:boolean}>({queryKey:['account-email',ownerId],queryFn:async()=>{
    const response=await fetch('/api/v1/auth/email',{credentials:'include'});if(!response.ok)throw new Error(t('邮箱信息读取失败。'));return response.json()}})
  const [editing,setEditing]=useState(false),[verify,setVerify]=useState(false),[email,setEmail]=useState(''),[password,setPassword]=useState(''),[token,setToken]=useState('')
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('')
  async function submit(event:FormEvent) {
    event.preventDefault();setBusy(true);setError('');setMessage('')
    try {
      if(!verify) {await post('/email/verification',{email:email.trim(),current_password:password});setPassword('');setVerify(true);setMessage(t('验证码已发送，请查看邮箱。'))}
      else {await post('/email/verify',{token:token.trim()});setToken('');setEmail('');setVerify(false);setEditing(false);setMessage(t('邮箱已验证。'));await client.invalidateQueries({queryKey:['account-email',ownerId]})}
    } catch(cause) {setError(cause instanceof Error?uiMessage(cause.message):t('操作未完成，请重试。'))}
    finally {setBusy(false)}
  }
  return <section className="account-card"><h2>{t('邮箱与找回')}</h2>
    {state.isPending&&<p className="field-hint">{t('正在读取…')}</p>}
    {state.error&&<p role="alert">{uiMessage(state.error.message)}</p>}
    {state.data&&<>
      <p>{state.data.email?state.data.email.address:t('尚未绑定邮箱')}</p>
      <p className="field-hint mt-2">{state.data.available?t('验证后可用于找回密码。'):t('邮箱服务尚未配置。')}</p>
      {!editing&&<button type="button" className="btn-secondary mt-4" disabled={!state.data.available} onClick={()=>{setEditing(true);setError('');setMessage('')}}>{state.data.email?t('更换邮箱'):t('绑定邮箱')}</button>}
      {editing&&<form onSubmit={submit} className="account-form mt-4">
        {!verify?<><label>{t('邮箱')}<input className="input-xm" type="email" autoComplete="email" maxLength={254} required value={email} onChange={event=>setEmail(event.target.value)}/></label>
          <label>{t('当前密码')}<input className="input-xm" type="password" autoComplete="current-password" required value={password} onChange={event=>setPassword(event.target.value)}/></label></>:<label>{t('邮件验证码')}<input className="input-xm" autoComplete="one-time-code" spellCheck={false} maxLength={256} required value={token} onChange={event=>setToken(event.target.value)}/></label>}
        <div className="account-actions"><button className="btn-primary" type="submit" disabled={busy}>{busy?t('正在提交…'):verify?t('验证邮箱'):t('发送验证码')}</button>
          <button className="btn-ghost" type="button" disabled={busy} onClick={()=>{setEditing(false);setVerify(false);setPassword('');setToken('');setError('');setMessage('')}}>{t('取消')}</button></div>
      </form>}
    </>}
    {message&&<p role="status" className="field-hint mt-3">{message}</p>}{error&&<p role="alert" className="mt-3">{uiMessage(error)}</p>}
  </section>
}
