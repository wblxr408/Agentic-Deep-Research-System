"""Deterministic query variants and root-derived channel shares; no authority."""
from __future__ import annotations

import re
from math import ceil

from app.channels.catalog import CATALOG, route_query

VERSION='adrs-query-routes-v1'


def _term_pattern(term):
    expression=re.escape(term)
    if term and term[0].isascii() and term[0].isalnum():expression=r'(?<!\w)'+expression
    if term and term[-1].isascii() and term[-1].isalnum():expression+=r'(?!\w)'
    return expression


def _contains(text,term):
    return bool(re.search(_term_pattern(term),text,re.I))


def search_route(query,understanding,*,channels=None,remaining_calls,remaining_seconds,
                 remaining_nodes=1,max_results=10,web_only=False):
    """Original first. Every returned variant still needs source-policy admission."""
    original=query.strip()
    channel,operation,value=route_query(original)
    explicit=operation=='read' or original.partition(':')[0].strip().lower() in CATALOG or channel!='web'
    snapshot=understanding or {}
    options=snapshot.get('query_rewriting') or {'max_variants':1,'term_aliases':{}}
    slots=snapshot.get('slots') or {}
    candidates=[{'query':original,'reason':'original_plan_query'}]
    if not explicit:
        names=[item['name'] for item in slots.get('entities',[]) if not any(
            _contains(value,name) for name in [item['name'],*item.get('aliases',[])])]
        window=slots.get('time_window') or {}
        additions=names[:2]
        if window and not re.search(r'(?<!\d)(?:19|20)\d{2}(?!\d)',value):
            additions=[*additions,window['start_date'][:4]+' '+window['end_date'][:4]]
        # Explicit aliases are query alternatives, not proof of entity identity.
        for term,aliases in options.get('term_aliases',{}).items():
            group=[term,*aliases]
            matched=next((item for item in group if _contains(value,item)),None)
            if matched:
                for alias in group:
                    if alias==matched:continue
                    candidates.append({'query':re.sub(_term_pattern(matched),lambda _:alias,value,flags=re.I),
                        'reason':'explicit_term_alias','term':matched,'alias':alias})
        if additions:
            candidates.append({'query':' '.join([value,*additions]),'reason':'frozen_entity_time_context'})
    unique=[];seen=set();rejected=[]
    for item in candidates:
        key=item['query'].casefold()
        variant_channel,variant_operation,_=route_query(item['query'])
        if (variant_channel,variant_operation)!=(channel,operation):
            rejected.append({**item,'rejection':'query_variant_changed_transport'})
            continue
        if unique and len(item['query'])>1800:
            rejected.append({**item,'rejection':'expanded_query_too_long'})
            continue
        if key not in seen and item['query'] and (not unique or len(item['query'])<=1800):
            unique.append(item);seen.add(key)
    calls=max(0,min(int(remaining_calls),ceil(max(0,int(remaining_calls))/max(1,remaining_nodes))))
    variant_capacity=max(1,calls//3) if (snapshot.get('source_followup') or {}).get('version') in {'adrs-discovery-handoff-v1','adrs-discovery-handoff-v2'} else calls
    count=min(int(options.get('max_variants',1)),variant_capacity,calls,len(unique)) if remaining_seconds>0 else 0
    variants=unique[:count]
    requested=[channel] if explicit else list(channels or [channel])
    selected=[];skipped=[]
    for name in requested:
        reason=('source_scope_requires_web_transport' if web_only and name!='web' else
            'unsupported_channel_operation' if name not in CATALOG or operation not in CATALOG[name].operations else None)
        if reason:skipped.append({'channel':name,'reason':reason})
        elif name not in selected:selected.append(name)
    # Each selected channel needs at least one real request. Do not silently
    # replace an explicit unsupported/forbidden platform with web search.
    available=calls//max(1,len(variants))
    for name in selected[available:]:skipped.append({'channel':name,'reason':'original_call_share_insufficient'})
    selected=selected[:available]
    return {'version':VERSION,'original_query':original,'variants':variants,
        'omitted_variants':unique[count:],'rejected_variants':rejected,'explicit_transport':explicit,'channels':selected,
        'skipped_channels':skipped,'max_calls':calls,
        'timeout_seconds':max(0,float(remaining_seconds))/max(1,remaining_nodes),
        'top_k':min(20,max(1,int(max_results))),
        'variant_limit':int(options.get('max_variants',1)),
        'representation':{'lexical':'literal_terms_and_explicit_aliases',
            'learned_sparse':'internal_opt_in_only_external_channels_receive_text_queries',
            'dense':'internal_retrieval_only_when_explicitly_enabled',
            'behavioral':'no_authorized_behavior_dataset_or_model'},
        'authority':'existing_owner_channels_source_policy_and_root_budget'}
