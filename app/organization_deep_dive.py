"""Bounded, evidence-located technical cards for representative publications."""
from __future__ import annotations

import json
import re
from app.publication_literals import source_pattern
from typing import Literal
from urllib.parse import quote

from pydantic import Field
from app.research_scope import Identifier, ScopeRecord
from app.organization_relationships import RelationProof
from app.report_mechanisms import POLICY as MECHANISM_POLICY,SUPPORTED_POLICIES as MECHANISM_POLICIES,MechanismProposal,locate_graph

VERSION='adrs-technical-cards-v1'
FIELDS={'problem':'研究问题','prior_limitations':'已有方法局限','method_overview':'方法概览','mechanism':'机制／架构',
    'innovation':'创新主张','experimental_design':'实验设计','baselines':'对照基线','conditions':'适用／复现条件',
    'results':'来源报告的结果','limitations':'结果边界与局限'}
FieldName=Literal['problem','prior_limitations','method_overview','mechanism','innovation','experimental_design','baselines','conditions','results','limitations']
LEGACY_READING_FIELD_POLICY='adrs-question-reading-fields-v1'
READING_FIELD_POLICY='adrs-question-reading-fields-v2-revisable'
READING_FIELD_POLICIES={LEGACY_READING_FIELD_POLICY,READING_FIELD_POLICY}
READING_PROFILES={
    'unknown':('mechanism','experimental_design','baselines','conditions','results'),
    'empirical':('mechanism','experimental_design','baselines','conditions','results'),
    'theoretical':('mechanism','conditions','results'),
    'synthesis':('method_overview','conditions','results'),
}


class ReadingContractProposal(ScopeRecord):
    profile:Literal['unknown','empirical','theoretical','synthesis']='unknown'
    reason:str=Field(min_length=3,max_length=500)
    basis:tuple[RelationProof,...]=Field(default=(),max_length=3)
    additional_required_fields:tuple[FieldName,...]=Field(default=(),max_length=10)
    required_fields:tuple[FieldName,...]|None=Field(default=None,min_length=1,max_length=10)


def required_reading_fields(configuration,reading_contract=None):
    """A source-located reading plan narrows acquisition, never fact verification."""
    policy=(configuration or {}).get('reading_field_policy')
    if policy not in READING_FIELD_POLICIES:
        from app.analysis_phase_contract import enabled
        return [*(['mechanism'] if enabled(configuration) else []),'experimental_design','baselines','conditions','results']
    current=reading_contract or {}
    proposal=current.get('proposal') or {}
    valid=current.get('policy')==policy and current.get('status')=='source_located_planning_judgment'
    profile=proposal.get('profile','unknown') if valid else 'unknown'
    additional=(proposal.get('additional_required_fields') or []) if valid else []
    selected=(proposal.get('required_fields') if valid and policy==READING_FIELD_POLICY else None)
    return list(dict.fromkeys([*(selected if selected is not None else READING_PROFILES.get(profile,READING_PROFILES['unknown'])),
        *((configuration or {}).get('required_reading_fields') or []),
        *additional]))


def retain_reading_contract(previous,candidate,configuration=None):
    """Reassess inferred fields with located reasons; preserve explicit requirements."""
    if ((configuration or {}).get('reading_field_policy')==READING_FIELD_POLICY
            and (candidate or {}).get('policy')==READING_FIELD_POLICY
            and candidate.get('status')=='source_located_planning_judgment'
            and candidate.get('basis') and str(candidate.get('reason') or '').strip()):
        from copy import deepcopy
        chosen=deepcopy(candidate)
        chosen['required_fields']=required_reading_fields(configuration,chosen)
        if previous and reading_contract_context(previous)!=reading_contract_context(chosen):
            chosen['adjustment']={'previous_plan':reading_contract_context(previous),
                'reason':chosen['reason'],'semantics':'revised_acquisition_plan_not_new_reading_or_fact_approval'}
        return chosen,False
    if (previous or {}).get('status')=='source_located_planning_judgment':
        conflict=False
        if (candidate or {}).get('status')=='source_located_planning_judgment':
            old_fields=set(previous['required_fields']);new_fields=set(candidate['required_fields'])
            if old_fields<=new_fields:
                if old_fields<new_fields or previous.get('profile')!=candidate.get('profile'):return candidate,False
            else:conflict=True
        return previous,conflict
    return candidate or previous,False


def reading_contract_context(value):
    """Reader/writer needs the plan, not another serialization of its source excerpts."""
    if not value:return None
    pointers=[item['evidence_id'] for item in value.get('basis',[])] or value.get('basis_evidence_ids',[])
    return {**{key:value[key] for key in ('policy','status','profile','reason','required_fields','additional_required_fields') if key in value},
        'semantics':'field_acquisition_plan_not_source_semantic_or_fact_approval',
        'basis_evidence_ids':list(dict.fromkeys(pointers))}


class TechnicalStatement(ScopeRecord):
    text:str=Field(min_length=3,max_length=2400)
    proofs:tuple[RelationProof,...]=Field(min_length=1,max_length=12)


class FigureReference(ScopeRecord):
    label:str=Field(min_length=2,max_length=120)
    proof:RelationProof
    page:int|None=Field(default=None,ge=1,le=80)


class TechnicalCardProposal(ScopeRecord):
    output_id:Identifier
    fields:dict[FieldName,TechnicalStatement]=Field(default_factory=dict,max_length=10)
    figure_references:tuple[FigureReference,...]=Field(default=(),max_length=20)
    reading_contract:ReadingContractProposal|None=None
    mechanism_graph:MechanismProposal|None=None


class TechnicalPreviewRequest(ScopeRecord):
    technical_cards:tuple[TechnicalCardProposal,...]=Field(default=(),max_length=20)


def technical_instructions(configuration):
    if 'deep_dive' not in (configuration or {}).get('modules',[]):return ''
    return '''\nRepresentative technical reading: add "technical_cards" INSIDE organization_data.
Shape: [{"output_id":"accepted proposed publication ID","fields":{"problem":{"text":"source-grounded summary","proofs":[{"evidence_id":"ev-ID","quote":"literal original excerpt"}]},"method_overview":{"text":"brief method overview","proofs":[{"evidence_id":"ev-ID","quote":"literal excerpt"}]}},"figure_references":[{"label":"literal Figure/Table/Equation label","page":null,"proof":{"evidence_id":"ev-ID","quote":"literal source caption/reference"}}]}].
Keep analysis_text to a lead of at most four sentences; put the scientific detail and its proofs in technical_cards. A hardware-only quote does not cover model sizes, ranks, workloads or SLOs: supply their additional literal passages (up to twelve necessary proofs per field), or restrict that field text to what its quotes cover. Preserve source word wrapping and hyphens in quotations. A targeted follow-up replaces a supplied field only after its own source proofs validate; omitted fields are retained.
Allowed fields: problem, prior_limitations, method_overview, mechanism, innovation, experimental_design, baselines, conditions, results, limitations. Return 1–3 representative cards, not all publications. Use a few compact fields per card and COMPLETE JSON. Every supplied field needs literal proofs, not only citation numbers. Missing fields stay unknown. Abstract/metadata-only sources can support problem and method_overview; do not invent detailed mechanisms, novelty comparisons, baselines, settings, numerical results or conditions without acquired full text. Full text may be provided as bounded windows; do not claim to have read omitted passages. Preserve reported results as source claims, never independent reproduction. Figure references locate actual labels/pages; no source image is acquired merely by citing a figure. Omit unverifiable fields and page numbers.'''


def _pattern(value):return r'\s+'.join(re.escape(token) for token in value.split())


def _full_text(source):
    meta=source.get('acquisition') or {}
    if meta.get('coverage')!='full_text' or meta.get('truncated'):return False
    if meta.get('format')=='internal_source':
        snapshot=meta.get('source_access_snapshot') or {}
        return bool(source.get('source_type')=='knowledge_base' and source.get('collected_by')=='rag'
            and meta.get('complete_retained_artifact') and meta.get('parse_version_id')
            and meta.get('source_document_id')==snapshot.get('source_id')
            and (meta.get('research_record') or {}).get('kind')=='fulltext'
            and meta.get('retained_characters')==len(source.get('content') or ''))
    if meta.get('format')=='pdf':
        return bool(meta.get('total_pages') and meta.get('retained_pages')==meta['total_pages'] and meta.get('pages'))
    return bool(meta.get('scientific_sections') and meta.get('full_text_basis'))


def build_technical_cards(configuration,findings,evidence,proposals=None):
    configuration=configuration or {}
    from app.organization_findings import _publication_url
    sources={item['evidence_id']:item for item in evidence if item.get('evidence_id') and item.get('source_url')}
    outputs={item['output_id']:item for item in (findings.get('scope_result') or {}).get('outputs',[])}
    proposals=proposals or {};cards=[];pending=[];proposed={}
    values=proposals.get('technical_cards',[])
    if not isinstance(values,list):values=[];pending.append({'reason':'technical_cards_expected_array'})
    if len(values)>20:pending.append({'reason':'technical_card_limit_20'})
    for value in values[:20]:
        try:
            if not isinstance(value,dict):raise ValueError('technical_card_expected_object')
            # Validate fields independently: a malformed optional field must
            # not erase other source-located knowledge in this work's card.
            card=TechnicalCardProposal.model_validate({**value,'fields':{},'figure_references':[],'reading_contract':None,'mechanism_graph':None})
            if configuration.get('mechanism_graph_policy') in MECHANISM_POLICIES and value.get('mechanism_graph') is not None:
                try:
                    graph=MechanismProposal.model_validate(value['mechanism_graph'])
                    if configuration.get('mechanism_graph_policy')!=MECHANISM_POLICY and graph.status=='not_needed':
                        raise ValueError('mechanism_status_not_supported_by_frozen_policy')
                    card=card.model_copy(update={'mechanism_graph':graph})
                except ValueError as error:pending.append({'output_id':card.output_id,'kind':'mechanism_graph','reason':str(error)[:400]})
            if configuration.get('reading_field_policy') in READING_FIELD_POLICIES and value.get('reading_contract') is not None:
                try:card=card.model_copy(update={'reading_contract':ReadingContractProposal.model_validate(value['reading_contract'])})
                except ValueError as error:pending.append({'output_id':card.output_id,'kind':'reading_contract','reason':str(error)[:400]})
            valid_fields={};valid_figures=[]
            raw_fields=value.get('fields') or {}
            if not isinstance(raw_fields,dict):
                pending.append({'output_id':card.output_id,'reason':'technical_fields_expected_object'})
                raw_fields={}
            for key,statement in raw_fields.items():
                try:
                    if key not in FIELDS:raise ValueError('unknown technical field')
                    valid_fields[key]=TechnicalStatement.model_validate(statement)
                except ValueError as error:
                    pending.append({'output_id':card.output_id,'field':key,'reason':str(error)[:400]})
            for figure in value.get('figure_references') or []:
                try:valid_figures.append(FigureReference.model_validate(figure))
                except ValueError as error:
                    pending.append({'output_id':card.output_id,'kind':'figure_reference','reason':str(error)[:400]})
            card=card.model_copy(update={'fields':valid_fields,'figure_references':tuple(valid_figures[:20])})
            card=card.model_copy(update={'output_id':findings.get('publication_id_aliases',{}).get(card.output_id,card.output_id)})
            if card.output_id not in outputs or card.output_id in proposed:raise ValueError('unknown or duplicate representative output')
            proposed[card.output_id]=card
        except ValueError as error:pending.append({'reason':str(error)[:400]})

    def linked_source(source,output):
        if (source.get('acquisition') or {}).get('coverage')=='discovery_only':return False
        primary={_publication_url(url) for url in output['source_urls']}
        if _publication_url(source['source_url']) in primary:return True
        for other in sources.values():
            if _publication_url(other['source_url']) in primary:
                links=(other.get('acquisition') or {}).get('document_links',[])
                if _publication_url(source['source_url']) in {_publication_url(url) for url in links}:return True
        return False

    def locate(proof,output,require_full):
        source=sources.get(proof.evidence_id)
        if not source or not linked_source(source,output):raise ValueError('proof is not retained primary work or publisher-linked document')
        if require_full and not _full_text(source):raise ValueError('full_text_required_for_this_field')
        match=re.search(source_pattern(proof.quote,configuration),source.get('content') or '',re.I)
        if not match:raise ValueError('literal quote is absent from retained source')
        pages=[page['number'] for page in (source.get('acquisition') or {}).get('pages',[])
            if match.start()<page['end'] and match.end()>page['start']]
        return {'evidence_id':proof.evidence_id,'source_url':source['source_url'],'start':match.start(),'end':match.end(),
            'quote':match.group(),'pages':pages,'source_coverage':(source.get('acquisition') or {}).get('coverage','unknown')}

    # Without a requested representative, leave the available sample as unknown cards.
    requested=list(proposed) or list(outputs)[:3]
    for output_id in requested:
        output=outputs[output_id];proposal=proposed.get(output_id);fields={};figures=[]
        available=[source for source in sources.values() if linked_source(source,output)]
        full=any(_full_text(source) for source in available)
        reading_contract=None
        if configuration.get('reading_field_policy') in READING_FIELD_POLICIES:
            reading_contract={'policy':configuration['reading_field_policy'],'status':'fallback','profile':'unknown',
                'reason':'study_profile_not_established','basis':[],
                'semantics':'field_acquisition_plan_not_source_semantic_or_fact_approval'}
            candidate=proposal.reading_contract if proposal else None
            if candidate and candidate.basis:
                try:
                    anchors=[locate(proof,output,False) for proof in candidate.basis]
                    reading_contract.update(status='source_located_planning_judgment',profile=candidate.profile,
                        reason=candidate.reason,basis=anchors,proposal=candidate.model_dump(mode='json',
                            exclude={'required_fields'} if configuration['reading_field_policy']==LEGACY_READING_FIELD_POLICY else set()))
                except ValueError as error:pending.append({'output_id':output_id,'kind':'reading_contract','reason':str(error)})
            reading_contract['required_fields']=required_reading_fields(configuration,reading_contract)
        for key,label in FIELDS.items():
            statement=proposal.fields.get(key) if proposal else None
            record={'label':label,'text':None,'status':'unknown','proofs':[],'reason':'not_extracted_from_available_source'}
            if reading_contract is not None:record['required_for_reading']=key in reading_contract['required_fields']
            if statement:
                try:
                    anchors=[locate(proof,output,key not in {'problem','method_overview'}) for proof in statement.proofs]
                    source_text=' '.join(anchor['quote'] for anchor in anchors)
                    # Lexical numbers cannot establish entailment: 12,288 vs
                    # 12288, eight vs 8 and version identifiers caused real
                    # field loss. Keep exact source proofs for the mandatory
                    # semantic claim audit, and retain mismatches as diagnostics.
                    unmatched=[value for value in re.findall(r'(?<!\w)\d+(?:\.\d+)?%?',statement.text)
                        if not re.search(r'(?<![\d.])'+re.escape(value)+r'(?![\d.])',source_text)]
                    if unmatched:record['numeric_review_required']=unmatched
                    record.update(text=statement.text,status='source_summary_requires_semantic_review',proofs=anchors,reason=None)
                except ValueError as error:record['reason']=str(error)
            elif key not in {'problem','method_overview'} and not full:record['reason']='full_text_unavailable_not_inferred_from_abstract'
            fields[key]=record
        for item in proposal.figure_references if proposal else ():
            try:
                anchor=locate(item.proof,output,True)
                if not re.search(source_pattern(item.label,configuration),anchor['quote'],re.I):raise ValueError('figure_label_absent_from_source_quote')
                page=item.page
                if page is not None and page not in anchor['pages']:
                    if configuration.get('mechanism_graph_policy') not in MECHANISM_POLICIES:raise ValueError('figure_page_not_supported_by_pdf_offsets')
                    page=anchor['pages'][0] if len(anchor['pages'])==1 else None
                    pending.append({'output_id':output_id,'kind':'figure_reference_page_normalized','reason':'actual_source_page_used'})
                figures.append({'label':item.label,'proof':anchor,'page':page,'asset_status':'source_reference_only_not_image_acquired',
                    'source_url':anchor['source_url']+(f'#page={page}' if page else ''),'origin':'original_source_reference_not_system_generated_chart'})
            except ValueError as error:pending.append({'output_id':output_id,'kind':'figure_reference','reason':str(error)})
        graph=None
        if configuration.get('mechanism_graph_policy') in MECHANISM_POLICIES:
            graph={'policy':configuration['mechanism_graph_policy'],'status':'insufficient_evidence','reason':'structured_mechanism_not_acquired'}
            if proposal and proposal.mechanism_graph:
                try:graph=locate_graph(proposal.mechanism_graph,output,locate,policy=configuration['mechanism_graph_policy'])
                except ValueError as error:graph['reason']=str(error)
            if graph.get('status')=='source_figure_requested':
                from app.report_mechanisms import figure_label_key
                original=next((item for item in figures if figure_label_key(item['label'])==figure_label_key(graph['figure_label'])),None)
                if original:graph['original_reference']=original
                else:graph.update(status='insufficient_evidence',reason='mechanism_original_caption_reference_missing')
        cards.append({'output_id':output_id,'title':output['title'],'source_urls':output['source_urls'],
            **({'mechanism_graph':graph} if graph is not None else {}),
            **({'reading_contract':reading_contract} if reading_contract is not None else {}),
            'reading_depth':'full_text_source_with_bounded_context' if full else 'abstract_metadata_only',
            'full_text_available':full,'model_read_entire_document':False,'fields':fields,'figure_references':figures,
            'unknown_fields':[key for key,value in fields.items() if value['status']=='unknown'],
            'interpretation':'字段是有字面定位的来源摘要，未独立复现或完成语义审核；完整来源可用不等于模型看过全部正文。'})
    return {'schema_version':VERSION,'cards':cards,'pending_records':pending,'selected_output_ids':requested,
        'selection_basis':'analyst_proposed_representatives' if proposed else 'bounded_sample_fallback_not_quality_rank',
        'coverage':'representative_accepted_publications_only','effects':{'network_requests':0,'model_calls':0},
        'gaps':['原文图号／页码定位不代表已取得图片、表格结构或公式图像；未取得的资产明确留空。']}


def reconcile_retained_technical(configuration,findings,evidence,workflow):
    """Rebuild the consumed projection from saved reading, without model calls.

    Follow-up fields supersede earlier candidates only after their own primary
    source quotations validate. Replaced candidates remain in field history.
    """
    configuration=configuration or {}
    from copy import deepcopy
    previous=findings.get('technical_reading') or {}
    cards={row['output_id']:deepcopy(row) for row in previous.get('cards',[])}
    pending=[];phases=[];reading_contracts={}
    completed=(workflow or {}).get('completed') or {}
    # Targeted condition reading has precedence even if checkpoint JSON key
    # order was changed by a database serializer.
    keys=sorted(key for key in completed if key.startswith('question:deep_dive:'))
    for phase in keys:
        proposals=(completed[phase] or {}).get('organization_data') or {}
        if not proposals.get('technical_cards'):continue
        view=build_technical_cards(configuration,findings,evidence,proposals)
        phases.append(phase)
        pending.extend({'phase':phase,**row} for row in view['pending_records'])
        for candidate in view['cards']:
            target=cards.setdefault(candidate['output_id'],deepcopy(candidate))
            if configuration.get('reading_field_policy') in READING_FIELD_POLICIES:
                retained,conflict=retain_reading_contract(reading_contracts.get(candidate['output_id']),candidate.get('reading_contract'),configuration)
                if retained:
                    reading_contracts[candidate['output_id']]=retained
                    target['reading_contract']=deepcopy(retained)
                if conflict:pending.append({'output_id':candidate['output_id'],'phase':phase,'kind':'reading_contract',
                    'reason':'retained_source_located_reading_contract_not_silently_replaced'})
            for name,field in candidate['fields'].items():
                if not field.get('text') or not field.get('proofs'):continue
                old=target['fields'].get(name) or {}
                if old.get('text') and old.get('text')!=field['text']:
                    history=target.setdefault('field_history',{}).setdefault(name,[])
                    if not any(row.get('text')==old['text'] for row in history):history.append(deepcopy(old))
                target['fields'][name]={**field,'retained_phase':phase}
            for figure in candidate['figure_references']:
                if figure not in target['figure_references']:target['figure_references'].append(figure)
            graph=candidate.get('mechanism_graph') or {}
            if (configuration.get('mechanism_graph_policy')==MECHANISM_POLICY and graph.get('requirement_decision')
                    or graph.get('status') in {'source_located_requires_semantic_review','source_figure_requested'}):
                target['mechanism_graph']=deepcopy(graph)
            elif 'mechanism_graph' not in target and graph:target['mechanism_graph']=deepcopy(graph)
            target['unknown_fields']=[name for name,field in target['fields'].items() if field['status']=='unknown']
    if not phases:return previous
    for card in cards.values():
        reading_contract=card.get('reading_contract')
        if configuration.get('reading_field_policy') in READING_FIELD_POLICIES and reading_contract:
            for name,field in card['fields'].items():field['required_for_reading']=name in reading_contract['required_fields']
    return {**previous,'schema_version':VERSION,'cards':list(cards.values()),
        'pending_records':pending,'selected_output_ids':list(cards),'gaps':previous.get('gaps',[]),
        'reconciliation':{'policy':'adrs-retained-technical-fields-v2','phases':phases,
            'semantics':'source_located_candidates_require_final_semantic_audit'},
        'effects':{'network_requests':0,'model_calls':0}}


def technical_context(view):
    if not view:return None
    return {'schema_version':view['schema_version'],'cards':[{**{key:value for key,value in row.items() if key!='mechanism_graph'},
        **({'reading_contract':reading_contract_context(row['reading_contract'])} if row.get('reading_contract') else {})}
        for row in view['cards'][:20]],
        'retained_card_count':len(view['cards']),'pending_records':view['pending_records'][:10],'gaps':view['gaps'],
        **({'reading_selection':view['reading_selection']} if view.get('reading_selection') else {})}


def task_reading_progress(workflow,*,configuration=None,evidence=(),tool_histories=()):
    """Read the existing Analyst checkpoint; this is not another corpus ledger."""
    from collections import Counter
    progress=(workflow or {}).get('corpus_progress')
    current=bool((workflow or {}).get('binding') and progress and progress.get('version')=='adrs-task-corpus-progress-v1'
        and progress.get('analysis_binding')==(workflow or {}).get('binding'))
    from app.rag_corpus import declared_member_progress
    declared=declared_member_progress(configuration,evidence,
        scope_links=progress.get('declared_scope') if current else None,
        reading_items=progress.get('items') if current else None,tool_histories=tool_histories)
    declaration={'declared_membership':declared} if declared is not None else {}
    if not progress or progress.get('version')!='adrs-task-corpus-progress-v1':
        return {'status':'not_recorded','items':[],'semantics':'legacy_or_unstarted_not_zero_completed_papers',**declaration}
    if not current:
        return {'status':'stale_analysis_binding','items':[],**declaration,
            'semantics':'retained_progress_not_valid_for_current_analysis'}
    from app.rag_corpus import current_reading_items
    items=list(current_reading_items(progress.get('items'),evidence).values())
    return {**{key:value for key,value in progress.items() if key not in {'items','declared_scope'}},**declaration,
        'status':'recorded','items':items,'member_count':len(items),
        'reading_status_counts':dict(Counter(item['reading_status'] for item in items)),
        'works_with_field_gaps':sum(bool(item.get('missing_fields')) for item in items),
        'pending_supplementation_works':sum((item.get('supplementation') or {}).get('status')=='pending' for item in items),
        'unresolved_supplementation_works':sum((item.get('supplementation') or {}).get('status')=='completed_with_gaps' for item in items),
        'effects':{'model_calls':0,'network_requests':0,'index_writes':0}}


def technical_evidence_windows(source,limit):
    """Select source windows, keeping offsets instead of manufacturing a summary."""
    text=source.content;meta=source.acquisition or {};ranges=[(0,min(len(text),2000))]
    for section in meta.get('scientific_sections',[]):
        if re.search(r'method|experiment|evaluation|result|discussion|conclusion|limitation|方法|结果|讨论|结论',section['label'],re.I):
            ranges.append((section['start'],min(section['end'],section['start']+3500)))
    if meta.get('format')=='pdf':
        for hit in re.finditer(r'(?im)^.{0,30}(?:method|design|architecture|evaluation|experiment|baseline|result|limitation|conclusion).{0,70}$',text):
            ranges.append((max(0,hit.start()-200),min(len(text),hit.start()+3000)))
            if len(ranges)>=10:break
    if len(ranges)==1:ranges.append((ranges[0][1],min(len(text),limit)))
    merged=[]
    for lower,upper in sorted(ranges):
        if merged and lower<=merged[-1][1]:merged[-1]=(merged[-1][0],max(upper,merged[-1][1]))
        else:merged.append((lower,upper))
    lines=[];remaining=limit
    for lower,upper in merged:
        if remaining<=0:break
        upper=min(upper,lower+remaining);piece=text[lower:upper];remaining-=len(piece)
        lines.append(f'[retained source characters {lower}:{upper}]\n'+piece)
    return '\n'.join(lines),limit-remaining


def technical_markdown(view):
    if not view:return ''
    def safe(text):return str(text).replace('<','&lt;').replace('>','&gt;').replace('|','\\|').replace('\n',' ')
    lines=['\n\n## 代表成果深读与来源定位', '规则：'+VERSION]
    for card in view['cards']:
        lines+=['\n### '+safe(card['title']),card['interpretation'],f"阅读深度：{card['reading_depth']}；未知项：{len(card['unknown_fields'])}。"]
        for field in card['fields'].values():
            lines.append('\n**'+field['label']+'**：'+(safe(field['text']) if field['text'] else '未知（'+safe(field['reason'])+'）'))
            for anchor in field['proofs']:
                lines.append(f"- 原文 {safe(anchor['evidence_id'])} 字符 {anchor['start']}–{anchor['end']}，页 {','.join(map(str,anchor['pages'])) or '无PDF页码'}：<{quote(anchor['source_url'],safe=':/?#=&%+@~!$*,;()-_.')}>。")
        for figure in card['figure_references']:lines.append('- 原文定位：'+safe(figure['label'])+'；'+figure['asset_status']+'。')
    lines+=view['gaps']
    return '\n'.join(lines)
