import {useLocale,t,uiMessage} from '../i18n'
import {useRef,useState} from 'react'

export default function ArchiveTaskEvidence({sessionId,evidenceId,versionId,title}:{
  sessionId:string;evidenceId:string;versionId:string;title:string
}) {
  useLocale()

  const [group,setGroup]=useState('研究归档'),[name,setName]=useState(title.slice(0,300))
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[saved,setSaved]=useState('')
  const operation=useRef({key:'',id:''}),pending=useRef(false)
  async function archive() {
    if(pending.current)return
    pending.current=true;setBusy(true);setError('')
    try {
      if(!group.trim()||!name.trim())throw new Error(t("请填写归档分组和名称。"))
      const key=JSON.stringify([group.trim(),name.trim(),evidenceId,versionId])
      if(operation.current.key!==key)operation.current={key,id:crypto.randomUUID()}
      const response=await fetch(`/api/v1/research/${sessionId}/evidence/${encodeURIComponent(evidenceId)}/archive`,{
        method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:operation.current.id,
          version_id:versionId,group_name:group.trim(),name:name.trim()})})
      const value=await response.json().catch(()=>({detail:t("未取得归档结果，请保留当前字段后重试。")}))
      if(!response.ok)throw new Error(typeof value.detail==='string'?value.detail:t("归档字段或当前来源范围无效。"))
      if(typeof value.source_id!=='string')throw new Error(t("尚未取得归档身份，请保留当前字段后重试。"))
      setSaved(value.source_id)
    } catch(problem) {setError(problem instanceof Error?uiMessage(problem.message):t("归档未完成。"))}
    finally {pending.current=false;setBusy(false)}
  }
  return <details className="mt-2"><summary className="cursor-pointer">{t("保存这份原文到本人资料")}</summary>
    <p className="my-2 text-xs">{t("保存当前取得的文字及原始来源关联，默认只直接定位。之后可在资料管理中另行启用检索。")}</p>
    <label className="block">{t("分组")}<input className="input-xm my-1 w-full" disabled={busy} maxLength={100} value={group}
      onChange={event=>{setGroup(event.target.value);setSaved('')}}/></label>
    <label className="block">{t("名称")}<input className="input-xm my-1 w-full" disabled={busy} maxLength={300} value={name}
      onChange={event=>{setName(event.target.value);setSaved('')}}/></label>
    <button className="btn-ghost text-xs" type="button" disabled={busy||!!saved} onClick={()=>void archive()}>{busy?t("正在保存…"):t("归档当前原文版本")}</button>
    {saved&&<p role="status" className="break-all text-xs">{t("已保存到本人资料：")}{saved}{t("。未自动加入检索。")}</p>}
    {error&&<p role="alert" className="text-xs text-red-700">{uiMessage(error)}</p>}
  </details>
}
