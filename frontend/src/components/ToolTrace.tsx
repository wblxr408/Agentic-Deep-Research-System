import {useLocale,t} from '../i18n'
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
  status: 'running' | 'success' | 'error' | 'unknown'
  duration?: number
  agent?: string
  query?: string
  error?: string
}

interface ToolTraceProps {
  events: SSEvent[]
  records?: PersistedToolCall[]
}

export interface PersistedToolCall {
  call_id: string
  tool_name: string
  agent_type: string
  node_id?: string | null
  args_json: Record<string, unknown>
  status: string
  error_message?: string | null
  result_summary?: string | null
  started_at?: string | null
  completed_at?: string | null
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
  useLocale()

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

function ToolTrace({ events, records }: ToolTraceProps) {
  useLocale()

  const toolCalls = useMemo<ToolCall[]>(() => {
    // The owner-authorized audit rows also exist when a page missed the live events.
    if (records !== undefined) return records.map<ToolCall>(record => {
      const started = record.started_at ? Date.parse(record.started_at) : NaN
      const completed = record.completed_at ? Date.parse(record.completed_at) : NaN
      const duration = Number.isFinite(started) && Number.isFinite(completed) && completed >= started
        ? completed - started : undefined
      return { id: record.call_id, toolName: record.tool_name, agent: record.agent_type,
        status: record.status === 'success' ? 'success' : record.status === 'error' ? 'error'
          : ['running', 'started', 'pending'].includes(record.status) ? 'running' : 'unknown',
        query: getQuery({args: record.args_json}), error: record.error_message || undefined, duration }
    })
    const calls: ToolCall[] = []
    const callIndexById = new Map<string, number>()

    events.forEach((e, idx) => {
      if (Array.isArray(e.data.channel_attempts)) {
        e.data.channel_attempts.forEach((attempt, attemptIndex) => {
          if (!isRecord(attempt)) return
          calls.push({ id: `channel-${idx}-${attemptIndex}`, toolName: `${getString(attempt.channel) || 'channel'} / ${getString(attempt.backend) || 'backend'}`,
            status: attempt.status === 'success' ? 'success' : 'error', duration: Number(attempt.duration_ms) || 0,
            query:getString(attempt.query),
            error: getString(attempt.error_category) })
        })
        return
      }
      if (e.type === 'tool_start' || e.type === 'tool_call') {
        const toolName = getToolName(e.data)
        const callId = getString(e.data.call_id) ?? `tool-${idx}`
        callIndexById.set(callId, calls.length)
        calls.push({
          id: callId,
          toolName,
          status: 'running',
          agent: getString(e.data.agent),
          query: getQuery(e.data),
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
  }, [events, records])

  if (toolCalls.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center">
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none" className="mb-2 text-xmgray-200">
          <path d="M6 14H22M22 14L17 9M22 14L17 19" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        <p className="text-xs text-xmgray-400">{t("暂无工具调用")}</p>
      </div>
    )
  }

  return (
    <div className="space-y-2.5">
      {events.map((event,index)=>isRecord(event.data.candidate_fusion)&&<details key={`fusion-${index}`} className="rounded-lg border p-2 text-xs">
        <summary className="cursor-pointer">{t("联网候选融合与来源记录")}</summary>
        <pre className="whitespace-pre-wrap break-all text-[10px]">{JSON.stringify(event.data.candidate_fusion,null,2)}</pre>
      </details>)}
      {events.map((event,index)=>Array.isArray(event.data.retrieval_channels)&&<details key={`retrieval-${index}`} className="rounded-lg border p-2 text-xs">
        <summary className="cursor-pointer">{t("内部资料筛选与检索记录")}</summary>
        {event.data.retrieval_channels.filter(isRecord).map((item,position)=><div key={position} className="mt-2 space-y-1">
          <p>{getString(item.query)||t("当前检索")} · {getString(item.status)||getString(item.lexical)}</p>
          {typeof item.returned_total==='number'&&<p>{t("返回 ")}{item.returned_total} {t(" 项；请求目标 ")}{Number(item.requested_top_k)||0} {t("项。")}{Number(item.returned_shortfall)>0&&t("结果不足，保持原筛选范围。")}</p>}
          {isRecord(item.filter_selectivity)&&<p>{t("本人有效范围内观察 ")}{Number(item.filter_selectivity.observed_authorized_chunks)||0} {t("块， 其中")}{Number(item.filter_selectivity.retained_in_observed)||0} {t("块符合业务条件。")}{item.filter_selectivity.scope_complete===false&&t("此观察有数量上限，不代表整个资料集比例。")}</p>}
          {isRecord(item.channels)&&<div className="flex flex-wrap gap-2">{Object.entries(item.channels).filter(([,raw])=>isRecord(raw)&&(raw.status!=='skipped'||['no_matching_authorized_sparse_index','no_matching_authorized_paired_index','no_anchored_image_index'].includes(String(raw.reason)))).map(([name,raw])=>{
            if(!isRecord(raw))return null
            const labels:Record<string,string>={literal:'精确匹配',bm25:'关键词',fts:'全文词语',dense:'语义线索',structure:'文档结构',stem:'英文词形',learned_sparse:'学习稀疏语义',paired_dense:'整体语义',late_interaction:'细粒度语义',multimodal:'图文匹配'}
            const state:Record<string,string>={requested:'准备中',completed:'已完成',empty:'无匹配',failed:'未完成',skipped:'无可用资料'}
            const reasons:Record<string,string>={local_model_or_configuration_unavailable:'本地模型不可用',model_configuration_changed:'模型设置已变化',timeout:'本次处理超时',output_limit:'结果超出限制'}
            return <span key={name} className="rounded-md border px-2 py-1">{t(labels[name]||name)} · {t(reasons[String(raw.reason)]||state[String(raw.status)]||'未完成')}{typeof raw.result_count==='number'?` ${raw.result_count}`:''}</span>
          })}</div>}
          <details><summary>{t('查看检索细节')}</summary><pre className="whitespace-pre-wrap break-all text-xs">{JSON.stringify(item,null,2)}</pre></details>
        </div>)}
      </details>)}
      {toolCalls.map((call) => (
        <div
          key={call.id}
          className="flex items-center gap-3 p-2 rounded-xl hover:bg-xmgray-50 transition-colors group"
        >
          {/* Status dot */}
          <div className={`w-2 h-2 rounded-full shrink-0 ${
            call.status === 'success' ? 'bg-emerald-500' :
            call.status === 'error' ? 'bg-red-500' : call.status === 'unknown' ? 'bg-xmgray-400' :
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
                <span className="text-[10px] text-red-500 shrink-0">{t("失败")}</span>
              )}
              {call.status === 'running' && (
                <span className="text-[10px] text-xm-500 shrink-0">{t("执行中")}</span>
              )}
              {call.status === 'unknown' && (
                <span className="text-[10px] text-xmgray-500 shrink-0">{t("结果未知")}</span>
              )}
            </div>
            {call.query && (
              <p title={call.query} className="text-[10px] text-xmgray-400 truncate mt-0.5 pl-9">{call.query}</p>
            )}
            {call.error && (
              <p className="text-[10px] text-red-500 truncate mt-0.5 pl-9">{call.error}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

export default ToolTrace
