"""Local image/text vectors from actual version-bound source inputs."""
from __future__ import annotations

import base64
import binascii
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


def configuration():
    cfg=get_settings().rag
    if (not cfg.multimodal_model or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',cfg.multimodal_model)
            or '..' in cfg.multimodal_model or not cfg.multimodal_revision
            or not re.fullmatch(r'[a-fA-F0-9]{40}',cfg.multimodal_revision)):
        raise ValueError('multimodal_requires_pinned_cached_model')
    return {'model':cfg.multimodal_model,'revision':cfg.multimodal_revision,'algorithm':'clip_projected_image_text',
        'local_files_only':True,'trust_remote_code':False,'weights_format':'safetensors_required'}


def encode_image_text(image,text,text_start,source_text_characters):
    options=configuration()
    with tempfile.TemporaryDirectory(prefix='adrs-multimodal-') as directory:
        path=Path(directory)/'input.json'
        path.write_text(json.dumps({'image':image['data'],'width':image['width'],'height':image['height'],
            'text':text,'text_start':text_start,'source_text_characters':source_text_characters},ensure_ascii=False),encoding='utf-8')
        raw=CommandRunner().run([sys.executable,str(Path(__file__).with_name('multimodal_worker.py')),
            str(path),json.dumps(options,ensure_ascii=True)],timeout=180,max_bytes=1024*1024)
    try:payload=json.loads(raw)
    except ValueError:raise ValueError('multimodal_local_model_unavailable') from None
    if not isinstance(payload,dict) or not payload.get('ok'):
        raise ValueError(payload.get('error','multimodal_local_model_unavailable') if isinstance(payload,dict) else 'multimodal_local_model_unavailable')
    output=payload.get('result')
    if not isinstance(output,dict):raise ValueError('multimodal_invalid_output')
    dimension=output.get('dimension');windows=output.get('text_windows');profile=output.get('profile');coverage=output.get('coverage')
    if (not isinstance(dimension,int) or isinstance(dimension,bool) or not 1<=dimension<=4096
            or not isinstance(windows,list) or len(windows)>8 or not isinstance(profile,dict) or not isinstance(coverage,dict)
            or profile.get('model')!=options['model'] or profile.get('revision')!=options['revision']
            or coverage.get('encoded_text_windows')!=len(windows)):
        raise ValueError('multimodal_invalid_output')
    for window in windows:
        if (not isinstance(window,dict) or not isinstance(window.get('start'),int) or not isinstance(window.get('end'),int)
                or not text_start<=window['start']<window['end']<=text_start+len(text)):
            raise ValueError('multimodal_invalid_offsets')
    try:image_bytes=base64.b64decode(output['image_f32le'],validate=True);text_bytes=base64.b64decode(output['text_f32le'],validate=True)
    except (KeyError,TypeError,ValueError,binascii.Error):raise ValueError('multimodal_invalid_output') from None
    stride=dimension*4
    if len(image_bytes)!=stride or len(text_bytes)!=len(windows)*stride:raise ValueError('multimodal_invalid_output')
    for block in (image_bytes,text_bytes):
        for start in range(0,len(block),stride):
            values=[item[0] for item in struct.iter_unpack('<f',block[start:start+stride])]
            if any(not math.isfinite(value) for value in values) or not .98<=math.sqrt(sum(value*value for value in values))<=1.02:
                raise ValueError('multimodal_invalid_output')
    profile['profile_id']=identity(profile)
    return {'image_bytes':image_bytes,'text_bytes':text_bytes,'dimension':dimension,'windows':windows,
        'profile':profile,'coverage':coverage}
