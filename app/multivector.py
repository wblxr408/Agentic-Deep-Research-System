"""Explicit paired local encoders; a shared space is operator-declared."""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import sys
import tempfile

from app.channels.execution import CommandRunner
from app.config import get_settings
from app.evidence_chunks import identity


def paired_configuration():
    cfg=get_settings().rag
    for model,revision in ((cfg.multivector_document_model,cfg.multivector_document_revision),
            (cfg.multivector_query_model,cfg.multivector_query_revision)):
        if (not model or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',model) or '..' in model
                or not revision or not re.fullmatch(r'[a-fA-F0-9]{40}',revision)):
            raise ValueError('multivector_requires_pinned_model_pair')
    if not cfg.multivector_space or not re.fullmatch(r'[A-Za-z0-9_.-]{1,120}',cfg.multivector_space):
        raise ValueError('multivector_requires_declared_shared_space')
    digest=lambda text:hashlib.sha256(text.encode('utf-8')).hexdigest()
    pair={'space':cfg.multivector_space,'space_compatibility':'operator_declared_not_inferred_from_dimension',
        'document_model':cfg.multivector_document_model,'document_revision':cfg.multivector_document_revision,
        'query_model':cfg.multivector_query_model,'query_revision':cfg.multivector_query_revision,
        'document_prefix_digest':digest(cfg.multivector_document_prefix),'query_prefix_digest':digest(cfg.multivector_query_prefix),
        'maximum_input_tokens':cfg.multivector_max_input_tokens,'local_files_only':True,'trust_remote_code':False,
        'normalization':'l2_per_token_and_sentence'}
    pair['pair_id']=identity(pair)
    return pair


def encode_paired_texts(chunks,*,role='document',timeout=180):
    if role not in {'document','query'}:raise ValueError('multivector_invalid_role')
    pair=paired_configuration();cfg=get_settings().rag
    if not 1<=len(chunks)<=200:raise ValueError('multivector_chunk_limit')
    if not isinstance(timeout,(int,float)) or not 0<timeout<=180:raise ValueError('multivector_deadline_unavailable')
    options={'model':pair[role+'_model'],'revision':pair[role+'_revision'],'max_input_tokens':pair['maximum_input_tokens']}
    with tempfile.TemporaryDirectory(prefix='adrs-multivector-') as directory:
        path=Path(directory)/'chunks.json';path.write_text(json.dumps({'chunks':chunks,'prefix':getattr(cfg,'multivector_'+role+'_prefix')},ensure_ascii=False),encoding='utf-8')
        raw=CommandRunner().run([sys.executable,str(Path(__file__).with_name('multivector_worker.py')),
            str(path),json.dumps(options,ensure_ascii=True)],timeout=timeout,max_bytes=18*1024*1024)
    try:payload=json.loads(raw)
    except ValueError:raise ValueError('multivector_local_model_unavailable') from None
    if not isinstance(payload,dict) or not payload.get('ok'):
        raise ValueError(payload.get('error','multivector_local_model_unavailable') if isinstance(payload,dict) else 'multivector_local_model_unavailable')
    output=payload.get('result')
    if not isinstance(output,dict):raise ValueError('multivector_invalid_output')
    observed=output.get('observed');vectors=output.get('vectors')
    if not isinstance(observed,dict) or not isinstance(vectors,list) or len(vectors)!=len(chunks):raise ValueError('multivector_invalid_output')
    token_dim=observed.get('token_dimension');pooled_dim=observed.get('pooled_dimension')
    if not isinstance(token_dim,int) or not isinstance(pooled_dim,int) or not 1<=token_dim<=4096 or not 1<=pooled_dim<=4096:
        raise ValueError('multivector_invalid_output')
    decoded=[];total=0
    for text,vector in zip(chunks,vectors,strict=True):
        if not isinstance(vector,dict):raise ValueError('multivector_invalid_output')
        count=vector.get('input_tokens');locations=vector.get('locations')
        if not isinstance(count,int) or not 1<=count<=pair['maximum_input_tokens'] or not isinstance(locations,list) or len(locations)!=count:
            raise ValueError('multivector_invalid_output')
        if any(item is not None and (not isinstance(item,dict) or not isinstance(item.get('start'),int)
                or not isinstance(item.get('end'),int) or not 0<=item['start']<item['end']<=len(text)) for item in locations):
            raise ValueError('multivector_invalid_offsets')
        if not any(item is not None for item in locations):raise ValueError('multivector_no_source_tokens')
        try:token_bytes=base64.b64decode(vector['tokens_f32le'],validate=True);pooled_bytes=base64.b64decode(vector['pooled_f32le'],validate=True)
        except (KeyError,TypeError,ValueError,binascii.Error):raise ValueError('multivector_invalid_output') from None
        if len(token_bytes)!=count*token_dim*4 or len(pooled_bytes)!=pooled_dim*4:raise ValueError('multivector_invalid_output')
        if any(not math.isfinite(item[0]) for block in (token_bytes,pooled_bytes) for item in struct.iter_unpack('<f',block)):
            raise ValueError('multivector_invalid_output')
        for block,dimension in ((token_bytes,token_dim),(pooled_bytes,pooled_dim)):
            stride=dimension*4
            for offset in range(0,len(block),stride):
                norm=math.sqrt(sum(value[0]*value[0] for value in struct.iter_unpack('<f',block[offset:offset+stride])))
                if not .98<=norm<=1.02:raise ValueError('multivector_invalid_output')
        total+=len(token_bytes)+len(pooled_bytes)
        decoded.append({'token_bytes':token_bytes,'pooled_bytes':pooled_bytes,'locations':locations,'input_tokens':count})
    if total>12*1024*1024 or observed.get('stored_bytes')!=total or observed.get('truncated_inputs')!=0:
        raise ValueError('multivector_invalid_output')
    return {'pair':pair,'observed':observed,'vectors':decoded}
