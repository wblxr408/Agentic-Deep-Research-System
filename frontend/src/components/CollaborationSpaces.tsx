import {useRef,useState,type FormEvent} from 'react'
import {useQuery,useQueryClient} from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {t,uiMessage,useLocale} from '../i18n'

type Space={id:string;name:string;owner_id:string;role:'owner'|'member'}
type Invitation={id:string;workspace_name:string;inviter:string}
type Detail={id:string;name:string;role:'owner'|'member';members:{id:string;username:string;role:'owner'|'member'}[];invitations:{id:string;username:string}[]}
type Choice={resource_id:string;version:string;title:string;sequence?:number;status?:string}
type Choices={reports:Choice[];documents:Choice[]}
type Share={id:string;type:'report'|'document';owner_id:string;owner:string;title:string|null;available:boolean}
type SharedContent={id:string;type:'report'|'document';owner:string;title:string;content:string;report_status?:string}

async function request<T>(path:string, init?:RequestInit):Promise<T> {
  const response=await fetch('/api/v1/workspaces'+path,{credentials:'include',...init})
  const value=await response.json().catch(()=>({})) as {detail?:string}
  if (!response.ok) {
    if(response.status===401)window.dispatchEvent(new Event('deepintel:session-expired'))
    const messages:Record<string,string>={workspace_not_found:'空间不存在或已不可访问。',workspace_account_not_found:'没有找到该账号。',
      workspace_resource_not_found:'内容已不可访问，请刷新后重试。',workspace_member_not_found:'成员已不可访问。',
      workspace_invitation_not_found:'邀请已不可访问。',workspace_invitation_closed:'邀请已处理。',workspace_invitation_expired:'邀请已过期。',
      workspace_already_member:'该账号已是成员。',workspace_invitation_exists:'该账号已有待处理邀请。',workspace_share_exists:'该版本已经分享。',
      workspace_owner_required:'只有空间所有者可以操作。',workspace_owner_cannot_leave:'所有者可归档空间。',
      workspace_member_limit:'空间成员已达上限。',workspace_limit:'空间已达上限。',workspace_share_limit:'分享已达上限。',
      workspace_request_conflict:'操作内容已变化，请重新提交。'}
    throw new Error(t(messages[String(value.detail)]||'操作未完成，请重试。'))
  }
  return value as T
}

function SharedReader({ownerId,spaceId,shareId,onClose}:{ownerId:string;spaceId:string;shareId:string;onClose:()=>void}) {
  const result=useQuery({queryKey:['collaboration',ownerId,spaceId,'content',shareId],
    queryFn:({signal})=>request<SharedContent>(`/${spaceId}/shares/${shareId}`,{signal}),
    staleTime:0,refetchOnMount:'always',refetchInterval:30000,retry:false})
  return <div className="shared-reader" aria-label={t('共享内容')}>
    <div className="shared-reader-heading"><div><p className="field-hint">{t('共享内容')}</p><h3>{result.data?.title||t('正在读取…')}</h3></div>
      <button type="button" className="btn-ghost" onClick={onClose}>{t('关闭')}</button></div>
    {result.isFetching&&<p role="status">{t('正在读取…')}</p>}
    {result.error&&<p role="alert">{uiMessage(result.error.message)}</p>}
    {!result.isFetching&&!result.error&&result.data&&<>
      <p className="field-hint">{t('分享者：{0}',result.data.owner)}{result.data.report_status==='saved_draft'?` · ${t('草稿')}`:''}</p>
      {result.data.type==='report'?<article className="shared-reader-body"><ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml
        components={{a:({children})=><span>{children}</span>,img:({alt})=><span>{alt||t('图像')}</span>}}>{result.data.content}</ReactMarkdown></article>
        :<pre className="shared-document">{result.data.content}</pre>}
    </>}
  </div>
}

function SpaceDetail({ownerId,space,onAction}:{ownerId:string;space:Space;onAction:(path:string,method:string,body?:Record<string,unknown>,withId?:boolean)=>Promise<boolean>}) {
  const [username,setUsername]=useState(''),[choice,setChoice]=useState(''),[opened,setOpened]=useState<string|null>(null)
  const detail=useQuery({queryKey:['collaboration',ownerId,space.id,'detail'],queryFn:({signal})=>request<Detail>(`/${space.id}`,{signal}),staleTime:0,refetchOnMount:'always',refetchInterval:30000,retry:false})
  const available=useQuery({queryKey:['collaboration',ownerId,space.id,'available'],queryFn:({signal})=>request<Choices>(`/${space.id}/shareable`,{signal}),staleTime:0,refetchOnMount:'always',refetchInterval:30000,retry:false})
  const shared=useQuery({queryKey:['collaboration',ownerId,space.id,'shares'],queryFn:({signal})=>request<{items:Share[]}>(`/${space.id}/shares`,{signal}),staleTime:0,refetchOnMount:'always',refetchInterval:30000,retry:false})
  const options=[...(available.data?.reports||[]).map(item=>({kind:'report' as const,...item})),
    ...(available.data?.documents||[]).map(item=>({kind:'document' as const,...item}))]
  const selected=options.find(item=>JSON.stringify([item.kind,item.resource_id,item.version])===choice)
  async function invite(event:FormEvent) {event.preventDefault();if(await onAction(`/${space.id}/invitations`,'POST',{username:username.trim()},true))setUsername('')}
  async function share(event:FormEvent) {
    event.preventDefault();const item=selected
    if(!item)return
    if(await onAction(`/${space.id}/shares`,'POST',{resource_type:item.kind,resource_id:item.resource_id,version:item.version},true))setChoice('')
  }
  return <div className="collaboration-detail">
    <div className="collaboration-detail-heading"><div><p className="field-hint">{space.role==='owner'?t('所有者'):t('成员')}</p><h3>{space.name}</h3></div>
      {space.role==='owner'?<button type="button" className="btn-ghost" onClick={()=>void onAction(`/${space.id}`,'DELETE')}>{t('归档空间')}</button>
        :<button type="button" className="btn-ghost" onClick={()=>void onAction(`/${space.id}/members/${ownerId}`,'DELETE')}>{t('退出空间')}</button>}</div>
    {detail.error&&<p role="alert">{uiMessage(detail.error.message)}</p>}
    {detail.data&&<><h4>{t('成员')}</h4><div className="collaboration-list">
      {detail.data.members.map(member=><div className="collaboration-row" key={member.id}><span>{member.username} <small>{member.role==='owner'?t('所有者'):t('成员')}</small></span>
        {space.role==='owner'&&member.id!==ownerId&&<button type="button" className="btn-ghost" onClick={()=>void onAction(`/${space.id}/members/${member.id}`,'DELETE')}>{t('移除')}</button>}</div>)}
      {detail.data.invitations.map(invitation=><div className="collaboration-row" key={invitation.id}><span>{invitation.username} <small>{t('等待接受')}</small></span>
        <button type="button" className="btn-ghost" onClick={()=>void onAction(`/${space.id}/invitations/${invitation.id}`,'DELETE')}>{t('撤回邀请')}</button></div>)}
    </div>
    {space.role==='owner'&&<form className="collaboration-inline-form" onSubmit={invite}><label className="sr-only" htmlFor="workspace-invite">{t('邀请账号')}</label>
      <input id="workspace-invite" className="input-xm" value={username} onChange={event=>setUsername(event.target.value)} placeholder={t('输入用户名')} minLength={3} maxLength={120} required/>
      <button type="submit" className="btn-secondary">{t('邀请')}</button></form>}</>}
    <h4>{t('共享内容')}</h4><p className="field-hint">{t('仅共享所选正文，不共享私人来源。')}</p>
    {available.error&&<p role="alert">{uiMessage(available.error.message)}</p>}
    {available.data&&<form className="collaboration-inline-form" onSubmit={share}><label className="sr-only" htmlFor="workspace-share">{t('选择本人内容')}</label>
      <select id="workspace-share" className="input-xm" value={choice} onChange={event=>setChoice(event.target.value)} required>
        <option value="">{t('选择本人内容')}</option>{options.map(item=><option key={`${item.kind}:${item.resource_id}:${item.version}`} value={JSON.stringify([item.kind,item.resource_id,item.version])}>
          {item.kind==='report'?t('报告'):t('资料')} · {item.title}{item.sequence?` · ${t('版本 {0}',item.sequence)}`:''}{item.status==='saved_draft'?` · ${t('草稿')}`:''}</option>)}</select>
      <button type="submit" className="btn-secondary" disabled={!selected}>{t('分享')}</button></form>}
    {available.data&&<p className="field-hint">{t('资料需允许跨任务复用，列表显示最近 200 项。')}</p>}
    {shared.error&&<p role="alert">{uiMessage(shared.error.message)}</p>}
    {shared.data&&<div className="collaboration-list">{shared.data.items.length===0&&<p className="field-hint">{t('还没有共享内容。')}</p>}
      {shared.data.items.map(item=><div className="collaboration-row" key={item.id}><div><strong>{item.title||t('内容已不可用')}</strong>
        <small>{item.type==='report'?t('报告'):t('资料')} · {item.owner}</small></div><div className="account-actions">
          {item.available&&<button type="button" className="btn-ghost" onClick={()=>setOpened(item.id)}>{t('查看')}</button>}
          {item.owner_id===ownerId&&<button type="button" className="btn-ghost" onClick={()=>{if(opened===item.id)setOpened(null);void onAction(`/${space.id}/shares/${item.id}`,'DELETE')}}>{t('撤回')}</button>}</div></div>)}
    </div>}
    {opened&&<SharedReader key={opened} ownerId={ownerId} spaceId={space.id} shareId={opened} onClose={()=>setOpened(null)}/>}
  </div>
}

export default function CollaborationSpaces({ownerId}:{ownerId:string}) {
  useLocale()
  const client=useQueryClient(), requests=useRef(new Map<string,string>())
  const [spaceId,setSpaceId]=useState<string|null>(null),[name,setName]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false)
  const spaces=useQuery({queryKey:['collaboration',ownerId,'spaces'],queryFn:({signal})=>request<{items:Space[]}>('',{signal}),staleTime:0,refetchOnMount:'always',refetchInterval:30000,retry:false})
  const invites=useQuery({queryKey:['collaboration',ownerId,'invitations'],queryFn:({signal})=>request<{items:Invitation[]}>('/invitations',{signal}),staleTime:0,refetchOnMount:'always',refetchInterval:30000,retry:false})
  const selected=spaces.data?.items.find(item=>item.id===spaceId)
  async function action(path:string,method:string,body?:Record<string,unknown>,withId=false) {
    if(busy)return false
    setBusy(true);setError('')
    const key=JSON.stringify([path,method,body]),requestId=requests.current.get(key)||crypto.randomUUID()
    if(withId)requests.current.set(key,requestId)
    try {
      await request(path,{method,...(body?{headers:{'Content-Type':'application/json'},body:JSON.stringify(withId?{...body,request_id:requestId}:body)}:{})})
      requests.current.delete(key);await client.invalidateQueries({queryKey:['collaboration',ownerId]});return true
    } catch(cause) {setError(cause instanceof Error?cause.message:t('操作未完成，请重试。'));return false}
    finally {setBusy(false)}
  }
  async function create(event:FormEvent) {event.preventDefault();if(await action('','POST',{name:name.trim()},true))setName('')}
  return <section className="account-card collaboration-card" aria-busy={busy}><div className="account-list-heading"><h2>{t('协作空间')}</h2></div>
    <p className="field-hint">{t('邀请成员，分享选定的报告与资料。')}</p>
    {(spaces.error||invites.error||error)&&<p role="alert" className="mt-3">{uiMessage(error||spaces.error?.message||invites.error?.message||'')}</p>}
    {(invites.data?.items||[]).map(invitation=><div className="collaboration-row" key={invitation.id}><div><strong>{invitation.workspace_name}</strong><small>{t('{0} 邀请你加入',invitation.inviter)}</small></div>
      <div className="account-actions"><button type="button" className="btn-secondary" disabled={busy} onClick={()=>void action(`/invitations/${invitation.id}/accept`,'POST')}>{t('接受')}</button>
        <button type="button" className="btn-ghost" disabled={busy} onClick={()=>void action(`/invitations/${invitation.id}/decline`,'POST')}>{t('拒绝')}</button></div></div>)}
    <form className="collaboration-inline-form" onSubmit={create}><label className="sr-only" htmlFor="workspace-name">{t('空间名称')}</label>
      <input id="workspace-name" className="input-xm" value={name} onChange={event=>setName(event.target.value)} placeholder={t('空间名称')} maxLength={120} required/>
      <button className="btn-secondary" type="submit" disabled={busy}>{t('创建空间')}</button></form>
    <div className="collaboration-spaces">{spaces.data?.items.map(space=><button type="button" key={space.id} className={space.id===spaceId?'active':''} aria-pressed={space.id===spaceId} onClick={()=>setSpaceId(space.id)}>
      {space.name}<small>{space.role==='owner'?t('所有者'):t('成员')}</small></button>)}</div>
    {spaces.data?.items.length===0&&<p className="field-hint">{t('还没有协作空间。')}</p>}
    {selected&&<SpaceDetail key={selected.id} ownerId={ownerId} space={selected} onAction={action}/>}
  </section>
}
