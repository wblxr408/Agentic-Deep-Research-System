"""Deterministic views of an owned, frozen report; no model, IO or new authority."""
from __future__ import annotations

import math
import re
from collections import Counter
from copy import deepcopy
from urllib.parse import urlsplit

from app.query_understanding import identity

VERSION = 'adrs-research-delivery-v1'
MODULE_LABELS = {'landscape': '研究全景', 'evolution': '技术演进', 'relationships': '组织与学者关系',
    'deep_dive': '代表成果深读', 'validation': '资料对照与比较', 'actions': '建议与后续行动'}
SECTION_WORDS = {'landscape': ('全景', '布局', 'landscape', 'overview', '统计'),
    'evolution': ('演进', '趋势', 'evolution', 'trend'),
    'relationships': ('关系', '合作', '学者', 'relationship', 'network'),
    'deep_dive': ('深读', '机制', '专题', 'deep dive', 'technical'),
    'validation': ('核验', '验证', '缺口', '资料对照', 'audit', 'validation', 'verification'),
    'actions': ('行动', '建议', 'recommendation', 'action')}
PRESET_MODULES = {'organization-development-v1': ('landscape', 'evolution', 'deep_dive', 'validation', 'actions'),
    'technology-comparison-v1': ('landscape', 'deep_dive', 'evolution', 'validation', 'actions'),
    'cooperation-matching-v1': ('relationships', 'landscape', 'deep_dive', 'validation', 'actions'),
    'field-trends-v1': ('landscape', 'evolution', 'deep_dive', 'validation', 'actions'),
    'research-map-v1': ('relationships', 'evolution', 'landscape', 'deep_dive', 'validation', 'actions')}


def _sections(markdown: str) -> list[dict]:
    """Split only actual H2 headings, ignoring headings inside fenced code."""
    sections, title, lines, fence = [], '报告概览', [], None
    for line in markdown.splitlines(keepends=True):
        match = re.match(r'^\s{0,3}(`{3,}|~{3,})(.*)$', line)
        if match:
            marker = match[1]
            if fence is None:
                fence = (marker[0], len(marker))
            elif marker[0] == fence[0] and len(marker) >= fence[1] and not match[2].strip():
                fence = None
        heading = re.match(r'^##\s+(.+?)\s*#*\s*$', line) if fence is None else None
        if heading:
            if lines:
                sections.append({'title': title, 'markdown': ''.join(lines).strip()})
            title, lines = heading[1], []
        else:
            lines.append(line)
    if lines:
        sections.append({'title': title, 'markdown': ''.join(lines).strip()})
    return sections


def _heading_key(value: str) -> str:
    return re.sub(r'^[\d一二三四五六七八九十.、()（）\s]+', '', value).casefold().strip()


def report_for_reading(report: str, citations: list[dict] | None = None) -> str:
    """Project legacy program-added records out of prose; keep the stored text.

    These exact headings and prefixes were produced by ADRS itself. This is
    deliberately not a general caveat/sentence filter for research content.
    """
    sections = []
    for section in _sections(report):
        title = section['title'].strip()
        if title == '研究对象、口径与冻结配置':
            break  # Start of the old root's deterministic record appendices.
        if title in {'核验结果', '本次保留依据定位'}:
            continue
        body = section['markdown']
        if title.casefold() in {'references','参考文献','参考资料'} and citations is not None:
            # The research ledger retains every discovered source. The reader
            # bibliography contains the references actually used in this view,
            # preserving original source numbers rather than renumbering.
            body='\n\n'.join('['+row['citation_id'].replace('citation:','')+'] '+
                str(row.get('source_title') or '')+' — '+str(row.get('source_url') or '')
                for row in citations if re.fullmatch(r'citation:\d+',row.get('citation_id','')))
        for label in ('来源摘述（待审核）', '分析判断（待复核）', '证据缺口'):
            body = re.sub(r'(?m)^\*\*' + re.escape(label) + r'\*\*：', '', body)
        body = '\n'.join(line for line in body.splitlines()
            if not line.startswith(('> 按本次所选研究模块组织；', '> 模块交付存在缺口：')))
        if title == '报告概览':
            sections.append(body.strip())
        elif body.strip():
            sections.append(f'## {title}\n\n{body.strip()}')
    reader = re.sub(r'\[citation:(\d+)\]', r'[\1]', '\n\n'.join(sections).strip())
    references = []
    for citation in citations or []:
        match = re.fullmatch(r'citation:(\d+)', citation.get('citation_id', ''))
        url = citation.get('source_url') or ''
        try:
            valid = urlsplit(url).scheme in {'http', 'https'} and bool(urlsplit(url).hostname)
        except ValueError:
            valid = False
        if match and valid and not any(ord(char) < 32 for char in url):
            references.append(f"[{match[1]}]: <{url.replace('<','%3C').replace('>','%3E')}>")
    return reader + '\n\n' + '\n'.join(references) + '\n'


def _apply_surface_corrections(charts,corrections):
    from app.report_surface_review import surface_binding
    if not corrections or corrections.get('base_binding')!=surface_binding(charts,None):return
    by_chart={row['chart_id']:row for row in charts}
    for correction in corrections.get('cells',[]):
        parts=correction['cell_id'].rsplit(':',2)
        if len(parts)!=3 or not parts[1].isdigit() or not parts[2].isdigit():continue
        chart=by_chart.get(parts[0]);row_index,column=int(parts[1]),int(parts[2])
        if (chart and chart.get('kind') in {'table','matrix'} and row_index<len(chart.get('rows',[]))
                and 0<column<len(chart['rows'][row_index]['values'])):
            chart['rows'][row_index]['values'][column]=correction['text']


def _finite(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def build_delivery_view(*, task_id: str, execution_id: str | None, query: str, report: str,
        citations: list[dict], understanding: dict | None, organization_result: dict | None,
        audit: dict | None, source_media: dict | None = None) -> dict:
    """Caller authenticates the actual session owner before supplying any data."""
    frozen = (understanding or {}).get('delivery') or {}
    template, theme = frozen.get('template', 'markdown-v1'), frozen.get('theme', 'plain-v1')
    result = organization_result or {}
    from app.source_figure_extraction import MEDIA_POLICY as FIGURE_MEDIA_POLICY
    figure_media_required=frozen.get('source_figure_policy') is not None
    actual_media=source_media if source_media is not None else result.get('source_media') or {}
    figure_media_ok=(not figure_media_required or frozen.get('source_figure_policy')==FIGURE_MEDIA_POLICY
        and actual_media.get('policy')==FIGURE_MEDIA_POLICY
        and actual_media.get('status') in {'rendered','no_located_pages'}
        and all(page.get('figures') for page in actual_media.get('pages') or []))
    pdf_projection=bool(frozen.get('pdf_chart_policy') and frozen.get('drawing_mode','builtin')=='builtin'
        and frozen.get('layout') is None and ('pdf' in (frozen.get('formats') or [])
            or result.get('delivery_target')=='main_and_appendix_pdf'))
    pdf_issues=[]
    from app.report_quality import reader_quality_satisfied
    reader_quality_ok=reader_quality_satisfied(result.get('module_report'),audit)
    summary = result.get('report_summary') or {}
    statistics = result.get('statistics') or summary.get('statistics') or {}
    relationships = result.get('relationship_view') or summary.get('relationships') or {}
    stats_id = statistics.get('snapshot_id')
    all_sources = deepcopy(summary.get('sources') or [])
    used={'citation:'+number for number in re.findall(r'\[citation:(\d+)\]',report)}
    if figure_media_required:
        illustrated={key for page in actual_media.get('pages') or [] for key in page.get('evidence_ids') or []}
        used.update(row['citation_id'] for row in citations if (row.get('locator') or {}).get('evidence_id') in illustrated)
    timeline=None;visual_issues=[]
    from app.report_timeline import POLICY as EVENT_POLICY,build_timeline
    timeline_enabled=(frozen.get('event_timeline_policy')==EVENT_POLICY
        and frozen.get('drawing_mode','builtin')=='builtin' and frozen.get('layout') is None
        and 'evolution' in (((understanding or {}).get('slots') or {}).get('modules') or [])
        and (template!='custom' or any(page.get('module')=='evolution'
            and page.get('chart_kind','auto') in {'auto','timeline','table'} for page in frozen.get('pages') or [])))
    if timeline_enabled:
        timeline,missing=build_timeline(result,citations,used)
        visual_issues=[{'location':row['output_id'],'reason':row['reason']} for row in missing]
        if timeline:used.update(timeline['citation_ids'])
    from app.report_mechanisms import POLICY as MECHANISM_POLICY,SUPPORTED_POLICIES as MECHANISM_POLICIES,build_mechanism_charts
    mechanism_requested=frozen.get('mechanism_graph_policy') is not None
    mechanism_enabled=(frozen.get('mechanism_graph_policy') in MECHANISM_POLICIES
        and frozen.get('drawing_mode','builtin')=='builtin' and frozen.get('layout') is None
        and 'deep_dive' in (((understanding or {}).get('slots') or {}).get('modules') or []))
    mechanisms=[];visual_requirements=[]
    if mechanism_requested and frozen['mechanism_graph_policy'] not in MECHANISM_POLICIES:
        visual_issues.append({'location':'mechanisms','reason':'mechanism_policy_unsupported'})
    if mechanism_enabled:
        quality=(audit or {}).get('reader_quality') or {}
        mechanisms,visual_requirements=build_mechanism_charts(result,citations,used,quality,actual_media,configuration=frozen)
        for chart in mechanisms:used.update(chart['citation_ids'])
        for requirement in visual_requirements:used.update(requirement.get('citation_ids') or [])
        if quality.get('coverage_complete') is not True:
            visual_issues.append({'location':'mechanisms','reason':'mechanism_reader_scope_unavailable'})
    citations = deepcopy([row for row in citations if row.get('citation_id') in used]) if used else deepcopy(citations)
    reader_report = report_for_reading(report, citations)
    sections = _sections(reader_report)
    main_sections, appendix_sections, in_appendix = [], [], False
    for section in sections:
        if section['title'] == '技术附录':
            in_appendix = True
        if section['title'].strip().casefold() in {'references', '参考文献', '参考资料'}:
            continue
        (appendix_sections if in_appendix else main_sections).append(section)
    def reading_markdown(items):
        return '\n\n'.join(row['markdown'] if row['title'] == '报告概览'
            else f"## {row['title']}\n\n{row['markdown']}" for row in items)
    main_report = reading_markdown(main_sections)
    appendix_report = reading_markdown(appendix_sections)
    aliases = report_for_reading('', citations).strip()
    if aliases:
        main_report += '\n\n'+aliases+'\n'
        if appendix_report:
            appendix_report += '\n\n'+aliases+'\n'
    if appendix_sections:
        sections = main_sections
    narrative = []
    for section in sections:
        if section['title'].strip().casefold() in {'核验结果','references','参考文献','本次保留依据定位','研究对象、口径与冻结配置'}:
            break
        narrative.append(section)
    available_citations = {item['citation_id'] for item in citations if item.get('citation_id')}
    evidence_citations = {item.get('locator', {}).get('evidence_id'): item['citation_id'] for item in citations
        if item.get('citation_id') and isinstance(item.get('locator'), dict)}
    # Provenance of a chart dataset is not an assertion that every citation
    # independently supports every bar. Metric member IDs remain authoritative.
    charts = []
    if timeline:charts.append(timeline)
    charts.extend(mechanisms)
    technical_rows = []
    fields = [('problem', '问题'), ('mechanism', '机制'), ('conditions', '实验条件'), ('results', '来源结果')]
    for card in (result.get('technical_reading') or {}).get('cards', [])[:20]:
        values, refs = [card.get('title') or card.get('output_id', '')], []
        cell_refs={}
        for key, _ in fields:
            source_fields=card.get('fields') or {}
            members=[source_fields.get(name) or {} for name in
                (('conditions','experimental_design','baselines') if key=='conditions' else (key,))]
            members=[field for field in members if field.get('text') and field.get('proofs')]
            field_refs=[evidence_citations[p['evidence_id']] for field in members for p in field.get('proofs', [])
                if p.get('evidence_id') in evidence_citations]
            values.append('\n'.join(dict.fromkeys(field['text'] for field in members)) if field_refs else '—')
            cell_refs[str(len(values)-1)]=list(dict.fromkeys(field_refs))
            refs.extend(field_refs)
        if refs and any(value != '—' for value in values[1:]):
            technical_rows.append({'values': values, 'citation_ids': list(dict.fromkeys(refs)),
                'cell_citation_ids':cell_refs})
    if len(technical_rows)>1:
        charts.append({'chart_id': 'technical_comparison', 'title': '问题、机制与实验条件对照',
            'module': 'deep_dive', 'kind': 'table', 'unit_label': '来源中的技术说明',
            'columns': ['成果', *[label for _, label in fields]], 'rows': technical_rows,
            'note': '按取得的原文摘要对照机制与条件；不同实验的结果不作为性能排名。',
            'citation_ids': list(dict.fromkeys(ref for row in technical_rows for ref in row['citation_ids']))})
    for key, title, module, kind in [
        ('annual_publications', '已采纳样本的年度发表', 'evolution', 'line'),
        ('classification_publications', '已采纳样本的技术分类', 'landscape', 'bar')]:
        rows = (statistics.get('series') or {}).get(key) or []
        if rows:
            points = [{'label': str(row.get('x', '未知')), 'value': _finite(row.get('y')),
                'metric_id': row.get('metric_id'), 'missing': row.get('y') is None} for row in rows]
            charts.append({'chart_id': key, 'title': title, 'module': module, 'kind': kind,
                'unit': 'publication', 'unit_label': '采纳发表记录（篇）', 'snapshot_id': stats_id,
                'points': points[:200], 'total_points': len(points), 'truncated': len(points) > 200,
                'metric_ids': [row['metric_id'] for row in points if row['metric_id']],
                'citation_ids': [], 'source_binding': 'statistical_snapshot_metric_members_and_dataset_sources',
                'note': '按本报告纳入的发表记录统计；空白年份表示未覆盖，技术分类采用多标签计数。'})
    object_rows = statistics.get('object_rows') or []
    if object_rows:
        charts.append({'chart_id': 'object_publications', 'title': '研究对象的采纳发表样本', 'module': 'landscape',
            'kind': 'bar', 'unit': 'publication', 'unit_label': '采纳发表记录（篇）', 'snapshot_id': stats_id,
            'points': [{'label': row.get('name', row['entity_id']), 'value': _finite(row.get('publication_count')),
                'metric_id': row.get('publication_metric_id')} for row in object_rows[:200]],
            'total_points': len(object_rows), 'truncated': len(object_rows) > 200,
            'metric_ids': [row.get('publication_metric_id') for row in object_rows if row.get('publication_metric_id')],
            'citation_ids': [], 'source_binding': 'statistical_snapshot_metric_members_and_dataset_sources',
            'note': '按各对象的成果署名计数，同一成果可计入多个对象。'})
    entities = {row['entity_id']: row for row in relationships.get('entities', []) if row.get('entity_id')}
    edges = []
    for row in relationships.get('records', []):
        ids = [key for key in row.get('entity_ids', []) if key in entities]
        if len(ids) < 2:
            continue
        proofs = row.get('proofs') or []
        for other in ids[1:]:
            edges.append({'source': ids[0], 'target': other, 'label': row.get('name') or row.get('kind'),
                'kind': row.get('kind'), 'relationship_id': row.get('relationship_id'), 'status': row.get('status'),
                'proofs': deepcopy(proofs), 'event_time': deepcopy(row.get('event_time')),
                'citation_ids': list(dict.fromkeys(evidence_citations[p['evidence_id']] for p in proofs
                    if p.get('evidence_id') in evidence_citations))})
    if edges:
        retained_edges = edges[:100]
        nodes = {key for edge in retained_edges for key in (edge['source'], edge['target'])}
        charts.append({'chart_id': 'source_relationships', 'title': '有来源的关系观察', 'module': 'relationships',
            'kind': 'network', 'unit': 'source_relationship_observation', 'unit_label': '来源关系观察',
            'nodes': [{'id': key, 'label': entities[key].get('name', key)} for key in sorted(nodes)],
            'edges': retained_edges, 'total_edges': len(edges), 'truncated': len(edges) > 100,
            'snapshot_id': relationships.get('schema_version'),
            'note': '连线表示同一来源记录中的参与方；关系种类见数据表。'})
    domains = Counter()
    for citation in {row['citation_id']: row for row in citations if row.get('citation_id')}.values():
        try:
            host = urlsplit(citation.get('source_url', '')).hostname or '内部/未提供域名'
        except ValueError:
            host = '未提供有效域名'
        domains[host] += 1
    if domains:
        charts.append({'chart_id': 'citation_sources', 'title': '本次引用的来源分布', 'module': 'validation',
            'kind': 'bar', 'unit': 'citation', 'unit_label': '引用条目（条）', 'snapshot_id': None,
            'points': [{'label': name, 'value': value, 'metric_id': None} for name, value in domains.most_common(200)],
            'total_points': len(domains), 'truncated': len(domains) > 200,
            'citation_ids': sorted(available_citations), 'source_binding': 'retained_citation_ids',
            'note': '按参考资料所属域名统计引用条目。'})
    corrections=result.get('surface_corrections') or {}
    if not pdf_projection:_apply_surface_corrections(charts,corrections)
    if result.get('delivery_target')=='main_and_appendix_pdf' and not pdf_projection:
        from app.report_pdf import printed_charts
        charts=printed_charts(charts)
    selected_modules = ((understanding or {}).get('slots') or {}).get('modules') or []
    if template == 'custom':
        specs = frozen.get('pages') or []
    elif template == 'markdown-v1':
        specs = [{'page_id': f'section-{index+1}', 'title': section['title'],
            '_section': index, 'chart_kind': 'none'} for index, section in enumerate(sections)]
        if pdf_projection or timeline_enabled or mechanism_enabled:
            from app.organization_purpose import MODULES
            owned={_heading_key(MODULES[row['module_id']][0]):row['module_id']
                for row in (result.get('module_report') or {}).get('modules',[]) if row['module_id'] in MODULES}
            for spec in specs:
                module=owned.get(_heading_key(spec['title']))
                if module and (pdf_projection or module=='evolution' and timeline_enabled or module=='deep_dive' and mechanism_enabled):
                    spec.update(module=module,chart_kind='auto')
    else:
        ordering = PRESET_MODULES.get(template, tuple(MODULE_LABELS))
        ordered_modules = [module for module in ordering if module in selected_modules]
        ordered_modules += [module for module in selected_modules if module not in ordered_modules]
        specs = [{'page_id': module, 'title': MODULE_LABELS[module], 'module': module,
            'chart_kind': 'auto'} for module in ordered_modules if module in MODULE_LABELS]
        if not specs:
            specs = [{'page_id': f'section-{index+1}', 'title': section['title'],
                '_section': index, 'chart_kind': 'auto'} for index, section in enumerate(sections)]
        elif any(section['title'] == '核心判断' for section in sections):
            index = next(i for i, section in enumerate(sections) if section['title'] == '核心判断')
            specs.insert(0, {'page_id': 'core-judgements', 'title': '核心判断', '_section': index, 'chart_kind': 'none'})
        # Generic research has no organization modules, yet can show real
        # citation provenance without inventing a publication corpus.
        if not selected_modules and charts:
            specs.append({'page_id': 'source-coverage', 'title': '证据来源与覆盖', 'module': 'validation', 'chart_kind': 'auto'})
    pages = []
    for index, spec in enumerate(specs):
        module, gaps = spec.get('module'), []
        exact = [row for row in sections if _heading_key(row['title']) == _heading_key(spec.get('title', ''))]
        matched = [sections[spec['_section']]] if '_section' in spec else exact
        match_basis = 'original_section' if '_section' in spec else 'exact_title' if exact else 'module_heading_match'
        if not matched and module:
            matched = [row for row in narrative if any(word in row['title'].casefold() for word in SECTION_WORDS.get(module, ()))]
        markdown = '\n\n'.join(row['markdown'] if len(matched) == 1
            else f"### {row['title']}\n\n{row['markdown']}" for row in matched)
        if not markdown:
            gaps.append('本次报告未找到该页对应章节；请查看完整报告或修改问题后重新研究。')
        if spec.get('question') and not exact:
            gaps.append('尚无与自定义页面标题精确对应的回答；模块片段仅供参考，未证明已回答本页问题。')
        applicable = [chart for chart in charts if chart.get('module') == module] if module else []
        requested_kind = spec.get('chart_kind', 'auto')
        if ((result.get('module_report') or {}).get('reader_quality_policy')=='adrs-reader-quality-v1'
                and requested_kind=='auto' and template!='custom' and frozen.get('layout') is None):
            report_module=next((row for row in (result.get('module_report') or {}).get('modules',[])
                if row.get('module_id')==module),{})
            used_metrics={binding['metric_id'] for paragraph in [*report_module.get('paragraphs',[]),
                *report_module.get('appendix',[])] for binding in paragraph.get('statistic_bindings',[])}
            applicable=[chart for chart in applicable if chart['kind'] in {'table','matrix','network','flow'}
                or chart.get('kind')=='timeline' or used_metrics.intersection(chart.get('metric_ids',[]))]
        chosen = []
        if requested_kind != 'none':
            if requested_kind in ('auto', 'table'):
                chosen = applicable
            elif requested_kind=='timeline' and timeline_enabled:
                chosen=[chart for chart in applicable if chart['kind']=='timeline']
            elif requested_kind=='flow' and mechanism_enabled:
                chosen=[chart for chart in applicable if chart['kind']=='flow']
            elif requested_kind in ('bar', 'line', 'timeline'):
                chosen = [chart for chart in applicable if chart['kind'] != 'network'
                    and chart['kind'] not in {'timeline','flow'}
                    and (requested_kind == 'bar' or chart['chart_id'] == 'annual_publications')]
            elif requested_kind == 'network':
                chosen = [chart for chart in applicable if chart['kind'] == 'network']
            else:
                gaps.append('此图型尚无内置适配器；请明确改选表格、条形、折线或关系图。')
            if not chosen and (requested_kind!='auto' or template=='custom'):
                gaps.append('本页没有匹配图型的可追溯数据，不从正文猜测数值或生成装饰图。')
                if (frozen.get('mechanism_graph_policy')==MECHANISM_POLICY and module=='deep_dive'
                        and requested_kind=='flow' and not any(row.get('source_figure_id') for row in visual_requirements)):
                    visual_issues.append({'location':spec['page_id'],'reason':'explicit_mechanism_page_not_fulfilled'})
        chart_refs = []
        for chart in chosen:
            kind = chart['kind'] if requested_kind == 'auto' else requested_kind
            override=(frozen.get('chart_skill_ids') or {}).get(chart['chart_id'])
            chart_refs.append({'chart_id': chart['chart_id'], 'kind': kind,
                **({'drawing_skill_id':override} if override else {})})
        if len(markdown) > 16000:
            gaps.append('页面片段显示前16000字符；完整正文和JSON保留全部内容。')
        used = {'citation:' + number for number in re.findall(r'\[(?:citation:)?(\d+)\]', markdown)}
        pages.append({'page_id': f'page-{index+1}', 'declared_page_id': spec.get('page_id'),
            'title': spec.get('title', f'第{index+1}页'), 'question': spec.get('question', ''), 'module': module,
            'markdown': markdown[:16000], 'content_match': match_basis if matched else 'not_found',
            'citation_ids': sorted(used & available_citations), 'charts': chart_refs, 'gaps': gaps,
            **({'requested_chart_kind':requested_kind} if pdf_projection else {}),
            'semantics': 'report_excerpt_not_new_facts_or_independent_answer_verification'})
    layout_binding = None
    if frozen.get('layout') is not None:
        from app.report_layout_binding import bind_layout
        # The layout supplies its own cover title; do not repeat the Markdown
        # document heading inside its first narrative slot.
        layout_narrative = deepcopy(narrative)
        if layout_narrative and layout_narrative[0]['title'] == '报告概览':
            layout_narrative[0]['markdown'] = re.sub(r'^\s*#\s+[^\n]+\n?', '', layout_narrative[0]['markdown'], count=1)
        layout_binding, pages, charts = bind_layout(frozen['layout'], narrative=layout_narrative, charts=charts,
            statistics=statistics, citations=citations, result=result, slots=(understanding or {}).get('slots') or {},
            task_id=task_id, execution_id=execution_id, descriptor_id=frozen.get('descriptor_id'),
            chart_skill_ids=frozen.get('chart_skill_ids') or {})
    if pdf_projection:
        from app.report_pdf import project_pdf_view
        charts,pages,pdf_issues=project_pdf_view(charts,pages,frozen['pdf_chart_policy'])
        _apply_surface_corrections(charts,corrections)
    for requirement in visual_requirements:
        if requirement.get('required') is None:
            visual_issues.append({'location':requirement['requirement_id'],
                'reason':requirement.get('reason') or 'mechanism_reader_need_not_assessed'})
            continue
        if requirement.get('source_figure_id'):continue
        actual=next((row for row in charts if row.get('source_chart_id',row['chart_id'])==requirement.get('chart_id')),None)
        placed=bool(actual and any(ref['chart_id']==actual['chart_id'] and ref['kind']=='flow'
            for page in pages for ref in page.get('charts') or []))
        if placed:requirement.update(status='source_descriptor_referenced_pending_semantic_and_visual_review',chart_id=actual['chart_id'])
        elif requirement['required']:
            visual_issues.append({'location':requirement['requirement_id'],
                'reason':requirement.get('reason') or 'required_mechanism_not_referenced'})
    drawing_mode = frozen.get('drawing_mode', 'builtin')
    formats = frozen.get('formats') or ['markdown']
    drawing = {'requested_mode': drawing_mode, 'requested_skill_ids': frozen.get('drawing_skill_ids') or [],
        'skill_versions': frozen.get('skill_versions') or [], 'renderer': VERSION if drawing_mode == 'builtin' else None,
        'status': 'ready' if drawing_mode == 'builtin' else 'blocked_adapter_unavailable',
        'reason': None if drawing_mode == 'builtin' else '所选Skill尚无受信绘图执行适配器；未执行该Skill、未静默换用内置图。请改选内置后重新研究。'}
    if drawing_mode!='builtin':
        from app.research_figures import VERSION as FIGURE_VERSION, _drawing_data, figure_requests
        execution=result.get('chart_rendering') or {}
        requests=figure_requests(charts,pages)
        used={item['chart_id'] for item in requests}
        data_identity=identity(_drawing_data(requests))
        policy=frozen.get('drawing_policy') or {}
        bound=(execution.get('version')==FIGURE_VERSION and execution.get('status')=='rendered'
            and execution.get('task_id')==task_id and execution.get('execution_id')==execution_id
            and execution.get('descriptor_id')==frozen.get('descriptor_id')
            and execution.get('data_identity')==data_identity and execution.get('skills')==policy.get('skills'))
        assets=execution.get('assets') or []
        request_by_id={item['chart_id']:item for item in requests}
        valid_assets=(bound and {item.get('chart_id') for item in assets}==used and len(assets)==len(used)
            and all(str(item.get('svg','')).startswith('data:image/svg+xml;base64,')
                and str(item.get('png','')).startswith('data:image/png;base64,')
                and item.get('source_chart_id')==request_by_id[item['chart_id']]['source_chart_id']
                and item.get('presentation')==request_by_id[item['chart_id']]['presentation']
                and item.get('drawing_skill_id')==request_by_id[item['chart_id']].get('drawing_skill_id') for item in assets))
        no_figures=bool(layout_binding is not None and not requests and not layout_binding['required_missing'])
        drawing.update(renderer=execution.get('adapter'),status='not_needed' if no_figures else 'rendered' if valid_assets else 'blocked',
            reason=None if valid_assets or no_figures else execution.get('reason') or 'drawing_not_rendered_or_input_changed',
            skills=policy.get('skills',[]),visual_review=execution.get('visual_review','not_run'))
        if valid_assets:
            for chart in charts:
                matches=[item for item in assets if item.get('source_chart_id')==chart['chart_id']]
                if matches:chart['rendered_assets']=deepcopy(matches)
    surface_ok=True
    if (result.get('module_report') or {}).get('surface_review_policy')=='adrs-report-surfaces-v1':
        from app.report_surface_review import surface_binding
        surface_review=(audit or {}).get('surface_review') or {}
        surface_ok=(surface_review.get('passed') is True and surface_review.get('binding')==
            surface_binding(charts,source_media if source_media is not None else result.get('source_media'),
                visual_requirements if mechanism_requested else None))
    view = {'schema_version': VERSION, 'task_id': task_id, 'execution_id': execution_id,
        'delivery_complete': surface_ok and reader_quality_ok and not bool((result.get('module_report') or {}).get('issues'))
            and not pdf_issues and not visual_issues and figure_media_ok
            and drawing['status'] in {'ready','rendered','not_needed'}
            and not (layout_binding and layout_binding['required_missing'])
            and bool(audit) and not audit.get('needs_review',True) and not audit.get('audit_incomplete',False),
        'template': template, 'theme': theme, 'descriptor_id': frozen.get('descriptor_id'),
        'configuration_origin': 'frozen_task' if frozen else 'legacy_report_readonly_compatibility',
        **({'template_revision':deepcopy(frozen['template_revision'])} if frozen.get('template_revision') else {}),
        'title': (re.search(r'^#\s+(.+)$', report, re.M).group(1)[:180]
            if re.search(r'^#\s+(.+)$', report, re.M) else query[:180]),
        'question':query, 'report_markdown': reader_report,
        'main_report_markdown': main_report, 'appendix_markdown': appendix_report,
        'review_status':'draft_needs_review' if pdf_issues or visual_issues or not figure_media_ok or not surface_ok or not reader_quality_ok or not audit or audit.get('needs_review',True) else 'automatic_review_completed_human_review_pending',
        'pages': pages, 'charts': charts, 'drawing': drawing,
        **({'pdf_chart_policy':frozen['pdf_chart_policy'],'pdf_projection_issues':pdf_issues} if pdf_projection else {}),
        **({'event_timeline_policy':EVENT_POLICY,'visualization_issues':visual_issues} if timeline_enabled else {}),
        **({'mechanism_graph_policy':frozen['mechanism_graph_policy'],'visual_requirements':visual_requirements,
            'visualization_issues':visual_issues} if mechanism_requested else {}),
        'source_media':deepcopy(actual_media if figure_media_required else source_media or {'status':'not_loaded','pages':[]}),
        **({'layout_binding':layout_binding} if layout_binding is not None else {}),
        'sources': all_sources, 'citations': citations, 'audit': deepcopy(audit),
        'statistics': deepcopy(statistics), 'module_results': {key: deepcopy(result.get(field)) for key, field in
            [('relationships', 'relationship_view'), ('deep_dive', 'technical_reading'), ('evolution', 'trend_view'), ('actions', 'actions')]},
        'gaps': list(dict.fromkeys(str(gap) for gap in [*(summary.get('gaps') or []), *(result.get('gaps') or []),
            *(['未保存正文来源支持审核，不能把已生成报告标为已核实。'] if not audit else []),
            *(['所需图表尚无可用的PDF表示，报告图文交付未完成。'] if pdf_issues else []),
            *(['所需可视化仍有来源或呈现缺口。'] if visual_issues else []),
            *(['所需论文图块未完成，不能用整页预览替代。'] if not figure_media_ok else [])])),
        'formats': [{'format': name, 'status': 'ready' if name in {'markdown', 'html', 'json','pdf'} else
            'adapter_unavailable',
            'alternative': 'browser_print_to_pdf' if name == 'pdf' else None,
            'presentation': 'server_pdf_from_same_reviewed_report' if name == 'pdf' else
                'standalone_interactive' if name == 'html' else 'source_text' if name == 'markdown' else
                'structured_data' if name == 'json' else None} for name in formats],
        'full_report_available': True, 'effects': {'model_calls': 0, 'network_calls': 0, 'permissions_changed': False}}
    if source_media and source_media.get('status')=='blocked':view['delivery_complete']=False
    view['artifact_id'] = identity({'view': view, 'report': report})
    return view
