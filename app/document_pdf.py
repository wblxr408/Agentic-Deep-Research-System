"""Bounded native PDF structure and explicitly requested local OCR."""
from __future__ import annotations

from collections import defaultdict
import csv
import io
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from app.document_structure import DocumentBuilder, MAX_CELLS, MAX_FIGURES, MAX_TABLES


def _ocr_page(page, builder, options, deadline):
    if not options.get('allow_ocr'):
        return {'status':'not_requested','words':[]}
    if not options.get('ocr_enabled'):
        return {'status':'disabled_by_server','words':[]}
    remaining=deadline-time.monotonic()
    if remaining<1:return {'status':'deadline_exhausted','words':[]}
    language=options.get('ocr_language','eng')
    if not re.fullmatch(r'[a-z]{3}(?:_[a-z]{3,4})?(?:\+[a-z]{3}(?:_[a-z]{3,4})?){0,3}',language):
        return {'status':'invalid_language_configuration','words':[]}
    if page.width<=0 or page.height<=0:return {'status':'invalid_page_geometry','words':[]}
    resolution=min(160,max(36,int(72*math.sqrt(5_000_000/(page.width*page.height)))))
    width,height=int(page.width*resolution/72),int(page.height*resolution/72)
    if width*height>5_000_000:return {'status':'pixel_limit','words':[]}
    try:
        with tempfile.TemporaryDirectory(prefix='adrs-local-ocr-') as directory:
            image=Path(directory)/'page.png';output=Path(directory)/'recognized'
            page.to_image(resolution=resolution).save(str(image),format='PNG')
            from PIL import Image
            with Image.open(image) as rendered:pixel_width,pixel_height=rendered.size
            if pixel_width*pixel_height>5_000_000:return {'status':'pixel_limit','words':[]}
            remaining=min(10,deadline-time.monotonic())
            if remaining<=0:return {'status':'deadline_exhausted','words':[]}
            completed=subprocess.run([options.get('ocr_binary') or 'tesseract',str(image),str(output),'-l',language,'tsv'],
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                timeout=remaining,check=False,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            if completed.returncode!=0:return {'status':'engine_or_language_unavailable','words':[]}
            with output.with_suffix('.tsv').open('rb') as stream:raw=stream.read(2*1024*1024+1)
            if len(raw)>2*1024*1024:return {'status':'output_limit','words':[]}
            words=[]
            word_limit=min(2000,max(1,int(options.get('max_words',2000))))
            for row in csv.DictReader(io.StringIO(raw.decode('utf-8',errors='replace')),delimiter='\t'):
                if row.get('level')!='5' or not row.get('text','').strip():continue
                if len(words)>=word_limit:break
                try:
                    left,top,w,h=(float(row[key]) for key in ('left','top','width','height'))
                    confidence=float(row['conf'])
                    if not all(math.isfinite(value) for value in (left,top,w,h,confidence)):continue
                    words.append({'text':row['text'],'bbox':[page.bbox[0]+left*page.width/pixel_width,
                        page.bbox[1]+top*page.height/pixel_height,page.bbox[0]+(left+w)*page.width/pixel_width,
                        page.bbox[1]+(top+h)*page.height/pixel_height],
                        'coordinate_accuracy':'rendered_OCR_to_page_estimate',
                        'line_key':(row['block_num'],row['par_num'],row['line_num']),
                        'recognition_confidence':confidence})
                except (ValueError,KeyError):continue
            return {'status':'recognized_requires_review' if words else 'no_words_recognized','words':words,
                'engine':'tesseract','language':language,'resolution':resolution,'truncated':len(words)>=word_limit,
                'confidence_semantics':'OCR_word_recognition_score_not_fact_or_layout_verification'}
    except FileNotFoundError:return {'status':'engine_unavailable','words':[]}
    except subprocess.TimeoutExpired:return {'status':'timeout','words':[]}
    except (OSError,ValueError,RuntimeError):return {'status':'render_or_engine_error','words':[]}


def _fallback_pdf(raw,builder):
    import pypdf
    from pypdf import PdfReader
    reader=PdfReader(io.BytesIO(raw),strict=False)
    if reader.is_encrypted:raise ValueError('encrypted_pdf')
    total=len(reader.pages);builder.engine='pypdf_native_without_layout'
    builder.engine_version=getattr(pypdf,'__version__',None)
    builder.warn('layout_tables_images_unavailable_fallback')
    for index in range(min(total,builder.max_pages)):
        if builder.size>=builder.max_chars:builder.truncated=True;break
        start=builder.size;value=reader.pages[index].extract_text() or ''
        block=builder.add(value,'paragraph',{'page':index+1,'bbox':None},extraction_method='pypdf_native')
        builder.pages.append({'number':index+1,'start':start,'end':builder.size,'has_text':bool(block),
            'ocr':{'status':'unavailable_without_layout_renderer'},'layout':'unavailable'})
    builder.truncated|=total>builder.max_pages
    return builder.finish(total_pages=total,retained_pages=sum(page['has_text'] for page in builder.pages),
        coverage='partial_text' if builder.truncated or any(not page['has_text'] for page in builder.pages) else 'full_text')


def parse_pdf(raw, *, max_chars=160000,max_pages=80,options=None):
    if not raw.startswith(b'%PDF-'):raise ValueError('invalid_pdf_signature')
    builder=DocumentBuilder('pdf',max_chars=max_chars,max_pages=max_pages);options=options or {}
    try:import pdfplumber
    except ImportError:return _fallback_pdf(raw,builder)
    from pdfminer.pdfdocument import PDFPasswordIncorrect
    deadline=time.monotonic()+min(25,max(1,float(options.get('timeout_seconds',15))))
    ocr_pages=0;ocr_words=0;structure_truncated=False
    try:opened=pdfplumber.open(io.BytesIO(raw))
    except PDFPasswordIncorrect:raise ValueError('encrypted_pdf') from None
    with opened as document:
        import pypdf
        from pypdf import PdfReader
        text_document=PdfReader(io.BytesIO(raw),strict=False)
        total=len(document.pages);builder.engine='pypdf_text_with_pdfplumber_layout'
        builder.engine_version=f"pypdf:{getattr(pypdf,'__version__','unknown')};pdfplumber:{getattr(pdfplumber,'__version__','unknown')}"
        for index,page in enumerate(document.pages[:max_pages]):
            if time.monotonic()>=deadline or builder.size>=max_chars:
                builder.truncated=True;builder.warn('parser_deadline_or_character_limit');break
            start=builder.size;before=len(builder.blocks);native=page.extract_words(expand_ligatures=False)
            lines=defaultdict(list)
            # Coordinates from native words; line grouping is a stated heuristic.
            for word in native[:30000]:lines[round(float(word['top'])/3)*3].append(word)
            if len(native)>30000:builder.truncated=True;builder.warn('page_word_limit')
            # A horizontal line can cross both columns. Keep the PDF's native
            # text stream instead of concatenating unrelated left/right lines.
            # Layout assets retain their own coordinates; this page transcript
            # has no fabricated character bounding boxes or verified order.
            native_text=text_document.pages[index].extract_text() or ''
            if native_text:
                builder.add(native_text,'paragraph',{'page':index+1,'bbox':None},
                    extraction_method='pypdf_native_text_stream',reading_order='PDF_text_stream_not_semantically_verified')
            elif native:
                for top,words in sorted(lines.items()):
                    words=sorted(words,key=lambda word:word['x0'])
                    builder.add(' '.join(word['text'] for word in words),'paragraph',{'page':index+1,'bbox':None},
                        extraction_method='native_word_fallback',reading_order='coordinate_heuristic_not_verified')
            ocr={'status':'native_text_available'}
            if not native:
                if ocr_pages>=int(options.get('max_ocr_pages',8)) or ocr_words>=8000:
                    ocr={'status':'ocr_page_limit'}
                else:
                    ocr=_ocr_page(page,builder,{**options,'max_words':min(2000,8000-ocr_words)},deadline)
                    if options.get('allow_ocr') and options.get('ocr_enabled'):ocr_pages+=1
                    ocr_lines=defaultdict(list)
                    for word in ocr.pop('words',[]):ocr_lines[word['line_key']].append(word);ocr_words+=1
                    for words in ocr_lines.values():
                        box=[min(word['bbox'][0] for word in words),min(word['bbox'][1] for word in words),
                            max(word['bbox'][2] for word in words),max(word['bbox'][3] for word in words)]
                        builder.add(' '.join(word['text'] for word in words),'ocr_text',{'page':index+1,'bbox':box},
                            extraction_method='local_tesseract',recognition_words=words)
                    if ocr.get('truncated'):builder.truncated=True
                builder.warn('ocr_requires_review' if ocr.get('status')=='recognized_requires_review' else 'native_text_missing')
            table_status='not_attempted_without_native_text'
            if native and time.monotonic()<deadline and len(builder.tables)<MAX_TABLES:
                try:
                    found=page.find_tables();table_status='line_grid_candidates_not_semantic_verification'
                    for table in found[:min(8,MAX_TABLES-len(builder.tables))]:
                        values=table.extract();cells=[]
                        for row_index,row in enumerate(table.rows):
                            for column,box in enumerate(row.cells):
                                if len(cells)>=MAX_CELLS:break
                                value=values[row_index][column] if row_index<len(values) and column<len(values[row_index]) else None
                                cells.append({'row':row_index,'column':column,'text':value,
                                    'row_span':None,'column_span':None,'source_locator':{'bbox':list(box) if box else None},
                                    'cell_status':'extracted' if box else 'missing_or_merged_cell_unknown_span'})
                        builder.table(cells,{'page':index+1,'bbox':list(table.bbox)},semantics='native_line_grid_candidate_spans_unknown')
                    if len(found)>8:
                        builder.warn('page_table_limit');structure_truncated=True
                except (ValueError,TypeError,IndexError):table_status='table_extraction_failed';builder.warn(table_status)
            for image in page.images[:min(20,MAX_FIGURES-len(builder.figures))]:
                builder.figure({'page':index+1,'bbox':[image['x0'],image['top'],image['x1'],image['bottom']]},
                    source_name=image.get('name'),embedded_image_present=True,image_bytes_retained=False,
                    pixel_size=image.get('srcsize'),caption_status='unlinked_requires_review')
            if native and len(builder.tables)>=MAX_TABLES:structure_truncated=True
            if len(page.images)>20:
                builder.warn('page_figure_limit');structure_truncated=True
            page_blocks=builder.blocks[before:]
            for block in page_blocks:
                text=block['raw_text']
                if re.match(r'\s*(?:fig(?:ure)?\.?|table|图|表)\s*\d+',text,re.I):block['kind']='caption_candidate'
            captions=[block for block in page_blocks if block['kind']=='caption_candidate'][:50]
            for figure in builder.figures[-20:]:
                if figure['source_locator'].get('page')!=index+1:continue
                box=figure['source_locator']['bbox'];candidates=[]
                for block in captions:
                    caption_box=block['source_locator'].get('bbox')
                    if not caption_box:continue
                    distance=min(abs(caption_box[1]-box[3]),abs(box[1]-caption_box[3]))
                    if distance<=80 and min(box[2],caption_box[2])>=max(box[0],caption_box[0]):
                        candidates.append((distance,block['block_id']))
                figure['caption_candidate_block_ids']=[identity for _,identity in sorted(candidates)[:3]]
                if candidates:figure['caption_status']='same_page_proximity_candidates_not_confirmed_identity'
            builder.pages.append({'number':index+1,'start':start,'end':builder.size,
                'has_text':len(builder.blocks)>before,'width':page.width,'height':page.height,
                'coordinate_system':'PDF_points_top_left','ocr':ocr,'table_status':table_status})
            page.close()
        builder.truncated|=total>max_pages
        return builder.finish(total_pages=total,retained_pages=sum(page['has_text'] for page in builder.pages),
            structure_truncated=structure_truncated,
            coverage_semantics='retained_native_text_not_complete_tables_images_or_verified_reading_order',
            coverage='partial_text' if builder.truncated or any(not page['has_text'] for page in builder.pages) else 'full_text')
