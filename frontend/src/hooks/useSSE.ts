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
  const [events, setEvents] = useState<SSEvent[]>([])
  const [status, setStatus] = useState<string>('disconnected')
  const [error, setError] = useState<string | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const completedRef = useRef(false)

  const clearEvents = useCallback(() => {
    setEvents([])
    setError(null)
    completedRef.current = false
  }, [])

  useEffect(() => {
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
      setStatus('connected')
      setError(null)
    }

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        setEvents(prev => [
          ...prev,
          { type: 'message', data, timestamp: new Date().toISOString() }
        ])
      } catch {
        // Ignore parse errors
      }
    }

    // Listen for specific event types
    const eventTypes = [
      'connected', 'agent_start', 'agent_complete', 'agent_end', 'thought',
      'tool_start', 'tool_call', 'tool_complete', 'tool_result', 'tool_error',
      'state_update', 'reflection', 'report_chunk',
      'report_citation', 'done', 'workflow_error', 'workflow_start',
    ]

    eventTypes.forEach(type => {
      eventSource.addEventListener(type, (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data)
          if (type === 'done' || type === 'workflow_error') {
            completedRef.current = true
            eventSource.close()
            eventSourceRef.current = null
            setStatus('disconnected')
          }
          setEvents(prev => [
            ...prev,
            { type, data, timestamp: new Date().toISOString() }
          ])
        } catch {
          setEvents(prev => [
            ...prev,
            { type, data: { raw: event.data }, timestamp: new Date().toISOString() }
          ])
        }
      })
    })

    eventSource.onerror = () => {
      if (completedRef.current) {
        return
      }
      setStatus('error')
      setError('SSE connection error')
      // EventSource will auto-reconnect
    }

    return () => {
      eventSource.close()
      eventSourceRef.current = null
      completedRef.current = false
      setStatus('disconnected')
    }
  }, [sessionId, runKey])

  return { events, status, error, clearEvents }
}
