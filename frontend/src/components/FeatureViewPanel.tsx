import {useState} from 'react'
import {useQuery} from '@tanstack/react-query'

interface FeatureResponse {source_id:string;parse_version_id:string|null;legacy_gap:boolean;view:null|{schema_version:string;profile_id:string;profile:unknown;statistics:Record<string,unknown>;dense:unknown;temporal:unknown;modality:unknown;candidate_decisions:Record<string,unknown>;children:Array<{logical_chunk_id:string;start:number;end:number;lexical:unknown;status?:string}>;display_limit?:number}}

export default function FeatureViewPanel({sourceId}:{sourceId:string}) {
  const [downloadError,setDownloadError]=useState('')
  const query=useQuery<FeatureResponse>({queryKey:['document-features',sourceId],queryFn:async()=>{
    const response=await fetch(`/api/v1/documents/sources/${sourceId}/features`)
    if(!response.ok)throw new Error('无法读取本人资料的特征视图。')
    return response.json()
  }})
  async function download() {
    setDownloadError('')
    try {
      const response=await fetch(`/api/v1/documents/sources/${sourceId}/features?include_chunks=true`)
      if(!response.ok)throw new Error('特征下载失败。')
      const data=await response.json(),url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json;charset=utf-8'}))
      const link=document.createElement('a');link.href=url;link.download=`source-${sourceId}-features.json`;link.click();window.setTimeout(()=>URL.revokeObjectURL(url),1000)
    }catch(failure){setDownloadError(failure instanceof Error?failure.message:'下载失败。')}
  }
  const view=query.data?.view
  return <section aria-label="特征视图与编码依据" className="mt-5 space-y-3 border-t pt-4 text-sm"><h4 className="font-medium">特征视图与编码依据</h4>
    {query.isPending&&<p role="status">正在读取已保存特征…</p>}{query.error&&<p role="alert" className="text-red-700">{query.error.message}</p>}
    {query.data?.legacy_gap&&<p>暂无内容特征记录。</p>}
    {view&&<><p className="break-all text-xs">{view.schema_version} · {view.profile_id}</p><p className="text-xs text-xmgray-500">统计范围为本来源保留的小块；重叠块分别计数，不能当作论文数量或全库IDF。未知日期、未编码图像及未采用候选分别列示。</p>
      {Object.entries({词项统计:view.statistics,稠密编码:view.dense,时间依据:view.temporal,模态覆盖:view.modality,候选与未采用原因:view.candidate_decisions,冻结策略:view.profile}).map(([label,value])=><details key={label}><summary className="cursor-pointer">{label}</summary><pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(value,null,2)}</pre></details>)}
      <details><summary className="cursor-pointer">小块词项、位置与未知（页面最多20项）</summary><div className="max-h-96 space-y-3 overflow-auto">{view.children.map(chunk=><article key={chunk.logical_chunk_id} className="rounded bg-xmgray-50 p-2"><p className="break-all text-xs">{chunk.logical_chunk_id} · {chunk.start}–{chunk.end} · {chunk.status||'已保留'}</p><pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(chunk,null,2)}</pre></article>)}</div></details>
      <button type="button" className="btn-ghost" onClick={()=>void download()}>下载完整特征计划</button>{downloadError&&<p role="alert" className="text-red-700">{downloadError}</p>}
    </>}
  </section>
}
