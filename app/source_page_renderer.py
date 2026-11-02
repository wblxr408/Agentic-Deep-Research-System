"""Application-owned PDF page renderer; no paths, URLs or executable plans."""
from __future__ import annotations

import base64
import io
import json
import math
import sys
from contextlib import redirect_stdout


def figure_crops(document,requests):
    from app.source_figure_extraction import EXTRACTOR,FIGURE_RENDERER,COORDINATES,rectangle,renderer_key
    if not isinstance(requests,list) or not 1<=len(requests)<=8:raise ValueError('source_figure_batch_invalid')
    result=[];seen=set()
    for request in requests:
        if not isinstance(request,dict) or request.get('extractor')!=EXTRACTOR or request.get('coordinate_system')!=COORDINATES:
            raise ValueError('source_figure_layout_version_changed')
        number=request.get('page');figure_id=request.get('figure_id')
        if type(number) is not int or not 1<=number<=80 or number>len(document.pages):
            raise ValueError('source_figure_page_invalid')
        if not isinstance(figure_id,str) or not figure_id.startswith('source-figure-') or figure_id in seen:
            raise ValueError('source_figure_identity_invalid')
        seen.add(figure_id);page=document.pages[number-1]
        if page.rotation%360:raise ValueError('source_figure_rotation_not_supported')
        cropbox=tuple(page.cropbox or page.bbox);x0,top,x1,bottom=cropbox
        if not all(math.isfinite(v) for v in cropbox) or not x0<x1 or not top<bottom:
            raise ValueError('source_figure_page_geometry_invalid')
        region=rectangle(request['region_bbox']);caption=rectangle(request['caption_bbox'])
        if any(box[2]>x1-x0 or box[3]>bottom-top for box in (region,caption)):
            raise ValueError('source_figure_region_outside_cropbox')
        left,y,right,end=region
        area=(right-left)*(end-y)
        if left<=.5 and y<=.5 and right>=x1-x0-.5 and end>=bottom-top-.5:
            raise ValueError('source_figure_region_is_page')
        bounds=(x0+left,top+y,x0+right,top+end)
        # Rasterize the complete region, including vector/text objects. Taking
        # a PDF embedded bitmap alone can omit axes, legends and other panels.
        cropped=page.crop(bounds,strict=True)
        scale=min(180/72,1900/max(cropped.width,cropped.height),math.sqrt(1_900_000/area))
        image=cropped.to_image(resolution=72*scale).original
        if image.width>2000 or image.height>2000 or image.width*image.height>2_000_000:
            raise ValueError('source_figure_pixel_limit')
        out=io.BytesIO();image.save(out,format='PNG',optimize=True);png=out.getvalue()
        if len(png)>1_500_000:raise ValueError('source_figure_byte_limit')
        result.append({'figure_id':figure_id,'page':number,'renderer':renderer_key(request),
            'region_bbox':region,'caption_bbox':caption,'page_cropbox':list(cropbox),'page_rotation':page.rotation,
            'coordinate_system':COORDINATES,'width':image.width,'height':image.height,
            'png':base64.b64encode(png).decode('ascii')})
        page.close()
    return {'renderer':FIGURE_RENDERER,'figures':result}


def render(payload):
    import pdfplumber
    raw=base64.b64decode(payload['pdf'],validate=True)
    pages=payload.get('pages')
    if not raw.startswith(b'%PDF-') or not 1<=len(raw)<=12*1024*1024:raise ValueError('original_size_or_format')
    if 'figures' in payload:
        if pages is not None:raise ValueError('source_figure_selection_conflict')
        with pdfplumber.open(io.BytesIO(raw)) as document:return figure_crops(document,payload['figures'])
    if (not isinstance(pages,list) or not 1<=len(pages)<=8
            or any(type(page) is not int or not 1<=page<=80 for page in pages)
            or len(set(pages))!=len(pages)):raise ValueError('page_selection_invalid')
    result=[]
    with pdfplumber.open(io.BytesIO(raw)) as document:
        for number in pages:
            if number>len(document.pages):raise ValueError('original_page_not_found')
            page=document.pages[number-1]
            width,height=page.width,page.height
            if not all(math.isfinite(value) and 0<value<=20000 for value in (width,height)):
                raise ValueError('original_page_geometry_invalid')
            scale=min(110/72,1900/max(width,height),math.sqrt(1_900_000/(width*height)))
            image=page.to_image(resolution=72*scale).original
            if image.width>2000 or image.height>2000 or image.width*image.height>2_000_000:
                raise ValueError('page_pixel_limit')
            out=io.BytesIO();image.save(out,format='PNG',optimize=True)
            png=out.getvalue()
            if len(png)>1_500_000:raise ValueError('page_byte_limit')
            result.append({'page':number,'width':image.width,'height':image.height,
                'png':base64.b64encode(png).decode('ascii')})
    return {'renderer':'adrs-original-pdf-page-v1','pages':result}


if __name__=='__main__':
    raw=sys.stdin.buffer.read(17_000_001)
    if len(raw)>17_000_000:raise ValueError('renderer_input_limit')
    # A PDF/library diagnostic cannot corrupt the JSON result channel.
    with redirect_stdout(sys.stderr):result=render(json.loads(raw.decode('utf-8')))
    sys.stdout.write(json.dumps(result,separators=(',',':')))
