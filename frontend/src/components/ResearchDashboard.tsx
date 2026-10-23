/**
 * ResearchDashboard - Xiaomi-style research interface.
 *
 * Design: Xiaomi's "less is more" philosophy
 * - Large search input centered at top
 * - Clean white cards with subtle shadows
 * - Orange accent for active states
 * - Generous whitespace, minimal chrome
 * - Split layout: traces | report
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useSSE } from '../hooks/useSSE'
import type { SSEvent } from '../hooks/useSSE'
import AgentTrace from './AgentTrace'
import ToolTrace from './ToolTrace'
import ReportPreview from './ReportPreview'
import ReportDownloads from './ReportDownloads'
import ReportHistory from './ReportHistory'
import ClassificationPanel from './ClassificationPanel'
import IngestionPanel from './IngestionPanel'
import type { OrganizationReportSnapshot } from './OrganizationReportSummary'
import ChannelPanel from './ChannelPanel'
import OrganizationResearchPanel, { defaultOrganizationDraft, organizationRequest } from './OrganizationResearchPanel'
import OrganizationWeightsPanel from './OrganizationWeightsPanel'
import type { WeightSelection } from './OrganizationWeightsPanel'
import ResearchMatchingPanel from './ResearchMatchingPanel'
import QueryUnderstandingPanel, { defaultQueryDraft, queryDraftRequest, UnderstandingSummary } from './QueryUnderstandingPanel'
import type { QueryDraft, UnderstandingSnapshot } from './QueryUnderstandingPanel'
import ResearchPlanSummary from './ResearchPlanSummary'
import ResearchConfigurationEditor from './ResearchConfigurationEditor'
import ResearchQuality from './ResearchQuality'
import ResearchCancellation from './ResearchCancellation'
import type { PlanSummaryProps } from './ResearchPlanSummary'
import type { DeliveryView } from './ReportDeliveryView'

interface ResearchResult {
  execution_id?:string|null
  report_audit?: {needs_review?:boolean;audit_incomplete?:boolean;total_claims?:number;supported_claims?:number;
    revision_requests?:Array<{claim_id:string;text:string;reason:string;requested_action:string}>}|null
  analysis_recovery_available?: boolean
  analysis_progress?: {phase: string|null;status:string;completed_steps:number}|null
  budget_state?: {used_total_tokens?:number;max_total_tokens?:number;cost_status?:string;token_usage_estimated?:boolean;hard_stop_reason?:string|null;model_stop_reason?:string|null;inflight_model_requests?:number} | null
  report_editorial?: { note?: string } | null
  delivery_view?: DeliveryView | null
  plan_manifest?: PlanSummaryProps['plan']
  plan_history?: PlanSummaryProps['history']
  iteration_control?: PlanSummaryProps['control']
  query_understanding?: UnderstandingSnapshot | null
  session_id: string
  query: string
  status: string
  report: string | null
  citations: Array<{
    citation_id: string
    source_url: string
    source_title: string
    source_type: string
    extracted_evidence?:string
    locator?:{evidence_id:string;start:number;end:number;parse_version_id?:string|null;chunk_reference?:unknown;returned_span?:unknown}|null
  }> | Record<string, unknown> | null
  agent_trace: unknown[]
  execution_plan?: { nodes: Array<{ node_id: string; node_type: string; query: string; status: string }> }
  restart_parameters?: Record<string, unknown>
  export_view?: unknown
  skill_context?: {
    auto_matched_skill_ids?: string[]
    manually_enabled_skill_ids?: string[]
    manually_disabled_skill_ids?: string[]
    effective_skill_ids?: string[]
    effective_tool_allowlist?: string[]
    match_results?: Array<{
      skill_id: string
      slug: string
      name: string
      reason: string
      priority: number
      allowed_tools: string[]
    }>
  }
  created_at: string
  completed_at: string | null
  organization_research?: {
    purpose?: string
    modules?: string[]
    corpus?: Record<string, unknown>
    taxonomy?: { request?: unknown }
    action_requirements?: unknown
    scope: { organization_types: string[]; entities: Array<{ entity_id: string; name: string }>; disciplines: string[]; start_date: string; end_date: string }
    effective_weights: { effective_weights: Record<string, number> }
  } | null
  organization_result?: { evidence_count?: number; counting_unit?: string; gaps?: string[]; report_summary?: OrganizationReportSnapshot;
    analyst_context?:unknown;report_context?:unknown;
    chart_rendering?:{status:string;reason?:string|null}} | null
}

interface SkillItem {
  id: string
  name: string
  slug: string
  description: string
  enabled: boolean
  allowed_tools: string[]
}

interface ResearchDashboardProps {
  onBack?: () => void
}

function ResearchDashboard({ onBack }: ResearchDashboardProps) {
  const [query, setQuery] = useState('')
  const [ragGroup, setRagGroup] = useState('')
  const [useInternalDocs, setUseInternalDocs] = useState(false)
  const [outputLength, setOutputLength] = useState<'short' | 'medium' | 'long'>('medium')
  const [activeSessionId, setActiveSessionId] = useState<string | null>(() => new URLSearchParams(window.location.search).get('session'))
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamRunKey, setStreamRunKey] = useState('')
  const [sessionStatus, setSessionStatus] = useState<string | null>(null)
  const [enabledSkillIds, setEnabledSkillIds] = useState<string[]>([])
  const [disabledSkillIds, setDisabledSkillIds] = useState<string[]>([])
  const [selectedChannels, setSelectedChannels] = useState<string[]>([])
  const [organizationDraft, setOrganizationDraft] = useState(defaultOrganizationDraft)
  const [weightSelection, setWeightSelection] = useState<WeightSelection>()
  const [queryDraft, setQueryDraft] = useState<QueryDraft>(defaultQueryDraft)
  const [understanding, setUnderstanding] = useState<UnderstandingSnapshot | null>(null)
  const [understandingKey, setUnderstandingKey] = useState('')
  const requestDraftKey = JSON.stringify({ query, queryDraft, organizationDraft, weightSelection, useInternalDocs,
    ragGroup, outputLength, enabledSkillIds, disabledSkillIds, selectedChannels })
  const requestKeyRef = useRef(requestDraftKey)
  requestKeyRef.current = requestDraftKey
  const inputRef = useRef<HTMLInputElement>(null)
  const handledTerminal=useRef<SSEvent|null>(null)
  const handledGap=useRef<SSEvent|null>(null)

  // SSE for real-time updates
  const { events, status: sseStatus, error: sseError, clearEvents } = useSSE(activeSessionId, streamRunKey)

  const { data: skillsData } = useQuery<{ items: SkillItem[] }>({
    queryKey: ['skills'],
    queryFn: async () => {
      const res = await fetch('/api/v1/skills')
      if (!res.ok) throw new Error('Failed to fetch skills')
      return res.json()
    },
  })

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  // Fetch research result
  const { data: result, refetch: refetchResult } = useQuery<ResearchResult>({
    queryKey: ['research', activeSessionId],
    queryFn: async () => {
      const res = await fetch(`/api/v1/research/${activeSessionId}`)
      if (!res.ok) throw new Error('Failed to fetch result')
      return res.json()
    },
    enabled: !!activeSessionId,
    refetchInterval: query => ['pending', 'running'].includes(query.state.data?.status || 'running') ? 3000 : false,
  })

  const resumeAnalysis = useMutation({
    mutationFn: async () => {
      const response=await fetch(`/api/v1/research/${activeSessionId}/analysis/resume`,{method:'POST'})
      const data=await response.json()
      if (!response.ok) {
        const messages:Record<string,string>={
          analysis_original_allowance_exhausted:'原任务的额度或期限已用完，无法继续本次分析。',
          analysis_sources_changed:'研究资料的访问权限已变化，请调整资料后发起新研究。',
          analysis_inputs_changed:'研究输入已变化，已保存的分析步骤不能继续复用。',
          analysis_phase_attempt_limit:'当前问题已达到两次尝试上限。',
          analysis_checkpoint_changed:'任务状态已变化，请刷新后查看。',
          analysis_checkpoint_not_recoverable:'当前任务没有可继续的分析检查点。',
          analysis_original_deadline_unavailable:'原任务的期限记录不完整，无法恢复。',
        }
        throw new Error(messages[String(data.detail)] || '暂时无法继续分析，请稍后重试。')
      }
      return data as {execution_id:string}
    },
    onSuccess: async data => {
      clearEvents()
      setStreamRunKey(data.execution_id)
      const refreshed=await refetchResult()
      const status=refreshed.data?.status || 'running'
      setSessionStatus(status)
      setIsStreaming(['pending','running'].includes(status))
    },
  })

  function buildRequest(q: string) {
    const drawingIds = queryDraft.drawingMode==='builtin'?[]:[
      ...(queryDraft.drawingMode==='manual_skill'?queryDraft.drawingSkillIds:[]),
      ...Object.values(queryDraft.chartSkillIds||{}).filter(Boolean)]
    if (drawingIds.some(id => disabledSkillIds.includes(id))) throw new Error('绘图 Skill 已在会话中禁用，请先解除禁用或重新选择。')
    return { query: q, use_internal_docs: useInternalDocs,
      rag_group: useInternalDocs ? ragGroup.trim() || null : null, output_length: outputLength,
      enabled_skill_ids: [...new Set([...enabledSkillIds, ...drawingIds])], disabled_skill_ids: disabledSkillIds,
      channels: selectedChannels, organization_research: organizationRequest(organizationDraft, q, weightSelection),
      ...queryDraftRequest(queryDraft, organizationDraft.enabled) }
  }

  async function previewRequest(body: ReturnType<typeof buildRequest>, key: string): Promise<UnderstandingSnapshot> {
    const response = await fetch('/api/v1/research/understanding', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    })
    const data = await response.json()
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '查询配置无效，请检查对象、日期和页面设置。')
    if (requestKeyRef.current !== key) throw new Error('预览期间配置已变化，请重新预览。')
    setUnderstanding(data)
    setUnderstandingKey(key)
    return data
  }

  const previewMutation = useMutation({
    mutationFn: async () => previewRequest(buildRequest(query.trim()), requestKeyRef.current),
  })

  // Always recompute against the authenticated owner's current configuration.
  const startMutation = useMutation({
    mutationFn: async (q: string) => {
      const key = requestKeyRef.current
      const body = buildRequest(q)
      const preview = await previewRequest(body, key)
      if (!preview.ready) throw new Error('请先处理查询解释中的待澄清项，再开始研究。')
      const res = await fetch('/api/v1/research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...body, query_preview_id: preview.interpretation_id }),
      })
      if (!res.ok) {
        const problem = await res.json().catch(() => ({}))
        if (problem.detail?.understanding) {
          setUnderstanding(problem.detail.understanding)
          setUnderstandingKey(key)
        }
        if (problem.detail?.category === 'query_preview_changed') throw new Error('研究配置或上下文已更新，已显示新解释，请重新提交。')
        if (problem.detail?.category === 'query_clarification_required') throw new Error('请先处理查询解释中的待澄清项。')
        throw new Error(typeof problem.detail === 'string' ? problem.detail : '研究配置未通过校验，请检查对象、学科和日期。')
      }
      return res.json()
    },
    onSuccess: (data) => {
      const url = new URL(window.location.href)
      url.searchParams.set('session', data.session_id)
      window.history.replaceState(null, '', url)
      setActiveSessionId(data.session_id)
      setIsStreaming(data.status === 'running')
      setSessionStatus(data.status)
      clearEvents()
    },
  })

  // Detect when streaming ends
  const previousWeightSelection = useRef('')
  const applyWeightSelection = useCallback((selection: WeightSelection) => {
    const signature = JSON.stringify(selection)
    const changed = signature !== previousWeightSelection.current
    previousWeightSelection.current = signature
    setWeightSelection(selection)
    // A corrected draft must not keep displaying a previous submission error.
    if (changed && !selection.error && startMutation.error && !startMutation.isPending) startMutation.reset()
  }, [startMutation.error, startMutation.isPending, startMutation.reset])

  useEffect(() => {
    const doneEvent = events.find((e: SSEvent) => e.type === 'done' || e.type === 'workflow_error')
    if (doneEvent&&handledTerminal.current!==doneEvent) {
      handledTerminal.current=doneEvent
      setIsStreaming(false)
      setSessionStatus(doneEvent.type === 'done' ? String(doneEvent.data.status||'completed') : 'failed')
      void refetchResult()
    }
  }, [events,refetchResult])

  useEffect(()=>{
    const gap=[...events].reverse().find(event=>event.data.delivery_gap===true)
    if(gap&&handledGap.current!==gap){handledGap.current=gap;void refetchResult()}
  },[events,refetchResult])

  useEffect(() => {
    if (sseStatus === 'error') {
      setIsStreaming(false)
    }
  }, [sseStatus])

  useEffect(() => {
    if (result?.status) {
      if (!query) setQuery(result.query)
      setSessionStatus(result.status)
      if (['completed', 'failed', 'paused', 'canceled', 'pending_confirmation'].includes(result.status)) {
        setIsStreaming(false)
      }
    }
  }, [result, query])

  // Build report from streaming chunks
  const streamedReport = events
    .filter((e: SSEvent) => e.type === 'report_chunk')
    .map((e: SSEvent) => String(e.data.chunk || ''))
    .join('')

  // Collect stats from events
  const historicalEvents: SSEvent[] = (result?.agent_trace || []).flatMap(event => {
    if (typeof event !== 'object' || event === null || !('event_type' in event)) return []
    const data = event as Record<string, unknown>
    const metadata = typeof data.metadata === 'object' && data.metadata !== null ? data.metadata as Record<string, unknown> : {}
    return [{ type: String(data.event_type), data: { ...data, ...metadata } }]
  })
  const traceEvents = events.some(event => event.type !== 'connected') ? events : historicalEvents
  const progressEvent=[...events].reverse().find(event=>event.type==='state_update' && event.data.analysis_progress)
  const analysisProgress=(progressEvent?.data.analysis_progress as ResearchResult['analysis_progress']) || result?.analysis_progress
  const analysisLabels:Record<string,string>={extract_publications:'整理成果与署名',landscape:'研究布局',
    evolution:'研究演进',relationships:'组织与学者关系',deep_dive:'成果深读',validation:'来源核对',actions:'研究与合作行动'}
  const progressParts=analysisProgress?.phase?.split(':') || []
  const analysisPhase=analysisLabels[progressParts[0]==='question'?progressParts[1]:progressParts[0]] || '综合分析'
  const drawingReason=result?.organization_result?.chart_rendering?.reason
  const drawingMessages:Record<string,string>={
    drawing_original_budget_insufficient:'原任务剩余额度不足以完成绘图。',
    drawing_original_deadline_exhausted:'原任务的绘图期限已到。',
    drawing_renderer_failed:'文件绘图未完成，请查看研究记录中的渲染原因和依赖配置。',
    no_source_bound_chart_data:'所选页面没有可用于绘图的来源数据，请调整页面或补充资料。',
    drawing_plan_incomplete:'绘图计划未完整返回，当前报告与数据已保留。',
    model_routing_configuration_changed:'模型配置已变化，本任务保留原模型绑定。',
    model_context_capability_exceeded:'所选绘图模型的上下文容量不足。',
    no_eligible_model_route:'没有满足绘图阶段及资料许可的配置模型。',
  }
  const analysisBatch=progressParts[0]==='extract_publications'?progressParts[1]:
    progressParts[2]==='conditions'?progressParts[3]:progressParts[2]
  const agentEvents = traceEvents.filter((e: SSEvent) =>
    ['agent_start', 'agent_complete', 'agent_end'].includes(e.type)
  )
  const toolEvents = traceEvents.filter((e: SSEvent) =>
    ['tool_start', 'tool_call', 'tool_complete', 'tool_result', 'tool_error'].includes(e.type)
  )

  // Latest DAG node status
  const dagNodeEvents = traceEvents.filter((e: SSEvent) => e.type === 'agent_start')
  const currentNode = dagNodeEvents.length > 0
    ? (dagNodeEvents[dagNodeEvents.length - 1].data as { agent?: string })?.agent || ''
    : ''

  const handleStart = useCallback(() => {
    if (query.trim().length < 5 || startMutation.isPending || previewMutation.isPending) return
    startMutation.mutate(query.trim())
  }, [query, startMutation, previewMutation.isPending])

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleStart()
    }
    if (e.key === 'Escape') {
      onBack?.()
    }
  }, [handleStart, onBack])

  const handleNewResearch = useCallback(() => {
    const url = new URL(window.location.href)
    url.searchParams.delete('session')
    window.history.replaceState(null, '', url)
    setActiveSessionId(null)
    setQuery('')
    setQueryDraft(defaultQueryDraft)
    setUnderstanding(null)
    setUnderstandingKey('')
    setRagGroup('')
    setSessionStatus(null)
    clearEvents()
    inputRef.current?.focus()
  }, [clearEvents])

  const handleRestartedResearch = useCallback((sessionId: string) => {
    const url = new URL(window.location.href)
    url.searchParams.set('session',sessionId)
    window.history.replaceState(null,'',url)
    setActiveSessionId(sessionId)
    setIsStreaming(true)
    setSessionStatus('running')
    clearEvents()
  }, [clearEvents])

  const displayReport = result?.status === 'completed' ? result.report : streamedReport || result?.report || ''
  const normalizedCitations = Array.isArray(result?.citations) ? result.citations : []
  const effectiveSkillIds = result?.skill_context?.effective_skill_ids || []
  const autoMatchedSkillIds = result?.skill_context?.auto_matched_skill_ids || []
  const effectiveTools = result?.skill_context?.effective_tool_allowlist || []
  const matchedSkills = result?.skill_context?.match_results || []
  const manuallyEnabledSkillIds = result?.skill_context?.manually_enabled_skill_ids || []
  const manuallyDisabledSkillIds = result?.skill_context?.manually_disabled_skill_ids || []
  const showConfirmationState = sessionStatus === 'pending_confirmation'
  const hasVisibleEvents = events.some((event: SSEvent) => event.type !== 'connected')
  const isConnectingStream = isStreaming && (sseStatus === 'connecting' || sseStatus === 'connected') && !hasVisibleEvents
  const canRefetchResult = Boolean(activeSessionId)
  const workflowErrorEvent = [...events].reverse().find((event: SSEvent) => event.type === 'workflow_error')
  const isFailed = sessionStatus === 'failed'
  const isCanceled=sessionStatus==='canceled'
  const stoppedLabel=isCanceled?'已取消':sessionStatus==='paused'?'已暂停':sessionStatus==='pending'?'待执行':isFailed?'失败':sessionStatus==='completed'?'已完成':'等待状态'
  const emptyReportTitle = isConnectingStream
    ? '正在建立研究流连接...'
    : isCanceled?'研究已取消':isFailed
      ? '研究执行失败'
      : sseError
      ? '实时流已中断'
      : '报告暂未生成'
  const emptyReportDescription = isConnectingStream
    ? '任务已提交，正在等待首个 Agent 事件和报告片段。'
    : isCanceled?'已保留取得的资料和用量。本次任务未生成完成报告。':isFailed
      ? String(workflowErrorEvent?.data.error || workflowErrorEvent?.data.message || '任务执行过程中发生错误。')
      : sseError
      ? '实时事件连接失败，但仍可继续读取已落库的研究结果。'
      : '当前任务尚未返回可展示的报告内容。'

  const [reportElement, setReportElement] = useState<HTMLDivElement | null>(null)

  // ======= RENDER =======

  // Full-screen research mode
  if (!activeSessionId) {
    return (
      <div className="min-h-[calc(100vh-3.5rem)] flex flex-col items-center justify-center px-6">
        {/* Back button */}
        {onBack && (
          <button
            onClick={onBack}
            className="absolute top-20 left-6 btn-ghost"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M10 12L6 8L10 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            返回
          </button>
        )}

        {/* Hero text */}
        <div className="text-center mb-12 animate-fade-up">
          <h2 className="text-4xl md:text-5xl font-bold text-xmgray-900 tracking-tight">
            开始你的研究
          </h2>
          <p className="mt-3 text-base text-xmgray-400">
            输入研究主题，AI 将自动完成全流程研究
          </p>
        </div>

        {/* Search input - Xiaomi style large */}
        <div className="w-full max-w-2xl animate-fade-up" style={{ animationDelay: '0.1s' }}>
          <div className="relative">
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="例如：分析 2025 年中国新能源汽车市场格局"
              className="input-xm pr-36 text-base"
              autoFocus
            />
            <button
              aria-label="开始研究"
              onClick={handleStart}
              disabled={isStreaming || query.trim().length < 5 || startMutation.isPending || previewMutation.isPending}
              className="absolute right-2 top-1/2 -translate-y-1/2 btn-primary py-2.5 px-5"
            >
              {startMutation.isPending ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/40 border-t-white rounded-full animate-spin" />
                  启动中
                </>
              ) : (
                <>
                  研究
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path d="M2 7H12M12 7L8 3M12 7L8 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </>
              )}
            </button>
          </div>
          <p className="mt-3 text-xs text-xmgray-400 text-center">
            默认联网研究，可按需补充内部资料
          </p>
          {startMutation.error && <p role="alert" className="mt-3 rounded-xl bg-red-50 p-3 text-sm text-red-700">{startMutation.error.message}</p>}
          {previewMutation.error && <p role="alert" className="mt-3 rounded-xl bg-red-50 p-3 text-sm text-red-700">{previewMutation.error.message}</p>}
          {understanding && understandingKey !== requestDraftKey && <p className="mt-2 text-xs text-amber-800">配置已变化，下方解释来自上次预览；开始研究前会重新解释。</p>}
          <QueryUnderstandingPanel value={queryDraft} onChange={setQueryDraft} organizationEnabled={organizationDraft.enabled}
            skills={skillsData?.items.filter(skill => skill.enabled) || []} preview={understanding}
            onPreview={() => { if (query.trim().length >= 5) previewMutation.mutate() }}
            canPreview={query.trim().length >= 5}
            busy={startMutation.isPending || previewMutation.isPending} />
          <OrganizationResearchPanel value={organizationDraft} onChange={setOrganizationDraft} />
          {organizationDraft.enabled && <OrganizationWeightsPanel disciplines={organizationDraft.disciplines} onChange={applyWeightSelection} />}
          <div className="mt-4 rounded-2xl border border-xmgray-100 bg-white/80 p-4 text-left shadow-sm">
            <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-center">
              <label className="block">
                <span className="text-xs font-medium text-xmgray-500">内部资料分组（可选）</span>
                <input
                  type="text"
                  value={ragGroup}
                  disabled={!useInternalDocs}
                  onChange={e => setRagGroup(e.target.value)}
                  placeholder="例如：company_docs / project_a"
                  className="mt-1 w-full rounded-xl border border-xmgray-200 px-3 py-2 text-sm text-xmgray-700 outline-none focus:border-xm-400 disabled:bg-xmgray-50 disabled:text-xmgray-400"
                />
              </label>
              <label className="flex items-center gap-2 rounded-xl bg-xmgray-50 px-3 py-2 text-xs text-xmgray-600">
                <input
                  type="checkbox"
                  checked={useInternalDocs}
                  onChange={e => setUseInternalDocs(e.target.checked)}
                  className="accent-orange-500"
                />
                补充检索内部资料
              </label>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              {[
                { value: 'short', label: '短文' },
                { value: 'medium', label: '中篇' },
                { value: 'long', label: '长篇' },
              ].map(option => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setOutputLength(option.value as 'short' | 'medium' | 'long')}
                  className={`rounded-full px-4 py-2 text-sm transition-colors ${
                    outputLength === option.value
                      ? 'bg-xm-500 text-white'
                      : 'bg-xmgray-50 text-xmgray-600 hover:bg-xmgray-100'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <div className="mt-4 rounded-2xl border border-xmgray-100 bg-xmgray-50/60 p-4">
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs font-medium text-xmgray-600">Session Skills</span>
                <span className="text-[11px] text-xmgray-400">自动匹配 + 手动覆盖</span>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                {skillsData?.items.filter(skill => skill.enabled).map(skill => {
                  const manuallyEnabled = enabledSkillIds.includes(skill.id)
                  const manuallyDisabled = disabledSkillIds.includes(skill.id)
                  const stateLabel = manuallyDisabled ? '已禁用' : manuallyEnabled ? '已启用' : '自动'
                  return (
                    <div key={skill.id} className="rounded-xl border border-xmgray-200 bg-white px-3 py-2">
                      <div className="text-sm text-xmgray-700">{skill.name}</div>
                      <div className="mt-2 flex gap-2">
                        <button
                          type="button"
                          className={`tag text-[11px] ${manuallyEnabled ? 'bg-xm-50 text-xm-700 border-xm-100' : ''}`}
                          onClick={() => {
                            setDisabledSkillIds(prev => prev.filter(id => id !== skill.id))
                            setEnabledSkillIds(prev => prev.includes(skill.id) ? prev.filter(id => id !== skill.id) : [...prev, skill.id])
                          }}
                        >
                          启用
                        </button>
                        <button
                          type="button"
                          className={`tag text-[11px] ${manuallyDisabled ? 'bg-red-50 text-red-600 border-red-100' : ''}`}
                          onClick={() => {
                            setEnabledSkillIds(prev => prev.filter(id => id !== skill.id))
                            setDisabledSkillIds(prev => prev.includes(skill.id) ? prev.filter(id => id !== skill.id) : [...prev, skill.id])
                          }}
                        >
                          禁用
                        </button>
                        <span className="text-[11px] text-xmgray-400 self-center">{stateLabel}</span>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
            <p className="mt-2 text-[11px] text-xmgray-400">
              启用后检索你维护的内部资料，并结合联网证据分析；留空分组会检索你的全部资料。
            </p>
            <ChannelPanel selected={selectedChannels} onChange={setSelectedChannels} />
          </div>
        </div>

        {/* Example queries */}
        <div className="mt-10 flex flex-wrap justify-center gap-2 animate-fade-in" style={{ animationDelay: '0.3s' }}>
          {[
            '2025年AI Agent市场分析',
            '量子计算最新进展',
            '中国新能源汽车出口数据',
          ].map(q => (
            <button
              key={q}
              onClick={() => setQuery(q)}
              className="tag hover:bg-xmgray-100 cursor-pointer transition-colors"
            >
              {q}
            </button>
          ))}
        </div>
      </div>
    )
  }

  // ======= ACTIVE RESEARCH MODE =======

  return (
      <div className="max-w-7xl mx-auto px-6 py-8">
      {showConfirmationState && (
        <div className="mb-6 rounded-2xl border border-amber-100 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          当前任务需要确认，尚未进入执行。
        </div>
      )}
      {sseError && (
        <div className="mb-6 rounded-2xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-red-700">
          SSE 连接异常：{sseError}
          {canRefetchResult && (
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="ml-3 text-red-800 underline underline-offset-2"
            >
              刷新页面
            </button>
          )}
        </div>
      )}
      {isConnectingStream && (
        <div className="mb-6 rounded-2xl border border-xm-100 bg-xm-50 px-4 py-3 text-sm text-xm-700">
          研究任务已启动，正在等待实时事件流连接完成。
        </div>
      )}
      {/* Top bar: query + stats */}
      <div className="flex items-center justify-between mb-6 gap-4">
        <div className="flex items-center gap-4 min-w-0">
          {/* Back / New */}
          <button onClick={handleNewResearch} className="btn-ghost shrink-0">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M10 12L6 8L10 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            新研究
          </button>

          {/* Current query */}
          <div className="min-w-0">
            <p className="text-sm text-xmgray-400 truncate max-w-xl">{result?.query || query}</p>
          </div>
        </div>

        {/* Stats */}
        <div className="flex items-center gap-6 shrink-0">
          {/* Agent stats */}
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5">
              <div className={`status-dot ${isStreaming ? 'streaming' : 'online'}`} />
              <span className="text-xs text-xmgray-500">
                {isStreaming ? currentNode || '执行中' : stoppedLabel}
              </span>
            </div>
            <div className="h-4 w-px bg-xmgray-200" />
            <span className="text-xs text-xmgray-400">{agentEvents.length} 步</span>
            <div className="h-4 w-px bg-xmgray-200" />
            <span className="text-xs text-xmgray-400">{toolEvents.length} 工具</span>
          </div>
        </div>
      </div>

      {/* Main content grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Traces panel */}
        <div className="lg:col-span-4 space-y-4">
          {result?.execution_plan?.nodes?.length ? <section className="card p-5" aria-label="本次研究计划">
            <h3 className="text-sm font-medium text-xmgray-700">本次研究计划</h3>
            <ol className="mt-3 max-h-72 space-y-3 overflow-y-auto text-xs text-xmgray-600">{result.execution_plan.nodes.map(node => <li key={node.node_id}>
              <span className="font-medium">{({ search: '搜索取证', browser: '网页取证', analyst: '综合分析', report: '报告', reflection: '核验', rag: '内部资料', mcp: '扩展工具' } as Record<string, string>)[node.node_type] || node.node_type}</span>
              <span className="ml-2">{isCanceled&&['pending','running'].includes(node.status)?'任务已取消':({ done: '已完成', failed: '失败', skipped: '已跳过', pending: '待执行', running: '执行中' } as Record<string, string>)[node.status] || node.status}</span>
              <p className="mt-1 break-words">{node.query}</p>
            </li>)}</ol>
          </section> : null}
          {/* Agent Trace - Xiaomi card */}
          <div className="card p-0 overflow-hidden">
            <div className="px-5 py-4 flex items-center justify-between border-b border-xmgray-100">
              <div className="flex items-center gap-2">
                <div className="w-5 h-5 rounded-md bg-xm-500/10 flex items-center justify-center">
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                    <path d="M6 1.5L10 3.5V6.5L6 8.5L2 6.5V3.5L6 1.5Z" stroke="#ff8c00" strokeWidth="1.2" strokeLinejoin="round"/>
                  </svg>
                </div>
                <h3 className="text-sm font-medium text-xmgray-700">Agent 轨迹</h3>
              </div>
              <span className="tag text-[11px]">
                {isStreaming
                  ? <><span className="status-dot streaming mr-1" />运行中</>
                  : stoppedLabel}
              </span>
            </div>
            <div className="p-4 h-[420px] overflow-y-auto">
              <AgentTrace events={traceEvents} />
            </div>
          </div>

          {/* Tool Trace */}
          <div className="card p-0 overflow-hidden">
            <div className="px-5 py-4 flex items-center justify-between border-b border-xmgray-100">
              <div className="flex items-center gap-2">
                <div className="w-5 h-5 rounded-md bg-emerald-500/10 flex items-center justify-center">
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                    <path d="M2 6H10M10 6L7 3M10 6L7 9" stroke="#10b981" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </div>
                <h3 className="text-sm font-medium text-xmgray-700">工具调用</h3>
              </div>
              <span className="text-xs text-xmgray-400">{toolEvents.length} 次</span>
            </div>
            <div className="p-4 h-44 overflow-y-auto">
              <ToolTrace events={traceEvents} />
            </div>
          </div>
        </div>

        {/* Right: Report panel */}
        <div className="lg:col-span-8 space-y-4">
          {result && <UnderstandingSummary value={result.query_understanding} />}
          {result&&result.execution_id!==undefined&&<ResearchCancellation key={`cancel-${result.session_id}-${result.execution_id}`}
            sessionId={result.session_id} executionId={result.execution_id} status={result.status}
            inflight={result.budget_state?.inflight_model_requests} onRefresh={async()=>{const refreshed=await refetchResult();if(refreshed.error)throw refreshed.error}}/>}
          {result && <ResearchPlanSummary status={result.status} plan={result.plan_manifest} dag={result.execution_plan} history={result.plan_history} control={result.iteration_control} />}
          {result&&['completed','paused','failed','canceled'].includes(result.status)&&<ResearchConfigurationEditor key={`configure-${result.session_id}`}
            query={typeof result.restart_parameters?.query==='string'?result.restart_parameters.query:result.query} parameters={result.restart_parameters} onStarted={handleRestartedResearch}/>}
          {result?.organization_research && <section className="card p-5 text-sm text-xmgray-700" aria-label="本次组织研究范围">
            <h3 className="font-medium">本次组织研究范围</h3>
            <p className="mt-2">{result.organization_research.scope.entities.map(entity => entity.name).join('、') || '范围内候选发现'} · {result.organization_research.scope.disciplines.join('、')}</p>
            <p className="mt-1 text-xs text-xmgray-500">{result.organization_research.scope.start_date} 至 {result.organization_research.scope.end_date}</p>
            {typeof result.organization_result?.evidence_count==='number' && <p className="mt-2 text-xs text-xmgray-500">取得 {result.organization_result.evidence_count} 条有来源证据，按证据 ID 去重；这是证据数量，成果归属与论文统计仍需核验。</p>}
          </section>}
          {result?.status === 'completed' && result.organization_research && <ResearchMatchingPanel key={result.session_id}
            sessionId={result.session_id} query={typeof result.restart_parameters?.query==='string'?result.restart_parameters.query:result.query} scope={result.organization_research.scope}
            disciplines={result.organization_research.scope.disciplines} restartParameters={result.restart_parameters}
            purpose={result.organization_research.purpose} modules={result.organization_research.modules}
            corpus={result.organization_research.corpus}
            taxonomy={result.organization_research.taxonomy?.request}
            actionRequirements={result.organization_research.action_requirements}
            onStarted={handleRestartedResearch} />}
          {/* Report */}
          {result?.status === 'completed' && result.organization_research && <ClassificationPanel key={`classification-${result.session_id}`} sessionId={result.session_id} />}
          {activeSessionId && <IngestionPanel key={`ingestion-${activeSessionId}`} sessionId={activeSessionId} />}
          {result&&['completed','paused','failed','canceled'].includes(result.status)&&<ResearchQuality key={`quality-${result.session_id}`} sessionId={result.session_id}/>}
          <div className="card p-0 overflow-hidden">
            <div className="px-5 py-4 flex items-center justify-between border-b border-xmgray-100">
              <div className="flex items-center gap-2">
                <div className="w-5 h-5 rounded-md bg-xmgray-100 flex items-center justify-center">
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
                    <rect x="2" y="1.5" width="8" height="9" rx="1.5" stroke="#9e9e9e" strokeWidth="1.2"/>
                    <path d="M4 4H8M4 6H8M4 8H6" stroke="#9e9e9e" strokeWidth="1" strokeLinecap="round"/>
                  </svg>
                </div>
                <h3 className="text-sm font-medium text-xmgray-700">研究报告</h3>
              </div>
              <div className="flex items-center gap-3">
                {result?.status === 'completed' && <ReportDownloads result={result} reportElement={reportElement} />}
                {isStreaming && (
                  <span className="tag-orange text-[11px]">
                    <span className="status-dot streaming mr-1" />流式生成中
                  </span>
                )}
                {normalizedCitations.length > 0 && (
                  <span className="tag text-[11px]">{normalizedCitations.length} 条引用</span>
                )}
                {effectiveSkillIds.length > 0 && (
                  <span className="tag text-[11px]">{effectiveSkillIds.length} 个 skill 生效</span>
                )}
              </div>
            </div>
            <div className="p-6 min-h-[500px] max-h-[680px] overflow-y-auto">
              {activeSessionId&&<ReportHistory key={activeSessionId} sessionId={activeSessionId}/>}
              {analysisProgress && <section data-app-only aria-label="研究分析进度" className="mb-4 rounded-lg border border-xmgray-200 p-3 text-sm">
                <p>{isCanceled?'研究已取消，保留最后分析进度':analysisProgress.status==='completed'?'分阶段分析已完成':analysisProgress.status==='paused'?'分析已暂停':`当前分析：${analysisPhase}${progressParts[2]==='conditions'?' · 实验条件补读':''}${analysisBatch?` · 第${analysisBatch}组`:''}`}</p>
                <p className="text-xs text-xmgray-500">已保留 {analysisProgress.completed_steps} 个分析步骤。阶段结果和用量随研究保存。</p>
                {result?.analysis_recovery_available && <button type="button" className="mt-2 text-xmorange"
                  disabled={resumeAnalysis.isPending || isStreaming} onClick={()=>resumeAnalysis.mutate()}>
                  {resumeAnalysis.isPending?'正在继续…':'继续本次分析'}</button>}
                {resumeAnalysis.error && <p role="alert" className="mt-2 text-red-600">{resumeAnalysis.error.message}</p>}
              </section>}
              {(effectiveSkillIds.length > 0 || effectiveTools.length > 0) && (
                <div className="mb-5 rounded-2xl border border-xmgray-100 bg-xmgray-50/70 p-4">
                  <div className="text-sm font-medium text-xmgray-700">当前 Session Skill 上下文</div>
                  {effectiveSkillIds.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {effectiveSkillIds.map(skillId => {
                        const skill = skillsData?.items.find(item => item.id === skillId)
                        const autoMatched = autoMatchedSkillIds.includes(skillId)
                        return (
                          <span key={skillId} className="tag text-[11px]">
                            {skill?.name || skillId}
                            {autoMatched ? ' · auto' : ' · manual'}
                          </span>
                        )
                      })}
                    </div>
                  )}
                  {effectiveTools.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {effectiveTools.map(tool => (
                        <span key={tool} className="tag-orange text-[11px]">{tool}</span>
                      ))}
                    </div>
                  )}
                  {matchedSkills.length > 0 && (
                    <div className="mt-4 space-y-2">
                      {matchedSkills.map(match => {
                        const skill = skillsData?.items.find(item => item.id === match.skill_id)
                        return (
                          <div key={match.skill_id} className="rounded-xl border border-xmgray-100 bg-white px-3 py-3">
                            <div className="flex items-center justify-between gap-3">
                              <div>
                                <div className="text-sm font-medium text-xmgray-700">{skill?.name || match.name}</div>
                                <div className="mt-1 text-[11px] text-xmgray-400">
                                  {match.reason} · priority {match.priority}
                                </div>
                              </div>
                              <span className="tag text-[11px]">auto match</span>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  )}
                  {(manuallyEnabledSkillIds.length > 0 || manuallyDisabledSkillIds.length > 0) && (
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      <div className="rounded-xl border border-xmgray-100 bg-white px-3 py-3">
                        <div className="text-xs font-medium text-xmgray-600">手动启用</div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {manuallyEnabledSkillIds.length > 0 ? manuallyEnabledSkillIds.map(skillId => {
                            const skill = skillsData?.items.find(item => item.id === skillId)
                            return <span key={skillId} className="tag text-[11px]">{skill?.name || skillId}</span>
                          }) : <span className="text-[11px] text-xmgray-400">无</span>}
                        </div>
                      </div>
                      <div className="rounded-xl border border-xmgray-100 bg-white px-3 py-3">
                        <div className="text-xs font-medium text-xmgray-600">手动禁用</div>
                        <div className="mt-2 flex flex-wrap gap-2">
                          {manuallyDisabledSkillIds.length > 0 ? manuallyDisabledSkillIds.map(skillId => {
                            const skill = skillsData?.items.find(item => item.id === skillId)
                            return <span key={skillId} className="tag text-[11px]">{skill?.name || skillId}</span>
                          }) : <span className="text-[11px] text-xmgray-400">无</span>}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
              {result?.status==='paused' && drawingReason && <p data-app-only role="status"
                className="mb-3 rounded-lg bg-xmgray-50 p-3 text-sm text-xmgray-600">
                {drawingMessages[drawingReason] || '绘图尚未满足交付要求，当前稿和数据已保留。'}
                <span className="block text-xs">研究记录：{drawingReason}</span>
              </p>}
              {result?.status==='paused' && result?.report_audit?.needs_review && <p data-app-only
                role="status" className="mb-3 rounded-lg bg-xmgray-50 p-3 text-sm text-xmgray-600">
                当前稿已保留。{result.report_audit.audit_incomplete?'来源核对尚未完成。':'部分陈述需要补证或调整。'}
                可在下方“研究记录”查看具体内容。
              </p>}
              <div ref={setReportElement}><ReportPreview
                report={displayReport ?? ''}
                citations={normalizedCitations}
                sessionId={activeSessionId}
                streaming={isStreaming}
                emptyTitle={emptyReportTitle}
                emptyDescription={emptyReportDescription}
                reportSummary={result?.organization_result?.report_summary}
                deliveryView={result?.delivery_view}
                reportEditorial={result?.report_editorial}
                budgetState={result?.budget_state}
                reportAudit={result?.report_audit}
                contextEvidence={{analyst:result?.organization_result?.analyst_context,report:result?.organization_result?.report_context}}
              /></div>
            </div>
          </div>

          {/* Citations panel */}
          {normalizedCitations.length > 0 && (
            <div className="card p-0 overflow-hidden">
              <div className="px-5 py-4 border-b border-xmgray-100">
                <h3 className="text-sm font-medium text-xmgray-700">
                  引用来源
                </h3>
              </div>
              <div className="p-5 max-h-52 overflow-y-auto space-y-2">
                {normalizedCitations.map((c, i) => (
                  <a
                    key={i}
                    href={c.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-start gap-3 p-2.5 rounded-xl hover:bg-xmgray-50 transition-colors group"
                  >
                    <span className="shrink-0 w-5 h-5 rounded bg-xmgray-100 text-[10px] font-medium text-xmgray-500 flex items-center justify-center mt-0.5 group-hover:bg-xm-100 group-hover:text-xm-700 transition-colors">
                      {i + 1}
                    </span>
                    <div className="min-w-0">
                      <p className="text-sm text-xmgray-700 group-hover:text-xm-700 transition-colors truncate">
                        {c.source_title || c.source_url}
                      </p>
                      <p className="text-xs text-xmgray-400 truncate mt-0.5">{c.source_url}</p>
                    </div>
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className="shrink-0 mt-1 text-xmgray-300 group-hover:text-xmgray-400 transition-colors">
                      <path d="M5 2H2V10H10V7" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default ResearchDashboard
