"""Purpose-specific research routes and conditional cooperation action cards."""
from __future__ import annotations

from datetime import datetime
import re
from app.publication_literals import source_pattern
from typing import Annotated, Literal
from urllib.parse import quote, urlsplit

from pydantic import Field
from app.research_scope import Identifier, ScopeRecord
from app.research_matching import MetricCondition, RelationKind, WeightConfigurationRequest
from app.organization_relationships import RelationProof

VERSION='adrs-purpose-actions-v1'
Text=Annotated[str,Field(min_length=3,max_length=1200)]


class ActionRequirements(ScopeRecord):
    research_goal:Text|None=None
    cooperation_goal:Text|None=None
    offering:Text|None=None
    time_window:Text|None=None
    constraints:tuple[Text,...]=Field(default=(),max_length=12)
    required_relations:tuple[RelationKind,...]=Field(default=(),max_length=4)
    required_metrics:tuple[MetricCondition,...]=Field(default=(),max_length=20)


class ContactPointer(ScopeRecord):
    evidence_id:Identifier
    url:str=Field(min_length=8,max_length=2000)


class ActionProposal(ScopeRecord):
    action_id:Identifier
    entity_id:Identifier
    mode:Literal['research_validation','cooperation']
    question:Text
    basis:tuple[RelationProof,...]=Field(min_length=1,max_length=5)
    complementary_hypothesis:Text|None=None
    steps:tuple[Text,...]=Field(default=(),max_length=8)
    public_contacts:tuple[ContactPointer,...]=Field(default=(),max_length=5)


class ActionPreviewRequest(ScopeRecord):
    requirements:ActionRequirements=Field(default_factory=ActionRequirements)
    action_cards:tuple[ActionProposal,...]=Field(default=(),max_length=20)
    weights:WeightConfigurationRequest|None=None


def action_instructions(config):
    if 'actions' not in (config or {}).get('modules',[]):return ''
    return '''\nPurpose-specific actions: add "action_cards" INSIDE organization_data.
Shape: [{"action_id":"id","entity_id":"SELECTED ID","mode":"research_validation|cooperation","question":"a concrete question to validate or discuss","basis":[{"evidence_id":"ev-ID","quote":"literal supporting source"}],"complementary_hypothesis":null,"steps":["bounded proposed next step, not already performed"],"public_contacts":[]}].
Use research_validation for research development; cooperation for cooperation discovery; comprehensive may contain both. Missing cooperation_goal/offering/time_window are missing requirements, never fill them using model guesses. Use only retained sources for actual people/teams/contact pointers; historical author affiliation does not prove present employment or contactability. A public contact pointer needs the exact URL in a retained original public link, not an invented URL or email. Suggestions do not send messages or publish. Priority, scores, hard conditions and confirmed relationship status are computed by the server; do not supply or invent them. Keep 1–3 compact action cards. The raw action requirements are user constraints, not proof of feasibility.'''


def frozen_weight_request(config):
    frozen=config['effective_weights'];raw=frozen.get('raw_config') or {}
    return WeightConfigurationRequest.model_validate({'preset':'custom','config_version':frozen['config_version'],
        'weights':raw.get('weights') or frozen['effective_weights'],
        'performance_groups':raw.get('performance_groups',{'venue':1.0,'paper':1.0}),
        'metric_weights':raw.get('metric_weights',{}),'mappings':frozen.get('mappings',[])})


def build_action_view(config,findings,evidence,proposals=None,*,requirements=None,weights=None,state=None):
    from app.channels.execution import public_url
    from app.channels.models import ChannelError
    from app.organization_corpus import source_scope
    from app.research_matching import score_matching_snapshot
    from app.research_matching_bridge import snapshot_from_research
    findings,proposals,state=findings or {},proposals or {},state or {}
    request=requirements or ActionRequirements.model_validate(config.get('action_requirements') or {})
    sources={item['evidence_id']:item for item in evidence if item.get('evidence_id') and item.get('source_url')}
    scoped=findings.get('scope_result') or {}
    entities={item['entity_id']:item for item in scoped.get('selected_entities',config['scope']['entities'])}
    purpose=config.get('purpose','research_development')
    modes={'research_development':('research_validation',),'cooperation_discovery':('cooperation',),'comprehensive':('research_validation','cooperation')}[purpose]
    pending=[];proposed={};values=proposals.get('action_cards',[])
    if not isinstance(values,list):values=[];pending.append({'reason':'action_cards_expected_array'})
    if len(values)>20:pending.append({'reason':'action_card_limit_20','received_count':len(values)})
    def proof(value):
        source=sources.get(value.evidence_id)
        if not source or (source.get('acquisition') or {}).get('coverage')=='discovery_only':raise ValueError('action basis requires acquired source evidence')
        match=re.search(source_pattern(value.quote,config),source.get('content') or '',re.I)
        if not match:raise ValueError('action basis is absent from retained original')
        return {'evidence_id':value.evidence_id,'source_url':source['source_url'],'start':match.start(),'end':match.end(),'quote':match.group()}
    for raw in values[:20]:
        try:
            item=ActionProposal.model_validate(raw)
            if item.entity_id not in entities or item.mode not in modes:raise ValueError('action target or mode is outside selected research purpose')
            key=(item.entity_id,item.mode)
            if key in proposed:raise ValueError('duplicate target/mode action')
            anchors=[proof(value) for value in item.basis]
            names=[entities[item.entity_id]['name'],*entities[item.entity_id].get('aliases',[])]
            if not any(any(re.search(r'\s+'.join(re.escape(word) for word in name.split()),sources[anchor['evidence_id']]['content'],re.I) for name in names) for anchor in anchors):
                raise ValueError('action source does not identify its target')
            contacts=[]
            for pointer in item.public_contacts:
                source=sources.get(pointer.evidence_id)
                if not source or pointer.url not in (source.get('acquisition') or {}).get('public_links',[]):
                    pending.append({'action_id':item.action_id,'reason':'contact_URL_not_retained_as_original_public_link'});continue
                try:
                    public_url(pointer.url)
                    policy=source_scope(config)
                    if policy:policy.admit(pointer.url,for_read=False)
                except (ValueError,ChannelError):
                    pending.append({'action_id':item.action_id,'reason':'contact_URL_not_admissible'});continue
                contacts.append({'url':pointer.url,'evidence_id':pointer.evidence_id,'source_url':source['source_url'],
                    'status':'published_pointer_identity_and_current_contactability_unverified','basis':'retained_original_anchor_href'})
            proposed[key]={'action_id':item.action_id,'question':item.question,'basis':anchors,'steps':list(item.steps),
                'complementary_hypothesis':item.complementary_hypothesis,'public_contacts':contacts}
        except (ValueError,KeyError) as error:pending.append({'reason':str(error)[:450]})

    priority=None;priority_gap=None
    try:
        session_id=state.get('task_id');execution_id=(state.get('session') or {}).get('execution_id')
        if not session_id or not execution_id:raise ValueError('real_run_provenance_required_for_priority')
        dates=[datetime.fromisoformat(config['evidence_cutoff']).date()]
        dates += [datetime.fromisoformat(item['collected_at']).date() for item in sources.values() if item.get('collected_at')]
        if state.get('completed_at'):dates.append(datetime.fromisoformat(state['completed_at']).date())
        snapshot=snapshot_from_research(session_id,execution_id,max(dates),config,findings,
            {'collected_evidence':evidence},origin='saved_research' if state.get('status')=='completed' else 'running_research')
        # The original bridge leaves unverified relation facts unknown. Neither
        # a generated card nor a high score can promote them to confirmed.
        snapshot=snapshot.model_copy(update={'required_relations':request.required_relations,'required_metrics':request.required_metrics})
        priority=score_matching_snapshot(snapshot,weights or frozen_weight_request(config),'action-priority:'+session_id).model_dump(mode='json')
    except (ValueError,KeyError,TypeError) as error:priority_gap=str(error)[:500]
    rows={};exclusions={}
    if priority:
        for group in priority['groups']:
            for row in group['complete']+group['pending_evidence']:
                rows.setdefault(row['entity_id'],[]).append({'group_id':group['group_id'],'context':group['context'],
                    'effective_weights':group['effective_weights'],**row})
        exclusions={item['entity_id']:item['reasons'] for item in priority['excluded']}

    cards=[];pairs=list(proposed) or [(identity,mode) for identity in entities for mode in modes][:20]
    relationship_records=(findings.get('relationship_view') or {}).get('records',[])
    for identity,mode in pairs:
        proposal=proposed.get((identity,mode));entity=entities[identity]
        missing=[]
        if mode=='cooperation':
            for key in ('cooperation_goal','offering','time_window'):
                if not getattr(request,key):missing.append(key)
        elif not (request.research_goal or config['scope']['topic']):missing.append('research_goal')
        relevant=[record for record in relationship_records if identity in record['entity_ids']]
        people={}
        for output in scoped.get('outputs',[]):
            for affiliation in output['affiliations']:
                if affiliation['entity_id']==identity:
                    person=people.setdefault(affiliation['author_id'],{'name':affiliation['author_id'],'publication_ids':[],
                        'status':'historical_author_affiliation_not_current_job_or_contactability'})
                    if output['output_id'] not in person['publication_ids']:person['publication_ids'].append(output['output_id'])
        excluded=exclusions.get(identity,[])
        priorities=rows.get(identity,[])
        status='needs_requirements' if missing else 'hard_conditions_not_established' if excluded else 'needs_source_grounded_action' if not proposal else 'conditional_research_route' if mode=='research_validation' else 'needs_feasibility_and_contact_review'
        cards.append({'action_id':proposal['action_id'] if proposal else 'pending:'+identity+':'+mode,'entity_id':identity,'entity_name':entity['name'],
            'mode':mode,'status':status,'question':proposal['question'] if proposal else None,
            'basis':proposal['basis'] if proposal else [],'proposed_steps':proposal['steps'] if proposal else [],
            'complementary_hypothesis':proposal['complementary_hypothesis'] if proposal else None,
            'public_contacts':proposal['public_contacts'] if proposal else [],'missing_requirements':missing,
            'goal':request.cooperation_goal if mode=='cooperation' else request.research_goal or config['scope']['topic'],
            'unverified_constraints':list(request.constraints),'priority_groups':priorities,'hard_condition_reasons':excluded,
            'related_people':list(people.values())[:50],'related_people_count':len(people),
            'relationship_observations':relevant[:25],'relationship_observation_count':len(relevant),
            'operational_readiness':'not_established','outbound_action_taken':False,
            'priority_semantics':'按冻结范围与当前偏好的样本契合度；缺项保留区间，不代表质量、可联系性或合作成功率。'})
    return {'schema_version':VERSION,'purpose':purpose,'purpose_basis':'frozen_request' if 'purpose' in config else 'legacy_research_validation_default',
        'allowed_modes':list(modes),'requirements':request.model_dump(mode='json'),
        'cards':cards,'pending_records':pending,'priority_preview':priority,'priority_gap':priority_gap,
        'frozen_weight_configuration':config['effective_weights'],'weight_source':'explicit_preview_override' if weights else 'original_frozen_run_configuration',
        'boundaries':['需求不足先补研究目标、可提供资源及时间要求，不由模型代填。',
            '优先级复用原硬条件、分层权重、家族聚合与缺失区间，不通过评分改写关系状态。',
            '人员信息仅反映已得发表署名，不代表现任职、可联系或合作可行；生成建议不发起外部联系。',
            '不同学科／载体保持分组，未知不补零，区间重叠不输出确定优劣。'],
        'effects':{'network_requests':0,'model_calls':0,'messages_sent':0,'original_report_modified':False}}


def action_context(view):
    if not view:return None
    cards=[]
    for card in view['cards'][:5]:
        selected={key:card[key] for key in ('action_id','entity_id','entity_name','mode','status','question','proposed_steps',
            'complementary_hypothesis','missing_requirements','goal','unverified_constraints','hard_condition_reasons')}
        selected['basis_references']=[{key:proof[key] for key in ('evidence_id','start','end')} for proof in card['basis']]
        selected['priority_groups']=[{key:group.get(key) for key in ('group_id','score','lower_bound','upper_bound','coverage','missing_dimensions')} for group in card['priority_groups']]
        cards.append(selected)
    return {**{key:view[key] for key in ('schema_version','purpose','requirements','priority_gap','boundaries')},
        'cards':cards,'retained_card_count':len(view['cards']),'context_note':'完整来源／关系／人员与贡献保存在结果；此处只传有界引用。'}


def action_markdown(view):
    if not view:return ''
    def safe(value):return str(value).replace('<','&lt;').replace('>','&gt;').replace('|','\\|').replace('\n',' ')
    lines=['\n\n## 研究验证路线与条件行动卡','规则：'+VERSION,*view['boundaries']]
    for card in view['cards']:
        lines+=['\n### '+safe(card['entity_name']),f"{card['mode']} · {card['status']}",safe(card['question'] or '尚无有原文依据的验证议题，需补证。')]
        if card['missing_requirements']:lines.append('- 待补需求：'+', '.join(card['missing_requirements']))
        for reason in card['hard_condition_reasons']:lines.append('- 硬条件：'+safe(reason))
        for group in card['priority_groups']:
            lines.append(f"- 比较组 {safe(group['group_id'])}：区间 {group['lower_bound']}–{group['upper_bound']}，覆盖率 {group['coverage']}；不是合作成功概率。")
        for step in card['proposed_steps']:lines.append('- 建议下一步（未执行）：'+safe(step))
        for basis in card['basis']:lines.append(f"- 原文 {safe(basis['evidence_id'])} 字符 {basis['start']}–{basis['end']}：<{quote(basis['source_url'],safe=':/?#=&%+@~!$*,;()-_.')}>。")
    if view['priority_gap']:lines.append('匹配缺口：'+safe(view['priority_gap']))
    return '\n'.join(lines)
