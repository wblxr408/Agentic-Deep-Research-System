"""Bounded local SPLADE max-pooled masked-LM document representations."""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
from contextlib import redirect_stderr,redirect_stdout

MAX_CHUNKS=200


def run(path,options):
    import torch
    from transformers import AutoModelForMaskedLM,AutoTokenizer
    payload=json.loads(path.read_text(encoding='utf-8'));chunks=payload['chunks']
    if not isinstance(chunks,list) or not 1<=len(chunks)<=MAX_CHUNKS:raise ValueError('sparse_chunk_limit')
    if any(not isinstance(item,str) or len(item)>4000 for item in chunks):raise ValueError('sparse_input_invalid')
    model_name,revision=options['model'],options['revision']
    tokenizer=AutoTokenizer.from_pretrained(model_name,revision=revision,local_files_only=True,trust_remote_code=False)
    model=AutoModelForMaskedLM.from_pretrained(model_name,revision=revision,local_files_only=True,trust_remote_code=False,use_safetensors=True)
    model.eval();maximum=int(options['max_input_tokens']);top_k=int(options['top_k'])
    model_limit=getattr(model.config,'max_position_embeddings',None)
    if isinstance(model_limit,int) and maximum>model_limit:raise ValueError('sparse_model_context_limit')
    vocab=tokenizer.get_vocab();vocab_encoded=json.dumps(vocab,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    vocabulary_identity=hashlib.sha256(vocab_encoded).hexdigest()
    result=[];largest=0;vocab_size=None
    with torch.inference_mode():
        for start in range(0,len(chunks),4):
            batch=chunks[start:start+4]
            untruncated=tokenizer(batch,add_special_tokens=True,truncation=False,padding=False)['input_ids']
            counts=[len(ids) for ids in untruncated];largest=max(largest,*counts)
            if any(count>maximum for count in counts):raise ValueError('sparse_input_exceeds_model_context')
            inputs=tokenizer(batch,add_special_tokens=True,truncation=False,padding=True,return_tensors='pt')
            logits=model(**inputs).logits
            if logits.ndim!=3 or not torch.isfinite(logits).all():raise ValueError('sparse_model_invalid_output')
            values=torch.amax(torch.log1p(torch.relu(logits))*inputs['attention_mask'].unsqueeze(-1),dim=1)
            vocab_size=int(values.shape[1]);limit=min(top_k,vocab_size)
            if max(vocab.values(),default=-1)>=vocab_size:raise ValueError('sparse_vocabulary_mismatch')
            weights,indices=torch.topk(values,k=limit,dim=1,sorted=True)
            nonzero=(values>0).sum(dim=1).tolist()
            for row in range(len(batch)):
                terms=[{'token_id':int(token),'weight':float(weight)} for token,weight in zip(indices[row].tolist(),weights[row].tolist()) if weight>0]
                result.append({'terms':terms,'input_tokens':counts[row],'nonzero_before_top_k':int(nonzero[row]),
                    'top_k_truncated':nonzero[row]>limit})
    return {'profile':{'kind':'splade_masked_lm_max_pool','model':model_name,'revision':revision,
        'tokenizer_vocabulary_id':vocabulary_identity,'vocabulary_size':vocab_size,'maximum_input_tokens':maximum,
        'top_k':top_k,'pooling':'max_log1p_relu_masked_logits','local_files_only':True,'trust_remote_code':False,'weights_format':'safetensors_required',
        'transformers_version':importlib.metadata.version('transformers'),'torch_version':str(torch.__version__)},
        'vectors':result,'coverage':{'chunk_count':len(chunks),'largest_input_tokens':largest,'truncated_inputs':0}}


if __name__=='__main__':
    with open(os.devnull,'w') as sink,redirect_stdout(sink),redirect_stderr(sink):
        try:payload={'ok':True,'result':run(Path(sys.argv[1]),json.loads(sys.argv[2]))}
        except Exception as error:
            code=str(error)
            payload={'ok':False,'error':code if isinstance(error,ValueError) and code.startswith('sparse_') else 'sparse_local_model_unavailable'}
    print(json.dumps(payload,ensure_ascii=True,allow_nan=False))
