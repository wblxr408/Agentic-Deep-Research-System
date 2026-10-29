"""Small current-phase output and reading contracts, without new agents."""
from __future__ import annotations

import json
import re
from copy import deepcopy

VERSION='adrs-analysis-phase-output-v1'

SHAPES={
    'landscape':{'interpretations':[{'entity_ids':['SELECTED ID'],'statement':'focused source-grounded interpretation',
        'kind':'inference','basis':[{'passage_id':'CURRENT ID'}]}]},
    'deep_dive':{'technical_cards':[{'output_id':'ASSIGNED ID','fields':{
        'problem':{'text':'the research problem','proofs':[{'passage_id':'CURRENT ID'}]},
        'method_overview':{'text':'how the method addresses it','proofs':[{'passage_id':'CURRENT ID'}]},
        'mechanism':{'text':'actual mechanism, when its source passage is supplied','proofs':[{'passage_id':'CURRENT ID'}]}},
        'figure_references':[]}]},
    'relationships':{'relationship_entities':[],'research_relationships':[],'geographies':[]},
    'evolution':{'trend_observations':[{'trend_id':'id','entity_ids':['SELECTED ID'],'kind':'inference',
        'claim_domain':'research_topic','statement':'bounded interpretation of the actual works',
        'supporting':[{'passage_id':'CURRENT ID'}],'opposing':[],
        'alternative_explanations':['a relevant rival explanation, if needed'],
        'conditions':[],'horizon_start':None,'horizon_end':None}]},
    'actions':{'action_cards':[{'action_id':'id','entity_id':'SELECTED ID','mode':'research_validation',
        'question':'specific next research question','basis':[{'passage_id':'CURRENT ID'}],
        'complementary_hypothesis':None,'steps':['one proposed next step'],'public_contacts':[]}]},
}
SHAPES['validation']=SHAPES['evolution']


def enabled(configuration):
    return (configuration or {}).get('analysis_phase_policy')==VERSION


def contract(configuration, phase):
    if not enabled(configuration):return None
    if phase=='extraction':
        return {'version':VERSION,'phase':'extraction','required_arrays':['outputs'],
            'allowed_fields':['identity_aliases','candidate_entities','outputs','research_families',
                'relationships','output_relations','interpretations'],'judgments':False}
    modules=(configuration or {}).get('modules') or []
    if phase!='question' or len(modules)!=1 or modules[0] not in SHAPES:return None
    module=modules[0]
    return {'version':VERSION,'phase':module,'required_arrays':list(SHAPES[module]),
        'allowed_fields':list(SHAPES[module]),'judgments':module in {'landscape','evolution','validation','actions'}}


def instructions(configuration, phase, seed=None):
    policy=contract(configuration,phase)
    if not policy:return ''
    if phase=='extraction':
        return ('\nCurrent phase output contract overrides general Skill deliverables: extract the primary '
            'publication identity only, using the already specified organization_data schema. '
            'organization_data.outputs MUST be an array (empty if unsupported). Do not write a company '
            'profile, technical review or final report in this identity response.')
    organization=deepcopy(SHAPES[policy['phase']])
    if policy['phase']=='actions' and configuration.get('purpose')=='cooperation_discovery':
        organization['action_cards'][0]['mode']='cooperation'
    if policy['phase']=='deep_dive' and (seed or {}).get('reading_focus'):
        from app.organization_deep_dive import FIELDS
        organization['technical_cards'][0]['fields']={field:{'text':'the source-supported requested field',
            'proofs':[{'passage_id':'CURRENT ID'}]} for field in seed['reading_focus'] if field in FIELDS}
    shape={'analysis_text':'one concise lead, at most four sentences','organization_data':organization}
    if policy['judgments']:shape['research_judgments']=[]
    return ('\nCURRENT PHASE OUTPUT CONTRACT (overrides generic Skill report templates):\n'+
        json.dumps(shape,ensure_ascii=False,separators=(',',':'))+
        '\nThe example describes field names, not facts. Use the actual selected IDs and only supported '
        'records. Required organization_data arrays must be present; use [] when no record is supported. '
        'Do not add organization_profile, literature_review, another module, a separate report or extra '
        'root keys. Skills supply research methods, not an alternative output schema. '
        'Prefer one to three substantive records and, when applicable, one focused connecting judgment; '
        'do not repeat the paper inventory, prior chapters or the same conditions in every field. '
        'A passage reference is exactly {"passage_id":"CURRENT ID"}, without quote or evidence_id. '
        'Choose multiple IDs in the existing proof arrays when a field needs several passages. '
        'Keep all numerical conditions necessary for the statement; references alone do not prove support. '
        'For deep reading return a card for each assigned output ID; a targeted follow-up supplies only '
        'its requested missing fields. This phase supplies structured research material; the later writer owns the report.')


def bound_response(value, configuration, phase):
    """Retain declared phase fields and record unused model output."""
    policy=contract(configuration,phase)
    if not policy:return value,None
    organization=value.get('organization_data')
    if not isinstance(organization,dict):raise ValueError('phase_organization_data_missing')
    missing=[key for key in policy['required_arrays'] if not isinstance(organization.get(key),list)]
    if missing:raise ValueError('phase_required_arrays_missing:'+','.join(missing))
    if policy['judgments'] and 'research_judgments' in value and not isinstance(value['research_judgments'],list):
        raise ValueError('phase_research_judgments_expected_array')
    roots=['analysis_text','organization_data']+(['research_judgments'] if policy['judgments'] else [])
    retained={key:item for key,item in value.items() if key in roots}
    retained['organization_data']={key:item for key,item in organization.items() if key in policy['allowed_fields']}
    return retained,{**policy,'unused_root_fields':[key for key in value if key not in roots],
        'unused_organization_fields':[key for key in organization if key not in policy['allowed_fields']]}


def output_allowance(configuration, phase, repairs, recovery_counts):
    policy=contract(configuration,phase)
    if not policy:return None
    default=8192 if phase=='extraction' or policy['phase']=='deep_dive' else (
        6144 if policy['phase'] in {'evolution','validation','actions'} else 4096)
    if recovery_counts.get('length'):
        # A complete response can need more output room after truncation.
        # The trusted meter/provider still admits the full input+output bound.
        return min(8192,default+2048)
    return int(repairs.get('output_tokens') or default)


def reading_representatives(outputs, metadata, evidence, configuration, query):
    """Select reading order; all accepted outputs remain in the root corpus."""
    if not enabled(configuration):return outputs,None
    requests=list(re.finditer(r'逐篇|全部(?:论文|成果)|所有论文|\bevery\s+paper\b|\ball\s+(?:papers|publications)\b',query,re.I))
    explicit_all=any(not re.search(r'(?:不需要|不必|不用|不要|无需|并非|\bnot\b|\bwithout\b|no need to)[^，。;.!?]{0,16}$',
        query[max(0,match.start()-32):match.start()],re.I) for match in requests)
    all_requested=(configuration.get('corpus') or {}).get('collection_mode')=='seeds_only' or explicit_all
    entities=[row['entity_id'] for row in configuration.get('scope',{}).get('entities',[])]
    limit=len(outputs) if all_requested else max(4,min(20,len(entities)))
    by_source={row.evidence_id:row for row in evidence}
    from app.evidence_selection import _terms
    terms=set(_terms(query));remaining=list(outputs);selected=[];years=set()

    def rank(row):
        sources=[by_source[key] for key in metadata.get(row['output_id'],{}).get('evidence_ids',[]) if key in by_source]
        full=any((source.acquisition or {}).get('coverage')=='full_text'
            and not (source.acquisition or {}).get('truncated') for source in sources)
        text=(row.get('title') or '').casefold()
        relevance=sum(term in text for term in terms)
        year=str(row.get('published_on') or '')[:4]
        return full,relevance,year not in years,str(row.get('published_on') or '')

    def take(row):
        selected.append(row);remaining.remove(row);years.add(str(row.get('published_on') or '')[:4])

    if all_requested:selected=list(outputs);remaining=[]
    else:
        for entity in entities:
            if any(any(aff.get('entity_id')==entity for aff in row.get('affiliations',[])) for row in selected):continue
            options=[row for row in remaining if any(aff.get('entity_id')==entity for aff in row.get('affiliations',[]))]
            if options and len(selected)<limit:take(max(options,key=rank))
        while remaining and len(selected)<limit:take(max(remaining,key=rank))
    return selected,{'version':VERSION,'selection':'explicit_all_or_declared_material' if all_requested else 'representative_reading',
        'selected_output_ids':[row['output_id'] for row in selected],
        'selected_works':[{'output_id':row['output_id'],'title':row.get('title'),
            'published_on':row.get('published_on'),'full_text_available':rank(row)[0]} for row in selected[:20]],
        'not_selected_output_ids':[row['output_id'] for row in remaining],
        'not_represented_entity_ids':[entity for entity in entities if not any(
            any(aff.get('entity_id')==entity for aff in row.get('affiliations',[])) for row in selected)],
        'accepted_output_count':len(outputs),'limit':limit,
        'basis':['current_full_text','selected_object_coverage','publication_year_coverage','literal_topic_match'],
        'semantics':'reading_selection_not_quality_ranking_or_causal_evidence_all_outputs_retained'}
