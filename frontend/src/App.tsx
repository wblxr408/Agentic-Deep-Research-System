import {useLocale,t,uiMessage} from './i18n'
import { useState, useCallback, useEffect, useRef } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ResearchDashboard from './components/ResearchDashboard'
import LLMConfigPanel from './components/LLMConfigPanel'
import DocumentManager from './components/DocumentManager'
import SkillManager from './components/SkillManager'
import AuthGate from './components/AuthGate'
import type { AuthState, Account } from './components/AuthGate'
import AccountPanel, { AdminAccounts } from './components/AccountPanel'
import { AppearanceProvider, AppearanceControls, palettes, useAppearance } from './components/Appearance'
import { Icon, TraceLoader } from './components/Interface'
import TechnicalDocs from './components/TechnicalDocs'

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000, retry: 1 } } })
type View = 'home' | 'research' | 'settings' | 'documents' | 'skills' | 'technology' | 'login' | 'register' | 'account' | 'admin'
function initialView(): View {
  const params = new URLSearchParams(window.location.search), view = params.get('view')
  return ['home', 'research', 'settings', 'documents', 'skills', 'technology', 'login', 'register', 'account', 'admin'].includes(view || '') ? view as View : params.has('session') ? 'research' : 'home'
}

function Header({ view, navigate, auth }: { view: View; navigate: (view: View) => void; auth: AuthState | null }) {
  useLocale()

  const { language } = useAppearance(), en = language === 'en'
  return <header className={`site-header ${view === 'home' ? 'site-header--hero' : ''}`}>
    <a className="brand" href="?view=home" onClick={event => { event.preventDefault(); navigate('home') }} aria-label={t("DeepIntel 首页")}>
      <span className="brand-mark"><Icon name="layers" size={23} /></span><span>DeepIntel<span className="brand-period">.</span></span>
    </a>
    <nav className="primary-nav" aria-label={t("主导航")}>
      <button type="button" aria-current={view === 'research' ? 'page' : undefined} onClick={() => navigate('research')}>{en ? 'Research' : t("研究")}</button>
      <button type="button" aria-current={view === 'documents' ? 'page' : undefined} onClick={() => navigate('documents')}>{en ? 'Sources' : t("资料")}</button>
      <button type="button" aria-current={view === 'skills' ? 'page' : undefined} onClick={() => navigate('skills')}>Skills</button>
      <a href="?view=technology" target="_blank" rel="noopener noreferrer">{en ? 'How it works' : t("技术原理")} <span aria-hidden="true">↗</span></a>
    </nav>
    <div className="header-tools"><AppearanceControls /><button type="button" className="icon-button" aria-label={t("模型设置")} title={t("模型设置")} onClick={() => navigate('settings')}><Icon name="settings" /></button>
      <div className="header-auth">{auth?.authenticated && auth.user ? <button type="button" className="header-account" onClick={() => navigate('account')} aria-label={t("账号：{0}", auth.user.username)}><span>{auth.user.username}</span><span className="header-role">{auth.user.role === 'admin' ? t("管理员") : t("普通用户")}</span></button> : <><button type="button" onClick={() => navigate('login')}>{en ? 'Log in' : t("登录")}</button>{auth?.registration_enabled && <button type="button" className="header-register" onClick={() => navigate('register')}>{en ? 'Sign up' : t("注册")}</button>}</>}</div>
    </div>
  </header>
}

function Home({ navigate }: { navigate: (view: View) => void }) {
  useLocale()

  const { language, theme } = useAppearance(), en = language === 'en'
  const palette = palettes.find(item => item.id === theme) || palettes[0]
  return <>
    <section className={`home-hero ${en ? 'home-hero--english' : ''}`} aria-label={en ? 'Research is all you need' : t("知之为知之，不知则搜之。")}>
      <img className="home-hero__art" src={`/backgrounds/${palette.image}`} alt="" fetchPriority="high" />
      <div className="home-hero__shade" />
      <div className="home-hero__content">
        <h1>{en ? <>Research is<br /><em>all you need</em></> : <>{t("知之为知之，")}<br /><em>{t("不知则搜之。")}</em></>}</h1>
        <p className="hero-subtitle">{en ? 'In Sources We Trust' : t("搜而不思则罔，思而不搜则殆。")}</p>
        <div className="hero-actions"><button type="button" className="hero-button" onClick={() => navigate('research')}>{en ? 'Start researching' : t("开始研究")}<Icon name="arrow" /></button>
          <a href="?view=technology" target="_blank" rel="noopener noreferrer" className="hero-link">{en ? 'How it works' : t("了解技术原理")}<Icon name="external" size={16} /></a></div>
      </div>
      <div className="hero-bottom" aria-hidden="true"><span></span><span>↓</span></div>
    </section>
    <section className="home-index" aria-label={t("工作区入口")}>
      {[
        { view: 'research' as View, icon: 'search', title: en ? 'Ask a question.' : t("从一个问题开始"), description: en ? 'Scope, sources and a research plan.' : t("确定范围、来源和研究计划。") },
        { view: 'documents' as View, icon: 'book', title: en ? 'Follow the sources.' : t("回到资料本身"), description: en ? 'Your documents, passages and references.' : t("整理资料，定位原文与引用。") },
        { view: 'skills' as View, icon: 'layers', title: en ? 'Make it your own.' : t("按你的方式研究"), description: en ? 'Choose methods and visualization skills.' : t("选择研究方法与绘图 Skill。") },
      ].map((item, index) => <button type="button" className="home-index-item" key={item.view} onClick={() => navigate(item.view)}>
        <span className="index-number">0{index + 1}</span><Icon name={item.icon} size={27} /><h2>{item.title}</h2><p>{item.description}</p><span className="index-arrow"><Icon name="arrow" /></span>
      </button>)}
    </section>
    <footer className="site-footer"><span>DeepIntel.</span><a href="?view=technology" target="_blank" rel="noopener noreferrer">{en ? 'Explore the process' : t("查看研究流程")} ↗</a></footer>
  </>
}

function Workspace() {
  useLocale()

  const [view, setView] = useState<View>(initialView)
  const [researchVisited, setResearchVisited] = useState(() => initialView() === 'research')
  const [auth, setAuth] = useState<AuthState | null>(null)
  const [authError, setAuthError] = useState<string | null>(null)
  const authRequest = useRef(0)
  const identity = useRef<string | null>(null)
  const identityKnown = useRef(false)
  const clearPrivateState = useCallback(async () => {
    setAuth(null); setResearchVisited(false)
    await queryClient.cancelQueries(); queryClient.clear()
    const url = new URL(window.location.href); url.searchParams.delete('session')
    window.history.replaceState(null, '', url)
  }, [])
  const refreshAuth = useCallback(async () => {
    const request = ++authRequest.current, controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 10000)
    setAuthError(null)
    try {
      const response = await fetch('/api/v1/auth/status', { credentials: 'include', signal: controller.signal })
      if (!response.ok) throw new Error(t("无法读取登录状态，请重试。"))
      const status = await response.json() as { initialized?: unknown; registration_enabled?: boolean; auth_enabled?: boolean }
      if (typeof status.initialized !== 'boolean') throw new Error(t("登录状态无效，请重试。"))
      let authenticated = false
      let user: Account | undefined
      if (status.initialized || status.auth_enabled === false) {
        const me = await fetch('/api/v1/auth/me', { credentials: 'include', signal: controller.signal })
        if (!me.ok && ![401, 403].includes(me.status)) throw new Error(t("会话连接失败，请重试。"))
        authenticated = me.ok
        if (me.ok) user = await me.json() as Account
      }
      if (request === authRequest.current) {
        if (identity.current !== (user?.id || null)) {
          await queryClient.cancelQueries(); queryClient.clear(); setResearchVisited(false)
          if (identityKnown.current) { const url = new URL(window.location.href); url.searchParams.delete('session'); window.history.replaceState(null, '', url) }
        }
        if (request !== authRequest.current) return
        identity.current = user?.id || null
        identityKnown.current = true
        setAuth({ initialized: status.initialized, authenticated, user, registration_enabled: status.registration_enabled === true, auth_enabled: status.auth_enabled })
      }
    } catch (error) {
      if (request === authRequest.current) {
        setAuth(null); setResearchVisited(false); queryClient.clear()
        setAuthError(controller.signal.aborted ? t("连接超时，请重试。") : error instanceof Error ? uiMessage(error.message) : t("无法连接研究服务。"))
      }
    } finally { window.clearTimeout(timeout) }
  }, [])
  const broadcastAuth = useCallback(() => {
    try { localStorage.setItem('deepintel.auth-event.v1', `${Date.now()}:${Math.random()}`) } catch { /* storage can be disabled */ }
  }, [])
  const authenticated = useCallback(async () => {
    await clearPrivateState(); broadcastAuth(); await refreshAuth()
    if (['login', 'register'].includes(initialView())) {
      const url = new URL(window.location.href); url.searchParams.set('view', 'research'); window.history.replaceState(null, '', url); setView('research')
    }
  }, [clearPrivateState, broadcastAuth, refreshAuth])
  const logout = useCallback(async () => {
    const response = await fetch('/api/v1/auth/logout', { method: 'POST' })
    if (!response.ok && response.status !== 401) throw new Error(t("退出未完成，请重试。"))
    ++authRequest.current; identity.current = null
    await clearPrivateState(); broadcastAuth()
    const url = new URL(window.location.href); url.searchParams.set('view', 'login'); window.history.replaceState(null, '', url); setView('login')
    await refreshAuth()
  }, [clearPrivateState, broadcastAuth, refreshAuth])
  useEffect(() => { void refreshAuth() }, [refreshAuth])
  useEffect(() => {
    const invalidate = () => { void clearPrivateState().then(refreshAuth) }
    const changed = (event: StorageEvent) => { if (event.key === 'deepintel.auth-event.v1') invalidate() }
    window.addEventListener('storage', changed); window.addEventListener('deepintel:session-expired', invalidate)
    window.addEventListener('deepintel:auth-policy-changed', invalidate)
    const refocus = () => { if (document.visibilityState === 'visible') void refreshAuth() }
    document.addEventListener('visibilitychange', refocus)
    return () => { window.removeEventListener('storage', changed); window.removeEventListener('deepintel:session-expired', invalidate); window.removeEventListener('deepintel:auth-policy-changed', invalidate); document.removeEventListener('visibilitychange', refocus) }
  }, [clearPrivateState, refreshAuth])
  useEffect(() => {
    const changed = () => setView(initialView())
    window.addEventListener('popstate', changed)
    return () => window.removeEventListener('popstate', changed)
  }, [])
  useEffect(() => { if (view === 'research') setResearchVisited(true) }, [view])
  const navigate = useCallback((next: View) => {
    const url = new URL(window.location.href); url.searchParams.set('view', next)
    window.history.pushState(null, '', url); setView(next)
    window.scrollTo({ top: 0 })
  }, [])

  if (view === 'technology') return <TechnicalDocs />
  if (!auth && view !== 'home') return <main className="connection-screen">{authError ? <><p role="alert">{uiMessage(authError)}</p><button className="btn-primary" onClick={() => void refreshAuth()}>{t("重新连接")}</button></> : <p role="status"><TraceLoader />{t("连接研究工作区")}</p>}</main>
  if (auth && !auth.authenticated && view !== 'home') return <AuthGate key={`${auth.initialized}:${view === 'register'}`} state={auth} mode={view === 'register' ? 'register' : 'login'} onModeChange={navigate} onAuthenticated={() => void authenticated()} />

  return <div className="app-shell"><a href="#main-content" className="skip-link">{t("跳到内容")}</a><Header view={view} navigate={navigate} auth={auth} />
    <main id="main-content">
      {view === 'home' && <Home navigate={navigate} />}
      {auth?.authenticated && (researchVisited || view === 'research' || view === 'login' || view === 'register') && <div key={auth.user?.id} hidden={!['research', 'login', 'register'].includes(view)} className="research-surface"><ResearchDashboard onBack={() => navigate('home')} /></div>}
      {view === 'settings' && <section className="management-surface"><LLMConfigPanel /></section>}
      {view === 'documents' && <section className="management-surface"><DocumentManager /></section>}
      {view === 'skills' && <section className="management-surface"><SkillManager /></section>}
      {view === 'account' && auth?.user && <section className="management-surface"><AccountPanel account={auth.user} onLogout={logout} onAdmin={() => navigate('admin')} /></section>}
      {view === 'admin' && auth?.user && <section className="management-surface">{auth.user.role === 'admin' ? <AdminAccounts account={auth.user} /> : <div className="account-panel"><h1>{t("需要管理员权限")}</h1><button type="button" className="btn-secondary" onClick={() => navigate('account')}>{t("返回账号")}</button></div>}</section>}
    </main>
  </div>
}

export default function App() {
  useLocale()

  return <AppearanceProvider><QueryClientProvider client={queryClient}><Workspace /></QueryClientProvider></AppearanceProvider>
}

