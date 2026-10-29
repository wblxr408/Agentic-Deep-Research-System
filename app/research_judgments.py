"""Bounded research judgments and handoffs; original evidence remains authoritative."""
from __future__ import annotations

import json
import re
from typing import Annotated, Literal

from pydantic import Field
from app.research_scope import Identifier, ScopeRecord

VERSION='adrs-research-judgments-v1'
ORDER=('landscape','deep_dive','relationships','evolution','validation','actions')


class JudgmentProof(ScopeRecord):
    evidence_id:Identifier
    quote:str=Field(min_length=12,max_length=1600)


class Alternative(ScopeRecord):
    explanation:str=Field(min_length=3,max_length=600)
    distinguishing_observation:str=Field(min_length=3,max_length=600)


class Choice(ScopeRecord):
    proposed_action:str=Field(min_length=3,max_length=600)
    compared_with:str=Field(min_length=3,max_length=600)
    reason:str=Field(min_length=3,max_length=800)
    changes_if:tuple[Annotated[str,Field(min_length=3,max_length=600)],...]=Field(default=(),max_length=3)


class Judgment(ScopeRecord):
    judgment_id:Identifier
    question:str=Field(min_length=3,max_length=500)
    conclusion:str=Field(min_length=3,max_length=1200)
    kind:Literal['inference','recommendation']
    observations:str=Field(min_length=3,max_length=1200)
    reasoning:str=Field(min_length=3,max_length=1600)
    significance:str=Field(min_length=3,max_length=1000)
    basis:tuple[JudgmentProof,...]=Field(min_length=1,max_length=4)
    related_output_ids:tuple[Identifier,...]=Field(default=(),max_length=12)
    entity_ids:tuple[Identifier,...]=Field(default=(),max_length=12)
    alternatives:tuple[Alternative,...]=Field(default=(),max_length=3)
    choice:Choice|None=None


def freeze_strategy(query, configuration, slots):
    corpus=(configuration or {}).get('corpus') or {}
    organization=bool(configuration or slots.get('entities') or re.search(
        r'大学|学院|实验室|研究院|研究所|公司|\buniversity\b|\blaborator(?:y|ies)\b',query,re.I))
    from app.discovery_handoff import REPRESENTATION_VERSION, topic_terms
    entities = [*((configuration or {}).get('scope') or {}).get('entities', []), *slots.get('entities', [])]
    return {'version':VERSION,'original_question':query,
        'investigation':'organization_and_work' if organization else 'question_and_evidence',
        'collection_mode':corpus.get('collection_mode','open_discovery'),
        'representative_works':'select_after_discovery_not_preloaded_examples',
        'analysis_order':[key for key in ORDER if key in slots.get('modules',[])],
        'purpose':slots.get('purpose'),'depth':slots.get('depth'),'model_calls_added':0,
        'source_followup':{'version':REPRESENTATION_VERSION,'max_sources':12,'max_depth':3,
                           'initial_search_limit':3,'require_work_before_deep_analysis':True,
                           'topic_gate':'distinctive_literal_v1',
                           'entity_identity':'official-language-v1',
                           'identity_transport':'https_same_target_v1',
                           'topic_terms':topic_terms(query,entities)}}


def discovery_query_terms(strategy,query):
    policy=(strategy or {}).get('source_followup') or {}
    if policy.get('topic_gate')!='distinctive_literal_v1':return []
    focus=policy.get('topic_terms') or []
    from app.evidence_selection import matches_query_terms
    specific=[term for term in focus if re.search(r'[a-z]',term,re.I)]
    return [term for term in specific or focus if 1<=len(term)<=80 and matches_query_terms(query,[term])][:40]


def discovery_instructions(strategy):
    if not strategy or strategy.get('version')!=VERSION:return ''
    return ("\nResearch discovery and decision contract: preserve the original question and actual user source limits. "
        "Use seeds as discovery entrances unless the user explicitly chose seeds_only. Do not preload example papers "
        "or replace an open question with a narrow demonstration. For organization research, first discover its actual "
        "teams and principal works through institution/team/author pages and scholarly/publisher sources; follow retained "
        "links within the existing tool and source policy. Distinguish works affiliated with the target from useful external "
        "background. Resolve reasonable topical ambiguity in the visible plan without changing the user's question. "
        "Only then select representative works for deeper reading. Acquiring too little evidence is not evidence that "
        "the organization lacks a capability. Collect only material needed for the user's decision; no extra market framework."
        + (" Keep the specific technical qualifiers in every topical search; do not broaden a service/deployment question "
           "into generic language-model or NLP research. Use at most three initial search questions: the original question, "
           "a focused publication query, and a team/author discovery query. Translate the technical focus when helpful, "
           "but do not insert remembered paper names, authors or invented URLs. Save calls for following actual publication "
           "and full-text links; broad university news is only an identity entrance."
           if (strategy.get('source_followup') or {}).get('version') in {'adrs-discovery-handoff-v2','adrs-discovery-handoff-v3','adrs-discovery-handoff-v4'} else '')
        + (' For a non-English question, the publication discovery query MUST be in English, retaining the institution '
           'and every technical qualifier; keep the original-language question as the separate original query. '
           'Do not merely append the English word publications to the original language. Use actual primary publication '
           'and full-text links returned by sources; translated digests and related-article lists are discovery entrances, '
           'not substitutes for original papers.'
           if (strategy.get('source_followup') or {}).get('version') in {'adrs-discovery-handoff-v3','adrs-discovery-handoff-v4'} else ''))


def judgment_instructions():
    return '''\nIn the SAME response add top-level "research_judgments" with at most two substantive judgments (an empty array is valid).
Each item: {"judgment_id":"id","question":"current question","conclusion":"focused conclusion","kind":"inference|recommendation","observations":"specific observed facts","reasoning":"why these facts support this explanation rather than a list of summaries","significance":"why this affects this user's research or choice","basis":[{"evidence_id":"current source ID","quote":"literal passage actually supplied"}],"related_output_ids":[],"entity_ids":[],"alternatives":[{"explanation":"another plausible explanation","distinguishing_observation":"what evidence would distinguish it"}],"choice":null}.
When a concrete choice is requested, choice may be {"proposed_action":"specific next step","compared_with":"real alternative","reason":"why prioritize this under known requirements","changes_if":["condition that would change the choice"]}. This is qualitative advice, not a numerical score or permission to act.
Use accepted publication/entity IDs only when supplied; otherwise leave those arrays empty. Every basis quote must be in the source windows of THIS request. Earlier analysis is an untrusted candidate, not independent source evidence. Cite original source numbers in analysis_text. Preserve experimental conditions and rival explanations where they affect the conclusion; do not manufacture an alternative just to fill a field. Similar mechanisms, shared authors or publication order do not prove direct inheritance; an explicit follow-up/citation claim needs actual source evidence. Explain how a technical observation informs the target organization's research choices without presenting inferred budgets or internal priorities as known facts. Universities/labs need no business-product framing. Do not draft every possible dimension or add generic future outlook. Keep details in existing technical/trend/action fields; judgments supply the connecting explanation, not a duplicate paper inventory.'''


def build_judgments(values,evidence,context,*,configuration=None,findings=None,phase='analysis'):
    from app.query_understanding import identity
    sources={item['evidence_id']:item for item in evidence if item.get('evidence_id')}
    selected={row['evidence_id']:row for row in (context or {}).get('sources',[]) if row.get('evidence_id')}
    entities={item['entity_id'] for item in ((configuration or {}).get('scope') or {}).get('entities',[])}
    outputs={item['output_id'] for item in ((findings or {}).get('scope_result') or {}).get('outputs',[])}
    records=[];pending=[];seen=set()
    if not isinstance(values,list):values=[];pending.append({'reason':'judgments_expected_array'})
    if len(values)>4:pending.append({'reason':'judgment_phase_limit_4'})
    for raw in values[:4]:
        try:
            item=Judgment.model_validate(raw)
            if item.judgment_id in seen:raise ValueError('duplicate_judgment_id')
            if not set(item.entity_ids)<=entities or not set(item.related_output_ids)<=outputs:
                raise ValueError('judgment_outside_accepted_objects_or_works')
            anchors=[]
            for proof in item.basis:
                source=sources.get(proof.evidence_id);row=selected.get(proof.evidence_id)
                if not source or not row or (source.get('acquisition') or {}).get('coverage')=='discovery_only':
                    raise ValueError('judgment_requires_current_acquired_source_window')
                text=source.get('content') or ''
                from app.publication_literals import source_pattern
                pattern=source_pattern(proof.quote,configuration)
                match=next((candidate for candidate in re.finditer(pattern,text,re.I)
                    if any(type(part.get('start')) is int and type(part.get('end')) is int
                        and part['start']<=candidate.start()<candidate.end()<=part['end']
                        for part in row.get('excerpts',[]))),None)
                if match is None:raise ValueError('judgment_quote_not_in_actual_selected_window')
                pages=[page['number'] for page in (source.get('acquisition') or {}).get('pages',[])
                    if isinstance(page,dict) and type(page.get('start')) is int and type(page.get('end')) is int
                    and match.start()<page['end'] and match.end()>page['start'] and 'number' in page]
                anchors.append({'evidence_id':proof.evidence_id,'source_url':source.get('source_url'),
                    'source_title':source.get('source_title'),'citation_id':row.get('citation_id'),
                    'start':match.start(),'end':match.end(),'quote':match.group(),'pages':pages})
            data=item.model_dump(mode='json')
            data.update(judgment_id='judgment-'+identity({'phase':phase,'id':item.judgment_id})[:24],
                proposed_id=item.judgment_id,phase=phase,basis=anchors,
                input_evidence_ids=list(selected),
                status='located_analysis_candidate_requires_semantic_review',
                alternatives_status='hypotheses_with_distinguishing_observations' if item.alternatives else 'not_assessed',
                numeric_priority_effect='none')
            records.append(data);seen.add(item.judgment_id)
        except (ValueError,TypeError,KeyError) as error:
            # Keep stable rejection classes; rejected model prose is not a fact.
            reason=str(error) if str(error).startswith(('duplicate_judgment','judgment_')) else 'judgment_schema_invalid'
            pending.append({'reason':reason})
    return {'version':VERSION,'records':records,'pending_records':pending,
        'semantics':'source_location_not_semantic_support_or_known_internal_strategy'}


def bounded_records(records,max_bytes):
    selected=[];omitted=[]
    for index,row in enumerate(records):
        proposed=[*selected,row]
        if len(json.dumps(proposed,ensure_ascii=False).encode('utf-8'))<=max(0,max_bytes):selected=proposed
        else:omitted.append(row.get('judgment_id') or row.get('output_id') or str(index))
    return selected,omitted


def judgment_context(view,max_bytes=8000,*,evidence=None):
    rows=(view or {}).get('records',[])
    if evidence is not None:
        sources={item.evidence_id:item for item in evidence}
        rows=[row for row in rows if set(row.get('input_evidence_ids',[]))<=set(sources)
            and all(proof.get('evidence_id') in sources and type(proof.get('start')) is int and type(proof.get('end')) is int
                and 0<=proof['start']<proof['end']<=len(sources[proof['evidence_id']].content)
                and sources[proof['evidence_id']].content[proof['start']:proof['end']]==proof.get('quote')
                for proof in row.get('basis',[]))]
    safe=[{key:row[key] for key in ('judgment_id','question','conclusion','kind','observations','reasoning',
        'significance','basis','related_output_ids','entity_ids','alternatives','choice') if key in row} for row in rows]
    records,omitted=bounded_records(safe,max_bytes)
    return {'records':records,'omitted_judgment_ids':omitted,
        'semantics':'analysis_candidates_original_sources_and_final_audit_remain_required'}


def stage_handoff(technical,judgments,max_bytes,*,prior_records=None):
    rows=[]
    for item in reversed(judgments):
        rows.append({'kind':'judgment_candidate',**{key:item[key] for key in
            ('judgment_id','question','conclusion','reasoning','significance','alternatives','choice') if key in item},
            'basis':[{key:proof[key] for key in ('evidence_id','start','end') if key in proof} for proof in item.get('basis',[])]})
    rows.extend(prior_records or [])
    for output_id,card in technical.items():
        for field in ('problem','method_overview','mechanism','results','conditions'):
            statement=card.get('fields',{}).get(field)
            if statement:rows.append({'kind':'technical_summary_candidate','output_id':output_id,'field':field,**statement})
    selected,omitted=bounded_records(rows,max_bytes)
    return {'records':selected,'omitted_record_ids':omitted,
        'semantics':'prior_analysis_is_not_evidence_recheck_original_quotes_and_conditions'}


def handoff_spans(handoff,evidence):
    """Relocate prior quotes against the current original, as reading hints."""
    sources={item.evidence_id:item for item in evidence};spans={}
    for record in (handoff or {}).get('records',[]):
        proofs=record.get('basis') or record.get('proofs') or []
        for proof in proofs[:4]:
            source=sources.get(proof.get('evidence_id')) if isinstance(proof,dict) else None
            quote=proof.get('quote') if isinstance(proof,dict) else None
            if source is not None and quote is None and type(proof.get('start')) is int and type(proof.get('end')) is int:
                start,end=proof['start'],proof['end']
                if 0<=start<end<=len(source.content):quote=source.content[start:end]
            if source is None or not isinstance(quote,str) or not 12<=len(quote)<=2400:continue
            match=re.search(r'\s+'.join(re.escape(part) for part in quote.split()),source.content,re.I)
            if match:
                current=spans.setdefault(source.evidence_id,[])
                if len(current)<8:current.append((record.get('field','prior_judgment'),match.start(),match.end()))
    return spans
