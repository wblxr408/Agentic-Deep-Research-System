import {t,useLocale} from '../i18n'
import TaxonomyEditor,{defaultTaxonomy,taxonomyRequest} from './TaxonomyEditor'
import type {TaxonomyDraft} from './TaxonomyEditor'

export interface ChunkDraft {
  strategy:'fixed'|'sliding'|'recursive'|'structure'|'semantic';semanticSimilarity:number;context:'matched'|'parent';sourceExcerpt:boolean
  entities:Array<{id:string;name:string;kind:string}>;classification:boolean;disciplines:string;taxonomy:TaxonomyDraft
}
export const defaultChunkDraft:ChunkDraft={strategy:'structure',semanticSimilarity:0.65,context:'matched',sourceExcerpt:false,entities:[],classification:false,disciplines:'',taxonomy:{...defaultTaxonomy}}
export function chunkPolicyRequest(value:ChunkDraft) {
  if(value.entities.some(item=>item.name.trim().length<2))throw new Error(t("实体词典中的名称至少需要两个字符。"))
  const disciplines=[...new Set(value.disciplines.split(/[,，、]/).map(item=>item.trim()).filter(Boolean))]
  if(disciplines.length>8)throw new Error(t("块分类最多声明8个学科。"))
  if(value.classification&&!disciplines.length)throw new Error(t("启用块级分类时请填写适用学科。"))
  return {strategy:value.strategy,...(value.strategy==='semantic'?{semantic_similarity:value.semanticSimilarity}:{}),retrieval_context:value.context,include_source_excerpt:value.sourceExcerpt,
    entity_terms:value.entities.map(item=>({entity_id:item.id,name:item.name.trim(),kind:item.kind})),
    disciplines:value.classification?disciplines:[],taxonomy:value.classification?taxonomyRequest(value.taxonomy):null}
}
export default function ChunkPolicyPanel({value,onChange}:{value:ChunkDraft;onChange:(value:ChunkDraft)=>void}) {
  useLocale()

  const update=(patch:Partial<ChunkDraft>)=>onChange({...value,...patch})
  return <fieldset className="space-y-3 rounded-xl border border-xmgray-200 p-3 text-sm"><legend>{t("片段处理")}</legend>
    <label className="block text-xs">{t("分块方式")}<select aria-label={t("分块方式")} className="input-xm mt-1" value={value.strategy} onChange={event=>update({strategy:event.target.value as ChunkDraft['strategy']})}>
      <option value="structure">{t("按章节、表格和代码结构")}</option><option value="semantic">{t('按语义变化')}</option><option value="recursive">{t("按段落／换行递归边界")}</option><option value="sliding">{t("固定窗口与重叠")}</option><option value="fixed">{t("固定长度，不重叠")}</option></select></label>
    {value.strategy==='semantic'&&<label className="block text-xs">{t('主题相似程度')}<select className="input-xm mt-1" value={value.semanticSimilarity} onChange={event=>update({semanticSimilarity:Number(event.target.value)})}><option value={0.5}>{t('宽松')}</option><option value={0.65}>{t('均衡')}</option><option value={0.8}>{t('紧密')}</option></select><span>{t('使用已配置的本地编码模型，片段不重叠')}</span></label>}
    <p className="text-xs text-xmgray-500"></p>
    <label className="block text-xs">{t("检索时的上下文")}<select aria-label={t("检索时的上下文")} className="input-xm mt-1" value={value.context} onChange={event=>update({context:event.target.value as ChunkDraft['context']})}>
      <option value="matched">{t("只返回命中片段")}</option><option value="parent">{t("需要时返回有限父级上下文")}</option></select></label>
    <label className="flex items-start gap-2 text-xs"><input type="checkbox" checked={value.sourceExcerpt} onChange={event=>update({sourceExcerpt:event.target.checked})} />{t("检索时附上开头摘录")}</label>
    <details><summary className="cursor-pointer text-xs">{t("需要识别的名称")}</summary>
      <div className="mt-2 space-y-2">{value.entities.map((entity,index)=><div key={entity.id} className="flex gap-2">
        <select aria-label={t("实体{0}类型", index+1)} className="input-xm w-24 text-xs" value={entity.kind} onChange={event=>update({entities:value.entities.map(item=>item.id===entity.id?{...item,kind:event.target.value}:item)})}><option value="organization">{t("机构")}</option><option value="person">{t("人员")}</option><option value="location">{t("地域")}</option><option value="other">{t("其他")}</option></select>
        <input aria-label={t("实体{0}名称", index+1)} className="input-xm text-xs" maxLength={200} value={entity.name} onChange={event=>update({entities:value.entities.map(item=>item.id===entity.id?{...item,name:event.target.value}:item)})} placeholder={t("来源中实际出现的名称")} />
        <button type="button" className="btn-ghost text-xs" onClick={()=>update({entities:value.entities.filter(item=>item.id!==entity.id)})}>{t("移除")}</button>
      </div>)}<button type="button" className="btn-ghost text-xs" disabled={value.entities.length>=40} onClick={()=>update({entities:[...value.entities,{id:'term-'+crypto.randomUUID(),name:'',kind:'organization'}]})}>{t("添加实体词")}</button></div>
    </details>
    <label className="flex items-start gap-2 text-xs"><input type="checkbox" checked={value.classification} onChange={event=>update({classification:event.target.checked})} />{t("按学科分类片段")}</label>
    {value.classification&&<><label className="block text-xs">{t("块分类适用学科（逗号分隔）")}<input aria-label={t("块分类适用学科")} className="input-xm mt-1" value={value.disciplines} onChange={event=>update({disciplines:event.target.value})} placeholder={t("例如：材料科学、计算机科学")} /></label><TaxonomyEditor matchScope="chunk" value={value.taxonomy} onChange={taxonomy=>update({taxonomy})} /></>}
  </fieldset>
}
