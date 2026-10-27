import {useSyncExternalStore} from 'react'
import {english as baseEnglish} from './locales/en'
import {layoutEnglish} from './locales/layout'
import {skillVersionsEnglish} from './locales/skillVersions'
import {skillStagesEnglish} from './locales/skillStages'
import {questionQualityEnglish} from './locales/questionQuality'
import {budgetAllocationEnglish} from './locales/budgetAllocation'
import {accountRecoveryEnglish} from './locales/accountRecovery'
import {collaborationEnglish} from './locales/collaboration'
import {sourceSyncEnglish} from './locales/sourceSync'
import {systemMessages} from './locales/system'
const english:Record<string,string>={...baseEnglish,...layoutEnglish,...skillVersionsEnglish,...skillStagesEnglish,...questionQualityEnglish,...budgetAllocationEnglish,...accountRecoveryEnglish,...collaborationEnglish,...sourceSyncEnglish}
export type Locale='zh'|'en'
const key='deepintel.appearance.v1'
let language:Locale=(()=>{try{return JSON.parse(localStorage.getItem(key)||'{}').language==='en'?'en':'zh'}catch{return 'zh'}})()
const listeners=new Set<()=>void>()
export function setLocale(next:Locale){if(next===language)return;language=next;for(const notify of listeners)notify()}
function subscribe(notify:()=>void){listeners.add(notify);return()=>{listeners.delete(notify)}}
export function useLocale(){return useSyncExternalStore(subscribe,()=>language,()=>language)}
export const joinLabels=(values:readonly string[])=>values.join(language==='en'?', ':'、')
export const localeCode=()=>language==='en'?'en-US':'zh-CN'
const renderedMessages=new Map<string,{source:string;values:unknown[]}>()
const singular:Record<string,string>={sources:'source',actions:'action',subjects:'subject',methods:'method',skills:'skill',items:'item',records:'record',versions:'version',steps:'step',pages:'page',users:'user',documents:'document',columns:'column',sections:'section',components:'component'}
export function t(source:string,...values:unknown[]):string{
 let message=language==='en'?(english[source]??source):source
 if(language==='en'&&Number(values[0])===1)message=message.replace(/^((?:[A-Za-z]+\s+){0,4}\{0\}\s+)(sources|actions|subjects|methods|skills|items|records|versions|steps|pages|users|documents|columns|sections|components)\b/,(all,prefix,noun)=>prefix+singular[noun])
 const result=message.replace(/\{(\d+)\}/g,(_,index:string)=>String(values[Number(index)]??''))
 // Remember message arguments, never reinterpret source names or report content.
 if(values.length&&source!==result){
  if(renderedMessages.size>=1500)renderedMessages.delete(renderedMessages.keys().next().value!)
  renderedMessages.set(result,{source,values})
 }
 return result
}
const proxyCache=new WeakMap<object,object>()
/** Only source-owned UI definitions enter this function; API records never do. */
export function uiDefinition<T>(definition:T):T{
 if(!definition||typeof definition!=='object')return definition
 const old=proxyCache.get(definition as object);if(old)return old as T
 const proxy=new Proxy(definition as object,{get(target,property,receiver){const value=Reflect.get(target,property,receiver);return typeof value==='string'?t(value):value&&typeof value==='object'?uiDefinition(value):value}})
 proxyCache.set(definition as object,proxy);return proxy as T
}
const transportMessages:Record<string,string>={'Failed to fetch':'网络连接失败，请重试。','NetworkError when attempting to fetch resource.':'网络连接失败，请重试。','Network request failed':'网络连接失败，请重试。'}
let reverse:Map<string,string>|undefined
/** Re-render system feedback created before a language switch. Not for API/user content. */
export function uiMessage<T>(message:T):T{
 if(typeof message!=='string')return message
 if(transportMessages[message])return t(transportMessages[message]) as T
 const saved=renderedMessages.get(message)
 if(saved)return t(saved.source,...saved.values) as T
 if(Object.prototype.hasOwnProperty.call(english,message))return t(message) as T
 reverse??=new Map(Object.entries(english).map(([source,target])=>[target,source]))
 const source=reverse.get(message)
 return (source?t(source):message) as T
}

/** Stable source wording for legacy error classification; never display it directly. */
export function messageSource(message:string):string{
 const saved=renderedMessages.get(message)
 if(saved)return saved.source.replace(/\{(\d+)\}/g,(_,index:string)=>String(saved.values[Number(index)]??''))
 reverse??=new Map(Object.entries(english).map(([source,target])=>[target,source]))
 return reverse.get(message)??message
}

const systemSet=new Set(systemMessages)
const systemPatterns=systemMessages.filter(source=>source.includes('{0}')).map(source=>({source,pattern:new RegExp('^'+source.split(/(\{\d+\})/).map(part=>/^\{\d+\}$/.test(part)?'(.*?)':part.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('')+'$','s')}))
/** Only trusted diagnostic wording is localized; arbitrary report/error text is retained. */
export function systemMessage(message:string,blockers:string[]=[]):string{
 if(blockers.length){
  const suffix=' '+blockers.join('；')+'，需要你决定新的范围或额度。'
  if(message.endsWith(suffix))return systemMessage(message.slice(0,-suffix.length))+' '+t('{0}，需要你决定新的范围或额度。',blockers.map(value=>systemMessage(value)).join(language==='en'?'; ':'；'))
 }
 if(systemSet.has(message))return t(message)
 for(const {source,pattern} of systemPatterns){const match=pattern.exec(message);if(match)return t(source,...match.slice(1).map(value=>systemSet.has(value)?t(value):value))}
 return message
}
