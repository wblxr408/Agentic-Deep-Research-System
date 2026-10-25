import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
import './workspace.css'
import './research-workspace.css'
import './report-reader.css'
import './configuration.css'
import './accounts.css'

// Existing components use native fetch. Make every API request carry the
// HttpOnly administrator session without duplicating credentials options.
const nativeFetch = window.fetch.bind(window)
window.fetch = async (input, init = {}) => {
  const response = await nativeFetch(input, { ...init, credentials: init.credentials ?? 'include' })
  const url = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, window.location.href)
  if (url.origin === window.location.origin && url.pathname.startsWith('/api/') && response.status === 401 && !/\/auth\/(login|register|initialize|status|me)$/.test(url.pathname)) window.dispatchEvent(new Event('deepintel:session-expired'))
  return response
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
