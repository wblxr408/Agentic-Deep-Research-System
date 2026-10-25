"""Evidence-bound relationship observations; no network, model, or graph service."""
from __future__ import annotations

import calendar
from collections import Counter, defaultdict
from itertools import combinations
import re
from typing import Literal
from urllib.parse import quote

from pydantic import Field
from app.research_scope import Identifier, Label, ScopeRecord

VERSION = 'adrs-relationship-observations-v1'
KINDS = {'coauthorship':'共著', 'funding':'资助', 'project':'项目', 'joint_laboratory':'联合实验室', 'exchange':'交流'}
CUES = {
    'funding': r'fund(?:ed|ing)|financial|grants?|经费|资助|捐赠|基金',
    'project': r'projects?|课题|项目',
    'joint_laboratory': r'joint\s+(?:research\s+)?lab(?:orator(?:y|ies))?|联合实验室|共建实验室',
    'exchange': r'visit(?:ed|ing)?|workshops?|meetings?|exchang\w*|交流|访问|考察|会议|汇报会|研讨',
}


class RelationProof(ScopeRecord):
    evidence_id: Identifier
    quote: str = Field(min_length=3, max_length=2400)


class Counterparty(ScopeRecord):
    entity_id: Identifier
    name: Label
    type: Literal['university','laboratory','company','agency','foundation','other']
    proof: RelationProof


class RelationshipObservation(ScopeRecord):
    relationship_id: Identifier
    kind: Literal['funding','project','joint_laboratory','exchange']
    name: Label
    entity_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=20)
    party_roles: dict[str, Literal['participant','funder','recipient','host','visitor','project_partner']] = Field(default_factory=dict, max_length=20)
    related_output_id: Identifier | None = None
    stage: Literal['occurred','announced','planned','unknown'] = 'unknown'
    polarity: Literal['positive','negative','uncertain'] = 'positive'
    event_date: str | None = Field(default=None,max_length=10)
    date_proof: RelationProof | None = None
    proof: RelationProof


class LocationObservation(ScopeRecord):
    entity_id: Identifier
    place: Label
    kind: Literal['partner_location','event_location','rd_site']
    proof: RelationProof
    relationship_id: Identifier | None = None


class RelationshipPreviewRequest(ScopeRecord):
    relationship_entities: tuple[Counterparty, ...] = Field(default=(),max_length=100)
    research_relationships: tuple[RelationshipObservation, ...] = Field(default=(),max_length=200)
    geographies: tuple[LocationObservation, ...] = Field(default=(),max_length=100)


def relationship_instructions(configuration):
    if 'relationships' not in (configuration or {}).get('modules', []):
        return ''
    return '''\nRelationship extraction: add these fields INSIDE organization_data, alongside the existing fields.
"relationship_entities": [{"entity_id":"external-id","name":"literal organization name","type":"university|laboratory|company|agency|foundation|other","proof":{"evidence_id":"ev-ID","quote":"literal identity excerpt"}}],
"research_relationships": [{"relationship_id":"event-id","kind":"funding|project|joint_laboratory|exchange","name":"source event/project/lab name","entity_ids":["SELECTED entity ID","other entity ID"],"party_roles":{"SELECTED entity ID":"participant"},"related_output_id":null,"stage":"occurred|announced|planned|unknown","polarity":"positive|negative|uncertain","event_date":"YYYY or YYYY-MM or YYYY-MM-DD, or null","date_proof":{"evidence_id":"ev-ID","quote":"literal event date, not the retrieval date"},"proof":{"evidence_id":"ev-ID","quote":"literal excerpt identifying parties AND actual relation type"}}],
"geographies": [{"entity_id":"party ID","place":"literal place","kind":"partner_location|event_location|rd_site","relationship_id":null,"proof":{"evidence_id":"ev-ID","quote":"literal organization and geographic context"}}].
Use selected entity IDs exactly. Counterparties are source-mentioned partners, not new research targets. Every party must be named in the relation proof (selected aliases allowed). For statements referring to a joint lab as a party, register that lab as a counterparty and quote its identity. A work funding claim may use related_output_id plus its named funder, but does NOT prove funding of an author's institution. Coauthorship is computed from accepted publication affiliations: do not propose formal cooperation from it. No project/lab/visit evidence means empty arrays, not invented cooperation. Preserve planned future financing as planned; a promise is not funds received. Event dates need their own literal proof; unknown dates remain null. Locations of partners or meetings are not R&D centers; rd_site requires an explicit research/development site predicate. Quote at most 2400 characters per proof and return the complete JSON.''' 


def _pattern(text):
    return r'\s+'.join(re.escape(token) for token in text.split())


def _has(text, name):
    return bool(re.search(_pattern(name),text,re.I))


def _date_literal_present(value, text):
    from app.organization_findings import _date_bounds
    lower,_,precision=_date_bounds(value)
    year,month,day=str(lower.year),f'(?:{lower.month:02d}|{lower.month})',f'(?:{lower.day:02d}|{lower.day})'
    month_names='(?:'+calendar.month_name[lower.month]+'|'+calendar.month_abbr[lower.month]+')'
    if precision=='year':pattern=year
    elif precision=='month':pattern=f'(?:{year}[-/.年]{month}月?|{month_names}\\s+{year}|{year}\\s+{month_names})'
    else:pattern=f'(?:{year}[-/.年]{month}[-/.月]{day}日?|{month_names}\\s+{day},?\\s+{year}|{day}\\s+{month_names}\\s+{year})'
    return bool(re.search(r'(?<!\d)'+pattern+r'(?!\d)',text,re.I))


def build_relationship_view(configuration, findings, evidence, proposals=None, *, origin='analyst'):
    """Validate proposed source claims and project existing attributed coauthors."""
    from app.organization_findings import _date_bounds, _publication_url
    findings, proposals = findings or {}, proposals or {}
    scope = configuration['scope']
    scoped = findings.get('scope_result') or {}
    entities = {item['entity_id']:{**item,'selected':True} for item in scoped.get('selected_entities',scope['entities'])}
    sources = {item['evidence_id']:item for item in evidence if item.get('evidence_id') and item.get('source_url')}
    outputs = {item['output_id']:item for item in scoped.get('outputs',[])}
    pending, records, locations = [], [], []

    def proof(value):
        source = sources.get(value.evidence_id)
        if not source or (source.get('acquisition') or {}).get('coverage') == 'discovery_only':
            raise ValueError('proof must reference retained acquired evidence')
        match = re.search(_pattern(value.quote), source.get('content') or '',re.I)
        if not match:
            raise ValueError('proof quote is absent from retained source')
        return {'evidence_id':value.evidence_id,'source_url':source['source_url'],'start':match.start(),
            'end':match.end(),'quote':match.group()}

    def identity_in(entity_id,text):
        entity = entities[entity_id]
        return any(_has(text,name) for name in [entity['name'],*entity.get('aliases',[])])

    def bounded(key,model,maximum):
        values = proposals.get(key,[])
        if not isinstance(values,list):
            pending.append({'kind':key,'reason':'expected_array'});return
        if len(values)>maximum:
            pending.append({'kind':key,'reason':'extraction_limit_exceeded'})
        for value in values[:maximum]:
            try:yield model.model_validate(value)
            except ValueError as error:pending.append({'kind':key,'reason':str(error)[:400]})

    for item in bounded('relationship_entities',Counterparty,100):
        try:
            anchor=proof(item.proof)
            if item.entity_id in entities or not _has(anchor['quote'],item.name):
                raise ValueError('counterparty ID conflicts or name is absent')
            if any(item.name.casefold() in [name.casefold() for name in [other['name'],*other.get('aliases',[])]] for other in entities.values()):
                raise ValueError('counterparty name may duplicate a selected identity; do not merge or rename it')
            entities[item.entity_id]={'entity_id':item.entity_id,'name':item.name,'type':item.type,'selected':False,
                'resolution_status':'source_named_pending_disambiguation','identity_proof':anchor}
        except ValueError as error:pending.append({'kind':'counterparty','entity_id':item.entity_id,'reason':str(error)})

    # Only direct, accepted publication affiliations establish organization coauthorship.
    for output in outputs.values():
        affiliations=output['affiliations'];ids=sorted({item['entity_id'] for item in affiliations})
        if len(ids)<2:continue
        anchors=[]; anchored_entities=set()
        for affiliation in affiliations:
            for checked in findings.get('source_checks',{}).get('proofs',[]):
                if _has(checked['quote'],affiliation['author_id']) and _has(checked['quote'],affiliation['raw_affiliation']):
                    try:
                        anchor=proof(RelationProof(evidence_id=checked['evidence_id'],quote=checked['quote']))
                        if anchor not in anchors:anchors.append(anchor)
                        anchored_entities.add(affiliation['entity_id'])
                    except ValueError:pass
        if not set(ids)<=anchored_entities or not set(ids)<=set(entities):
            pending.append({'kind':'coauthorship','output_id':output['output_id'],'reason':'retained_affiliation_proofs_unavailable'});continue
        records.append({'relationship_id':'coauthor:'+output['output_id'],'kind':'coauthorship','name':output['title'],
            'entity_ids':ids,'related_output_id':output['output_id'],'stage':'publication_observation','polarity':'positive',
            'status':'literal_affiliations_checked_not_partnership','proofs':anchors,
            'event_time':{'lower':output['published_on'],'upper':output.get('published_until') or output['published_on'],
                'precision':output.get('date_precision','day'),'basis':'publication_date_not_relationship_duration'},
            'gaps':['共著不证明正式协议、主导方、当前合作持续性或战略关系。']})
        for affiliation in affiliations:
            # Preserve address text, without guessing country boundaries or geocoding.
            matching=next((anchor for anchor in anchors if _has(anchor['quote'],affiliation['raw_affiliation'])),None)
            if matching:
                locations.append({'entity_id':affiliation['entity_id'],'place':affiliation['raw_affiliation'],
                    'kind':'publication_affiliation','related_output_id':output['output_id'],'proof':matching,
                    'time_basis':'publication_date','is_rd_site':False,'status':'literal_affiliation_address_not_current_site'})

    seen=set(item['relationship_id'] for item in records)
    for item in bounded('research_relationships',RelationshipObservation,200):
        try:
            item=item.model_copy(update={'related_output_id':findings.get('publication_id_aliases',{}).get(item.related_output_id,item.related_output_id)})
            if item.relationship_id in seen or len(set(item.entity_ids))!=len(item.entity_ids):
                raise ValueError('duplicate relation or party IDs')
            if not set(item.party_roles)<=set(item.entity_ids):
                raise ValueError('party roles must reference this relationship')
            if any(key not in entities for key in item.entity_ids):
                raise ValueError('relationship has unknown party IDs')
            if not any(entities[key].get('selected') for key in item.entity_ids) and item.related_output_id not in outputs:
                # A declared lab may be the recipient; require an explicit selected party too.
                raise ValueError('relationship must involve a selected research object')
            if len(item.entity_ids)<2 and not item.related_output_id:
                raise ValueError('relationship requires two named parties or a named funder and accepted work')
            anchor=proof(item.proof);text=anchor['quote'];source=sources[anchor['evidence_id']]
            if not all(identity_in(key,text) for key in item.entity_ids):
                raise ValueError('relation proof must identify every named party')
            if item.related_output_id:
                output=outputs.get(item.related_output_id)
                if not output or _publication_url(source['source_url']) not in {_publication_url(url) for url in output['source_urls']}:
                    raise ValueError('funded work is unavailable or proof belongs to another primary work')
            cue=re.search(CUES[item.kind],text,re.I)
            if not cue:
                raise ValueError('coauthorship or generic cooperation is not this relation type')
            denial=re.search(r'\b(?:no|not|never|without)\b.{0,45}(?:'+CUES[item.kind]+r')|(?:未|没有|并未).{0,10}(?:建立|资助|合作|设立|访问)',text,re.I)
            polarity='negative' if denial else item.polarity
            # Tie future wording to the relation's sentence, not another event
            # elsewhere in a multi-event proof paragraph.
            sentence_start=max([text.rfind(mark,0,cue.start()) for mark in ('。',';','!','?','\n')]+[-1])+1
            ends=[index for mark in ('。',';','!','?','\n') if (index:=text.find(mark,cue.end()))>=0]
            relation_sentence=text[sentence_start:min(ends) if ends else len(text)]
            stage='planned' if re.search(r'\bwill\b|\bplans?\b|\bpropos\w*\b|将在|拟立项|计划|拟设',relation_sentence,re.I) else item.stage
            status='source_denial_requires_review' if polarity=='negative' else 'uncertain_source_claim' if polarity=='uncertain' else 'source_assertion_requires_review'
            event_time={'lower':None,'upper':None,'precision':'unknown','basis':'unknown_not_retrieval_or_publication_date'}
            gaps=[]
            if item.event_date:
                try:
                    if not item.date_proof:raise ValueError('event date needs a separate literal proof')
                    date_anchor=proof(item.date_proof)
                    if date_anchor['evidence_id']!=anchor['evidence_id']:raise ValueError('date must be tied to the same event source')
                    lower,upper,precision=_date_bounds(item.event_date)
                    if not _date_literal_present(item.event_date,date_anchor['quote']):
                        raise ValueError('date values are absent at the declared precision')
                    event_time={'lower':lower.isoformat(),'upper':upper.isoformat(),'precision':precision,'basis':'explicit_event_source','proof':date_anchor}
                    if upper.isoformat()<scope['start_date'] or lower.isoformat()>scope['end_date']:status='event_outside_requested_period'
                except ValueError as error:gaps.append(str(error))
            else:gaps.append('事件时间未知；不把发布时间、采集日或持续若干年换算成事件日期／到期日。')
            counter=[]
            if item.kind=='funding' and item.related_output_id and polarity=='positive':
                for match in re.finditer(r'no\s+(?:specific\s+)?funding|received\s+no\s+funding|未(?:获得|接受).{0,12}资助',source['content'],re.I):
                    start=max(0,source['content'].rfind('\n',0,match.start())+1)
                    end=source['content'].find('\n',match.end());end=len(source['content']) if end<0 else end
                    counter.append({'evidence_id':anchor['evidence_id'],'source_url':source['source_url'],
                        'start':start,'end':end,'quote':source['content'][start:end]})
                if counter:status='potential_conflict_requires_review';gaps.append('同一成果页面另有未获资助陈述；先核对资助口径，不静默采纳任一说法。')
            records.append({'relationship_id':item.relationship_id,'kind':item.kind,'name':item.name,
                'entity_ids':list(item.entity_ids),'related_output_id':item.related_output_id,'stage':stage,'polarity':polarity,
                'party_roles':item.party_roles,
                'status':status,'proofs':[anchor],'event_time':event_time,'counter_evidence':counter,
                'gaps':gaps+(['经费承诺不证明已到账、实际拨付或未来兑现。'] if item.kind=='funding' else [])})
            seen.add(item.relationship_id)
        except ValueError as error:pending.append({'kind':item.kind,'relationship_id':item.relationship_id,'reason':str(error)})

    for item in bounded('geographies',LocationObservation,100):
        try:
            if item.entity_id not in entities:raise ValueError('location has unknown entity ID')
            anchor=proof(item.proof)
            if not identity_in(item.entity_id,anchor['quote']) or not _has(anchor['quote'],item.place):
                raise ValueError('location must quote organization and place together')
            if item.relationship_id and item.relationship_id not in seen:raise ValueError('event location references unavailable event')
            if item.kind=='rd_site' and not re.search(r'(?:research|development|R&D)\s+(?:cent(?:er|re)|site|campus)|研发中心|研究中心|研发基地',anchor['quote'],re.I):
                raise ValueError('partner or event geography does not establish an R&D site')
            locations.append({'entity_id':item.entity_id,'place':item.place,'kind':item.kind,'proof':anchor,
                'relationship_id':item.relationship_id,'is_rd_site':False,'rd_site_claim':item.kind=='rd_site',
                'status':'explicit_site_claim_requires_review' if item.kind=='rd_site' else 'source_geography_not_rd_site',
                'time_basis':'event_time_if_linked_otherwise_unknown'})
        except ValueError as error:pending.append({'kind':'geography','entity_id':item.entity_id,'reason':str(error)})

    pair_observations=defaultdict(list)
    for row in records:
        if row['kind']=='coauthorship':
            for pair in combinations(row['entity_ids'],2):pair_observations[pair].append(row)
    pairs=[{'entity_ids':list(pair),'publication_count':len({row['related_output_id'] for row in rows}),
        'publication_ids':sorted({row['related_output_id'] for row in rows}),
        'first_observed_lower':min(row['event_time']['lower'] for row in rows),
        'last_observed_upper':max(row['event_time']['upper'] for row in rows),
        'continuity':'observed_publications_only_not_continuous_contract'} for pair,rows in pair_observations.items()]
    counts=Counter(row['kind'] for row in records)
    return {'schema_version':VERSION,'origin':origin,'entities':list(entities.values()),'records':records,
        'locations':locations,'pending_records':pending,'coauthor_pairs':pairs,
        'coverage':{kind:{'observations':counts[kind],'status':'source_observations_require_review' if counts[kind] else 'not_established_not_absent'} for kind in KINDS},
        'counting_unit':'source_relationship_observation_not_publication_or_contract_count',
        'limits':{'relationships':200,'counterparties':100,'locations':100,'proof_characters':2400},
        'boundaries':['共著、资助、项目、联合实验室与交流分开；共著频次不等于战略协议或合作成功率。',
            '伙伴、署名与活动所在地不等于目标组织研发中心，不由地点推断投资或内部组织布局。',
            '事件时间与关系有效期分开，未知不补日期；经费承诺不等于到账，源陈述与独立核实分开。',
            '未建立关系不代表关系不存在；本次只覆盖已取得来源，当前任职不覆盖历史署名。'],
        'effects':{'network_requests':0,'model_calls':0,'scope_expanded':False}}


def relationship_markdown(view):
    if not view:return ''
    def safe(value):return str(value).replace('|','\\|').replace('<','&lt;').replace('>','&gt;').replace('\n',' ')
    names={item['entity_id']:item['name'] for item in view['entities']}
    lines=['\n\n## 关系来源、时间与地域边界', '规则：'+VERSION, *view['boundaries'],
        '| 类型 | 来源中的事项 | 参与方 | 事件时间／精度 | 状态／阶段 |','| --- | --- | --- | --- | --- |']
    for row in view['records']:
        time=row['event_time'];dates=f"{time['lower']}..{time['upper']} ({time['precision']})" if time['lower'] else '未知'
        lines.append('| '+' | '.join([KINDS[row['kind']],safe(row['name']),safe('、'.join(names.get(key,key) for key in row['entity_ids'])),dates,safe(row['status']+' / '+row['stage'])])+' |')
    lines.append('\n### 关系来源定位')
    for row in view['records']:
        lines.append('\n'+safe(row['name']))
        for anchor in row['proofs']:
            lines.append(f"\n来源 {safe(anchor['evidence_id'])}：<{quote(anchor['source_url'],safe=':/?#=&%+@~!$*,;()-_.')}>；原文字符 {anchor['start']}–{anchor['end']}。\n")
    for kind,coverage in view['coverage'].items():
        if not coverage['observations']:lines.append(f"- {KINDS[kind]}：本样本未建立，不等于不存在。")
    for item in view['locations']:lines.append(f"- {safe(names[item['entity_id']])}：{safe(item['place'])}（{item['kind']}；{item['status']}）。")
    for item in view['pending_records']:lines.append('- 待核：'+safe(item['reason']))
    return '\n'.join(lines)


def relationship_context(view):
    if not view:return None
    return {**{key:view[key] for key in ('schema_version','origin','coverage','boundaries')},
        'records':view['records'][:20],'locations':view['locations'][:20],
        'pending_records':view['pending_records'][:20],
        'retained_record_count':len(view['records']),'context_record_count':min(20,len(view['records'])),
        'context_note':'完整关系与原文位置保存在结果／附录；这里仅提供有界上下文，不据截断推断缺失或零值。'}
