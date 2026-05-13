/**
 * App.tsx - Xiaomi-style frontend for Agentic Deep Research System
 *
 * Design reference: Xiaomi official website
 * - Massive whitespace, minimal UI
 * - Clean white background with subtle gray accents
 * - Orange (#FF8C00) as primary accent color
 * - Large typography, subtle shadows
 * - Smooth micro-interactions
 */

import { useState, useCallback } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ResearchDashboard from './components/ResearchDashboard'
import LLMConfigPanel from './components/LLMConfigPanel'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60,
      retry: 1,
    },
  },
})

/* ============================================================
 * HEADER - Ultra minimal, floating
 * ============================================================ */
function getBackendUrl(path: string) {
  const { protocol, hostname } = window.location
  return `${protocol}//${hostname}:8000${path}`
}

function Header({
  onOpenSettings,
  onOpenResearch,
  onOpenDocs,
  onOpenAbout,
}: {
  onOpenSettings?: () => void
  onOpenResearch?: () => void
  onOpenDocs?: () => void
  onOpenAbout?: () => void
}) {
  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-white/80 backdrop-blur-md border-b border-xmgray-100/80">
      <div className="max-w-6xl mx-auto px-6 md:px-8 h-14 flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-lg bg-xm-500 flex items-center justify-center">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M8 2L14 6V10L8 14L2 10V6L8 2Z" stroke="white" strokeWidth="1.5" strokeLinejoin="round"/>
              <circle cx="8" cy="8" r="2" fill="white"/>
            </svg>
          </div>
          <span className="text-base font-semibold text-xmgray-900 tracking-tight">DeepIntel</span>
        </div>

        {/* Nav */}
        <nav className="hidden md:flex items-center gap-8">
          <button type="button" onClick={onOpenResearch} className="text-sm text-xmgray-500 hover:text-xmgray-900 transition-colors">研究</button>
          <button type="button" onClick={onOpenDocs} className="text-sm text-xmgray-500 hover:text-xmgray-900 transition-colors">文档</button>
          <button type="button" onClick={onOpenAbout} className="text-sm text-xmgray-500 hover:text-xmgray-900 transition-colors">关于</button>
        </nav>

        {/* Status & Settings */}
        <div className="flex items-center gap-4">
          <button
            onClick={onOpenSettings}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-xmgray-50 transition-colors"
            title="LLM 配置"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="text-xmgray-400">
              <path d="M8 10C9.10457 10 10 9.10457 10 8C10 6.89543 9.10457 6 8 6C6.89543 6 6 6.89543 6 8C6 9.10457 6.89543 10 8 10Z" stroke="currentColor" strokeWidth="1.5"/>
              <path d="M13.0607 9.81802L12.2426 10.636C12.0848 10.7939 11.9961 11.0079 11.9961 11.231V12.5C11.9961 12.7761 11.7722 13 11.4961 13H10.2272C10.0041 13 9.78987 13.0886 9.63206 13.2464L8.81396 14.0645C8.36514 14.5133 7.63466 14.5133 7.18583 14.0645L6.36774 13.2464C6.20992 13.0886 5.99574 13 5.77262 13H4.5C4.22386 13 4 12.7761 4 12.5V11.231C4 11.0079 3.91132 10.7939 3.7535 10.636L2.93541 9.81802C2.48658 9.3692 2.48658 8.63871 2.93541 8.18989L3.7535 7.37179C3.91132 7.21398 4 6.99979 4 6.77668V5.5C4 5.22386 4.22386 5 4.5 5H5.77262C5.99574 5 6.20992 4.91132 6.36774 4.7535L7.18583 3.93541C7.63466 3.48658 8.36514 3.48658 8.81396 3.93541L9.63206 4.7535C9.78987 4.91132 10.0041 5 10.2272 5H11.4961C11.7722 5 11.9961 5.22386 11.9961 5.5V6.77668C11.9961 6.99979 12.0848 7.21398 12.2426 7.37179L13.0607 8.18989C13.5095 8.63871 13.5095 9.3692 13.0607 9.81802Z" stroke="currentColor" strokeWidth="1.2"/>
            </svg>
            <span className="text-xs text-xmgray-500 hidden sm:inline">设置</span>
          </button>
          <div className="flex items-center gap-2">
            <div className="status-dot online" />
            <span className="text-xs text-xmgray-400">系统在线</span>
          </div>
        </div>
      </div>
    </header>
  )
}

/* ============================================================
 * HERO SECTION - Xiaomi-style with large typography
 * ============================================================ */
function HeroSection({ onExplore, onDemo }: { onExplore: () => void; onDemo: () => void }) {
  return (
    <section className="min-h-[60vh] flex flex-col items-center justify-center text-center px-6 pt-24 pb-16">
      {/* Overline tag */}
      <div className="tag-orange mb-6 animate-fade-in">
        Autonomous Research Agent
      </div>

      {/* Main headline */}
      <h1 className="text-5xl md:text-6xl lg:text-7xl font-bold text-xmgray-900 tracking-tight leading-[1.1] max-w-4xl animate-fade-up" style={{ animationDelay: '0.1s' }}>
        让 AI 自主完成
        <br />
        <span className="text-xm-500">深度研究报告</span>
      </h1>

      {/* Subheadline */}
      <p className="mt-6 text-lg text-xmgray-500 max-w-xl leading-relaxed animate-fade-up" style={{ animationDelay: '0.2s' }}>
        输入研究主题，DeepIntel 自动规划研究路径、抓取网页、分析证据、
        校验幻觉，生成带引用的结构化报告。
      </p>

      {/* CTA */}
      <div className="mt-10 flex flex-col sm:flex-row items-center gap-4 animate-fade-up" style={{ animationDelay: '0.3s' }}>
        <button
          onClick={onExplore}
          className="btn-primary text-base px-8 py-4 shadow-xm hover:shadow-xm-hover"
        >
          开始研究
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="ml-1">
            <path d="M3 8H13M13 8L9 4M13 8L9 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
        <button onClick={onDemo} className="btn-secondary text-base px-8 py-4">
          查看演示
        </button>
      </div>

      {/* Tech tags */}
      <div className="mt-12 flex flex-wrap justify-center gap-3 animate-fade-in" style={{ animationDelay: '0.4s' }}>
        {['LangGraph', 'Qwen 3.6', 'Playwright', 'RAG', 'Multi-Agent', 'Self-Reflection'].map(tag => (
          <span key={tag} className="tag">{tag}</span>
        ))}
      </div>
    </section>
  )
}

/* ============================================================
 * FEATURES SECTION - 3 cards with icons
 * ============================================================ */
const features = [
  {
    icon: (
      <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
        <path d="M14 4L24 9V19L14 24L4 19V9L14 4Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
        <path d="M14 14L24 9M14 14V24M14 14L4 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
    ),
    title: '自主研究工作流',
    desc: '从查询到报告，全流程 AI 自动完成。Planner 动态规划、Agent 并行执行、Reflection 质量把控。',
  },
  {
    icon: (
      <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
        <rect x="4" y="4" width="8" height="8" rx="2" stroke="currentColor" strokeWidth="1.5"/>
        <rect x="16" y="4" width="8" height="8" rx="2" stroke="currentColor" strokeWidth="1.5"/>
        <rect x="4" y="16" width="8" height="8" rx="2" stroke="currentColor" strokeWidth="1.5"/>
        <path d="M20 16V24M24 20H16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
    ),
    title: 'Research DAG 生成',
    desc: 'LLM 动态生成研究计划 DAG，自动识别可并行节点，按拓扑序执行，最大化效率。',
  },
  {
    icon: (
      <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
        <circle cx="14" cy="14" r="10" stroke="currentColor" strokeWidth="1.5"/>
        <path d="M10 14C10 11.8 11.8 10 14 10C16.2 10 18 11.8 18 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
        <circle cx="14" cy="18" r="1.5" fill="currentColor"/>
      </svg>
    ),
    title: 'Self-Reflection 校验',
    desc: 'Reflection Agent 从事实性、一致性、完整性、引用覆盖率多维度校验，降低幻觉率。',
  },
  {
    icon: (
      <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
        <path d="M6 22V10L14 6L22 10V22" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
        <path d="M10 22V16H18V22" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
        <rect x="12" y="10" width="4" height="4" stroke="currentColor" strokeWidth="1.5"/>
      </svg>
    ),
    title: '工具驱动多 Agent',
    desc: 'Search / Browser / RAG Agent 通过工具调用协作，非角色扮演，每个工具调用可追踪。',
  },
  {
    icon: (
      <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
        <path d="M4 8H24" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
        <path d="M4 14H20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
        <path d="M4 20H16" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
    ),
    title: '流式输出',
    desc: '报告以 Markdown 形式流式生成，实时显示 Agent 思考过程和工具调用轨迹。',
  },
  {
    icon: (
      <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
        <circle cx="14" cy="14" r="10" stroke="currentColor" strokeWidth="1.5"/>
        <path d="M10 14L13 17L18 11" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
      </svg>
    ),
    title: '引用溯源',
    desc: '每个结论都有 Citation 标注，连接回原始来源，支持一键访问。',
  },
]

function FeaturesSection() {
  return (
    <section className="max-w-6xl mx-auto px-6 md:px-8 py-24">
      <div className="text-center mb-16">
        <h2 className="section-title">核心能力</h2>
        <p className="section-subtitle">六大核心技术架构，支撑端到端自主研究</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {features.map((feature, i) => (
          <div
            key={i}
            className="card p-7 group hover:border-xmgray-200"
            style={{ animationDelay: `${i * 0.08}s` }}
          >
            <div className="w-12 h-12 rounded-2xl bg-xm-50 text-xm-500 flex items-center justify-center mb-5 group-hover:bg-xm-100 transition-colors duration-300">
              {feature.icon}
            </div>
            <h3 className="text-lg font-semibold text-xmgray-900 mb-2">{feature.title}</h3>
            <p className="text-sm text-xmgray-500 leading-relaxed">{feature.desc}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

/* ============================================================
 * MAIN APP
 * ============================================================ */
function App() {
  const [view, setView] = useState<'home' | 'research' | 'settings'>('home')

  const handleExplore = useCallback(() => {
    setView('research')
  }, [])

  const handleOpenSettings = useCallback(() => {
    setView('settings')
  }, [])

  const handleOpenDocs = useCallback(() => {
    window.open(getBackendUrl('/docs'), '_blank', 'noopener,noreferrer')
  }, [])

  const handleOpenAbout = useCallback(() => {
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })
  }, [])

  return (
    <QueryClientProvider client={queryClient}>
      <div className="min-h-screen bg-white">
        <Header
          onOpenSettings={handleOpenSettings}
          onOpenResearch={handleExplore}
          onOpenDocs={handleOpenDocs}
          onOpenAbout={handleOpenAbout}
        />

        {view === 'home' && (
          <>
            <HeroSection onExplore={handleExplore} onDemo={handleExplore} />
            <FeaturesSection />
            {/* Footer */}
            <footer className="border-t border-xmgray-100 py-8 text-center">
              <p className="text-sm text-xmgray-400">
                DeepIntel · Agentic Deep Research System · Powered by LangGraph + Qwen
              </p>
            </footer>
          </>
        )}

        {view === 'research' && (
          <main className="pt-14">
            <ResearchDashboard onBack={() => setView('home')} />
          </main>
        )}

        {view === 'settings' && (
          <main className="pt-20 px-6 pb-12">
            <LLMConfigPanel onClose={() => setView('home')} />
          </main>
        )}
      </div>
    </QueryClientProvider>
  )
}

export default App
