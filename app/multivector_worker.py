"""Bounded, local document/query encoder for pooled and token-level features."""
from __future__ import annotations

import base64
from contextlib import redirect_stderr,redirect_stdout
import importlib.metadata
import json
import os
from pathlib import Path
import sys


def run(path, options):
    import torch
    from sentence_transformers import SentenceTransformer
    payload=json.loads(path.read_text(encoding='utf-8'));chunks=payload['chunks'];prefix=payload['prefix']
    if not isinstance(chunks,list) or not 1<=len(chunks)<=200:raise ValueError('multivector_chunk_limit')
    if any(not isinstance(item,str) or len(item)>4000 for item in chunks):raise ValueError('multivector_input_invalid')
    model=SentenceTransformer(options['model'],revision=options['revision'],device='cpu',local_files_only=True,
        trust_remote_code=False,model_kwargs={'use_safetensors':True})
    model.eval();tokenizer=getattr(model,'tokenizer',None)
    if tokenizer is None or not getattr(tokenizer,'is_fast',False):raise ValueError('multivector_fast_tokenizer_required')
    maximum=int(options['max_input_tokens']);model_limit=getattr(model,'max_seq_length',None)
    if not isinstance(model_limit,int) or model_limit<maximum:raise ValueError('multivector_model_context_limit')
    vectors=[];total_bytes=0;token_dim=None;pooled_dim=None
    with torch.inference_mode():
        for text in chunks:
            full=prefix+text
            aligned=tokenizer(full,add_special_tokens=True,truncation=False,return_offsets_mapping=True)
            ids=aligned['input_ids'];offsets=aligned['offset_mapping']
            if len(ids)>maximum:raise ValueError('multivector_input_exceeds_model_context')
            features=model.tokenize([full])
            actual_ids=features['input_ids'][0].tolist()
            if actual_ids!=ids or len(offsets)!=len(ids):raise ValueError('multivector_token_alignment_unavailable')
            result=model.forward(features)
            attention=result['attention_mask'][0]
            if not bool(torch.all(attention==1)):raise ValueError('multivector_token_alignment_unavailable')
            tokens=result['token_embeddings'][0];pooled=result['sentence_embedding'][0]
            if tokens.ndim!=2 or pooled.ndim!=1 or len(tokens)!=len(ids):raise ValueError('multivector_model_invalid_output')
            if not torch.isfinite(tokens).all() or not torch.isfinite(pooled).all():raise ValueError('multivector_model_invalid_output')
            norms=torch.linalg.vector_norm(tokens,dim=1,keepdim=True);pooled_norm=torch.linalg.vector_norm(pooled)
            if torch.any(norms<=0) or pooled_norm<=0:raise ValueError('multivector_model_invalid_output')
            tokens=(tokens/norms).cpu().float().numpy().astype('<f4',copy=False)
            pooled=(pooled/pooled_norm).cpu().float().numpy().astype('<f4',copy=False)
            if token_dim is not None and (tokens.shape[1]!=token_dim or pooled.shape[0]!=pooled_dim):raise ValueError('multivector_dimension_mismatch')
            token_dim=int(tokens.shape[1]);pooled_dim=int(pooled.shape[0])
            if not 1<=token_dim<=4096 or not 1<=pooled_dim<=4096:raise ValueError('multivector_dimension_limit')
            token_bytes=tokens.tobytes();pooled_bytes=pooled.tobytes();total_bytes+=len(token_bytes)+len(pooled_bytes)
            if total_bytes>12*1024*1024:raise ValueError('multivector_source_budget_exceeded')
            locations=[]
            for start,end in offsets:
                if not 0<=start<=end<=len(full):raise ValueError('multivector_token_alignment_unavailable')
                usable=end>start and start>=len(prefix)
                locations.append({'start':start-len(prefix),'end':end-len(prefix)} if usable else None)
            if not any(item is not None for item in locations):raise ValueError('multivector_no_source_tokens')
            vectors.append({'input_tokens':len(ids),'locations':locations,
                'tokens_f32le':base64.b64encode(token_bytes).decode('ascii'),
                'pooled_f32le':base64.b64encode(pooled_bytes).decode('ascii')})
    return {'vectors':vectors,'observed':{'token_dimension':token_dim,'pooled_dimension':pooled_dim,
        'stored_bytes':total_bytes,'input_chunks':len(chunks),'truncated_inputs':0,
        'sentence_transformers_version':importlib.metadata.version('sentence-transformers'),
        'transformers_version':importlib.metadata.version('transformers'),'torch_version':str(torch.__version__),
        'maximum_sequence_tokens':model_limit,'tokenizer':'fast_offset_mapping_verified_against_model_input_ids',
        'normalization':'l2_per_token_and_sentence','dtype':'float32_little_endian'}}


if __name__=='__main__':
    with open(os.devnull,'w') as sink,redirect_stdout(sink),redirect_stderr(sink):
        try:payload={'ok':True,'result':run(Path(sys.argv[1]),json.loads(sys.argv[2]))}
        except Exception as error:
            code=str(error)
            payload={'ok':False,'error':code if isinstance(error,ValueError) and code.startswith('multivector_') else 'multivector_local_model_unavailable'}
    print(json.dumps(payload,ensure_ascii=True,allow_nan=False))
