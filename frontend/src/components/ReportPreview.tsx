import {useLocale,t} from '../i18n'
/**
 * ReportPreview - Xiaomi-style report rendering with Markdown and citations.
 */

import { createElement, useId, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import OrganizationReportSummary from './OrganizationReportSummary'
import type { OrganizationReportSnapshot } from './OrganizationReportSummary'
import { EvidenceCards, EvidenceDialog } from './EvidenceViewer'
import { Icon, Modal, safeExternalUrl, TraceLoader } from './Interface'
import type { RetainedCitation } from './RetainedCitations'
import ReportDeliveryView from './ReportDeliveryView'
import ReportLayoutView from './ReportLayoutView'
import ReportMarkdownTable from './ReportMarkdownTable'
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
  report, citations, streaming = false, emptyTitle, emptyDescription, reportSummary, sessionId,
  deliveryView, reportEditorial, budgetState, reportAudit, contextEvidence,
}: ReportPreviewProps) {
  useLocale()

  const readerReport = deliveryView?.report_markdown ?? report
  const [selectedCitation,setSelectedCitation] = useState<RetainedCitation|null>(null)
  const [records,setRecords] = useState(false)
  const prefix = useId().replace(/:/g,'')
  const definitions = useMemo(()=>citations.flatMap(citation=>{
    const url=safeExternalUrl(citation.source_url)
    if(!/^citation:\d+$/.test(citation.citation_id))return []
    const target='<'+(url?url.replace(/</g,'%3C').replace(/>/g,'%3E'):`#retained-${prefix}-${citation.citation_id.replace('citation:','')}`)+'>'
    return [`[${citation.citation_id}]: ${target}`,`[${citation.citation_id.replace('citation:','')}]: ${target}`]
  }).join('\n'),[citations,prefix])
  const headings = useMemo(()=>{
    let fence=''
    return readerReport.split('\n').flatMap(line=>{
      const marker=/^\s*(```+|~~~+)/.exec(line)
      if(marker){if(!fence)fence=marker[1][0];else if(fence===marker[1][0])fence='';return []}
      if(fence)return []
      const match=/^(#{1,3})\s+(.+?)(?:\s+#+)?$/.exec(line)
      return match?[{level:match[1].length,title:match[2].replace(/[*_`]/g,'').replace(/\\([\\#~.>+!(){}\[\]-])/g,'$1')}]:[]
    })
  },[readerReport])
  const structured=Boolean(deliveryView&&deliveryView.template!=='markdown-v1')

  function renderCitation(id:string) {
    const citation=citations.find(item=>item.citation_id===id),label=`[${id.replace('citation:','')}]`
    return citation?<button type="button" className="citation-button" data-citation-id={id} onClick={()=>setSelectedCitation(citation)} aria-label={t('查看来源：{0}',citation.source_title)}>{label}</button>:label
  }

  function renderMarkdown(text:string,withIds=false,interactions:string[]=[]) {
    let headingIndex=0
    const heading=(level:number,children:ReactNode)=>createElement('h'+level,{id:withIds?`reader-${prefix}-${headingIndex++}`:undefined,tabIndex:withIds?-1:undefined},children)
    return <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
      h1:({children})=>heading(1,children),h2:({children})=>heading(2,children),h3:({children})=>heading(3,children),
      a:({href,children})=>{
        const number=/^\[?(?:citation:)?(\d+)\]?$/.exec(String(children).trim())
        const numbered=number?citations.find(item=>item.citation_id==='citation:'+number[1]):undefined
        const numberedMatches=numbered&&(safeExternalUrl(numbered.source_url)===safeExternalUrl(href)&&Boolean(safeExternalUrl(href))||href===`#retained-${prefix}-${numbered.citation_id.replace('citation:','')}`)
        const citation=numberedMatches?numbered:citations.find(item=>safeExternalUrl(item.source_url)===safeExternalUrl(href)&&Boolean(safeExternalUrl(href)))
        const url=href?.startsWith('#')?href:safeExternalUrl(href)
        return citation?<button type="button" className="citation-button" data-citation-id={citation.citation_id} onClick={()=>setSelectedCitation(citation)} aria-label={t("查看来源：{0}", citation.source_title)}>{number?`[${number[1]}]`:children}</button>:<a href={url} target={url?.startsWith('#')?undefined:'_blank'} rel="noopener noreferrer">{children}</a>
      },
      img:({src,alt})=><a href={safeExternalUrl(src)} target="_blank" rel="noopener noreferrer">{alt||t("查看原图")}</a>,
      table:({children})=>interactions.some(item=>item==='sort'||item==='filter')?<ReportMarkdownTable interactions={interactions}>{children}</ReportMarkdownTable>:<table>{children}</table>,
      code:({node:_node,className,children,...props})=>{
        const language=/language-(\w+)/.exec(className||'')
        return language?<SyntaxHighlighter style={oneDark} language={language[1]} PreTag="div">{String(children).replace(/\n$/,'')}</SyntaxHighlighter>:<code className={className} {...props}>{children}</code>
      },
    }}>{text+'\n\n'+definitions}</ReactMarkdown>
  }

  if(!readerReport&&!deliveryView?.pages.length)return <div className="reader-empty">{streaming?<TraceLoader/>:<Icon name="book" size={36}/>}<h3>{emptyTitle||t("研究报告")}</h3>{emptyDescription&&<p>{emptyDescription}</p>}</div>
  return <div className="report-reader">
    {!structured&&headings.length>1&&<nav className="reader-toc" aria-label={t("报告目录")}>{headings.map((item,index)=><a key={index} href={`#reader-${prefix}-${index}`} data-level={item.level}>{item.title}</a>)}</nav>}
    <div className="report-content">
      {structured&&deliveryView&&(deliveryView.layout_binding?.schema_version==='adrs-report-layout-binding-v1'
        ?<ReportLayoutView key={deliveryView.artifact_id} view={deliveryView} renderMarkdown={text=>renderMarkdown(text,false,deliveryView.layout_binding?.layout.interactions||[])} renderCitation={renderCitation}/>
        :<ReportDeliveryView key={deliveryView.artifact_id} view={deliveryView} renderMarkdown={text=>renderMarkdown(text)}/>)}
      {!structured&&<article className="reader-prose">{renderMarkdown(readerReport,true)}</article>}
      {structured&&<details className="reader-fulltext" data-full-report><summary>{t("全文")}</summary><article className="reader-prose">{renderMarkdown(readerReport)}</article></details>}
    </div>
    <EvidenceCards citations={citations} onSelect={setSelectedCitation}/>
    <EvidenceDialog key={`${sessionId||''}-${selectedCitation?.citation_id||''}`} citation={selectedCitation} sessionId={sessionId} onClose={()=>setSelectedCitation(null)}/>
    <div data-app-only className="reader-record-link"><button type="button" className="btn-ghost" onClick={()=>setRecords(true)}><Icon name="source" size={16}/>{t("研究记录")}</button></div>
    <Modal open={records} onClose={()=>setRecords(false)} title={t("研究记录")} wide>
      <div className="report-records">
        <ContextEvidenceSummary analyst={contextEvidence?.analyst} report={contextEvidence?.report} sessionId={sessionId}/>
        {reportAudit&&<section><h3>{t("内容核对")}</h3><p>{reportAudit.supported_claims??0} / {reportAudit.total_claims??0} {t(" 项支持")}</p>
          {typeof reportAudit.source_supported_claims==='number'&&<p>{t("原文支持 ")}{reportAudit.source_supported_claims} {t(" · 方法依据 ")}{reportAudit.method_supported_claims??0}</p>}
          {!!reportAudit.revision_requests?.length&&<details><summary>{t("待处理陈述")}</summary><ol>{reportAudit.revision_requests.map(item=><li key={item.claim_id}><p>{item.text}</p><p>{item.reason}</p></li>)}</ol></details>}
        </section>}
        {budgetState&&<section><h3>{t("用量")}</h3><p>{budgetState.used_total_tokens?.toLocaleString()??'—'} / {budgetState.max_total_tokens?.toLocaleString()??'—'} Token</p>
          {(budgetState.model_stop_reason||budgetState.hard_stop_reason)&&<p>{t("停止原因：")}{budgetState.model_stop_reason||budgetState.hard_stop_reason}</p>}
          {!!budgetState.model_requests?.some(item=>item.routing)&&<details><summary>{t("模型路径")}</summary>{budgetState.model_requests.filter(item=>item.routing).slice(-50).map((item,index)=><p key={index}>{item.routing?.stage} · {item.routing?.provider} / {item.routing?.model} · {item.routing?.reason}</p>)}</details>}
          {!!budgetState.routing_decisions?.length&&<details><summary>{t("路由调整")}</summary>{budgetState.routing_decisions.map((item,index)=><p key={item.upgrade_id||index}>{item.stage} · {item.status} · {item.reason}{item.to_model&&` · ${item.from_model} → ${item.to_model}`}</p>)}</details>}
        </section>}
        {!!deliveryView?.layout_binding?.missing?.length&&<details><summary>{t('版式资料')}</summary><ul>{deliveryView.layout_binding.missing.map((item,index)=><li key={index}>{t('第 {0} 章 · 第 {1} 个组件',item.section_index,item.block_index)} · {item.status==='omitted'?t('已省略'):item.status==='required_missing'?t('等待资料'):t('暂无匹配资料')}</li>)}</ul></details>}
        {deliveryView?.template_revision&&<section><h3>{t('报告样式')}</h3><p>{t('使用第 {0} 次保存的样式',deliveryView.template_revision.version)}{deliveryView.template_revision.modified_for_task?' · '+t('本次有调整'):''}</p></section>}
        {deliveryView&&<details><summary>{t("生成与交付记录")}</summary><p>{t("产物：")}{deliveryView.artifact_id}</p>{reportEditorial?.note&&<p>{reportEditorial.note}</p>}{deliveryView.gaps.map((gap,index)=><p key={index}>{gap}</p>)}
          <pre>{JSON.stringify({audit:deliveryView.audit,module_results:deliveryView.module_results,drawing:deliveryView.drawing,formats:deliveryView.formats},null,2)}</pre>
        </details>}
        {reportSummary&&<OrganizationReportSummary snapshot={reportSummary}/>}
        {readerReport!==report&&<details><summary>{t("原始报告")}</summary><pre>{report}</pre></details>}
      </div>
    </Modal>
    {streaming&&<span className="reader-stream-caret" aria-label={t("内容更新中")}/>}
  </div>
}

export default ReportPreview
