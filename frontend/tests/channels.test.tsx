// @vitest-environment jsdom
import React from 'react'
import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ResearchDashboard from '../src/components/ResearchDashboard'
import ToolTrace from '../src/components/ToolTrace'

vi.mock('../src/hooks/useSSE', () => ({ useSSE: () => ({ events: [], status: 'idle', error: null, clearEvents: vi.fn() }) }))
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })
const config = { enabled: true, backends: [], timeout_seconds: 20, max_attempts: 3, feeds: [], transcription_provider: null }
const catalog = [
  { name: 'github', label: 'GitHub', operations: ['search', 'read'], backends: ['gh', 'github-api'], optional_backends: [], config, setup: '公开 API 或已有 gh 认证', last_attempt: null },
  { name: 'rss', label: 'RSS / Atom', operations: ['search', 'read'], backends: ['feed'], optional_backends: [], config, setup: '配置公开 feed', last_attempt: null },
]
function mount() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ResearchDashboard /></QueryClientProvider>)
}

test('selects sources, saves priority, collects actual content and sends research selection', async () => {
  const user = userEvent.setup()
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/v1/channels') return Response.json({ items: catalog })
    if (url === '/api/v1/channels/github/config') return Response.json(JSON.parse(String(init?.body)))
    if (url === '/api/v1/channels/collect') return Response.json({ status: 'success', items: [{ url: 'https://github.com/a/b', title: 'Repository', content: 'Actual content', channel: 'github', backend: 'github-api' }], attempts: [] })
    if (url === '/api/v1/research' && init?.method === 'POST') return Response.json({ session_id: 'session-1', status: 'running' })
    return Response.json({ items: [] })
  })
  vi.stubGlobal('fetch', fetcher)
  mount()
  await user.click(await screen.findByRole('checkbox', { name: 'GitHub' }))
  await user.click(screen.getByRole('button', { name: '维护 GitHub' }))
  await user.selectOptions(screen.getByLabelText('首选后端'), 'github-api')
  await user.click(screen.getByRole('button', { name: '保存渠道配置' }))
  await waitFor(() => expect(screen.getByRole('status').textContent).toContain('已保存'))
  const saved = fetcher.mock.calls.find(([url]) => url === '/api/v1/channels/github/config')
  expect(JSON.parse(String(saved?.[1]?.body)).backends).toEqual(['github-api', 'gh'])
  await user.type(screen.getByLabelText('采集关键词或链接'), 'langgraph')
  await user.click(screen.getByRole('button', { name: '采集内容' }))
  expect(await screen.findByText('Actual content')).toBeTruthy()
  await user.type(screen.getByPlaceholderText('例如：分析 2025 年中国新能源汽车市场格局'), 'research question')
  await user.click(screen.getByRole('button', { name: '开始研究' }))
  await waitFor(() => expect(fetcher.mock.calls.some(([url]) => url === '/api/v1/research')).toBe(true))
  expect(JSON.parse(String(fetcher.mock.calls.find(([url]) => url === '/api/v1/research')?.[1]?.body)).channels).toEqual(['github'])
})

test('failed maintenance is visible and cannot claim saved success', async () => {
  const user = userEvent.setup()
  vi.stubGlobal('fetch', vi.fn(async (url: string) => url === '/api/v1/channels' ? Response.json({ items: catalog }) : url.includes('/config') ? Response.json({ detail: 'state_unavailable' }, { status: 503 }) : Response.json({ items: [] })))
  mount()
  await user.click(await screen.findByRole('button', { name: '维护 GitHub' }))
  await user.click(screen.getByRole('button', { name: '保存渠道配置' }))
  expect((await screen.findByRole('alert')).textContent).toContain('state_unavailable')
  expect(screen.queryByText('已保存')).toBeNull()
})

test('research tool trace displays both failed and successful channel backends', () => {
  render(<ToolTrace events={[{ type: 'tool_complete', data: { channel_attempts: [
    { channel: 'github', backend: 'gh', status: 'failed', error_category: 'dependency_missing', duration_ms: 5 },
    { channel: 'github', backend: 'github-api', status: 'success', error_category: null, duration_ms: 50 },
  ] }, timestamp: '2026-10-12T00:00:00Z' }]} />)
  expect(screen.getByText('github / gh')).toBeTruthy()
  expect(screen.getByText('dependency_missing')).toBeTruthy()
  expect(screen.getByText('github / github-api')).toBeTruthy()
  expect(screen.queryByText('unknown')).toBeNull()
})
