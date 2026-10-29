"""Bounded source passages and reading context; no new tool or model authority."""
from __future__ import annotations

import json
import re
from copy import deepcopy

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

IDENTITY_CONTEXT_VERSION = 'adrs-publication-identity-v2'
QUESTION_SEED_VERSION = 'adrs-question-publication-seed-v5'
LEGACY_CONTEXT_PACKING_VERSION = 'adrs-context-packing-v1'
CONTEXT_PACKING_VERSION = 'adrs-context-packing-v2'


def analysis_binding(query, configuration, skills, hints, evidence, *, packing_version=CONTEXT_PACKING_VERSION,
                     research_strategy_version=None):
    """Bind retained question phases to their exact frozen model inputs."""
    from app.query_understanding import identity
    from app.evidence_selection import VERSION as SELECTION_VERSION
    bound={'version':'adrs-analysis-questions-v2','query':query,'configuration':configuration,
        'identity_context_version':IDENTITY_CONTEXT_VERSION,
        'question_seed_version':QUESTION_SEED_VERSION,
        'context_selection_version':SELECTION_VERSION,
        'skills':skills,'hints':hints,'evidence':[
            {'id':item.evidence_id,'url':item.source_url,'content':item.content,'acquisition':item.acquisition}
            for item in evidence]}
    # Keep the exact historical binding for existing roots; new roots explicitly
    # bind the packing contract before any phase is checkpointed.
    if packing_version != LEGACY_CONTEXT_PACKING_VERSION:
        bound['context_packing_version']=packing_version
    if research_strategy_version:
        bound['research_strategy_version']=research_strategy_version
    return identity(bound)


def workflow_packing_version(workflow):
    return (workflow or {}).get('context_packing_version', LEGACY_CONTEXT_PACKING_VERSION)


RETAINED_SYNTHESIS_VERSION = 'adrs-retained-synthesis-v1'


def _synthesis_identity(state):
    root=state.get('session') or {}
    return {key:str(value) if value is not None else None for key,value in {
        'owner_id':root.get('owner_id'),'task_id':state.get('task_id'),
        'execution_id':root.get('execution_id')}.items()}


def _bound_evidence_subset(evidence, identifiers):
    if (not isinstance(identifiers,list) or not identifiers
            or not all(isinstance(item,str) for item in identifiers)
            or len(set(identifiers))!=len(identifiers)):
        return None
    by_id={item.evidence_id:item for item in evidence}
    if len(by_id)!=len(evidence) or any(item not in by_id for item in identifiers):
        return None
    return [by_id[item] for item in identifiers]


def capture_retained_synthesis(state, query, skills, hints):
    """Keep the completed input/result before a bounded acquisition round."""
    from app.graph.state import deserialize_evidence
    from app.planning_control import retained_evidence_version
    workflow=state.get('analysis_workflow') or {}
    identity=_synthesis_identity(state)
    if (not all(identity.values()) or not state.get('analysis')
            or workflow.get('status')!='completed'
            or workflow.get('question_seed_version')!=QUESTION_SEED_VERSION
            or state.get('evidence_access_gaps')):
        return None
    evidence=[deserialize_evidence(item) for item in state.get('collected_evidence',[])]
    identifiers=[item.evidence_id for item in evidence]
    if (_bound_evidence_subset(evidence,identifiers) is None
            or workflow.get('binding')!=analysis_binding(query,state.get('organization_research'),skills,hints,evidence,
                packing_version=workflow_packing_version(workflow),research_strategy_version=workflow.get('research_strategy_version'))):
        return None
    return deepcopy({'version':RETAINED_SYNTHESIS_VERSION,**identity,
        'material_version':retained_evidence_version(state),'evidence_ids':identifiers,
        'analysis':state['analysis'],'workflow':workflow,
        'organization_result':state.get('organization_result'),
        'verification':state.get('verification')})


def reuse_retained_synthesis(state, query, skills, hints):
    """Reuse only after current access checks and exact original-input checks."""
    from app.graph.state import deserialize_evidence
    from app.planning_control import retained_evidence_version
    frame=state.get('retained_synthesis') or {}
    identity=_synthesis_identity(state)
    if (frame.get('version')!=RETAINED_SYNTHESIS_VERSION or not all(identity.values())
            or any(frame.get(key)!=value for key,value in identity.items())
            or state.get('evidence_access_gaps')
            or frame.get('material_version')!=retained_evidence_version(state)):
        return None
    workflow=frame.get('workflow') or {}
    if (not frame.get('analysis') or workflow.get('status')!='completed'
            or workflow.get('question_seed_version')!=QUESTION_SEED_VERSION):
        return None
    evidence=[deserialize_evidence(item) for item in state.get('collected_evidence',[])]
    subset=_bound_evidence_subset(evidence,frame.get('evidence_ids'))
    if (subset is None or workflow.get('binding')!=analysis_binding(
            query,state.get('organization_research'),skills,hints,subset,packing_version=workflow_packing_version(workflow),
            research_strategy_version=workflow.get('research_strategy_version'))):
        return None
    workflow=deepcopy(workflow)
    workflow['retained_material_reuse']={'version':RETAINED_SYNTHESIS_VERSION,**identity,
        'original_binding':workflow['binding'],'evidence_ids':list(frame['evidence_ids']),
        'material_version':frame['material_version'],
        'current_binding':analysis_binding(query,state.get('organization_research'),skills,hints,evidence,
            packing_version=workflow_packing_version(workflow),research_strategy_version=workflow.get('research_strategy_version'))}
    return {'analysis':frame['analysis'],'analysis_workflow':workflow,
        'organization_result':deepcopy(frame.get('organization_result')),
        'verification':deepcopy(frame.get('verification'))}


def analysis_input_matches(state, query, skills, hints, evidence):
    """A report continuation retains both the original and extended bindings."""
    from app.planning_control import retained_evidence_version
    workflow=state.get('analysis_workflow') or {}
    packing_version=workflow_packing_version(workflow)
    expected=analysis_binding(query,state.get('organization_research'),skills,hints,evidence,packing_version=packing_version,
        research_strategy_version=workflow.get('research_strategy_version'))
    if workflow.get('binding')==expected:
        return True
    reuse=workflow.get('retained_material_reuse') or {}
    identity=_synthesis_identity(state)
    if (reuse.get('version')!=RETAINED_SYNTHESIS_VERSION or not all(identity.values())
            or any(reuse.get(key)!=value for key,value in identity.items())
            or state.get('evidence_access_gaps')
            or reuse.get('current_binding')!=expected
            or reuse.get('original_binding')!=workflow.get('binding')
            or reuse.get('material_version')!=retained_evidence_version(state)):
        return False
    subset=_bound_evidence_subset(evidence,reuse.get('evidence_ids'))
    return subset is not None and workflow['binding']==analysis_binding(
        query,state.get('organization_research'),skills,hints,subset,packing_version=packing_version,
        research_strategy_version=workflow.get('research_strategy_version'))


def identity_batches(evidence, *, acquired_only=False, configuration=None):
    """Keep acquired full text with retained publisher links, two groups/call.

    Grouping only selects reading context. It does not prove work identity or
    transfer affiliation/date authority between different publications.
    """
    from app.organization_findings import _publication_url
    if acquired_only:
        evidence=[item for item in evidence if (item.acquisition or {}).get('coverage')!='discovery_only']
    primary=[item for item in evidence if (item.acquisition or {}).get('coverage')=='full_text']
    publishers=[item for item in evidence if (item.acquisition or {}).get('publisher_metadata') or (
        (item.acquisition or {}).get('coverage') != 'discovery_only' and
        re.search(r'(?m)^citation_title:\s*\S',item.content[:8000]) and
        re.search(r'(?m)^citation_(?:publication_)?date:\s*\S',item.content[:8000]))]
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
    batches = [list(dict.fromkeys(key for group in groups[index:index+2] for key in group))
        for index in range(0,len(groups),2)] or [[]]
    if configuration:
        from app.organization_identity import identity_sources
        anchors = identity_sources(configuration,[item.model_dump(mode='json') for item in evidence])
        # Use the existing first extraction call. Current official-language
        # entrances supply names, not a separate autonomous identity agent.
        names = list(dict.fromkeys(key for ids in anchors.values() for key in ids))
        batches[0] = list(dict.fromkeys([*names,*batches[0]]))
    return batches


def encoded(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def question_seed(seed, *, deep=False, max_bytes=12000):
    """Keep every assigned deep-reading identity, without repeating attribution.

    Full validated affiliations remain in the root. Deep reading consumes the
    accepted work identity and its source mapping, not another attribution
    extraction. Actual provider admission still bounds the complete message.
    """
    value=deepcopy(seed or {})
    value.pop('pending_records',None)
    value['omitted_output_ids']=[]
    if deep:
        value['outputs']=[{key:item for key,item in output.items() if key!='affiliations'}
            for output in value.get('outputs',[])]
        value['attribution_context']='server_accepted_affiliations_retained_in_root_not_reextracted_here'
    else:
        while value.get('outputs') and len(encoded(value).encode('utf-8'))>max_bytes:
            removed=value['outputs'].pop()
            value['omitted_output_ids'].append(removed['output_id'])
            value.get('publication_metadata',{}).pop(removed['output_id'],None)
    manifest={'version':QUESTION_SEED_VERSION,'selected_output_ids':[item['output_id'] for item in value.get('outputs',[])],
        'omitted_output_ids':list(value['omitted_output_ids']),
        'all_assigned_identities_required':deep,'retained_seed_bytes':len(encoded(value).encode('utf-8')),
        'affiliation_details':'retained_in_root' if deep else 'included_for_selected_outputs',
        'source_reading_and_semantic_support':'not_established_by_seed_presence'}
    return value,manifest


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


def reading_source_spans(reading, evidence, analysis_workflow=None):
    """Use located technical proofs as retrieval hints, never as verdicts.

    Recheck exact retained text before carrying an old card's location into a
    new writing context. No field summary is substituted for source content.
    """
    sources={source.evidence_id:source for source in evidence}
    spans={}
    for card in (reading or {}).get('cards',[]):
        for field,statement in card.get('fields',{}).items():
            if statement.get('status')!='source_summary_requires_semantic_review':continue
            for proof in statement.get('proofs',[]):
                source=sources.get(proof.get('evidence_id'))
                start,end=proof.get('start'),proof.get('end')
                if source is None or type(start) is not int or type(end) is not int:continue
                if not 0<=start<end<=len(source.content) or source.content[start:end]!=proof.get('quote'):continue
                spans.setdefault(source.evidence_id,[]).append((field,start,end))
    if not analysis_workflow:
        return spans
    from app.organization_deep_dive import FIELDS
    from app.organization_findings import _publication_url
    by_url={}
    for source in evidence:
        if source.source_url and (source.acquisition or {}).get('coverage')!='discovery_only':
            by_url.setdefault(_publication_url(source.source_url),[]).append(source)
    for record in (analysis_workflow.get('completed') or {}).values():
        if not isinstance(record,dict):continue
        data=record.get('organization_data')
        if not isinstance(data,dict) or not isinstance(data.get('technical_cards'),list):continue
        for card in data['technical_cards'][:20]:
            if not isinstance(card,dict) or not isinstance(card.get('fields'),dict):continue
            for field,statement in card['fields'].items():
                if field not in FIELDS or not isinstance(statement,dict):continue
                if not isinstance(statement.get('proofs'),list):continue
                for proof in statement['proofs'][:5]:
                    if not isinstance(proof,dict):continue
                    if not isinstance(proof.get('evidence_id'),str):continue
                    source=sources.get(proof['evidence_id']);quote=proof.get('quote')
                    if source is None or not isinstance(quote,str) or len(quote)>2400 or len(quote.strip())<12:continue
                    if not source.source_url or (source.acquisition or {}).get('coverage')=='discovery_only':continue
                    # Layout tolerance locates actual text, never accepts the
                    # candidate summary or substitutes normalized source bytes.
                    literal_pattern=r'\s+'.join(re.escape(word) for word in quote.split())
                    parts=[]
                    for word in quote.split():
                        parts.append(r'(?:-\s*\r?\n\s*)?'.join(re.escape(char) for char in word)
                            if re.fullmatch(r'[A-Za-z]{4,64}',word) else re.escape(word).replace(r'\-',r'-\s*'))
                    pattern=r'\s+'.join(parts)
                    for current in by_url.get(_publication_url(source.source_url),[]):
                        match=re.search(literal_pattern,current.content,re.I)
                        if not match and (current.acquisition or {}).get('format')=='pdf':
                            match=re.search(pattern,current.content,re.I)
                        if match:
                            item=(field,match.start(),match.end())
                            if item not in spans.setdefault(current.evidence_id,[]):spans[current.evidence_id].append(item)
    return spans


def _ranges(source, query, deep, focus=None, located_spans=None):
    text, meta = source.content, source.acquisition or {}
    spans = []
    if deep:
        for field,start,end in located_spans or []:
            lower,upper=_paragraph_window(text,start,end)
            spans.append((field,lower,upper))
            spans.append(('retained_field_proof',lower,upper))
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


def _bounded_deep_excerpt(record, item, source, meta, quota, proofs):
    """Fit a literal window; a located proof is either complete or not selected."""
    lower, upper = item['start'], item['end']
    proof = next(((field, start, end) for field, start, end in proofs
        if lower <= start < end <= upper and field in item['roles']), None)

    def make(start, end):
        roles=[]
        for role, role_start, role_end in item['entries']:
            if not (start < role_end and end > role_start):
                continue
            relevant=[(a,b) for field,a,b in proofs if field==role and lower<=a<b<=upper]
            if role=='retained_field_proof':
                relevant=[(a,b) for _,a,b in proofs if lower<=a<b<=upper]
            if relevant and not any(start<=a and b<=end for a,b in relevant):
                continue
            if role not in roles:roles.append(role)
        if not roles:return None
        return {'role':roles[0], 'roles':roles, 'start':start, 'end':end,
            'quote':source.content[start:end],
            'boundary':'retained_bounded_window_not_full_section' if start==lower and end==upper
                else 'literal_window_reduced_to_fit_context',
            'pages':[p['number'] for p in meta.get('pages',[]) if isinstance(p,dict)
                and isinstance(p.get('start'),int) and isinstance(p.get('end'),int)
                and start<p['end'] and end>p['start'] and 'number' in p]}

    ceiling=quota-600
    current=len(encoded(record).encode('utf-8'))
    share=min(ceiling,current+max(800,(ceiling-current)//2))

    def fits(excerpt, limit=ceiling):
        return excerpt is not None and len(encoded({**record,'excerpts':[*record['excerpts'],excerpt]}).encode('utf-8'))<=limit

    whole=make(lower,upper)
    if fits(whole):return whole
    if proof:
        _,start,end=proof
        if not fits(make(start,end)):return None
        limit=share if fits(make(start,end),share) else ceiling
        # Grow around the entire proof, never truncate its actual source text.
        left,right=0,max(start-lower,upper-end)
        while left<right:
            size=(left+right+1)//2
            if fits(make(max(lower,start-size),min(upper,end+size)),limit):left=size
            else:right=size-1
        return make(max(lower,start-left),min(upper,end+left))
    minimum=min(upper-lower,160)
    if minimum<=0 or not fits(make(lower,lower+minimum)):return None
    limit=share if fits(make(lower,lower+minimum),share) else ceiling
    left,right=minimum,upper-lower
    while left<right:
        size=(left+right+1)//2
        if fits(make(lower,lower+size),limit):left=size
        else:right=size-1
    end=lower+left
    # Prefer a sentence or line boundary without changing the source offset.
    boundary=max(source.content.rfind(mark,lower+minimum,end) for mark in ('\n','。','. '))
    if boundary>=lower+minimum and boundary>=end-240:end=boundary+1
    return make(lower,end)


def evidence_context(evidence, query: str, *, deep: bool, max_bytes: int, preferred_ids=None, focus=None, identity_only=False,
                     located_spans=None, required_groups=None, packing_version=CONTEXT_PACKING_VERSION,
                     acquired_only=False) -> tuple[str, dict]:
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
    if acquired_only:
        # Filter ranked pairs, not the original evidence array: source numbers
        # are shared by analysis, writing, audit and historical source access.
        priority=[pair for pair in priority if (pair[1].acquisition or {}).get('coverage')!='discovery_only']
        assessment['discovery_leads']='excluded_until_source_text_is_acquired'
    required={}
    if deep and not identity_only and packing_version==CONTEXT_PACKING_VERSION:
        for output_id,identifiers in (required_groups or {}).items():
            allowed=set(identifiers or [])
            eligible=[source.evidence_id for _,source in priority if source.evidence_id in allowed
                and (source.acquisition or {}).get('coverage')=='full_text' and source.content.strip()]
            if eligible:required[output_id]=eligible
    mandatory=[]
    for identifiers in required.values():
        if not any(item in mandatory for item in identifiers):mandatory.append(identifiers[0])
    if mandatory:
        priority=[pair for pair in priority if pair[1].evidence_id in mandatory]+[
            pair for pair in priority if pair[1].evidence_id not in mandatory]
    retained = priority if identity_only else priority[:max(1,len(mandatory),allowance//(7000 if deep else 2200))]
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
        linked=[item for item in (meta.get('linked_entities') or []) if isinstance(item,dict)
            and isinstance(item.get('uri'),str) and len(item['uri'])<=300][:2]
        if linked:record['user_declared_entity_links']={'items':linked,'offset_unit':'retained_source_document_character',
            'identity_verified':False}
        image_match=meta.get('image_match')
        if isinstance(image_match,dict):record['image_locator']={'selection':image_match.get('selection'),
            'source_text_range':image_match.get('source_text_range'),'status':'search_signal_only_image_pixels_not_read'}
        beam_path=meta.get('beam_path')
        if isinstance(beam_path,dict):record['retrieval_path']={'depth':beam_path.get('depth'),
            'edge_kinds':[item.get('kind') for item in (beam_path.get('edges') or []) if isinstance(item,dict)],
            'status':'retrieval_signal_not_confirmed_identity_or_relationship'}
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
        ranges = _ranges(source, query, deep, focus=focus,
            located_spans=(located_spans or {}).get(source.evidence_id))
        if deep:
            # Merge overlaps once while preserving every retrieval role. A
            # single experimental paragraph often answers several fields.
            merged=[]
            for role,start,end in sorted(ranges,key=lambda row:row[1]):
                end=min(end,start+5000)
                if merged and start<=merged[-1]['end'] and max(merged[-1]['end'],end)-merged[-1]['start']<=6000:
                    merged[-1]['end']=max(merged[-1]['end'],end)
                    if role not in merged[-1]['roles']:merged[-1]['roles'].append(role)
                    merged[-1]['entries'].append((role,start,end))
                else:merged.append({'start':start,'end':end,'roles':[role],'entries':[(role,start,end)]})
            desired=list(focus or CONDITION_QUERIES)
            merged.sort(key=lambda item:('retained_field_proof' not in item['roles'],
                -sum(role in item['roles'] for role in desired),item['start']))
            covered=set()
            for item in merged:
                start,end=item['start'],item['end']
                if packing_version==CONTEXT_PACKING_VERSION:
                    excerpt=_bounded_deep_excerpt(record,item,source,meta,quota,
                        (located_spans or {}).get(source.evidence_id,[]))
                    if excerpt is None:continue
                else:
                    excerpt={'role':item['roles'][0],'roles':item['roles'],'start':start,'end':end,
                        'quote':source.content[start:end],'boundary':'retained_bounded_window_not_full_section',
                        'pages':[p['number'] for p in meta.get('pages',[]) if isinstance(p,dict)
                            and isinstance(p.get('start'),int) and isinstance(p.get('end'),int)
                            and start<p['end'] and end>p['start'] and 'number' in p]}
                candidate={**record,'excerpts':[*record['excerpts'],excerpt]}
                if len(encoded(candidate).encode('utf-8'))<=quota-600:
                    record=candidate;covered.update(excerpt['roles'])
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
    selected_intervals={}
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
        selected_intervals[row['evidence_id']]=intervals
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
    selected_ids={row['evidence_id'] for row in rows}
    manifest = {'sources': rows, 'omitted_evidence_ids': omitted,
        'total_sources': len(evidence), 'selected_sources': len(rows),
        'selection': 'per_source_method_evaluation_question_windows_with_located_proof_neighbors' if located_spans
            else 'per_source_method_evaluation_question_windows',
        'source_selection':assessment,
        'conclusion_coverage': 'not_assessed', 'offset_unit': 'task_retained_evidence_character'}
    if required:
        body_roles={'method','evaluation','limitations','question',*CONDITION_QUERIES}
        body_ids={row['evidence_id'] for row in rows if any(
            body_roles.intersection(part.get('roles',[part.get('role')])) for part in row['excerpts'])}
        manifest['required_full_text_groups']={output_id:{'eligible_evidence_ids':identifiers,
            'selected_evidence_ids':[item for item in identifiers if item in body_ids]}
            for output_id,identifiers in required.items()}
        manifest['missing_full_text_outputs']=[output_id for output_id,group in manifest['required_full_text_groups'].items()
            if not group['selected_evidence_ids']]
    if located_spans:
        manifest['located_proofs']=[{'evidence_id':key,'field':field,'start':start,'end':end,
            'selected':key in selected_ids and any(lower<=start and end<=upper
                for lower,upper in selected_intervals.get(key,[])),
            'support':'not_assessed'} for key,spans in located_spans.items() for field,start,end in spans]
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
