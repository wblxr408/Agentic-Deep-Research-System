/**
 * AgentTrace - Xiaomi-style agent execution trace.
 *
 * Xiaomi design:
 * - Minimal, clean timeline
 * - Left accent border for status
 * - Agent icons instead of text
 * - Subtle color coding
 */

import { useMemo, useEffect, useRef } from 'react'
import type { SSEvent } from '../hooks/useSSE'

interface AgentTraceProps {
  events: SSEvent[]
}

// Agent display config
type AgentConfig = { label: string; color: string; bg: string }

const AGENT_CONFIG: Record<string, AgentConfig> = {
  planner:  { label: '规划器', color: 'text-violet-600',  bg: 'bg-violet-50' },
  search:    { label: '搜索',   color: 'text-blue-600',    bg: 'bg-blue-50' },
  browser:   { label: '浏览器', color: 'text-emerald-600', bg: 'bg-emerald-50' },
  rag:       { label: '检索',   color: 'text-amber-600',  bg: 'bg-amber-50' },
  analyst:   { label: '分析师', color: 'text-purple-600', bg: 'bg-purple-50' },
  reflection:{ label: '反思',   color: 'text-rose-600',   bg: 'bg-rose-50' },
  report:    { label: '报告',   color: 'text-xm-600',    bg: 'bg-xm-50' },
  replan:    { label: '重规划', color: 'text-orange-600', bg: 'bg-orange-50' },
  dag_executor: { label: '执行器', color: 'text-cyan-600', bg: 'bg-cyan-50' },
}

const DEFAULT_AGENT_COLOR = 'text-xmgray-500'
const DEFAULT_AGENT_BG = 'bg-xmgray-50'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function getQueryPreview(data: Record<string, unknown>): string {
  const args = data.args
  if (!isRecord(args) || typeof args.query !== 'string') {
    return ''
  }
  return args.query
}

function getAgentConfig(agent: string): AgentConfig {
  return AGENT_CONFIG[agent] ?? {
    label: agent || '?',
    color: 'text-xmgray-600',
    bg: DEFAULT_AGENT_BG,
  }
}

function AgentIcon({ agent }: { agent: string }) {
  const cfg = getAgentConfig(agent)
  return (
    <span className={`inline-flex items-center justify-center w-5 h-5 rounded-md text-[10px] font-semibold ${cfg.bg} ${cfg.color}`}>
      {cfg.label.slice(0, 1)}
    </span>
  )
}

function AgentTrace({ events }: AgentTraceProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events])

  const items = useMemo(() => {
    return events
      .filter(e => e.type !== 'connected' && e.type !== 'workflow_start' && e.type !== 'state_update')
      .map((e, idx) => {
        let content = ''
        let agent = ''
        let eventClass = ''

        switch (e.type) {
          case 'agent_start':
            agent = String(e.data.agent || 'agent')
            content = String(e.data.content || `${agent} 开始执行`)
            eventClass = 'agent_start'
            break
          case 'agent_end':
          case 'agent_complete':
            agent = String(e.data.agent || 'agent')
            content = String(e.data.content || e.data.summary || `${agent} 执行完成`)
            eventClass = 'agent_complete'
            break
          case 'tool_call':
          case 'tool_start':
            agent = String(e.data.agent || '')
            content = `${String(e.data.tool_name || e.data.tool || 'tool')}: ${getQueryPreview(e.data).slice(0, 60)}`
            eventClass = 'tool_start'
            break
          case 'tool_result':
          case 'tool_complete':
            content = `${String(e.data.tool_name || e.data.tool || 'tool')} 完成`
            if (e.data.result_summary) {
              content += ` · ${String(e.data.result_summary).slice(0, 40)}`
            }
            eventClass = e.data.status === 'error' ? 'tool_error' : 'tool_complete'
            break
          case 'tool_error':
            content = `错误: ${e.data.error || '未知错误'}`
            eventClass = 'tool_error'
            break
          case 'error':
            content = String(e.data.message || e.data.content || '发生错误')
            eventClass = 'error'
            break
          case 'done':
            content = '研究完成'
            eventClass = 'done'
            break
          default:
            if (e.data.content) {
              content = String(e.data.content).slice(0, 120)
            } else if (e.data.summary) {
              content = String(e.data.summary).slice(0, 120)
            } else {
              content = `${e.type}`
            }
            eventClass = 'thought'
        }

        const cfg = agent ? getAgentConfig(agent) : null

        return {
          id: `trace-${idx}-${e.timestamp || idx}`,
          type: e.type,
          agent,
          content,
          eventClass,
          color: cfg?.color || DEFAULT_AGENT_COLOR,
          bg: cfg?.bg || DEFAULT_AGENT_BG,
          timestamp: e.timestamp || new Date().toISOString(),
        }
      })
  }, [events])

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center">
        <svg width="32" height="32" viewBox="0 0 32 32" fill="none" className="mb-3 text-xmgray-200">
          <circle cx="16" cy="16" r="14" stroke="currentColor" strokeWidth="1.5"/>
          <path d="M16 10V16L20 18" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
        </svg>
        <p className="text-sm text-xmgray-400">等待 Agent 活动...</p>
      </div>
    )
  }

  return (
    <div className="space-y-0.5">
      {items.map((item) => (
        <div
          key={item.id}
          className={`agent-trace-item ${item.eventClass} animate-fade-in`}
        >
          {/* Agent badge */}
          <div className="flex items-center gap-2 mb-0.5">
            {item.agent && <AgentIcon agent={item.agent} />}
            <span className={`text-xs font-medium ${item.agent ? item.color : 'text-xmgray-500'}`}>
              {item.agent
                ? (AGENT_CONFIG[item.agent]?.label || item.agent)
                : ''}
            </span>
            <span className="text-[10px] text-xmgray-400 ml-auto">
              {new Date(item.timestamp).toLocaleTimeString('zh-CN', { hour12: false })}
            </span>
          </div>
          {/* Content */}
          <p className="text-xs text-xmgray-600 leading-relaxed pl-7 break-words">
            {item.content}
          </p>
        </div>
      ))}
      <div ref={bottomRef} />
    </div>
  )
}

export default AgentTrace
