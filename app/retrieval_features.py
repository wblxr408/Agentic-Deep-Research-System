"""Source-anchored feature views. No model, network, training or database I/O."""
from __future__ import annotations

from collections import Counter,defaultdict
from datetime import date
import importlib.metadata
import math
import re
import unicodedata
from typing import Literal

from pydantic import Field,model_validator
from app.evidence_chunks import identity
from app.research_scope import ScopeRecord

VERSION='adrs-retrieval-features-v1'
TOKENIZER_VERSION='adrs-mixed-literal-v1'
FEATURE_BYTES=8*1024*1024
CJK_CLASS=r'\u3400-\u4dbf\u4e00-\u9fff\U00020000-\U0002ebef'
CJK='['+CJK_CLASS+']+'
WORD='[^\\W_'+CJK_CLASS+']+'
LEXEMES=re.compile(CJK+'|'+WORD+'(?:[.+/_-]'+WORD+r')*(?:\+\+(?:\d+)?|#)?',re.UNICODE)


class FeaturePolicy(ScopeRecord):
    dense:bool=False
    sparse:bool=False
    english_stemming:bool=False
    cjk_mode:Literal['characters','bigrams','both']='both'
    max_token_events:int=Field(default=1024,ge=128,le=2048)
    source_date:date|None=None
    as_of:date|None=None
    half_life_days:int=Field(default=730,ge=30,le=3650)
    window_start:date|None=None
    window_end:date|None=None

    @model_validator(mode='after')
    def valid_window(self):
        if self.window_start and self.window_end and self.window_start>self.window_end:
            raise ValueError('feature_time_window_is_reversed')
        if self.source_date and self.as_of is None:raise ValueError('source_date_requires_explicit_as_of')
        return self


def normalize_term(value):
    return unicodedata.normalize('NFKC',value).casefold()


def lexical_view(text,*,start=0,policy=None):
    """Offsets always reference the unmodified Unicode input, not normalized terms."""
    policy=policy if isinstance(policy,FeaturePolicy) else FeaturePolicy.model_validate(policy or {})
    counts=Counter();positions=defaultdict(list);count=0;truncated=False;long_terms=0;last_end=0
    for match in LEXEMES.finditer(text):
        value=match.group();base=match.start()
        if re.fullmatch(CJK,value):
            spans=[]
            if policy.cjk_mode in {'characters','both'}:spans.extend((i,i+1) for i in range(len(value)))
            if policy.cjk_mode in {'bigrams','both'}:spans.extend((i,i+2) for i in range(len(value)-1))
            # Retained token order is stable across document/query generation.
            spans.sort()
        else:spans=[(0,len(value))]
        for left,right in spans:
            if count>=policy.max_token_events:truncated=True;break
            raw=value[left:right];term=normalize_term(raw)
            if not term or len(term)>128:long_terms+=1;continue
            counts[term]+=1;count+=1;last_end=base+right
            if len(positions[term])<2:
                positions[term].append({'start':start+base+left,'end':start+base+right,'quote':raw})
        if truncated:break
    return {'tokenizer_version':TOKENIZER_VERSION,'normalization':'NFKC_casefold_original_offsets_preserved',
        'cjk_mode':policy.cjk_mode,'stemming':'not_applied_to_this_original_lexical_view',
        'terms':dict(counts),'positions':dict(positions),'length':count,'truncated':truncated,
        'coverage_end':start+last_end,'omitted_overlong_terms':long_terms,
        'positions_limit_per_term':2,'semantics':'lexical_features_not_learned_sparse_or_semantic_token_embeddings'}


def temporal_view(policy):
    result={'source_date':policy.source_date.isoformat() if policy.source_date else None,
        'as_of':policy.as_of.isoformat() if policy.as_of else None,'half_life_days':policy.half_life_days,
        'window_start':policy.window_start.isoformat() if policy.window_start else None,
        'window_end':policy.window_end.isoformat() if policy.window_end else None,
        'basis':'explicit_user_declared_source_date_not_independently_verified',
        'status':'unknown_source_date','age_days':None,'decay_weight':None,'in_window':None,
        'publication_date_inferred_from_mentions':False,'trend_inferred':False}
    if not policy.source_date:return result
    age=(policy.as_of-policy.source_date).days
    if age<0:
        result['status']='future_declared_date_requires_review';return result
    result.update(status='derived_from_declared_date',age_days=age,
        decay_weight=round(math.exp2(-age/policy.half_life_days),8),
        in_window=(policy.window_start is None or policy.source_date>=policy.window_start)
            and (policy.window_end is None or policy.source_date<=policy.window_end))
    return result


def dense_configuration(settings):
    revision=settings.embed_revision
    if not revision or not re.fullmatch(r'[a-fA-F0-9]{40}',revision):
        raise ValueError('dense_requires_pinned_40_character_model_commit')
    libraries={}
    for name in ('sentence-transformers','transformers','torch'):
        try:libraries[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:libraries[name]='unavailable'
    return {'model':settings.embed_model,'requested_revision':revision,'encoder_library_versions':libraries,
        'dimension':settings.embed_dimension,'normalization':'l2','encoder_method':'SentenceTransformer.encode',
        'schema_version':VERSION}


def validate_vectors(vectors,count,dimension):
    if len(vectors)!=count:raise ValueError('embedding_count_mismatch_no_source_committed')
    for vector in vectors:
        if len(vector)!=dimension or any(not isinstance(value,(float,int)) or isinstance(value,bool) or not math.isfinite(value) for value in vector):
            raise ValueError('embedding_dimension_or_finite_value_mismatch_no_source_committed')
        norm=math.sqrt(sum(value*value for value in vector))
        if not .98<=norm<=1.02:raise ValueError('embedding_normalization_mismatch_no_source_committed')


def validate_sparse_output(output,count):
    """Do not persist an incomplete or malformed model result as encoded features."""
    if not isinstance(output,dict):raise ValueError('sparse_actual_encoding_required')
    profile=output.get('profile');coverage=output.get('coverage');vectors=output.get('vectors')
    if not isinstance(profile,dict) or not isinstance(coverage,dict) or not isinstance(vectors,list) or len(vectors)!=count:
        raise ValueError('sparse_actual_encoding_required')
    size=profile.get('vocabulary_size');limit=profile.get('top_k');maximum=profile.get('maximum_input_tokens')
    if (profile.get('kind')!='splade_masked_lm_max_pool' or profile.get('local_files_only') is not True
            or not isinstance(size,int) or isinstance(size,bool) or size<1
            or not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=512
            or not isinstance(maximum,int) or isinstance(maximum,bool) or not 1<=maximum<=512
            or not re.fullmatch(r'[a-f0-9]{64}',str(profile.get('tokenizer_vocabulary_id','')))
            or coverage.get('chunk_count')!=count or coverage.get('truncated_inputs')!=0):
        raise ValueError('sparse_invalid_profile_or_coverage')
    for vector in vectors:
        if not isinstance(vector,dict):raise ValueError('sparse_invalid_vector')
        terms=vector.get('terms');tokens=vector.get('input_tokens');nonzero=vector.get('nonzero_before_top_k')
        if (not isinstance(terms,list) or len(terms)>limit or not isinstance(tokens,int) or isinstance(tokens,bool)
                or not 1<=tokens<=maximum or not isinstance(nonzero,int) or isinstance(nonzero,bool)
                or not len(terms)<=nonzero<=size or vector.get('top_k_truncated') is not (nonzero>limit)):
            raise ValueError('sparse_invalid_vector')
        seen=set()
        for term in terms:
            if not isinstance(term,dict):raise ValueError('sparse_invalid_vector')
            token=term.get('token_id');weight=term.get('weight')
            if (not isinstance(token,int) or isinstance(token,bool) or not 0<=token<size or token in seen
                    or not isinstance(weight,(int,float)) or isinstance(weight,bool) or not math.isfinite(weight) or weight<=0):
                raise ValueError('sparse_invalid_vector')
            seen.add(token)


def vector_parameter(vector):
    """Bind text explicitly; asyncpg need not infer an unregistered vector codec."""
    return '['+','.join(repr(float(value)) for value in vector)+']'


def candidate_decisions():
    return {
        'learned_sparse':{'status':'not_selected','candidates':['LSR','SPLADE','DeepImpact'],
            'reason':'requires_frozen_model_vocabulary_and_sparse_index_with_demonstrated_recall_cost_benefit'},
        'fine_grained_semantic':{'status':'not_selected','candidates':['token_embeddings','ColBERT_MaxSim'],
            'reason':'literal_token_positions_are_not_semantic_multi_vectors_requires_dedicated_model_and_index'},
        'behavioral':{'status':'not_selected_no_authorized_training_data','candidates':['collaborative_filtering','Item2Vec','sequence_model','behavioral_two_tower'],
            'reason':'no_stable_user_item_exposure_click_history_training_objective_or_cross_task_reuse_assumption',
            'reference':'https://github.com/zhongqiangwu960812/AI-RecommenderSystem/blob/master/Recall/YoutubeDNN/utils.py',
            'reference_input_fields':['user_id','article_id','expo_time'],'implicit_behavior_collection':False},
        'bsr':{'status':'beam_search_retrieval_planned','reason':'bounded_beam_over_real_authorized_source_structure_and_mention_edges_not_a_feature_encoding_or_confirmed_entity_graph'},
        'multimodal':{'status':'text_and_structure_only','joint_image_text_encoding':False,
            'reason':'retained_image_pointers_and_captions_are_not_authorized_image_bytes_or_image_embeddings'},
        'entity_linking':{'status':'dictionary_mentions_only','model_ner':False,'confirmed_relationship_inference':False},
    }


def build_feature_plan(text,chunk_plan,parsed,*,policy=None,dense_profile=None,sparse_output=None,stem_output=None):
    policy=policy if isinstance(policy,FeaturePolicy) else FeaturePolicy.model_validate(policy or {})
    policy_data=policy.model_dump(mode='json')
    if not policy.sparse:policy_data.pop('sparse',None)
    if not policy.english_stemming:policy_data.pop('english_stemming',None)
    if policy.sparse:validate_sparse_output(sparse_output,len(chunk_plan['children']))
    if policy.english_stemming and (not isinstance(stem_output,dict) or not isinstance(stem_output.get('profile'),dict)
            or not isinstance(stem_output.get('vectors'),list) or len(stem_output['vectors'])!=len(chunk_plan['children'])
            or not isinstance(stem_output.get('coverage'),dict) or stem_output['coverage'].get('chunk_count')!=len(chunk_plan['children'])):
        raise ValueError('stemming_actual_derivation_required')
    profile={'schema_version':VERSION,'tokenizer_version':TOKENIZER_VERSION,'policy':policy_data,
        'dense_configuration':dense_profile if policy.dense else None}
    if policy.sparse:profile['sparse_configuration']=sparse_output['profile']
    if policy.english_stemming:profile['stemming_configuration']=stem_output['profile']
    children=[];used_bytes=0;omitted=0;df=Counter()
    import json
    for chunk in chunk_plan['children']:
        lexical=lexical_view(text[chunk['start']:chunk['end']],start=chunk['start'],policy=policy)
        entry={'logical_chunk_id':chunk['logical_chunk_id'],'source_version':chunk_plan['source_version'],
            'start':chunk['start'],'end':chunk['end'],'lexical':lexical,
            'entity_mentions':chunk['entity_mentions'],'date_mentions':chunk['date_mentions'],
            'reference_mentions':chunk['reference_mentions'],'labels':chunk['labels'],
            'confirmed_entity_relations':False,'entity_disambiguation':'not_performed'}
        serialized=len(json.dumps(entry,ensure_ascii=False).encode('utf-8'))
        if used_bytes+serialized>FEATURE_BYTES-65536:
            omitted+=1
            children.append({'logical_chunk_id':chunk['logical_chunk_id'],'source_version':chunk_plan['source_version'],
                'start':chunk['start'],'end':chunk['end'],'lexical':None,'status':'omitted_under_source_feature_budget'})
            continue
        used_bytes+=serialized;df.update(lexical['terms'].keys());children.append(entry)
    available=[entry for entry in children if entry.get('lexical') is not None];n=len(available)
    for entry in available:
        lexical=entry['lexical']
        weights={term:(1+math.log(tf))*(math.log((n+1)/(df[term]+1))+1) for term,tf in lexical['terms'].items()}
        norm=math.sqrt(sum(value*value for value in weights.values()))
        lexical['source_tfidf']={term:round(value/norm,7) for term,value in weights.items()} if norm else {}
    # A final bounded representation includes IDF weights, not only initial TF.
    actual_bytes=len(json.dumps(children,ensure_ascii=False).encode('utf-8'))
    for entry in reversed(available):
        if actual_bytes<=FEATURE_BYTES-65536:break
        before=len(json.dumps(entry,ensure_ascii=False).encode('utf-8'))
        retained={key:entry[key] for key in ('logical_chunk_id','source_version','start','end')}
        entry.clear();entry.update(retained,lexical=None,status='omitted_under_source_feature_budget')
        actual_bytes+=len(json.dumps(entry,ensure_ascii=False).encode('utf-8'))-before;omitted+=1
    available=[entry for entry in children if entry.get('lexical') is not None]
    if len(available)!=n:
        # Source IDF no longer has its complete cohort; do not retain stale weights.
        for entry in available:entry['lexical']['source_tfidf']={}
    actual_df=Counter(term for entry in available for term in entry['lexical']['terms'])
    count=len(available)
    temporal=temporal_view(policy)
    figures=(parsed or {}).get('figures',[])
    result={'schema_version':VERSION,'profile':profile,'profile_id':identity(profile),'source_version':chunk_plan['source_version'],
        'chunk_profile_id':chunk_plan['profile_id'],'children':children,
        'statistics':{'scope':'this_source_retained_feature_chunks_not_global_corpus_or_publications',
            'document_count':count,'total_chunk_count':len(children),'omitted_chunk_count':omitted,
            'token_event_count':sum(entry['lexical']['length'] for entry in available),
            'average_length':sum(entry['lexical']['length'] for entry in available)/count if count else None,
            'document_frequency':dict(actual_df),'idf_formula':'log((N+1)/(df+1))+1; tf=1+log(count); vector=l2_normalized',
            'idf_weights_status':'complete_for_retained_feature_cohort' if len(available)==n else 'omitted_after_budget_changed_cohort',
            'overlapping_chunks_counted_separately':True,
            'token_coverage':'no_text_chunks' if not children else 'partial' if omitted or any(entry['lexical']['truncated'] for entry in available) else 'complete_selected_lexical_policy'},
        'temporal':temporal,'modality':{'text':bool(text),'structure_available':bool(parsed),
            'figure_pointer_count':len(figures),'image_bytes_retained':False,'image_embeddings':False,
            'figure_references':[{'figure_id':item.get('figure_id'),'source_locator':item.get('source_locator')} for item in figures[:50]]},
        'candidate_decisions':candidate_decisions(),'dense':{'status':'requested_pending_actual_encoding' if policy.dense else 'disabled_no_encoding',
            'profile':dense_profile if policy.dense else None},'effects':{'language_model_calls':0,'behavioral_training':False,'external_image_fetches':0}}
    # Bound the complete source plan, including DF and weights. A budget gap
    # remains unknown; no shortened vector is mislabeled as complete.
    if len(json.dumps(result,ensure_ascii=False).encode('utf-8'))>FEATURE_BYTES-65536:
        for entry in children:
            if entry.get('lexical') is not None:
                retained={key:entry[key] for key in ('logical_chunk_id','source_version','start','end')}
                entry.clear();entry.update(retained,lexical=None,status='omitted_under_total_feature_budget')
        result['statistics'].update(document_count=0,omitted_chunk_count=len(children),token_event_count=None,average_length=None,
            document_frequency={},idf_weights_status='unavailable_under_total_feature_budget',token_coverage='unknown_under_total_feature_budget')
    if policy.sparse:
        for entry,vector in zip(children,sparse_output['vectors']):entry['learned_sparse']=vector
        result['learned_sparse']={'status':'encoded_splade','profile':sparse_output['profile'],'coverage':sparse_output['coverage']}
        result['candidate_decisions']['learned_sparse']={'status':'splade_encoded_other_methods_not_selected',
            'reason':'actual_local_masked_lm_weights_retained_with_vocabulary_identity'}
        result['effects']['local_sparse_encoding_calls']=1
        if len(json.dumps(result,ensure_ascii=False).encode('utf-8'))>FEATURE_BYTES-65536:
            raise ValueError('sparse_feature_budget_exceeded')
    if policy.english_stemming:
        for entry,vector in zip(children,stem_output['vectors']):entry['stemmed_english']=vector
        result['stemmed_english']={'status':'derived_postgresql_english','profile':stem_output['profile'],
            'coverage':stem_output['coverage'],'original_lexical_view_retained':True}
        if len(json.dumps(result,ensure_ascii=False).encode('utf-8'))>FEATURE_BYTES-65536:
            raise ValueError('stemming_feature_budget_exceeded')
    result['metadata_budget_bytes']=FEATURE_BYTES
    return result
