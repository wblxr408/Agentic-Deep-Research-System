import {useState} from 'react'
import type {RefObject,KeyboardEvent} from 'react'
import {UnderstandingSummary} from './QueryUnderstandingPanel'
import type {UnderstandingSnapshot} from './QueryUnderstandingPanel'
import {Icon,Modal,TraceLoader} from './Interface'
import ResearchOptionsEditor from './ResearchOptionsEditor'
import type {ChoiceSection} from './ResearchOptionsEditor'
import type {ResearchSetup} from './researchSetup'
import {setupSummary} from './researchSetup'
import '../research-choices.css'

interface Props {
  value:ResearchSetup;onChange:(value:ResearchSetup)=>void;onStart:()=>void;onPreview:()=>void;onBack?:()=>void
  inputRef:RefObject<HTMLTextAreaElement>;onKeyDown?:(event:KeyboardEvent<HTMLTextAreaElement>)=>void
  busy:boolean;starting:boolean;understanding:UnderstandingSnapshot|null;previewCurrent:boolean;error?:string
  skills:Array<{id:string;name:string;enabled:boolean;stages?:string[];agent_hints?:Record<string,string|null>}>;restart?:boolean
}
export default function ResearchComposer(p:Props) {
  const [editing,setEditing]=useState<ResearchSetup|null>(null),[section,setSection]=useState<ChoiceSection>('focus')
  const summary=setupSummary(p.value)
  const open=(next:ChoiceSection)=>{if(p.starting)return;setSection(next);setEditing(structuredClone(p.value))}
  return <div className={`research-composer ${p.restart?'research-composer--restart':''}`}>
    {p.onBack&&<button className="composer-back" type="button" onClick={p.onBack}><Icon name="back" size={17}/>首页</button>}
    <div className="composer-heading"><h1>{p.restart?'重新安排这项研究':'你想研究什么？'}</h1></div>
    <div className="question-box"><label className="sr-only" htmlFor={p.restart?'restart-question':'research-question'}>研究问题</label><textarea id={p.restart?'restart-question':'research-question'} ref={p.inputRef} disabled={p.starting} value={p.value.query} onChange={event=>p.onChange({...p.value,query:event.target.value})} onKeyDown={p.onKeyDown} placeholder="写下你想弄清楚的问题。" rows={4}/>
      <div className="question-actions"><button type="button" className="composer-config" disabled={p.starting} onClick={()=>open('focus')}><Icon name="settings" size={18}/>研究选项</button><div className="question-submit"><button type="button" className="btn-ghost" disabled={p.busy||p.value.query.trim().length<5} onClick={p.onPreview}>{p.busy&&!p.starting?'预览中…':'预览计划'}</button><button type="button" className="btn-primary" disabled={p.busy||p.value.query.trim().length<5||!!(p.restart&&(!p.previewCurrent||!p.understanding?.ready))} onClick={p.onStart}>{p.starting?<TraceLoader/>:<Icon name="arrow" size={18}/>} {p.restart?'创建新研究':'开始研究'}</button></div></div>
    </div>
    <div className="research-quick-choices" role="group" aria-label="常用研究选择">{([{id:'focus',label:'研究深度',value:summary.depth,icon:'layers'},{id:'scope',label:'研究范围',value:summary.scope,icon:'search'},{id:'report',label:'报告样式',value:summary.report,icon:'chart'}] as const).map(item=><button key={item.id} type="button" disabled={p.starting} aria-label={item.label+'：'+item.value} onClick={()=>open(item.id)}><Icon name={item.icon} size={17}/><span><small>{item.label}</small><strong>{item.value}</strong></span><Icon name="chevron" size={14}/></button>)}</div>
    <div className="research-choice-summary"><button type="button" onClick={()=>open('sources')}><Icon name="book" size={14}/>{summary.sources}</button>{summary.time!=='按问题确定'&&<button type="button" onClick={()=>open('scope')}>{summary.time}</button>}{p.value.queryDraft.constraints&&<button type="button" onClick={()=>open('focus')}>已补充研究重点</button>}</div>
    {p.error&&<p role="alert" className="composer-error">{p.error}</p>}
    {p.understanding&&<div className="composer-preview">{p.previewCurrent?<><UnderstandingSummary value={p.understanding}/>{!p.value.organizationDraft.enabled&&!!p.understanding.context_candidates?.length&&<div className="choice-reference-objects"><span>你指的是哪些对象？</span>{p.understanding.context_candidates.map(item=><label key={item.entity_id}><input type="checkbox" checked={p.value.queryDraft.referenceIds.includes(item.entity_id)} onChange={event=>p.onChange({...p.value,queryDraft:{...p.value.queryDraft,referenceIds:event.target.checked?[...p.value.queryDraft.referenceIds,item.entity_id]:p.value.queryDraft.referenceIds.filter(id=>id!==item.entity_id)}})}/>{item.name}</label>)}</div>}</>:<p className="choice-preview-stale">{p.busy?'正在更新计划…':'选择已更新，可重新预览。'}</p>}</div>}
    {!p.restart&&!p.value.query&&<div className="composer-examples"><span>试着问</span>{['北京大学近年 AI 系统研究的演进与团队','固态电池的技术路线与关键研究机构','企业与高校在具身智能领域的合作'].map(question=><button key={question} type="button" onClick={()=>{p.onChange({...p.value,query:question});p.inputRef.current?.focus()}}>{question}<Icon name="arrow" size={15}/></button>)}</div>}
    <Modal open={!!editing} onClose={()=>setEditing(null)} title="这次怎样研究" wide>{editing&&<ResearchOptionsEditor key={section} initial={section} value={editing} onChange={setEditing} skills={p.skills} onCancel={()=>setEditing(null)} onApply={()=>{p.onChange(editing);setEditing(null)}}/>}</Modal>
  </div>
}
