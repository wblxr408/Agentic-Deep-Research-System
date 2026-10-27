"""Bounded local-only semantic boundaries; source text arrives in a temp file."""
from __future__ import annotations

import importlib.metadata
import json
import math
import os
from pathlib import Path
import sys
from contextlib import redirect_stderr,redirect_stdout

MAX_UNITS=1000


def run(path,options):
    sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
    from app.evidence_chunks import semantic_units
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer

    text=path.read_text(encoding='utf-8');size=int(options['size']);threshold=float(options['threshold'])
    if not text.strip() or not 100<=size<=4000 or not -1<=threshold<=1:raise ValueError('semantic_input_invalid')
    units=semantic_units(text,size)
    if not units or len(units)>MAX_UNITS:raise ValueError('semantic_unit_limit')
    model=SentenceTransformer(options['model'],revision=options['revision'],trust_remote_code=False,local_files_only=True)
    tokenizer=getattr(model,'tokenizer',None);maximum=getattr(model,'max_seq_length',None)
    if not tokenizer or not isinstance(maximum,int) or maximum<=0:raise ValueError('semantic_token_coverage_unknown')
    prompt=(getattr(model,'prompts',{}) or {}).get(getattr(model,'default_prompt_name',None),'')
    passages=[text[start:end] for start,end in units];token_counts=[]
    for passage in passages:
        encoded=tokenizer(prompt+passage,add_special_tokens=True,truncation=False,
            return_attention_mask=False,return_token_type_ids=False)['input_ids']
        count=len(encoded);token_counts.append(count)
        if count>maximum:raise ValueError('semantic_unit_exceeds_encoder_context')
    vectors=np.asarray(model.encode(passages,batch_size=32,normalize_embeddings=True,
        show_progress_bar=False,convert_to_numpy=True))
    if vectors.ndim!=2 or vectors.shape[0]!=len(units) or vectors.shape[1]!=int(options['dimension']):
        raise ValueError('semantic_encoder_dimension_mismatch')
    if not np.isfinite(vectors).all():raise ValueError('semantic_encoder_invalid_vector')
    norms=np.linalg.norm(vectors,axis=1)
    if not np.isfinite(norms).all() or np.any(norms<0.98) or np.any(norms>1.02):raise ValueError('semantic_encoder_invalid_vector')
    boundaries=[0];decisions=[];group_start=0
    for index in range(1,len(units)):
        similarity=float(np.dot(vectors[index-1],vectors[index]));cut=similarity<threshold or units[index][1]-group_start>size
        if cut:boundaries.append(units[index][0]);group_start=units[index][0]
        decisions.append({'offset':units[index][0],'similarity':round(similarity,6),
            'boundary':cut,'reason':'semantic_change' if similarity<threshold else 'size_limit' if cut else 'similar'})
    boundaries.append(len(text))
    if any(boundaries[index]>=boundaries[index+1] for index in range(len(boundaries)-1)):
        raise ValueError('semantic_chunk_boundaries_invalid')
    return {'status':'encoded_local_source_units','boundaries':boundaries,'unit_count':len(units),
        'unit_ranges':[[start,end] for start,end in units],'decisions':decisions,'threshold':threshold,
        'coverage':{'status':'all_units_within_encoder_context','maximum_sequence_tokens':maximum,
            'largest_unit_tokens':max(token_counts,default=0),'truncated_units':0},
        'encoding_profile':{'model':options['model'],'requested_revision':options['revision'],'dimension':vectors.shape[1],
            'sentence_transformers_version':importlib.metadata.version('sentence-transformers'),
            'transformers_version':importlib.metadata.version('transformers'),'torch_version':torch.__version__,
            'normalization':'l2','local_files_only':True,'trust_remote_code':False}}


if __name__=='__main__':
    with open(os.devnull,'w') as sink,redirect_stdout(sink),redirect_stderr(sink):
        try:payload={'ok':True,'result':run(Path(sys.argv[1]),json.loads(sys.argv[2]))}
        except Exception as error:
            code=str(error)
            payload={'ok':False,'error':code if isinstance(error,ValueError) and code.startswith('semantic_') else 'semantic_local_model_unavailable'}
    print(json.dumps(payload,ensure_ascii=True))
