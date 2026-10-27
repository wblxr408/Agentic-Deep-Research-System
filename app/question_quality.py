"""Read-only, source-bound observations for the questions in one research task.

The model's audit is displayed as a model assessment, not as a factual verdict.
Only exact, unambiguous paragraph associations are made here; semantic matching
or attribution of an entire evidence corpus to each question would be misleading.
"""
from __future__ import annotations

from collections import Counter, defaultdict

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

    rows = []
    for key in selected:
        module = next((item for item in (contract.get('modules') or [])
                       if isinstance(item, dict) and item.get('module_id') == key), None)
        data = observations(key)
        rows.append({'module_id': key, 'module_label': MODULES[key][0],
                     'module_scope': MODULES[key][1],
                     'status': ('unknown' if not bound or module is None else
                                'recorded' if data['paragraphs'] else
                                'unmapped' if data['unmapped_paragraphs'] else 'missing'), **data})
    snapshot = identity({'version': VERSION, 'task_id': state.get('task_id'),
                         'report_binding': review.get('report_binding'),
                         'report': report, 'selected': selected, 'contract': contract, 'audit': audit})
    return {'schema_version': VERSION, 'snapshot_id': snapshot,
            'research_question': state.get('user_query') or '', 'report_binding_current': bound,
            'question_structure': 'frozen_selected_modules' if selected else 'unavailable_for_legacy_or_general_task',
            'summary': observations('summary'), 'modules': rows,
            'semantics': 'structural_mapping_and_saved_model_assessments_not_independent_fact_verification',
            'effects': {'model_calls': 0, 'network_collection': 0}}
