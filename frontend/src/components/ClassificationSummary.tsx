import StatisticsSummary from './StatisticsSummary'
import type { StatisticalSnapshot } from './StatisticsSummary'

export interface ClassificationSnapshot {
  snapshot_id: string; created_at: string; reason: string
  taxonomy: { version: string; semantics: string; request: { preset: string; version: string; nodes: unknown[] }; nodes: Array<{ node_id: string; label: string }> }
  records: Array<{ output_id: string; title: string; year: number | null; labels: Array<{ node_id: string; label: string; axis: string; role: string; ancestors: string[]; basis: { evidence_id: string; source_url: string; start: number; end: number; quote: string } }> }>
  annual: Array<{ year: number; publication_count: number; label_counts: Record<string, number> }>
  unobserved_years: number[]; interpretation: string
  statistics?: StatisticalSnapshot
  comparison?: { previous_version: string; changes: unknown[]; same_publication_ids: boolean; same_evidence_ids: boolean } | null
}
const axes = ['problem', 'method', 'application']
export default function ClassificationSummary({ snapshot }: { snapshot: ClassificationSnapshot }) {
  const names = Object.fromEntries(snapshot.taxonomy.nodes.map(node => [node.node_id, node.label]))
  return <section aria-label="学科分类结果" className="mt-4 space-y-3 text-sm">
    <h3 className="font-semibold">问题、方法与应用分类 · {snapshot.taxonomy.version}</h3><p className="text-xs text-xmgray-600">{snapshot.taxonomy.semantics}</p>
    <div className="overflow-x-auto"><table aria-label="成果学科分类" className="w-full text-left"><thead><tr><th className="min-w-56 p-2">成果</th><th className="p-2">年</th>{['问题','方法','应用'].map(label => <th className="min-w-40 p-2" key={label}>{label}</th>)}</tr></thead>
      <tbody>{snapshot.records.map(row => <tr key={row.output_id}><th className="p-2 font-normal">{row.title}</th><td className="p-2">{row.year || '未知'}</td>{axes.map(axis => <td className="p-2" key={axis}>{row.labels.filter(tag => tag.axis === axis).map(tag => `${tag.label}（${tag.role === 'core' ? '核心' : '关联'}）`).join('、') || '未知'}</td>)}</tr>)}</tbody></table></div>
    <p className="text-xs">{snapshot.interpretation}</p>
    <table aria-label="分类年度样本" className="w-full text-left"><thead><tr><th>已覆盖年</th><th>采纳发表</th><th>交叉标签计数</th></tr></thead><tbody>{snapshot.annual.map(row => <tr key={row.year}><th className="font-normal">{row.year}</th><td>{row.publication_count}</td><td>{Object.entries(row.label_counts).map(([id,count]) => `${names[id] || id}: ${count}`).join('；') || '未知'}</td></tr>)}</tbody></table>
    <p className="text-xs">未覆盖年份（不补零）：{snapshot.unobserved_years.join('、') || '无范围内缺年；仍不代表全集'}</p>
    {snapshot.statistics && <StatisticsSummary snapshot={snapshot.statistics} />}
    {snapshot.comparison && <p aria-label="重分类变化说明" className="rounded-lg bg-amber-50 p-3 text-xs">从 {snapshot.comparison.previous_version} 重分类，{snapshot.comparison.changes.length} 项成果标签变化；这是规则变化，不能解释为成果或投入增长。{snapshot.comparison.same_publication_ids && snapshot.comparison.same_evidence_ids ? '使用相同成果与证据。' : '成果或证据集合不同，需核对范围。'}</p>}
    <details><summary className="cursor-pointer">分类依据与层次</summary><ul className="mt-2 space-y-2">{snapshot.records.flatMap(row => row.labels.map(tag => <li key={`${row.output_id}:${tag.node_id}`}>
      {tag.ancestors.map(id => names[id] || id).reverse().concat(tag.label).join(' › ')} · <q>{tag.basis.quote}</q> · {tag.basis.evidence_id} · 字符 {tag.basis.start}–{tag.basis.end}
    </li>))}</ul></details><details><summary className="cursor-pointer">完整分类快照</summary><pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(snapshot,null,2)}</pre></details>
  </section>
}
