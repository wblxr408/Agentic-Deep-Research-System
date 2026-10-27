"""Read-only, source-bound observations for the questions in one research task.

The model's audit is displayed as a model assessment, not as a factual verdict.
Only exact, unambiguous paragraph associations are made here; semantic matching
or attribution of an entire evidence corpus to each question would be misleading.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import re

from app.organization_purpose import MODULES, report_prose
from app.query_understanding import identity


VERSION = 'adrs-question-coverage-v1'


def _paragraph_line(paragraph):
    text = paragraph.get('rendered_text')
    numbers = paragraph.get('citations')
    if not isinstance(text, str) or not isinstance(numbers, list):
        return None
    if any(type(number) is not int or number < 1 for number in numbers):
        return None
    refs = ' '.join(f'[citation:{number}]' for number in numbers)
    return (report_prose(text) + ' ' + refs).strip()


def _anchor(check, sources):
    source = sources.get(check.get('evidence_id'))
    if not source or not check.get('quote_valid'):
        return None
    text = source.get('content') or ''
    start, end = check.get('quote_start'), check.get('quote_end')
    quote = check.get('source_quote')
    if (type(start) is not int or type(end) is not int or not isinstance(text, str)
            or not isinstance(quote, str) or not 0 <= start < end <= len(text)
            or text[start:end] != quote):
        return None
    pages = [page.get('number') for page in ((source.get('acquisition') or {}).get('pages') or [])
             if isinstance(page, dict) and type(page.get('start')) is int and type(page.get('end')) is int
             and start < page['end'] and end > page['start']]
    return {'evidence_id': check['evidence_id'], 'source_title': source.get('source_title') or '',
            'source_url': source.get('source_url') or '', 'start': start, 'end': end,
            'pages': [page for page in pages if type(page) is int],
            'quote': quote[:400], 'quote_truncated': len(quote) > 400,
            'coverage': (source.get('acquisition') or {}).get('coverage', 'unknown')}


def _claim_view(claim, sources):
    checks = claim.get('source_checks') or []
    anchors = [_anchor(check, sources) for check in checks if isinstance(check, dict)]
    anchors = [anchor for anchor in anchors if anchor]
    status = claim.get('status')
    if status == 'supported' and claim.get('model_verdict') == 'supported':
        if claim.get('support_basis') == 'source_excerpt' and checks and len(anchors) == len(checks):
            assessment = 'model_source_supported'
        elif claim.get('support_basis') == 'task_method':
            assessment = 'model_task_method_supported'
        else:
            assessment = 'unavailable'
    elif status in {'contradicted', 'unverifiable', 'missing_citation', 'invalid_citation', 'not_checked'}:
        assessment = status
    else:
        assessment = 'unavailable'
    return {'claim_id': claim.get('claim_id'), 'text': claim.get('text') or '',
            'assessment': assessment, 'assessment_kind': claim.get('assessment_kind'),
            'source_anchors': anchors}


def _stored_anchor(proof, sources):
    if not isinstance(proof, dict): return None
    return _anchor({'evidence_id': proof.get('evidence_id'), 'quote_valid': True,
                    'quote_start': proof.get('start'), 'quote_end': proof.get('end'),
                    'source_quote': proof.get('quote')}, sources)


def _anchors(proofs, sources):
    return [anchor for proof in (proofs or []) if (anchor := _stored_anchor(proof, sources))]


def _technical_materials(view, sources, bound):
    from app.organization_deep_dive import FIELDS, _full_text
    cards = []
    for card in (view or {}).get('cards', []):
        fields = []
        for key, label in FIELDS.items():
            field = (card.get('fields') or {}).get(key) or {}
            proofs = field.get('proofs') or []
            anchors = _anchors(proofs, sources)
            complete = bool(proofs) and len(anchors) == len(proofs)
            if key not in {'problem', 'method_overview'}:
                complete = complete and all(_full_text(sources[anchor['evidence_id']]) for anchor in anchors)
            fields.append({'field': key, 'label': label, 'text': field.get('text'),
                           'status': 'located' if complete else 'unknown', 'source_anchors': anchors})
        figures = []
        for figure in card.get('figure_references') or []:
            if not isinstance(figure, dict): continue
            anchor = _stored_anchor(figure.get('proof'), sources)
            page = figure.get('page')
            if anchor and (page is None or page in anchor['pages']):
                figures.append({'label': figure.get('label') or '', 'page': page, 'source_anchor': anchor})
        cards.append({'output_id': card.get('output_id'), 'title': card.get('title') or '',
                      'full_text_available': card.get('full_text_available') if bound else None,
                      'fields': fields, 'figure_references': figures})
    return {'available': bool(view), 'cards': cards,
            'pending_count': len((view or {}).get('pending_records') or [])}


def _trend_materials(view, workflow, sources):
    """Associate retained trend records only with their actual saved phase."""
    origin = defaultdict(set)
    for phase, record in ((workflow or {}).get('completed') or {}).items():
        parts = phase.split(':')
        if len(parts) < 2 or parts[0] != 'question' or parts[1] not in {'evolution', 'validation'}:
            continue
        data = (record or {}).get('organization_data') or {}
        for item in data.get('trend_observations') or []:
            if isinstance(item, dict) and item.get('trend_id'):
                origin[(item['trend_id'], item.get('kind'), item.get('statement'))].add(parts[1])
    grouped = {'evolution': [], 'validation': [], 'unassigned': []}
    for item in (view or {}).get('records') or []:
        if not isinstance(item, dict): continue
        phases = origin.get((item.get('trend_id'), item.get('kind'), item.get('statement')), set())
        key = next(iter(phases)) if len(phases) == 1 else 'unassigned'
        supporting, opposing = item.get('supporting') or [], item.get('opposing') or []
        anchors = _anchors(supporting, sources)
        counter_anchors = _anchors(opposing, sources)
        grouped[key].append({'trend_id': item.get('trend_id'), 'kind': item.get('kind'),
            'statement': item.get('statement') or '', 'source_anchors': anchors, 'opposing_anchors': counter_anchors,
            'source_status': 'located' if supporting and len(anchors) == len(supporting) else 'unknown',
            'opposing_status': 'located' if opposing and len(counter_anchors) == len(opposing) else
                               'unknown' if opposing else 'not_recorded',
            'alternative_explanations': item.get('alternative_explanations') or [],
            'conditions': item.get('conditions') or [], 'horizon_start': item.get('horizon_start'),
            'horizon_end': item.get('horizon_end')})
    return grouped


def _action_materials(view, sources):
    cards = []
    for card in (view or {}).get('cards') or []:
        if not isinstance(card, dict): continue
        basis = card.get('basis') or []
        anchors = _anchors(basis, sources)
        contacts = []
        for contact in card.get('public_contacts') or []:
            if not isinstance(contact, dict): continue
            source = sources.get(contact.get('evidence_id')) or {}
            url = contact.get('url')
            if url and url in ((source.get('acquisition') or {}).get('public_links') or []):
                contacts.append({'url': url, 'evidence_id': contact['evidence_id'],
                                 'source_url': source.get('source_url') or ''})
        cards.append({'action_id': card.get('action_id'), 'entity_name': card.get('entity_name') or '',
            'mode': card.get('mode'), 'question': card.get('question'), 'steps': card.get('proposed_steps') or [],
            'source_anchors': anchors, 'source_status': 'located' if basis and len(anchors) == len(basis) else 'unknown',
            'missing_requirements': card.get('missing_requirements') or [],
            'public_contacts': contacts, 'status': card.get('status')})
    return {'available': bool(view), 'cards': cards,
            'pending_count': len((view or {}).get('pending_records') or [])}


def question_quality(state):
    """Observe selected module coverage using the existing task snapshot only."""
    from app.db.report_delivery import report_binding

    review = state.get('review_status') or {}
    config = state.get('organization_research') or {}
    result = state.get('organization_result') or {}
    audit = review.get('final_report_audit') or {}
    report = state.get('final_report') or ''
    bound = bool(report and review.get('report_payload_kind') == 'report'
                 and review.get('report_binding') == report_binding(state))
    contract = (audit.get('module_contract') or result.get('module_report') or {}) if bound else {}
    selected = [key for key in config.get('modules', []) if key in MODULES]
    evidence = [item for item in (state.get('collected_evidence') or []) if isinstance(item, dict)]
    sources = {item['evidence_id']: item for item in evidence if item.get('evidence_id')}
    sections = []
    if isinstance(contract.get('summary'), list):
        sections.append(('summary', contract['summary']))
    for module in contract.get('modules') or []:
        if isinstance(module, dict) and module.get('module_id') in selected:
            sections.append((module['module_id'], (module.get('paragraphs') or []) + (module.get('appendix') or [])))
    owners = defaultdict(list)
    for key, paragraphs in sections:
        for item in paragraphs:
            line = _paragraph_line(item) if isinstance(item, dict) else None
            if line: owners[line].append(key)
    lines = Counter(line.strip() for line in report.splitlines() if line.strip())
    claims = defaultdict(list)
    if bound and not audit.get('disclosure_requires_revision'):
        for claim in audit.get('claims') or []:
            if isinstance(claim, dict) and claim.get('paragraph_context'):
                claims[claim['paragraph_context'].strip()].append(claim)

    def observations(key):
        mapped = []
        missing_or_ambiguous = 0
        for section, paragraphs in sections:
            if section != key: continue
            for paragraph in paragraphs:
                if not isinstance(paragraph, dict): continue
                line = _paragraph_line(paragraph)
                if not line or len(owners[line]) != 1 or lines[line] != 1:
                    missing_or_ambiguous += 1
                    continue
                paragraph_claims = [_claim_view(row, sources) for row in claims.get(line, [])]
                mapped.append({'text': paragraph['rendered_text'], 'kind': paragraph.get('kind'),
                               'citations': paragraph.get('citations', []), 'claims': paragraph_claims,
                               'assessment': 'claims_recorded' if paragraph_claims else 'audit_unavailable'})
        return {'paragraphs': mapped, 'unmapped_paragraphs': missing_or_ambiguous}

    trends = _trend_materials(result.get('trend_view'), state.get('analysis_workflow'), sources)
    topics = {'deep_dive': _technical_materials(result.get('technical_reading'), sources, bound),
              'evolution': {'available': bool(result.get('trend_view')), 'records': trends['evolution']},
              'validation': {'available': bool(result.get('trend_view')), 'records': trends['validation']},
              'actions': _action_materials(result.get('actions'), sources)}
    rows = []
    for key in selected:
        module = next((item for item in (contract.get('modules') or [])
                       if isinstance(item, dict) and item.get('module_id') == key), None)
        data = observations(key)
        rows.append({'module_id': key, 'module_label': MODULES[key][0],
                     'module_scope': MODULES[key][1],
                     'status': ('unknown' if not bound or module is None else
                                'recorded' if data['paragraphs'] else
                                'unmapped' if data['unmapped_paragraphs'] else 'missing'),
                     'materials': topics.get(key), **data})
    if not selected and bound:
        # A general task has one user question but no frozen module contract.
        # Show saved report claims without pretending that they answer it.
        general = []
        for line, matching in claims.items():
            if lines[line] != 1: continue
            general.append({'text': re.sub(r'\[citation:\d+\]', '', line).strip(), 'kind': None,
                            'citations': [], 'claims': [_claim_view(row, sources) for row in matching],
                            'assessment': 'claims_recorded'})
        rows.append({'module_id': 'report', 'module_label': '报告内容', 'module_scope': '',
                     'status': 'recorded' if general else 'unknown', 'materials': None,
                     'paragraphs': general, 'unmapped_paragraphs': 0})
    snapshot = identity({'version': VERSION, 'task_id': state.get('task_id'),
                         'report_binding': review.get('report_binding'),
                         'report': report, 'selected': selected, 'contract': contract, 'audit': audit,
                         'materials': topics, 'unassigned_trends': trends['unassigned']})
    return {'schema_version': VERSION, 'snapshot_id': snapshot,
            'research_question': state.get('user_query') or '', 'report_binding_current': bound,
            'question_structure': 'frozen_selected_modules' if selected else 'general_report' if bound else 'unavailable_for_legacy_or_general_task',
            'summary': observations('summary'), 'modules': rows,
            'unassigned_trends': trends['unassigned'] if {'evolution', 'validation'} & set(selected) else [],
            'semantics': 'structural_mapping_and_saved_model_assessments_not_independent_fact_verification',
            'effects': {'model_calls': 0, 'network_collection': 0}}
