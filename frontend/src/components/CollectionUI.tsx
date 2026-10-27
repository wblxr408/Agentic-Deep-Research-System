import {uiDefinition,t,uiMessage,useLocale} from '../i18n'
import {useRef,useState} from 'react'
import type {ReactNode} from 'react'
import {Icon,TraceLoader} from './Interface'
import '../collections.css'

export const stageNames:Record<string,string>=uiDefinition({planner:'规划',search:'搜索',browser:'网页阅读',rag:'内部资料',mcp:'外部工具',analyst:'分析',reflection:'核对',report:'写作',render:'绘图'})
export async function collectionRequest(path:string,options:RequestInit={}) {
  const response=await fetch(path,options),body=await response.json().catch(()=>({}))
  if(!response.ok){
    const detail=body.detail
    const known:Record<string,string>={source_not_found:t("这份资料暂时无法读取"),retention_task_not_owned_or_missing:t("请选择自己的研究链接"),invalid_skill_document:t("请检查方法的阶段、工具和指令内容"),skill_version_conflict:t('方法已更新，请重新读取后再试。'),skill_default_changed:t('默认版本已变化，请重新读取后再试。'),skill_default_missing:t('当前版本未提供默认来源'),skill_default_already_linked:t('方法已关联默认来源，请重新读取。'),skill_version_or_slug_conflict:t('方法名称或版本已变化，请重新读取。'),skill_slug_conflict:t('方法名称标识已被使用。'),skill_frontmatter_scalar_not_editable:t('请调整方法原文中的版本或启停字段。'),skill_merge_too_large:t('方法较长，请对照后手动编辑。'),skill_merge_identity_changed:t('更新会改变方法标识，请手动编辑。'),skill_version_not_found:t('这个版本暂时无法读取。')}
    known.semantic_chunking_unavailable_or_incomplete=t('语义分块需要本地固定版本的编码模型，且全部片段须能完整编码。')
    known.sparse_encoding_unavailable_or_incomplete=t('学习稀疏特征需要已配置的本地模型，且全部片段须能完整编码。')
    known.sparse_feature_budget_exceeded=t('学习稀疏特征超出资料大小限制。')
    known.stemming_feature_budget_exceeded=t('英文词形特征超出资料大小限制。')
    const message=typeof detail==='string'?(known[detail]||(detail.startsWith('invalid_skill_document:')?known.invalid_skill_document:detail)):response.status===422?t("请检查必填项和所选范围"):response.status===403?t("当前账号无法修改这项内容"):t("暂时无法完成，请重试")
    throw new Error(message)
  }
  return body
}
export const jsonOptions=(body:unknown,method='POST'):RequestInit=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
export function useCollectionAction(){
  const lock=useRef(false),[busy,setBusy]=useState(false),[error,setError]=useState('')
  async function run(action:()=>Promise<void>){if(lock.current)return;lock.current=true;setBusy(true);setError('');try{await action()}catch(error){setError(error instanceof Error?uiMessage(error.message):t("暂时无法完成，请重试"))}finally{lock.current=false;setBusy(false)}}
  return {busy,error,setError,run}
}
export function CollectionHeader({title,count,action,children}:{title:string;count:string;action:ReactNode;children?:ReactNode}){
  useLocale()
return <header className="collection-header"><div><span className="collection-eyebrow">{count}</span><h1>{title}</h1>{children}</div><div className="collection-header-actions">{action}</div></header>}
export function CollectionTabs({value,items,onChange,disabled=false}:{value:string;items:Record<string,string>;onChange:(value:string)=>void;disabled?:boolean}){
  useLocale()
return <div className="collection-tabs" role="tablist">{Object.entries(items).map(([id,label])=><button key={id} type="button" role="tab" aria-selected={value===id} tabIndex={value===id?0:-1} disabled={disabled} onClick={()=>onChange(id)} onKeyDown={event=>{const keys=Object.keys(items),index=keys.indexOf(id);let next=index;if(event.key==='ArrowRight')next=(index+1)%keys.length;else if(event.key==='ArrowLeft')next=(index-1+keys.length)%keys.length;else if(event.key==='Home')next=0;else if(event.key==='End')next=keys.length-1;else return;event.preventDefault();onChange(keys[next]);(event.currentTarget.parentElement?.querySelectorAll('button')[next] as HTMLButtonElement)?.focus()}}>{label}</button>)}</div>}
export function CollectionTags({label,values,onChange}:{label:string;values:string[];onChange:(values:string[])=>void}){
  useLocale()

 const [text,setText]=useState('')
 const add=()=>{const next=text.trim();if(next){onChange([...new Set([...values,next])].slice(0,20));setText('')}}
 return <div className="collection-field"><span>{label}</span>{!!values.length&&<div className="collection-tags">{values.map(value=><span key={value}>{value}<button type="button" aria-label={t("移除话题 {0}", value)} onClick={()=>onChange(values.filter(item=>item!==value))}><Icon name="close" size={12}/></button></span>)}</div>}<div className="collection-tag-entry"><input aria-label={t("添加{0}", label)} placeholder={t("填写一个话题后回车")} value={text} disabled={values.length>=20} onChange={event=>setText(event.target.value)} onBlur={add} onKeyDown={event=>{if(event.key==='Enter'){event.preventDefault();add()}}}/><button type="button" className="btn-ghost" onClick={add} disabled={!text.trim()||values.length>=20}>{t("添加")}</button></div></div>
}

export function CollectionEmpty({title,children,action}:{title:string;children?:ReactNode;action?:ReactNode}){
  useLocale()
return <div className="collection-empty"><Icon name="book" size={28}/><h3>{title}</h3>{children&&<p>{children}</p>}{action}</div>}
export function ActionFooter({busy,error,onCancel,label,onSave,disabled=false}:{busy:boolean;error?:string;onCancel:()=>void;label:string;onSave?:()=>void;disabled?:boolean}){
  useLocale()
return <><div className="collection-feedback" aria-live="polite">{error&&<p role="alert">{uiMessage(error)}</p>}</div><footer className="collection-footer"><button type="button" className="btn-ghost" disabled={busy} onClick={onCancel}>{t("取消")}</button>{onSave&&<button type="button" className="btn-primary" disabled={busy||disabled} onClick={onSave}>{busy?<TraceLoader/>:<Icon name="check" size={16}/>} {busy?t("保存中…"):label}</button>}</footer></>}
