import {uiDefinition,useLocale,t} from '../i18n'
interface PriorityGroup {group_id:string;score:number|null;lower_bound:number|null;upper_bound:number|null;coverage:number;missing_dimensions:string[];contributions:Record<string,unknown>}
export interface ActionView {
  schema_version:string;purpose:string;boundaries:string[];priority_gap:string|null
  requirements:unknown;pending_records:Array<{reason:string}>
  cards:Array<{action_id:string;entity_name:string;mode:string;status:string;question:string|null;goal:string|null;missing_requirements:string[];hard_condition_reasons:string[];unverified_constraints:string[];proposed_steps:string[];complementary_hypothesis:string|null;priority_groups:PriorityGroup[];
    basis:Array<{evidence_id:string;source_url:string;start:number;end:number;quote:string}>;
    related_people:Array<{name:string;publication_ids:string[];status:string}>;related_people_count:number;
    public_contacts:Array<{url:string;source_url:string;status:string}>;relationship_observations:Array<{relationship_id:string;kind:string;status:string}>}>
}
const statuses:Record<string,string>=uiDefinition({needs_requirements:'需求待补',hard_conditions_not_established:'硬条件未成立',needs_source_grounded_action:'议题缺少来源依据',conditional_research_route:'有条件的研究验证路线',needs_feasibility_and_contact_review:'待核实可行性／联系入口'})
const labels:Record<string,string>=uiDefinition({cooperation_goal:'合作需求',offering:'可提供资源',time_window:'时间要求',research_goal:'研究目标'})
function url(value:string) {try {const x=new URL(value);return ['http:','https:'].includes(x.protocol)?x.href:undefined}catch{return undefined}}
export default function ActionSummary({view}:{view:ActionView}) {
  useLocale()

  return <section aria-label={t("研究与合作行动卡")} className="mt-5 space-y-3 rounded-xl border border-xmgray-200 p-4 text-sm"><h3 className="font-semibold">{t("研究验证路线与条件行动卡")}</h3><p className="text-xs text-xmgray-500">{view.schema_version} · {view.purpose}</p><ul className="text-xs text-xmgray-600">{view.boundaries.map(text=><li key={text}>{text}</li>)}</ul>
    {view.priority_gap && <p className="text-xs text-amber-800">{t("匹配缺口：")}{view.priority_gap}</p>}
    {view.cards.map(card=><details className="rounded-lg border border-xmgray-200 p-3" key={card.action_id}><summary className="cursor-pointer">{card.entity_name} · {card.mode==='cooperation'?t("合作行动"):t("研究验证")} · {statuses[card.status]||card.status}</summary>
      <p className="mt-3">{card.question||t("尚未取得有原文支持的具体议题。")}</p><p className="mt-2 text-xs">{t("目标：")}{card.goal||t("待补充")}</p>
      {!!card.missing_requirements.length && <p className="mt-2 text-xs text-amber-800">{t("待补：")}{card.missing_requirements.map(key=>labels[key]||key).join('、')}</p>}
      {!!card.hard_condition_reasons.length && <p className="mt-2 text-xs text-amber-800">{t("硬条件：")}{card.hard_condition_reasons.join('；')}</p>}
      {card.priority_groups.map(group=><div key={group.group_id} className="mt-3 rounded bg-xmgray-50 p-2 text-xs"><p>{t("可比组 ")}{group.group_id} · {group.lower_bound===null?t("无适用分项"):`${group.lower_bound.toFixed(2)}–${group.upper_bound?.toFixed(2)}`} {t(" · 覆盖率 ")}{(group.coverage*100).toFixed(2)}%</p><p>{t("待补维度：")}{group.missing_dimensions.join('、')||t("当前计分维度无缺失；仍不代表合作可行")}</p><details><summary>{t("分项贡献与依据")}</summary><pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words">{JSON.stringify(group.contributions,null,2)}</pre></details></div>)}
      {card.complementary_hypothesis && <p className="mt-3 text-xs">{t("互补假设（待验证）：")}{card.complementary_hypothesis}</p>}
      <ul className="mt-2 text-xs">{card.proposed_steps.map((text,index)=><li key={index}>{t("建议下一步（未执行）：")}{text}</li>)}{card.unverified_constraints.map((text,index)=><li key={'constraint-'+index}>{t("待核约束：")}{text}</li>)}</ul>
      <details className="mt-3"><summary className="cursor-pointer">{t("来源、人员与已有关系")}</summary><ul className="text-xs">{card.basis.map((proof,index)=><li className="mt-2" key={index}><a className="underline" href={url(proof.source_url)} target="_blank" rel="noopener noreferrer">{proof.evidence_id}</a> · {proof.start}–{proof.end}<blockquote>{proof.quote}</blockquote></li>)}</ul><p className="mt-3 text-xs">{t("发表署名人员 ")}{card.related_people_count} {t(" 位；不是当前职务或可联系性证明。")}</p><ul className="text-xs">{card.related_people.map(person=><li key={person.name}>{person.name} · {person.publication_ids.join('、')}</li>)}{card.relationship_observations.map(relation=><li key={relation.relationship_id}>{relation.kind} · {relation.status}{t("（优先级不改写此状态）")}</li>)}</ul></details>
      {!!card.public_contacts.length && <ul className="mt-3 text-xs">{card.public_contacts.map((contact,index)=><li key={index}><a className="underline" href={url(contact.url)} target="_blank" rel="noopener noreferrer">{t("公开来源中的入口")}</a> {t(" · 归属与当前可联系性待核；未发送消息。")}</li>)}</ul>}
    </details>)}
    <details><summary className="cursor-pointer">{t("冻结需求与未采纳项")}</summary><pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs">{JSON.stringify(view.requirements,null,2)}</pre><ul className="text-xs">{view.pending_records.map((item,index)=><li key={index}>{item.reason}</li>)}</ul></details>
  </section>
}
