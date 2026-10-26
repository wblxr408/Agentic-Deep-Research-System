import {uiDefinition,useLocale,t,uiMessage} from '../i18n'
import {useRef,useState} from 'react'
import {useMutation,useQuery} from '@tanstack/react-query'

interface Generation {generation_id:string;source_version:string;feature_profile_id:string;status:string;created_at:string;document_count:number;source_chunk_count:number;postings:number;coverage:string}
interface IndexView {source_id:string;source_status:string;source_version:string|null;feature_profile_id:string|null;current:{mode:string;generation_id:string|null;revision:number};generations:Generation[];has_more_generations:boolean;choices:unknown;adjacency:unknown}
interface IndexBody {request_id:string;action:'rebuild'|'disable'|'activate';expected_source_version:string|null;expected_feature_profile_id:string|null;expected_generation_id:string|null;expected_revision:number;target_generation_id:string|null}

const modeNames:Record<string,string>=uiDefinition({direct:'仅直接定位',lexical:'已发布词汇索引，使用受任务与有效期约束',legacy_fts_no_generation:'旧全文检索，未保存词项代际',unpublished_no_head:'新表示尚未发布索引'})
const errorNames:Record<string,string>=uiDefinition({index_expected_head_revision_conflict:'索引状态已变化，已刷新；请重新选择操作。',index_expected_source_or_feature_version_conflict:'来源或特征版本已变化，已刷新；请重新选择操作。',retained_feature_version_unavailable_reupload_required:'该旧来源没有兼容的保留特征，可重新上传生成独立版本。',source_not_active_for_index_build:'来源未启用，无法建立检索索引。',retained_target_generation_unavailable:'目标代际已不可用或与当前来源版本不同。',index_operation_not_committed_retry_same_request_id:'尚未确认操作结果，请使用同一请求重试。'})

export default function SourceIndexPanel({sourceId}:{sourceId:string}) {
  useLocale()

  const pending=useRef<IndexBody|null>(null),[localError,setLocalError]=useState(''),[relations,setRelations]=useState<unknown>(null)
  const query=useQuery<IndexView>({queryKey:['source-index',sourceId],queryFn:async()=>{
    const response=await fetch(`/api/v1/documents/sources/${sourceId}/index`)
    if(!response.ok)throw new Error(t("无法读取本人来源的索引状态。"))
    return response.json()
  }})
  const operation=useMutation<Record<string,unknown>,Error,IndexBody>({mutationFn:async body=>{
    const response=await fetch(`/api/v1/documents/sources/${sourceId}/index/actions`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
    const data=await response.json()
    if(!response.ok) {
      if([404,409,422].includes(response.status))pending.current=null
      if(response.status===409)await query.refetch()
      throw new Error(errorNames[data.detail]||(typeof data.detail==='string'?data.detail:t("操作未完成；请查看当前状态。")))
    }
    return data
  },onSuccess:async()=>{pending.current=null;setLocalError('');await query.refetch()}})
  function submit(action:IndexBody['action'],target:string|null=null) {
    if(!query.data||operation.isPending)return
    if(pending.current&&(pending.current.action!==action||pending.current.target_generation_id!==target)) {setLocalError(t("上次操作的结果尚未确认，请先重试上一操作。"));return}
    const data=query.data
    const body=pending.current||{request_id:crypto.randomUUID(),action,target_generation_id:target,expected_source_version:data.source_version,expected_feature_profile_id:data.feature_profile_id,expected_generation_id:data.current.generation_id,expected_revision:data.current.revision}
    pending.current=body;setLocalError('');operation.mutate(body)
  }
  const adjacent=useMutation({mutationFn:async()=>{
    const response=await fetch(`/api/v1/documents/sources/${sourceId}/index?include_adjacency=true`)
    if(!response.ok)throw new Error(t("无法读取本来源的有界结构邻接。"))
    const data:IndexView=await response.json();setRelations(data.adjacency)
  }})
  const data=query.data
  return <section aria-label={t("索引代际与使用范围")} className="mt-5 space-y-3 border-t pt-4 text-sm"><h4 className="font-medium">{t("索引代际与使用范围")}</h4>
    {query.isPending&&<p role="status">{t("正在读取当前索引…")}</p>}{query.error&&<p role="alert" className="text-red-700">{uiMessage(query.error.message)}</p>}
    {data&&<><p>{modeNames[data.current.mode]||data.current.mode} {t(" · 来源状态：")}{data.source_status} {t(" · 索引状态版本：")}{data.current.revision}</p>
      <p className="break-all text-xs">{t("当前代际：")}{data.current.generation_id||t("无")}</p>
      <p className="text-xs text-xmgray-500">{t("重建使用已保存词项，不重新采集或调用模型。关闭后只保留直接定位；回滚切换后续检索代际。原文、特征和旧报告依据保留。")}</p>
      {!data.feature_profile_id&&<p className="text-xs text-amber-800">{t("旧资料未保存兼容特征；可关闭检索，重建需重新上传生成独立表示。")}</p>}
      <div className="flex flex-wrap gap-2"><button type="button" className="btn-ghost" disabled={operation.isPending||!data.feature_profile_id||data.source_status!=='active'} onClick={()=>submit('rebuild')}>{data.current.mode==='direct'?t("建立词汇索引并启用检索"):t("用保留特征重建词汇索引")}</button>
        <button type="button" className="btn-ghost" disabled={operation.isPending||data.current.mode==='direct'} onClick={()=>submit('disable')}>{t("关闭检索，仅保留定位")}</button>
        <button type="button" className="btn-ghost" disabled={operation.isPending} onClick={()=>void query.refetch()}>{t("读取当前状态")}</button></div>
      {operation.isPending&&<p role="status">{t("正在提交索引操作…")}</p>}{operation.error&&<p role="alert" className="text-red-700">{uiMessage(operation.error.message)}</p>}{localError&&<p role="alert" className="text-red-700">{localError}</p>}
      {operation.error&&pending.current&&<button type="button" className="btn-ghost" disabled={operation.isPending} onClick={()=>{if(pending.current)operation.mutate(pending.current)}}>{t("用同一请求重试上一操作")}</button>}
      {operation.data&&<details open><summary>{t("本次操作结果")}</summary><pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(operation.data,null,2)}</pre></details>}
      <div className="max-h-80 overflow-auto"><table className="w-full text-left text-xs" aria-label={t("已保留索引代际")}><thead><tr><th>{t("代际／创建时间")}</th><th>{t("词项覆盖")}</th><th>{t("操作")}</th></tr></thead><tbody>{data.generations.map(generation=><tr key={generation.generation_id}><td className="max-w-48 break-all p-2">{generation.generation_id}<p>{generation.created_at}</p></td><td className="p-2">{generation.document_count}/{generation.source_chunk_count}{t("块 · ")}{generation.postings}{t("词项")}<p>{generation.coverage}</p></td><td className="p-2"><button type="button" className="btn-ghost text-xs" disabled={operation.isPending||data.source_status!=='active'||generation.generation_id===data.current.generation_id||generation.source_version!==data.source_version||generation.feature_profile_id!==data.feature_profile_id} onClick={()=>submit('activate',generation.generation_id)}>{t("使用此保留代际")}</button></td></tr>)}</tbody></table></div>
      {data.has_more_generations&&<p className="text-xs">{t("显示最近20代；未自动删除更早的保留代际。")}</p>}
      <details><summary className="cursor-pointer">{t("索引方式与候选取舍")}</summary><pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(data.choices,null,2)}</pre></details>
      <button type="button" className="btn-ghost text-xs" disabled={adjacent.isPending} onClick={()=>adjacent.mutate()}>{t("查看有界结构／提及邻接")}</button>
      {adjacent.error&&<p role="alert" className="text-red-700">{uiMessage(adjacent.error.message)}</p>}{relations!=null&&<details open><summary>{t("结构与字面提及；不是已确认合作关系")}</summary><pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(relations,null,2)}</pre></details>}
    </>}
  </section>
}
