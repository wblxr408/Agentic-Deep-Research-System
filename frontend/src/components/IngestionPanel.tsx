import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import ArchiveTaskEvidence from './ArchiveTaskEvidence'

interface RetainedVersion { version_id: string; character_count: number; format: string; coverage: string; collected_at: string | null; first_evidence_id: string; acquisition: Record<string, unknown>;archive_available?:boolean }
interface IngestionData {
  persisted: boolean; origin: string
  view: { schema_version: string; session_id: string; retained_content: string; reuse_scope: string
    body_duplicates?:{method:string;groups:unknown[];automatic_removal:boolean}
    summary: Record<string, number | string>; conflicts: unknown[]
    sources: Record<string, { source_id: string; source_url: string | null; title: string | null; source_type: string; evidence_ids: string[]; versions: Record<string, RetainedVersion> }>
    events: Record<string, { evidence_id: string; source_id: string; version_id: string; outcome: string }>
    recovery_events: Record<string, { outcome_id: string; node_id: string; tool_name: string; error_category: string | null; recovery_status: string; retry_count: number; approval_request_id?: string | null }>
  }
  corpus: Record<string, unknown> | null; declared_scope: Record<string, unknown>
}
function sourceLink(value: string | null) { try { const url = new URL(value || ''); return ['http:','https:'].includes(url.protocol) ? url.href : undefined } catch { return undefined } }
const recoveryNames: Record<string, string> = { resolved_by_later_success:'后续已恢复', pending_manual_review:'终止，待人工处理', awaiting_original_approval:'等待原审批', bounded_original_retry_policy:'原预算内有限重试', canceled_no_automatic_retry:'任务已取消，不自动重试', budget_exhausted_requires_explicit_recovery:'预算停止，需显式恢复条件' }
export default function IngestionPanel({ sessionId }: { sessionId: string }) {
  const [downloadError,setDownloadError] = useState('')
  const query = useQuery<IngestionData>({queryKey:['ingestion',sessionId],queryFn:async () => {
    const response = await fetch(`/api/v1/research/${sessionId}/ingestion`)
    if (!response.ok) throw new Error('无法读取当前任务的接入账本。')
    return response.json()
  }})
  const data = query.data
  async function download() {
    setDownloadError('')
    try {
    const response = await fetch(`/api/v1/research/${sessionId}/ingestion?include_content=true`)
    if (!response.ok) throw new Error('原文下载失败，请刷新登录状态后重试。')
    const payload = await response.json()
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json;charset=utf-8'}))
    const link = document.createElement('a'); link.href = url; link.download = `research-${sessionId}-retained-evidence.json`; link.click()
    window.setTimeout(() => URL.revokeObjectURL(url),1000)
    } catch (error) { setDownloadError(error instanceof Error ? error.message : '原文下载失败。') }
  }
  return <details className="card p-5 text-sm" aria-label="任务证据接入账本">
    <summary className="cursor-pointer font-medium">证据接入、版本与恢复</summary>
    <p className="my-2 text-xs text-xmgray-600">当前任务内保留取得后的文字；不代表原始网络字节、现实论文全集或事实审核通过。不自动转入跨任务知识库。</p>
    <button type="button" className="btn-ghost" disabled={query.isFetching} onClick={() => void query.refetch()}>刷新账本</button>
    {query.isPending && <p role="status">正在读取已保存接入状态…</p>}
    {query.error && <p role="alert" className="text-red-700">{query.error.message}</p>}
    {data && <div className="mt-3 space-y-4">
      <p>{data.persisted ? '已保存任务账本' : '历史快照只读投影；未改写原研究'} · {data.view.schema_version}</p>
      <dl className="flex flex-wrap gap-3">{Object.entries(data.view.summary).filter(([key]) => key !== 'schema_version').map(([key,value]) => <div key={key}><dt className="text-xs text-xmgray-500">{({sources:'来源',retained_versions:'保留版本',intake_events:'接入事件',discovery_only_versions:'仅发现版本',reused_version_events:'版本复用事件',unresolved_outcomes:'待处理结果',recovered_outcomes:'已恢复结果',conflicts:'输入冲突',body_duplicate_groups:'相同正文分组'} as Record<string,string>)[key] || key}</dt><dd>{value}</dd></div>)}</dl>
      <div className="max-h-[32rem] overflow-auto"><table aria-label="取得资料及版本" className="w-full text-left text-xs"><thead><tr><th>来源</th><th>版本与覆盖</th><th>取得时间与证据引用</th></tr></thead>
        <tbody>{Object.values(data.view.sources).flatMap(source => Object.values(source.versions).map(version => <tr key={`${source.source_id}:${version.version_id}`}>
          <th className="max-w-xs break-all p-2 font-normal">{sourceLink(source.source_url) ? <a href={sourceLink(source.source_url)} target="_blank" rel="noopener noreferrer">{source.title || source.source_url}</a> : source.title || source.source_type}<p>{source.source_type}</p></th>
          <td className="max-w-xs break-all p-2">{version.coverage} · {version.format} · {version.character_count} 字符<details><summary>版本与定位</summary><code>{version.version_id}</code><pre className="whitespace-pre-wrap break-words">{JSON.stringify(version.acquisition,null,2)}</pre></details></td>
          <td className="p-2">{version.collected_at || '获取时间未记录'}<code className="block">{version.first_evidence_id}</code><p>偏移按该版本保留文字字符定位</p>
            {version.archive_available&&<ArchiveTaskEvidence
              key={version.version_id} sessionId={sessionId} evidenceId={version.first_evidence_id} versionId={version.version_id}
              title={source.title||source.source_url||'保留网页原文'}/>}
          </td>
        </tr>))}</tbody></table></div>
      <section><h4 className="font-medium">失败、审批与恢复记录</h4><p className="text-xs">重试与审批沿用原任务操作及预算；这里不自动新建工作。</p>
        <ul>{Object.values(data.view.recovery_events).map(record => <li key={record.outcome_id} className="my-2 rounded-lg bg-xmgray-50 p-2">{record.node_id} · {record.tool_name} · {recoveryNames[record.recovery_status] || record.recovery_status} · {record.error_category || '未记录原因'} · 重试 {record.retry_count}{record.approval_request_id && <code className="block">审批 {record.approval_request_id}</code>}</li>)}</ul>
        {!Object.keys(data.view.recovery_events).length && <p>当前保存账本中没有失败或审批结果。</p>}
      </section>
      {!!data.view.conflicts.length && <pre className="whitespace-pre-wrap break-words text-amber-800">{JSON.stringify(data.view.conflicts,null,2)}</pre>}
      {!!data.view.body_duplicates?.groups.length&&<details><summary>相同正文的来源与版本</summary>
        <p className="text-xs">相同文字不代表独立来源或事实已经核实；原始引用全部保留。</p>
        <pre className="whitespace-pre-wrap break-words text-xs">{JSON.stringify(data.view.body_duplicates,null,2)}</pre>
      </details>}
      <details><summary>声明范围与样本流转</summary><pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify({declared_scope:data.declared_scope,corpus:data.corpus},null,2)}</pre></details>
      <button type="button" className="btn-ghost" onClick={() => void download()}>下载本人任务的保留原文与版本</button>
      {downloadError && <p role="alert" className="text-red-700">{downloadError}</p>}
    </div>}
  </details>
}
