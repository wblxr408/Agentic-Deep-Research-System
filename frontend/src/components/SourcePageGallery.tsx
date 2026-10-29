import {useState} from 'react'
import {t,useLocale} from '../i18n'
import {Modal,safeExternalUrl} from './Interface'

export interface SourcePage {
  asset_id:string;page:number;width:number;height:number;png:string;source_url:string
  titles:string[];captions:string[];output_ids:string[];evidence_ids:string[]
}

export default function SourcePageGallery({pages,taskId}:{pages:SourcePage[];taskId:string}) {
  useLocale()
  const [selected,setSelected]=useState<SourcePage|null>(null)
  if(!pages.length)return null
  const valid=pages.filter(page=>/^[0-9a-f-]{36}$/i.test(page.asset_id)&&Number.isInteger(page.page)&&page.page>=1&&page.page<=80&&page.png.startsWith('data:image/png;base64,'))
  function picture(page:SourcePage,large=false) {
    const title=page.titles.join(' · '),url=safeExternalUrl(page.source_url)
    return <figure className="source-page" key={`${page.asset_id}-${page.page}`}>
      <figcaption>{title}<small>{t('原文第 {0} 页',page.page)}</small></figcaption>
      {large?<img src={page.png} alt={t('{0}，原文第 {1} 页',title,page.page)} width={page.width} height={page.height}/>:<>
        <a data-app-only href={`#original-${page.asset_id}-${page.page}`} onClick={event=>{event.preventDefault();setSelected(page)}} aria-label={t('放大原文页')}><img src={page.png} alt={t('{0}，原文第 {1} 页',title,page.page)} width={page.width} height={page.height}/></a>
        <img className="source-page-offline" src={page.png} alt={t('{0}，原文第 {1} 页',title,page.page)} width={page.width} height={page.height}/>
      </>}
      <details><summary>{t('图注与来源')}</summary>{page.captions.map((caption,index)=><p key={index}>{caption}</p>)}</details>
      <div className="source-page-links">{url&&<a href={url} target="_blank" rel="noopener noreferrer">{t('查看来源')}</a>}
        <a data-app-only href={`/api/v1/research/${encodeURIComponent(taskId)}/source-assets/${page.asset_id}`} download>{t('下载原始 PDF')}</a>
        <a href={page.png} download={`original-${page.asset_id}-page-${page.page}.png`}>{t('下载PNG')}</a>
      </div>
    </figure>
  }
  return <section className="source-page-gallery" aria-label={t('原文图示')}>
    <h3>{t('原文图示')}</h3><div className="source-page-grid">{valid.map(page=>picture(page))}</div>
    <div data-app-only><Modal open={!!selected} onClose={()=>setSelected(null)} title={t('原文图示')} wide>{selected&&picture(selected,true)}</Modal></div>
    <style>{`.source-page-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:20px}.source-page{min-width:0;margin:0}.source-page figcaption{line-height:1.5;overflow-wrap:anywhere}.source-page small{display:block;font-weight:400;opacity:.7;margin:6px 0 12px}.source-page img{display:block;width:100%;height:auto;max-height:640px;object-fit:contain;background:#fff}.source-page-links{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;margin-top:12px}.source-page .source-page-offline{display:none}.source-page details{font-size:13px} @media print{.source-page a[data-app-only]{display:none!important}.source-page .source-page-offline{display:block!important}.source-page-grid{display:block}.source-page{break-inside:avoid;margin:18px 0}}`}</style>
  </section>
}
