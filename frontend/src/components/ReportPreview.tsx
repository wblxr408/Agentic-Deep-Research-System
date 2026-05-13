/**
 * ReportPreview - Xiaomi-style report rendering with Markdown and citations.
 */

import { useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'

interface ReportPreviewProps {
  report: string
  citations: Array<{ citation_id: string; source_url: string; source_title: string }>
  streaming?: boolean
}

function ReportPreview({ report, citations, streaming = false }: ReportPreviewProps) {
  const citationMap = useMemo(() => {
    const map = new Map<string, { url: string; title: string }>()
    citations.forEach(c => {
      map.set(c.citation_id, { url: c.source_url, title: c.source_title })
    })
    return map
  }, [citations])

  if (!report) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center py-16">
        {streaming ? (
          <>
            <div className="relative w-10 h-10 mb-4">
              <div className="absolute inset-0 border-2 border-xm-200 rounded-full" />
              <div className="absolute inset-0 border-2 border-xm-500 border-t-transparent rounded-full animate-spin" />
            </div>
            <p className="text-sm text-xmgray-500 font-medium">正在生成研究报告...</p>
            <p className="text-xs text-xmgray-400 mt-1">请稍候，AI 正在分析和撰写</p>
          </>
        ) : (
          <>
            <svg width="40" height="40" viewBox="0 0 40 40" fill="none" className="mb-4 text-xmgray-200">
              <rect x="6" y="4" width="28" height="32" rx="4" stroke="currentColor" strokeWidth="1.5"/>
              <path d="M12 12H28M12 18H28M12 24H20" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
            <p className="text-sm text-xmgray-400">输入研究主题后，报告将在此显示</p>
          </>
        )}
      </div>
    )
  }

  return (
    <div className="report-content">
      <ReactMarkdown
        components={{
          // Links
          link: ({ href, children }) => (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="citation-ref"
            >
              {children}
            </a>
          ),
          // Code blocks
          code: ({ node, className, children, ...props }) => {
            const match = /language-(\w+)/.exec(className || '')
            const isInline = !match
            return isInline ? (
              <code className={className} {...props}>
                {children}
              </code>
            ) : (
              <SyntaxHighlighter
                style={oneDark}
                language={match[1]}
                PreTag="div"
              >
                {String(children).replace(/\n$/, '')}
              </SyntaxHighlighter>
            )
          },
          // Citation references
          text: ({ children }) => {
            const text = String(children)
            const citationPattern = /\[citation:(\d+)\]/g
            if (!citationPattern.test(text)) return <>{children}</>

            const parts = text.split(/(\[citation:\d+\])/g)
            return (
              <>
                {parts.map((part, i) => {
                  const match = part.match(/\[citation:(\d+)\]/)
                  if (match) {
                    const num = match[1]
                    const citation = citationMap.get(`citation:${num}`)
                    if (citation?.url) {
                      return (
                        <a
                          key={i}
                          href={citation.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="citation-ref text-xs align-super"
                          title={citation.title}
                        >
                          [{num}]
                        </a>
                      )
                    }
                    return <span key={i} className="text-xm-600 text-xs align-super">[{num}]</span>
                  }
                  return <span key={i}>{part}</span>
                })}
              </>
            )
          },
        }}
      >
        {report}
      </ReactMarkdown>
      {streaming && (
        <span className="inline-block w-1.5 h-4 bg-xm-500 ml-1 animate-pulse" />
      )}
    </div>
  )
}

export default ReportPreview
