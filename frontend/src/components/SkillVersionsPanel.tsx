import {useState} from 'react'
import {useInfiniteQuery,useQuery,useQueryClient} from '@tanstack/react-query'
import {localeCode,t,uiMessage,useLocale} from '../i18n'
import {collectionRequest,jsonOptions,useCollectionAction} from './CollectionUI'

interface Difference {text:string;truncated:boolean}
interface DefaultStatus {current_version:number;bundle_slug:string|null;source_available:boolean;linked:boolean;provenance:string|null;base_hash:string|null;target_hash:string|null;base_release:string|null;target_release:string|null;update_available:boolean;personal_diff:Difference|null;default_diff:Difference|null;conflicts:Array<{start_line:number;end_line:number}>;merge_error:string|null}
interface HistoryPage {current_version:number;items:Array<{version:number;created_at:string;current:boolean}>;next_before:number|null}
interface VersionText {version:number;markdown_content:string;created_at:string}

function DifferenceView({title,difference}:{title:string;difference:Difference|null}){
 if(!difference)return null
 return <details className="skill-version-difference"><summary>{title}</summary>{difference.text?<pre>{difference.text}</pre>:!difference.truncated&&<p>{t('没有内容变化')}</p>}{difference.truncated&&<small>{t('差异较长，仅显示前一部分。')}</small>}</details>
}

export default function SkillVersionsPanel({skillId,onChanged,action}:{skillId:string;onChanged:()=>Promise<void>;action:ReturnType<typeof useCollectionAction>}){
 useLocale()
 const client=useQueryClient(),[view,setView]=useState<number|null>(null),[confirm,setConfirm]=useState<'associate'|'restore'|null>(null),[notice,setNotice]=useState(''),[showDefault,setShowDefault]=useState(false)
 const base=`/api/v1/skills/${encodeURIComponent(skillId)}`
 const status=useQuery<DefaultStatus>({queryKey:['skill-default-update',skillId],queryFn:({signal})=>collectionRequest(`${base}/default-update`,{signal})})
 const history=useInfiniteQuery<HistoryPage>({queryKey:['skill-versions',skillId],initialPageParam:undefined as number|undefined,
  queryFn:({pageParam,signal})=>collectionRequest(`${base}/versions${typeof pageParam==='number'?`?before=${pageParam}`:''}`,{signal}),
  getNextPageParam:last=>last.next_before??undefined})
 const version=useQuery<VersionText>({queryKey:['skill-version',skillId,view],enabled:view!==null,
  queryFn:({signal})=>collectionRequest(`${base}/versions/${view}`,{signal})})
 const defaultSource=useQuery<{markdown_content:string}>({queryKey:['skill-default-source',skillId],enabled:showDefault,
  queryFn:({signal})=>collectionRequest(`${base}/default-source`,{signal})})
 const data=status.data,needsAssociation=!!data?.source_available&&(!data.linked||data.provenance==='unverified')
 async function reload(){await Promise.all([client.invalidateQueries({queryKey:['skill-default-update',skillId]}),client.invalidateQueries({queryKey:['skill-versions',skillId]}),client.invalidateQueries({queryKey:['skill-version',skillId]})]);await onChanged()}
 function associate(){if(!data?.target_hash||!data.bundle_slug)return;void action.run(async()=>{
  await collectionRequest(`${base}/default-association`,jsonOptions({expected_version:data.current_version,target_hash:data.target_hash,bundle_slug:data.bundle_slug}))
  setConfirm(null);setNotice(t('已关联默认来源'));await reload()
 })}
 function upgrade(){if(!data?.target_hash||!data.base_hash)return;void action.run(async()=>{
  const result=await collectionRequest(`${base}/default-update`,jsonOptions({expected_version:data.current_version,base_hash:data.base_hash,target_hash:data.target_hash})) as {conflicts:unknown[]}
  setNotice(result.conflicts.length?t('已更新，保留了 {0} 处个人改动。',result.conflicts.length):t('已更新默认方法'));await reload()
 })}
 function restore(){if(view===null||!data)return;void action.run(async()=>{
  await collectionRequest(`${base}/versions/${view}/restore`,jsonOptions({expected_version:data.current_version}))
  setConfirm(null);setView(null);setNotice(t('已恢复为新版本'));await reload()
 })}
 return <section className="skill-versions" aria-label={t('版本与更新')}>
  <div className="skill-versions-heading"><div><h3>{t('版本与更新')}</h3>{data&&<p>{t('当前版本 {0}',`v${data.current_version}`)}{data.target_release&&<> · {t('随附版本 {0}',data.target_release)}</>}</p>}</div>
   {data?.bundle_slug&&<span className="collection-status">{!data.source_available?t('当前版本未提供默认来源'):needsAssociation?t('来源待确认'):data.update_available?t('有默认更新'):t('默认已是最新')}</span>}</div>
  {notice&&<p className="skill-version-notice" role="status">{uiMessage(notice)}</p>}
  {status.isPending?<p className="collection-help">{t('正在读取版本…')}</p>:status.error?<button type="button" className="btn-ghost" onClick={()=>void status.refetch()}>{t('重新读取')}</button>:data&&<>
   {needsAssociation?<><p className="collection-help">{t('发现对应的默认方法。先对照内容，再决定是否关联。')}</p><DifferenceView title={t('对照当前内容与默认内容')} difference={data.default_diff}/>
    {confirm==='associate'?<div className="collection-confirm"><span>{t('以当前默认内容作为以后更新的对照基线，保留你的方法内容。')}</span><button type="button" className="btn-ghost" disabled={action.busy} onClick={()=>setConfirm(null)}>{t('取消')}</button><button type="button" className="btn-secondary" disabled={action.busy} onClick={associate}>{t('确认关联')}</button></div>:<button type="button" className="btn-ghost" disabled={action.busy} onClick={()=>setConfirm('associate')}>{t('关联默认来源')}</button>}</>:
   data.bundle_slug?<><DifferenceView title={t('我的修改')} difference={data.personal_diff}/><DifferenceView title={t('默认版本变化')} difference={data.default_diff}/>
    {data.conflicts.length>0&&<><p className="collection-help">{t('有 {0} 处内容同时被修改，更新时保留你的内容。',data.conflicts.length)}</p><details className="skill-version-difference"><summary>{t('查看保留的位置')}</summary><ul>{data.conflicts.map((item,index)=><li key={`${item.start_line}-${index}`}>{t('原版本第 {0}—{1} 行',item.start_line,item.end_line)}</li>)}</ul></details></>}
    {data.update_available&&<button type="button" className="btn-secondary" disabled={action.busy||!!data.merge_error} onClick={upgrade}>{t('更新并保留我的修改')}</button>}</>:<p className="collection-help">{t('这是你的个人方法。')}</p>}
   {data.merge_error&&<p className="collection-danger">{t('无法自动合并，请对照差异后手动编辑。')}</p>}
   {data.source_available&&<details className="skill-version-difference" onToggle={event=>setShowDefault(event.currentTarget.open)}><summary>{t('查看默认原文')}</summary>{defaultSource.isPending?<p>{t('正在读取版本…')}</p>:defaultSource.error?<button type="button" className="btn-ghost" onClick={()=>void defaultSource.refetch()}>{t('重新读取')}</button>:<pre>{defaultSource.data?.markdown_content}</pre>}</details>}
  </>}
  <div className="skill-version-history"><h4>{t('历史版本')}</h4>{history.isPending?<p className="collection-help">{t('正在读取版本…')}</p>:history.error?<button type="button" className="btn-ghost" onClick={()=>void history.refetch()}>{t('重新读取')}</button>:<>
   <div className="skill-version-list">{history.data?.pages.flatMap(page=>page.items).map(item=><button type="button" key={item.version} className={view===item.version?'is-selected':''} aria-pressed={view===item.version} onClick={()=>{setView(item.version);setConfirm(null)}}><span>v{item.version}{item.current&&<em>{t('当前')}</em>}</span><time>{new Date(item.created_at).toLocaleDateString(localeCode())}</time></button>)}</div>
   {history.hasNextPage&&<button type="button" className="btn-ghost" disabled={history.isFetchingNextPage} onClick={()=>void history.fetchNextPage()}>{t('显示更早版本')}</button>}
  </>}</div>
  {view!==null&&<div className="skill-version-preview"><h4>{t('版本 {0}',`v${view}`)}</h4>{version.isPending?<p>{t('正在读取版本…')}</p>:version.error?<button type="button" className="btn-ghost" onClick={()=>void version.refetch()}>{t('重新读取')}</button>:<pre>{version.data?.markdown_content}</pre>}
   {view!==data?.current_version&&(confirm==='restore'?<div className="collection-confirm"><span>{t('恢复会生成新版本，保留当前启停状态。')}</span><button type="button" className="btn-ghost" disabled={action.busy} onClick={()=>setConfirm(null)}>{t('取消')}</button><button type="button" className="btn-secondary" disabled={action.busy} onClick={restore}>{t('确认恢复')}</button></div>:<button type="button" className="btn-ghost" disabled={action.busy||!version.data||!data} onClick={()=>setConfirm('restore')}>{t('恢复此版本')}</button>)}
  </div>}
  {action.error&&<div role="alert"><p className="collection-danger">{uiMessage(action.error)}</p><button type="button" className="btn-ghost" disabled={action.busy} onClick={()=>{action.setError('');void reload()}}>{t('重新读取')}</button></div>}
 </section>
}
