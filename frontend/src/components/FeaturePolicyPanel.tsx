export interface FeatureDraft {dense:boolean;cjkMode:'characters'|'bigrams'|'both';maxTokenEvents:number;sourceDate:string;asOf:string;halfLifeDays:number;windowStart:string;windowEnd:string}
export const defaultFeatureDraft:FeatureDraft={dense:false,cjkMode:'both',maxTokenEvents:1024,sourceDate:'',asOf:'',halfLifeDays:730,windowStart:'',windowEnd:''}
export function featurePolicyRequest(value:FeatureDraft) {
  if(!Number.isInteger(value.maxTokenEvents)||value.maxTokenEvents<128||value.maxTokenEvents>2048)throw new Error('每块词项事件上限须为128–2048的整数。')
  if(!Number.isInteger(value.halfLifeDays)||value.halfLifeDays<30||value.halfLifeDays>3650)throw new Error('时间半衰期须为30–3650天的整数。')
  if(value.sourceDate&&!value.asOf)throw new Error('声明来源日期时，请同时选择计算时点。')
  if(value.windowStart&&value.windowEnd&&value.windowStart>value.windowEnd)throw new Error('特征时间窗口起点不能晚于终点。')
  return {dense:value.dense,cjk_mode:value.cjkMode,max_token_events:value.maxTokenEvents,source_date:value.sourceDate||null,as_of:value.asOf||null,half_life_days:value.halfLifeDays,window_start:value.windowStart||null,window_end:value.windowEnd||null}
}
export type IndexMode='direct'|'lexical'
export function indexPolicyRequest(mode:IndexMode) {return {mode,reason:mode==='direct'?'user_selected_direct_citation_only':'user_selected_cross_document_lexical_retrieval'}}
export default function FeaturePolicyPanel({value,onChange,indexMode,onIndexChange}:{value:FeatureDraft;onChange:(value:FeatureDraft)=>void;indexMode:IndexMode;onIndexChange:(value:IndexMode)=>void}) {
  const update=(patch:Partial<FeatureDraft>)=>onChange({...value,...patch})
  return <fieldset className="space-y-3 rounded-xl border border-xmgray-200 p-3 text-sm"><legend>检索细节</legend>
    <label className="block text-xs">资料用途<select aria-label="资料索引用途" className="input-xm mt-1" value={indexMode} onChange={event=>onIndexChange(event.target.value as IndexMode)}><option value="lexical">加入内部资料检索</option><option value="direct">仅保存与直接定位引用</option></select></label>
    {indexMode==='direct'&&<p className="text-xs text-xmgray-500">可按来源和原位置查看；跨资料检索不召回此来源。之后可在详情显式建立词汇索引。</p>}
    <label className="flex items-start gap-2"><input type="checkbox" disabled={indexMode==='direct'} checked={value.dense} onChange={event=>update({dense:event.target.checked})} />语义检索（需要本机模型）</label>
    <p className="text-xs text-xmgray-500"></p>
    <div className="grid gap-3 sm:grid-cols-2"><label className="text-xs">中文词项方式<select aria-label="中文词项方式" className="input-xm mt-1" value={value.cjkMode} onChange={event=>update({cjkMode:event.target.value as FeatureDraft['cjkMode']})}><option value="both">字符与相邻二元组</option><option value="characters">单字符</option><option value="bigrams">相邻二元组</option></select></label>
      <label className="text-xs">每块词项事件上限<input aria-label="每块词项事件上限" className="input-xm mt-1" type="number" min={128} max={2048} value={value.maxTokenEvents} onChange={event=>update({maxTokenEvents:Number(event.target.value)})} /></label></div>
    <details><summary className="cursor-pointer text-xs">可选来源日期与时间视图</summary><p className="my-2 text-xs text-xmgray-500"></p>
      <div className="grid gap-3 sm:grid-cols-2"><label className="text-xs">声明的来源日期<input aria-label="声明的来源日期" type="date" className="input-xm mt-1" value={value.sourceDate} onChange={event=>update({sourceDate:event.target.value})} /></label>
        <label className="text-xs">时间计算时点<input aria-label="时间计算时点" type="date" className="input-xm mt-1" value={value.asOf} onChange={event=>update({asOf:event.target.value})} /></label>
        <label className="text-xs">时间窗口起点<input aria-label="特征时间窗口起点" type="date" className="input-xm mt-1" value={value.windowStart} onChange={event=>update({windowStart:event.target.value})} /></label>
        <label className="text-xs">时间窗口终点<input aria-label="特征时间窗口终点" type="date" className="input-xm mt-1" value={value.windowEnd} onChange={event=>update({windowEnd:event.target.value})} /></label>
        <label className="text-xs">时间半衰期（天）<input aria-label="特征时间半衰期" type="number" min={30} max={3650} className="input-xm mt-1" value={value.halfLifeDays} onChange={event=>update({halfLifeDays:Number(event.target.value)})} /></label></div>
    </details>
  </fieldset>
}
