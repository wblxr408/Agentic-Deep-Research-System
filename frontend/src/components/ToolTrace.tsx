/**
 * ToolTrace - Xiaomi-style tool invocation timeline.
 *
 * Xiaomi design:
 * - Clean horizontal timeline with dots
 * - Tool icons + status
 * - Subtle animations
 */

import { useMemo } from 'react'
import type { SSEvent } from '../hooks/useSSE'

interface ToolCall {
  id: string
  toolName: string
  status: 'running' | 'success' | 'error'
  duration?: number
  agent?: string
  query?: string
  error?: string
}

interface ToolTraceProps {
  events: SSEvent[]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function getString(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined
}

function getToolName(data: Record<string, unknown>): string {
  return getString(data.tool_name) ?? getString(data.tool) ?? 'unknown'
}

function getQuery(data: Record<string, unknown>): string | undefined {
  const args = data.args
  if (!isRecord(args)) {
    return undefined
  }
  return getString(args.query)
}

// Tool icons
const TOOL_ICONS: Record<string, { icon: JSX.Element; color: string; bg: string }> = {
  search: {
    icon: (
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <circle cx="5" cy="5" r="3.5" stroke="currentColor" strokeWidth="1.2"/>
        <path d="M8 8L11 11" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
      </svg>
    ),
    color: 'text-blue-600',
    bg: 'bg-blue-50',
  },
  browser: {
    icon: (
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <rect x="1" y="2" width="10" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.2"/>
        <path d="M1 4H11" stroke="currentColor" strokeWidth="1.2"/>
        <circle cx="3" cy="3" r="0.5" fill="currentColor"/>
        <circle cx="5" cy="3" r="0.5" fill="currentColor"/>
      </svg>
    ),
    color: 'text-emerald-600',
    bg: 'bg-emerald-50',
  },
  rag: {
    icon: (
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <path d="M2 2H10V10H2Z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round"/>
        <path d="M4 5H8M4 7H6" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
      </svg>
    ),
    color: 'text-amber-600',
    bg: 'bg-amber-50',
  },
  duckduckgo_search: {
    icon: (
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <circle cx="5" cy="5" r="3.5" stroke="currentColor" strokeWidth="1.2"/>
        <path d="M8 8L11 11" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
      </svg>
    ),
    color: 'text-blue-600',
    bg: 'bg-blue-50',
  },
  playwright: {
    icon: (
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <rect x="1" y="2" width="10" height="8" rx="1.5" stroke="currentColor" strokeWidth="1.2"/>
        <path d="M1 4H11" stroke="currentColor" strokeWidth="1.2"/>
      </svg>
    ),
    color: 'text-emerald-600',
    bg: 'bg-emerald-50',
  },
}

function ToolIcon({ toolName }: { toolName: string }) {
  const toolKey = Object.keys(TOOL_ICONS).find(k => toolName.toLowerCase().includes(k))
  const cfg = toolKey ? TOOL_ICONS[toolKey] : { icon: null, color: 'text-xmgray-600', bg: 'bg-xmgray-50' }
  return (
    <span className={`inline-flex items-center justify-center w-6 h-6 rounded-lg ${cfg.bg} ${cfg.color}`}>
      {cfg.icon || (
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
          <circle cx="6" cy="6" r="4.5" stroke="currentColor" strokeWidth="1.2"/>
          <path d="M6 4V6.5L7.5 7.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/>
        </svg>
      )}
    </span>
  )
}

function ToolTrace({ events }: ToolTraceProps) {
  const toolCalls = useMemo<ToolCall[]>(() => {
    const calls: ToolCall[] = []
    const callIndexById = new Map<string, number>()

    events.forEach((e, idx) => {
      if (e.type === 'tool_start' || e.type === 'tool_call') {
        const toolName = getToolName(e.data)
        const callId = getString(e.data.call_id) ?? `tool-${idx}`
        callIndexById.set(callId, calls.length)
        calls.push({
          id: callId,
          toolName,
          status: 'running',
          agent: getString(e.data.agent),
          query: getQuery(e.data)?.slice(0, 40),
        })
      } else if (e.type === 'tool_complete' || e.type === 'tool_result') {
        const toolName = getToolName(e.data)
        const callId = getString(e.data.call_id)
        const runningIdx = callId
          ? callIndexById.get(callId)
          : calls.findIndex(c => c.toolName === toolName && c.status === 'running')

        if (runningIdx !== -1) {
          const index = runningIdx ?? -1
          if (index !== -1) {
            calls[index].status = e.data.status === 'error' ? 'error' : 'success'
            calls[index].duration = Number(e.data.duration_ms) || 0
            calls[index].error = getString(e.data.error)
          }
        } else {
          calls.push({
            id: callId ?? `tool-${idx}`,
            toolName,
            status: e.data.status === 'error' ? 'error' : 'success',
            duration: Number(e.data.duration_ms) || 0,
            error: getString(e.data.error),
          })
        }
      } else if (e.type === 'tool_error') {
        const toolName = getToolName(e.data)
        const callId = getString(e.data.call_id)
        const runningIdx = callId
          ? callIndexById.get(callId)
          : calls.findIndex(c => c.toolName === toolName && c.status === 'running')

        if (runningIdx !== undefined && runningIdx !== -1) {
          calls[runningIdx].status = 'error'
          calls[runningIdx].error = getString(e.data.error) ?? 'Unknown error'
        }
      }
    })

    return calls
  }, [events])

  if (toolCalls.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center">
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none" className="mb-2 text-xmgray-200">
          <path d="M6 14H22M22 14L17 9M22 14L17 19" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        <p className="text-xs text-xmgray-400">暂无工具调用</p>
      </div>
    )
  }

  return (
    <div className="space-y-2.5">
      {toolCalls.map((call) => (
        <div
          key={call.id}
          className="flex items-center gap-3 p-2 rounded-xl hover:bg-xmgray-50 transition-colors group"
        >
          {/* Status dot */}
          <div className={`w-2 h-2 rounded-full shrink-0 ${
            call.status === 'success' ? 'bg-emerald-500' :
            call.status === 'error' ? 'bg-red-500' :
            'bg-xm-500 streaming-indicator'
          }`} />

          {/* Icon */}
          <ToolIcon toolName={call.toolName} />

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-xmgray-700 truncate">
                {call.toolName}
              </span>
              {call.status === 'success' && call.duration !== undefined && (
                <span className="text-[10px] text-xmgray-400 shrink-0">
                  {call.duration >= 1000 ? `${(call.duration / 1000).toFixed(1)}s` : `${call.duration}ms`}
                </span>
              )}
              {call.status === 'error' && (
                <span className="text-[10px] text-red-500 shrink-0">失败</span>
              )}
              {call.status === 'running' && (
                <span className="text-[10px] text-xm-500 shrink-0">执行中</span>
              )}
            </div>
            {call.query && (
              <p className="text-[10px] text-xmgray-400 truncate mt-0.5 pl-9">{call.query}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

export default ToolTrace
