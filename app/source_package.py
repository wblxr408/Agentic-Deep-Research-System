"""Bounded offline package from authorized saved data; no network or models."""
from __future__ import annotations

import base64
import io
import json
import zipfile

MAX_PACKAGE_BYTES=128*1024*1024
MAX_TEXT_BYTES=24*1024*1024


def build_source_package(export_view,state,originals):
    view=export_view.get('delivery_view') or {}
    if export_view.get('status')!='completed' or not view.get('delivery_complete'):
        raise ValueError('source_package_report_not_deliverable')
    evidence=state.get('collected_evidence') or []
    if len(evidence)>256:raise ValueError('source_package_evidence_limit')
    output=io.BytesIO();total=0;text_size=0;files=[];sources=[]
    manifest={'schema_version':'adrs-source-package-v1','session_id':str(state['task_id']),
        'report_artifact_id':view.get('artifact_id'),'sources':sources,'pages':[],'files':files,
        'effects':{'network_calls':0,'model_calls':0},
        'original_page_presentation':'whole_original_pdf_page_not_segmented_figure'}
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=4) as archive:
        def write(path,data):
            nonlocal total
            if isinstance(data,str):data=data.encode('utf-8')
            total+=len(data)
            if total>MAX_PACKAGE_BYTES:raise ValueError('source_package_byte_limit')
            archive.writestr(path,data);files.append({'path':path,'bytes':len(data)})
        original_paths={}
        for row in originals:
            from uuid import UUID
            asset_id=str(UUID(str(row['asset_id'])))
            if asset_id in original_paths:continue
            path=f'originals/{asset_id}.pdf'
            write(path,row['original_bytes']);original_paths[asset_id]=path
        for index,item in enumerate(evidence,1):
            text=item.get('content') or ''
            if not isinstance(text,str):raise ValueError('source_package_text_invalid')
            text_size+=len(text.encode('utf-8'))
            if text_size>MAX_TEXT_BYTES:raise ValueError('source_package_text_byte_limit')
            path=f'text/source-{index:03d}.txt';write(path,text)
            acquisition=item.get('acquisition') or {};asset=acquisition.get('source_asset') or {}
            original=original_paths.get(asset.get('asset_id'))
            sources.append({'evidence_id':item.get('evidence_id'),'title':item.get('source_title'),
                'source_url':item.get('source_url'),'source_type':item.get('source_type'),
                'format':acquisition.get('format'),'coverage':acquisition.get('coverage'),
                'collected_at':item.get('collected_at'),'text_path':path,'original_path':original,
                'original_status':'retained' if original else 'not_retained',
                'original_reason':None if original else asset.get('reason') or 'no_original_binary_captured',
                'pages':acquisition.get('pages') or []})
        gallery=[]
        for page in (view.get('source_media') or {}).get('pages',[]):
            from uuid import UUID
            asset_id=str(UUID(page['asset_id']));number=page['page']
            if type(number) is not int or not 1<=number<=80:raise ValueError('source_package_page_invalid')
            prefix='data:image/png;base64,'
            if not page.get('png','').startswith(prefix):raise ValueError('source_package_page_invalid')
            path=f'images/{asset_id}-page-{number}.png'
            write(path,base64.b64decode(page['png'][len(prefix):],validate=True))
            manifest['pages'].append({**{key:page.get(key) for key in (
                'asset_id','page','source_url','evidence_ids','output_ids','titles','captions','proofs','width','height')},'path':path})
            title=' · '.join(page.get('titles') or [])
            title=title.replace('\\','\\\\').replace('[','\\[').replace(']','\\]').replace('\n',' ')
            gallery.append(f'![{title} · 原文第 {number} 页]({path})')
        markdown=view.get('report_markdown') or ''
        if gallery:markdown+='\n\n## 原文图示\n\n'+'\n\n'.join(gallery)+'\n'
        write('report.md',markdown)
        write('report.json',json.dumps(export_view,ensure_ascii=False,indent=2))
        # The manifest describes the archive; it is a research record, separate
        # from the normal report. Source-controlled titles never become paths.
        write('sources.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    if output.tell()>MAX_PACKAGE_BYTES:raise ValueError('source_package_byte_limit')
    return output.getvalue()
