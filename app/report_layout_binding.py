"""Bind a validated layout to the current owned report's retained data.

The caller supplies only the same report, citations and snapshots used for
delivery. This module neither reads sample files nor performs IO, model calls,
research, or permission changes. Missing data stays missing.
"""
from __future__ import annotations

from copy import deepcopy
import math
import re

from app.report_layout import ReportLayout

VERSION = 'adrs-report-layout-binding-v1'

ROLE_WORDS = {
    'overview': ('核心判断', '核心结论', '概览', '全景', '布局', 'overview', 'summary', 'landscape'),
    'findings': ('研究发现', '主要发现', '关键发现', '成果', '机制', '深读', '专题', 'findings', 'results', 'mechanism'),
    'evolution': ('演进', '趋势', '变化', 'evolution', 'trend', 'development'),
    'comparison': ('对比', '比较', '条件', 'comparison', 'compare'),
    'relationships': ('关系', '合作', '团队', '学者', 'relationship', 'collaboration', 'network'),
    'recommendations': ('建议', '行动', '下一步', 'recommendation', 'action', 'opportunit'),
    'references': ('参考', '来源', '依据', 'references', 'sources', 'evidence'),
}
ROLE_LABELS = {'overview':'研究概览','findings':'研究发现','evolution':'研究演进','comparison':'对照分析',
               'relationships':'关系与合作','recommendations':'建议','references':'参考资料','general':'研究内容'}
ROLE_CHARTS = {
    'overview': ('object_publications', 'classification_publications', 'annual_publications'),
    'findings': ('classification_publications', 'technical_comparison', 'object_publications'),
    'evolution': ('annual_publications',),
    'comparison': ('technical_comparison', 'object_publications'),
    'relationships': ('source_relationships',),
    'recommendations': (),
    'references': ('citation_sources',),
    'general': ('classification_publications', 'annual_publications', 'object_publications',
                'technical_comparison', 'source_relationships'),
}
SOURCE_CHARTS = {
    'statistics': frozenset({'annual_publications', 'classification_publications', 'object_publications'}),
    'relationships': frozenset({'source_relationships'}),
    'technical_comparison': frozenset({'technical_comparison'}),
    'sources': frozenset({'citation_sources'}),
    'narrative': frozenset(),
}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _citation_ids(text, available):
    ids = {'citation:' + value for value in re.findall(r'\[(?:citation:)?(\d+)\]', text)}
    return sorted(ids & available)


def _chunks(markdown):
    """Split at paragraph boundaries, preserving fenced code and table rows."""
    chunks, current, fence = [], [], None
    for line in markdown.splitlines(keepends=True):
        match = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = (marker[0], len(marker))
            elif marker[0] == fence[0] and len(marker) >= fence[1]:
                fence = None
        if not line.strip() and fence is None:
            if current:
                chunks.append(''.join(current).strip())
                current = []
        else:
            current.append(line)
    if current:
        chunks.append(''.join(current).strip())
    return [chunk for chunk in chunks if chunk]


def _assign_sections(layout, narrative):
    """Named roles claim matching current headings before generic sections."""
    assigned, used = {}, set()
    for section in layout.sections:
        if section.role == 'general':
            continue
        words = ROLE_WORDS.get(section.role, ())
        candidates = [i for i, row in enumerate(narrative) if i not in used
                      and any(word in str(row.get('title', '')).casefold() for word in words)]
        if candidates:
            assigned[section.section_id] = candidates[0]
            used.add(candidates[0])
    for section in layout.sections:
        if section.role != 'general':
            continue
        index = next((i for i in range(len(narrative)) if i not in used), None)
        if index is not None:
            assigned[section.section_id] = index
            used.add(index)
    return assigned


def _source_bound_charts(charts, statistics, citations, result):
    """Do not bind unsupported rows, unanchored edges, or invented zeroes."""
    available = {item.get('citation_id') for item in citations if item.get('citation_id')}
    evidence_citations = {item.get('locator', {}).get('evidence_id'): item['citation_id']
                          for item in citations if item.get('citation_id') and isinstance(item.get('locator'), dict)}
    registry = statistics.get('metric_registry') or {}
    snapshot_id = statistics.get('snapshot_id')
    established = bool(statistics.get('publication_ids')) and bool(snapshot_id)
    accepted = []
    for original in charts:
        chart = deepcopy(original)
        chart_id = chart.get('chart_id')
        if chart_id in SOURCE_CHARTS['statistics']:
            if not established or chart.get('snapshot_id') != snapshot_id:
                continue
            points = []
            for point in chart.get('points') or []:
                metric = registry.get(point.get('metric_id'))
                if not isinstance(metric, dict):
                    continue
                value, expected = point.get('value'), metric.get('value')
                if value is None and expected is None:
                    points.append(point)
                elif _number(value) and _number(expected) and value == expected:
                    points.append(point)
            if not points or not any(_number(p.get('value')) for p in points) or not chart.get('unit_label'):
                continue
            chart['points'] = points
            chart['metric_ids'] = [p['metric_id'] for p in points if p.get('metric_id')]
        elif chart_id == 'source_relationships':
            edges = [edge for edge in chart.get('edges') or [] if set(edge.get('citation_ids') or []) & available]
            if not edges:
                continue
            node_ids = {item for edge in edges for item in (edge.get('source'), edge.get('target'))}
            chart['edges'] = edges
            chart['nodes'] = [node for node in chart.get('nodes') or [] if node.get('id') in node_ids]
            chart['citation_ids'] = sorted({ref for edge in edges for ref in edge.get('citation_ids') or []} & available)
        elif chart_id == 'technical_comparison':
            rows = []
            for card in (result.get('technical_reading') or {}).get('cards', [])[:20]:
                values, references = [card.get('title') or card.get('output_id', '')], []
                for key in ('problem', 'mechanism', 'conditions', 'results'):
                    field = (card.get('fields') or {}).get(key) or {}
                    refs = [evidence_citations.get(proof.get('evidence_id')) for proof in field.get('proofs') or []]
                    refs = [ref for ref in refs if ref in available]
                    values.append(field.get('text') or '—' if refs else '—')
                    references.extend(refs)
                if references and any(value != '—' for value in values[1:]):
                    rows.append({'values': values, 'citation_ids': list(dict.fromkeys(references))})
            if not rows:
                continue
            chart['rows'] = rows
            chart['citation_ids'] = list(dict.fromkeys(ref for row in rows for ref in row['citation_ids']))
        elif chart_id == 'citation_sources':
            if not available or not set(chart.get('citation_ids') or []) <= available:
                continue
        else:
            continue
        accepted.append(chart)
    return accepted


def _compatible(chart, requested):
    if requested == 'none':
        return False
    if requested == 'auto':
        return True
    if requested == 'table':
        return bool(chart.get('points') or chart.get('rows') or chart.get('edges'))
    if requested == 'network':
        return bool(chart.get('edges') and chart.get('nodes'))
    if requested in {'line', 'timeline'}:
        # The existing trusted renderer accepts only an ordered year series.
        return chart.get('chart_id') == 'annual_publications' and sum(_number(p.get('value')) for p in chart.get('points') or []) >= 2
    if requested == 'bar':
        return bool(chart.get('points'))
    return False


def _metric_candidates(statistics, role, binding):
    if binding not in {'auto', 'statistics'} or not statistics.get('publication_ids') or not statistics.get('snapshot_id'):
        return []
    registry = statistics.get('metric_registry') or {}
    prefixes = {'overview': ('sample:', 'object:'), 'findings': ('label:', 'sample:'),
                'evolution': ('year:',), 'comparison': ('object:',), 'general': ('sample:', 'object:', 'label:')}.get(role, ())
    return [deepcopy(value) for key, value in registry.items()
            if key.startswith(prefixes) and isinstance(value, dict) and _number(value.get('value'))
            and value.get('unit') and value.get('metric_id') == key]


def bind_layout(layout_data, *, narrative, charts, statistics, citations, result, slots, task_id, execution_id, descriptor_id, chart_skill_ids=None):
    """Build a declarative, traceable slot map for a later trusted renderer."""
    layout = ReportLayout.model_validate(layout_data)
    charts = _source_bound_charts(charts, statistics, citations, result)
    chart_by_id = {chart['chart_id']: chart for chart in charts}
    available = {item['citation_id'] for item in citations if item.get('citation_id')}
    assigned = _assign_sections(layout, narrative)
    overrides = chart_skill_ids or {}
    used_charts, used_metrics, sections, pages, missing, unplaced = set(), set(), [], [], [], {}
    for section_number, section in enumerate(layout.sections, 1):
        matched = narrative[assigned[section.section_id]] if section.section_id in assigned else None
        markdown = (matched or {}).get('markdown') or ''
        chunks = _chunks(markdown)
        slot_rows, fallback_indexes = [], []
        for block in section.blocks:
            row = {**block.model_dump(mode='json'), 'status': 'missing', 'data': None, 'citation_ids': []}
            if block.kind == 'heading' and matched:
                row.update(status='bound', data={'kind': 'heading', 'text': matched.get('title', '')})
            elif block.kind in {'text', 'list', 'callout'} and block.binding in {'auto', 'narrative'}:
                fallback_indexes.append(len(slot_rows))
            elif block.kind in {'text', 'list', 'callout'} and block.binding == 'sources' and citations:
                row.update(status='bound', data={'kind': 'sources', 'items': [
                    {key: item.get(key) for key in ('citation_id', 'source_title', 'source_url', 'source_type')}
                    for item in citations if item.get('citation_id') in available]},
                    citation_ids=sorted(available))
            elif block.kind in {'text', 'list', 'callout'} and block.binding == 'statistics':
                metrics = [item for item in _metric_candidates(statistics, section.role, block.binding)
                           if item['metric_id'] not in used_metrics][:12]
                if metrics:
                    used_metrics.update(item['metric_id'] for item in metrics)
                    row.update(status='bound', data={'kind': 'metrics', 'snapshot_id': statistics['snapshot_id'], 'items': metrics})
            elif block.kind in {'text', 'list', 'callout'} and block.binding in {'relationships', 'technical_comparison'}:
                source_id = 'source_relationships' if block.binding == 'relationships' else 'technical_comparison'
                chart = chart_by_id.get(source_id)
                if chart:
                    items = chart.get('edges') if block.binding == 'relationships' else chart.get('rows')
                    row.update(status='bound', data={'kind': block.binding, 'items': deepcopy(items),
                        **({'nodes': deepcopy(chart.get('nodes') or [])} if block.binding == 'relationships' else
                           {'columns': deepcopy(chart.get('columns') or [])})},
                        citation_ids=sorted({ref for item in items for ref in item.get('citation_ids') or []} & available))
            elif block.kind == 'metric':
                metric = next((item for item in _metric_candidates(statistics, section.role, block.binding)
                               if item['metric_id'] not in used_metrics), None)
                if metric:
                    used_metrics.add(metric['metric_id'])
                    row.update(status='bound', data={'kind': 'metric', 'snapshot_id': statistics['snapshot_id'],
                        'metric': metric})
            elif block.kind in {'chart', 'image'} and block.chart_kind == 'none':
                if markdown:
                    fallback_indexes.append(len(slot_rows))
            elif block.kind in {'chart', 'table', 'image'}:
                allowed = SOURCE_CHARTS.get(block.binding)
                preferred = ROLE_CHARTS.get(section.role, ()) if block.binding == 'auto' else tuple(chart_by_id)
                candidates = [chart_by_id[chart_id] for chart_id in preferred if chart_id in chart_by_id
                              and (allowed is None or chart_id in allowed)
                              and _compatible(chart_by_id[chart_id], 'table' if block.kind == 'table' else block.chart_kind)]
                chart = next((item for item in candidates if item['chart_id'] not in used_charts), None)
                if chart is None and block.binding != 'auto' and candidates:
                    chart = candidates[0]
                if chart:
                    used_charts.add(chart['chart_id'])
                    kind = 'table' if block.kind == 'table' else chart['kind'] if block.chart_kind == 'auto' else block.chart_kind
                    skill = overrides.get(block.block_id) or overrides.get(chart['chart_id'])
                    reference = {'chart_id': chart['chart_id'], 'kind': kind, 'layout_block_id': block.block_id,
                                 **({'drawing_skill_id': skill} if skill else {})}
                    row.update(status='bound', data={'kind': 'chart', 'reference': reference},
                               citation_ids=sorted(set(chart.get('citation_ids') or []) & available))
            if row['status'] == 'missing' and block.kind != 'heading' and block.chart_kind != 'none' and block.missing == 'text' and markdown and len(slot_rows) not in fallback_indexes:
                fallback_indexes.append(len(slot_rows))
            slot_rows.append(row)
        # Give each prose slot a contiguous share, never repeat paragraphs to fill space.
        if matched and markdown and not fallback_indexes:
            source_index=assigned[section.section_id]
            unplaced[source_index]={'title':matched.get('title',''),'markdown':markdown,
                                   'citation_ids':_citation_ids(markdown,available),'reason':'no_narrative_slot'}
        per_slot, extra = divmod(len(chunks), len(fallback_indexes)) if fallback_indexes else (0, 0)
        for position, slot_index in enumerate(fallback_indexes):
            start = position * per_slot + min(position, extra)
            end = start + per_slot + (1 if position < extra else 0)
            text = '\n\n'.join(chunks[start:end])
            if text:
                row = slot_rows[slot_index]
                row.update(status='bound' if row['kind'] in {'text', 'list', 'callout'} and row['binding'] in {'auto','narrative'} else 'text_fallback',
                           data={'kind': 'narrative', 'markdown': text}, citation_ids=_citation_ids(text, available))
        for block_number, row in enumerate(slot_rows, 1):
            if row['status'] != 'missing':
                continue
            row['status'] = 'omitted' if row['missing'] == 'omit' or row['chart_kind'] == 'none' else 'required_missing' if row['missing'] == 'require_data' else 'missing'
            missing.append({'section_id': section.section_id, 'block_id': row['block_id'], 'kind': row['kind'],
                            'section_index':section_number,'block_index':block_number,'role':section.role,
                            'binding': row['binding'], 'policy': row['missing'], 'status': row['status']})
        refs = [row['data']['reference'] for row in slot_rows if row['data'] and row['data'].get('kind') == 'chart']
        section_title = (matched or {}).get('title') or ROLE_LABELS[section.role]
        sections.append({'section_id': section.section_id, 'role': section.role, 'level': section.level,
                         'columns': section.columns, 'title': section_title,
                         'title_origin': 'current_report' if matched else 'role_default', 'blocks': slot_rows})
        pages.append({'page_id': section.section_id, 'declared_page_id': section.section_id,
                      'title': section_title, 'question': '', 'module': None,
                      'markdown': '\n\n'.join(row['data']['markdown'] for row in slot_rows
                                            if row['data'] and row['data'].get('kind') == 'narrative'),
                      'content_match': 'current_report_section' if matched else 'not_found',
                      'citation_ids': sorted({ref for row in slot_rows for ref in row['citation_ids']}),
                      'charts': refs, 'gaps': [], 'semantics': 'current_task_data_only'})
    assigned_indexes=set(assigned.values())
    for index, item in enumerate(narrative):
        if index not in assigned_indexes and item.get('markdown'):
            unplaced[index]={'title':item.get('title',''),'markdown':item['markdown'],
                             'citation_ids':_citation_ids(item['markdown'],available),'reason':'no_matching_section'}
    required = [item for item in missing if item['status'] == 'required_missing']
    binding = {'schema_version': VERSION, 'task_id': task_id, 'execution_id': execution_id,
        'descriptor_id': descriptor_id, 'status': 'required_data_missing' if required else 'partial' if any(item['status']=='missing' for item in missing) else 'bound',
        'layout':layout.model_dump(mode='json'),
        'sections': sections, 'missing': missing, 'required_missing': required,
        'unplaced_sections':[unplaced[index] for index in sorted(unplaced)],
        'context': {'entities': deepcopy(slots.get('entities') or []), 'disciplines': deepcopy(slots.get('disciplines') or [])},
        'effects': {'model_calls': 0, 'network_calls': 0, 'permissions_changed': False}}
    return binding, pages, charts
