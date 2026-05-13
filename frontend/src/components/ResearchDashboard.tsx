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

interface ResearchResult {
  session_id: string
  query: string
  status: string
  report: string | null
  citations: Array<{
    citation_id: string
    source_url: string
    source_title: string
    source_type: string
  }>
  agent_trace: unknown[]
  created_at: string
  completed_at: string | null
}

interface ResearchDashboardProps {
  onBack?: () => void
}

function ResearchDashboard({ onBack }: ResearchDashboardProps) {
  const [query, setQuery] = useState('')
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  // SSE for real-time updates
  const { events, clearEvents } = useSSE(activeSessionId)

  // Focus input on mount
  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  // Fetch research result
  const { data: result } = useQuery<ResearchResult>({
    queryKey: ['research', activeSessionId],
    queryFn: async () => {
      const res = await fetch(`/api/v1/research/${activeSessionId}`)
      if (!res.ok) throw new Error('Failed to fetch result')
      return res.json()
    },
    enabled: !!activeSessionId && !isStreaming,
    refetchInterval: isStreaming ? 3000 : false,
  })

  // Start research mutation
  const startMutation = useMutation({
    mutationFn: async (q: string) => {
      const res = await fetch('/api/v1/research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q }),
      })
      if (!res.ok) throw new Error('Failed to start research')
      return res.json()
    },
    onSuccess: (data) => {
      setActiveSessionId(data.session_id)
      setIsStreaming(true)
      clearEvents()
    },
  })

  // Detect when streaming ends
  useEffect(() => {
    const doneEvent = events.find((e: SSEvent) => e.type === 'done' || e.type === 'error')
    if (doneEvent) {
      setIsStreaming(false)
    }
  }, [events])

  // Build report from streaming chunks
  const streamedReport = events
    .filter((e: SSEvent) => e.type === 'report_chunk')
    .map((e: SSEvent) => String(e.data.chunk || ''))
    .join('')

  // Collect stats from events
  const agentEvents = events.filter((e: SSEvent) =>
    ['agent_start', 'agent_complete', 'agent_end'].includes(e.type)
  )
  const toolEvents = events.filter((e: SSEvent) =>
    ['tool_start', 'tool_call', 'tool_complete', 'tool_result', 'tool_error'].includes(e.type)
  )

  // Latest DAG node status
  const dagNodeEvents = events.filter((e: SSEvent) => e.type === 'agent_start')
  const currentNode = dagNodeEvents.length > 0
    ? (dagNodeEvents[dagNodeEvents.length - 1].data as { agent?: string })?.agent || ''
    : ''

  const handleStart = useCallback(() => {
    if (query.trim().length < 5) return
    startMutation.mutate(query.trim())
  }, [query, startMutation])

  const handleKeyDown = useCallback((e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleStart()
    }
    if (e.key === 'Escape') {
      onBack?.()
    }
  }, [handleStart, onBack])

  const handleNewResearch = useCallback(() => {
    setActiveSessionId(null)
    setQuery('')
    clearEvents()
    inputRef.current?.focus()
  }, [clearEvents])

  const displayReport = streamedReport || result?.report || ''

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
              onClick={handleStart}
              disabled={isStreaming || query.trim().length < 5 || startMutation.isPending}
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
            按 Enter 开始研究 · 整个过程自动完成
          </p>
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
                {isStreaming ? currentNode || '执行中' : '已完成'}
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
                  : '已完成'}
              </span>
            </div>
            <div className="p-4 h-[420px] overflow-y-auto">
              <AgentTrace events={events} />
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
              <ToolTrace events={events} />
            </div>
          </div>
        </div>

        {/* Right: Report panel */}
        <div className="lg:col-span-8 space-y-4">
          {/* Report */}
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
                {isStreaming && (
                  <span className="tag-orange text-[11px]">
                    <span className="status-dot streaming mr-1" />流式生成中
                  </span>
                )}
                {result?.citations && result.citations.length > 0 && (
                  <span className="tag text-[11px]">{result.citations.length} 条引用</span>
                )}
              </div>
            </div>
            <div className="p-6 min-h-[500px] max-h-[680px] overflow-y-auto">
              <ReportPreview
                report={displayReport}
                citations={result?.citations || []}
                streaming={isStreaming}
              />
            </div>
          </div>

          {/* Citations panel */}
          {result?.citations && result.citations.length > 0 && (
            <div className="card p-0 overflow-hidden">
              <div className="px-5 py-4 border-b border-xmgray-100">
                <h3 className="text-sm font-medium text-xmgray-700">
                  引用来源
                </h3>
              </div>
              <div className="p-5 max-h-52 overflow-y-auto space-y-2">
                {result.citations.map((c, i) => (
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
