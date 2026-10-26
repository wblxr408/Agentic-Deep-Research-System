import {t,useLocale,uiMessage} from '../i18n'
import {useState} from 'react'
import {useQuery,useQueryClient} from '@tanstack/react-query'
import ReactMarkdown from 'react-markdown'
import {Icon,Modal} from './Interface'
import {CollectionHeader,CollectionEmpty,CollectionTabs,CollectionTags,ActionFooter,collectionRequest,jsonOptions,stageNames,useCollectionAction} from './CollectionUI'

interface Skill {id:string;name:string;slug:string;description:string;enabled:boolean;stages:string[];tags:string[];keywords:string[];allowed_tools:string[];markdown_content?:string|null;prompt?:string;constraints?:string;overview?:string}
interface Draft {name:string;description:string;prompt:string;constraints:string;stages:string[];tools:string[];keywords:string[]}
function patchMetadata(markdown:string,changes:Record<string,unknown>){
 const match=/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/.exec(markdown)
 if(!match)throw new Error(t("请在原文中补全方法名称与用途声明"))
 let header=match[1]
 if(header.trim().startsWith('{'))header=JSON.stringify({...JSON.parse(header),...changes})
 else for(const [key,value] of Object.entries(changes)){
  const lines=header.split(/\r?\n/),start=lines.findIndex(line=>line.startsWith(key+':'))
  const next=key+': '+JSON.stringify(value)
  if(start<0)lines.push(next)
  else{let end=start+1;while(end<lines.length&&(lines[end].trim()===''||/^\s|^#/.test(lines[end])))end++;lines.splice(start,end-start,next)}
  header=lines.join('\n')
 }
 return `---\n${header}\n---\n${markdown.slice(match[0].length)}`
}
function patchSection(markdown:string,title:string,value:string){
 const headings=[...markdown.matchAll(/^#\s+([^\n\r]+)\s*$/gm)],index=headings.findIndex(item=>item[1].trim().toLowerCase()===title.toLowerCase())
 if(index<0)return value.trim()?markdown.trimEnd()+`\n\n# ${title}\n${value.trim()}\n`:markdown
 const current=headings[index],end=headings[index+1]?.index??markdown.length
 return markdown.slice(0,current.index)+`# ${title}\n${value.trim()}\n\n`+markdown.slice(end)
}
function initialDraft(skill?:Skill):Draft{return {name:skill?.name||'',description:skill?.description||'',prompt:skill?.prompt||'',constraints:skill?.constraints||'',stages:skill?.stages||['analyst'],tools:skill?.allowed_tools||[],keywords:skill?.keywords||[]}}
function compose(draft:Draft,original?:Skill){
 if(!original)return `---\nname: ${JSON.stringify(draft.name.trim())}\nslug: method-${crypto.randomUUID()}\ndescription: ${JSON.stringify(draft.description.trim())}\nenabled: true\nstages: ${JSON.stringify(draft.stages)}\nkeywords: ${JSON.stringify(draft.keywords.length?draft.keywords:[draft.name.trim()])}\nallowed_tools: ${JSON.stringify(draft.tools)}\n---\n\n# Prompt\n${draft.prompt.trim()}\n\n# Constraints\n${draft.constraints.trim()}\n`
 const changes:Record<string,unknown>={}
 if(draft.name!==original.name)changes.name=draft.name.trim()
 if(draft.description!==original.description)changes.description=draft.description.trim()
 if(JSON.stringify(draft.stages)!==JSON.stringify(original.stages))changes.stages=draft.stages
 if(JSON.stringify(draft.tools)!==JSON.stringify(original.allowed_tools))changes.allowed_tools=draft.tools
 if(JSON.stringify(draft.keywords)!==JSON.stringify(original.keywords))changes.keywords=draft.keywords
 let markdown=patchMetadata(original.markdown_content||'',changes)
 if(draft.prompt!==(original.prompt||''))markdown=patchSection(markdown,'Prompt',draft.prompt)
 if(draft.constraints!==(original.constraints||''))markdown=patchSection(markdown,'Constraints',draft.constraints)
 return markdown
}
export default function SkillManager(){
  useLocale()

 const client=useQueryClient(),action=useCollectionAction(),[search,setSearch]=useState(''),[state,setState]=useState('all'),[stage,setStage]=useState('all'),[selected,setSelected]=useState<string|null>(null),[editor,setEditor]=useState<Skill|'new'|null>(null),[importing,setImporting]=useState(false),[notice,setNotice]=useState(''),[remove,setRemove]=useState(false)
 const skills=useQuery<{items:Skill[]}>({queryKey:['skills','management'],queryFn:({signal})=>collectionRequest('/api/v1/skills?include_disabled=true',{signal})})
 const detail=useQuery<Skill>({queryKey:['skill-detail',selected],enabled:!!selected,queryFn:({signal})=>collectionRequest('/api/v1/skills/'+selected,{signal})})
 const items=skills.data?.items||[],filtered=items.filter(item=>(state==='all'||item.enabled===(state==='enabled'))&&(stage==='all'||item.stages.includes(stage))&&[item.name,item.description,...item.tags,...item.keywords].join(' ').toLowerCase().includes(search.trim().toLowerCase()))
 const refresh=async()=>{await client.invalidateQueries({queryKey:['skills']});await client.invalidateQueries({queryKey:['skill-detail']})}
 function toggle(skill:Skill){void action.run(async()=>{const full=await collectionRequest('/api/v1/skills/'+skill.id) as Skill;await collectionRequest('/api/v1/skills/'+skill.id,jsonOptions({markdown_content:patchMetadata(full.markdown_content||'',{enabled:!full.enabled})},'PUT'));await refresh();setNotice(t(full.enabled?"已停用「{0}」":"已启用「{0}」",full.name))})}
 return <div className="collection-workspace"><CollectionHeader title={t("研究方法")} count={t("{0} 个 Skills", items.length)} action={<><button type="button" className="btn-ghost" onClick={()=>{action.setError('');setImporting(true)}}>{t("导入文件")}</button><button type="button" className="btn-primary" onClick={()=>{action.setError('');setEditor('new')}}><Icon name="plus" size={17}/>{t("新建方法")}</button></>}/>
  {notice&&<div className="collection-notice" role="status">{uiMessage(notice)}<button type="button" className="icon-button" aria-label={t("关闭提示")} onClick={()=>setNotice('')}><Icon name="close" size={13}/></button></div>}
  <div className="collection-toolbar"><label className="collection-search"><Icon name="search" size={17}/><input type="search" aria-label={t("搜索方法")} placeholder={t("搜索名称或用途")} value={search} onChange={event=>setSearch(event.target.value)}/></label><select aria-label={t("方法阶段筛选")} value={stage} onChange={event=>setStage(event.target.value)}><option value="all">{t("所有阶段")}</option>{Object.entries(stageNames).map(([id,label])=><option key={id} value={id}>{label}</option>)}</select><select aria-label={t("方法状态筛选")} value={state} onChange={event=>setState(event.target.value)}><option value="all">{t("所有状态")}</option><option value="enabled">{t("已启用")}</option><option value="disabled">{t("已停用")}</option></select></div>
  <p className="collection-results">{skills.isPending?t("正在读取方法…"):t("{0} 个方法", filtered.length)}</p>{skills.error?<CollectionEmpty title={t("暂时无法读取方法")} action={<button type="button" className="btn-ghost" onClick={()=>void skills.refetch()}>{t("重新读取")}</button>}/>:!skills.isPending&&!filtered.length?<CollectionEmpty title={items.length?t("没有符合条件的方法"):t("添加你的第一个研究方法")} action={items.length?<button type="button" className="btn-ghost" onClick={()=>{setSearch('');setState('all');setStage('all')}}>{t("清除筛选")}</button>:<button type="button" className="btn-primary" onClick={()=>setEditor('new')}>{t("新建方法")}</button>}/>:<div className="collection-skill-grid">{filtered.map(skill=><article className="collection-skill-card" key={skill.id}><button type="button" className="collection-skill-main" aria-label={t("查看方法 {0}", skill.name)} onClick={()=>{action.setError('');setRemove(false);setSelected(skill.id)}}><header><span className="collection-skill-icon"><Icon name={skill.stages.includes('render')?'chart':'layers'} size={22}/></span><Icon name="arrow" size={17}/></header><div><h3>{skill.name}</h3><p>{skill.description}</p></div></button><footer className="collection-skill-footer"><div className="collection-tags">{skill.stages.length?skill.stages.slice(0,3).map(id=><span key={id}>{stageNames[id]||t("研究方法")}</span>):<span>{t("自动匹配")}</span>}</div><button type="button" role="switch" aria-label={`${skill.enabled?t("停用"):t("启用")}${skill.name}`} aria-checked={skill.enabled} className="collection-switch" disabled={action.busy} onClick={()=>toggle(skill)}><span/>{skill.enabled?t("已启用"):t("已停用")}</button></footer></article>)}</div>}
  {action.error&&!selected&&<p role="alert" className="collection-danger">{uiMessage(action.error)}</p>}
  <Modal open={!!selected} onClose={()=>{if(!action.busy)setSelected(null)}} title={detail.data?.name||t("研究方法")} wide><div className="collection-dialog">{detail.isPending?<p role="status">{t("读取方法…")}</p>:detail.error?<CollectionEmpty title={t("暂时无法读取方法")} action={<button type="button" className="btn-ghost" onClick={()=>void detail.refetch()}>{t("重新读取")}</button>}/>:detail.data&&<><div className="collection-detail-heading"><p>{detail.data.description}</p><span className="collection-status" data-state={detail.data.enabled?'enabled':'disabled'}>{detail.data.enabled?t("已启用"):t("已停用")}</span></div><div className="collection-detail-actions"><button type="button" className="btn-primary" disabled={action.busy} onClick={()=>{setEditor(detail.data!);setSelected(null)}}>{t("编辑方法")}</button><button type="button" className="btn-ghost" disabled={action.busy} onClick={()=>toggle(detail.data!)}>{detail.data.enabled?t("停用"):t("启用")}</button><button type="button" className="btn-ghost collection-danger" disabled={action.busy} onClick={()=>setRemove(true)}>{t("移除")}</button></div><div className="collection-tags">{detail.data.stages.map(id=><span key={id}>{stageNames[id]||t("研究方法")}</span>)}</div><div className="collection-reading"><ReactMarkdown>{[detail.data.overview,detail.data.prompt,detail.data.constraints&&t("### 执行规则\n{0}", detail.data.constraints)].filter(Boolean).join('\n\n')||t("此方法使用分阶段指令。")}</ReactMarkdown></div><details className="collection-advanced"><summary>{t("查看完整原文")}</summary><pre className="collection-reading">{detail.data.markdown_content}</pre></details>{remove&&<div className="collection-confirm"><span>{t("移除「{0}」？",detail.data.name)}</span><button type="button" className="btn-ghost" disabled={action.busy} onClick={()=>setRemove(false)}>{t("取消")}</button><button type="button" className="btn-secondary collection-danger" disabled={action.busy} onClick={()=>void action.run(async()=>{await collectionRequest('/api/v1/skills/'+selected,{method:'DELETE'});setSelected(null);setRemove(false);await refresh();setNotice(t("已移除方法"))})}>{t("确认移除")}</button></div>}{action.error&&<p role="alert">{uiMessage(action.error)}</p>}</>}</div></Modal>
  <Modal open={!!editor} onClose={()=>{if(!action.busy)setEditor(null)}} title={editor==='new'?t("新建研究方法"):t("编辑研究方法")} wide>{editor&&<SkillEditor key={editor==='new'?'new':editor.id} original={editor==='new'?undefined:editor} action={action} onClose={()=>setEditor(null)} onSaved={async()=>{setEditor(null);await refresh();setNotice(t("已保存研究方法"))}}/>}</Modal>
  <Modal open={importing} onClose={()=>{if(!action.busy)setImporting(false)}} title={t("导入研究方法")}><div className="collection-dialog"><SkillImport action={action} onClose={()=>setImporting(false)} onSaved={async()=>{setImporting(false);await refresh();setNotice(t("已导入研究方法"))}}/></div></Modal>
 </div>
}
function SkillEditor({original,action,onClose,onSaved}:{original?:Skill;action:ReturnType<typeof useCollectionAction>;onClose:()=>void;onSaved:()=>Promise<void>}){
  useLocale()

 const [draft,setDraft]=useState(()=>initialDraft(original)),[raw,setRaw]=useState<string|null>(null),[rawStart,setRawStart]=useState<string|null>(null),[validation,setValidation]=useState('')
 const update=(patch:Partial<Draft>)=>{setDraft({...draft,...patch});setValidation('');action.setError('')}
 async function save(){
  if(raw===null&&(!draft.name.trim()||!draft.description.trim()||!original&&!draft.prompt.trim())){setValidation(t("请填写名称、用途和执行步骤"));return}
  if(raw!==null&&!raw.trim()){setValidation(t("方法原文不能为空"));return}
  await action.run(async()=>{await collectionRequest('/api/v1/skills'+(original?'/'+original.id:''),jsonOptions({markdown_content:raw??compose(draft,original)},original?'PUT':'POST'));await onSaved()})
 }
 return <div className="collection-dialog collection-form"><CollectionTabs value={raw===null?'form':'source'} items={raw===null?{form:t("填写方法"),source:t("编辑原文")}:{source:t("编辑原文")}} disabled={action.busy} onChange={mode=>{if(mode==='source')try{{const text=compose(draft,original);setRaw(text);setRawStart(text)}}catch(error){setValidation(uiMessage((error as Error).message))}}}/>{raw===null?<fieldset disabled={action.busy}><label className="collection-field">{t("方法名称")}<input aria-label={t("方法名称")} maxLength={120} value={draft.name} placeholder={t("例如：论文技术解读")} onChange={event=>update({name:event.target.value})}/></label><label className="collection-field">{t("什么时候使用")}<textarea aria-label={t("方法用途")} rows={2} maxLength={400} value={draft.description} placeholder={t("说明适合解决哪类研究问题")} onChange={event=>update({description:event.target.value})}/></label><div className="collection-field"><span>{t("参与哪些步骤")}</span><div className="collection-checks">{Object.entries(stageNames).map(([id,label])=><label key={id}><input type="checkbox" aria-label={t("参与{0}", label)} checked={draft.stages.includes(id)} onChange={event=>update({stages:event.target.checked?[...draft.stages,id]:draft.stages.filter(key=>key!==id)})}/>{label}</label>)}</div>{!draft.stages.length&&<small>{t("按用途自动匹配")}</small>}</div><CollectionTags label={t("适用话题")} values={draft.keywords} onChange={keywords=>update({keywords})}/>{!draft.keywords.length&&!original&&<p className="collection-note">{t("未填写话题时，按方法名称匹配。")}</p>}<label className="collection-field">{t("执行步骤")}<textarea aria-label={t("方法执行步骤")} rows={6} value={draft.prompt} placeholder={t("写下要完成的步骤、判断依据与输出形式")} onChange={event=>update({prompt:event.target.value})}/></label><details className="collection-advanced"><summary>{t("规则与工具")}</summary><div><label className="collection-field">{t("执行规则")}<textarea aria-label={t("方法执行规则")} rows={3} value={draft.constraints} onChange={event=>update({constraints:event.target.value})}/></label><div className="collection-checks">{Object.entries({search:t("搜索"),browser:t("网页阅读"),rag:t("内部资料"),mcp:t("外部工具")}).map(([id,label])=><label key={id}><input type="checkbox" checked={draft.tools.includes(id)} onChange={event=>update({tools:event.target.checked?[...draft.tools,id]:draft.tools.filter(tool=>tool!==id)})}/>{label}</label>)}</div></div></details></fieldset>:<><label className="collection-field">{t("方法原文")}<textarea className="collection-code" aria-label={t("方法原文")} rows={16} disabled={action.busy} value={raw} onChange={event=>{setRaw(event.target.value);setValidation('');action.setError('')}}/></label><button type="button" className="btn-ghost" disabled={action.busy} onClick={()=>{setRaw(null);setValidation('');action.setError('')}}>{t("放弃原文修改，返回表单")}</button></>}<ActionFooter busy={action.busy} error={validation||action.error} onCancel={onClose} label={t("保存方法")} disabled={!!original&&JSON.stringify(draft)===JSON.stringify(initialDraft(original))&&(raw===null||raw===rawStart)} onSave={()=>void save()}/></div>
}
function SkillImport({action,onClose,onSaved}:{action:ReturnType<typeof useCollectionAction>;onClose:()=>void;onSaved:()=>Promise<void>}){
  useLocale()

 const [file,setFile]=useState<File|null>(null)
 return <div className="collection-form"><label className="collection-drop"><Icon name="source" size={28}/><strong>{file?.name||t("选择方法文件")}</strong><span>{t("Markdown · 最多 256 KB")}</span><input type="file" aria-label={t("导入方法文件")} accept=".md" disabled={action.busy} onChange={event=>{setFile(event.target.files?.[0]||null);action.setError('')}}/></label><ActionFooter busy={action.busy} error={uiMessage(action.error)} onCancel={onClose} disabled={!file} label={t("导入方法")} onSave={()=>void action.run(async()=>{if(!file||!file.name.toLowerCase().endsWith('.md')||file.size>262144)throw new Error(t("请选择 256 KB 以内的 Markdown 文件"));const form=new FormData();form.append('file',file);await collectionRequest('/api/v1/skills/upload',{method:'POST',body:form});await onSaved()})}/></div>
}
