import type { WeightPreview } from './OrganizationWeightsPanel'
import { dimensionLabels } from './OrganizationWeightsPanel'
import CorpusSummary from './CorpusSummary'
import type { CorpusSnapshot } from './CorpusSummary'
import ClassificationSummary from './ClassificationSummary'
import type { ClassificationSnapshot } from './ClassificationSummary'
import RelationshipSummary from './RelationshipSummary'
import type { RelationshipView } from './RelationshipSummary'
import TechnicalReadingSummary from './TechnicalReadingSummary'
import type { TechnicalReading } from './TechnicalReadingSummary'
import TrendSummary from './TrendSummary'
import type { TrendView } from './TrendSummary'
import ActionSummary from './ActionSummary'
import type { ActionView } from './ActionSummary'
import StatisticsSummary from './StatisticsSummary'
import type { StatisticalSnapshot } from './StatisticsSummary'

interface ReportEntity { entity_id: string; name: string; type: string; resolution_status?: string; source_urls?: string[] }
export interface OrganizationReportSnapshot {
  schema_version: string
  configuration: {
    scope: { topic: string; organization_types: string[]; entities: ReportEntity[]; disciplines: string[]; start_date: string; end_date: string }
    selected_preset?: { name: string; preset_id: string; version: number } | null
    [key: string]: unknown
  }
  weights: WeightPreview
  corpus?: CorpusSnapshot | null
  classification?: ClassificationSnapshot | null
  relationships?: RelationshipView | null
  technical_reading?: TechnicalReading | null
  trends?: TrendView | null
  actions?: ActionView | null
  statistics?: StatisticalSnapshot | null
  analysis?: { purpose: string; purpose_label: string; modules: string[]; module_labels: Record<string, string>; rule_version: string } | null
  versions: Record<string, string | null>
  request_frozen_at: string | null
  sources: Array<{ evidence_id: string; source_title: string | null; source_url: string; collected_at: string | null }>
  sample: {
    summary: { publication_count: number; research_family_count: number } | null
    views: Array<{ entity_id: string; name: string; publication_count: number; research_family_count: number }>
    entities: ReportEntity[]; coverage: string; counting_note: string
  }
  evaluation: {
    applied_to_evidence: boolean; catalog_schema_version: string | null; adapter_rule_version: string | null
    schemes: Array<{ scheme_id: string; availability: string; access_note: string; source_url: string }>
    sources: Array<{ source_id: string; scheme_id: string; edition: string; metric_year: number; access: string; coverage: string; source_url: string }>
  }
  pending_records: Array<{ kind: string; title?: string; id?: string; reason: string }>
  gaps: string[]
  matching_semantics: string
}

function sourceUrl(value: string) {
  try { const parsed = new URL(value); return ['https:', 'http:'].includes(parsed.protocol) ? parsed.href : undefined }
  catch { return undefined }
}
const types: Record<string, string> = { university: '高校', laboratory: '科研实验室', company: '企业' }

export default function OrganizationReportSummary({ snapshot }: { snapshot: OrganizationReportSnapshot }) {
  const { configuration, weights, sample, evaluation } = snapshot
  const scope = configuration.scope
  return <section aria-label="报告口径与冻结配置" className="mb-6 rounded-xl border border-xmgray-200 bg-xmgray-50 p-4 text-sm">
    <h2 className="font-semibold text-xmgray-800">研究对象、口径与权重</h2>
    {snapshot.analysis && <div className="mt-2 space-y-1">
      <p aria-label="报告研究目的">研究目的：<span>{snapshot.analysis.purpose_label}</span></p>
      <p aria-label="报告研究模块">研究模块：<span>{snapshot.analysis.modules.map(key => snapshot.analysis!.module_labels[key]).join('、')}</span></p>
      <p className="text-xs text-xmgray-500">目的与模块采用本次冻结配置，独立于匹配权重和报告模板。</p>
    </div>}
    {snapshot.corpus && <CorpusSummary corpus={snapshot.corpus} />}
    {snapshot.classification && <ClassificationSummary snapshot={snapshot.classification} />}
    {snapshot.relationships && <RelationshipSummary view={snapshot.relationships} />}
    {snapshot.technical_reading && <TechnicalReadingSummary reading={snapshot.technical_reading} />}
    {snapshot.trends && <TrendSummary view={snapshot.trends} />}
    {snapshot.actions && <ActionSummary view={snapshot.actions} />}
    {snapshot.statistics && <StatisticsSummary snapshot={snapshot.statistics} />}
    <p className="mt-2">{sample.entities.map(entity => entity.name).join('、') || '范围内候选发现尚未确立对象'} · {scope.disciplines.join('、')}</p>
    <p className="mt-1 text-xs text-xmgray-600">{scope.start_date} 至 {scope.end_date} · 配置 {weights.config_version}</p>
    <details className="mt-3">
      <summary role="button" className="cursor-pointer text-xm-700">展开研究口径</summary>
      <div className="mt-3 space-y-4">
        <section><h3>研究范围</h3><p>{scope.topic} · {scope.organization_types.map(type => types[type] || type).join('、')}</p>
          <p>请求冻结：{snapshot.request_frozen_at || '未保存'}；采集时间在实际来源中逐项保留。</p>
          <ul>{sample.entities.map(entity => <li key={entity.entity_id}>{entity.source_urls?.length ?
            <a href={sourceUrl(entity.source_urls[0])} target="_blank" rel="noopener noreferrer">{entity.name}</a> : entity.name}
            {' · '}{types[entity.type] || entity.type} · {entity.resolution_status || '待核'}</li>)}</ul>
        </section>
        <section><h3>统计口径</h3><p>{sample.counting_note}</p>
          {sample.summary ? <table aria-label="报告对象样本"><thead><tr><th>对象</th><th>发表记录</th><th>研究家族</th></tr></thead>
            <tbody>{sample.views.map(view => <tr key={view.entity_id}><th scope="row">{view.name}</th><td>{view.publication_count}</td><td>{view.research_family_count}</td></tr>)}
              <tr><th scope="row">去重汇总</th><td>{sample.summary.publication_count}</td><td>{sample.summary.research_family_count}</td></tr></tbody></table> : <p>未建立成果统计；证据条数不作为论文数。</p>}
          <p>{snapshot.matching_semantics}</p>
        </section>
        <section><h3>有效权重</h3>
          <table aria-label="报告有效权重"><thead><tr><th>维度</th><th>生效比例</th></tr></thead><tbody>
            {Object.entries(weights.effective_weights).map(([key, value]) => <tr key={key}><th scope="row">{dimensionLabels[key] || key}</th><td>{(value * 100).toFixed(2)}%</td></tr>)}
          </tbody></table>
          <p>规则 {weights.rule_version} · 预设 {weights.preset_version} · {snapshot.versions.scope_rule_version}</p>
          {configuration.selected_preset && <p>个人方案：{configuration.selected_preset.name} · v{configuration.selected_preset.version}</p>}
          <details><summary>原始权重、组内比例及有序映射</summary><pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(weights, null, 2)}</pre></details>
        </section>
        <section><h3>评价口径与来源可用性</h3>
          <p>{evaluation.applied_to_evidence ? '成果评价采用本次保存的适用记录。' : '目录样本未自动应用到本次成果；缺少指标不作零分或最低等级。'}</p>
          <p>{evaluation.catalog_schema_version || '目录版本未保存'} · {evaluation.adapter_rule_version || '规则版本未保存'}</p>
          <ul>{evaluation.schemes.map(scheme => <li key={scheme.scheme_id}>
            <a href={sourceUrl(scheme.source_url)} target="_blank" rel="noopener noreferrer">{scheme.scheme_id}</a> · {evaluation.sources.some(source => source.scheme_id === scheme.scheme_id && source.access === 'public') ? '部分公开样本' : '需授权导入／尚无公开样本'}
          </li>)}</ul>
          <details><summary>目录来源版本与覆盖</summary><ul>{evaluation.sources.map(source => <li key={source.source_id}>
            <a href={sourceUrl(source.source_url)} target="_blank" rel="noopener noreferrer">{source.scheme_id} · {source.edition} · {source.metric_year}</a> · {source.access} · {source.coverage}
          </li>)}</ul></details>
        </section>
        <section><h3>实际取证来源</h3><ol>{snapshot.sources.map(source => <li key={source.evidence_id}>
          <a href={sourceUrl(source.source_url)} target="_blank" rel="noopener noreferrer">{source.source_title || source.source_url}</a>
          <span> · {source.evidence_id} · {source.collected_at || '采集时间未保存'}</span>
        </li>)}</ol></section>
        <section><h3>缺口与解释边界</h3><ul>{snapshot.gaps.map((gap, index) => <li key={index}>{gap}</li>)}</ul>
          <ul>{snapshot.pending_records.map((item, index) => <li key={index}>待核 {item.title || item.id || item.kind}：{item.reason}</li>)}</ul>
        </section>
      </div>
    </details>
  </section>
}
