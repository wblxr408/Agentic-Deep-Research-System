"""Encode supplied real image and bounded source text with one local CLIP model."""
from __future__ import annotations

import base64
from contextlib import redirect_stdout,redirect_stderr
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import sys


def run(path,options):
    import torch
    from PIL import Image
    from transformers import CLIPModel,CLIPProcessor
    payload=json.loads(path.read_text(encoding='utf-8'))
    image_bytes=base64.b64decode(payload['image'],validate=True);text=payload['text'];base=int(payload['text_start'])
    if len(image_bytes)>1_400_000 or not isinstance(text,str) or len(text)>16000:raise ValueError('multimodal_input_limit')
    processor=CLIPProcessor.from_pretrained(options['model'],revision=options['revision'],local_files_only=True,trust_remote_code=False)
    model=CLIPModel.from_pretrained(options['model'],revision=options['revision'],local_files_only=True,trust_remote_code=False,use_safetensors=True)
    model.eval();tokenizer=processor.tokenizer
    if not getattr(tokenizer,'is_fast',False):raise ValueError('multimodal_fast_tokenizer_required')
    maximum=getattr(model.config.text_config,'max_position_embeddings',None)
    if not isinstance(maximum,int) or not 3<=maximum<=1024:raise ValueError('multimodal_model_context_invalid')
    with Image.open(io.BytesIO(image_bytes)) as image:
        image.load();inputs=processor(images=image.convert('RGB'),return_tensors='pt')
    windows=[];text_array=None;total_windows=0
    with torch.inference_mode():
        image_vector=model.get_image_features(pixel_values=inputs['pixel_values'])[0]
        if not torch.isfinite(image_vector).all() or torch.linalg.vector_norm(image_vector)<=0:raise ValueError('multimodal_invalid_output')
        image_vector=image_vector/torch.linalg.vector_norm(image_vector)
        if text.strip():
            encoded=tokenizer(text,add_special_tokens=True,truncation=True,max_length=maximum,padding='max_length',
                return_overflowing_tokens=True,return_offsets_mapping=True,return_tensors='pt')
            total_windows=len(encoded['input_ids']);offsets=encoded.pop('offset_mapping')
            accepted=[]
            for index in range(min(total_windows,8)):
                spans=[(int(start),int(end)) for start,end in offsets[index].tolist() if end>start]
                if not spans:continue
                start=min(item[0] for item in spans);end=max(item[1] for item in spans)
                if not 0<=start<end<=len(text):raise ValueError('multimodal_invalid_offsets')
                windows.append({'start':base+start,'end':base+end,'input_tokens':int(encoded['attention_mask'][index].sum())})
                accepted.append(index)
            if accepted:
                selected={key:value[accepted] for key,value in encoded.items() if key in {'input_ids','attention_mask','position_ids'}}
                text_vectors=model.get_text_features(**selected)
                norms=torch.linalg.vector_norm(text_vectors,dim=1,keepdim=True)
                if not torch.isfinite(text_vectors).all() or torch.any(norms<=0):raise ValueError('multimodal_invalid_output')
                text_array=(text_vectors/norms).cpu().float().numpy().astype('<f4',copy=False)
    image_array=image_vector.cpu().float().numpy().astype('<f4',copy=False);dimension=int(image_array.shape[0])
    if not 1<=dimension<=4096 or text_array is not None and text_array.shape[1]!=dimension:raise ValueError('multimodal_dimension_mismatch')
    image_vector_bytes=image_array.tobytes();text_vector_bytes=text_array.tobytes() if text_array is not None else b''
    vocabulary=tokenizer.get_vocab();encoded_vocab=json.dumps(vocabulary,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    return {'image_f32le':base64.b64encode(image_vector_bytes).decode('ascii'),
        'text_f32le':base64.b64encode(text_vector_bytes).decode('ascii'),'dimension':dimension,'text_windows':windows,
        'coverage':{'total_token_windows':total_windows,'encoded_text_windows':len(windows),'text_characters_considered':len(text),
            'source_text_characters':int(payload['source_text_characters']),'image_width':payload['width'],'image_height':payload['height'],
            'image_render_sha256':hashlib.sha256(image_bytes).hexdigest()},
        'profile':{'model':options['model'],'revision':options['revision'],'normalization':'l2_image_and_text',
            'tokenizer_vocabulary_id':hashlib.sha256(encoded_vocab).hexdigest(),'text_context_tokens':maximum,
            'transformers_version':importlib.metadata.version('transformers'),'torch_version':str(torch.__version__),
            'local_files_only':True,'trust_remote_code':False,'weights_format':'safetensors_required','dtype':'float32_little_endian'}}


if __name__=='__main__':
    with open(os.devnull,'w') as sink,redirect_stdout(sink),redirect_stderr(sink):
        try:payload={'ok':True,'result':run(Path(sys.argv[1]),json.loads(sys.argv[2]))}
        except Exception as error:
            code=str(error)
            payload={'ok':False,'error':code if isinstance(error,ValueError) and code.startswith('multimodal_') else 'multimodal_local_model_unavailable'}
    print(json.dumps(payload,ensure_ascii=True,allow_nan=False))
