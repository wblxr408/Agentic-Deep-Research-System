import {useRef,useState} from 'react'
import {useQuery,useQueryClient} from '@tanstack/react-query'
import {t,uiDefinition,uiMessage,useLocale} from '../i18n'
import {collectionRequest,jsonOptions} from './CollectionUI'

type Figure=Record<string,unknown>
interface Structure {format:string;pages?:Array<{number:number;start?:number;end?:number}>;figures:Figure[]}
interface Observation {transcription:string;visual_summary:string;layout:string[];chart_observations:string[];uncertainties:string[];image_encoded?:boolean;dimension?:number;text_windows?:Array<{start:number;end:number}>;coverage?:{total_token_windows:number;encoded_text_windows:number;source_text_characters:number;text_characters_considered:number}}
interface Operation {operation_id:string;kind:string;status:string;parse_version:string;lifecycle_revision:number;input:{selection:{kind:string;page?:number;figure_id?:string}};
  result:Observation|null;usage:{status:string;total_tokens?:number}|null;error_category:string|null;model_name:string;created_at:string}
const states:Record<string,string>=uiDefinition({preparing:'准备页面',running:'正在识别',completed:'识别完成',failed:'识别未完成',canceled:'已取消',interrupted:'处理中断'})
const errors:Record<string,string>=uiDefinition({
  processing_personal_model_required:'请先配置自己的模型',processing_model_private_scope_denied:'当前模型未开放内部资料处理',
  processing_model_configuration_invalid:'模型连接配置无效',
  processing_data_class_not_allowed:'资料包含受限内容，无法发送给当前模型',processing_original_file_mismatch:'所选文件与这份资料的原始版本不一致',
  processing_source_version_changed:'资料版本已变化，请重新选择',processing_model_configuration_changed:'模型配置已变化，请重新操作',
  processing_context_changed:'资料或模型配置已变化，本次结果未保存',processing_source_busy:'这份资料正在处理中',
  processing_active_limit:'已有其他资料正在处理',processing_history_limit:'处理记录已达到上限',processing_request_conflict:'操作内容已变化，请重新提交',
  visual_page_not_available:'此页面不在当前解析范围内',visual_embedded_image_unavailable:'无法读取此内嵌图片',
  visual_source_format_unsupported:'当前来源不支持这种图像处理',visual_image_pixel_limit:'页面或图片尺寸超出限制',
  visual_image_size_limit:'图片大小超出限制',visual_render_failed:'页面或图片无法读取',
  visual_model_invalid_response:'模型未返回可读取的结果',processing_model_image_unsupported_or_rejected:'当前模型不支持所选图像或拒绝了请求',
  processing_model_authentication_failed:'模型凭据未通过验证',processing_model_busy:'模型暂时繁忙',
  processing_model_response_unknown:'模型响应未确认',model_response_unknown:'模型响应未确认',
  processing_interrupted_before_dispatch:'处理在发送模型前中断',processing_interrupted:'处理已中断',processing_canceled:'已取消',
  multimodal_configuration_unavailable:'请先配置本地图文模型',multimodal_processing_failed:'图文特征生成未完成',
})
const explain=(value:string|null)=>value?(errors[value]||t('处理未完成')):''

export default function DocumentVisualPanel({sourceId,parseVersion,structure,onChanged}:{sourceId:string;parseVersion:string;structure:Structure;onChanged?:()=>Promise<void>}){
  const locale=useLocale(),client=useQueryClient(),[file,setFile]=useState<File|null>(null),[target,setTarget]=useState(''),
    [detail,setDetail]=useState('low'),[working,setWorking]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),
    [expanded,setExpanded]=useState<string|null>(null),[edits,setEdits]=useState<Record<string,string>>({})
  const requestId=useRef(crypto.randomUUID()),guard=useRef(false),applyIds=useRef<Record<string,string>>({})
  const options=structure.format==='pdf'?(structure.pages||[]).map(page=>({value:`page:${page.number}`,label:t('第 {0} 页',page.number)})):
    structure.format==='docx'?structure.figures.filter(figure=>figure.embedded_image_present===true&&figure.target_mode!=='External'&&typeof figure.figure_id==='string')
      .map(figure=>({value:`figure:${figure.figure_id}`,label:t('内嵌图片 {0}',String(figure.figure_id).replace('figure:',''))})):[]
  const query=useQuery<{items:Operation[]}>({queryKey:['document-processing',sourceId],queryFn:({signal})=>collectionRequest(`/api/v1/documents/sources/${sourceId}/processing`,{signal}),
    refetchInterval:value=>working||value.state.data?.items.some(item=>['preparing','running'].includes(item.status))?2000:false})
  const active=query.data?.items.some(item=>['preparing','running'].includes(item.status))||false
  const reset=()=>{requestId.current=crypto.randomUUID()}
  async function start(kind:'vision'|'image_embedding'='vision'){
    if(guard.current||!file||!target)return
    guard.current=true;setWorking(true);setError('')
    const form=new FormData(),split=target.indexOf(':'),kind=target.slice(0,split),selected=target.slice(split+1)
    form.set('file',file);form.set('request_id',requestId.current);form.set('parse_version_id',parseVersion);form.set('target_kind',kind)
    form.set(kind==='page'?'page':'figure_id',selected);form.set('language',locale);form.set('detail',detail)
    try{
      const response=await fetch(`/api/v1/documents/sources/${sourceId}/processing/${kind==='vision'?'vision':'multimodal-features'}`,{method:'POST',body:form})
      const data=await response.json().catch(()=>({}))
      if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'processing_failed')
      setExpanded(data.operation_id);reset();if(data.status==='failed')setError(explain(data.error_category)||t('处理未完成'));await client.invalidateQueries({queryKey:['document-processing',sourceId]});if(kind==='image_embedding')await client.invalidateQueries({queryKey:['document-features',sourceId]})
    }catch(problem){const code=problem instanceof Error?problem.message:'';setError(explain(code)||t('处理未完成'));await client.invalidateQueries({queryKey:['document-processing',sourceId]})}
    finally{guard.current=false;setWorking(false)}
  }
  async function cancel(operationId:string){
    try{await collectionRequest(`/api/v1/documents/sources/${sourceId}/processing/${operationId}/cancel`,jsonOptions({}));await client.invalidateQueries({queryKey:['document-processing',sourceId]})}
    catch{setError(t('暂时无法完成，请重试'))}
  }
  async function applyText(item:Operation){
    const page=structure.pages?.find(value=>value.number===item.input.selection.page),content=edits[item.operation_id]??item.result?.transcription
    if(!page||typeof page.start!=='number'||typeof page.end!=='number'||!content?.trim())return
    setError('');setNotice('');applyIds.current[item.operation_id]??=crypto.randomUUID()
    try{
      await collectionRequest(`/api/v1/documents/sources/${sourceId}/versions`,jsonOptions({request_id:applyIds.current[item.operation_id],
        expected_parse_version:item.parse_version,expected_revision:item.lifecycle_revision,reason:`visual_transcription:${item.operation_id}`,
        mode:'patch',start:page.start,end:page.end,text:`\n\n${content}\n\n`,format:'txt',publish:true}))
      delete applyIds.current[item.operation_id];setNotice(t('已生成新的资料版本'));await onChanged?.()
    }catch{setError(t('资料或模型配置已变化，本次结果未保存'))}
  }
  return <section className="document-visual-panel" aria-label={t('页面与图片理解')}>
    <div className="document-visual-header"><div><h5>{t('页面与图片理解')}</h5><p>{t('选择原文件和页面，发送至你配置的模型。')}</p></div></div>
    {options.length?<div className="document-visual-form"><label className="collection-field">{t('选择页面或图片')}<select value={target} disabled={working} onChange={event=>{setTarget(event.target.value);reset()}}><option value="">{t('请选择')}</option>{options.map(option=><option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
      <label className="collection-field">{t('选择相同版本的原文件')}<input type="file" accept={structure.format==='pdf'?'.pdf':'.docx'} disabled={working} onChange={event=>{setFile(event.target.files?.[0]||null);reset()}}/></label>
      <label className="collection-field">{t('图像细节')}<select value={detail} disabled={working} onChange={event=>{setDetail(event.target.value);reset()}}><option value="low">{t('快速')}</option><option value="high">{t('精细')}</option></select></label>
      <div className="flex flex-wrap gap-2"><button type="button" className="btn-secondary" disabled={!file||!target||working||active} onClick={()=>void start('vision')}>{working?t('正在处理…'):t('开始理解')}</button>
      <button type="button" className="btn-secondary" disabled={!file||!target||working||active} onClick={()=>void start('image_embedding')}>{t('生成本地图文特征')}</button></div></div>:<p>{t('当前资料没有可选择的页面或内嵌图片')}</p>}
    {error&&<p role="alert">{uiMessage(error)}</p>}{notice&&<p role="status">{notice}</p>}
    {query.isError&&<p role="alert">{t('处理记录暂时无法读取')}</p>}
    {!!query.data?.items.length&&<div className="document-visual-history">{query.data.items.filter(item=>item.kind==='vision').map(item=><article key={item.operation_id}>
      <div className="document-visual-row"><button type="button" className="btn-ghost" onClick={()=>setExpanded(expanded===item.operation_id?null:item.operation_id)}>{item.input.selection.kind==='page'?t('第 {0} 页',item.input.selection.page):t('内嵌图片 {0}',item.input.selection.figure_id?.replace('figure:',''))} · {states[item.status]||item.status}</button><span>{item.model_name}</span>{['preparing','running'].includes(item.status)&&<button type="button" className="btn-ghost" onClick={()=>void cancel(item.operation_id)}>{t('取消处理')}</button>}</div>
      {item.error_category&&<p>{explain(item.error_category)}</p>}{item.usage&&<p>{item.usage.status==='reported'?t('实际用量 {0} Token',item.usage.total_tokens):t('用量待确认')}</p>}
      {expanded===item.operation_id&&item.result&&<div className="document-visual-result">
        {item.result.visual_summary&&<section><strong>{t('图像概览')}</strong><p>{item.result.visual_summary}</p></section>}
        {item.result.transcription&&<section><strong>{t('图中文字')}</strong>{item.input.selection.kind==='page'?<><textarea className="collection-field" value={edits[item.operation_id]??item.result.transcription} onChange={event=>{setEdits({...edits,[item.operation_id]:event.target.value});delete applyIds.current[item.operation_id]}}/><p>{t('应用后将替换这一页的保留文字，并创建新版本。')}</p><button type="button" className="btn-secondary" disabled={!(edits[item.operation_id]??item.result.transcription).trim()} onClick={()=>void applyText(item)}>{t('应用识别文字')}</button></>:<p>{item.result.transcription}</p>}</section>}
        {!!item.result.layout.length&&<section><strong>{t('版面')}</strong><ul>{item.result.layout.map((line,index)=><li key={index}>{line}</li>)}</ul></section>}
        {!!item.result.chart_observations.length&&<section><strong>{t('图表观察')}</strong><ul>{item.result.chart_observations.map((line,index)=><li key={index}>{line}</li>)}</ul></section>}
        {!!item.result.uncertainties.length&&<section><strong>{t('不确定项')}</strong><ul>{item.result.uncertainties.map((line,index)=><li key={index}>{line}</li>)}</ul></section>}
      </div>}
    </article>)}</div>}
    {!!query.data?.items.some(item=>item.kind==='image_embedding')&&<div className="document-visual-history"><h5>{t('图文特征记录')}</h5>{query.data.items.filter(item=>item.kind==='image_embedding').map(item=><article key={item.operation_id}>
      <div className="document-visual-row"><span>{item.input.selection.kind==='page'?t('第 {0} 页',item.input.selection.page):t('内嵌图片 {0}',item.input.selection.figure_id?.replace('figure:',''))} · {states[item.status]||item.status}</span><span>{item.model_name}</span>{['preparing','running'].includes(item.status)&&<button type="button" className="btn-ghost" onClick={()=>void cancel(item.operation_id)}>{t('取消处理')}</button>}</div>
      {item.error_category&&<p>{explain(item.error_category)}</p>}{item.result?.image_encoded&&<p>{t('图像已编码 · 文本片段 {0}',item.result.text_windows?.length||0)}</p>}
    </article>)}</div>}
  </section>
}
