"""Annotate already acquired HTML against retained text; do not follow assets."""
from __future__ import annotations

from html.parser import HTMLParser
import re
import time
from urllib.parse import urljoin,urlsplit

from app.document_structure import VERSION,MAX_CELLS,MAX_TABLES,MAX_FIGURES


def annotate_html(raw_html,retained_text,source_url):
    def location(value):
        value=' '.join(value.split())
        if not value or len(value)>12000:return {'start':None,'end':None,'status':'empty_or_overlong_fragment'}
        pattern=r'\s+'.join(re.escape(word) for word in value.split())
        matches=[]
        for match in re.finditer(pattern,retained_text):
            matches.append((match.start(),match.end()))
            if len(matches)>2:break
        return {'start':matches[0][0] if len(matches)==1 else None,'end':matches[0][1] if len(matches)==1 else None,
            'status':'unique_literal_retained_text_match' if len(matches)==1 else 'ambiguous_match' if matches else 'fragment_not_retained'}
    class Structure(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.tables=[];self.figures=[];self.blocks=[];self.warnings=[];self.table=None;self.cell=None
            self.row=-1;self.column=0;self.occupied=set();self.capture=None;self.buffer=[];self.skip=0
            self.figure_stack=[];self.figure_count=0;self.cells=0
            self.table_depth=0;self.deadline=time.monotonic()+5
        def warn(self,reason):
            if reason not in self.warnings:self.warnings.append(reason)
        def handle_starttag(self,tag,attrs):
            if time.monotonic()>self.deadline:raise TimeoutError('html_annotation_time_limit')
            values=dict(attrs)
            if tag in {'script','style','nav','footer','header','noscript','iframe'}:self.skip+=1;return
            if self.skip:return
            if tag=='table':
                self.table_depth+=1
                if self.table_depth>1:self.warn('nested_table_not_flattened');return
            if self.table_depth>1:return
            if tag=='img' and len(self.figures)>=MAX_FIGURES:self.warn('html_figure_limit')
            if tag=='table' and len(self.tables)>=MAX_TABLES:self.warn('html_table_limit')
            if tag=='figure':self.figure_count+=1;self.figure_stack.append(self.figure_count)
            if tag=='img' and len(self.figures)<MAX_FIGURES:
                pointer_truncated=len(values.get('src',''))>2000
                raw=values.get('src','')[:2000];resolved=urljoin(source_url,raw)
                try:public=resolved if urlsplit(resolved).scheme in {'http','https'} else None
                except ValueError:public=None
                if pointer_truncated:public=None
                self.figures.append({'figure_id':f'figure:{len(self.figures)+1}','source_url':public,
                    'source_src':raw,'source_alt':values.get('alt','')[:2000],
                    'alt_status':'source_supplied_not_verified_description',
                    'figure_container':self.figure_stack[-1] if self.figure_stack else None,
                    'source_locator':{'html_line':self.getpos()[0],'html_column':self.getpos()[1]},
                    'image_bytes_retained':False,'resource_followed':False,'image_understanding':'not_performed'})
                self.figures[-1]['pointer_truncated']=pointer_truncated
            if tag=='table' and self.table is None and len(self.tables)<MAX_TABLES:
                self.table={'table_id':f'table:{len(self.tables)+1}','cells':[],
                    'source_locator':{'html_line':self.getpos()[0]},'semantics':'explicit_DOM_spans_not_verified_values'}
                self.row=-1;self.column=0;self.occupied=set()
            elif tag=='tr' and self.table is not None:self.row+=1;self.column=0
            elif tag in {'td','th'} and self.table is not None and self.cells<MAX_CELLS:
                span_valid=True
                while (self.row,self.column) in self.occupied:self.column+=1
                try:
                    row_span,column_span=int(values.get('rowspan','1')),int(values.get('colspan','1'))
                    if not 1<=row_span<=100 or not 1<=column_span<=100:raise ValueError()
                except ValueError:
                    row_span=column_span=1;span_valid=False;self.warn('invalid_table_span_not_trusted')
                self.cell={'row':self.row if self.row>=0 else None,'column':self.column,'row_span':row_span if span_valid else None,'column_span':column_span if span_valid else None,
                    'header':tag=='th','source_locator':{'html_line':self.getpos()[0],'html_column':self.getpos()[1]},'parts':[]}
                for row in range(self.row,self.row+row_span):
                    for column in range(self.column,self.column+column_span):self.occupied.add((row,column))
                self.column+=column_span
            if tag in {'h1','h2','h3','h4','h5','h6','p','figcaption','pre'} and self.capture is None and self.cell is None:
                self.capture=(tag,self.getpos(),self.figure_stack[-1] if self.figure_stack else None);self.buffer=[]
        def handle_endtag(self,tag):
            if tag in {'script','style','nav','footer','header','noscript','iframe'}:
                self.skip=max(0,self.skip-1);return
            if self.skip:return
            if tag=='table':
                self.table_depth=max(0,self.table_depth-1)
                if self.table_depth:return
            elif self.table_depth>1:return
            if tag in {'td','th'} and self.cell is not None:
                text=' '.join(''.join(self.cell.pop('parts')).split())
                self.cell.update({'text':text,'retained_location':location(text)})
                self.table['cells'].append(self.cell);self.cells+=1;self.cell=None
            if tag=='table' and self.table is not None:
                self.tables.append(self.table);self.table=None
            if self.capture is not None and self.capture[0]==tag:
                captured,pos,container=self.capture;text=' '.join(''.join(self.buffer).split())
                if text and len(self.blocks)<2000:
                    self.blocks.append({'block_id':f'html-block:{len(self.blocks)+1}',
                        'kind':'caption' if captured=='figcaption' else 'heading' if captured.startswith('h') else 'code' if captured=='pre' else 'paragraph',
                        'heading_level':int(captured[1]) if re.fullmatch(r'h[1-6]',captured) else None,
                        'text':text[:12000],'retained_location':location(text),
                        'source_locator':{'html_line':pos[0],'html_column':pos[1]},'figure_container':container})
                elif text:self.warn('html_block_limit')
                self.capture=None;self.buffer=[]
            if tag=='figure' and self.figure_stack:self.figure_stack.pop()
        def handle_data(self,data):
            if time.monotonic()>self.deadline:raise TimeoutError('html_annotation_time_limit')
            if self.skip:return
            if self.table_depth>1:return
            if self.cell is not None:
                remaining=max(0,12000-sum(map(len,self.cell['parts'])))
                if remaining:self.cell['parts'].append(data[:remaining])
                if len(data)>remaining:self.cell['text_truncated']=True;self.warn('html_fragment_limit')
            elif self.capture is not None:
                remaining=max(0,12000-sum(map(len,self.buffer)))
                if remaining:self.buffer.append(data[:remaining])
                if len(data)>remaining:self.warn('html_fragment_limit')
    parser=Structure()
    try:parser.feed(raw_html)
    except (TimeoutError,ValueError):parser.warn('html_annotations_partial')
    for figure in parser.figures:
        figure['caption_block_ids']=[block['block_id'] for block in parser.blocks
            if block['kind']=='caption' and block['figure_container'] is not None and block['figure_container']==figure['figure_container']]
    if parser.cells>=MAX_CELLS:parser.warn('html_table_cell_limit')
    return {'schema_version':VERSION,'format':'html','parser_engine':'retained_page_with_DOM_annotations',
        'blocks':parser.blocks,'tables':parser.tables,'figures':parser.figures,'offset_unit':'existing_retained_text_character',
        'truncated':bool(parser.warnings),
        'quality':{'status':'annotations_not_independent_review','warnings':list(dict.fromkeys(parser.warnings)),
            'human_review':'not_reviewed','semantic_confidence':None},
        'locator_note':'HTML positions refer to source DOM; retained offsets only present for unique literal matches. Raw HTML bytes not archived here.',
        'deduplication':{'automatic_content_removal':False,'semantic_deduplication':'not_enabled'}}
