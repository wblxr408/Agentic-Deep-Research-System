export interface TaxonomyDraft { preset: string; version: string; customText: string }
export const defaultTaxonomy: TaxonomyDraft = { preset: 'auto', version: 'topic-policy-v1', customText: '[]' }
export function taxonomyRequest(value = defaultTaxonomy) {
  if (!value.version.trim()) throw new Error('请填写分类版本。')
  let nodes: unknown[] = []
  if (value.preset === 'custom') {
    try { nodes = JSON.parse(value.customText) } catch { throw new Error('自定义分类须填写有效的 JSON 数组。') }
    if (!Array.isArray(nodes) || !nodes.length) throw new Error('自定义分类至少需要一个节点。')
  }
  return { preset: value.preset, version: value.version.trim(), nodes }
}
export default function TaxonomyEditor({ value = defaultTaxonomy, onChange,matchScope='publication' }: { value?: TaxonomyDraft; onChange: (value: TaxonomyDraft) => void;matchScope?:'publication'|'chunk' }) {
  return <fieldset className="mt-3 space-y-2 rounded-xl border border-xmgray-200 p-3">
    <legend className="text-sm font-medium">学科分类规则</legend>
    <label className="block text-xs">分类方案<select aria-label="分类方案" className="input-xm mt-1" value={value.preset} onChange={e => onChange({ ...value, preset: e.target.value })}>
      <option value="auto">按所选学科选择规则；未支持学科保留未知</option><option value="materials_science">材料科学</option>
      <option value="computer_science">计算机科学</option><option value="business">商科</option><option value="custom">自定义问题／方法／应用分类</option>
    </select></label>
    <label className="block text-xs">分类版本<input aria-label="分类版本" className="input-xm mt-1" value={value.version} maxLength={300} onChange={e => onChange({ ...value, version: e.target.value })} /></label>
    {value.preset === 'custom' && <><label className="block text-xs">自定义分类节点<textarea aria-label="自定义分类节点" className="input-xm mt-1 min-h-40 font-mono text-xs" value={value.customText} onChange={e => onChange({ ...value, customText: e.target.value })} /></label>
      <p className="text-xs text-xmgray-500">节点包含 node_id、label、discipline、axis（problem／method／application）、role（core／associated）、terms（词组数组），可加 parent_id。父子属于同一学科和层次。</p></>}
    <p className="text-xs text-xmgray-500">{matchScope==='chunk'?'此处只匹配资料块正文词面，保留位置、核心／关联、多标签和未知；不等于组织成果分类、官方标签或机制核验。':'规则匹配主成果题名和明确标记的摘要，保留原文位置和未知；旧材料只用已保留的题名。不把载体等级当作主题，不等于已核实全文机制。预设是产品分类口径。'}</p>
  </fieldset>
}
