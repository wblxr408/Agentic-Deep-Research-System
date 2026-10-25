import { useState, useCallback, useEffect, useRef } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ResearchDashboard from './components/ResearchDashboard'
import LLMConfigPanel from './components/LLMConfigPanel'
import DocumentManager from './components/DocumentManager'
import SkillManager from './components/SkillManager'
import AuthGate from './components/AuthGate'
import { AppearanceProvider, AppearanceControls, palettes, useAppearance } from './components/Appearance'
import { Icon, TraceLoader } from './components/Interface'
import TechnicalDocs from './components/TechnicalDocs'

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000, retry: 1 } } })
type View = 'home' | 'research' | 'settings' | 'documents' | 'skills' | 'technology'
function initialView(): View {
  const params = new URLSearchParams(window.location.search), view = params.get('view')
  return ['home', 'research', 'settings', 'documents', 'skills', 'technology'].includes(view || '') ? view as View : params.has('session') ? 'research' : 'home'
}

function Header({ view, navigate }: { view: View; navigate: (view: View) => void }) {
  const { language } = useAppearance(), en = language === 'en'
  return <header className={`site-header ${view === 'home' ? 'site-header--hero' : ''}`}>
    <a className="brand" href="?view=home" onClick={event => { event.preventDefault(); navigate('home') }} aria-label="DeepIntel 首页">
      <span className="brand-mark"><Icon name="layers" size={23} /></span><span>DeepIntel<span className="brand-period">.</span></span>
    </a>
    <nav className="primary-nav" aria-label="主导航">
      <button type="button" aria-current={view === 'research' ? 'page' : undefined} onClick={() => navigate('research')}>{en ? 'Research' : '研究'}</button>
      <button type="button" aria-current={view === 'documents' ? 'page' : undefined} onClick={() => navigate('documents')}>{en ? 'Sources' : '资料'}</button>
      <button type="button" aria-current={view === 'skills' ? 'page' : undefined} onClick={() => navigate('skills')}>Skills</button>
      <a href="?view=technology" target="_blank" rel="noopener noreferrer">{en ? 'How it works' : '技术原理'} <span aria-hidden="true">↗</span></a>
    </nav>
    <div className="header-tools"><AppearanceControls /><button type="button" className="icon-button" aria-label="模型设置" title="模型设置" onClick={() => navigate('settings')}><Icon name="settings" /></button></div>
  </header>
}

function Home({ navigate }: { navigate: (view: View) => void }) {
  const { language, theme } = useAppearance(), en = language === 'en'
  const palette = palettes.find(item => item.id === theme) || palettes[0]
  return <>
    <section className={`home-hero ${en ? 'home-hero--english' : ''}`} aria-label={en ? 'Research is all you need' : '知之为知之，不知则搜之。'}>
      <img className="home-hero__art" src={`/backgrounds/${palette.image}`} alt="" fetchPriority="high" />
      <div className="home-hero__shade" />
      <div className="home-hero__content">
        <h1>{en ? <>Research is<br /><em>all you need</em></> : <>知之为知之，<br /><em>不知则搜之。</em></>}</h1>
        <p className="hero-subtitle">{en ? 'In Sources We Trust' : '搜而不思则罔，思而不搜则殆。'}</p>
        <div className="hero-actions"><button type="button" className="hero-button" onClick={() => navigate('research')}>{en ? 'Start researching' : '开始研究'}<Icon name="arrow" /></button>
          <a href="?view=technology" target="_blank" rel="noopener noreferrer" className="hero-link">{en ? 'How it works' : '了解技术原理'}<Icon name="external" size={16} /></a></div>
      </div>
      <div className="hero-bottom" aria-hidden="true"><span></span><span>↓</span></div>
    </section>
    <section className="home-index" aria-label="工作区入口">
      {[
        { view: 'research' as View, icon: 'search', title: en ? 'Ask a question.' : '从一个问题开始', description: en ? 'Scope, sources and a research plan.' : '确定范围、来源和研究计划。' },
        { view: 'documents' as View, icon: 'book', title: en ? 'Follow the sources.' : '回到资料本身', description: en ? 'Your documents, passages and references.' : '整理资料，定位原文与引用。' },
        { view: 'skills' as View, icon: 'layers', title: en ? 'Make it your own.' : '按你的方式研究', description: en ? 'Choose methods and visualization skills.' : '选择研究方法与绘图 Skill。' },
      ].map((item, index) => <button type="button" className="home-index-item" key={item.view} onClick={() => navigate(item.view)}>
        <span className="index-number">0{index + 1}</span><Icon name={item.icon} size={27} /><h2>{item.title}</h2><p>{item.description}</p><span className="index-arrow"><Icon name="arrow" /></span>
      </button>)}
    </section>
    <footer className="site-footer"><span>DeepIntel.</span><a href="?view=technology" target="_blank" rel="noopener noreferrer">{en ? 'Explore the process' : '查看研究流程'} ↗</a></footer>
  </>
}

function Workspace() {
  const [view, setView] = useState<View>(initialView)
  const [researchVisited, setResearchVisited] = useState(() => initialView() === 'research')
  const [auth, setAuth] = useState<{ initialized: boolean; authenticated: boolean } | null>(null)
  const [authError, setAuthError] = useState<string | null>(null)
  const authRequest = useRef(0)
  const refreshAuth = useCallback(async () => {
    const request = ++authRequest.current, controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 10000)
    setAuth(null); setAuthError(null)
    try {
      const response = await fetch('/api/v1/auth/status', { credentials: 'include', signal: controller.signal })
      if (!response.ok) throw new Error('无法读取登录状态，请重试。')
      const status = await response.json() as { initialized?: unknown }
      if (typeof status.initialized !== 'boolean') throw new Error('登录状态无效，请重试。')
      let authenticated = false
      if (status.initialized) {
        const me = await fetch('/api/v1/auth/me', { credentials: 'include', signal: controller.signal })
        if (!me.ok && ![401, 403].includes(me.status)) throw new Error('会话连接失败，请重试。')
        authenticated = me.ok
      }
      if (request === authRequest.current) setAuth({ initialized: status.initialized, authenticated })
    } catch (error) {
      if (request === authRequest.current) setAuthError(controller.signal.aborted ? '连接超时，请重试。' : error instanceof Error ? error.message : '无法连接研究服务。')
    } finally { window.clearTimeout(timeout) }
  }, [])
  useEffect(() => { void refreshAuth() }, [refreshAuth])
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
  if (!auth && view !== 'home') return <main className="connection-screen">{authError ? <><p role="alert">{authError}</p><button className="btn-primary" onClick={() => void refreshAuth()}>重新连接</button></> : <p role="status"><TraceLoader />连接研究工作区</p>}</main>
  if (auth && !auth.authenticated && view !== 'home') return <AuthGate state={auth} onAuthenticated={() => void refreshAuth()} />

  return <div className="app-shell"><a href="#main-content" className="skip-link">跳到内容</a><Header view={view} navigate={navigate} />
    <main id="main-content">
      {view === 'home' && <Home navigate={navigate} />}
      {auth?.authenticated && (researchVisited || view === 'research') && <div hidden={view !== 'research'} className="research-surface"><ResearchDashboard onBack={() => navigate('home')} /></div>}
      {view === 'settings' && <section className="management-surface"><LLMConfigPanel /></section>}
      {view === 'documents' && <section className="management-surface"><DocumentManager /></section>}
      {view === 'skills' && <section className="management-surface"><SkillManager /></section>}
    </main>
  </div>
}

export default function App() {
  return <AppearanceProvider><QueryClientProvider client={queryClient}><Workspace /></QueryClientProvider></AppearanceProvider>
}

