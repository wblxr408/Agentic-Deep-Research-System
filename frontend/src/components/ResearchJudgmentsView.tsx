import {t,useLocale} from '../i18n'
import RetainedCitations from './RetainedCitations'
import type {RetainedCitation} from './RetainedCitations'

const object=(value:unknown):value is Record<string,unknown>=>Boolean(value&&typeof value==='object'&&!Array.isArray(value))
const rows=(value:unknown)=>Array.isArray(value)?value.filter(object):[]
const text=(value:unknown)=>typeof value==='string'?value:''

export default function ResearchJudgmentsView({value,strategy,sessionId}:{value?:unknown;strategy?:unknown;sessionId?:string|null}) {
  useLocale()
  const judgments=object(value)?rows(value.records):[]
  const intent=object(strategy)?strategy:{}
  if(!judgments.length&&!text(intent.original_question))return null
  return <details className="my-3 rounded-lg border p-3 text-sm">
    <summary className="cursor-pointer font-medium">{t('研究判断与依据')}</summary>
    {text(intent.original_question)&&<div className="my-3"><p className="text-xs text-xmgray-500">{t('原始研究问题')}</p><p>{text(intent.original_question)}</p><p className="mt-1 text-xs text-xmgray-500">{intent.collection_mode==='seeds_only'?t('仅研究指定样本'):t('沿当前来源范围发现研究')}</p></div>}
    {judgments.map((item,index)=>{
      const citations:RetainedCitation[]=rows(item.basis).flatMap((proof,number)=>typeof proof.start==='number'&&typeof proof.end==='number'&&text(proof.evidence_id)?[{
        citation_id:`judgment:${index}:${number}`,source_url:text(proof.source_url),source_title:text(proof.source_title)||t('研究来源'),
        extracted_evidence:text(proof.quote),locator:{evidence_id:text(proof.evidence_id),start:proof.start,end:proof.end,offset_unit:'task_retained_evidence_character'},
      }]:[])
      const choice=object(item.choice)?item.choice:null
      return <article key={text(item.judgment_id)||index} className="my-3 rounded-lg border p-3">
        <h4 className="font-medium">{text(item.conclusion)}</h4>
        <p className="mt-1 text-xs text-xmgray-500">{text(item.question)}</p>
        <dl className="mt-3 space-y-2">{[['observations','观察'],['reasoning','推导'],['significance','研究意义']].map(([key,label])=><div key={key}><dt className="text-xs font-medium">{t(label)}</dt><dd className="mt-1">{text(item[key])}</dd></div>)}</dl>
        {rows(item.alternatives).length>0&&<details className="mt-3"><summary className="cursor-pointer">{t('其他解释与区分依据')}</summary>{rows(item.alternatives).map((alternative,i)=><div key={i} className="mt-2"><p>{text(alternative.explanation)}</p><p className="mt-1 text-xs text-xmgray-500">{text(alternative.distinguishing_observation)}</p></div>)}</details>}
        {choice&&<div className="mt-3 border-t pt-3"><h5 className="font-medium">{t('选择与取舍')}</h5><p className="mt-1">{text(choice.proposed_action)}</p><p className="mt-1">{t('比较选择：')}{text(choice.compared_with)}</p><p className="mt-1">{text(choice.reason)}</p>{Array.isArray(choice.changes_if)&&choice.changes_if.length>0&&<p className="mt-1 text-xs">{t('改变选择的条件：')}{choice.changes_if.filter(value=>typeof value==='string').join('；')}</p>}</div>}
        <RetainedCitations sessionId={sessionId} citations={citations}/>
      </article>
    })}
  </details>
}
