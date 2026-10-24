// @vitest-environment jsdom
import React from 'react'
import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ResearchDashboard from '../src/components/ResearchDashboard'

vi.mock('../src/hooks/useSSE', () => ({ useSSE: () => ({ events: [], status: 'idle', error: null, clearEvents: vi.fn() }) }))
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

function mount() {
  const submitted: Record<string, unknown>[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/v1/research' && init?.method === 'POST') {
      submitted.push(JSON.parse(String(init.body)))
      return Response.json({ session_id: 'source-test', status: 'running' })
    }
    return Response.json({ items: [] })
  }))
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ResearchDashboard /></QueryClientProvider>)
  return submitted
}

test('public research submits with internal documents disabled by default', async () => {
  const user = userEvent.setup()
  const submitted = mount()
  await user.type(screen.getByPlaceholderText('例如：分析 2025 年中国新能源汽车市场格局'), '公开市场研究')
  await user.click(screen.getByRole('button', { name: '开始研究' }))
  await waitFor(() => expect(submitted).toHaveLength(1))
  expect(submitted[0].use_internal_docs).toBe(false)
  expect(submitted[0].rag_group).toBeNull()
  expect(submitted[0].allow_web_after_rag_hit).toBeUndefined()
})

test.each([true, false])('enabling documents and then retaining selection %s sends the matching scope', async (keepEnabled) => {
  const user = userEvent.setup()
  const submitted = mount()
  const toggle = screen.queryByRole('checkbox', { name: '补充检索内部资料' })
  expect(toggle).toBeTruthy()
  const group = screen.getByRole('textbox', { name: '内部资料分组（可选）' }) as HTMLInputElement
  expect(group.disabled).toBe(true)
  await user.click(toggle!)
  expect(group.disabled).toBe(false)
  await user.type(group, 'project-a')
  if (!keepEnabled) {
    await user.click(toggle!)
    expect(group.disabled).toBe(true)
  }
  await user.type(screen.getByPlaceholderText('例如：分析 2025 年中国新能源汽车市场格局'), '公开市场研究')
  await user.click(screen.getByRole('button', { name: '开始研究' }))
  await waitFor(() => expect(submitted).toHaveLength(1))
  expect(submitted[0].use_internal_docs).toBe(keepEnabled)
  expect(submitted[0].rag_group).toBe(keepEnabled ? 'project-a' : null)
})
