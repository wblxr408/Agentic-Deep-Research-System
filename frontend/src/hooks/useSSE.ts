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

export function useSSE(sessionId: string | null): {
  events: SSEvent[]
  status: string
  error: string | null
  clearEvents: () => void
} {
  const [events, setEvents] = useState<SSEvent[]>([])
  const [status, setStatus] = useState<string>('disconnected')
  const [error, setError] = useState<string | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  const clearEvents = useCallback(() => {
    setEvents([])
  }, [])

  useEffect(() => {
    if (!sessionId) {
      setStatus('disconnected')
      return
    }

    // Close existing connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }

    setStatus('connecting')
    setError(null)

    const eventSource = new EventSource(`/api/v1/research/stream/${sessionId}`)
    eventSourceRef.current = eventSource

    eventSource.onopen = () => {
      setStatus('connected')
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
      'report_citation', 'done', 'error', 'workflow_start',
    ]

    eventTypes.forEach(type => {
      eventSource.addEventListener(type, (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data)
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
      setStatus('error')
      setError('SSE connection error')
      // EventSource will auto-reconnect
    }

    return () => {
      eventSource.close()
      setStatus('disconnected')
    }
  }, [sessionId])

  return { events, status, error, clearEvents }
}
