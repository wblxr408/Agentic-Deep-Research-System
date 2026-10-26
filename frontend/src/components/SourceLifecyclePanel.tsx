import {uiDefinition,useLocale,t,uiMessage} from '../i18n'
import {useEffect,useMemo,useRef,useState} from 'react'
import {useMutation,useQuery} from '@tanstack/react-query'
import RetentionPolicyPanel,{defaultRetentionDraft,retentionPolicyRequest} from './RetentionPolicyPanel'
import type {RetentionDraft} from './RetentionPolicyPanel'

interface Lifecycle {revision:number;reuse_scope:string;task_id?:string|null;valid_from?:string|null;valid_until?:string|null;purge_after?:string|null;state:string;is_current:boolean|null;family_id?:string}
interface Version extends Lifecycle {source_id:string;name:string;status:string;parse_version:string}
interface View {source_id:string;source_status:string;parse_version:string|null;current:Lifecycle;versions:Version[];has_more_versions:boolean;access_epoch:number;events:unknown[];maintenance:unknown;report_semantics:string}
interface Pending {url:string;body:Record<string,unknown>}
function localDate(value:string|null|undefined) {if(!value)return '';const date=new Date(value);return new Date(date.getTime()-date.getTimezoneOffset()*60000).toISOString().slice(0,16)}
const messages:Record<string,string>=uiDefinition({source_lifecycle_revision_conflict:'资料状态已变化，已刷新；请重新选择操作。',lifecycle_request_id_payload_conflict:'同一请求的内容发生变化，已拒绝；请重新读取状态。',revision_original_parse_version_conflict:'原文版本已变化，请重新读取。',patch_outside_retained_original:'修订范围超出了所保留的原文。',revision_has_no_text_change:'内容没有变化，无需创建新版本。',retention_task_not_owned_or_missing:'所填任务不存在或不属于当前账号。',only_deleted_or_due_noncurrent_source_can_be_purged:'只能永久清理已隐藏或达到清理时间的非当前版本。',lifecycle_result_unconfirmed_retry_same_request_id:'尚未确认结果，请确认结果并重试。'})

export default function SourceLifecyclePanel({sourceId,onChanged}:{sourceId:string;onChanged:()=>Promise<void>}) {
  useLocale()

  const [policy,setPolicy]=useState<RetentionDraft>(defaultRetentionDraft),[reason,setReason]=useState(''),[error,setError]=useState('')
  const [revisionMode,setRevisionMode]=useState<'replace'|'patch'>('replace'),[text,setText]=useState(''),[rangeStart,setRangeStart]=useState('0'),[rangeEnd,setRangeEnd]=useState('0'),[publish,setPublish]=useState(true)
  const [original,setOriginal]=useState<string|null>(null),[format,setFormat]=useState<'txt'|'md'|'json'>('txt')
  const [pruneBefore,setPruneBefore]=useState('')
  const pending=useRef<Pending|null>(null)
  const originalCharacters=useMemo(()=>Array.from(original||''),[original])
  const query=useQuery<View>({queryKey:['source-lifecycle',sourceId],queryFn:async()=>{const response=await fetch(`/api/v1/documents/sources/${sourceId}/lifecycle`);if(!response.ok)throw new Error(t("无法读取本人资料的生命周期。"));return response.json()}})
  useEffect(()=>{const current=query.data?.current;if(!current)return;setPolicy({reuse_scope:current.reuse_scope==='owner'?'owner':current.reuse_scope==='group'||current.reuse_scope==='legacy_explicit_group'?'group':'task',task_id:current.task_id||'',valid_from:localDate(current.valid_from),valid_until:localDate(current.valid_until),purge_after:localDate(current.purge_after)})},[query.data])
  const operation=useMutation<unknown,Error,Pending>({mutationFn:async request=>{
    const response=await fetch(request.url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(request.body)})
    const result=await response.json()
    if(!response.ok){if([400,404,409,413,422].includes(response.status))pending.current=null;if(response.status===409)await query.refetch();throw new Error(messages[result.detail]||(typeof result.detail==='string'?result.detail:t("提交未完成。")))}
    return result
  },onSuccess:async()=>{pending.current=null;setError('');setOriginal(null);await query.refetch();await onChanged()}})
  function send(action:string) {
    if(!query.data||operation.isPending)return
    if(pending.current){setError(t("上一操作结果尚未确认，请先确认结果并重试。"));return}
    if(!reason.trim()){setError(t("请填写本次修订或维护原因。"));return}
    try {
      const body:Record<string,unknown>={request_id:crypto.randomUUID(),expected_revision:query.data.current.revision,reason}
      let url=`/api/v1/documents/sources/${sourceId}/lifecycle/actions`
      if(action==='revise') {
        url=`/api/v1/documents/sources/${sourceId}/versions`;Object.assign(body,{expected_parse_version:query.data.parse_version,mode:revisionMode,text,format,publish})
        if(revisionMode==='patch') {const start=Number(rangeStart),end=Number(rangeEnd);if(!rangeStart.trim()||!rangeEnd.trim()||!Number.isInteger(start)||!Number.isInteger(end)||start<0||end<start)throw new Error(t("请填写有效的原文字符范围。"));Object.assign(body,{start,end})}
      } else {body.action=action;if(action==='set_access')body.policy=retentionPolicyRequest(policy);if(action==='prune_indexes'){if(!pruneBefore)throw new Error(t("请选择清理截止时间。"));body.before=new Date(pruneBefore).toISOString()}}
      pending.current={url,body};setError('');operation.mutate(pending.current)
    } catch(failure){setError(failure instanceof Error?uiMessage(failure.message):t("资料配置无效。"))}
  }
  const preview=useMutation({mutationFn:async()=>{const response=await fetch(`/api/v1/documents/sources/${sourceId}/parsing?include_content=true`);if(!response.ok)throw new Error(t("无法读取所保留原文。"));const result=await response.json();setOriginal(result.text||'')}})
  const view=query.data
  return <section aria-label={t("资料版本与生命周期")} className="mt-5 space-y-3 border-t pt-4 text-sm"><h4 className="font-medium">{t("资料管理")}</h4>
    {query.isPending&&<p role="status">{t("正在读取版本…")}</p>}{query.error&&<p role="alert">{uiMessage(query.error.message)}</p>}
    {view&&<><p>{view.current.is_current?t("当前版本"):view.current.is_current===null?t("历史资料"):t("保留的旧版本")} · {({active:t("使用中"),archived:t("已归档"),tombstone:t("已隐藏"),candidate:t("候选版本")} as Record<string,string>)[view.current.state]||t("已保存")}</p>
      <p>{t("使用范围：")}{view.current.reuse_scope==='task'?(view.current.task_id?t("仅指定的研究"):t("尚未绑定研究")):view.current.reuse_scope==='owner'?t("我的研究"):t("选择此分组的研究")}。</p>
      <p className="text-xs text-xmgray-500">{t("研究使用当前有效版本。")}</p>
      <label className="block">{t("操作原因")}<textarea aria-label={t("资料维护原因")} className="input-xm mt-1 w-full" value={reason} onChange={event=>setReason(event.target.value)} maxLength={2000}/></label>
      <details><summary className="cursor-pointer">{t("修改保存范围和有效期")}</summary><RetentionPolicyPanel value={policy} onChange={setPolicy}/><button type="button" className="btn-secondary mt-2" disabled={operation.isPending} onClick={()=>send('set_access')}>{t("保存使用范围与有效期")}</button></details>
      <details><summary className="cursor-pointer">{t("纠正原文并保存新版本")}</summary><div className="mt-2 space-y-2"><label>{t("修订方式")}<select aria-label={t("原文修订方式")} value={revisionMode} onChange={event=>setRevisionMode(event.target.value as typeof revisionMode)} className="input-xm ml-2"><option value="replace">{t("替换全文")}</option><option value="patch" disabled={!view.parse_version}>{t("替换原位片段")}</option></select></label>
        {!view.parse_version&&<p className="text-xs">{t("旧资料缺少稳定解析版本，请先全文替换保存新版本，再使用原位修订。")}</p>}
        <button type="button" className="btn-ghost ml-2" disabled={preview.isPending} onClick={()=>preview.mutate()}>{t("查看所保留原文")}</button>{preview.error&&<p role="alert">{uiMessage(preview.error.message)}</p>}
        {original!==null&&<div><p className="text-xs">{t("原文共")}{originalCharacters.length}{t("个Unicode字符，预览前10000字符。选择文字可自动填写原位范围；从0开始，结束位置不包含在替换中。")}</p><textarea aria-label={t("选择保留原文片段")} readOnly className="input-xm h-48 w-full whitespace-pre-wrap text-xs" value={originalCharacters.slice(0,10000).join('')} onSelect={event=>{const area=event.currentTarget;if(view.parse_version&&area.selectionEnd>area.selectionStart){setRangeStart(String(Array.from(area.value.slice(0,area.selectionStart)).length));setRangeEnd(String(Array.from(area.value.slice(0,area.selectionEnd)).length));setRevisionMode('patch')}}}/></div>}
        {revisionMode==='patch'&&<div className="flex gap-2"><label>{t("开始")}<input aria-label={t("原位修订开始位置")} type="number" min={0} className="input-xm w-24" value={rangeStart} onChange={event=>setRangeStart(event.target.value)}/></label><label>{t("结束")}<input aria-label={t("原位修订结束位置")} type="number" min={0} className="input-xm w-24" value={rangeEnd} onChange={event=>setRangeEnd(event.target.value)}/></label></div>}
        <label className="block">{t("新内容格式")}<select aria-label={t("修订内容格式")} className="input-xm ml-2" value={format} onChange={event=>setFormat(event.target.value as typeof format)}><option value="txt">{t("纯文本")}</option><option value="md">Markdown</option><option value="json">JSON</option></select></label>
        <textarea aria-label={t("资料修订内容")} className="input-xm min-h-40 w-full" value={text} onChange={event=>setText(event.target.value)} placeholder={revisionMode==='replace'?t("新的完整原文"):t("该范围的替换文字；可留空表示删除片段")}/>
        <label className="flex gap-2"><input type="checkbox" checked={publish} onChange={event=>setPublish(event.target.checked)}/>{t("保存后切换为当前版本；取消则保留为候选版本")}</label>
        <p className="text-xs">{t("新版本继承当前复用范围和表示选择；重新解析、分块并增量建立已选索引。若保留稠密表示，会按当前授权模型配置重新编码。")}</p>
        <button type="button" className="btn-primary" disabled={operation.isPending||view.current.state==='tombstone'} onClick={()=>send('revise')}>{t("保存新原文版本")}</button></div></details>
      <div className="flex flex-wrap gap-2"><button type="button" className="btn-ghost" disabled={operation.isPending||view.current.state==='tombstone'} onClick={()=>send('tombstone')}>{t("隐藏并保留恢复能力")}</button>
        <button type="button" className="btn-ghost" disabled={operation.isPending||view.current.state!=='tombstone'} onClick={()=>send('restore')}>{t("恢复保留资料")}</button>
        <button type="button" className="btn-ghost" disabled={operation.isPending||view.current.is_current===true||view.current.state==='tombstone'} onClick={()=>send('activate')}>{t("切换此版本供后续研究使用")}</button>
        <button type="button" className="btn-ghost" disabled={operation.isPending||view.current.is_current===true} onClick={()=>send('purge')}>{t("永久清理此非当前来源")}</button>
        <button type="button" className="btn-ghost" disabled={operation.isPending} onClick={()=>send('cleanup')}>{t("清理本族已到期旧版本（最多20项）")}</button></div>
      <p className="text-xs text-xmgray-500">{t("永久清理无法恢复原始来源；不会连带删除已完成任务中独立保留的证据与报告。没有自动后台清理。")}</p>
      <details><summary>{t("清理不再使用的索引代际")}</summary><label className="block text-xs">{t("清理此前且未生效的代际")}<input aria-label={t("索引清理截止时间")} type="datetime-local" className="input-xm ml-2" value={pruneBefore} onChange={event=>setPruneBefore(event.target.value)}/></label><button type="button" className="btn-ghost mt-2" disabled={operation.isPending} onClick={()=>send('prune_indexes')}>{t("显式清理最多20个旧索引代际")}</button><p className="text-xs">{t("保留当前生效代际和全部来源正文；清理后不能再回滚到被清理的代际。")}</p></details>
      {operation.isPending&&<p role="status">{t("正在提交资料操作…")}</p>}{operation.error&&<p role="alert" className="text-red-700">{uiMessage(operation.error.message)}</p>}{error&&<p role="alert" className="text-red-700">{uiMessage(error)}</p>}
      {operation.error&&pending.current&&<button type="button" className="btn-secondary" onClick={()=>{if(pending.current)operation.mutate(pending.current)}} disabled={operation.isPending}>{t("确认结果并重试")}</button>}
      {operation.data!=null&&<details open><summary>{t("实际提交结果与受影响报告")}</summary><pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(operation.data,null,2)}</pre></details>}
      <details><summary>{t("同族保留版本（最近50项）")}</summary><ul>{view.versions.map(version=><li key={version.source_id} className="my-2 break-all">{version.name} · {version.is_current?t("当前"):t("旧版本")} · {({active:t("使用中"),tombstone:t("已隐藏"),candidate:t("候选")} as Record<string,string>)[version.state]||t("已保存")}</li>)}</ul>{view.has_more_versions&&<p>{t("还有更早版本，未自动删除。")}</p>}</details>
      <details><summary>{t("修订记录与维护方式")}</summary><pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify({events:view.events,maintenance:view.maintenance,access_epoch:view.access_epoch},null,2)}</pre></details>
    </>}
  </section>
}
