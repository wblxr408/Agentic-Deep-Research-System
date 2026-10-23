import TaxonomyEditor,{defaultTaxonomy,taxonomyRequest} from './TaxonomyEditor'
import type {TaxonomyDraft} from './TaxonomyEditor'

export interface ChunkDraft {
  strategy:'fixed'|'sliding'|'recursive'|'structure';context:'matched'|'parent';sourceExcerpt:boolean
  entities:Array<{id:string;name:string;kind:string}>;classification:boolean;disciplines:string;taxonomy:TaxonomyDraft
}
export const defaultChunkDraft:ChunkDraft={strategy:'structure',context:'matched',sourceExcerpt:false,entities:[],classification:false,disciplines:'',taxonomy:{...defaultTaxonomy}}
export function chunkPolicyRequest(value:ChunkDraft) {
  if(value.entities.some(item=>item.name.trim().length<2))throw new Error('实体词典中的名称至少需要两个字符。')
  const disciplines=[...new Set(value.disciplines.split(/[,，、]/).map(item=>item.trim()).filter(Boolean))]
  if(disciplines.length>8)throw new Error('块分类最多声明8个学科。')
  if(value.classification&&!disciplines.length)throw new Error('启用块级分类时请填写适用学科。')
  return {strategy:value.strategy,retrieval_context:value.context,include_source_excerpt:value.sourceExcerpt,
    entity_terms:value.entities.map(item=>({entity_id:item.id,name:item.name.trim(),kind:item.kind})),
    disciplines:value.classification?disciplines:[],taxonomy:value.classification?taxonomyRequest(value.taxonomy):null}
}
export default function ChunkPolicyPanel({value,onChange}:{value:ChunkDraft;onChange:(value:ChunkDraft)=>void}) {
  const update=(patch:Partial<ChunkDraft>)=>onChange({...value,...patch})
  return <fieldset className="space-y-3 rounded-xl border border-xmgray-200 p-3 text-sm"><legend>分块与研究元数据</legend>
    <label className="block text-xs">分块方式<select aria-label="分块方式" className="input-xm mt-1" value={value.strategy} onChange={event=>update({strategy:event.target.value as ChunkDraft['strategy']})}>
      <option value="structure">按章节、表格和代码结构</option><option value="recursive">按段落／换行递归边界</option><option value="sliding">固定窗口与重叠</option><option value="fixed">固定长度，不重叠</option></select></label>
    <p className="text-xs text-xmgray-500">使用下方块长度与重叠设置；固定长度策略的实际重叠为0。长表格／代码保留父级范围。</p>
    <label className="block text-xs">检索时的上下文<select aria-label="检索时的上下文" className="input-xm mt-1" value={value.context} onChange={event=>update({context:event.target.value as ChunkDraft['context']})}>
      <option value="matched">只返回命中片段</option><option value="parent">需要时返回有限父级上下文</option></select></label>
    <label className="flex items-start gap-2 text-xs"><input type="checkbox" checked={value.sourceExcerpt} onChange={event=>update({sourceExcerpt:event.target.checked})} />附上文档开头的有界原文摘录作为背景；不生成摘要</label>
    <details><summary className="cursor-pointer text-xs">可选实体词典（只标提及，不确认关系）</summary>
      <div className="mt-2 space-y-2">{value.entities.map((entity,index)=><div key={entity.id} className="flex gap-2">
        <select aria-label={`实体${index+1}类型`} className="input-xm w-24 text-xs" value={entity.kind} onChange={event=>update({entities:value.entities.map(item=>item.id===entity.id?{...item,kind:event.target.value}:item)})}><option value="organization">机构</option><option value="person">人员</option><option value="location">地域</option><option value="other">其他</option></select>
        <input aria-label={`实体${index+1}名称`} className="input-xm text-xs" maxLength={200} value={entity.name} onChange={event=>update({entities:value.entities.map(item=>item.id===entity.id?{...item,name:event.target.value}:item)})} placeholder="来源中实际出现的名称" />
        <button type="button" className="btn-ghost text-xs" onClick={()=>update({entities:value.entities.filter(item=>item.id!==entity.id)})}>移除</button>
      </div>)}<button type="button" className="btn-ghost text-xs" disabled={value.entities.length>=40} onClick={()=>update({entities:[...value.entities,{id:'term-'+crypto.randomUUID(),name:'',kind:'organization'}]})}>添加实体词</button></div>
    </details>
    <label className="flex items-start gap-2 text-xs"><input type="checkbox" checked={value.classification} onChange={event=>update({classification:event.target.checked})} />启用块级学科词面分类</label>
    {value.classification&&<><label className="block text-xs">块分类适用学科（逗号分隔）<input aria-label="块分类适用学科" className="input-xm mt-1" value={value.disciplines} onChange={event=>update({disciplines:event.target.value})} placeholder="例如：材料科学、计算机科学" /></label><TaxonomyEditor matchScope="chunk" value={value.taxonomy} onChange={taxonomy=>update({taxonomy})} /></>}
  </fieldset>
}
