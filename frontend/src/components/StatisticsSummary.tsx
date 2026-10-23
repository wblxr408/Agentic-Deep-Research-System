export interface StatisticalMetric {
  metric_id: string; label: string; kind: string; value: number | null; display: string
  unit: string; counting_unit?: string; numerator: number | null; denominator: number | null
  member_ids?: string[]; numerator_ids?: string[]; denominator_ids?: string[]; basis?: string; status?: string
}
export interface StatisticalSnapshot {
  schema_version: string; snapshot_id: string; classification_snapshot_id: string | null
  metric_registry: Record<string, StatisticalMetric>; conventions: string[]; calculation_status: string
  conflicts: Array<Record<string, unknown>>
  series: { annual_publications: Array<{ x: number; y: number | null; metric_id: string; missing: boolean }>
    classification_publications: Array<{ x: string; y: number; metric_id: string }> }
}

export default function StatisticsSummary({ snapshot }: { snapshot: StatisticalSnapshot }) {
  const metrics = Object.values(snapshot.metric_registry)
  const annual = snapshot.series.annual_publications
  const chartWidth = Math.max(500, annual.length * 50 + 60)
  const maximum = Math.max(1, ...annual.map(point => point.y ?? 0))
  const labels = snapshot.series.classification_publications.slice(0, 40)
  const labelMaximum = Math.max(1, ...labels.map(point => point.y))
  return <section aria-label="统一统计快照" className="mt-4 space-y-3 text-sm" data-statistics-snapshot={snapshot.snapshot_id}>
    <h3 className="font-semibold">可复核统计与样本图表</h3>
    <p className="break-all text-xs text-xmgray-600">数据版本：{snapshot.snapshot_id} · {snapshot.calculation_status}</p>
    <ul className="list-disc space-y-1 pl-5 text-xs">{snapshot.conventions.map(note => <li key={note}>{note}</li>)}</ul>
    <figure className="overflow-x-auto rounded-lg border bg-white p-3">
      <figcaption>年度采纳发表样本；虚线表示未覆盖，不能按零计算增长。</figcaption>
      <svg role="img" aria-label="年度采纳发表样本，未覆盖年份单独标记" viewBox={`0 0 ${chartWidth} 250`} style={{ minWidth: chartWidth }}>
        <line x1="35" y1="195" x2={chartWidth - 10} y2="195" stroke="#94a3b8" />
        {annual.map((point, index) => {
          const metric = snapshot.metric_registry[point.metric_id]
          const x = 45 + index * ((chartWidth - 60) / Math.max(1, annual.length))
          const height = point.y === null ? 0 : point.y / maximum * 145
          return <g key={point.metric_id} data-metric-id={point.metric_id}>
            <title>{`${point.x}：${metric.display}；${point.metric_id}`}</title>
            {point.missing ? <><rect x={x} y="165" width="25" height="30" fill="none" stroke="#b45309" strokeDasharray="3 3" /><text x={x + 12} y="155" textAnchor="middle" fontSize="10">未覆盖</text></> :
              <><rect x={x} y={195 - height} width="25" height={height} fill="#0f766e" /><text x={x + 12} y={185 - height} textAnchor="middle" fontSize="12">{metric.display}</text></>}
            <text x={x + 12} y="215" textAnchor="middle" fontSize="11">{point.x}</text>
          </g>
        })}
      </svg>
    </figure>
    {!!labels.length && <figure className="overflow-x-auto rounded-lg border bg-white p-3">
      <figcaption>各标签已观测匹配篇数；每篇每标签只计一次，同篇可计入多个标签。</figcaption>
      <svg role="img" aria-label="多标签采纳发表分布" viewBox={`0 0 640 ${labels.length * 32 + 20}`} className="w-full min-w-[500px]">
        {labels.map((point, index) => <g key={point.metric_id} data-metric-id={point.metric_id}>
          <title>{`${point.x}：${snapshot.metric_registry[point.metric_id].display}；${point.metric_id}`}</title>
          <text x="4" y={index * 32 + 20} fontSize="11">{point.x.length > 22 ? point.x.slice(0, 22) + '…' : point.x}</text>
          <rect x="220" y={index * 32 + 6} width={point.y / labelMaximum * 340} height="18" fill="#2563eb" />
          <text x={230 + point.y / labelMaximum * 340} y={index * 32 + 20} fontSize="12">{snapshot.metric_registry[point.metric_id].display}</text>
        </g>)}
      </svg>
      {snapshot.series.classification_publications.length > labels.length && <p>图中显示前 {labels.length} 个标签，全部数值见下表与下载快照。</p>}
    </figure>}
    <details><summary className="cursor-pointer">全部指标、分子分母与成员依据</summary>
      <div className="max-h-[36rem] overflow-auto"><table aria-label="可复算统计指标" className="w-full text-left text-xs">
        <thead><tr><th>指标</th><th>数值</th><th>分子</th><th>分母</th><th>计数单位与依据</th></tr></thead>
        <tbody>{metrics.map(metric => <tr key={metric.metric_id} data-metric-id={metric.metric_id}>
          <th className="p-2 font-normal">{metric.label}<code className="block break-all text-[10px]">{metric.metric_id}</code></th>
          <td className="p-2">{metric.display}</td><td className="p-2">{metric.numerator ?? '不适用／未知'}</td><td className="p-2">{metric.denominator ?? '不适用'}</td>
          <td className="p-2">{metric.counting_unit || metric.unit}<details><summary>成员与口径</summary><pre className="max-w-lg whitespace-pre-wrap break-words">{JSON.stringify(metric, null, 2)}</pre></details></td>
        </tr>)}</tbody>
      </table></div>
    </details>
    {!!snapshot.conflicts.length && <details open className="rounded-lg bg-amber-50 p-3"><summary>输入统计冲突；展示值采用程序重算结果</summary><pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(snapshot.conflicts, null, 2)}</pre></details>}
  </section>
}
