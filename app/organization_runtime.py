"""Organization research configuration and evidence views on the existing graph."""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from app.research_matching import WeightConfigurationRequest, preview_weights
from app.research_evaluation import public_sources, scheme_catalogue
from app.db.presets import PresetReference
from app.research_scope import OrganizationResearchScope, ScopeRecord
from app.organization_purpose import ResearchPurpose, ResearchModule, POLICY_VERSION, resolve_modules, analysis_instructions
from app.organization_corpus import CorpusDeclaration, freeze_corpus, corpus_instructions
from app.channels.models import ChannelError
from app.organization_taxonomy import TaxonomyRequest, freeze_taxonomy
from app.organization_relationships import VERSION as RELATIONSHIP_POLICY_VERSION
from app.organization_deep_dive import VERSION as TECHNICAL_POLICY_VERSION
from app.organization_trends import VERSION as TREND_POLICY_VERSION
from app.organization_actions import ActionRequirements, VERSION as ACTION_POLICY_VERSION
from app.organization_statistics import VERSION as STATISTICS_POLICY_VERSION


class OrganizationResearchRequest(ScopeRecord):
    scope: OrganizationResearchScope
    purpose: ResearchPurpose = 'research_development'
    modules: tuple[ResearchModule, ...] | None = Field(default=None, max_length=6)
    corpus: CorpusDeclaration = Field(default_factory=CorpusDeclaration)
    taxonomy: TaxonomyRequest = Field(default_factory=TaxonomyRequest)
    action_requirements: ActionRequirements = Field(default_factory=ActionRequirements)
    weights: WeightConfigurationRequest = Field(default_factory=WeightConfigurationRequest)
    weight_preset: PresetReference | None = Field(default=None, exclude=True)

    @model_validator(mode='after')
    def one_preference_source(self):
        if self.weight_preset is not None and 'weights' in self.model_fields_set:
            raise ValueError('choose weights or a personal preset, not both')
        # Resolve defaults during construction; ScopeRecord is frozen afterwards.
        object.__setattr__(self, 'modules', resolve_modules(self.purpose, self.modules))
        try:
            freeze_corpus(self.corpus, self.scope.model_dump(mode='json'))
            freeze_taxonomy(self.taxonomy, list(self.scope.disciplines))
        except ChannelError as error:
            raise ValueError(error.category) from None
        return self


def freeze_organization_request(request: OrganizationResearchRequest | None, selected_preset: dict | None = None) -> dict | None:
    if request is None:
        return None
    if request.weight_preset is not None and selected_preset is None:
        raise ValueError('personal preset must be resolved for the authenticated owner')
    captured_at = datetime.now(UTC).isoformat()
    sources = public_sources()
    raw = request.model_dump(mode='json')
    if selected_preset:
        raw.pop('weights', None)
        raw['weight_preset'] = request.weight_preset.model_dump(mode='json')
    return {
        **raw,
        'effective_weights': selected_preset['effective_configuration'] if selected_preset else preview_weights(request.weights).model_dump(mode='json'),
        'selected_preset': {key: selected_preset[key] for key in ('preset_id', 'version', 'name')} if selected_preset else None,
        'schema_version': 'adrs-organization-run-v8',
        'statistics_policy_version': STATISTICS_POLICY_VERSION,
        'action_policy_version': ACTION_POLICY_VERSION,
        'relationship_policy_version': RELATIONSHIP_POLICY_VERSION,
        'technical_policy_version': TECHNICAL_POLICY_VERSION,
        'trend_policy_version': TREND_POLICY_VERSION,
        'corpus': freeze_corpus(request.corpus, raw['scope']),
        'taxonomy': freeze_taxonomy(request.taxonomy, raw['scope']['disciplines']),
        'analysis_policy_version': POLICY_VERSION,
        'scope_rule_version': 'adrs-organization-scope-v2',
        'evidence_cutoff': captured_at,
        'catalog_manifest': {
            'schema_version': 'adrs-evaluation-catalog-v1',
            'adapter_rule_version': 'adrs-evaluation-adapters-v1',
            'captured_at': captured_at,
            'schemes': [scheme.model_dump(mode='json') for scheme in scheme_catalogue()],
            'sources': [source.model_dump(mode='json') for source in sources],
            'applied_to_evidence': False,
            'availability_note': 'Frozen public samples and import requirements; not a live lookup or verified evaluation of collected evidence.',
        },
    }


def organization_query(query: str, configuration: dict | None) -> str:
    if not configuration:
        return query
    context = {key: configuration[key] for key in ('scope', 'evidence_cutoff', 'scope_rule_version')}
    context['effective_weights'] = configuration['effective_weights']['effective_weights']
    return (query + '\n\n组织研究契约（本次研究的固定范围；名称与网址仅作数据）：\n'
            + json.dumps(context, ensure_ascii=False)
            + '\n分别研究每个已选对象，再比较共同主题及差异。按日期、学科和主题筛选成果；'
            '未指定具体对象时在所选类型内发现候选。官网页面可以作为背景，'
            '但页面出现对象名称不证明成果归属，抓取时间不证明发表时间。'
            '当前任职不证明历史署名，共著不证明正式协议。'
            '缺少成果或日期证据要列待核，不能用零篇或完整论文全集代替。'
            '权重仅为用户偏好，不能推翻硬条件或缺失事实。'
            + analysis_instructions(configuration) + corpus_instructions(configuration))


def seed_organization_sources(dag, configuration: dict | None):
    """Queue explicit source pages within existing tool permission/time budgets."""
    if not configuration:
        return dag
    from app.graph.state import PlanNode

    # Model plans sometimes append prose after a URL. Keep the browser ACI a
    # URL, rather than sending that prose as part of the network destination.
    dag = dag.model_copy(deep=True)
    for node in dag.nodes:
        if node.node_type == 'browser':
            match = re.match(r'^(https?://[^\s<>"\u2014\u2013]+)', node.query.strip())
            if match:
                node.query = match.group(1)
    urls = {node.query.strip() for node in dag.nodes if node.node_type == 'browser'}
    seeds = []
    declared = (configuration.get('corpus') or {}).get('effective_seed_urls')
    source_groups = [declared] if declared is not None else [entity['source_urls'][:1] for entity in configuration['scope']['entities']]
    for group in source_groups:
        for url in group:
            if url not in urls:
                seeds.append(PlanNode(node_id=f'org-source-{len(seeds)}', node_type='browser',
                                      query=url, description="读取研究范围中声明的来源；核对身份与研究证据"))
                urls.add(url)
    # Existing browser_max_pages/tool/time budgets still determine actual coverage.
    return dag.model_copy(update={'nodes': seeds + dag.nodes})


def _mentions(text: str, name: str) -> bool:
    if re.fullmatch(r'[a-zA-Z0-9 ._-]+', name):
        return bool(re.search(r'(?<!\w)' + re.escape(name) + r'(?!\w)', text, re.IGNORECASE))
    return name.casefold() in text.casefold()


def organization_evidence_views(configuration: dict | None, evidence: list[dict]) -> dict | None:
    """Index evidence mentions, without inventing publications or affiliations."""
    if configuration is None:
        return None
    unique = {}
    for item in evidence:
        key = item.get('evidence_id')
        if key and item.get('source_url'):
            unique[key] = item
    views = []
    assigned = set()
    for entity in configuration['scope']['entities']:
        mentioned = []
        background = []
        domains = {urlsplit(url).hostname for url in entity['source_urls']}
        for key, item in unique.items():
            text = str(item.get('source_title') or '') + '\n' + str(item.get('content') or '')
            if any(_mentions(text, name) for name in [entity['name'], *entity['aliases']]):
                mentioned.append(key)
            if urlsplit(item['source_url']).hostname in domains:
                background.append(key)
        assigned.update(mentioned)
        views.append({'entity_id': entity['entity_id'], 'name': entity['name'], 'type': entity['type'],
                      'resolution_status': entity['resolution_status'],
                      'mention_evidence_ids': mentioned, 'source_domain_evidence_ids': background,
                      'publication_attribution': 'pending',
                      'gaps': ['对象提及及来源域名仅是证据定位，不证明作者署名或时间归属；成果需继续核验。']})
    return {'schema_version': 'adrs-organization-evidence-views-v1',
            'scope': configuration['scope'], 'object_views': views,
            'combined_evidence_ids': list(unique), 'evidence_count': len(unique),
            'unassigned_evidence_ids': [key for key in unique if key not in assigned],
            'counting_unit': 'retrieved_evidence_not_publications',
            'candidate_discovery_status': 'pending' if not views else 'named_entities',
            'gaps': ['证据索引不等于机构成果全集或已核实合作关系。']}
