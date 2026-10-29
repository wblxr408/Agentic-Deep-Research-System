"""Source-aware extractive context selection, without a new model or authority."""
from __future__ import annotations

import re
from urllib.parse import urlsplit

VERSION='adrs-evidence-selection-v1'


def _terms(text):
    words=re.findall(r'[a-z][a-z0-9_+.-]{1,}|[\u3400-\u9fff]{2,}',str(text or '')[:3000].casefold())
    result=[]
    for word in words:
        if re.fullmatch(r'[\u3400-\u9fff]+',word):result.extend(word[index:index+2] for index in range(len(word)-1))
        elif word not in {'the','and','with','for','this','that','from','what','how','research'}:result.append(word)
    return list(dict.fromkeys(result))[:160]


def matches_query_terms(text,terms):
    """Literal topic cue, including simple plurals; never evidence support."""
    text=str(text or '')[:160000].casefold()
    for term in terms:
        term=str(term).strip().casefold()
        if not term:continue
        if term.isascii() and re.search('[a-z]',term):
            if re.search(r'(?<![a-z0-9_])'+re.escape(term)+r's?(?![a-z0-9_])',text):return True
        elif term in text:return True
    return False


def source_priority(evidence,query,*,preferred_ids=None,identity_only=False,deep=False):
    """Keep original citation numbers while ranking candidate source utility.

    Lexical matching is a selection signal; content support is not assessed here.
    """
    terms=_terms(query);preferred=set(preferred_ids or [])
    scored=[];manifest=[]
    for number,source in enumerate(evidence,1):
        meta=source.acquisition or {}
        title=(source.source_title or '').casefold();text=source.content.casefold()
        hits=[term for term in terms if term in text or term in title]
        title_hits=[term for term in hits if term in title]
        coverage=meta.get('coverage','unspecified')
        body=coverage not in {'discovery_only','metadata','metadata_only','coverage_unknown','unspecified'}
        full=coverage=='full_text'
        lexical=(len(hits)+len(title_hits))/max(1,len(terms)*2)
        score=lexical+(0.3 if full and deep else .15 if full else .08 if body else 0)
        # Pin only explicit current work/publication references, not model scores.
        pinned=source.evidence_id in preferred
        try:group=urlsplit(source.source_url or '').netloc.lower() or meta.get('source_document_id') or source.evidence_id
        except ValueError:group=source.evidence_id
        item={'evidence_id':source.evidence_id,'citation_id':number,'lexical_relevance':round(lexical,6),
            'selection_utility':round(score,6),'matched_terms':hits[:24],'preferred_current_work':pinned,
            'coverage':coverage,'truncated':bool(meta.get('truncated')),'source_group':str(group),
            'support':'not_assessed','reliability':'source_origin_and_coverage_only_not_authenticity_verification'}
        scored.append((number,source,item));manifest.append(item)
    scored.sort(key=lambda row:(not row[2]['preferred_current_work'],-row[2]['selection_utility'],row[0]))
    if identity_only:
        # Identity extraction must not pull unrelated works into the batch.
        scored=[row for row in scored if row[2]['preferred_current_work']]
    # Source-group balancing only breaks close scores, preserving pinned works.
    ordered=[];counts={}
    while scored:
        best=min(scored,key=lambda row:(not row[2]['preferred_current_work'],
            -(row[2]['selection_utility']-.08*counts.get(row[2]['source_group'],0)),row[0]))
        scored.remove(best);ordered.append((best[0],best[1]))
        group=best[2]['source_group'];counts[group]=counts.get(group,0)+1
    return ordered,{'version':VERSION,'question':query[:1500],
        'method':'bounded_literal_query_match_coverage_and_source_group_balance',
        'candidates':manifest,'support':'not_assessed','extra_model_calls':0}


def context_coverage(manifest,assessment,*,deep=False,focus=None):
    sources=manifest['sources'];selected={row['evidence_id'] for row in sources}
    excerpt_count=sum(len(row['excerpts']) for row in sources)
    candidates=assessment['candidates']
    question={'question':assessment['question'],'selected_evidence_ids':list(dict.fromkeys(row['evidence_id'] for row in sources)),
        'selected_excerpt_count':excerpt_count,'candidate_count':len(candidates),
        'relevance_basis':'literal_matching_and_document_coverage_not_semantic_support',
        'support_status':'requires_downstream_claim_verdicts','gaps':[]}
    if not sources:question['gaps'].append('no_source_excerpt_fits_current_context_allowance')
    if sources and not any(row['evidence_id'] in selected and row['matched_terms'] for row in candidates):
        question['gaps'].append('no_literal_query_match_in_selected_sources')
    if deep and sources and not any(row.get('source_coverage')=='full_text' for row in sources):
        question['gaps'].append('selected_context_has_no_declared_full_text_source')
    requested=list(focus or ('experimental_design','baselines','conditions','results')) if deep else []
    question['reading_facets']={role:[row['evidence_id'] for row in sources
        if row.get('reading_facets',{}).get(role)=='selected_window'] for role in requested}
    for role,ids in question['reading_facets'].items():
        if not ids:question['gaps'].append('no_selected_window_for:'+role)
    question['omitted_evidence_ids']=list(dict.fromkeys(manifest['omitted_evidence_ids']))
    question['next_action']='reuse_retained_text_or_bounded_replan_with_original_budget' if question['gaps'] else 'continue_semantic_analysis_and_audit'
    return question


def excerpt_anchor(source,excerpt):
    """Task-retained character span, not a forged original-PDF byte offset."""
    start,end=excerpt['start'],excerpt['end']
    return {'evidence_id':source.evidence_id,'start':start,'end':end,
        'offset_unit':'task_retained_evidence_character','paragraph_start':source.content[:start].count('\n\n')+1,
        'paragraph_end':source.content[:end].count('\n\n')+1,'pages':excerpt.get('pages',[]),
        'content_scope':'literal_retained_text_not_full_document_read_or_entailment'}
