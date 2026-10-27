import {useRef,useState} from 'react'
import {useQuery,useQueryClient} from '@tanstack/react-query'
import {t,uiDefinition,uiMessage,useLocale} from '../i18n'
import {collectionRequest,jsonOptions} from './CollectionUI'

interface Chunk {logical_chunk_id:string;start:number;end:number;title_path:Array<{title:string}>}
interface Entity {name:string;kind:string;start:number;end:number}
interface Relation {subject:string;predicate:string;object:string;evidence:string;start:number;end:number}
interface Operation {operation_id:string;kind:string;status:string;accepted:boolean;input:{primary:{chunk_id:string}};
  result:{entities:Entity[];relations:Relation[];omitted_unanchored_or_invalid:number}|null;model_name:string;
  error_category:string|null;usage:{status:string;total_tokens?:number}|null}
const states:Record<string,string>=uiDefinition({preparing:'准备中',running:'正在处理',completed:'已完成',failed:'处理未完成',canceled:'已取消',interrupted:'处理中断'})
const kinds:Record<string,string>=uiDefinition({person:'人员',organization:'机构',location:'地域',technology:'技术',date:'时间',other:'其他'})
const errors:Record<string,string>=uiDefinition({processing_personal_model_required:'请先配置自己的模型',processing_model_private_scope_denied:'当前模型未开放内部资料处理',
  processing_model_configuration_invalid:'模型连接配置无效',processing_context_changed:'资料或模型配置已变化，本次结果未保存',
  processing_source_version_changed:'资料版本已变化，请重新选择',processing_chunk_version_changed:'片段版本已变化，请重新读取',processing_chunk_not_available:'片段暂时不可用',
  processing_data_class_not_allowed:'资料包含受限内容，无法发送给当前模型',processing_sensitive_urls_not_allowed:'片段包含受限链接，请先处理链接',
  processing_model_request_rejected:'模型拒绝了本次请求',processing_model_invalid_response:'模型未返回可读取的结果',processing_model_busy:'模型暂时繁忙',
  processing_model_authentication_failed:'模型凭据未通过验证',processing_model_response_unknown:'模型响应未确认',processing_source_busy:'这份资料正在处理中',
  processing_active_limit:'已有其他资料正在处理',processing_history_limit:'处理记录已达到上限'})

export default function ChunkEntityPanel({sourceId,parseVersion,profileId,chunks}:{sourceId:string;parseVersion:string;profileId:string;chunks:Chunk[]}){
  const locale=useLocale(),client=useQueryClient(),[chunk,setChunk]=useState(''),[busy,setBusy]=useState(''),[error,setError]=useState(''),[expanded,setExpanded]=useState<string|null>(null)
  const requestId=useRef(crypto.randomUUID()),guard=useRef(false)
  const query=useQuery<{items:Operation[]}>({queryKey:['document-processing',sourceId],queryFn:({signal})=>collectionRequest(`/api/v1/documents/sources/${sourceId}/processing`,{signal}),
    refetchInterval:value=>busy==='start'||value.state.data?.items.some(item=>['preparing','running'].includes(item.status))?2000:false})
  const active=query.data?.items.some(item=>['preparing','running'].includes(item.status))||false
  async function start(){
    if(!chunk||guard.current)return
    guard.current=true;setBusy('start');setError('')
    try{const item=await collectionRequest(`/api/v1/documents/sources/${sourceId}/processing/text`,jsonOptions({request_id:requestId.current,
      parse_version_id:parseVersion,kind:'entity_extraction',chunk_id:chunk,chunk_profile_id:profileId,language:locale})) as Operation
      setExpanded(item.operation_id);requestId.current=crypto.randomUUID();await client.invalidateQueries({queryKey:['document-processing',sourceId]})
    }catch(problem){const code=problem instanceof Error?problem.message:'';setError(errors[code]||t('处理未完成'));await client.invalidateQueries({queryKey:['document-processing',sourceId]})}
    finally{guard.current=false;setBusy('')}
  }
  async function mark(item:Operation){
    if(guard.current)return
    guard.current=true;setBusy(item.operation_id);setError('')
    try{await collectionRequest(`/api/v1/documents/sources/${sourceId}/processing/${item.operation_id}/annotation`,jsonOptions({accepted:!item.accepted}));await client.invalidateQueries({queryKey:['document-processing',sourceId]})}
    catch(problem){const code=problem instanceof Error?problem.message:'';setError(errors[code]||t('处理未完成'))}
    finally{guard.current=false;setBusy('')}
  }
  async function cancel(item:Operation){
    try{await collectionRequest(`/api/v1/documents/sources/${sourceId}/processing/${item.operation_id}/cancel`,jsonOptions({}));await client.invalidateQueries({queryKey:['document-processing',sourceId]})}
    catch{setError(t('暂时无法完成，请重试'))}
  }
  return <section className="document-visual-panel" aria-label={t('实体与关系候选')}>
    <div className="document-visual-header"><div><h5>{t('实体与关系候选')}</h5><p>{t('选择一个片段，让模型识别其中的人、机构、技术与关系。')}</p></div></div>
    <div className="document-visual-form"><label className="collection-field">{t('选择片段')}<select value={chunk} disabled={!!busy} onChange={event=>{setChunk(event.target.value);requestId.current=crypto.randomUUID()}}><option value="">{t('请选择')}</option>{chunks.map((item,index)=><option key={item.logical_chunk_id} value={item.logical_chunk_id}>{t('片段 {0}',index+1)} · {item.title_path.map(part=>part.title).join(' / ')||`${item.start}–${item.end}`}</option>)}</select></label>
      <button type="button" className="btn-secondary" disabled={!chunk||!!busy||active} onClick={()=>void start()}>{busy==='start'?t('正在处理…'):t('识别候选')}</button></div>
    {error&&<p role="alert">{uiMessage(error)}</p>}
    {!!query.data?.items.length&&<div className="document-visual-history">{query.data.items.filter(item=>item.kind==='entity_extraction').map(item=><article key={item.operation_id}>
      <div className="document-visual-row"><button type="button" className="btn-ghost" onClick={()=>setExpanded(expanded===item.operation_id?null:item.operation_id)}>{t('实体与关系候选')} · {states[item.status]||item.status}</button><span>{item.model_name}</span>{['preparing','running'].includes(item.status)&&<button type="button" className="btn-ghost" onClick={()=>void cancel(item)}>{t('取消处理')}</button>}</div>
      {item.error_category&&<p>{errors[item.error_category]||t('处理未完成')}</p>}{item.usage&&<p>{item.usage.status==='reported'?t('实际用量 {0} Token',item.usage.total_tokens):t('用量待确认')}</p>}
      {expanded===item.operation_id&&item.result&&<div className="document-visual-result"><section><strong>{t('识别的实体')}</strong>{item.result.entities.length?<ul>{item.result.entities.map((entity,index)=><li key={index}>{entity.name} · {kinds[entity.kind]||t('其他')}</li>)}</ul>:<p>{t('没有可定位的实体')}</p>}</section>
        {!!item.result.relations.length&&<section><strong>{t('关系候选')}</strong><ul>{item.result.relations.map((relation,index)=><li key={index}>{relation.subject} · {relation.predicate} · {relation.object}<p>{relation.evidence}</p></li>)}</ul></section>}
        {!!item.result.omitted_unanchored_or_invalid&&<p>{t('有 {0} 项未能定位，未加入候选',item.result.omitted_unanchored_or_invalid)}</p>}
        <button type="button" className="btn-secondary" disabled={!!busy} onClick={()=>void mark(item)}>{item.accepted?t('从后续研究移除'):t('用于后续研究')}</button></div>}
    </article>)}</div>}
  </section>
}
