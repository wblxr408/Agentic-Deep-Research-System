// @vitest-environment jsdom
import React from 'react'
import { afterEach, expect, test, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from '../src/App'

vi.mock('../src/components/ResearchDashboard', () => ({ default: () => <h1>研究工作台</h1> }))

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

class RenderBoundary extends React.Component<React.PropsWithChildren, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() { return this.state.failed ? <p role="alert">认证后页面无法呈现</p> : this.props.children }
}

test('a successful login renders the authenticated home and opens research', async () => {
  const user = userEvent.setup()
  let authenticated = false
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url === '/api/v1/auth/status') return Response.json({ initialized: true })
    if (url === '/api/v1/auth/me') return Response.json({}, { status: authenticated ? 200 : 401 })
    if (url === '/api/v1/auth/login') { authenticated = true; return Response.json({ principal: { username: 'channel_test' } }) }
    throw new Error(`Unexpected request: ${url}`)
  }))
  render(<RenderBoundary><App /></RenderBoundary>)
  await user.type(await screen.findByLabelText('用户名'), 'channel_test')
  await user.type(screen.getByLabelText('密码'), 'local-test-password')
  await user.click(screen.getByRole('button', { name: '登录' }))
  await user.click(await screen.findByRole('button', { name: '开始研究' }))
  expect(await screen.findByRole('heading', { name: '研究工作台' })).toBeTruthy()
  expect(screen.queryByRole('alert')).toBeNull()
})
