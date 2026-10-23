import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'

interface ParsingData {
  source_id:string;parse_version_id:string|null;status:string;semantics:string;profile:Record<string,unknown>|null;text:string|null
  structure:{schema_version:string;format:string;parser_engine:string;truncated?:boolean;quality:Record<string,unknown>
    blocks:Array<{block_id:string;kind:string;start?:number;end?:number;source_locator:Record<string,unknown>;raw_text?:string}>
    tables:Array<{table_id:string;cells:Array<{row:number;column:number;text:string|null;row_span:number|null;column_span:number|null}>;semantics?:string}>
    figures:Array<Record<string,unknown>>;deduplication?:Record<string,unknown>}|null
  reviews:Array<{review_id:string;status:string;note:string;created_at:string}>
}
const statusNames:Record<string,string>={accepted_structure:'人工接受该版本结构',needs_correction:'结构需要修正',unreadable:'无法可靠读取'}
export default function DocumentParsingPanel({sourceId}:{sourceId:string}) {
  const [status,setStatus]=useState('needs_correction'),[note,setNote]=useState(''),[requestId,setRequestId]=useState(()=>crypto.randomUUID())
  const [downloadError,setDownloadError]=useState('')
  const query=useQuery<ParsingData>({queryKey:['document-parsing',sourceId],queryFn:async()=>{
    const response=await fetch(`/api/v1/documents/sources/${sourceId}/parsing`)
    if (!response.ok) throw new Error('无法读取本人资料的解析记录。')
    return response.json()
  }})
  const review=useMutation({mutationFn:async()=>{
    if (!query.data?.parse_version_id || !note.trim())throw new Error('请填写该解析版本的问题或审核说明。')
    const response=await fetch(`/api/v1/documents/sources/${sourceId}/parsing/reviews`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:requestId,parse_version_id:query.data.parse_version_id,status,note})})
    const data=await response.json()
    if (!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'审核记录未保存。')
    return data
  },onSuccess:()=>{setNote('');setRequestId(crypto.randomUUID());void query.refetch()}})
  async function download() {
    setDownloadError('')
    try {
      const response=await fetch(`/api/v1/documents/sources/${sourceId}/parsing?include_content=true`)
      if (!response.ok)throw new Error('无法下载解析原文。')
      const data=await response.json(),url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json;charset=utf-8'}))
      const link=document.createElement('a');link.href=url;link.download=`source-${sourceId}-parsing.json`;link.click();window.setTimeout(()=>URL.revokeObjectURL(url),1000)
    }catch(error){setDownloadError(error instanceof Error?error.message:'下载失败。')}
  }
  const data=query.data,structure=data?.structure
  return <section aria-label="文档结构、质量与人工审核" className="mt-5 space-y-3 border-t pt-4 text-sm">
    <h4 className="font-medium">解析结构与质量</h4>
    {query.isPending&&<p role="status">正在读取已保存解析记录…</p>}
    {query.error&&<p role="alert" className="text-red-700">{query.error.message}</p>}
    {data&&!structure&&<p>旧资料未保留结构化解析；没有追认布局或OCR。可显式重新上传生成独立版本。</p>}
    {data&&structure&&<>
      <p className="break-all text-xs">{structure.format} · {structure.parser_engine} · {data.parse_version_id}</p>
      <p className="text-xs">{data.semantics} 图像指针、OCR识别分数和解析成功都不代表事实审核通过。</p>
      <details open><summary className="cursor-pointer">质量、覆盖与识别缺口</summary><pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(structure.quality,null,2)}</pre>{structure.truncated&&<p className="text-amber-800">已截断，未保留部分不能当作已读。</p>}</details>
      <details><summary className="cursor-pointer">{structure.blocks.length} 个正文／结构块及原位置</summary>{structure.blocks.length>100&&<p>页面显示前100块，完整结构见JSON下载。</p>}<div className="max-h-80 overflow-auto">{structure.blocks.slice(0,100).map(block=><article key={block.block_id} className="my-2 rounded bg-xmgray-50 p-2"><p>{block.block_id} · {block.kind} · 字符 {block.start??'未知'}–{block.end??'未知'}</p><pre className="whitespace-pre-wrap break-words text-xs">{JSON.stringify(block,null,2)}</pre></article>)}</div></details>
      <details><summary className="cursor-pointer">{structure.tables.length} 个表格候选与单元格</summary><div className="max-h-96 overflow-auto">{structure.tables.map(table=><section key={table.table_id} className="my-3"><p>{table.table_id} · {table.semantics}</p><table className="w-full text-left text-xs"><thead><tr><th>行／列</th><th>跨度</th><th>来源值</th></tr></thead><tbody>{table.cells.map((cell,index)=><tr key={index}><td>{cell.row+1}/{cell.column+1}</td><td>{cell.row_span??'未知'}×{cell.column_span??'未知'}</td><td className="whitespace-pre-wrap p-1">{cell.text??'未恢复／合并状态未知'}</td></tr>)}</tbody></table></section>)}</div></details>
      <details><summary className="cursor-pointer">{structure.figures.length} 个图像指针／图注关系</summary><p className="text-xs">仅显示实际保留的指针，不自动加载外部图片或生成图内结论。</p><pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(structure.figures,null,2)}</pre></details>
      <details><summary className="cursor-pointer">重复与近似候选</summary><pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(structure.deduplication,null,2)}</pre></details>
      <section><h5 className="font-medium">标记本版本的解析问题</h5><label className="mt-2 block text-xs">结构审核状态<select disabled={review.isPending} className="input-xm mt-1" aria-label="结构审核状态" value={status} onChange={event=>{setStatus(event.target.value);setRequestId(crypto.randomUUID())}}>{Object.entries(statusNames).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
        <textarea disabled={review.isPending} className="input-xm mt-2" aria-label="解析审核说明" maxLength={2000} value={note} onChange={event=>{setNote(event.target.value);setRequestId(crypto.randomUUID())}} placeholder="记录错行、乱码、表格或原图位置的问题；不改写已保存正文。" />
        <button type="button" className="btn-ghost mt-2" disabled={review.isPending||!note.trim()} onClick={()=>review.mutate()}>保存结构审核记录</button>
        {review.error&&<p role="alert" className="text-red-700">{review.error.message}</p>}
        {review.isSuccess&&<p role="status">结构审核记录已保存；原文和原报告未改写。</p>}
        <ul>{data.reviews.map(record=><li className="my-2 rounded bg-xmgray-50 p-2 text-xs" key={record.review_id}>{statusNames[record.status]||record.status} · {record.created_at}<p>{record.note}</p></li>)}</ul>
      </section>
      <button type="button" className="btn-ghost" onClick={()=>void download()}>下载本版本原文、结构与审核记录</button>
      {downloadError&&<p role="alert" className="text-red-700">{downloadError}</p>}
    </>}
  </section>
}
