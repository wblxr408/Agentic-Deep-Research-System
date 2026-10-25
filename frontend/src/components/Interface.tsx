import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'

export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, ReactNode> = {
    search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></>,
    arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
    back: <path d="M20 12H4m6-6-6 6 6 6" />,
    book: <><path d="M12 5v16M3 3l9 2 9-2v16l-9 2-9-2z" /><path d="m6 8 3 1m6 0 3-1" /></>,
    layers: <><path d="m12 3 10 6-10 6L2 9zM2 14l10 6 10-6M2 18l10 6 10-6" /></>,
    settings: <><path d="M4 6h16M4 12h16M4 18h16" /><path d="M8 3v6m8 0v6m-6 0v6" /></>,
    close: <path d="m6 6 12 12M18 6 6 18" />,
    plus: <path d="M12 4v16M4 12h16" />,
    minus: <path d="M4 12h16" />,
    fit: <><path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5" /><rect x="8" y="8" width="8" height="8" rx="1" /></>,
    target: <><circle cx="12" cy="12" r="7" /><circle cx="12" cy="12" r="2" /><path d="M12 1v4m0 14v4M1 12h4m14 0h4" /></>,
    play: <path d="m8 4 12 8-12 8z" />,
    pause: <path d="M8 4v16M16 4v16" />,
    step: <><path d="m5 5 10 7-10 7zM19 5v14" /></>,
    network: <><circle cx="12" cy="12" r="3" /><circle cx="4" cy="4" r="2" /><circle cx="20" cy="5" r="2" /><circle cx="6" cy="21" r="2" /><path d="m6 6 4 4m5 0 4-4m-8 9-4 4" /></>,
    source: <><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M9 8h6m-6 4h6m-6 4h3" /></>,
    chart: <><path d="M4 3v17h17M8 15l4-5 4 2 5-7" /></>,
    download: <><path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5" /></>,
    external: <><path d="M14 3h7v7m0-7-11 11M10 5H4v16h16v-6" /></>,
    check: <path d="m5 12 4 4L20 5" />,
  }
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] || paths.source}</svg>
}

export function TraceLoader() {
  return <svg className="trace-loader" width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
    <rect className="trace-loader-track" x="3" y="3" width="18" height="18" rx="6" fill="none" stroke="currentColor" strokeWidth="1.6" />
    <rect className="trace-loader-dash" x="3" y="3" width="18" height="18" rx="6" pathLength="100" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
  </svg>
}

export const statusLabels: Record<string, string> = { pending: '等待', waiting: '等待', running: '进行中', started: '进行中', done: '完成', completed: '完成', success: '完成', paused: '已暂停', failed: '失败', error: '失败', canceled: '已取消', skipped: '跳过', unknown: '未记录', pending_confirmation: '待确认' }
export function StatusPill({ status, label }: { status: string; label?: string }) {
  return <span className="state-pill" data-status={status}>{status === 'running' && <TraceLoader />}<span>{label || statusLabels[status] || status}</span></span>
}

export function Modal({ open, onClose, title, children, wide = false }: { open: boolean; onClose: () => void; title: string; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    if (!open || !ref.current) return
    const node = ref.current, trigger = document.activeElement as HTMLElement | null
    node.showModal()
    heading.current?.focus()
    return () => { node.close(); if (trigger?.isConnected) trigger.focus() }
  }, [open])
  if (!open) return null
  return <dialog ref={ref} className={`interface-dialog ${wide ? 'interface-dialog--wide' : ''}`} aria-label={title}
    onCancel={event => { event.preventDefault(); onClose() }}
    onClick={event => { if (event.target === event.currentTarget) { const rect = event.currentTarget.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose() } }}>
    <div className="dialog-heading"><h2 ref={heading} tabIndex={-1}>{title}</h2><button className="icon-button" type="button" aria-label="关闭窗口" onClick={onClose}><Icon name="close" /></button></div>
    <div className="dialog-content">{children}</div>
  </dialog>
}

export function safeExternalUrl(value?: string): string | undefined {
  try { const url = new URL(value || ''); return ['https:', 'http:'].includes(url.protocol) ? url.href : undefined } catch { return undefined }
}
