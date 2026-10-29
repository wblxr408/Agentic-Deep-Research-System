"""Request-local references to already selected literal source text.

These functions never select new evidence, fetch, call a model or grant access.
The existing phase, source lifecycle and final audit retain their authority.
"""
from __future__ import annotations

from copy import deepcopy
import json

VERSION = 'adrs-phase-passages-v1'
MAX_PASSAGES = 128
MAX_CHARACTERS = 560


def _literal(row, sources):
    source=sources.get(row.get('evidence_id'))
    start,end=row.get('start'),row.get('end')
    if (not source or type(start) is not int or type(end) is not int
            or not 0<=start<end<=len(source.get('content') or '')
            or source['content'][start:end]!=row.get('quote')):
        raise ValueError('phase_passage_not_current_literal_source')
    return source


def attach_passages(text, manifest, evidence, *, assigned_groups=None):
    """Add IDs to the same selected text, without duplicating prompt bodies."""
    payload=json.loads(text)
    if not isinstance(payload,dict) or not isinstance(payload.get('sources'),list):
        raise ValueError('phase_passage_payload_invalid')
    sources={row['evidence_id']:row for row in evidence}
    records=[]
    for source in payload.get('sources',[]):
        from app.publication_opening import auxiliary_identity_source
        original_source=sources.get(source['evidence_id']) or {}
        source['source_role']='auxiliary_profile_or_cv' if auxiliary_identity_source(original_source) else (
            'acquired_full_text' if source.get('source_coverage')=='full_text' else 'acquired_supporting_source')
        if assigned_groups is not None:
            source['assigned_output_ids']=[key for key,identifiers in assigned_groups.items()
                if source['evidence_id'] in identifiers]
        parts=[]
        for excerpt in source.get('excerpts',[]):
            original={**excerpt,'evidence_id':source['evidence_id']}
            retained=_literal(original,sources)
            quote=excerpt['quote'];left=0
            while left<len(quote):
                if len(records)>=MAX_PASSAGES:
                    # Keep the remaining original text visible. There is no ID
                    # for this tail; the legacy literal-proof path still applies.
                    start,end=excerpt['start']+left,excerpt['end']
                    pages=[page['number'] for page in (retained.get('acquisition') or {}).get('pages',[])
                        if start<page['end'] and end>page['start']]
                    parts.append({**{key:value for key,value in excerpt.items() if key!='boundary'},
                        'start':start,'end':end,'quote':quote[left:],'pages':pages,
                        'passage_reference':'limit_reached_literal_only',
                        'boundary':{'scope':'fragment_of_selected_window',
                            'parent_start':excerpt['start'],'parent_end':excerpt['end']}})
                    break
                right=min(len(quote),left+MAX_CHARACTERS)
                if right<len(quote):
                    cut=quote.rfind('\n',left+MAX_CHARACTERS//2,right)
                    if cut<0:cut=quote.rfind(' ',left+MAX_CHARACTERS//2,right)
                    if cut>=0:right=cut+1
                start,end=excerpt['start']+left,excerpt['start']+right
                identifier='p'+str(len(records)+1)
                pages=[page['number'] for page in (retained.get('acquisition') or {}).get('pages',[])
                    if start<page['end'] and end>page['start']]
                record={'passage_id':identifier,'evidence_id':source['evidence_id'],
                    'citation_id':source['citation_id'],'start':start,'end':end,'quote':quote[left:right],
                    'pages':pages}
                records.append(record)
                parts.append({**{key:value for key,value in excerpt.items() if key!='boundary'},
                    **{key:record[key] for key in ('passage_id','start','end','quote','pages')},
                    'boundary':{'scope':'fragment_of_selected_window',
                        'parent_start':excerpt['start'],'parent_end':excerpt['end']}})
                left=right
        source['excerpts']=parts
    updated=deepcopy(manifest)
    updated['source_roles']=[{key:source[key] for key in ('evidence_id','source_role','assigned_output_ids')
        if key in source} for source in payload['sources']]
    updated['proof_passages']={'version':VERSION,'records':records,
        'semantics':'request_local_literal_locations_not_entailment_or_new_permissions'}
    return json.dumps(payload,ensure_ascii=False,separators=(',',':')),updated


def resolve_proofs(value, manifest, evidence):
    """Resolve only exact reference objects in this model response.

    Invalid references remain invalid objects for existing field validators;
    never fabricate a source, silently select another passage or join quotes.
    """
    table=manifest.get('proof_passages') or {}
    if table.get('version')!=VERSION:raise ValueError('phase_passage_contract_unavailable')
    records=table.get('records')
    if not isinstance(records,list) or len(records)>MAX_PASSAGES:
        raise ValueError('phase_passage_manifest_invalid')
    sources={row['evidence_id']:row for row in evidence}
    selected={row['evidence_id']:row for row in manifest.get('sources',[])}
    lookup={}
    for row in records:
        _literal(row,sources)
        source=selected.get(row['evidence_id']) or {}
        if (not isinstance(row.get('passage_id'),str) or row['passage_id'] in lookup or len(row['quote'])>MAX_CHARACTERS
                or row.get('citation_id')!=source.get('citation_id')
                or not any(part['start']<=row['start']<row['end']<=part['end']
                    for part in source.get('excerpts',[]))):
            raise ValueError('phase_passage_manifest_invalid')
        lookup[row['passage_id']]=row
    events=[];visited=0

    def walk(item,path,depth):
        nonlocal visited
        visited+=1
        if depth>32 or visited>4096:raise ValueError('phase_proof_response_bound_exceeded')
        if isinstance(item,list):return [walk(child,[*path,index],depth+1) for index,child in enumerate(item)]
        if not isinstance(item,dict):return item
        if 'passage_id' in item:
            identifier=item.get('passage_id')
            row=lookup.get(identifier) if isinstance(identifier,str) else None
            valid=set(item)=={'passage_id'} and row is not None and len(events)<256
            if len(events)<256:
                events.append({'kind':'request_local_proof_reference','path':path,'passage_id':identifier,
                    'status':'resolved' if valid else 'invalid',
                    **({key:row[key] for key in ('evidence_id','start','end')} if valid else {})})
            return {'evidence_id':row['evidence_id'],'quote':row['quote']} if valid else deepcopy(item)
        return {key:walk(child,[*path,key],depth+1) for key,child in item.items()}

    return walk(value,[],0),events
