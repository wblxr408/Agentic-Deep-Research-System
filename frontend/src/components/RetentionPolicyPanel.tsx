import {t,useLocale} from '../i18n'
import {useEffect,useState} from 'react'
export interface RetentionDraft {reuse_scope:'task'|'group'|'owner';task_id:string;valid_from:string;valid_until:string;purge_after:string}
export const defaultRetentionDraft:RetentionDraft={reuse_scope:'task',task_id:'',valid_from:'',valid_until:'',purge_after:''}
export function retentionPolicyRequest(value:RetentionDraft) {
  const date=(input:string)=>input?new Date(input).toISOString():null
  const policy={reuse_scope:value.reuse_scope,task_id:value.reuse_scope==='task'&&value.task_id.trim()?value.task_id.trim():null,valid_from:date(value.valid_from),valid_until:date(value.valid_until),purge_after:date(value.purge_after)}
  if(policy.task_id&&!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(policy.task_id))throw new Error(t("请粘贴本人研究工作区的完整链接。"))
  if(policy.valid_from&&policy.valid_until&&policy.valid_until<=policy.valid_from)throw new Error(t("失效时间应晚于生效时间。"))
  return policy
}
export default function RetentionPolicyPanel({value,onChange}:{value:RetentionDraft;onChange:(value:RetentionDraft)=>void}) {
  useLocale()

  const [link,setLink]=useState('')
  useEffect(()=>{if(/^[0-9a-f-]{36}$/i.test(value.task_id))setLink(`${window.location.origin}/?view=research&session=${value.task_id}`);else if(!value.task_id)setLink('')},[value.task_id])
  return <fieldset className="space-y-3 rounded-lg border p-4 text-sm"><legend className="px-2 font-medium">{t("保存与复用范围")}</legend>
    <label className="block">{t("资料可供哪些研究使用")}<select aria-label={t("资料复用范围")} className="input-xm ml-2" value={value.reuse_scope} onChange={event=>onChange({...value,reuse_scope:event.target.value as RetentionDraft['reuse_scope'],task_id:''})}><option value="task">{t("仅绑定任务（默认）")}</option><option value="group">{t("明确选择同一分组的研究")}</option><option value="owner">{t("本人跨任务复用")}</option></select></label>
    {value.reuse_scope==='task'&&<label className="block">{t("研究链接")}<input aria-label={t("资料绑定研究链接")} className="input-xm mt-1 w-full" value={link} onChange={event=>{const next=event.target.value;setLink(next);let task=next;try{const url=new URL(next);if(['http:','https:'].includes(url.protocol))task=url.searchParams.get('session')||next}catch{}onChange({...value,task_id:task})}} placeholder={t("粘贴研究工作区链接，可稍后绑定")} /></label>}
    <p className="text-xs text-xmgray-500"></p>
    <div className="grid gap-2 sm:grid-cols-3">{(['valid_from','valid_until','purge_after'] as const).map((key,index)=><label className="block text-xs" key={key}>{[t("生效时间（可选）"),t("失效时间（可选）"),t("旧版本可清理时间（可选）")][index]}<input aria-label={[t("资料生效时间"),t("资料失效时间"),t("旧版本可清理时间")][index]} type="datetime-local" className="input-xm mt-1 w-full" value={value[key]} onChange={event=>onChange({...value,[key]:event.target.value})}/></label>)}</div>
    <p className="text-xs text-xmgray-500"></p>
  </fieldset>
}
