"""Run explicit semantic chunking with the existing pinned local encoder."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

from app.channels.execution import CommandRunner
from app.config import get_settings
from app.retrieval_features import dense_configuration


def build_semantic_plan(text,size,threshold):
    config=get_settings().rag
    dense_configuration(config)
    options={'model':config.embed_model,'revision':config.embed_revision,'dimension':config.embed_dimension,
        'size':size,'threshold':threshold}
    with tempfile.TemporaryDirectory(prefix='adrs-semantic-chunk-') as directory:
        path=Path(directory)/'source.txt';path.write_text(text,encoding='utf-8')
        raw=CommandRunner().run([sys.executable,str(Path(__file__).with_name('semantic_chunk_worker.py')),
            str(path),json.dumps(options,ensure_ascii=True)],timeout=120,max_bytes=2*1024*1024)
    try:payload=json.loads(raw)
    except ValueError:raise ValueError('semantic_local_model_unavailable') from None
    if not isinstance(payload,dict) or not payload.get('ok'):
        raise ValueError(payload.get('error','semantic_local_model_unavailable') if isinstance(payload,dict) else 'semantic_local_model_unavailable')
    return payload['result']
