import {useRef,useState} from 'react'
import {useQuery,useQueryClient} from '@tanstack/react-query'
import {t,uiDefinition,uiMessage,useLocale} from '../i18n'
import {collectionRequest,jsonOptions} from './CollectionUI'

interface Block {block_id:string;kind:string;raw_text?:string}
interface Candidate {candidate_id:string;occurrences:Array<{page:number;text:string}>;total_pages?:number;truncated?:boolean}
interface Structure {blocks:Block[];cleaning?:{repeated_page_margin_candidates?:Candidate[]}}
interface Source {id:string;name:string;group_name:string;status:string;is_current?:boolean|null}
interface ProcessingResult {original?:string;replacement?:string;reason?:string;relation?:string;explanation?:string}
interface Operation {operation_id:string;kind:string;status:string;parse_version:string;lifecycle_revision:number;
  input:{primary?:{block_id:string;start:number;end:number;partial_block:boolean};secondary?:{source_id:string;block_id:string}|null};
  result:ProcessingResult|null;error_category:string|null;usage:{status:string;total_tokens?:number}|null;model_name:string}
const states:Record<string,string>=uiDefinition({preparing:'准备中',running:'正在处理',completed:'已完成',failed:'处理未完成',canceled:'已取消',interrupted:'处理中断'})
const relations:Record<string,string>=uiDefinition({equivalent:'内容相近',overlapping:'部分重叠',different:'内容不同',uncertain:'无法判断'})
const errors:Record<string,string>=uiDefinition({processing_source_version_changed:'资料版本已变化，请重新选择',processing_context_changed:'资料或模型配置已变化，本次结果未保存',
  processing_secondary_no_longer_available:'对照资料已变化或不可用',processing_original_file_mismatch:'所选文件与这份资料的原始版本不一致',
  processing_block_not_available:'所选片段不可用',processing_block_invalid:'片段位置已变化',processing_distinct_blocks_required:'请选择两个不同的片段',
  processing_model_invalid_response:'模型未返回可读取的结果',processing_model_request_rejected:'模型拒绝了本次请求',
  processing_model_authentication_failed:'模型凭据未通过验证',processing_model_busy:'模型暂时繁忙',processing_model_response_unknown:'模型响应未确认',
  processing_personal_model_required:'请先配置自己的模型',processing_model_private_scope_denied:'当前模型未开放内部资料处理',
  processing_model_configuration_invalid:'模型连接配置无效',
  processing_data_class_not_allowed:'资料包含受限内容，无法发送给当前模型',processing_sensitive_urls_not_allowed:'片段包含受限链接，请先处理链接',
  processing_source_busy:'这份资料正在处理中',processing_active_limit:'已有其他资料正在处理',processing_history_limit:'处理记录已达到上限',
  processing_model_configuration_changed:'模型配置已变化，请重新操作',processing_request_conflict:'操作内容已变化，请重新提交',
  parsing_version_not_available:'资料版本已变化，请重新选择',source_lifecycle_revision_conflict:'资料已变化，请重新读取',
  cleaning_candidate_location_changed:'候选位置已变化，请重新读取',revision_has_no_text_change:'没有需要保存的改动'})
const explain=(code:string)=>errors[code]||t('处理未完成')

export default function DocumentTextPanel({sourceId,parseVersion,lifecycleRevision,structure,onChanged}:{sourceId:string;parseVersion:string;
  lifecycleRevision:number;structure:Structure;onChanged?:()=>Promise<void>}){
  const locale=useLocale(),client=useQueryClient(),[kind,setKind]=useState<'cleaning'|'semantic_comparison'>('cleaning'),[block,setBlock]=useState(''),
    [otherSource,setOtherSource]=useState(sourceId),[otherBlock,setOtherBlock]=useState(''),[busy,setBusy]=useState(''),[error,setError]=useState(''),
    [notice,setNotice]=useState(''),[expanded,setExpanded]=useState<string|null>(null),[edits,setEdits]=useState<Record<string,string>>({})
  const ids=useRef<Record<string,string>>({}),guard=useRef(false)
  const operations=useQuery<{items:Operation[]}>({queryKey:['document-processing',sourceId],queryFn:({signal})=>collectionRequest(`/api/v1/documents/sources/${sourceId}/processing`,{signal}),
    refetchInterval:value=>busy==='start'||value.state.data?.items.some(item=>['preparing','running'].includes(item.status))?2000:false})
  const sources=useQuery<{items:Source[]}>({queryKey:['document-sources','processing'],enabled:kind==='semantic_comparison',
    queryFn:({signal})=>collectionRequest('/api/v1/documents/sources?summary=true',{signal})})
  const other=useQuery<{parse_version_id:string|null;structure:Structure|null}>({queryKey:['document-parsing',otherSource],
    enabled:kind==='semantic_comparison'&&otherSource!==sourceId,queryFn:({signal})=>collectionRequest(`/api/v1/documents/sources/${otherSource}/parsing`,{signal})})
  const otherStructure=otherSource===sourceId?structure:other.data?.structure,otherVersion=otherSource===sourceId?parseVersion:other.data?.parse_version_id
  const active=operations.data?.items.some(item=>['preparing','running'].includes(item.status))||false
  const reset=(key:string)=>{delete ids.current[key]}
  async function perform(key:string,work:(id:string)=>Promise<unknown>){
    if(guard.current)return null
    guard.current=true;setBusy(key);setError('');setNotice('');ids.current[key]??=crypto.randomUUID()
    try{const result=await work(ids.current[key]);reset(key);await client.invalidateQueries({queryKey:['document-processing',sourceId]});return result}
    catch(problem){setError(explain(problem instanceof Error?problem.message:''));await client.invalidateQueries({queryKey:['document-processing',sourceId]});return null}
    finally{guard.current=false;setBusy('')}
  }
  async function start(){
    if(!block||kind==='semantic_comparison'&&(!otherBlock||!otherVersion))return
    const result=await perform('start',request_id=>collectionRequest(`/api/v1/documents/sources/${sourceId}/processing/text`,jsonOptions({request_id,
      parse_version_id:parseVersion,kind,block_id:block,language:locale,...(kind==='semantic_comparison'?{secondary_source_id:otherSource,
        secondary_parse_version:otherVersion,secondary_block_id:otherBlock}:{})}))) as Operation|null
    if(result)setExpanded(result.operation_id)
  }
  async function apply(item:Operation){
    const primary=item.input.primary,replacement=edits[item.operation_id]??item.result?.replacement
    if(!primary||!replacement?.trim())return
    const result=await perform(`apply:${item.operation_id}`,request_id=>collectionRequest(`/api/v1/documents/sources/${sourceId}/versions`,jsonOptions({request_id,
      expected_parse_version:item.parse_version,expected_revision:item.lifecycle_revision,reason:`model_cleaning:${item.operation_id}`,mode:'patch',
      start:primary.start,end:primary.end,text:replacement,format:'txt',publish:true})))
    if(result){setNotice(t('已生成新的资料版本'));await onChanged?.()}
  }
  async function remove(candidate:Candidate){
    const result=await perform(`margin:${candidate.candidate_id}`,request_id=>collectionRequest(`/api/v1/documents/sources/${sourceId}/parsing/remove-repeated-margin`,jsonOptions({
      request_id,expected_parse_version:parseVersion,expected_revision:lifecycleRevision,candidate_id:candidate.candidate_id})))
    if(result){setNotice(t('已生成新的资料版本'));await onChanged?.()}
  }
  async function cancel(item:Operation){
    try{await collectionRequest(`/api/v1/documents/sources/${sourceId}/processing/${item.operation_id}/cancel`,jsonOptions({}));await client.invalidateQueries({queryKey:['document-processing',sourceId]})}
    catch{setError(t('暂时无法完成，请重试'))}
  }
  const blockOptions=(items:Block[])=>items.map(item=><option key={item.block_id} value={item.block_id}>{item.block_id} · {item.kind} · {(item.raw_text||'').replace(/\s+/g,' ').slice(0,70)}</option>)
  return <section className="document-visual-panel" aria-label={t('清洗与相似内容')}>
    <div className="document-visual-header"><div><h5>{t('清洗与相似内容')}</h5><p>{t('查看重复页边内容，或让模型提出文字建议。')}</p></div></div>
    {!!structure.cleaning?.repeated_page_margin_candidates?.length&&<details><summary>{t('重复页边候选')} · {structure.cleaning.repeated_page_margin_candidates.length}</summary>
      {structure.cleaning.repeated_page_margin_candidates.map(candidate=><div className="document-visual-candidate" key={candidate.candidate_id}><p>{candidate.occurrences[0]?.text} · {candidate.truncated?t('前 {0} / {1} 个页面',candidate.occurrences.length,candidate.total_pages):t('{0} 个页面',candidate.occurrences.length)}</p><button type="button" className="btn-ghost" disabled={!!busy} onClick={()=>void remove(candidate)}>{t('移除并生成新版本')}</button></div>)}</details>}
    <div className="document-visual-form"><label className="collection-field">{t('处理方式')}<select value={kind} disabled={!!busy} onChange={event=>{setKind(event.target.value as typeof kind);setOtherBlock('');reset('start')}}><option value="cleaning">{t('文字修复建议')}</option><option value="semantic_comparison">{t('比较相似内容')}</option></select></label>
      <label className="collection-field">{t('选择原文片段')}<select value={block} disabled={!!busy} onChange={event=>{setBlock(event.target.value);reset('start')}}><option value="">{t('请选择')}</option>{blockOptions(structure.blocks)}</select></label></div>
    {kind==='semantic_comparison'&&<div className="document-visual-form"><label className="collection-field">{t('对照资料')}<select value={otherSource} disabled={!!busy} onChange={event=>{setOtherSource(event.target.value);setOtherBlock('');reset('start')}}><option value={sourceId}>{t('当前资料')}</option>{sources.data?.items.filter(item=>item.id!==sourceId&&item.status==='active'&&item.is_current!==false).map(item=><option key={item.id} value={item.id}>{item.name} · {item.group_name}</option>)}</select></label>
      <label className="collection-field">{t('对照片段')}<select value={otherBlock} disabled={!!busy||!otherStructure} onChange={event=>{setOtherBlock(event.target.value);reset('start')}}><option value="">{t('请选择')}</option>{blockOptions(otherStructure?.blocks||[])}</select></label></div>}
    <div><button type="button" className="btn-secondary" disabled={!!busy||active||!block||kind==='semantic_comparison'&&(!otherBlock||!otherVersion)} onClick={()=>void start()}>{busy==='start'?t('正在处理…'):t('发送给模型')}</button></div>
    {error&&<p role="alert">{uiMessage(error)}</p>}{notice&&<p role="status">{notice}</p>}
    {!!operations.data?.items.length&&<div className="document-visual-history">{operations.data.items.filter(item=>['cleaning','semantic_comparison'].includes(item.kind)).map(item=><article key={item.operation_id}>
      <div className="document-visual-row"><button type="button" className="btn-ghost" onClick={()=>setExpanded(expanded===item.operation_id?null:item.operation_id)}>{item.kind==='cleaning'?t('文字修复建议'):t('比较相似内容')} · {states[item.status]||item.status}</button><span>{item.model_name}</span>{['preparing','running'].includes(item.status)&&<button type="button" className="btn-ghost" onClick={()=>void cancel(item)}>{t('取消处理')}</button>}</div>
      {item.error_category&&<p>{explain(item.error_category)}</p>}{item.usage&&<p>{item.usage.status==='reported'?t('实际用量 {0} Token',item.usage.total_tokens):t('用量待确认')}</p>}
      {expanded===item.operation_id&&item.result&&(item.kind==='cleaning'?<div className="document-visual-result"><section><strong>{t('原文')}</strong><p>{item.result.original}</p></section><label className="collection-field">{t('修复建议')}<textarea value={edits[item.operation_id]??item.result.replacement??''} onChange={event=>{setEdits({...edits,[item.operation_id]:event.target.value});reset(`apply:${item.operation_id}`)}}/></label>
        {item.result.reason&&<p>{item.result.reason}</p>}{item.input.primary?.partial_block&&<p>{t('仅处理了所选片段的开头部分')}</p>}<button type="button" className="btn-secondary" disabled={!!busy||!(edits[item.operation_id]??item.result.replacement)?.trim()||(edits[item.operation_id]??item.result.replacement)===item.result.original} onClick={()=>void apply(item)}>{t('应用并生成新版本')}</button></div>:
        <div className="document-visual-result"><strong>{relations[item.result.relation||'']||t('无法判断')}</strong><p>{item.result.explanation}</p><p>{t('两个来源会分别保留。')}</p></div>)}
    </article>)}</div>}
  </section>
}
