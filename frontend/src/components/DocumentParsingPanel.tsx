import {uiDefinition,useLocale,t,uiMessage} from '../i18n'
import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import DocumentVisualPanel from './DocumentVisualPanel'
import DocumentTextPanel from './DocumentTextPanel'

interface ParsingData {
  source_id:string;parse_version_id:string|null;lifecycle_revision:number;status:string;semantics:string;profile:Record<string,unknown>|null;text:string|null
  structure:{schema_version:string;format:string;parser_engine:string;truncated?:boolean;quality:Record<string,unknown>;pages?:Array<{number:number;start?:number;end?:number}>
    blocks:Array<{block_id:string;kind:string;start?:number;end?:number;source_locator:Record<string,unknown>;raw_text?:string}>
    tables:Array<{table_id:string;cells:Array<{row:number;column:number;text:string|null;row_span:number|null;column_span:number|null}>;semantics?:string}>
    figures:Array<Record<string,unknown>>;deduplication?:Record<string,unknown>;cleaning?:{repeated_page_margin_candidates?:Array<{candidate_id:string;occurrences:Array<{page:number;text:string}>;total_pages?:number;truncated?:boolean}>}}|null
  reviews:Array<{review_id:string;status:string;note:string;created_at:string}>
}
const statusNames:Record<string,string>=uiDefinition({accepted_structure:'人工接受该版本结构',needs_correction:'结构需要修正',unreadable:'无法可靠读取'})
export default function DocumentParsingPanel({sourceId,onChanged}:{sourceId:string;onChanged?:()=>Promise<void>}) {
  useLocale()

  const [status,setStatus]=useState('needs_correction'),[note,setNote]=useState(''),[requestId,setRequestId]=useState(()=>crypto.randomUUID())
  const [downloadError,setDownloadError]=useState('')
  const query=useQuery<ParsingData>({queryKey:['document-parsing',sourceId],queryFn:async()=>{
    const response=await fetch(`/api/v1/documents/sources/${sourceId}/parsing`)
    if (!response.ok) throw new Error(t("无法读取本人资料的解析记录。"))
    return response.json()
  }})
  const review=useMutation({mutationFn:async()=>{
    if (!query.data?.parse_version_id || !note.trim())throw new Error(t("请填写该解析版本的问题或审核说明。"))
    const response=await fetch(`/api/v1/documents/sources/${sourceId}/parsing/reviews`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({request_id:requestId,parse_version_id:query.data.parse_version_id,status,note})})
    const data=await response.json()
    if (!response.ok)throw new Error(typeof data.detail==='string'?data.detail:t("审核记录未保存。"))
    return data
  },onSuccess:()=>{setNote('');setRequestId(crypto.randomUUID());void query.refetch()}})
  async function download() {
    setDownloadError('')
    try {
      const response=await fetch(`/api/v1/documents/sources/${sourceId}/parsing?include_content=true`)
      if (!response.ok)throw new Error(t("无法下载解析原文。"))
      const data=await response.json(),url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json;charset=utf-8'}))
      const link=document.createElement('a');link.href=url;link.download=`source-${sourceId}-parsing.json`;link.click();window.setTimeout(()=>URL.revokeObjectURL(url),1000)
    }catch(error){setDownloadError(error instanceof Error?uiMessage(error.message):t("下载失败。"))}
  }
  const data=query.data,structure=data?.structure
  return <section aria-label={t("文档结构、质量与人工审核")} className="mt-5 space-y-3 border-t pt-4 text-sm">
    <h4 className="font-medium">{t("解析结构与质量")}</h4>
    {query.isPending&&<p role="status">{t("正在读取已保存解析记录…")}</p>}
    {query.error&&<p role="alert" className="text-red-700">{uiMessage(query.error.message)}</p>}
    {data&&!structure&&<p>{t("暂无结构化解析记录。")}</p>}
    {data&&structure&&<>
      <p className="break-all text-xs">{structure.format} · {structure.parser_engine} · {data.parse_version_id}</p>
      <p className="text-xs">{t('原文、图片位置和模型结果分别保存。')}</p>
      <details open><summary className="cursor-pointer">{t("质量、覆盖与识别缺口")}</summary><pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(structure.quality,null,2)}</pre>{structure.truncated&&<p className="text-amber-800">{t("已截断，未保留部分不能当作已读。")}</p>}</details>
      <details><summary className="cursor-pointer">{structure.blocks.length} {t(" 个正文／结构块及原位置")}</summary>{structure.blocks.length>100&&<p>{t("页面显示前100块，完整结构见JSON下载。")}</p>}<div className="max-h-80 overflow-auto">{structure.blocks.slice(0,100).map(block=><article key={block.block_id} className="my-2 rounded bg-xmgray-50 p-2"><p>{block.block_id} · {block.kind} {t(" · 字符 ")}{block.start??t("未知")}–{block.end??t("未知")}</p><pre className="whitespace-pre-wrap break-words text-xs">{JSON.stringify(block,null,2)}</pre></article>)}</div></details>
      <details><summary className="cursor-pointer">{structure.tables.length} {t(" 个表格候选与单元格")}</summary><div className="max-h-96 overflow-auto">{structure.tables.map(table=><section key={table.table_id} className="my-3"><p>{table.table_id} · {table.semantics}</p><table className="w-full text-left text-xs"><thead><tr><th>{t("行／列")}</th><th>{t("跨度")}</th><th>{t("来源值")}</th></tr></thead><tbody>{table.cells.map((cell,index)=><tr key={index}><td>{cell.row+1}/{cell.column+1}</td><td>{cell.row_span??t("未知")}×{cell.column_span??t("未知")}</td><td className="whitespace-pre-wrap p-1">{cell.text??t("未恢复／合并状态未知")}</td></tr>)}</tbody></table></section>)}</div></details>
      <details><summary className="cursor-pointer">{structure.figures.length} {t(" 个图像指针／图注关系")}</summary><p className="text-xs">{t('原图位置与图注')}</p><pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(structure.figures,null,2)}</pre></details>
      {data.parse_version_id&&<DocumentVisualPanel sourceId={sourceId} parseVersion={data.parse_version_id} structure={structure} onChanged={onChanged}/>}
      {data.parse_version_id&&<DocumentTextPanel sourceId={sourceId} parseVersion={data.parse_version_id} lifecycleRevision={data.lifecycle_revision} structure={structure} onChanged={onChanged}/>}
      <details><summary className="cursor-pointer">{t("重复与近似候选")}</summary><pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(structure.deduplication,null,2)}</pre></details>
      <section><h5 className="font-medium">{t("标记本版本的解析问题")}</h5><label className="mt-2 block text-xs">{t("结构审核状态")}<select disabled={review.isPending} className="input-xm mt-1" aria-label={t("结构审核状态")} value={status} onChange={event=>{setStatus(event.target.value);setRequestId(crypto.randomUUID())}}>{Object.entries(statusNames).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
        <textarea disabled={review.isPending} className="input-xm mt-2" aria-label={t("解析审核说明")} maxLength={2000} value={note} onChange={event=>{setNote(event.target.value);setRequestId(crypto.randomUUID())}} placeholder={t("记录错行、乱码、表格或原图位置的问题；不改写已保存正文。")} />
        <button type="button" className="btn-ghost mt-2" disabled={review.isPending||!note.trim()} onClick={()=>review.mutate()}>{t("保存结构审核记录")}</button>
        {review.error&&<p role="alert" className="text-red-700">{uiMessage(review.error.message)}</p>}
        {review.isSuccess&&<p role="status">{t("结构审核记录已保存；原文和原报告未改写。")}</p>}
        <ul>{data.reviews.map(record=><li className="my-2 rounded bg-xmgray-50 p-2 text-xs" key={record.review_id}>{statusNames[record.status]||record.status} · {record.created_at}<p>{record.note}</p></li>)}</ul>
      </section>
      <button type="button" className="btn-ghost" onClick={()=>void download()}>{t("下载本版本原文、结构与审核记录")}</button>
      {downloadError&&<p role="alert" className="text-red-700">{downloadError}</p>}
    </>}
  </section>
}
