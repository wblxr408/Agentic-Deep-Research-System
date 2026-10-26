import {useLocale,t,uiMessage} from '../i18n'
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import ClassificationSummary from './ClassificationSummary'
import type { ClassificationSnapshot } from './ClassificationSummary'
import TaxonomyEditor, { defaultTaxonomy, taxonomyRequest } from './TaxonomyEditor'

export default function ClassificationPanel({ sessionId }: { sessionId: string }) {
  useLocale()

  const queryClient = useQueryClient()
  const [draft,setDraft] = useState({ ...defaultTaxonomy, version: `topic-reclassification-${Date.now()}` })
  const [reason,setReason] = useState('按新的研究方向口径重分类')
  const [selected,setSelected] = useState('')
  const [error,setError] = useState('')
  const versions = useQuery<{ versions: ClassificationSnapshot[] }>({ queryKey:['classifications',sessionId], queryFn: async () => {
    const r = await fetch(`/api/v1/research/${sessionId}/classifications`)
    if (!r.ok) throw new Error(t("无法读取分类历史，请稍后重试。"))
    return r.json()
  } })
  const save = useMutation<ClassificationSnapshot, Error>({ mutationFn: async () => {
    const r = await fetch(`/api/v1/research/${sessionId}/classifications`, { method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ taxonomy:taxonomyRequest(draft), reason }) })
    const x = await r.json()
    if (!r.ok) throw new Error(typeof x.detail === 'string' ? x.detail : t("分类配置无效，请检查节点、层次和学科。"))
    return x
  }, onSuccess: x => { setSelected(x.snapshot_id); void versions.refetch(); void queryClient.invalidateQueries({ queryKey:['research',sessionId] }) } })
  const snapshots = versions.data?.versions || []
  const current = snapshots.find(x => x.snapshot_id === selected) || snapshots[snapshots.length-1]
  function download() {
    if (!current) return
    const url = URL.createObjectURL(new Blob([JSON.stringify({ session_id:sessionId, classification:current },null,2)],{type:'application/json;charset=utf-8'}))
    const a = document.createElement('a'); a.href=url; a.download=`classification-${current.snapshot_id}.json`; a.click(); window.setTimeout(() => URL.revokeObjectURL(url),1000)
  }
  return <section aria-label={t("同证据学科重分类")} className="card p-5 text-sm">
    <h3 className="font-medium">{t("同证据学科重分类")}</h3><p className="mt-2 text-xs text-xmgray-500">{t("保存独立分类版本，使用本人的已采纳成果与保留原文；不调用模型或采集新来源。原报告采用首次冻结规则，不随此操作改写。")}</p>
    <TaxonomyEditor value={draft} onChange={setDraft} />
    <label className="mt-2 block text-xs">{t("重分类原因")}<input aria-label={t("重分类原因")} className="input-xm mt-1" value={reason} onChange={e => setReason(e.target.value)} /></label>
    <button className="btn-ghost mt-3" type="button" disabled={save.isPending} onClick={() => { setError('');try { taxonomyRequest(draft);save.mutate() } catch(e) { setError(e instanceof Error?e.message:t("分类配置无效")) } }}>{t("保存同证据分类")}</button>
    {save.isPending && <p role="status">{t("正在按已保存证据计算分类…")}</p>}
    {(error || save.error || versions.error) && <p role="alert" className="mt-2 text-red-700">{error || uiMessage(save.error?.message) || uiMessage(versions.error?.message)}</p>}
    {!!snapshots.length && <label className="mt-3 block text-xs">{t("查看分类版本")}<select aria-label={t("查看分类版本")} className="input-xm mt-1" value={current?.snapshot_id || ''} onChange={e => setSelected(e.target.value)}>{snapshots.map(x => <option value={x.snapshot_id} key={x.snapshot_id}>{x.taxonomy.version} · {x.created_at}</option>)}</select></label>}
    {current && <><ClassificationSummary snapshot={current} /><button type="button" className="btn-ghost mt-3" onClick={download}>{t("下载当前分类数据")}</button></>}
  </section>
}
