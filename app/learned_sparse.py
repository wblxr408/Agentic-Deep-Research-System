"""Explicit local-only SPLADE inference under fixed source and model bounds."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import tempfile

from app.channels.execution import CommandRunner
from app.config import get_settings


def build_sparse_features(chunks,*,timeout=120):
    config=get_settings().rag
    if (not config.sparse_model or not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',config.sparse_model)
            or '..' in config.sparse_model or not config.sparse_revision
            or not re.fullmatch(r'[a-fA-F0-9]{40}',config.sparse_revision)):
        raise ValueError('sparse_requires_pinned_cached_model')
    if not 1<=len(chunks)<=200:raise ValueError('sparse_chunk_limit')
    if not isinstance(timeout,(int,float)) or not 0<timeout<=120:raise ValueError('sparse_deadline_unavailable')
    options={'model':config.sparse_model,'revision':config.sparse_revision,
        'max_input_tokens':config.sparse_max_input_tokens,'top_k':config.sparse_top_k}
    with tempfile.TemporaryDirectory(prefix='adrs-sparse-') as directory:
        path=Path(directory)/'chunks.json';path.write_text(json.dumps({'chunks':chunks},ensure_ascii=False),encoding='utf-8')
        output=CommandRunner().run([sys.executable,str(Path(__file__).with_name('learned_sparse_worker.py')),
            str(path),json.dumps(options,ensure_ascii=True)],timeout=timeout,max_bytes=4*1024*1024)
    try:payload=json.loads(output)
    except ValueError:raise ValueError('sparse_local_model_unavailable') from None
    if not isinstance(payload,dict) or not payload.get('ok'):
        raise ValueError(payload.get('error','sparse_local_model_unavailable') if isinstance(payload,dict) else 'sparse_local_model_unavailable')
    return payload['result']
