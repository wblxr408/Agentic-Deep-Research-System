"""One complete text query in the same local CLIP projection space as images."""
from __future__ import annotations

import base64
from contextlib import redirect_stdout,redirect_stderr
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys


def run(path,options):
    import torch
    from transformers import CLIPModel,CLIPProcessor
    text=path.read_text(encoding='utf-8')
    if not text.strip() or len(text)>4000:raise ValueError('multimodal_query_invalid')
    processor=CLIPProcessor.from_pretrained(options['model'],revision=options['revision'],local_files_only=True,trust_remote_code=False)
    model=CLIPModel.from_pretrained(options['model'],revision=options['revision'],local_files_only=True,trust_remote_code=False,use_safetensors=True)
    model.eval();tokenizer=processor.tokenizer
    if not getattr(tokenizer,'is_fast',False):raise ValueError('multimodal_fast_tokenizer_required')
    maximum=getattr(model.config.text_config,'max_position_embeddings',None)
    if not isinstance(maximum,int) or not 3<=maximum<=1024:raise ValueError('multimodal_model_context_invalid')
    inputs=tokenizer(text,add_special_tokens=True,truncation=False,return_tensors='pt')
    token_count=int(inputs['input_ids'].shape[1])
    if token_count>maximum:raise ValueError('multimodal_query_exceeds_model_context')
    with torch.inference_mode():
        vector=model.get_text_features(**{key:value for key,value in inputs.items() if key in {'input_ids','attention_mask','position_ids'}})[0]
        norm=torch.linalg.vector_norm(vector)
        if not torch.isfinite(vector).all() or norm<=0:raise ValueError('multimodal_invalid_output')
        array=(vector/norm).cpu().float().numpy().astype('<f4',copy=False)
    vocab=json.dumps(tokenizer.get_vocab(),sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    return {'vector_f32le':base64.b64encode(array.tobytes()).decode('ascii'),'dimension':len(array),'input_tokens':token_count,
        'profile':{'model':options['model'],'revision':options['revision'],'normalization':'l2_image_and_text',
            'tokenizer_vocabulary_id':hashlib.sha256(vocab).hexdigest(),'text_context_tokens':maximum,
            'transformers_version':importlib.metadata.version('transformers'),'torch_version':str(torch.__version__),
            'local_files_only':True,'trust_remote_code':False,'weights_format':'safetensors_required','dtype':'float32_little_endian'}}


if __name__=='__main__':
    with open(os.devnull,'w') as sink,redirect_stdout(sink),redirect_stderr(sink):
        try:payload={'ok':True,'result':run(Path(sys.argv[1]),json.loads(sys.argv[2]))}
        except Exception as error:
            code=str(error)
            payload={'ok':False,'error':code if isinstance(error,ValueError) and code.startswith('multimodal_') else 'multimodal_local_model_unavailable'}
    print(json.dumps(payload,ensure_ascii=True,allow_nan=False))
