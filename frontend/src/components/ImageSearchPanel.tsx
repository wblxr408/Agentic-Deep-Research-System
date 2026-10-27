import {useEffect,useRef,useState} from 'react'
import {t,useLocale} from '../i18n'
import {collectionRequest,jsonOptions} from './CollectionUI'

interface ImageItem {operation_id:string;source_id:string;source_name:string;group_name:string;has_preview:boolean;score?:number;
  selection:{kind:string;page?:number;figure_id?:string}}
interface ImageResults {items:ImageItem[];status?:string;has_more?:boolean;coverage?:{scope_truncated:boolean}}

export default function ImageSearchPanel({groups,selectedGroup,onOpen}:{groups:string[];selectedGroup:string;onOpen:(id:string)=>void}){
  useLocale()
  const [group,setGroup]=useState(selectedGroup||groups[0]||''),[query,setQuery]=useState(''),[result,setResult]=useState<ImageResults|null>(null),
    [busy,setBusy]=useState(false),[error,setError]=useState('')
  const generation=useRef(0)
  useEffect(()=>{if(selectedGroup){generation.current++;setGroup(selectedGroup);setResult(null)}},[selectedGroup])
  useEffect(()=>{if(!group&&groups.length)setGroup(groups[0])},[group,groups])
  function explain(problem:unknown){
    const code=problem instanceof Error?problem.message:''
    const reasons:Record<string,string>={multimodal_configuration_unavailable:'请先配置本地图文模型',image_query_encoding_unavailable:'本地图文模型不可用或查询过长',
      image_search_reference_unavailable:'参考图片已不可用',image_search_timeout:'图片查找超时'}
    return t(reasons[code]||'图片查找暂时不可用')
  }
  async function browse(){
    if(busy||!group)return
    const current=++generation.current;setBusy(true);setError('')
    try{const data=await collectionRequest(`/api/v1/documents/image-features?${new URLSearchParams({group_name:group})}`) as ImageResults;if(current===generation.current)setResult(data)}
    catch(problem){if(current===generation.current)setError(explain(problem))}finally{setBusy(false)}
  }
  async function search(reference?:string){
    if(busy||!group||!reference&&!query.trim())return
    const current=++generation.current;setBusy(true);setError('')
    try{const data=await collectionRequest('/api/v1/documents/image-search',jsonOptions({group_name:group,
      ...(reference?{reference_operation_id:reference}:{query:query.trim()}),limit:20})) as ImageResults;if(current===generation.current)setResult(data)}
    catch(problem){if(current===generation.current)setError(explain(problem))}finally{setBusy(false)}
  }
  return <section className="document-visual-panel" aria-label={t('图片查找')}><div className="document-visual-form">
    <label className="collection-field">{t('资料分组')}<select value={group} onChange={event=>{generation.current++;setGroup(event.target.value);setResult(null)}}><option value="">{t('请选择')}</option>{groups.map(name=><option key={name} value={name}>{name}</option>)}</select></label>
    <label className="collection-field">{t('描述你要找的图片')}<input value={query} maxLength={4000} onChange={event=>setQuery(event.target.value)} onKeyDown={event=>{if(event.key==='Enter')void search()}}/></label>
    <div className="flex flex-wrap gap-2"><button type="button" className="btn-secondary" disabled={busy||!group||!query.trim()} onClick={()=>void search()}>{busy?t('正在查找…'):t('查找图片')}</button><button type="button" className="btn-ghost" disabled={busy||!group} onClick={()=>void browse()}>{t('浏览图片')}</button></div>
    </div>{error&&<p role="alert">{error}</p>}{result&&!result.items.length&&<p>{t(result.status==='no_compatible_images'?'当前分组没有可用的图文特征':'没有匹配的图片')}</p>}
    {result&&<div className="image-search-grid">{result.items.map(item=><article className="image-search-card" key={item.operation_id}>
      {item.has_preview?<img loading="lazy" src={`/api/v1/documents/image-features/${item.operation_id}/preview?${new URLSearchParams({group_name:group})}`} alt={item.source_name}/>:
        <div className="image-search-empty">{t('暂无图片预览')}</div>}
      <strong>{item.source_name}</strong><p>{item.selection.kind==='page'?t('第 {0} 页',item.selection.page):t('内嵌图片 {0}',item.selection.figure_id?.replace('figure:',''))}{typeof item.score==='number'?` · ${item.score.toFixed(3)}`:''}</p>
      <div className="flex flex-wrap gap-2"><button type="button" className="btn-ghost" onClick={()=>onOpen(item.source_id)}>{t('查看资料')}</button><button type="button" className="btn-ghost" disabled={busy} onClick={()=>void search(item.operation_id)}>{t('查找相似图片')}</button></div></article>)}</div>}
    {result&&(result.has_more||result.coverage?.scope_truncated)&&<p>{t('图片结果范围已截取')}</p>}
  </section>
}
