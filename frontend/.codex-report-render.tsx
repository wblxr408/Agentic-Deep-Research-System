import React from 'react'
import {renderToStaticMarkup} from 'react-dom/server'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import ReportDeliveryView from './src/components/ReportDeliveryView'
import type {DeliveryView} from './src/components/ReportDeliveryView'

export function renderReport(view:DeliveryView) {
  const refs=(view.citations||[]).flatMap(citation=>{
    try {
      const url=new URL(citation.source_url)
      return ['http:','https:'].includes(url.protocol)
        ? [`[${citation.citation_id.replace('citation:','')}]: <${url.href.replace(/</g,'%3C').replace(/>/g,'%3E')}>`]
        : []
    } catch { return [] }
  }).join('\n')
  return renderToStaticMarkup(<ReportDeliveryView view={view} renderMarkdown={text=><ReactMarkdown
    remarkPlugins={[remarkGfm]} components={{a:({href,children})=><a href={href} rel="noopener noreferrer">{children}</a>,
      img:({src,alt})=><a href={src}>来源图片：{alt||'原图'}</a>}}>{text+'\n\n'+refs}</ReactMarkdown>}/> )
}
