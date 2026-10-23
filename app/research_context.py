"""Bounded source passages and reading context; no new tool or model authority."""
from __future__ import annotations

import json
import re

from app.claim_verification import select_excerpts
from app.llm_budget import TokenBudgetExceeded, request_token_bound

ROLES = {
    'method': r'method|design|architecture|mechanism|approach|方法|架构|机制',
    'evaluation': r'evaluation|experiment|setup|baseline|result|实验|评估|结果',
    'limitations': r'limitation|discussion|conclusion|局限|讨论|结论',
}
CONDITION_QUERIES = {
    'experimental_design': 'evaluation methodology experimental design study design protocol measurement setup dataset samples',
    'baselines': 'comparison baseline control group reference method competing approach experimental comparison',
    'conditions': 'experimental setup conditions configuration sample size hardware environment workload parameters inclusion criteria',
    'results': 'evaluation results measurements confidence interval effect size sensitivity performance analysis',
}


def analysis_binding(query, configuration, skills, hints, evidence):
    """Bind retained question phases to their exact frozen model inputs."""
    from app.query_understanding import identity
    from app.evidence_selection import VERSION as SELECTION_VERSION
    return identity({'version':'adrs-analysis-questions-v2','query':query,'configuration':configuration,
        'context_selection_version':SELECTION_VERSION,
        'skills':skills,'hints':hints,'evidence':[
            {'id':item.evidence_id,'url':item.source_url,'content':item.content,'acquisition':item.acquisition}
            for item in evidence]})


def identity_batches(evidence):
    """Keep acquired full text with retained publisher links, two groups/call.

    Grouping only selects reading context. It does not prove work identity or
    transfer affiliation/date authority between different publications.
    """
    from app.organization_findings import _publication_url
    primary=[item for item in evidence if (item.acquisition or {}).get('coverage')=='full_text']
    publishers=[item for item in evidence if (item.acquisition or {}).get('publisher_metadata')]
    groups=[];seen=set()
    for item in primary:
        if item.evidence_id in seen:continue
        ids=[item.evidence_id]
        url=_publication_url(item.source_url)
        for page in publishers:
            links=(page.acquisition or {}).get('document_links') or []
            if url==_publication_url(page.source_url) or url in {_publication_url(link) for link in links if isinstance(link,str)}:
                ids.append(page.evidence_id)
        groups.append(list(dict.fromkeys(ids)));seen.update(ids)
    for item in publishers:
        if item.evidence_id not in seen:groups.append([item.evidence_id]);seen.add(item.evidence_id)
    if not groups:groups=[[item.evidence_id] for item in evidence]
    return [list(dict.fromkeys(key for group in groups[index:index+2] for key in group))
        for index in range(0,len(groups),2)] or [[]]


def encoded(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def byte_prefix(text: str, limit: int) -> str:
    return text.encode('utf-8')[:max(0, limit)].decode('utf-8', errors='ignore')


def _paragraph_window(text, start, end):
    """Keep a hit's neighbouring conditions inside bounded paragraph units."""
    lower=max(0,start-600);upper=min(len(text),end+1200)
    before=text.rfind('\n\n',lower,start)
    after=text.find('\n\n',end,upper)
    if before>=0:lower=before+2
    if after>=0:upper=after
    return lower,upper


def _ranges(source, query, deep, focus=None):
    text, meta = source.content, source.acquisition or {}
    spans = []
    for role, pattern in ROLES.items() if deep else []:
        sections = [item for item in meta.get('scientific_sections', [])
            if isinstance(item, dict) and re.search(pattern, str(item.get('label', '')), re.I)
            and isinstance(item.get('start'), int) and isinstance(item.get('end'), int)
            and 0 <= item['start'] < item['end'] <= len(text)]
        if sections:
            spans.append((role, sections[0]['start'], sections[0]['end']))
        else:
            hits = re.finditer(r'(?im)^[ \t]*(?:\d+(?:\.\d+)*\.?[ \t]+)?(?:[A-Za-z]+[ \t]+){0,2}(?:' + pattern + r')[A-Za-z :/—–-]{0,45}[ \t]*$', text)
            hit = next((item for item in hits if item.start() >= (1200 if meta.get('format') == 'pdf' and len(text)>5000 else 0)), None)
            if hit:
                spans.append((role, hit.start(), min(len(text), hit.start()+2400)))
    # Retrieval searches the entire retained body. Section windows alone can
    # miss an experiment's hardware/workload in an unlabelled subsection.
    lookup = query
    if deep:
        lookup=query+' method experimental setup baseline results measurement conditions dataset samples'
        if re.search(r'computer science|计算机|LLM|inference|GPU|大模型',query,re.I):
            lookup+=' hardware GPU model workload trace TTFT TPOT SLO'
    for item in select_excerpts(lookup, [source], max_sources=1, window=1200, windows_per_source=2):
        if item['quote'] and not any(start <= item['start'] < end for _, start, end in spans):
            spans.append(('question', item['start'], item['end']))
    if deep:
        requested=focus or tuple(CONDITION_QUERIES)
        for role in requested:
            if role not in CONDITION_QUERIES:continue
            field_query=CONDITION_QUERIES[role]
            if re.search(r'computer science|计算机|LLM|inference|GPU|大模型',query,re.I):
                field_query+=' GPU model workload trace latency throughput SLO'
            for item in select_excerpts(field_query,[source],max_sources=1,window=1600,windows_per_source=2):
                if item['quote']:
                    lower,upper=_paragraph_window(text,item['start'],item['end'])
                    spans.append((role,lower,upper))
    if not any(start == 0 for _, start, _ in spans):
        spans.append(('identity', 0, min(len(text), 1400)))
    # Publisher cover sheets can precede the actual title/author block. Keep
    # the next opening page as data, rather than treating a cover as the work's
    # complete attribution. This is not itself an affiliation judgement.
    pages = meta.get('pages') or []
    if meta.get('format') == 'pdf' and len(pages)>1:
        page = pages[1]; start, end = page.get('start'), page.get('end')
        if isinstance(start,int) and isinstance(end,int) and 0<=start<end<=len(text) and not any(lower<=start<upper for _,lower,upper in spans):
            spans.append(('opening_page_continuation', start, min(end,start+1800)))
    # Prioritise explicit condition retrieval in a condition-only follow-up.
    if focus:spans.sort(key=lambda row:0 if row[0] in focus else 1)
    return spans


def evidence_context(evidence, query: str, *, deep: bool, max_bytes: int, preferred_ids=None, focus=None, identity_only=False) -> tuple[str, dict]:
    """Distribute a UTF-8 payload allowance across sources, retaining exact spans.

    Omitted documents/passages remain in the task evidence. This is selection,
    never a claim of reading the full source or verifying its conclusions.
    """
    rows, omitted = [], []
    allowance = max(0, max_bytes-160)
    # Prefer useful passages from fewer sources to eight-character fragments
    # from every paper. Original citation numbers never change.
    indexed = list(enumerate(evidence, 1))
    primary = [item for item in indexed if (item[1].acquisition or {}).get('coverage') == 'full_text']
    from app.evidence_selection import source_priority,context_coverage,excerpt_anchor
    from app.evidence_ingestion import retained_evidence_identity
    priority,assessment=source_priority(evidence,query,preferred_ids=preferred_ids,identity_only=identity_only,deep=deep)
    retained = priority if identity_only else priority[:max(1, allowance//(7000 if deep else 2200))]
    chosen_ids = {source.evidence_id for _, source in retained}
    omitted.extend(source.evidence_id for source in evidence if source.evidence_id not in chosen_ids)
    weights={source.evidence_id:3 if (deep or identity_only) and (number,source) in primary else 1 for number,source in retained}
    for number, source in retained:
        quota=allowance*weights[source.evidence_id]//max(1,sum(weights.values()))
        meta = source.acquisition or {}
        retained_identity=retained_evidence_identity(source.model_dump(mode='json'))
        record = {'citation_id': number, 'evidence_id': source.evidence_id,
            'title': byte_prefix(source.source_title or '', 250),
            'url': byte_prefix(source.source_url or '', 1000),
            'source_coverage': meta.get('coverage', 'unspecified'),
            'source_truncated': meta.get('truncated'), 'model_read_entire_document': False,
            'structure_truncated': meta.get('structure_truncated'),
            'source_document_id': meta.get('source_document_id'), 'parse_version_id': meta.get('parse_version_id'),
            'retained_source_id':retained_identity['source_id'],'retained_version_id':retained_identity['version_id'],
            'source_type':source.source_type,'source_channel':source.source_channel,
            'collected_at':source.collected_at,'source_time_declarations':meta.get('time_declarations'),
            'chunk_reference':meta.get('chunk_reference'),
            'offset_unit': 'task_retained_evidence_character', 'excerpts': []}
        if identity_only:
            pages=meta.get('pages') or []
            opening=max((page['end'] for page in pages[:2] if isinstance(page,dict)
                and isinstance(page.get('end'),int)),default=6000)
            opening=min(len(source.content),16000,opening or 6000)
            room=max(0,quota-len(encoded(record).encode('utf-8'))-240)
            quote=byte_prefix(source.content[:opening],room)
            if len(quote.encode('utf-8'))<320:omitted.append(source.evidence_id);continue
            record['excerpts']=[{'role':'publication_identity','start':0,'end':len(quote),'quote':quote,
                'opening_complete':len(quote)==opening,
                'pages':[page['number'] for page in pages if isinstance(page,dict)
                    and isinstance(page.get('start'),int) and page['start']<len(quote) and 'number' in page]}]
            while quote and len(encoded(record).encode('utf-8'))>quota:
                excess=len(encoded(record).encode('utf-8'))-quota
                quote=byte_prefix(quote,max(0,len(quote.encode('utf-8'))-excess-128))
                record['excerpts'][0].update(quote=quote,end=len(quote),opening_complete=len(quote)==opening,
                    pages=[page['number'] for page in pages if isinstance(page,dict)
                        and isinstance(page.get('start'),int) and page['start']<len(quote) and 'number' in page])
            if len(quote.encode('utf-8'))<320:omitted.append(source.evidence_id);continue
            if len(encoded(record).encode('utf-8'))<=quota:rows.append(record)
            else:omitted.append(source.evidence_id)
            continue
        ranges = _ranges(source, query, deep, focus=focus)
        if deep:
            # Merge overlaps once while preserving every retrieval role. A
            # single experimental paragraph often answers several fields.
            merged=[]
            for role,start,end in sorted(ranges,key=lambda row:row[1]):
                end=min(end,start+5000)
                if merged and start<=merged[-1]['end'] and max(merged[-1]['end'],end)-merged[-1]['start']<=6000:
                    merged[-1]['end']=max(merged[-1]['end'],end)
                    if role not in merged[-1]['roles']:merged[-1]['roles'].append(role)
                else:merged.append({'start':start,'end':end,'roles':[role]})
            desired=list(focus or CONDITION_QUERIES)
            merged.sort(key=lambda item:(-sum(role in item['roles'] for role in desired),item['start']))
            covered=set()
            for item in merged:
                start,end=item['start'],item['end']
                excerpt={'role':item['roles'][0],'roles':item['roles'],'start':start,'end':end,
                    'quote':source.content[start:end],'boundary':'retained_bounded_window_not_full_section',
                    'pages':[p['number'] for p in meta.get('pages',[]) if isinstance(p,dict)
                        and isinstance(p.get('start'),int) and isinstance(p.get('end'),int)
                        and start<p['end'] and end>p['start'] and 'number' in p]}
                candidate={**record,'excerpts':[*record['excerpts'],excerpt]}
                if len(encoded(candidate).encode('utf-8'))<=quota-600:
                    record=candidate;covered.update(item['roles'])
            record['reading_facets']={role:'selected_window' if role in covered else 'not_selected'
                for role in desired}
            record['facet_interpretation']='retrieval_roles_not_semantic_completeness'
            if record['excerpts'] and len(encoded(record).encode('utf-8'))<=quota:rows.append(record)
            else:omitted.append(source.evidence_id)
            continue
        room = quota-len(encoded(record).encode('utf-8'))-len(ranges)*100
        per_window = min(2200, max(0, room//max(1, len(ranges))))
        for role, start, end in ranges:
            quote = byte_prefix(source.content[start:end], per_window)
            if not quote:
                continue
            end = start+len(quote)
            record['excerpts'].append({'role': role, 'start': start, 'end': end, 'quote': quote,
                'pages': [p['number'] for p in meta.get('pages', []) if isinstance(p, dict)
                    and isinstance(p.get('start'), int) and isinstance(p.get('end'), int)
                    and start < p['end'] and end > p['start'] and 'number' in p]})
        # Budget complete JSON records, rather than slicing JSON or locators.
        if per_window < 160 or not record['excerpts'] or len(encoded(record).encode('utf-8')) > quota:
            omitted.append(source.evidence_id)
        else:
            rows.append(record)
    by_id={source.evidence_id:source for source in evidence}
    for row in rows:
        source=by_id[row['evidence_id']]
        for excerpt in row['excerpts']:
            excerpt['anchor']=excerpt_anchor(source,excerpt)
        # The selected windows can be priority ordered rather than position ordered.
        intervals=[]
        for start,end in sorted((part['start'],part['end']) for part in row['excerpts']):
            if intervals and start<=intervals[-1][1]:intervals[-1]=(intervals[-1][0],max(end,intervals[-1][1]))
            else:intervals.append((start,end))
        selected_characters=sum(end-start for start,end in intervals)
        row['compression']={'method':'literal_extractive_windows_no_generated_summary',
            'retained_source_characters':len(source.content),'selected_unique_characters':selected_characters,
            'omitted_characters':max(0,len(source.content)-selected_characters),
            'semantic_information_loss':'not_measured'}
    omitted=list(dict.fromkeys(omitted))
    # Models need evidence and citation positions; engineering diagnostics and
    # retained-version identities stay in the research record, not writing input.
    prompt_sources=[]
    for row in rows:
        prompt_sources.append({**{key:row[key] for key in ('citation_id','evidence_id','title','url',
            'source_coverage','source_truncated','source_time_declarations') if key in row},
            'excerpts':[{key:part[key] for key in ('role','roles','start','end','quote','pages','boundary') if key in part}
                for part in row['excerpts']]})
    payload = {'sources': prompt_sources, 'omitted_evidence_ids': omitted}
    while rows and len(encoded(payload).encode('utf-8')) > max_bytes:
        omitted.append(rows.pop()['evidence_id'])
        prompt_sources.pop()
    manifest = {'sources': rows, 'omitted_evidence_ids': omitted,
        'total_sources': len(evidence), 'selected_sources': len(rows),
        'selection': 'per_source_method_evaluation_question_windows',
        'source_selection':assessment,
        'conclusion_coverage': 'not_assessed', 'offset_unit': 'task_retained_evidence_character'}
    manifest['question_evidence']=context_coverage(manifest,assessment,deep=deep and not identity_only,focus=focus)
    return encoded(payload), manifest


def analysis_context(text: str, max_bytes: int) -> tuple[str, int]:
    """Keep whole paragraph units distributed across H2 sections."""
    sections = re.split(r'(?m)(?=^## )', text)
    groups = [[block for block in section.split('\n\n') if block.strip()] for section in sections if section.strip()]
    selected, used = [], 0
    for depth in range(max((len(group) for group in groups), default=0)):
        for number, group in enumerate(groups):
            if depth >= len(group):
                continue
            block = group[depth]
            size = len(block.encode('utf-8'))+2
            if used+size <= max_bytes:
                selected.append((number, depth, block)); used += size
    selected.sort()
    return '\n\n'.join(row[2] for row in selected), sum(map(len, groups))-len(selected)


def fit_messages(builder, budget, purpose: str, output_tokens: int, *, max_bytes: int, request_extra=None):
    """Pack optional materials before provider admission, preserving output room.

    The existing trusted meter remains authoritative. No reservation, retries,
    token estimates masquerading as native usage, or budget reset occurs here.
    """
    allowance = max_bytes
    while True:
        messages, manifest = builder(allowance)
        bound = request_token_bound(messages, **(request_extra or {}))
        if budget is None or bound+output_tokens <= budget.available(purpose):
            manifest.update(prompt_bound=bound, requested_output_tokens=output_tokens)
            return messages, manifest
        if allowance <= 512:
            error=TokenBudgetExceeded('insufficient_context_budget')
            error.admission={'prompt_bound':bound,'requested_output_tokens':output_tokens,
                'available_tokens':budget.available(purpose),'attempted_material_bytes':allowance,
                'context_limit':getattr(budget,'context_limit',None)}
            raise error
        allowance = max(512, min(int(allowance*.75), allowance-(bound+output_tokens-budget.available(purpose))))
