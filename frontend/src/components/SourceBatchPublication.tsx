import {useLocale,t,uiMessage} from '../i18n'
import {useRef,useState} from 'react'
import {useMutation} from '@tanstack/react-query'
interface Member {source_id:string;expected_revision:number;label:string}
interface Body {request_id:string;members:{source_id:string;expected_revision:number}[];reason:string}
export default function SourceBatchPublication({sourceIds,onChanged,sourceNames={}}:{sourceIds:string[];sourceNames?:Record<string,string>;onChanged:()=>Promise<void>}) {
  useLocale()

  const [members,setMembers]=useState<Member[]>([]),[reason,setReason]=useState(''),[error,setError]=useState('')
  const pending=useRef<Body|null>(null)
  const prepare=useMutation({mutationFn:async()=>{
    if(pending.current)throw new Error(t("先确认上一请求结果，再重新选择批次。"))
    if(!sourceIds.length||sourceIds.length>20)throw new Error(t("请在来源列表选择1至20项。"))
    const current=await Promise.all(sourceIds.map(async id=>{const response=await fetch(`/api/v1/documents/sources/${id}/lifecycle`);if(!response.ok)throw new Error(t("部分已选资料无法读取；未准备发布。"));const view=await response.json();return {source_id:id,expected_revision:view.current.revision,label:sourceNames[id]||t("所选资料")} as Member}))
    setMembers(current);setError('')
  }})
  const publish=useMutation({mutationFn:async(body:Body)=>{
    const response=await fetch('/api/v1/documents/sources/publish',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const result=await response.json()
    if(!response.ok){if([400,404,409,422].includes(response.status)){pending.current=null;setMembers([])}throw new Error(typeof result.detail==='string'?result.detail:t("批量发布未完成。"))}
    return result
  },onSuccess:async()=>{pending.current=null;setMembers([]);setError('');await onChanged()}})
  function send() {
    if(publish.isPending)return
    if(!pending.current){if(!members.length||!reason.trim()){setError(t("先读取已选版本并填写发布原因。"));return}pending.current={request_id:crypto.randomUUID(),members:members.map(({source_id,expected_revision})=>({source_id,expected_revision})),reason}}
    setError('');publish.mutate(pending.current)
  }
  return <section className="mb-4 space-y-2 rounded-lg border p-3 text-sm" aria-label={t("批量切换资料版本")}><h4 className="font-medium">{t("批量启用版本")}</h4><p className="text-xs">{t("已选择 ")}{sourceIds.length} {t(" 份资料。")}</p>
    <button type="button" className="btn-ghost" disabled={prepare.isPending||publish.isPending||pending.current!==null} onClick={()=>prepare.mutate()}>{t("读取所选资料")}</button>
    {!!members.length&&<ul className="max-h-32 overflow-auto text-xs">{members.map(member=><li className="break-all" key={member.source_id}>{member.label}</li>)}</ul>}
    <label className="block">{t("发布原因")}<input aria-label={t("批量版本发布原因")} className="input-xm mt-1 w-full" value={reason} maxLength={2000} onChange={event=>setReason(event.target.value)} disabled={pending.current!==null}/></label>
    <button type="button" className="btn-secondary" disabled={publish.isPending||prepare.isPending||(!members.length&&!pending.current)} onClick={send}>{pending.current?t("用同一请求确认／重试"):t("启用这些版本")}</button>
    {prepare.isPending&&<p role="status">{t("正在读取所选版本…")}</p>}{publish.isPending&&<p role="status">{t("正在提交整批版本…")}</p>}
    {(error||prepare.error||publish.error)&&<p role="alert" className="text-red-700">{error||uiMessage(prepare.error?.message)||uiMessage(publish.error?.message)}</p>}
    {publish.data&&<p role="status">{t("已完成所选版本的切换。")}</p>}
  </section>
}
