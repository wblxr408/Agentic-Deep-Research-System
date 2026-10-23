import { useEffect, useRef, useState } from 'react'
import {chunkPolicyRequest} from './ChunkPolicyPanel'
import type {ChunkDraft} from './ChunkPolicyPanel'
import {featurePolicyRequest,indexPolicyRequest} from './FeaturePolicyPanel'
import type {FeatureDraft,IndexMode} from './FeaturePolicyPanel'
import {retentionPolicyRequest} from './RetentionPolicyPanel'
import type {RetentionDraft} from './RetentionPolicyPanel'

interface Item { id: string; file: File; path: string; status: 'pending' | 'running' | 'saved' | 'reused' | 'failed' | 'unsupported'; message?: string; sourceId?: string }
const formats = new Set(['json','md','docx','pdf','txt'])
export default function DocumentBatchIntake({ groupName, chunkSize, chunkOverlap, chunkDraft, featureDraft, indexMode, retentionDraft, allowOcr, onSaved }: {
  groupName: string; chunkSize: number; chunkOverlap: number; chunkDraft:ChunkDraft; featureDraft:FeatureDraft; indexMode:IndexMode; retentionDraft:RetentionDraft; allowOcr:boolean; onSaved: () => Promise<void>
}) {
  const [items,setItems] = useState<Item[]>([])
  const [running,setRunning] = useState(false)
  const [error,setError] = useState('')
  const [destination,setDestination] = useState('')
  const stop = useRef(false)
  useEffect(() => () => { stop.current = true }, [])
  function choose(files: FileList | null) {
    setError(''); setDestination('')
    const selected = Array.from(files || [])
    if (selected.length > 20) { setItems([]); setError(`本次选择 ${selected.length} 个文件；每批最多20个，请选择较小目录或文件集合。`); return }
    setItems(selected.map((file,index) => { const path = file.webkitRelativePath || file.name
      return { id:`${index}:${path}`, file, path, status:formats.has(file.name.split('.').pop()?.toLowerCase() || '') ? 'pending' : 'unsupported', message:formats.has(file.name.split('.').pop()?.toLowerCase() || '') ? undefined : '不支持此类型，未发送' }
    }))
  }
  async function run(failedOnly = false) {
    if (running) return
    if (!groupName.trim() || chunkSize < 100 || chunkSize > 4000 || chunkOverlap < 0 || chunkOverlap >= chunkSize || chunkOverlap > 1000) { setError('请填写分组，并设置有效分块长度与小于长度的重叠量。'); return }
    let chunkPolicyJson:string;let featurePolicyJson:string;let retentionPolicyJson:string
    try { chunkPolicyJson=JSON.stringify(chunkPolicyRequest(chunkDraft));featurePolicyJson=JSON.stringify(featurePolicyRequest(featureDraft));retentionPolicyJson=JSON.stringify(retentionPolicyRequest(retentionDraft)) }
    catch(failure) { setError(failure instanceof Error?failure.message:'分块策略无效。');return }
    const indexPolicyJson=JSON.stringify(indexPolicyRequest(indexMode))
    const pending = items.filter(item => failedOnly ? item.status === 'failed' : ['pending','failed'].includes(item.status))
    if (!pending.length) return
    stop.current = false; setRunning(true); setError(''); setDestination(groupName)
    let saved = false
    function update(id: string, patch: Partial<Item>) { setItems(previous => previous.map(item => item.id === id ? { ...item,...patch } : item)) }
    try {
      for (const item of pending) {
        if (stop.current) break
        update(item.id,{status:'running',message:undefined})
        const form = new FormData(); form.append('file',item.file); form.append('name',item.path.slice(-200)); form.append('group_name',groupName)
        form.append('chunk_size',String(chunkSize)); form.append('chunk_overlap',String(chunkOverlap))
        form.append('allow_ocr',String(allowOcr))
        form.append('chunk_policy_json',chunkPolicyJson)
        form.append('feature_policy_json',featurePolicyJson)
        form.append('index_policy_json',indexPolicyJson)
        form.append('retention_policy_json',retentionPolicyJson)
        try {
          const response = await fetch('/api/v1/documents/upload',{method:'POST',body:form})
          const payload = await response.json()
          if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : `接入失败（${response.status}）`)
          update(item.id,{status:payload.deduplicated ? 'reused' : 'saved',sourceId:payload.source_id,message:payload.deduplicated ? '复用本分组已提交版本' : `${payload.index?.mode==='direct'?`已保留来源及${payload.planned_chunk_count}个计划片段，仅直接定位`:`已提交${payload.chunk_count}个检索片段`}${payload.parse_quality?.status==='needs_review'?'；解析存在待核或未读部分':''}`})
          saved = true
        } catch (failure) { update(item.id,{status:'failed',message:failure instanceof Error ? failure.message : '接入失败；可重试此项'}) }
      }
      if (saved) await onSaved()
    } catch { setError('接入结果已保留，列表刷新失败；可手动刷新查看已提交来源。') }
    finally { setRunning(false) }
  }
  const statuses = { pending:'未处理',running:'接入中',saved:'已提交',reused:'已复用',failed:'失败',unsupported:'不支持' }
  return <section aria-label="批量资料接入" className="mt-5 space-y-3 border-t pt-4 text-sm">
    <h4 className="font-medium">批量接入文件或目录</h4>
    <p className="text-xs text-xmgray-500">最多20项，使用上方分组和分块设置；选定后点击才上传。目录仅在浏览器中枚举所选文件，服务端不读取本机路径。逐项提交，停止后保留已提交项。</p>
    <fieldset disabled={running} className="space-y-2">
      <label className="block">选择多个文件<input aria-label="选择批量文件" type="file" multiple accept=".json,.md,.docx,.pdf,.txt" onChange={event => choose(event.target.files)} className="block w-full" /></label>
      <label className="block">或选择目录<input aria-label="选择资料目录" type="file" multiple ref={element => { if (element) element.setAttribute('webkitdirectory','') }} onChange={event => choose(event.target.files)} className="block w-full" /></label>
    </fieldset>
    {destination && <p>本次接入分组：{destination}</p>}
    {error && <p role="alert" className="text-red-700">{error}</p>}
    <div className="flex flex-wrap gap-2"><button type="button" className="btn-primary" disabled={running || !items.some(item => ['pending','failed'].includes(item.status))} onClick={() => void run()}>开始／继续批量接入</button>
      <button type="button" className="btn-ghost" disabled={running || !items.some(item => item.status === 'failed')} onClick={() => void run(true)}>只重试失败项</button>
      <button type="button" className="btn-ghost" disabled={!running} onClick={() => { stop.current = true; setError('将在当前文件返回后停止；已发出的请求可能已经提交。') }}>处理完当前项后停止</button></div>
    {!!items.length && <div className="max-h-80 overflow-auto"><table className="w-full text-left text-xs" aria-label="批量接入逐项结果"><thead><tr><th>文件</th><th>状态</th><th>结果／恢复</th></tr></thead><tbody>{items.map(item => <tr key={item.id}>
      <td className="break-all p-2">{item.path}</td><td className="p-2">{statuses[item.status]}</td><td className="p-2">{item.message}<code className="block break-all">{item.sourceId}</code></td>
    </tr>)}</tbody></table></div>}
    <p className="text-xs text-xmgray-500" role="status">{running ? '正在逐项接入…' : '批次状态保留在当前页；已提交来源可从知识源列表回访。刷新后重新选择并上传，相同分组的成功项会复用。'}</p>
  </section>
}
