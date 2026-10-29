"""Source-bound evolution, external corroboration and conditional scenarios."""
from __future__ import annotations

from datetime import date
import re
from app.publication_literals import source_pattern
from typing import Annotated, Literal
from urllib.parse import urlsplit, quote

from pydantic import Field
from app.research_scope import Identifier, ScopeRecord
from app.organization_relationships import RelationProof

VERSION='adrs-trend-evidence-v1'
Hypothesis=Annotated[str,Field(min_length=3,max_length=1000)]


class TrendProposal(ScopeRecord):
    trend_id:Identifier
    entity_ids:tuple[Identifier,...]=Field(min_length=1,max_length=20)
    kind:Literal['observation','inference','scenario']
    claim_domain:Literal['research_topic','resource_investment','deployment','future_direction']='research_topic'
    statement:str=Field(min_length=3,max_length=2000)
    supporting:tuple[RelationProof,...]=Field(min_length=1,max_length=6)
    opposing:tuple[RelationProof,...]=Field(default=(),max_length=6)
    alternative_explanations:tuple[Hypothesis,...]=Field(default=(),max_length=8)
    conditions:tuple[Hypothesis,...]=Field(default=(),max_length=8)
    horizon_start:date|None=None
    horizon_end:date|None=None


class TrendPreviewRequest(ScopeRecord):
    trend_observations:tuple[TrendProposal,...]=Field(default=(),max_length=50)


def trend_instructions(config):
    if not {'evolution','validation'}&set((config or {}).get('modules',[])):return ''
    return '''\nTrend/corroboration: add "trend_observations" INSIDE organization_data.
Shape: [{"trend_id":"id","entity_ids":["SELECTED ID"],"kind":"observation|inference|scenario","claim_domain":"research_topic|resource_investment|deployment|future_direction","statement":"source observation, bounded inference or conditional future scenario","supporting":[{"evidence_id":"ev-ID","quote":"literal supporting text"}],"opposing":[],"alternative_explanations":["hypothesis, not an established fact"],"conditions":["condition to validate"],"horizon_start":null,"horizon_end":null}].
Use only existing acquired evidence, not search snippets. Explicitly separate observed changes from changing sample coverage or taxonomy. One year's paper is insufficient for a multi-year organizational trend. Quantity does not prove funding, staffing, internal priority or maturity. Patent similarity and papers do not prove product deployment. Deployment observations need explicit actual deployment in a relevant official document; plans are not deployments. For inferences include alternative explanations; scenarios additionally need nonempty conditions and a future start/end horizon. Missing contradicting evidence is a gap, not proof of unanimity. Do not invent external sources to fill a field. Keep 1–3 concise records and return complete JSON.'''


def _pattern(value):return r'\s+'.join(re.escape(token) for token in value.split())


def source_role(source,config,findings):
    from app.organization_findings import _publication_url
    url=source['source_url'];host=(urlsplit(url).hostname or '').lower()
    if any(host==domain or host.endswith('.'+domain) for domain in ('patents.google.com','patentscope.wipo.int','cnipa.gov.cn','epo.org')):
        return 'patent_document_not_deployment_evidence'
    for output in (findings.get('scope_result') or {}).get('outputs',[]):
        if _publication_url(url) in {_publication_url(item) for item in output['source_urls']}:return 'primary_publication'
    policy=(config.get('corpus') or {}).get('source_scope') or {}
    if any(host==domain or host.endswith('.'+domain) for domain in policy.get('official_domains',[])):
        return 'declared_official_document_entity_and_claim_require_review'
    if host=='arxiv.org' or host.endswith('.arxiv.org'):return 'preprint'
    if host in {'github.com','zenodo.org','figshare.com'}:return 'repository_or_dataset_identity_requires_review'
    return 'other_acquired_source_not_automatically_official'


def build_trend_view(config,findings,evidence,proposals=None):
    findings,proposals=findings or {},proposals or {};sources={item['evidence_id']:item for item in evidence if item.get('evidence_id') and item.get('source_url')}
    entities={item['entity_id']:item for item in (findings.get('scope_result') or {}).get('selected_entities',config['scope']['entities'])}
    records=[];pending=[];seen=set();values=proposals.get('trend_observations',[])
    if not isinstance(values,list):values=[];pending.append({'reason':'trend_observations_expected_array'})
    def anchor(proof):
        source=sources.get(proof.evidence_id)
        if not source or (source.get('acquisition') or {}).get('coverage')=='discovery_only':raise ValueError('support must be acquired retained evidence')
        match=re.search(source_pattern(proof.quote,config),source.get('content') or '',re.I)
        if not match:raise ValueError('support quote is absent from retained source')
        return {'evidence_id':proof.evidence_id,'source_url':source['source_url'],'start':match.start(),'end':match.end(),
            'quote':match.group(),'source_role':source_role(source,config,findings)}
    if len(values)>50:pending.append({'reason':'trend_record_limit_50'})
    for raw in values[:50]:
        try:
            item=TrendProposal.model_validate(raw)
            if item.trend_id in seen or not set(item.entity_ids)<=set(entities):raise ValueError('duplicate trend or entity outside selected objects')
            supporting=[anchor(proof) for proof in item.supporting];opposing=[anchor(proof) for proof in item.opposing]
            for identity in item.entity_ids:
                names=[entities[identity]['name'],*entities[identity].get('aliases',[])]
                if not any(any(re.search(_pattern(name),sources[proof['evidence_id']]['content'],re.I) for name in names) for proof in supporting):
                    raise ValueError('support_source_does_not_identify_claimed_organization')
            status='source_observation_requires_semantic_review' if item.kind=='observation' else 'bounded_inference_requires_review'
            gaps=[]
            if not opposing:gaps.append('未取得反向材料，不代表不存在反例或已完成独立交叉验证。')
            if item.kind!='observation' and not item.alternative_explanations:
                raise ValueError('inference_or_scenario_requires_alternative_explanations')
            if item.kind=='scenario':
                cutoff=date.fromisoformat(config['evidence_cutoff'][:10])
                if not item.conditions or not item.horizon_start or not item.horizon_end or item.horizon_start<cutoff or item.horizon_end<item.horizon_start:
                    raise ValueError('future_scenario_requires_conditions_and_valid_future_horizon')
                status='conditional_scenario_not_known_internal_plan'
            if item.claim_domain=='future_direction' and item.kind!='scenario':raise ValueError('future_direction_must_be_a_conditional_scenario')
            if item.claim_domain in {'resource_investment','deployment'} and item.kind=='observation':
                official=[proof for proof in supporting if proof['source_role'].startswith('declared_official_document')]
                if not official:raise ValueError('papers_patents_or_quantity_do_not_prove_investment_or_deployment')
                cue=r'deployed|in production|已部署|已上线|投入使用' if item.claim_domain=='deployment' else r'funding|budget|staff|investment|研发投入|经费|预算|人员'
                usable=[proof for proof in official if re.search(cue,proof['quote'],re.I) and not re.search(r'\bwill\b|\bplans?\b|拟|计划|尚未',proof['quote'],re.I)]
                if not usable:raise ValueError('explicit_actual_event_evidence_required_not_a_plan_or_technical_similarity')
                gaps.append('官方来源身份及语义仍需独立核实，字面事件词不等于已经验证的企业内部事实。')
            if item.kind=='observation':
                quoted=' '.join(proof['quote'] for proof in supporting)
                for number in re.findall(r'(?<!\w)\d+(?:\.\d+)?%?',item.statement):
                    if not re.search(r'(?<![\d.])'+re.escape(number)+r'(?![\d.])',quoted):raise ValueError('observation_number_missing_from_support_quotes')
            records.append({**item.model_dump(mode='json'),'supporting':supporting,'opposing':opposing,'status':status,'gaps':gaps,
                'alternative_explanations_status':'hypotheses_to_validate_not_observed_facts',
                'independent_corroboration':'not_established_by_url_or_domain_count',
                'source_domains':sorted({urlsplit(proof['source_url']).hostname or 'local-document' for proof in supporting+opposing})})
            seen.add(item.trend_id)
        except ValueError as error:pending.append({'reason':str(error)[:450]})
    years=sorted({item.get('year') for item in findings.get('publication_metadata',{}).values() if item.get('year') is not None})
    return {'schema_version':VERSION,'records':records,'pending_records':pending,
        'coverage_snapshot':{'sample_years':years,'multiple_sample_years_present':len(years)>=2,'longitudinal_trend_established':False,
            'sufficiency_note':'两个年份仅是最低存在条件，不自动证明可比覆盖或趋势成立。','source_count':len(sources),
            'taxonomy_version':(config.get('taxonomy') or {}).get('version'),'corpus_counts':(findings.get('corpus') or {}).get('counts')},
        'boundaries':['年度数量、来源覆盖、分类规则与技术路线变化分别解释；缺年份不补零。',
            '论文量不等于投入、内部战略或成熟度；相关专利／产品资料不证明成果已部署。',
            '高校／实验室可用学术问题、方法、平台及社会应用解释价值，不强制企业产品关联。',
            '未来方向仅为带期限、条件、依据及待验证信号的情景，不是已知内部计划。'],
        'effects':{'network_requests':0,'model_calls':0,'scope_expanded':False}}


def trend_context(view):
    if not view:return None
    return {**view,'records':view['records'][:8],'pending_records':view['pending_records'][:10],
        'retained_record_count':len(view['records']),'context_record_limit':8}


def trend_markdown(view):
    if not view:return ''
    def safe(value):return str(value).replace('<','&lt;').replace('>','&gt;').replace('|','\\|').replace('\n',' ')
    lines=['\n\n## 演进、交叉材料与条件情景','规则：'+VERSION,*view['boundaries']]
    for item in view['records']:
        lines+=['\n### '+safe(item['trend_id']),f"{item['kind']} · {item['status']}",safe(item['statement'])]
        if item['horizon_start']:lines.append(f"情景期限：{item['horizon_start']} 至 {item['horizon_end']}。")
        lines+=['- 待验证条件：'+safe(text) for text in item['conditions']]
        lines+=['- 替代解释（假设）：'+safe(text) for text in item['alternative_explanations']]
        for key,label in [('supporting','支持'),('opposing','反向材料')]:
            for anchor in item[key]:lines.append(f"- {label} {safe(anchor['evidence_id'])}，原文字符 {anchor['start']}–{anchor['end']}：<{quote(anchor['source_url'],safe=':/?#=&%+@~!$*,;()-_.')}>。")
        lines+=['- 缺口：'+safe(text) for text in item['gaps']]
    for item in view['pending_records']:lines.append('- 待核：'+safe(item['reason']))
    return '\n'.join(lines)
