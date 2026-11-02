"""Bounded PDFFigures2 layout adapter; original bytes in, source regions out.

Only shipped code and a fixed JAR are executed. The caller owns task/source
authorization; this module grants no file, network or model capability.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import tempfile
import unicodedata

EXTRACTOR_REVISION='3d7ad46753d4a315cccd1c2bcab398380e88c534'
EXTRACTOR='adrs-pdffigures2-3d7ad46-pdfbox2037-bc186-v1'
FIGURE_RENDERER='adrs-original-pdf-figure-v1'
COORDINATES='PDF_cropbox_points_top_left_72dpi'
MAX_LAYOUT_BYTES=2_000_000


def rectangle(value):
    if not isinstance(value,(list,tuple)) or len(value)!=4:
        raise ValueError('source_figure_rectangle_invalid')
    if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in value):
        raise ValueError('source_figure_rectangle_invalid')
    x0,y0,x1,y1=value
    if not 0<=x0<x1<=20000 or not 0<=y0<y1<=20000:
        raise ValueError('source_figure_rectangle_invalid')
    return [0.0 if number==0 else float(number) for number in value]


def layout_from_json(rows):
    if not isinstance(rows,list) or len(rows)>1000:raise ValueError('source_figure_layout_count_invalid')
    figures=[];pending=[];seen=set()
    def box(row):
        if not isinstance(row,dict):raise ValueError('source_figure_layout_box_invalid')
        return rectangle([row.get(key) for key in ('x1','y1','x2','y2')])
    for row in rows:
        if not isinstance(row,dict):raise ValueError('source_figure_layout_invalid')
        page=row.get('page');kind=row.get('figType');name=row.get('name');caption=row.get('caption')
        if (type(page) is not int or page<0 or kind not in {'Figure','Table'}
                or not isinstance(name,str) or not 1<=len(name)<=120
                or not isinstance(caption,str) or not 1<=len(caption)<=12000):
            raise ValueError('source_figure_layout_invalid')
        # Retained acquisition/page contracts support pages 1--80. Layout
        # outside that range does not become evidence or an illustrated page.
        if page>=80:continue
        if '\x00' in name or '\x00' in caption:
            pending.append({'page':page+1,'figure_type':kind,'figure_name':name.replace('\x00','\ufffd'),
                'reason':'source_figure_caption_unreadable'})
            continue
        try:region=box(row.get('regionBoundary'));caption_box=box(row.get('captionBoundary'))
        except ValueError as error:
            pending.append({'page':page+1,'figure_type':kind,'figure_name':name,'reason':str(error)})
            continue
        record={'page':page+1,'figure_type':kind,'figure_name':name,'caption':caption,
            'region_bbox':region,'caption_bbox':caption_box,'coordinate_system':COORDINATES,'extractor':EXTRACTOR,
            'scope':'complete_captioned_figure_group_not_individual_embedded_image',
            'visual_review':'not_performed'}
        from app.query_understanding import identity
        record['figure_id']='source-figure-'+identity(record)[:32]
        # Ambiguity belongs to the requested caption, not every other figure
        # on the page. Keep distinct regions; collapse exact duplicate output.
        if record['figure_id'] in seen:continue
        seen.add(record['figure_id']);figures.append(record)
    result={'extractor':EXTRACTOR,'source_revision':EXTRACTOR_REVISION,'figures':figures,'pending':pending,
        'coverage':'detected_captioned_regions_not_full_document_or_visual_verification'}
    if len(json.dumps(result,ensure_ascii=False).encode('utf8'))>MAX_LAYOUT_BYTES:
        raise ValueError('source_figure_layout_byte_limit')
    return result


def renderer_key(figure):
    from app.query_understanding import identity
    if figure.get('extractor')!=EXTRACTOR or figure.get('coordinate_system')!=COORDINATES:
        raise ValueError('source_figure_layout_version_changed')
    rectangle(figure['region_bbox']);rectangle(figure['caption_bbox'])
    if figure.get('figure_id')!='source-figure-'+identity({key:value for key,value in figure.items() if key!='figure_id'})[:32]:
        raise ValueError('source_figure_identity_changed')
    return FIGURE_RENDERER+':'+identity(figure)[:32]


def match_figure(layout,*,page,label,caption_quote=''):
    if layout.get('extractor')!=EXTRACTOR:raise ValueError('source_figure_layout_version_changed')
    match=re.fullmatch(r'(Figure|Fig\.?|Table|图|表)\s*(\d+(?:\.\d+)?)(?:\([a-z]\))?',label.strip(),re.I)
    if not match:raise ValueError('source_figure_label_not_supported')
    kind='Table' if match[1].casefold() in {'table','表'} else 'Figure'
    candidates=[row for row in layout['figures'] if row['page']==page
        and row['figure_type']==kind and row['figure_name'].strip()==match[2]]
    if not candidates:
        failed=next((row for row in layout.get('pending') or [] if row['page']==page
            and row['figure_type']==kind and row['figure_name'].strip()==match[2]),None)
        raise ValueError(failed['reason'] if failed else 'source_figure_region_not_located')
    if len(candidates)>1 and caption_quote:
        def compact(value):return re.sub(r'\s+','',unicodedata.normalize('NFKC',value)).casefold()
        prefix=compact(caption_quote)[:80]
        candidates=[row for row in candidates if prefix and prefix in compact(row['caption'])]
    if len(candidates)!=1:raise ValueError('source_figure_caption_ambiguous')
    renderer_key(candidates[0])
    return candidates[0]


def extract_figure_layout(original,*,timeout):
    from app.db.source_assets import MAX_ORIGINAL_BYTES
    from app.research_figures import run_renderer
    if (not isinstance(original,bytes) or not original.startswith(b'%PDF-')
            or not 1<=len(original)<=MAX_ORIGINAL_BYTES):raise ValueError('source_figure_original_invalid')
    if not 0<timeout<=45:raise ValueError('source_figure_timeout_invalid')
    application=Path(__file__).resolve().parent.parent
    jar=application/'resources'/'pdffigures2'/'pdffigures2.jar'
    environment={key:value for key,value in os.environ.items()
        if key.upper() in {'PATH','SYSTEMROOT','WINDIR','TEMP','TMP','JAVA_HOME','LANG','LC_ALL'}}
    # Readiness is established by the real extraction, never by a startup probe.
    with tempfile.TemporaryDirectory(prefix='adrs-figure-layout-') as folder:
        workspace=Path(folder);source=workspace/'source.pdf';source.write_bytes(original)
        try:
            completed=run_renderer(['java','-Xmx512m','-XX:ActiveProcessorCount=1','-Djava.awt.headless=true',
                '-jar',str(jar),str(source),'-d',str(workspace/'layout-'),'-t','1','-q'],
                '',timeout=timeout,cwd=folder,env=environment)
        except FileNotFoundError as error:raise ValueError('source_figure_extractor_unavailable') from error
        if completed.returncode:
            reason=('source_figure_extractor_unavailable' if 'Unable to access jarfile' in completed.stderr
                else 'source_figure_extraction_failed')
            raise ValueError(reason)
        try:
            with (workspace/'layout-source.json').open('rb') as stream:raw=stream.read(MAX_LAYOUT_BYTES+1)
        except FileNotFoundError as error:raise ValueError('source_figure_layout_missing') from error
        if len(raw)>MAX_LAYOUT_BYTES:raise ValueError('source_figure_layout_byte_limit')
        return layout_from_json(json.loads(raw.decode('utf8')))


def rasterize_figures(original,figures,*,timeout):
    import base64
    from app.db.source_assets import MAX_ORIGINAL_BYTES
    from app.research_figures import run_renderer
    import sys
    if (not isinstance(original,bytes) or not original.startswith(b'%PDF-')
            or not 1<=len(original)<=MAX_ORIGINAL_BYTES):raise ValueError('source_figure_original_invalid')
    if not isinstance(figures,list) or not 1<=len(figures)<=8:raise ValueError('source_figure_batch_invalid')
    expected={row['figure_id']:renderer_key(row) for row in figures}
    descriptors={row['figure_id']:row for row in figures}
    if len(expected)!=len(figures):raise ValueError('source_figure_batch_duplicate')
    if not 0<timeout<=15:raise ValueError('source_figure_timeout_invalid')
    payload=json.dumps({'pdf':base64.b64encode(original).decode('ascii'),'figures':figures},ensure_ascii=False)
    if len(payload.encode('utf8'))>17_000_000:raise ValueError('source_figure_renderer_input_limit')
    completed=run_renderer([sys.executable,'-m','app.source_page_renderer'],payload,
        timeout=timeout,cwd=str(Path(__file__).resolve().parent.parent),env=dict(os.environ))
    if completed.returncode:raise ValueError('source_figure_render_failed')
    if len(completed.stdout)>16_100_000:raise ValueError('source_figure_result_byte_limit')
    result=json.loads(completed.stdout);rows=result.get('figures') or []
    if (result.get('renderer')!=FIGURE_RENDERER or len(rows)!=len(figures)
            or {row.get('figure_id') for row in rows}!=set(expected)
            or any(row.get('renderer')!=expected[row['figure_id']]
                or any(row.get(key)!=descriptors[row['figure_id']].get(key)
                    for key in ('page','region_bbox','caption_bbox','coordinate_system')) for row in rows)):
        raise ValueError('source_figure_render_binding_changed')
    return rows
