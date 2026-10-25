/**
 * useSSE Hook: manages Server-Sent Events connection for research streaming.
 *
 * Usage:
 *   const { events, status, error } = useSSE(sessionId);
 */

import { useState, useEffect, useRef, useCallback } from 'react'

export interface SSEvent {
  type: string
  data: Record<string, unknown>
  timestamp?: string
}

export interface SSEState {
  events: SSEvent[]
  status: 'connecting' | 'connected' | 'disconnected' | 'error'
  error: string | null
}

export function useSSE(sessionId: string | null, runKey = ''): {
  events: SSEvent[]
  status: string
  error: string | null
  clearEvents: () => void
} {
  const feedKey = `${sessionId || ''}|${runKey}`
  const [feed, setFeed] = useState<{ key: string; events: SSEvent[] }>({ key: feedKey, events: [] })
  const events = feed.key === feedKey ? feed.events : []
  const [status, setStatus] = useState<string>('disconnected')
  const [error, setError] = useState<string | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const completedRef = useRef(false)

  const clearEvents = useCallback(() => {
    setFeed({ key: feedKey, events: [] })
    setError(null)
    completedRef.current = false
  }, [feedKey])

  useEffect(() => {
    let active = true
    const append = (event: SSEvent) => {
      if (!active) return
      if (typeof event.data.session_id === 'string' && event.data.session_id !== sessionId) return
      if (runKey && typeof event.data.execution_id === 'string' && event.data.execution_id !== runKey) return
      setFeed(previous => ({ key: feedKey, events: [...(previous.key === feedKey ? previous.events : []), event] }))
    }
    if (!sessionId) {
      setStatus('disconnected')
      setError(null)
      completedRef.current = false
      return
    }

    // Close existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }

    setStatus('connecting')
    setError(null)
    completedRef.current = false

    const eventSource = new EventSource(`/api/v1/research/stream/${sessionId}`)
    eventSourceRef.current = eventSource

    eventSource.onopen = () => {
      if (!active) return
      setStatus('connected')
      setError(null)
    }

    eventSource.onmessage = (event) => {
      if (!active) return
      try {
        const data = JSON.parse(event.data)
        append({ type: 'message', data, timestamp: new Date().toISOString() })
      } catch {
        // Ignore parse errors
      }
    }

    // Listen for specific event types
    const eventTypes = [
      'connected', 'agent_start', 'agent_complete', 'agent_end', 'agent_error', 'thought',
      'tool_start', 'tool_call', 'tool_complete', 'tool_result', 'tool_error',
      'state_update', 'reflection', 'report_chunk',
      'report_citation', 'done', 'workflow_error', 'workflow_start',
      'control_update',
    ]

    eventTypes.forEach(type => {
      eventSource.addEventListener(type, (event: MessageEvent) => {
        if (!active) return
        try {
          const data = JSON.parse(event.data)
          if (typeof data.session_id === 'string' && data.session_id !== sessionId) return
          if (runKey && typeof data.execution_id === 'string' && data.execution_id !== runKey) return
          if (type === 'done' || type === 'workflow_error') {
            completedRef.current = true
            eventSource.close()
            eventSourceRef.current = null
            setStatus('disconnected')
          }
          const retainedTime=typeof data.timestamp==='string'?data.timestamp:undefined
          const timestamp=retainedTime&&!/(?:Z|[+-]\d{2}:\d{2})$/i.test(retainedTime)?`${retainedTime}Z`:retainedTime
          append({ type, data, timestamp: timestamp||new Date().toISOString() })
        } catch {
          append({ type, data: { raw: event.data }, timestamp: new Date().toISOString() })
        }
      })
    })

    eventSource.onerror = () => {
      if (!active || completedRef.current) {
        return
      }
      setStatus('error')
      setError('SSE connection error')
      // EventSource will auto-reconnect
    }

    return () => {
      active = false
      eventSource.close()
      eventSourceRef.current = null
      completedRef.current = false
      setStatus('disconnected')
    }
  }, [sessionId, runKey, feedKey])

  return { events, status, error, clearEvents }
}
