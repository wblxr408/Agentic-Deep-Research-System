import {useState} from 'react'
import {t,useLocale} from '../i18n'
import {Modal,safeExternalUrl} from './Interface'

interface SourceFigure {
  figure_id:string;label:string;width:number;height:number;png:string
  layout:{caption:string;region_bbox:number[];caption_bbox:number[]}
}
export interface SourcePage {
  asset_id:string;page:number;width?:number;height?:number;png?:string;source_url:string
  presentation?:string;figures?:SourceFigure[]
  titles:string[];captions:string[];output_ids:string[];evidence_ids:string[]
  explanation?:string;report_anchor?:{paragraph_id:string;quote:string}
}

export default function SourcePageGallery({pages,taskId}:{pages:SourcePage[];taskId:string}) {
  useLocale()
  const [selected,setSelected]=useState<{page:SourcePage;figure?:SourceFigure}|null>(null)
  if(!pages.length)return null
  const valid=pages.filter(page=>/^[0-9a-f-]{36}$/i.test(page.asset_id)&&Number.isInteger(page.page)&&page.page>=1&&page.page<=80
    && (page.presentation==='original_pdf_figure_groups'||page.png?.startsWith('data:image/png;base64,')))
  function picture(page:SourcePage,large=false,focused?:SourceFigure) {
    const title=page.titles.join(' · '),url=safeExternalUrl(page.source_url)
    const cropped=page.presentation==='original_pdf_figure_groups'
    const figures=(focused?[focused]:page.figures||[]).filter(figure=>/^source-figure-[0-9a-f]{32}$/.test(figure.figure_id)&&figure.png?.startsWith('data:image/png;base64,'))
    return <figure className="source-page" key={`${page.asset_id}-${page.page}`}>
      <figcaption>{title}<small>{t('原文第 {0} 页',page.page)}</small></figcaption>
      {cropped?<>{!figures.length&&<p>{t('论文图块尚未可用')}</p>}{figures.map(figure=><div className="source-figure" key={figure.figure_id}>
        <h4>{figure.label}</h4>
        {large?<img src={figure.png} alt={`${title} · ${figure.label}`} width={figure.width} height={figure.height}/>:<>
          <a data-app-only href={`#original-${page.asset_id}-${figure.figure_id}`} onClick={event=>{event.preventDefault();setSelected({page,figure})}} aria-label={t('放大原文图块')}><img src={figure.png} alt={`${title} · ${figure.label}`} width={figure.width} height={figure.height}/></a>
          <img className="source-page-offline" src={figure.png} alt={`${title} · ${figure.label}`} width={figure.width} height={figure.height}/>
        </>}
        <p>{figure.layout.caption}</p><a href={figure.png} download={`original-${page.asset_id}-${figure.figure_id}.png`}>{t('下载PNG')}</a>
      </div>)}</>:large?<img src={page.png} alt={t('{0}，原文第 {1} 页',title,page.page)} width={page.width} height={page.height}/>:<>
        <a data-app-only href={`#original-${page.asset_id}-${page.page}`} onClick={event=>{event.preventDefault();setSelected({page})}} aria-label={t('放大原文页')}><img src={page.png} alt={t('{0}，原文第 {1} 页',title,page.page)} width={page.width} height={page.height}/></a>
        <img className="source-page-offline" src={page.png} alt={t('{0}，原文第 {1} 页',title,page.page)} width={page.width} height={page.height}/>
      </>}
      {page.explanation&&<p className="source-page-explanation">{page.explanation}</p>}
      {page.report_anchor&&page.report_anchor.quote!==page.explanation&&<blockquote>{page.report_anchor.quote}</blockquote>}
      {!cropped&&<details><summary>{t('图注与来源')}</summary>{page.captions.map((caption,index)=><p key={index}>{caption}</p>)}</details>}
      <div className="source-page-links">{url&&<a href={url} target="_blank" rel="noopener noreferrer">{t('查看来源')}</a>}
        <a data-app-only href={`/api/v1/research/${encodeURIComponent(taskId)}/source-assets/${page.asset_id}`} download>{t('下载原始 PDF')}</a>
        {!cropped&&<a href={page.png} download={`original-${page.asset_id}-page-${page.page}.png`}>{t('下载PNG')}</a>}
      </div>
    </figure>
  }
  return <section className="source-page-gallery" aria-label={t('原文图示')}>
    <h3>{t('原文图示')}</h3><div className="source-page-grid">{valid.map(page=>picture(page))}</div>
    <div data-app-only><Modal open={!!selected} onClose={()=>setSelected(null)} title={t('原文图示')} wide>{selected&&picture(selected.page,true,selected.figure)}</Modal></div>
    <style>{`.source-page-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:20px}.source-page{min-width:0;margin:0}.source-page figcaption{line-height:1.5;overflow-wrap:anywhere}.source-page small{display:block;font-weight:400;opacity:.7;margin:6px 0 12px}.source-page img{display:block;width:100%;height:auto;max-height:640px;object-fit:contain;background:#fff}.source-page-links{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;margin-top:12px}.source-page .source-page-offline{display:none}.source-page details{font-size:13px} @media print{.source-page a[data-app-only]{display:none!important}.source-page .source-page-offline{display:block!important}.source-page-grid{display:block}.source-page{break-inside:avoid;margin:18px 0}}`}</style>
  </section>
}
