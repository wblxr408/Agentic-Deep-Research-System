interface RelationAnchor { evidence_id:string; source_url:string; start:number; end:number; quote:string }
export interface RelationshipView {
  schema_version:string; origin:string
  entities:Array<{entity_id:string;name:string;type:string;selected:boolean}>
  records:Array<{relationship_id:string;kind:string;name:string;entity_ids:string[];party_roles?:Record<string,string>;related_output_id?:string|null;stage:string;status:string;polarity:string;event_time:{lower:string|null;upper:string|null;precision:string;basis:string};proofs:RelationAnchor[];counter_evidence?:RelationAnchor[];gaps:string[]}>
  locations:Array<{entity_id:string;place:string;kind:string;is_rd_site:boolean;status:string;proof:RelationAnchor}>
  coverage:Record<string,{observations:number;status:string}>
  coauthor_pairs:Array<{entity_ids:string[];publication_count:number;first_observed_lower:string;last_observed_upper:string;continuity:string}>
  pending_records:Array<{kind:string;reason:string}>
  boundaries:string[]
}
const kinds:Record<string,string>={coauthorship:'共著',funding:'资助',project:'项目',joint_laboratory:'联合实验室',exchange:'交流'}
const stages:Record<string,string>={publication_observation:'发表时观测',occurred:'事件陈述',announced:'已宣布',planned:'计划／承诺',unknown:'阶段未知'}
const states:Record<string,string>={literal_affiliations_checked_not_partnership:'署名字面已核，协议未知',source_assertion_requires_review:'来源陈述，待独立核实',source_denial_requires_review:'来源否认，待核',uncertain_source_claim:'不确定陈述',potential_conflict_requires_review:'存在待核冲突',event_outside_requested_period:'事件时间在研究范围外'}
const locations:Record<string,string>={publication_affiliation:'发表署名地址',partner_location:'伙伴所在地',event_location:'活动所在地',rd_site:'明确研发场所陈述（待核）'}
function Anchor({anchor}:{anchor:RelationAnchor}) {
  let url:string|undefined
  try { const parsed=new URL(anchor.source_url);if(['http:','https:'].includes(parsed.protocol))url=parsed.href } catch { /* source text remains readable */ }
  return <li className="mb-2 break-words text-xs"><a href={url} target="_blank" rel="noopener noreferrer" className="underline">{anchor.evidence_id}</a> · 字符 {anchor.start}–{anchor.end}<blockquote className="mt-1 border-l-2 border-orange-200 pl-2">{anchor.quote}</blockquote></li>
}
export default function RelationshipSummary({view}:{view:RelationshipView}) {
  const names=Object.fromEntries(view.entities.map(entity=>[entity.entity_id,entity.name]))
  const parties=(ids:string[])=>ids.map(id=>names[id]||id).join('、')
  return <section aria-label="关系来源与时间视图" className="mt-5 space-y-3 rounded-xl border border-xmgray-200 p-4 text-sm">
    <h3 className="font-semibold">关系来源、时间与地域边界</h3>
    <p className="text-xs text-xmgray-500">{view.schema_version} · {view.origin}。关系陈述不自动成为已核实合作事实；所有类型分别保留。</p>
    <ul className="space-y-1 text-xs text-xmgray-600">{view.boundaries.map(text=><li key={text}>{text}</li>)}</ul>
    <table aria-label="关系类型覆盖" className="w-full text-left"><thead><tr><th>类型</th><th>来源观测</th><th>范围说明</th></tr></thead><tbody>{Object.entries(view.coverage).map(([kind,value])=><tr key={kind}><th className="font-normal">{kinds[kind]||kind}</th><td>{value.observations}</td><td>{value.observations?'逐条查看阶段、时间和待核状态':'本样本未建立，不能说不存在'}</td></tr>)}</tbody></table>
    {view.records.map(row=><details key={row.relationship_id} className="rounded-lg border border-xmgray-200 p-3">
      <summary className="cursor-pointer">{kinds[row.kind]} · {row.name} · {states[row.status]||row.status}</summary>
      <div className="mt-3 space-y-2"><p>{parties(row.entity_ids)}</p><p>{stages[row.stage]||row.stage} · {row.event_time.lower?`${row.event_time.lower} 至 ${row.event_time.upper}（${row.event_time.precision}）`:'事件时间未知'}</p>
        <p className="text-xs">该日期仅表示来源中的事件／发表观测，不自动表示协议有效期或当前状态。</p>
        {!!row.party_roles && <p className="text-xs">来源角色（待核）：{Object.entries(row.party_roles).map(([id,role])=>`${names[id]||id}: ${role}`).join('；')||'未明确，不猜测资助方或主导方'}</p>}
        <ul>{row.proofs.map((anchor,index)=><Anchor key={index} anchor={anchor}/>)}</ul>
        {!!row.counter_evidence?.length && <div><h4 className="font-medium">反向陈述／待核冲突</h4><ul>{row.counter_evidence.map((anchor,index)=><Anchor key={index} anchor={anchor}/>)}</ul></div>}
        <ul className="text-xs text-amber-800">{row.gaps.map((gap,index)=><li key={index}>{gap}</li>)}</ul>
      </div>
    </details>)}
    {!!view.coauthor_pairs.length && <details><summary className="cursor-pointer">共著频次与观测时间</summary><table aria-label="共著观测" className="mt-2 w-full text-left"><thead><tr><th>双方</th><th>发表样本</th><th>最早／最晚观测边界</th></tr></thead><tbody>{view.coauthor_pairs.map((pair,index)=><tr key={index}><th className="font-normal">{parties(pair.entity_ids)}</th><td>{pair.publication_count}</td><td>{pair.first_observed_lower}／{pair.last_observed_upper}</td></tr>)}</tbody></table><p className="text-xs">按采纳发表计数；共同论文不等于多个项目，不按频次推断持续协议、主导关系或可联系性。</p></details>}
    {!!view.locations.length && <details><summary className="cursor-pointer">地点语义</summary><ul className="mt-2 space-y-2">{view.locations.map((place,index)=><li key={index}>{names[place.entity_id]||place.entity_id} · {place.place} · {locations[place.kind]||place.kind}<p className="text-xs">{place.is_rd_site?'仅保留明确场所陈述，仍待独立核实':'此地点不计为目标组织研发中心。'}</p><ul><Anchor anchor={place.proof}/></ul></li>)}</ul></details>}
    {!!view.pending_records.length && <details><summary className="cursor-pointer">未采纳／待核关系</summary><ul className="mt-2 space-y-1 text-xs">{view.pending_records.map((item,index)=><li key={index}>{item.kind}：{item.reason}</li>)}</ul></details>}
  </section>
}
