"""Versioned, source-anchored topic mapping; ordinary functions, no network/model."""
from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import re
from html.parser import HTMLParser
from typing import Literal
from uuid import uuid4

from pydantic import Field, model_validator
from app.research_scope import Identifier, Label, ScopeRecord

RULE_VERSION = 'adrs-disciplinary-mapping-v1'
AXES = ('problem', 'method', 'application')
AXIS_LABELS = {'problem': '问题', 'method': '方法', 'application': '应用'}


class TopicNode(ScopeRecord):
    node_id: Identifier
    label: Label
    discipline: Label
    axis: Literal['problem', 'method', 'application']
    role: Literal['core', 'associated'] = 'core'
    parent_id: Identifier | None = None
    terms: tuple[Label, ...] = Field(default=(), max_length=20)


class TaxonomyRequest(ScopeRecord):
    preset: Literal['auto', 'materials_science', 'computer_science', 'business', 'custom'] = 'auto'
    version: Label = 'topic-policy-v1'
    nodes: tuple[TopicNode, ...] = Field(default=(), max_length=100)

    @model_validator(mode='after')
    def valid_tree(self):
        if (self.preset == 'custom') != bool(self.nodes):
            raise ValueError('custom taxonomy requires nodes; presets do not accept node overrides')
        nodes = {node.node_id: node for node in self.nodes}
        if len(nodes) != len(self.nodes):
            raise ValueError('taxonomy node IDs must be unique')
        for node in self.nodes:
            visited, current = {node.node_id}, node
            while current.parent_id:
                parent = nodes.get(current.parent_id)
                if not parent or parent.axis != node.axis or discipline_key(parent.discipline) != discipline_key(node.discipline):
                    raise ValueError('parent must exist in the same axis and discipline')
                if parent.node_id in visited:
                    raise ValueError('taxonomy hierarchy must be acyclic')
                visited.add(parent.node_id)
                current = parent
            if not node.terms and not any(other.parent_id == node.node_id for other in self.nodes):
                raise ValueError('leaf taxonomy nodes require literal topic terms')
            if any(len(term) < 2 for term in node.terms):
                raise ValueError('topic terms must contain at least two characters')
        return self


class ReclassificationRequest(ScopeRecord):
    taxonomy: TaxonomyRequest
    reason: str = Field(min_length=3, max_length=1000)


def discipline_key(value):
    text = value.casefold().replace('_', ' ').strip()
    return {'materials science': 'materials_science', '材料科学': 'materials_science', '材料学': 'materials_science',
        'computer science': 'computer_science', '计算机科学': 'computer_science', 'business': 'business',
        'business and management': 'business', '商科': 'business'}.get(text, text)


# Product topic rules, not an official disciplinary classification or venue list.
PRESETS = {
    'materials_science': [
        ('materials-performance', '材料性能', 'problem', 'core', None, []),
        ('conversion-efficiency', '能量转换效率', 'problem', 'core', 'materials-performance', ['efficiency', '效率']),
        ('material-stability', '材料稳定性', 'problem', 'core', 'materials-performance', ['stability', '稳定性']),
        ('interface-passivation', '界面／表面钝化', 'method', 'core', None, ['surface passivation', 'interfacial passivation', '表面钝化']),
        ('dimensional-engineering', '维度工程', 'method', 'associated', None, ['dimensional engineering', '维度工程']),
        ('solar-cells', '太阳能电池', 'application', 'core', None, ['solar cells', 'solar cell', '太阳能电池']),
        ('energy-storage', '储能', 'application', 'associated', None, ['batteries', 'battery', '储能']),
    ],
    'computer_science': [
        ('system-performance', '系统性能', 'problem', 'core', None, ['latency', 'throughput', 'performance', '性能']),
        ('disaggregated-serving', '分离式服务', 'method', 'core', None, ['disaggregating', 'disaggregated', '分离式']),
        ('llm-serving', '大模型服务', 'application', 'associated', None, ['large language models', 'llm', '大模型']),
        ('networking', '网络通信', 'application', 'core', None, ['network', '网络']),
    ],
    'business': [
        ('organization-innovation', '组织创新', 'problem', 'core', None, ['innovation', '创新']),
        ('causal-inference', '因果分析', 'method', 'core', None, ['causal', '因果']),
        ('supply-chain', '供应链', 'application', 'associated', None, ['supply chain', '供应链']),
    ],
}


def freeze_taxonomy(request: TaxonomyRequest, disciplines: list[str]) -> dict:
    selected = {discipline_key(value) for value in disciplines}
    nodes = list(request.nodes)
    if request.preset != 'custom':
        keys = selected if request.preset == 'auto' else {request.preset}
        if request.preset != 'auto' and request.preset not in selected:
            raise ValueError('taxonomy preset is outside the requested disciplines')
        for key in sorted(keys):
            for identity, label, axis, role, parent, terms in PRESETS.get(key, []):
                nodes.append(TopicNode(node_id=f'{key}:{identity}', label=label, discipline=key, axis=axis,
                    role=role, parent_id=f'{key}:{parent}' if parent else None, terms=tuple(terms)))
    if any(discipline_key(node.discipline) not in selected for node in nodes):
        raise ValueError('taxonomy node discipline is outside the requested scope')
    return {'rule_version': RULE_VERSION, 'preset_edition': 'adrs-topic-presets-2026-10-21',
        'request': request.model_dump(mode='json'), 'version': request.version,
        'nodes': [node.model_dump(mode='json') for node in nodes], 'disciplines': disciplines,
        'match_scope': 'source_supported_primary_title_and_marked_publisher_abstract',
        'semantics': '按主成果题名及出版商明确标记的摘要作可编辑词面映射；旧材料未保留摘要标记时只用题名。不是官方标签、全文机制核验或主题硬筛选。'}


def _literal(term):
    pattern = r'\s+'.join(re.escape(word) for word in term.split())
    return re.compile((r'(?<![A-Za-z0-9])' if term[0].isascii() else '') + pattern
        + (r'(?![A-Za-z0-9])' if term[-1].isascii() else ''), re.IGNORECASE)


def classify_text_spans(taxonomy,text,*,offset=0):
    """Same literal rule vocabulary; chunk labels never become paper facts."""
    labels=[]
    for node in taxonomy['nodes']:
        if len(labels)>=24:break
        hit=next((match for term in node['terms'] if (match:=_literal(term).search(text))),None)
        if hit:labels.append({key:node[key] for key in ('node_id','label','axis','discipline','role')} | {
            'start':offset+hit.start(),'end':offset+hit.end(),'quote':hit.group(),'taxonomy_version':taxonomy['version'],
            'status':'source_body_literal_mapping_requires_review'})
    return labels


def publisher_abstract_spans(raw_html: str, retained_text: str) -> list[dict]:
    """Only explicit abstract containers, paragraphs present in retained text."""
    class AbstractParagraphs(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack, self.active_depth, self.paragraph_depth = [], None, None
            self.parts, self.paragraphs = [], []

        def handle_starttag(self, tag, attrs):
            if tag in {'br','hr','img','meta','input','link','source','wbr'}:
                if tag == 'br' and self.paragraph_depth:
                    self.parts.append(' ')
                return
            self.stack.append(tag)
            data = dict(attrs)
            marker = data.get('id','') + ' ' + data.get('class','')
            if self.active_depth is None and tag in {'div','section','article'} and re.search(r'(?i)(?:^|[\s_-])abstract(?:$|[\s_-])', marker):
                self.active_depth = len(self.stack)
            if tag == 'p' and self.active_depth is not None:
                self.paragraph_depth, self.parts = len(self.stack), []

        def handle_data(self, data):
            if self.paragraph_depth is not None and not any(tag in {'script','style','noscript'} for tag in self.stack):
                self.parts.append(data)

        def handle_endtag(self, tag):
            index = next((i for i in range(len(self.stack)-1,-1,-1) if self.stack[i] == tag), None)
            if index is None:
                return
            if self.paragraph_depth is not None and index < self.paragraph_depth:
                value = ' '.join(''.join(self.parts).split())
                if value:
                    self.paragraphs.append(value)
                self.paragraph_depth = None
            if self.active_depth is not None and index < self.active_depth:
                self.active_depth = None
            self.stack = self.stack[:index]
    parser = AbstractParagraphs()
    parser.feed(raw_html)
    spans = []
    for paragraph in parser.paragraphs[:20]:
        if not 30 <= len(paragraph) <= 12000:
            continue
        match = _literal(paragraph).search(retained_text)
        if match:
            spans.append({'start':match.start(), 'end':match.end(), 'quote':match.group(),
                'basis':'explicit_publisher_abstract_container_paragraph'})
    return spans


def classify_publications(taxonomy: dict, findings: dict, evidence: list[dict], scope: dict, *, reason='研究冻结规则首次分类', previous=None) -> dict:
    from app.organization_findings import _publication_url
    nodes = {node['node_id']: node for node in taxonomy['nodes']}
    sources = {item['evidence_id']: item for item in evidence if item.get('evidence_id')}
    records = []
    for output in (findings.get('scope_result') or {}).get('outputs', []):
        meta = findings.get('publication_metadata', {}).get(output['output_id'], {})
        anchors = []
        primary_urls = {_publication_url(url) for url in output['source_urls']}
        for identity in meta.get('evidence_ids', []):
            source = sources.get(identity)
            if not source or _publication_url(source.get('source_url') or '') not in primary_urls:
                continue
            match = _literal(output['title']).search(source.get('content') or '')
            if match:
                anchors.append((source, match.start(), match.group(), 'primary_title'))
                for span in (source.get('acquisition') or {}).get('publisher_abstract_spans', []):
                    start, end = span.get('start',-1), span.get('end',-1)
                    if 0 <= start < end <= len(source['content']) and source['content'][start:end] == span.get('quote'):
                        anchors.append((source, start, span['quote'], 'publisher_abstract'))
        labels = []
        for node in nodes.values():
            for source, offset, field_text, field in anchors:
                matched = next((hit for term in node['terms'] if (hit := _literal(term).search(field_text))), None)
                if not matched:
                    continue
                start, end = offset + matched.start(), offset + matched.end()
                parents, current = [], node
                while current.get('parent_id'):
                    parents.append(current['parent_id'])
                    current = nodes[current['parent_id']]
                labels.append({'node_id': node['node_id'], 'label': node['label'], 'axis': node['axis'],
                    'discipline': node['discipline'], 'role': node['role'], 'ancestors': parents,
                    'basis': {'evidence_id': source['evidence_id'], 'source_url': source['source_url'],
                        'start': start, 'end': end, 'quote': source['content'][start:end], 'field': field}})
                break
        records.append({'output_id': output['output_id'], 'title': output['title'], 'year': meta.get('year'),
            'labels': labels, 'axes': {axis: 'mapped' if any(tag['axis'] == axis for tag in labels) else 'unknown' for axis in AXES},
            'evidence_ids': sorted({anchor[0]['evidence_id'] for anchor in anchors}),
            'status': 'source_field_rule_mapping_requires_review' if labels else 'unknown',
            'unknown_reason': None if labels else '未命中冻结规则或缺少保留的主成果题名／明确摘要；不从载体推断学科。'})
    years = sorted({item['year'] for item in records if item['year'] is not None})
    annual = []
    for year in years:
        cohort = [item for item in records if item['year'] == year]
        counts = Counter(tag['node_id'] for item in cohort for tag in item['labels'])
        annual.append({'year': year, 'publication_count': len(cohort), 'label_counts': dict(counts),
            'unknown_publication_count': sum(not item['labels'] for item in cohort),
            'unknown_by_axis': {axis: sum(item['axes'][axis] == 'unknown' for item in cohort) for axis in AXES}})
    result = {'snapshot_id': str(uuid4()), 'schema_version': RULE_VERSION, 'created_at': datetime.now(UTC).isoformat(),
        'taxonomy': taxonomy, 'reason': reason, 'records': records, 'annual': annual,
        'evidence_ids': sorted({identity for row in records for identity in row['evidence_ids']}),
        'coverage': 'accepted_publications_in_retained_sample_only',
        'counting_unit': 'publication_multi_label_each_node_once_per_publication',
        'unknown_year_count': sum(item['year'] is None for item in records),
        'unobserved_years': [year for year in range(int(scope['start_date'][:4]), int(scope['end_date'][:4])+1) if year not in years],
        'interpretation': '各年仅为已采纳样本，未覆盖年份不补零；标签可交叉。重分类变化来自规则，不能解释为新增成果、投入增长或战略变化。',
        'effects': {'network_requests': 0, 'model_calls': 0, 'original_report_modified': False},
        'comparison': None}
    if previous:
        old = {row['output_id']: row for row in previous['records']}
        changes = []
        for row in records:
            earlier = old.get(row['output_id'], {})
            old_tags = {(tag['node_id'],tag['role'],tag['label']) for tag in earlier.get('labels', [])}
            new_tags = {(tag['node_id'],tag['role'],tag['label']) for tag in row['labels']}
            if old_tags != new_tags:
                changes.append({'output_id': row['output_id'], 'before': earlier.get('labels', []), 'after': row['labels']})
        result['comparison'] = {'kind': 'reclassification_only', 'previous_snapshot_id': previous['snapshot_id'],
            'previous_version': previous['taxonomy']['version'], 'same_publication_ids': set(old) == {row['output_id'] for row in records},
            'same_evidence_ids': previous['evidence_ids'] == result['evidence_ids'], 'changes': changes,
            'annual_before': previous['annual'], 'annual_after': annual, 'publication_growth_claim': False}
    return result


def classification_markdown(snapshot):
    if not snapshot:
        return ''
    def safe(value):
        return str(value).replace('|', '\\|').replace('<', '&lt;').replace('>', '&gt;').replace('\n', ' ').replace('\r', ' ')
    lines = ['\n\n## 学科问题、方法与应用分类', f"分类版本：{safe(snapshot['taxonomy']['version'])}；规则：{RULE_VERSION}。",
        snapshot['taxonomy']['semantics'], snapshot['interpretation'],
        '| 成果 | 年份 | 问题 | 方法 | 应用 |', '| --- | --- | --- | --- | --- |']
    for row in snapshot['records']:
        cells = [safe(row['title']), str(row['year'] or '未知')]
        for axis in AXES:
            cells.append('、'.join(safe(tag['label']) + ('（核心）' if tag['role']=='core' else '（关联）') for tag in row['labels'] if tag['axis']==axis) or '未知')
        lines.append('| ' + ' | '.join(cells) + ' |')
    lines.append('未覆盖年份（非零值）：' + ('、'.join(map(str,snapshot['unobserved_years'])) or '无范围内缺年；不代表现实全集'))
    return '\n'.join(lines)
