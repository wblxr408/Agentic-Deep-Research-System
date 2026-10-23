import {useState} from 'react'
import {useMutation,useQuery} from '@tanstack/react-query'

interface Chunk {logical_chunk_id:string;start:number;end:number;parent_block_id:string;kind:string;title_path:Array<{title:string}>;source_locators:unknown[];labels:unknown[];entity_mentions:unknown[];date_mentions:unknown[];reference_mentions:unknown[];metadata_quality:Record<string,unknown>}
interface Plan {schema_version:string;profile_id:string;source_version:string;profile:Record<string,unknown>;parents:Array<{parent_block_id:string;parent_id:string|null;kind:string;start:number;end:number;title:string|null}>;children:Chunk[];issues:unknown[];issue_count:number;truncated:boolean;unindexed_range:number[]|null;metadata_enrichment_omitted_chunks:number;summary_excerpt:unknown}
interface PlanResponse {source_id:string;parse_version_id:string|null;view:Plan|null;legacy_gap:boolean}
interface SpanResponse {source_id:string;parse_version_id:string|null;chunk:Chunk;context:{text:string;start:number;end:number;status:string;matched_start?:number;matched_end?:number}}

export default function ChunkPlanPanel({sourceId,groupName}:{sourceId:string;groupName:string}) {
  const [downloadError,setDownloadError]=useState('')
  const query=useQuery<PlanResponse>({queryKey:['document-chunk-plan',sourceId],queryFn:async()=>{
    const response=await fetch(`/api/v1/documents/sources/${sourceId}/chunk-plan`)
    if(!response.ok)throw new Error('无法读取本人资料的分块记录。')
    return response.json()
  }})
  const preview=useMutation<SpanResponse,Error,{id:string;context:'matched'|'parent'}>({mutationFn:async({id,context})=>{
    const params=new URLSearchParams({context,group_name:groupName})
    const response=await fetch(`/api/v1/documents/sources/${sourceId}/chunks/${encodeURIComponent(id)}?${params}`)
    const result=await response.json()
    if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:'无法读取该版本原文；请重新选择当前来源。')
    return result
  }})
  async function download() {
    setDownloadError('')
    try {
      const response=await fetch(`/api/v1/documents/sources/${sourceId}/chunk-plan?include_content=true`)
      if(!response.ok)throw new Error('无法下载本人来源的完整分块计划。')
      const data=await response.json(),url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json;charset=utf-8'}))
      const link=document.createElement('a');link.href=url;link.download=`source-${sourceId}-chunks.json`;link.click();window.setTimeout(()=>URL.revokeObjectURL(url),1000)
    }catch(failure){setDownloadError(failure instanceof Error?failure.message:'下载失败。')}
  }
  const plan=query.data?.view
  return <section aria-label="分块层级与原文定位" className="mt-5 space-y-3 border-t pt-4 text-sm">
    <h4 className="font-medium">分块层级与原文定位</h4>
    {query.isPending&&<p role="status">正在读取已保存分块…</p>}
    {query.error&&<p role="alert" className="text-red-700">{query.error.message}</p>}
    {query.data?.legacy_gap&&<p>旧资料没有版本化分块计划，原文件位置和父级未知。重新上传可生成独立版本。</p>}
    {plan&&<>
      <p className="break-all text-xs">{plan.schema_version} · {query.data?.parse_version_id}</p>
      <p>{plan.parents.length} 个父级范围，{plan.children.length} 个计划小块；是否发布检索见索引状态。字符范围采用规范原文的起点（含）至终点（不含）。</p>
      {plan.truncated&&<p className="text-amber-800">达到分块上限，未索引区间：{plan.unindexed_range?.join('–')}；完整保留文字见下载。</p>}
      {!!plan.metadata_enrichment_omitted_chunks&&<p className="text-amber-800">{plan.metadata_enrichment_omitted_chunks} 个块因元数据上限省略标签／提及，不能据此判断不存在相关内容。</p>}
      <details><summary className="cursor-pointer">实际策略、参数及缺口</summary><pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify({profile:plan.profile,profile_id:plan.profile_id,source_version:plan.source_version,issues:plan.issues,issue_count:plan.issue_count,source_excerpt:plan.summary_excerpt},null,2)}</pre></details>
      <details><summary className="cursor-pointer">父级结构</summary><pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(plan.parents.slice(0,100),null,2)}</pre>{plan.parents.length>100&&<p>展示前100个父级，完整计划可下载。</p>}</details>
      <p className="text-xs text-xmgray-500">实体、日期、引用标识和分类均为有原位置的词面记录；共现不确立合作、任职或技术事实。父级上下文限于当前可访问来源与分组。</p>
      <div className="max-h-96 space-y-2 overflow-auto">{plan.children.slice(0,100).map(chunk=><article key={chunk.logical_chunk_id} className="rounded border border-xmgray-100 p-2">
        <p className="text-xs">{chunk.kind} · {chunk.start}–{chunk.end} · {chunk.title_path.map(item=>item.title).join(' / ')||'未定位章节标题'}</p>
        <code className="block break-all text-xs">{chunk.logical_chunk_id}</code>
        <div className="my-2 flex flex-wrap gap-2"><button type="button" className="btn-ghost text-xs" disabled={preview.isPending} onClick={()=>{preview.reset();preview.mutate({id:chunk.logical_chunk_id,context:'matched'})}}>查看片段原文</button><button type="button" className="btn-ghost text-xs" disabled={preview.isPending} onClick={()=>{preview.reset();preview.mutate({id:chunk.logical_chunk_id,context:'parent'})}}>展开有限父级上下文</button></div>
        <details><summary className="cursor-pointer text-xs">原位置、标签和质量</summary><pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(chunk,null,2)}</pre></details>
      </article>)}</div>
      {plan.children.length>100&&<p className="text-xs">展示前100个小块；完整计划可下载。</p>}
      {preview.isPending&&<p role="status">正在读取该版本的有限原文…</p>}
      {preview.error&&<p role="alert" className="text-red-700">{preview.error.message}</p>}
      {preview.data&&<article className="rounded bg-xmgray-50 p-3" aria-label="已选择片段的原文预览"><p className="break-all text-xs">{preview.data.chunk.logical_chunk_id} · 实际返回 {preview.data.context.start}–{preview.data.context.end} · {preview.data.context.status}</p><pre className="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-words text-sm">{preview.data.context.text}</pre></article>}
      <button type="button" className="btn-ghost" onClick={()=>void download()}>下载完整原文与分块计划</button>
      {downloadError&&<p role="alert" className="text-red-700">{downloadError}</p>}
    </>}
  </section>
}
