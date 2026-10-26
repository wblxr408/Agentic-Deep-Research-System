import { useState, useCallback, useEffect, useRef } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useSSE } from '../hooks/useSSE'
import type { SSEvent } from '../hooks/useSSE'
import ResearchFlow, { mergeResearchEvents } from './ResearchFlow'
import ExecutionFeed from './ExecutionFeed'
import ResearchRunControls from './ResearchRunControls'
import type {RunControlState} from './ResearchRunControls'
import ResearchComposer from './ResearchComposer'
import {setupRequest} from './researchSetup'
import type {ResearchSetup} from './researchSetup'
import { Icon, StatusPill } from './Interface'
import ToolTrace from './ToolTrace'
import type { PersistedToolCall } from './ToolTrace'
import ReportPreview from './ReportPreview'
import ReportDownloads from './ReportDownloads'
import ReportHistory from './ReportHistory'
import ClassificationPanel from './ClassificationPanel'
import IngestionPanel from './IngestionPanel'
import type { OrganizationReportSnapshot } from './OrganizationReportSummary'
import { defaultOrganizationDraft } from './OrganizationResearchPanel'
import type { WeightSelection } from './OrganizationWeightsPanel'
import ResearchMatchingPanel from './ResearchMatchingPanel'
import { defaultQueryDraft, UnderstandingSummary } from './QueryUnderstandingPanel'
import type { QueryDraft, UnderstandingSnapshot } from './QueryUnderstandingPanel'
import ResearchPlanSummary from './ResearchPlanSummary'
import ResearchConfigurationEditor from './ResearchConfigurationEditor'
import ResearchQuality from './ResearchQuality'
import ResearchCancellation from './ResearchCancellation'
import type { PlanSummaryProps } from './ResearchPlanSummary'
import type { DeliveryView } from './ReportDeliveryView'

interface ResearchResult {
  pause_diagnosis?:RunControlState['pause_diagnosis']
  runtime_status?:string|null
  stop_reason?:string|null
  user_control?:{state?:string}|null
  execution_id?:string|null
  report_audit?: {needs_review?:boolean;audit_incomplete?:boolean;total_claims?:number;supported_claims?:number;
    revision_requests?:Array<{claim_id:string;text:string;reason:string;requested_action:string}>}|null
  analysis_recovery_available?: boolean
  report_recovery_available?: boolean
  analysis_progress?: {phase: string|null;status:string;completed_steps:number;stop_reason?:string|null;
    phases?:Array<{phase:string;status:string;summary:string;attempts:number}>;
    last_admission?:{prompt_bound?:number|null;requested_output_tokens?:number|null;available_tokens?:number|null;selected_sources?:number|null}|null}|null
  budget_state?: {used_total_tokens?:number;max_total_tokens?:number;cost_status?:string;token_usage_estimated?:boolean;hard_stop_reason?:string|null;model_stop_reason?:string|null;inflight_model_requests?:number} | null
  report_editorial?: { note?: string } | null
  delivery_view?: DeliveryView | null
  plan_manifest?: PlanSummaryProps['plan']
  plan_history?: PlanSummaryProps['history']
  iteration_control?: PlanSummaryProps['control']
  workflow_failure?: PlanSummaryProps['failure']
  operational_events?: PlanSummaryProps['operationalEvents']
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
  const inputRef = useRef<HTMLTextAreaElement>(null)
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
  const { data: result, error: resultError, refetch: refetchResult } = useQuery<ResearchResult>({
    queryKey: ['research', activeSessionId],
    queryFn: async () => {
      const res = await fetch(`/api/v1/research/${activeSessionId}`)
      if (!res.ok) throw new Error([401,403,404].includes(res.status)?'任务不存在或当前不可访问。':'任务记录读取失败，请重试。')
      return res.json()
    },
    enabled: !!activeSessionId,
    refetchInterval: query => ['pending', 'running'].includes(query.state.data?.status || 'running') ? 3000 : false,
  })

  const toolAudit = useQuery<PersistedToolCall[]>({
    queryKey: ['research-tool-calls', activeSessionId],
    queryFn: async () => {
      const response = await fetch(`/api/v1/research/${activeSessionId}/tool-calls`)
      if (!response.ok) throw new Error('暂时无法读取本次研究的调用记录。')
      return response.json()
    },
    enabled: !!activeSessionId,
    staleTime: 0,
    gcTime: 0,
    refetchInterval: ['pending', 'running'].includes(result?.status || 'running') ? 3000 : false,
  })

  const resumeSynthesis = useMutation({
    mutationFn: async (stage:'analysis'|'report') => {
      const response=await fetch(`/api/v1/research/${activeSessionId}/${stage}/resume`,{method:'POST'})
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
          report_original_allowance_exhausted:'原任务的额度或期限已用完，无法继续生成报告。',
          report_resume_attempt_limit:'本次报告已达到一次续作上限，当前资料和原稿已保留。',
          report_checkpoint_changed:'任务状态已变化，请刷新后查看。',
          report_checkpoint_not_recoverable:'当前任务没有可继续的报告检查点。',
        }
        throw new Error(messages[String(data.detail)] || '暂时无法继续研究，请稍后重试。')
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

  function currentSetup(q=query):ResearchSetup {
    return {query:q,queryDraft,organizationDraft,weights:weightSelection,outputLength,useInternal:useInternalDocs,group:ragGroup,channels:selectedChannels,enabled:enabledSkillIds,disabled:disabledSkillIds}
  }
  function buildRequest(q:string) { return setupRequest(currentSetup(q)) }

  async function previewRequest(body: ReturnType<typeof buildRequest>, key: string): Promise<UnderstandingSnapshot> {
    const response = await fetch('/api/v1/research/understanding', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    })
    const data = await response.json()
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '请检查对象、日期和报告选择。')
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
      if (!preview.ready) throw new Error('请按预览补全选择后开始研究。')
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
        if (problem.detail?.category === 'query_preview_changed') throw new Error('选择已变化，已更新计划，请再预览一次。')
        if (problem.detail?.category === 'query_clarification_required') throw new Error('请按计划补充需要的选择。')
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

  function applySetup(value:ResearchSetup) {
    if(JSON.stringify(value)!==JSON.stringify(currentSetup())){
      if(startMutation.error&&!startMutation.isPending)startMutation.reset()
      if(previewMutation.error&&!previewMutation.isPending)previewMutation.reset()
    }
    setQuery(value.query);setQueryDraft(value.queryDraft);setOrganizationDraft(value.organizationDraft)
    if(value.weights)applyWeightSelection(value.weights);else{previousWeightSelection.current='';setWeightSelection(undefined)}
    setOutputLength(value.outputLength);setUseInternalDocs(value.useInternal);setRagGroup(value.group)
    setSelectedChannels(value.channels);setEnabledSkillIds(value.enabled);setDisabledSkillIds(value.disabled)
  }

  useEffect(() => {
    const doneEvent = events.find((e: SSEvent) => e.type === 'done' || e.type === 'workflow_error')
    if (doneEvent&&handledTerminal.current!==doneEvent) {
      handledTerminal.current=doneEvent
      setIsStreaming(false)
      setSessionStatus(String(doneEvent.data.status||(doneEvent.type==='done'?'completed':'failed')))
      void refetchResult()
    }
  }, [events,refetchResult])

  useEffect(()=>{
    const gap=[...events].reverse().find(event=>event.data.delivery_gap===true)
    if(gap&&handledGap.current!==gap){handledGap.current=gap;void refetchResult()}
  },[events,refetchResult])

  const handledControl=useRef<SSEvent|null>(null)
  useEffect(()=>{
    const update=[...events].reverse().find(event=>event.type==='control_update'||
      (event.type==='state_update'&&(event.data.pause_diagnosis||event.data.recovery)))
    if(update&&handledControl.current!==update){
      handledControl.current=update
      if((update.data.recovery as {status?:string}|undefined)?.status==='running'&&
        !['completed','failed','canceled'].includes(result?.status||'')){
        setSessionStatus('running');setIsStreaming(true)
      }
      void refetchResult()
    }
  },[events,refetchResult,result?.status])

  useEffect(() => {
    if (result?.status && result.session_id === activeSessionId) {
      if (!query) setQuery(result.query)
      setSessionStatus(result.status)
      setIsStreaming(['pending', 'running'].includes(result.status))
    }
  }, [result, query, activeSessionId])

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
    const retainedTime = typeof data.timestamp === 'string' ? data.timestamp : undefined
    // Persisted trace timestamps use UTC without an offset; preserve their time on reopen.
    const timestamp = retainedTime && !/(?:Z|[+-]\d{2}:\d{2})$/i.test(retainedTime) ? `${retainedTime}Z` : retainedTime
    return [{ type: String(data.event_type), data: { ...data, ...metadata }, timestamp }]
  })
  const traceEvents = mergeResearchEvents(historicalEvents, events, result?.execution_id)
  const progressEvent=[...events].reverse().find(event=>event.type==='state_update' && event.data.analysis_progress)
  const liveAnalysisProgress=progressEvent?.data.analysis_progress as ResearchResult['analysis_progress']
  const analysisProgress=liveAnalysisProgress&&(!result||['pending','running'].includes(result.status))
    ? {...result?.analysis_progress,...liveAnalysisProgress}:result?.analysis_progress
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
  const planNodes = result?.execution_plan?.nodes
  const completedNodes = planNodes?.filter(node => node.status === 'done').length
  const toolCallCount = toolAudit.data?.length

  const handleStart = useCallback(() => {
    if (query.trim().length < 5 || startMutation.isPending || previewMutation.isPending) return
    startMutation.mutate(query.trim())
  }, [query, startMutation, previewMutation.isPending])

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      handleStart()
    }
    if (e.key === 'Escape') {
      onBack?.()
    }
  }, [handleStart, onBack])

  const handleNewResearch = useCallback(() => {
    startMutation.reset()
    previewMutation.reset()
    resumeSynthesis.reset()
    const url = new URL(window.location.href)
    url.searchParams.delete('session')
    window.history.replaceState(null, '', url)
    setActiveSessionId(null)
    setIsStreaming(false)
    setActivePanel('workflow')
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
    ? '正在连接执行记录。'
    : isCanceled?'资料与进度已保存。':isFailed
      ? String(workflowErrorEvent?.data.error || workflowErrorEvent?.data.message || '任务执行过程中发生错误。')
      : sseError
      ? '可刷新执行记录。'
      : '完成分析后生成报告。'

  const [reportElement, setReportElement] = useState<HTMLDivElement | null>(null)

  const [activePanel, setActivePanel] = useState('workflow')
  const configuration=useRef<HTMLDivElement>(null)
  const openRestartConfiguration=()=>{
    setActivePanel('records')
    requestAnimationFrame(()=>{
      const details=configuration.current?.querySelector('details')
      if(details){details.open=true;details.scrollIntoView({behavior:'smooth',block:'center'});details.querySelector('textarea')?.focus({preventScroll:true})}
    })
  }
  const selectedSession = useRef<string | null>(null)
  useEffect(() => {
    if (result && selectedSession.current !== result.session_id) {
      selectedSession.current = result.session_id
      setActivePanel(result.status === 'completed' ? 'report' : 'workflow')
    }
  }, [result])
  const busy = isStreaming || startMutation.isPending || previewMutation.isPending
  const stageLabels:Record<string,string>={planner:'规划研究',search:'搜索资料',browser:'读取来源',rag:'检索资料',analyst:analysisPhase,reflection:'核对来源',report:'生成报告',replan:'调整计划',dag_executor:'执行研究计划'}
  const stageEvent=[...traceEvents].reverse().find(event=>event.type==='agent_start')
  const currentStage=analysisProgress?.status==='running'?analysisPhase:stageLabels[String(stageEvent?.data.agent||'')]||'研究进行中'
  if(activeSessionId&&resultError&&!result)return <div className="research-workspace"><p role="alert" className="composer-error">{resultError.message}</p><div className="flex gap-3 mt-5"><button type="button" className="btn-secondary" onClick={()=>void refetchResult()}>重新读取</button><button type="button" className="btn-ghost" onClick={handleNewResearch}>新研究</button></div></div>

  if (!activeSessionId) return <ResearchComposer
    value={currentSetup()} onChange={applySetup} onStart={handleStart} onPreview={()=>previewMutation.mutate()} onBack={onBack}
    inputRef={inputRef} onKeyDown={handleKeyDown} busy={busy} starting={startMutation.isPending}
    understanding={understanding} previewCurrent={understandingKey===requestDraftKey}
    error={startMutation.error?.message||previewMutation.error?.message} skills={skillsData?.items||[]}
  />

  return <div className="research-workspace">
    <header className="workspace-heading">
      <div><h1>{result?.query || query || '研究工作区'}</h1><details className="workspace-question"><summary>完整研究问题</summary><p>{result?.query||query}</p></details></div>
      <button className="btn-secondary" type="button" onClick={handleNewResearch}><Icon name="plus" size={17}/>新研究</button>
    </header>
    <div className="workspace-toolbar"><div className="pill-tabs" role="group" aria-label="研究视图">
      {[['workflow','研究流程'],['report','图文报告'],['records','研究记录']].map(([id,label])=><button type="button" key={id} aria-pressed={activePanel===id} onClick={()=>setActivePanel(id)}>{label}</button>)}
    </div><div className="workspace-statistics"><StatusPill status={sessionStatus||'pending'} label={isStreaming ? currentStage : stoppedLabel}/>
      <span>{planNodes ? `${completedNodes}/${planNodes.length} 取证步骤` : `${agentEvents.length} 条记录`}</span>
      {toolCallCount!==undefined&&<span>{toolCallCount} 次工具调用</span>}
    </div></div>
    {showConfirmationState&&<p className="workspace-notice" role="status">等待确认</p>}
    {sseError&&<p className="workspace-notice" role="status">实时连接中断<button type="button" className="btn-ghost" disabled={!canRefetchResult} onClick={()=>void refetchResult()}>刷新记录</button></p>}
    <section hidden={activePanel!=='workflow'} aria-label="研究流程视图">
      {result&&<ResearchRunControls key={`run-${result.session_id}-${result.execution_id}`} value={result}
        onRefresh={async()=>{const value=await refetchResult();if(value.error)throw value.error}}
        onResumed={async execution=>{clearEvents();setStreamRunKey(execution);setSessionStatus('running');setIsStreaming(true);await refetchResult()}}
        onRestart={openRestartConfiguration} onSynthesis={stage=>resumeSynthesis.mutate(stage)} synthesisBusy={resumeSynthesis.isPending}/>}
      <ResearchFlow key={activeSessionId} plan={result?.plan_manifest} dag={result?.execution_plan} events={traceEvents} status={sessionStatus||'pending'} tools={toolAudit.data} analysis={analysisProgress} history={result?.plan_history} connection={sseStatus} runtimeStatus={result?.runtime_status}/>
      {resumeSynthesis.error&&<p role="alert" className="composer-error">{resumeSynthesis.error.message}</p>}
      <div className="workspace-summary-row">
        <section className="workspace-summary"><span className="eyebrow">当前阶段</span><h2>{isStreaming ? currentStage : stoppedLabel}</h2>
          {analysisProgress&&<p>{analysisPhase}{progressParts[2]==='conditions'?' · 条件补读':''}{analysisBatch?` · 第 ${analysisBatch} 组`:''} · {analysisProgress.completed_steps} 步已保存</p>}
          {analysisProgress?.stop_reason==='insufficient_context_budget'&&<p className="text-sm">本阶段剩余上下文额度不足。</p>}
        </section>
        <section className="workspace-summary"><span className="eyebrow">Token 额度</span><h2>{result?.budget_state?.used_total_tokens?.toLocaleString()??'—'}<small> / {result?.budget_state?.max_total_tokens?.toLocaleString()??'—'}</small></h2>
          {typeof result?.budget_state?.used_total_tokens==='number'&&typeof result.budget_state.max_total_tokens==='number'&&<progress aria-label="已用 Token 额度" value={result.budget_state.used_total_tokens} max={Math.max(1,result.budget_state.max_total_tokens)}/>}
          <p>模型与工具累计用量</p>
        </section>
      </div>
    </section>
    <section hidden={activePanel!=='report'} className="reader-workspace" aria-label="图文报告视图">
      <div className="reader-heading"><h2>研究报告</h2><div>{normalizedCitations.length>0&&<span>{normalizedCitations.length} 条引用</span>}{result?.status==='completed'&&<ReportDownloads result={result} reportElement={reportElement}/>}</div></div>
      {activeSessionId&&<ReportHistory key={activeSessionId} sessionId={activeSessionId}/>}
      <div ref={setReportElement}><ReportPreview key={activeSessionId} report={displayReport??''} citations={normalizedCitations} sessionId={activeSessionId}
        streaming={isStreaming} emptyTitle={isStreaming?`正在${currentStage}`:emptyReportTitle}
        emptyDescription={emptyReportDescription} reportSummary={result?.organization_result?.report_summary}
        deliveryView={result?.delivery_view} reportEditorial={result?.report_editorial} budgetState={result?.budget_state} reportAudit={result?.report_audit}
        contextEvidence={{analyst:result?.organization_result?.analyst_context,report:result?.organization_result?.report_context}}/></div>
    </section>
    <section hidden={activePanel!=='records'} className="workspace-records" aria-label="研究记录视图">
      <ExecutionFeed events={traceEvents} connection={sseStatus} status={sessionStatus||'pending'}/>
      {result&&<UnderstandingSummary value={result.query_understanding}/>}
      {result&&result.execution_id!==undefined&&<ResearchCancellation key={`cancel-${result.session_id}-${result.execution_id}`} sessionId={result.session_id} executionId={result.execution_id} status={result.status} inflight={result.budget_state?.inflight_model_requests} onRefresh={async()=>{const refreshed=await refetchResult();if(refreshed.error)throw refreshed.error}}/>}
      {result&&<ResearchPlanSummary status={result.status} plan={result.plan_manifest} dag={result.execution_plan} history={result.plan_history} control={result.iteration_control} failure={result.workflow_failure} operationalEvents={result.operational_events}/>}
      {result&&['completed','paused','failed','canceled'].includes(result.status)&&<div ref={configuration}><ResearchConfigurationEditor key={`configure-${result.session_id}`} query={typeof result.restart_parameters?.query==='string'?result.restart_parameters.query:result.query} parameters={result.restart_parameters} onStarted={handleRestartedResearch}/></div>}
      {result?.organization_research&&<section className="card p-5"><h3>研究范围</h3><p className="mt-3">{result.organization_research.scope.entities.map(entity=>entity.name).join('、')||'候选发现'} · {result.organization_research.scope.disciplines.join('、')}</p><p className="text-sm text-xmgray-600 mt-2">{result.organization_research.scope.start_date} — {result.organization_research.scope.end_date}</p>{typeof result.organization_result?.evidence_count==='number'&&<p className="text-sm mt-2">{result.organization_result.evidence_count} 条证据</p>}</section>}
      {result?.status==='completed'&&result.organization_research&&<ResearchMatchingPanel key={result.session_id} sessionId={result.session_id} query={typeof result.restart_parameters?.query==='string'?result.restart_parameters.query:result.query} scope={result.organization_research.scope} disciplines={result.organization_research.scope.disciplines} restartParameters={result.restart_parameters} purpose={result.organization_research.purpose} modules={result.organization_research.modules} corpus={result.organization_research.corpus} taxonomy={result.organization_research.taxonomy?.request} actionRequirements={result.organization_research.action_requirements} onStarted={handleRestartedResearch}/>}
      {result?.status==='completed'&&result.organization_research&&<ClassificationPanel key={`classification-${result.session_id}`} sessionId={result.session_id}/>}
      <IngestionPanel key={`ingestion-${activeSessionId}`} sessionId={activeSessionId}/>
      {result&&['completed','paused','failed','canceled'].includes(result.status)&&<ResearchQuality key={`quality-${result.session_id}`} sessionId={result.session_id}/>}
      <details className="card p-5"><summary>工具调用{toolCallCount!==undefined?` · ${toolCallCount}`:''}</summary><div className="mt-4">{toolAudit.error?<p role="alert">{toolAudit.error.message}</p>:<ToolTrace events={traceEvents} records={toolAudit.data}/>}</div></details>
      {(effectiveSkillIds.length>0||effectiveTools.length>0)&&<details className="card p-5"><summary>阶段 Skill 与工具</summary>
        <div className="mt-4 flex flex-wrap gap-2">{effectiveSkillIds.map(id=><span className="tool-chip" key={id}>{skillsData?.items.find(item=>item.id===id)?.name||id} · {autoMatchedSkillIds.includes(id)?'自动':'手动'}</span>)}{effectiveTools.map(tool=><span className="tool-chip" key={tool}>{tool}</span>)}</div>
        {matchedSkills.map(match=><p className="mt-3 text-sm" key={match.skill_id}>{match.name} · {match.reason}</p>)}
        <p className="mt-3 text-sm">手动启用 {manuallyEnabledSkillIds.length} · 禁用 {manuallyDisabledSkillIds.length}</p>
      </details>}
      {drawingReason&&<p className="workspace-notice">{drawingMessages[drawingReason]||drawingReason}</p>}
    </section>
  </div>
}

export default ResearchDashboard
