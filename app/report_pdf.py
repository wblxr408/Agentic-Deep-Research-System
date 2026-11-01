"""Deterministic PDF export of the authorized, reviewed delivery view."""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path


def printed_charts(charts):
    """The descriptors actually printed by the main/appendix PDF renderer."""
    selected=[]
    comparison=next((chart for chart in charts if chart.get('chart_id')=='technical_comparison'
        and chart.get('rows')),None)
    if comparison:
        selected.append({**comparison,'title':'代表成果的问题与机制',
            'columns':comparison.get('columns',[])[:3],
            'rows':[{**row,'values':row['values'][:3],
                'cell_citation_ids':{key:value for key,value in (row.get('cell_citation_ids') or {}).items()
                    if key in {'0','1','2'}}} for row in comparison['rows']]})
    selected.extend(chart for chart in charts if chart.get('kind')=='network'
        and chart.get('nodes') and len(chart['nodes'])<=24 and len(chart.get('edges',[]))<=60)
    return selected


def export_pdf(view,part):
    from app.research_figures import run_renderer
    from fastapi.encoders import jsonable_encoder
    if part not in {'main','appendix'}:raise ValueError('pdf_part_invalid')
    if not view.get('delivery_complete'):raise ValueError('pdf_report_not_deliverable')
    # No audit history, internal workflow or model prompt enters the renderer.
    payload={'part':part,'title':view['title'],
        'markdown':view['main_report_markdown' if part=='main' else 'appendix_markdown'],
        'charts':printed_charts(view.get('charts',[])),'sources':view.get('citations',[]),
        'original_pages':(view.get('source_media') or {}).get('pages',[]) if part=='appendix' else []}
    raw=json.dumps(jsonable_encoder(payload),ensure_ascii=False)
    if len(raw.encode('utf8'))>24_000_000:raise ValueError('pdf_input_limit')
    result=run_renderer([sys.executable,'-m','app.report_pdf_renderer'],raw,timeout=60,
        cwd=str(Path(__file__).resolve().parent.parent),env=dict(os.environ))
    if result.returncode:raise ValueError('pdf_render_failed')
    if len(result.stdout)>32_000_000:raise ValueError('pdf_output_limit')
    pdf=base64.b64decode(json.loads(result.stdout)['pdf'],validate=True)
    if not pdf.startswith(b'%PDF-'):raise ValueError('pdf_output_invalid')
    return pdf
