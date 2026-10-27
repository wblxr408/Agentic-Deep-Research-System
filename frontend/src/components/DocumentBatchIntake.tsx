import {useLocale,t,uiMessage} from '../i18n'
import { useEffect, useRef, useState } from 'react'
import {chunkPolicyRequest} from './ChunkPolicyPanel'
import type {ChunkDraft} from './ChunkPolicyPanel'
import {featurePolicyRequest,indexPolicyRequest} from './FeaturePolicyPanel'
import type {FeatureDraft,IndexMode} from './FeaturePolicyPanel'
import {retentionPolicyRequest} from './RetentionPolicyPanel'
import type {RetentionDraft} from './RetentionPolicyPanel'

interface Item { id: string; file: File; path: string; status: 'pending' | 'running' | 'saved' | 'reused' | 'failed' | 'unsupported'; message?: string; sourceId?: string }
const formats = new Set(['json','md','docx','pdf','txt'])
export default function DocumentBatchIntake({ groupName, chunkSize, chunkOverlap, chunkDraft, featureDraft, indexMode, retentionDraft, allowOcr, onSaved,onRunningChange,validateBeforeStart }: {
  groupName: string; chunkSize: number; chunkOverlap: number; chunkDraft:ChunkDraft; featureDraft:FeatureDraft; indexMode:IndexMode; retentionDraft:RetentionDraft; allowOcr:boolean; onSaved: () => Promise<void>;onRunningChange?:(running:boolean)=>void;validateBeforeStart?:()=>unknown
}) {
  useLocale()

  const [items,setItems] = useState<Item[]>([])
  const [running,setRunning] = useState(false)
  useEffect(()=>{onRunningChange?.(running)},[running,onRunningChange])
  const [error,setError] = useState('')
  const [notice,setNotice] = useState('')
  const [destination,setDestination] = useState('')
  const stop = useRef(false)
  const dispatching = useRef(false)
  const batchConfiguration = useRef<string | null>(null)
  useEffect(() => () => { stop.current = true }, [])
  function choose(files: FileList | null) {
    if (dispatching.current) return
    batchConfiguration.current = null
    setError(''); setNotice(''); setDestination('')
    const selected = Array.from(files || [])
    if (selected.length > 20) { setItems([]); setError(t("本次选择 {0} 个文件；每批最多20个，请选择较小目录或文件集合。", selected.length)); return }
    setItems(selected.map((file,index) => { const path = file.webkitRelativePath || file.name
      return { id:`${index}:${path}`, file, path, status:formats.has(file.name.split('.').pop()?.toLowerCase() || '') ? 'pending' : 'unsupported', message:formats.has(file.name.split('.').pop()?.toLowerCase() || '') ? undefined : t("不支持此类型，未发送") }
    }))
  }
  function reopen() {
    if (dispatching.current) return
    batchConfiguration.current = null
    setDestination(''); setError(''); setNotice(t("已重新列为待处理；已有来源保留，点击开始后按当前设置接入全部支持文件。"))
    setItems(previous => previous.map<Item>(item => item.status === 'unsupported' ? item : {
      ...item,status:'pending',message:undefined,sourceId:undefined,
    }))
  }
  async function run(failedOnly = false) {
    if (dispatching.current) return
    if (!groupName.trim() || chunkSize < 100 || chunkSize > 4000 || chunkOverlap < 0 || chunkOverlap >= chunkSize || chunkOverlap > 1000) { setError(t("请填写分组，并设置有效分块长度与小于长度的重叠量。")); return }
    let chunkPolicyJson:string;let featurePolicyJson:string;let retentionPolicyJson:string
    try { validateBeforeStart?.();chunkPolicyJson=JSON.stringify(chunkPolicyRequest(chunkDraft));featurePolicyJson=JSON.stringify(featurePolicyRequest(featureDraft));retentionPolicyJson=JSON.stringify(retentionPolicyRequest(retentionDraft)) }
    catch(failure) { setError(failure instanceof Error?uiMessage(failure.message):t("分块策略无效。"));return }
    const indexPolicyJson=JSON.stringify(indexPolicyRequest(indexMode))
    const configuration=JSON.stringify({groupName,chunkSize,chunkOverlap,allowOcr,
      chunkPolicyJson,featurePolicyJson,indexPolicyJson,retentionPolicyJson})
    if (batchConfiguration.current !== null && batchConfiguration.current !== configuration) {
      setError(t("本批接入设置已改变，不能沿用已提交状态继续或只重试失败项。请恢复原设置，或选择“重新使用当前设置”；已有来源不会删除。"))
      return
    }
    const pending = items.filter(item => failedOnly ? item.status === 'failed' : ['pending','failed'].includes(item.status))
    if (!pending.length) return
    // Lock synchronously before the first request; React's next render alone
    // must not allow two clicks to dispatch the same batch concurrently.
    dispatching.current = true; batchConfiguration.current = configuration
    stop.current = false; setRunning(true); setError(''); setNotice(''); setDestination(groupName)
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
          if (!response.ok) throw new Error(payload.detail==='semantic_chunking_unavailable_or_incomplete'?t('语义分块需要本地固定版本的编码模型，且全部片段须能完整编码。'):payload.detail==='sparse_encoding_unavailable_or_incomplete'?t('学习稀疏特征需要已配置的本地模型，且全部片段须能完整编码。'):payload.detail==='sparse_feature_budget_exceeded'?t('学习稀疏特征超出资料大小限制。'):payload.detail==='stemming_feature_budget_exceeded'?t('英文词形特征超出资料大小限制。'):payload.detail==='multivector_encoding_unavailable_or_incomplete'?t('细粒度语义需要配置本地模型，并确保每个片段可完整处理。'):payload.detail==='multivector_feature_budget_exceeded'?t('细粒度语义特征超出资料大小限制。'):typeof payload.detail === 'string' ? payload.detail : t("接入失败（{0}）", response.status))
          update(item.id,{status:payload.deduplicated ? 'reused' : 'saved',sourceId:payload.source_id,message:payload.deduplicated ? t("复用本分组已提交版本") : `${payload.index?.mode==='direct'?t("已保留来源及{0}个计划片段，仅直接定位", payload.planned_chunk_count):t("已提交{0}个检索片段", payload.chunk_count)}${payload.parse_quality?.status==='needs_review'?t("；解析存在待核或未读部分"):''}`})
          saved = true
        } catch (failure) { update(item.id,{status:'failed',message:failure instanceof Error ? uiMessage(failure.message) : t("接入失败；可重试此项")}) }
      }
      if (saved) await onSaved()
    } catch { setError(t("接入结果已保留，列表刷新失败；可手动刷新查看已提交来源。")) }
    finally { dispatching.current = false; setRunning(false) }
  }
  const statuses = { pending:t("未处理"),running:t("接入中"),saved:t("已提交"),reused:t("已复用"),failed:t("失败"),unsupported:t("不支持") }
  return <section aria-label={t("批量资料接入")} className="mt-5 space-y-3 border-t pt-4 text-sm">
    <h4 className="font-medium">{t("选择文件或文件夹")}</h4>
    <fieldset disabled={running} className="space-y-2">
      <label className="block">{t("选择多个文件")}<input aria-label={t("选择批量文件")} type="file" multiple accept=".json,.md,.docx,.pdf,.txt" onChange={event => choose(event.target.files)} className="block w-full" /></label>
      <label className="block">{t("或选择目录")}<input aria-label={t("选择资料目录")} type="file" multiple ref={element => { if (element) element.setAttribute('webkitdirectory','') }} onChange={event => choose(event.target.files)} className="block w-full" /></label>
    </fieldset>
    {destination && <p>{t("本次接入分组：")}{destination}</p>}
    {notice && <p role="status">{uiMessage(notice)}</p>}
    {error && <p role="alert" className="text-red-700">{uiMessage(error)}</p>}
    <div className="flex flex-wrap gap-2"><button type="button" className="btn-primary" disabled={running || !items.some(item => ['pending','failed'].includes(item.status))} onClick={() => void run()}>{t("开始导入")}</button>
      <button type="button" className="btn-ghost" disabled={running || !items.some(item => item.status === 'failed')} onClick={() => void run(true)}>{t("只重试失败项")}</button>
      <button type="button" className="btn-ghost" disabled={running || !items.some(item => item.status !== 'unsupported')} onClick={reopen}>{t("重新使用当前设置")}</button>
      <button type="button" className="btn-ghost" disabled={!running} onClick={() => { stop.current = true; setError(t("将在当前文件返回后停止；已发出的请求可能已经提交。")) }}>{t("停止后续导入")}</button></div>
    {!!items.length && <div className="max-h-80 overflow-auto"><table className="w-full text-left text-xs" aria-label={t("批量接入逐项结果")}><thead><tr><th>{t("文件")}</th><th>{t("状态")}</th><th>{t("结果／恢复")}</th></tr></thead><tbody>{items.map(item => <tr key={item.id}>
      <td className="break-all p-2">{item.path}</td><td className="p-2">{statuses[item.status]}</td><td className="p-2">{item.message}</td>
    </tr>)}</tbody></table></div>}
    <p className="text-xs text-xmgray-500" role="status">{running ? t("正在逐项接入…") : t("批次状态保留在当前页；已提交来源可从知识源列表回访。刷新后重新选择并上传，相同分组的成功项会复用。")}</p>
  </section>
}
