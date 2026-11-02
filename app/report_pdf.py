"""Deterministic PDF export of the authorized, reviewed delivery view."""
from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path
from copy import deepcopy

PDF_CHART_POLICY='adrs-pdf-referenced-charts-v2'


def project_pdf_view(charts,pages,policy):
    """One reviewed descriptor set for builtin PDF pages and their web view."""
    if policy!=PDF_CHART_POLICY:
        return [],deepcopy(pages),[{'location':'pdf','reason':'pdf_chart_policy_unsupported'}]
    from app.research_figures import figure_requests
    requests=figure_requests(charts,pages)
    projected=[];bindings={};issues=[]
    for request in requests:
        source=request['source_chart_id'];kind=request['presentation']
        rows=request.get('rows') or [];points=request.get('points') or []
        valid=(kind=='table' and bool(rows or points or request.get('edges'))
            or kind=='bar' and bool(points) and not rows
            or kind=='line' and source=='annual_publications' and bool(points)
            or kind=='network' and bool(request.get('nodes')) and len(request['nodes'])<=24
                and len(request.get('edges') or [])<=60)
        if not valid:
            issues.append({'location':source,'reason':'pdf_requested_chart_kind_unsupported','presentation':kind});continue
        chart={**request,'pdf_presentation':kind,'pdf_chart_policy':policy}
        if kind!='table':chart['kind']=kind
        if source=='technical_comparison' and kind=='table':
            chart.update(title='代表成果的问题与机制',columns=request.get('columns',[])[:3],
                rows=[{**row,'values':row['values'][:3],
                    'cell_citation_ids':{key:value for key,value in (row.get('cell_citation_ids') or {}).items()
                        if key in {'0','1','2'}}} for row in rows])
            for row in chart['rows']:
                row['citation_ids']=list(dict.fromkeys(ref for refs in row['cell_citation_ids'].values() for ref in refs))
            chart['citation_ids']=list(dict.fromkeys(ref for row in chart['rows'] for ref in row['citation_ids']))
        bindings[(source,kind,request.get('drawing_skill_id'))]=chart['chart_id']
        projected.append(chart)
    result=deepcopy(pages)
    for page in result:
        if not page.get('charts') and page.get('requested_chart_kind','auto') not in {'auto','none'}:
            issues.append({'location':page.get('page_id'),'reason':'pdf_requested_chart_data_unavailable',
                'presentation':page['requested_chart_kind']})
        refs=[]
        for ref in page.get('charts') or []:
            original=next((row for row in charts if row['chart_id']==ref['chart_id']),None)
            kind=original['kind'] if ref['kind']=='auto' and original else ref['kind']
            key=(ref['chart_id'],kind,ref.get('drawing_skill_id'))
            if key in bindings:refs.append({**ref,'chart_id':bindings[key],'kind':kind})
            else:
                page.setdefault('gaps',[]).append('所需图型暂无可用PDF表示，保留交付缺口。')
                if not any(issue['location']==ref['chart_id'] for issue in issues):
                    issues.append({'location':ref['chart_id'],'reason':'pdf_chart_reference_unresolved','presentation':kind})
        page['charts']=refs
    if sum(row['pdf_presentation']!='table' for row in projected)>12:
        issues.append({'location':'pdf','reason':'pdf_plot_count_exceeds_12'})
    return projected,result,issues


def printed_charts(charts,*,policy=None):
    """The descriptors actually printed by the main/appendix PDF renderer."""
    if policy is not None:
        if policy!=PDF_CHART_POLICY or any(chart.get('pdf_chart_policy')!=policy for chart in charts):
            raise ValueError('pdf_chart_projection_invalid')
        return deepcopy(charts)
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
        'charts':printed_charts(view.get('charts',[]),policy=view.get('pdf_chart_policy')),'sources':view.get('citations',[]),
        **({'pdf_chart_policy':view['pdf_chart_policy']} if view.get('pdf_chart_policy') else {}),
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
