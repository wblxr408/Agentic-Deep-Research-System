"""Application-owned PDF page renderer; no paths, URLs or executable plans."""
from __future__ import annotations

import base64
import io
import json
import math
import sys
from contextlib import redirect_stdout


def render(payload):
    import pdfplumber
    raw=base64.b64decode(payload['pdf'],validate=True)
    pages=payload['pages']
    if not raw.startswith(b'%PDF-') or not 1<=len(raw)<=12*1024*1024:raise ValueError('original_size_or_format')
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
