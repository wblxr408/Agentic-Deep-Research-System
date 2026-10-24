/**
 * ReportPreview - Xiaomi-style report rendering with Markdown and citations.
 */

import { useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import OrganizationReportSummary from './OrganizationReportSummary'
import type { OrganizationReportSnapshot } from './OrganizationReportSummary'
import RetainedCitations from './RetainedCitations'
import type { RetainedCitation } from './RetainedCitations'
import ReportDeliveryView from './ReportDeliveryView'
import ContextEvidenceSummary from './ContextEvidenceSummary'
import type { DeliveryView } from './ReportDeliveryView'

interface ReportPreviewProps {
  reportAudit?: {needs_review?:boolean;audit_incomplete?:boolean;total_claims?:number;supported_claims?:number;
    source_supported_claims?:number;method_supported_claims?:number;
    reused_supported_claims?:number;newly_checked_claims?:number;
    revision_requests?:Array<{claim_id:string;text:string;reason:string;requested_action:string}>}|null
  report: string
  citations: RetainedCitation[]
  sessionId?:string|null
  streaming?: boolean
  emptyTitle?: string
  emptyDescription?: string
  reportSummary?: OrganizationReportSnapshot | null
  deliveryView?: DeliveryView | null
  reportEditorial?: { note?: string } | null
  contextEvidence?:{analyst?:unknown;report?:unknown}
  budgetState?: {used_total_tokens?:number;max_total_tokens?:number;cost_status?:string;token_usage_estimated?:boolean;hard_stop_reason?:string|null;model_stop_reason?:string|null;
    routing_decisions?:Array<{upgrade_id?:string;stage:string;trigger:string;status:string;reason:string;from_model?:string;to_model?:string}>;
    model_requests?:Array<{routing?:{stage?:string;provider?:string;model?:string;reason?:string};cost_basis?:string}>} | null
}

function ReportPreview({
  report,
  citations,
  streaming = false,
  emptyTitle,
  emptyDescription,
  reportSummary,
  sessionId,
  deliveryView,
  reportEditorial,
  budgetState,
  reportAudit,
  contextEvidence,
}: ReportPreviewProps) {
  const readerReport = deliveryView?.report_markdown ?? report
  // Standard Markdown reference definitions resolve citations outside code
  // blocks without rewriting report text or introducing raw HTML.
  const citedReport = useMemo(() => {
    const references = citations.flatMap(citation => {
      try {
        const url = new URL(citation.source_url)
        if (!['http:', 'https:'].includes(url.protocol) || !/^citation:\d+$/.test(citation.citation_id)) return []
        const urlDefinition = `<${url.href.replace(/</g, '%3C').replace(/>/g, '%3E')}>`
        return [`[${citation.citation_id}]: ${urlDefinition}`, `[${citation.citation_id.replace('citation:', '')}]: ${urlDefinition}`]
      } catch { return [] }
    })
    return readerReport + '\n\n' + references.join('\n')
  }, [readerReport, citations])

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
            <p className="text-sm text-xmgray-500 font-medium">
              {emptyTitle || '输入研究主题后，报告将在此显示'}
            </p>
            {emptyDescription && (
              <p className="text-xs text-xmgray-400 mt-1">{emptyDescription}</p>
            )}
          </>
        )}
      </div>
    )
  }

  return (
    <div className="report-content">
      {deliveryView && deliveryView.template !== 'markdown-v1' && <ReportDeliveryView key={deliveryView.artifact_id} view={deliveryView}
        renderMarkdown={text=><ReactMarkdown remarkPlugins={[remarkGfm]} components={{a:({href,children})=><a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
          img:({src,alt})=><a href={src} target="_blank" rel="noopener noreferrer">来源图片：{alt||'原图'}</a>}}>{text+citedReport.slice(readerReport.length)}</ReactMarkdown>} />}
      <details data-full-report data-print-duplicate={deliveryView && deliveryView.template !== 'markdown-v1' ? 'true' : undefined} open={!deliveryView || deliveryView.template === 'markdown-v1'}>
      <summary className="cursor-pointer font-medium py-3">阅读全文</summary>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          img: ({src,alt}) => <a href={src} target="_blank" rel="noopener noreferrer">来源图片：{alt||'原图'}</a>,
          // Links
          a: ({ href, children }) => (
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
          code: ({ node: _node, className, children, ...props }) => {
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
        }}
      >
        {citedReport}
      </ReactMarkdown>
      </details>
      <details data-app-only aria-label="研究记录"><summary className="cursor-pointer font-medium py-3">研究记录</summary>
        <ContextEvidenceSummary analyst={contextEvidence?.analyst} report={contextEvidence?.report} sessionId={sessionId}/>
        {reportAudit && <section aria-label="报告内容核对">
          <p>陈述核对支持 {reportAudit.supported_claims ?? 0} / {reportAudit.total_claims ?? 0} 项。
            {typeof reportAudit.source_supported_claims==='number' && <>其中原文支持 {reportAudit.source_supported_claims} 项，任务方法依据支持 {reportAudit.method_supported_claims ?? 0} 项。</>}
            {typeof reportAudit.reused_supported_claims==='number' && <>复用相同输入的原判 {reportAudit.reused_supported_claims} 项，本轮新判 {reportAudit.newly_checked_claims ?? 0} 项。</>}
            {reportAudit.audit_incomplete?'本轮核对尚未完成。':reportAudit.needs_review?'当前稿有需要补证或调整的陈述。':''}</p>
          {!!reportAudit.revision_requests?.length && <details><summary>需要调整的陈述</summary>
            <ol className="list-decimal pl-5 space-y-2">{reportAudit.revision_requests.map(item=><li key={item.claim_id}>
              <p>{item.text}</p><p className="text-sm text-xmgray-500">{item.reason}</p>
            </li>)}</ol>
          </details>}
        </section>}
        {budgetState && <p>模型与工具 Token：{budgetState.used_total_tokens ?? '未知'} / {budgetState.max_total_tokens ?? '未知'}。
          {budgetState.token_usage_estimated && '含未知用量的保守预占。'}
          {budgetState.cost_status === 'unknown_price_or_usage' && '费用未知：尚无可用的完整价格或用量。'}
          {(budgetState.model_stop_reason || budgetState.hard_stop_reason) && ` 停止原因：${budgetState.model_stop_reason || budgetState.hard_stop_reason}`}</p>}
        {!!budgetState?.model_requests?.some(item=>item.routing) && <details><summary>实际模型路径</summary>
          <p className="text-xs">以下为最近50次请求；配置报价是估算依据，供应商账单尚未核对。</p>
          <ol>{budgetState.model_requests.filter(item=>item.routing).slice(-50).map((item,index)=><li key={index}>
            {item.routing?.stage}：{item.routing?.provider} / {item.routing?.model} · {item.routing?.reason}
            {item.cost_basis==='configured_price_estimate_not_invoice'?' · 配置报价估算':item.cost_basis==='unknown'?' · 费用未知':''}
          </li>)}</ol>
        </details>}
        {!!budgetState?.routing_decisions?.length && <details><summary>能力处理记录</summary>
          <p className="text-xs">已准备升级表示决定已保存；是否实际调用请结合模型路径查看。</p>
          <ol>{budgetState.routing_decisions.map((item,index)=><li key={item.upgrade_id||index}>
            {item.stage} · {item.trigger}：{item.status==='prepared'?'已准备升级':'保留原路径'} · {item.reason}
            {item.to_model&&` · ${item.from_model} → ${item.to_model}`}
          </li>)}</ol>
        </details>}
        {deliveryView && <>
          <p>产物版本：{deliveryView.artifact_id}</p>
          <p>陈述核对：{deliveryView.audit?.supported_claims ?? '未知'} / {deliveryView.audit?.total_claims ?? '未知'} 项；人工复核状态未确认。</p>
          {reportEditorial?.note && <p>{reportEditorial.note}</p>}
          {deliveryView.gaps.map((gap,index)=><p key={index}>{gap}</p>)}
          {deliveryView.pages.filter(page=>page.gaps.length).map(page=><details key={page.page_id}><summary>{page.title}：交付记录</summary>{page.gaps.map((gap,index)=><p key={index}>{gap}</p>)}</details>)}
          <details><summary>审核明细与结构化资料</summary><pre className="whitespace-pre-wrap break-all text-xs">{JSON.stringify({audit:deliveryView.audit,module_results:deliveryView.module_results,charts:deliveryView.charts},null,2)}</pre></details>
        </>}
        {reportSummary && <OrganizationReportSummary snapshot={reportSummary} />}
        <RetainedCitations key={sessionId||'unsaved-report'} sessionId={sessionId} citations={citations} />
        {readerReport !== report && <details><summary>保存的原始报告</summary><pre className="whitespace-pre-wrap break-all text-xs">{report}</pre></details>}
      </details>
      {streaming && (
        <span className="inline-block w-1.5 h-4 bg-xm-500 ml-1 animate-pulse" />
      )}
    </div>
  )
}

export default ReportPreview
