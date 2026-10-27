"""Bounded local rendering of a user-selected page or embedded image."""
from __future__ import annotations

import base64
import io
import json
import math
import os
from pathlib import Path
import posixpath
import sys
import zipfile
from contextlib import redirect_stderr,redirect_stdout

MAX_PIXELS=4_000_000
MAX_OUTPUT_BYTES=1_400_000
MAX_PACKAGE_BYTES=64*1024*1024


def _jpeg(image,detail):
    from PIL import Image,ImageOps
    if image.width<=0 or image.height<=0 or image.width*image.height>MAX_PIXELS:
        raise ValueError('visual_image_pixel_limit')
    image=ImageOps.exif_transpose(image)
    if image.mode not in ('RGB','L'):
        rgba=image.convert('RGBA');background=Image.new('RGBA',rgba.size,'white')
        image=Image.alpha_composite(background,rgba).convert('RGB')
    else:image=image.convert('RGB')
    side=1800 if detail=='high' else 768
    image.thumbnail((side,side))
    for quality in (82,68,52):
        output=io.BytesIO();image.save(output,format='JPEG',quality=quality,optimize=True)
        value=output.getvalue()
        if len(value)<=MAX_OUTPUT_BYTES:return {'data':base64.b64encode(value).decode('ascii'),
            'media_type':'image/jpeg','width':image.width,'height':image.height,'bytes':len(value)}
    raise ValueError('visual_image_size_limit')


def _render_pdf(path,page_number,detail):
    import pdfplumber
    if page_number<1:raise ValueError('visual_page_invalid')
    with pdfplumber.open(path) as pdf:
        if page_number>len(pdf.pages):raise ValueError('visual_page_not_found')
        page=pdf.pages[page_number-1]
        if page.width<=0 or page.height<=0:raise ValueError('visual_page_geometry_invalid')
        resolution=min(140,max(36,int(72*math.sqrt((MAX_PIXELS-10000)/(page.width*page.height)))))
        if int(page.width*resolution/72)*int(page.height*resolution/72)>MAX_PIXELS:
            raise ValueError('visual_image_pixel_limit')
        rendered=page.to_image(resolution=resolution).original
        result=_jpeg(rendered,detail)
        result.update(target={'kind':'page','page':page_number},resolution=resolution)
        return result


def _render_docx(path,target,figure_id,detail):
    from PIL import Image
    member=target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join('word',target))
    if not member.startswith('word/media/') or '..' in member.split('/'):
        raise ValueError('visual_embedded_image_unavailable')
    with zipfile.ZipFile(path) as archive:
        entries=archive.infolist()
        if len(entries)>10000 or sum(item.file_size for item in entries)>MAX_PACKAGE_BYTES:
            raise ValueError('visual_document_expansion_limit')
        info=archive.getinfo(member)
        if info.file_size>12*1024*1024:raise ValueError('visual_image_size_limit')
        raw=archive.read(info)
    with Image.open(io.BytesIO(raw)) as image:
        if image.format not in {'JPEG','PNG','GIF','WEBP','BMP','TIFF'}:
            raise ValueError('visual_embedded_image_format_unsupported')
        if image.width*image.height>MAX_PIXELS:raise ValueError('visual_image_pixel_limit')
        image.load();result=_jpeg(image,detail)
    result.update(target={'kind':'figure','figure_id':figure_id})
    return result


if __name__=='__main__':
    with open(os.devnull,'w') as sink,redirect_stdout(sink),redirect_stderr(sink):
        try:
            path=Path(sys.argv[1]);selection=json.loads(sys.argv[2])
            detail=selection.get('detail','low')
            if detail not in {'low','high'}:raise ValueError('visual_detail_invalid')
            result=(_render_pdf(path,int(selection['page']),detail) if selection['kind']=='page'
                else _render_docx(path,selection['target'],selection['figure_id'],detail))
            payload={'ok':True,'result':result}
        except Exception as error:
            code=str(error)
            payload={'ok':False,'error':code if isinstance(error,ValueError) and code.startswith('visual_') else 'visual_render_failed'}
    print(json.dumps(payload,ensure_ascii=True))
