import { useState } from 'react'
import type { Dispatch, RefObject, SetStateAction, KeyboardEvent } from 'react'
import QueryUnderstandingPanel, { UnderstandingSummary } from './QueryUnderstandingPanel'
import type { QueryDraft, UnderstandingSnapshot } from './QueryUnderstandingPanel'
import OrganizationResearchPanel from './OrganizationResearchPanel'
import type { OrganizationDraft } from './OrganizationResearchPanel'
import OrganizationWeightsPanel from './OrganizationWeightsPanel'
import type { WeightSelection } from './OrganizationWeightsPanel'
import ChannelPanel from './ChannelPanel'
import { Icon, Modal, TraceLoader } from './Interface'

interface Props {
  query: string; onQuery: (value:string)=>void; onStart:()=>void; onPreview:()=>void; onBack?:()=>void
  inputRef:RefObject<HTMLTextAreaElement>; onKeyDown:(event:KeyboardEvent<HTMLTextAreaElement>)=>void
  busy:boolean; starting:boolean; outputLength:string; onLength:(value:'short'|'medium'|'long')=>void
  queryDraft:QueryDraft; onDraft:(value:QueryDraft)=>void; organizationDraft:OrganizationDraft; onOrganization:(value:OrganizationDraft)=>void
  onWeights:(value:WeightSelection)=>void; understanding:UnderstandingSnapshot|null; previewCurrent:boolean; error?:string
  skills:Array<{id:string;name:string;enabled:boolean}>; enabled:string[]; disabled:string[]
  setEnabled:Dispatch<SetStateAction<string[]>>; setDisabled:Dispatch<SetStateAction<string[]>>
  useInternal:boolean; onInternal:(value:boolean)=>void; group:string; onGroup:(value:string)=>void
  channels:string[]; onChannels:(value:string[])=>void
}
export default function ResearchComposer(p:Props) {
  const [configuration,setConfiguration]=useState(false),[tab,setTab]=useState('scope')
  return <div className="research-composer">
    {p.onBack&&<button className="composer-back" type="button" onClick={p.onBack}><Icon name="back" size={17}/>首页</button>}
    <div className="composer-heading"><h1>你想研究什么？</h1></div>
    <div className="question-box"><label className="sr-only" htmlFor="research-question">研究问题</label><textarea id="research-question" ref={p.inputRef} value={p.query} onChange={e=>p.onQuery(e.target.value)} onKeyDown={p.onKeyDown}
      placeholder="描述研究对象、时间范围，以及你想弄清楚的问题。" rows={4}/>
      <div className="question-actions"><button type="button" className="composer-config" onClick={()=>setConfiguration(true)}><Icon name="settings" size={18}/>研究配置</button>
        <div className="question-submit"><button type="button" className="btn-ghost" disabled={p.busy||p.query.trim().length<5} onClick={p.onPreview}>预览计划</button><button type="button" className="btn-primary" disabled={p.busy||p.query.trim().length<5} onClick={p.onStart}>{p.starting?<TraceLoader/>:<Icon name="arrow" size={18}/>}开始研究</button></div>
      </div>
    </div>
    <div className="composer-options"><div role="group" aria-label="报告篇幅">{([['short','简报'],['medium','标准'],['long','深入']] as const).map(([value,label])=><button type="button" key={value} aria-pressed={p.outputLength===value} onClick={()=>p.onLength(value)}>{label}</button>)}</div><span>{p.useInternal?'联网 + 内部资料':'联网研究'}</span><span>{p.organizationDraft.enabled?'组织研究':'开放问题'}</span></div>
    {p.error&&<p role="alert" className="composer-error">{p.error}</p>}
    {p.understanding&&<div className="composer-preview">{!p.previewCurrent&&<p className="text-sm text-xmgray-600">配置已修改，请重新预览。</p>}<UnderstandingSummary value={p.understanding}/></div>}
    <div className="composer-examples"><span>试着问</span>{['北京大学近年 AI 系统研究的演进与团队','固态电池的技术路线与关键研究机构','企业与高校在具身智能领域的合作'].map(question=><button key={question} type="button" onClick={()=>{p.onQuery(question);p.inputRef.current?.focus()}}>{question}<Icon name="arrow" size={15}/></button>)}</div>
    <Modal open={configuration} onClose={()=>setConfiguration(false)} title="研究配置" wide>
      <div className="pill-tabs" role="group" aria-label="配置分组">{[['scope','对象与范围'],['methods','方法与交付'],['sources','来源与 Skill']].map(([id,label])=><button type="button" key={id} aria-pressed={tab===id} onClick={()=>setTab(id)}>{label}</button>)}</div>
      <div hidden={tab!=='scope'} className="configuration-group"><OrganizationResearchPanel value={p.organizationDraft} onChange={p.onOrganization}/>{p.organizationDraft.enabled&&<OrganizationWeightsPanel disciplines={p.organizationDraft.disciplines} onChange={p.onWeights}/>}</div>
      <div hidden={tab!=='methods'} className="configuration-group"><QueryUnderstandingPanel value={p.queryDraft} onChange={p.onDraft} organizationEnabled={p.organizationDraft.enabled} skills={p.skills.filter(s=>s.enabled)} preview={p.understanding} onPreview={p.onPreview} canPreview={p.query.trim().length>=5} busy={p.busy}/></div>
      <div hidden={tab!=='sources'} className="configuration-group"><section className="configuration-section"><h3>内部资料</h3><label className="flex items-center gap-3"><input type="checkbox" checked={p.useInternal} onChange={e=>p.onInternal(e.target.checked)}/>加入内部资料检索</label>{p.useInternal&&<label className="block mt-4"><span className="text-sm">资料分组</span><input className="input-xm mt-2" value={p.group} onChange={e=>p.onGroup(e.target.value)} placeholder="留空选择全部分组"/></label>}</section>
        <ChannelPanel selected={p.channels} onChange={p.onChannels}/>
        <section className="configuration-section"><h3>阶段 Skill</h3><div className="skill-selection">{p.skills.filter(s=>s.enabled).map(skill=><div className="skill-selection-row" key={skill.id}><span>{skill.name}</span><div role="group" aria-label={skill.name}>{[['auto','自动'],['enable','启用'],['disable','禁用']].map(([mode,label])=><button key={mode} type="button" aria-pressed={mode===(p.disabled.includes(skill.id)?'disable':p.enabled.includes(skill.id)?'enable':'auto')} onClick={()=>{p.setEnabled(ids=>mode==='enable'?[...new Set([...ids,skill.id])]:ids.filter(id=>id!==skill.id));p.setDisabled(ids=>mode==='disable'?[...new Set([...ids,skill.id])]:ids.filter(id=>id!==skill.id))}}>{label}</button>)}</div></div>)}</div></section>
      </div>
      <div className="configuration-footer"><button className="btn-primary" type="button" onClick={()=>setConfiguration(false)}>完成配置<Icon name="check" size={17}/></button></div>
    </Modal>
  </div>
}
