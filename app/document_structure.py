"""Deterministic retained document structure; no model or external I/O."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import re
import zipfile
import io
import posixpath
import sys
from xml.etree import ElementTree as ET

VERSION = 'adrs-document-structure-v1'
MAX_BLOCKS = 6000
MAX_TABLES = 40
MAX_FIGURES = 200
MAX_CELLS = 2000


def normalize_text(raw, limit):
    """Piecewise character map, including CRLF contraction and visible errors."""
    pieces, mapping, raw_end, size = [], [], 0, 0
    for match in re.finditer(r'\r\n?|[\x00-\x08\x0b\x0c\x0e-\x1f]', raw):
        for start, end, replacement, kind in ((raw_end, match.start(), None, 'identity'),
                (match.start(), match.end(), '\n' if match.group().startswith('\r') else '\ufffd', 'line_endings' if match.group().startswith('\r') else 'visible_control_replacement')):
            value = raw[start:end] if replacement is None else replacement
            retained = value[:max(0, limit-size)]
            if retained:
                pieces.append(retained)
                mapping.append({'start':size,'end':size+len(retained),'raw_start':start,
                    'raw_end':start+len(retained) if kind=='identity' else end,'transform':kind})
                size += len(retained)
            if len(retained)<len(value):return ''.join(pieces),mapping,start+len(retained),True
        raw_end=match.end()
        if size>=limit:return ''.join(pieces),mapping,raw_end,raw_end<len(raw)
    retained=raw[raw_end:raw_end+max(0,limit-size)]
    if retained:
        pieces.append(retained);mapping.append({'start':size,'end':size+len(retained),
            'raw_start':raw_end,'raw_end':raw_end+len(retained),'transform':'identity'})
    return ''.join(pieces),mapping,raw_end+len(retained),raw_end+len(retained)<len(raw)


class DocumentBuilder:
    def __init__(self, format, *, max_chars=160000, max_pages=80):
        self.format=format;self.max_chars=max_chars;self.max_pages=max_pages
        self.parts=[];self.size=0;self.blocks=[];self.tables=[];self.figures=[];self.pages=[]
        self.warnings=[];self.truncated=False;self.cell_count=0;self.engine='native_rules'
        self.engine_version='python:'+'.'.join(map(str,sys.version_info[:3]))

    def warn(self, reason):
        if reason not in self.warnings:self.warnings.append(reason)

    def add(self, raw, kind, locator, **metadata):
        if not raw:return None
        if len(self.blocks)>=MAX_BLOCKS:
            self.truncated=True;self.warn('block_limit');return None
        separator='\n\n' if self.parts else ''
        remaining=self.max_chars-self.size-len(separator)
        if remaining<=0:self.truncated=True;return None
        text,mapping,raw_end,truncated=normalize_text(raw,remaining)
        if not text:return None
        self.parts.append(separator+text);start=self.size+len(separator);self.size+=len(separator)+len(text)
        block={'block_id':f'block:{len(self.blocks)+1}','kind':kind,'start':start,'end':self.size,
            'source_locator':locator,'raw_text':raw[:raw_end],'normalization_map':mapping,
            'raw_text_truncated':truncated,**metadata}
        if '\x00' in block['raw_text']:
            # PostgreSQL JSONB rejects U+0000 even in a valid JSON string.
            # Keep a visible one-character projection and lossless original;
            # source offsets still address the decoded original code points.
            import base64
            block['raw_text_original_utf8_base64']=base64.b64encode(block['raw_text'].encode('utf-8')).decode('ascii')
            block['raw_text']=block['raw_text'].replace('\x00','\ufffd')
            block['raw_text_encoding']='visible_NUL_replacement_with_lossless_original_utf8_base64'
        self.blocks.append(block);self.truncated|=truncated
        return block

    def table(self, cells, locator, *, semantics='explicit_cells', truncated=False):
        if len(self.tables)>=MAX_TABLES:self.warn('table_limit');self.truncated=True;return None
        table_id=f'table:{len(self.tables)+1}';retained=[]
        for cell in cells:
            if self.cell_count>=MAX_CELLS:self.warn('table_cell_limit');truncated=True;break
            text=cell.get('text')
            block=self.add(text,'table_cell',{**locator,**cell.get('source_locator',{}),
                'row':cell['row'],'column':cell['column']},table_id=table_id) if text else None
            if text and not block:truncated=True;break
            retained.append({**cell,'text':self.parts[-1][-((block['end']-block['start'])):] if block else text,
                'block_id':block['block_id'] if block else None,'start':block['start'] if block else None,
                'end':block['end'] if block else None})
            self.cell_count+=1
        table={'table_id':table_id,'cells':retained,'source_locator':locator,'semantics':semantics,
            'truncated':truncated,'interpretation_status':'structure_extracted_values_not_verified'}
        self.tables.append(table)
        if truncated:self.warn('table_partial');self.truncated=True
        return table

    def figure(self, locator, **details):
        if len(self.figures)>=MAX_FIGURES:self.warn('figure_limit');return None
        figure={'figure_id':f'figure:{len(self.figures)+1}','source_locator':locator,
            'image_understanding':'not_performed','description_status':'source_pointer_not_generated_description',**details}
        self.figures.append(figure);return figure

    def finish(self, **extra):
        text=''.join(self.parts);groups=defaultdict(list)
        for block in self.blocks:
            value=text[block['start']:block['end']]
            if len(value.strip())>=25:
                groups[hashlib.sha256(value.encode('utf-8')).hexdigest()].append(block['block_id'])
        exact=[{'block_ids':ids,'status':'same_retained_text_distinct_locations_preserved'} for ids in groups.values() if len(ids)>1]
        # Lexical candidates only, bounded independently of total document size.
        candidates=[];seen=[];comparisons=0
        for block in self.blocks[:250]:
            value=text[block['start']:block['end']]
            if len(value)<80 or block['kind'] in {'code','table_cell'}:continue
            compact=re.sub(r'\s+',' ',value).casefold()
            grams={compact[index:index+5] for index in range(0,min(len(compact)-4,2000),3)}
            for prior_id,prior,prior_grams in seen[-25:]:
                if comparisons>=2000:break
                comparisons+=1
                if compact==prior:continue
                union=grams|prior_grams
                similarity=len(grams&prior_grams)/len(union) if union else 0
                if similarity>=0.85 and len(candidates)<40:
                    candidates.append({'block_ids':[prior_id,block['block_id']],'lexical_shingle_jaccard':round(similarity,4),
                        'status':'possible_near_duplicate_requires_review','automatically_removed':False})
            seen.append((block['block_id'],compact,grams))
        empty=[page['number'] for page in self.pages if not page.get('has_text')]
        replacements=text.count('\ufffd')
        if replacements:self.warn('replacement_characters_require_review')
        if empty:self.warn('pages_without_retained_text')
        result={'schema_version':VERSION,'format':self.format,'text':text,'blocks':self.blocks,'pages':self.pages,
            'tables':self.tables,'figures':self.figures,'truncated':self.truncated,'parser_engine':self.engine,'parser_engine_version':self.engine_version,
            'offset_unit':'normalized_retained_text_character','normalization_version':'crlf_and_visible_controls_v1',
            'quality':{'status':'needs_review' if self.warnings or self.truncated else 'extracted_not_reviewed',
                'warnings':self.warnings,'retained_characters':len(text),'replacement_characters':replacements,
                'replacement_ratio':replacements/max(1,len(text)),'pages_without_text':empty,
                'semantic_confidence':None,'human_review':'not_reviewed'},
            'deduplication':{'exact_groups':exact,'near_candidates':candidates,'semantic_deduplication':'not_enabled_no_validated_semantic_merge_rule',
                'candidate_comparisons':comparisons,'near_scope':'first_250_blocks_previous_25_at_most_2000_comparisons_40_candidates',
                'automatic_content_removal':False},**extra}
        return result


def parse_text(raw, *, format='txt', max_chars=160000):
    builder=DocumentBuilder(format,max_chars=max_chars)
    try:text=raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        text=raw.decode('utf-8-sig',errors='replace');builder.warn('invalid_utf8_replaced_not_ignored')
    if format=='json':
        data=json.loads(text);count=0
        def walk(value,pointer='',depth=0):
            nonlocal count
            count+=1
            if depth>40 or count>6000:builder.truncated=True;builder.warn('json_structure_limit');return
            if isinstance(value,dict):
                for key,item in value.items():walk(item,pointer+'/'+str(key).replace('~','~0').replace('/','~1'),depth+1)
            elif isinstance(value,list):
                for index,item in enumerate(value):walk(item,pointer+'/'+str(index),depth+1)
            else:builder.add(str(value) if isinstance(value,str) else json.dumps(value,ensure_ascii=False),'json_value',{'json_pointer':pointer})
        walk(data)
        result=builder.finish();result['original_serialized_text']=text[:max_chars]
        result['original_serialized_text_truncated']=len(text)>max_chars
        return result
    fenced=False;position=0
    for piece in re.split(r'(\n\s*\n)',text):
        if not piece:continue
        start=position;position+=len(piece)
        if not piece.strip():continue
        kind='paragraph';level=None
        if format=='md':
            if piece.lstrip().startswith(('```','~~~')):
                if len(re.findall(r'(?m)^\s*(?:```|~~~)',piece))%2:fenced=not fenced
                kind='code'
            elif fenced:kind='code'
            elif re.match(r'#{1,6}\s',piece):kind='heading';level=len(piece)-len(piece.lstrip('#'))
            lines=piece.splitlines(keepends=True)
            if kind!='code' and len(lines)>=2 and '|' in lines[0] and re.fullmatch(r'\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*',lines[1]):
                cells=[];offset=start
                for row,line in enumerate(lines):
                    if row==1:offset+=len(line);continue
                    cursor=0;values=re.split(r'(?<!\\)\|',line.rstrip('\r\n'))
                    for column,value in enumerate(values):
                        at=line.find(value,cursor);cursor=max(cursor,at+len(value)+1)
                        if (column==0 or column==len(values)-1) and not value.strip():continue
                        cells.append({'row':0 if row==0 else row-1,'column':column-(1 if line.lstrip().startswith('|') else 0),
                            'text':value,'row_span':1,'column_span':1,'header':row==0,
                            'source_locator':{'decoded_text_start':offset+max(0,at),'decoded_text_end':offset+max(0,at)+len(value)}})
                    offset+=len(line)
                builder.table(cells,{'decoded_text_start':start,'decoded_text_end':position},semantics='markdown_pipe_grid_escaped_pipes_not_split')
                continue
            if kind!='code':
                for match in re.finditer(r'!\[([^\]\n]*)\]\(([^)\n]+)\)',piece):
                    builder.figure({'decoded_text_start':start+match.start(),'decoded_text_end':start+match.end()},
                        source_alt=match.group(1),source_target=match.group(2),image_bytes_retained=False,
                        external_resource_followed=False,alt_status='source_supplied_unverified_description')
        builder.add(piece,kind,{'decoded_text_start':start,'decoded_text_end':position},heading_level=level)
    result=builder.finish()
    result['original_serialized_text']=text[:max_chars]
    result['original_serialized_text_truncated']=len(text)>max_chars
    return result


def parse_docx(raw, *, max_chars=160000):
    if not raw.startswith(b'PK\x03\x04'):raise ValueError('invalid_docx_signature')
    builder=DocumentBuilder('docx',max_chars=max_chars);builder.engine='bounded_ooxml'
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
        'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
        'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
    w=lambda name:'{'+ns['w']+'}'+name
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries=archive.infolist()
        if len(entries)>10000 or sum(item.file_size for item in entries)>64*1024*1024:
            raise ValueError('docx_expansion_limit')
        info=archive.getinfo('word/document.xml')
        if info.file_size>24*1024*1024:raise ValueError('docx_xml_limit')
        root=ET.fromstring(archive.read(info));body=root.find('w:body',ns)
        if body is None:raise ValueError('invalid_docx_body')
        relationships={}
        if 'word/_rels/document.xml.rels' in archive.namelist():
            rels=ET.fromstring(archive.read('word/_rels/document.xml.rels'))
            relationships={node.attrib.get('Id'):dict(node.attrib) for node in rels}
        names=set(archive.namelist())
        def figures(node,locator,block=None):
            doc_properties=[dict(item.attrib) for item in node.iter() if item.tag.endswith('}docPr')]
            for blip in node.findall('.//a:blip',ns):
                relation_id=blip.get('{'+ns['r']+'}embed') or blip.get('{'+ns['r']+'}link')
                relation=relationships.get(relation_id,{})
                target=relation.get('Target','')
                member=target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join('word',target))
                builder.figure(locator,relationship_id=relation_id,source_target=target,
                    target_mode=relation.get('TargetMode','Internal'),associated_block_id=block['block_id'] if block else None,
                    embedded_image_present=relation.get('TargetMode')!='External' and member in names,
                    source_image_properties=doc_properties[:20],image_bytes_retained=False,external_resource_followed=False)
        def paragraph_text(node):
            return ''.join(child.text or '' if child.tag==w('t') else '\t' if child.tag==w('tab') else '\n'
                for child in node.iter() if child.tag in {w('t'),w('tab'),w('br'),w('cr')})
        for index,node in enumerate(body):
            locator={'part':'word/document.xml','body_child_index':index}
            if node.tag==w('p'):
                style=node.find('w:pPr/w:pStyle',ns);value=style.get(w('val'),'') if style is not None else ''
                heading=re.fullmatch(r'Heading([1-9])',value,re.I)
                caption=value.casefold() in {'caption','题注'}
                block=builder.add(paragraph_text(node),'heading' if heading else 'caption_candidate' if caption else 'paragraph',locator,
                    heading_level=int(heading.group(1)) if heading else None,style_name=value)
                if caption and block:
                    for figure in builder.figures[-20:]:
                        if figure['source_locator'].get('body_child_index')==index-1:
                            figure['caption_candidate_block_id']=block['block_id']
                            figure['caption_status']='adjacent_XML_caption_style_candidate_requires_review'
                figures(node,locator,block)
            elif node.tag==w('tbl'):
                cells=[];previous={}
                for row_index,row in enumerate(node.findall('w:tr',ns)):
                    before=row.find('w:trPr/w:gridBefore',ns);column=int(before.get(w('val'),'0')) if before is not None else 0
                    if not 0<=column<=1000:raise ValueError('invalid_docx_table_span')
                    active={};continued_ids=set()
                    for cell_index,cell in enumerate(row.findall('w:tc',ns)):
                        span=cell.find('w:tcPr/w:gridSpan',ns);width=int(span.get(w('val'),'1')) if span is not None else 1
                        if width<1 or width>1000:raise ValueError('invalid_docx_table_span')
                        merge=cell.find('w:tcPr/w:vMerge',ns)
                        continued=merge is not None and merge.get(w('val'))!='restart'
                        if continued and column in previous:
                            original=previous[column]
                            if id(original) not in continued_ids:original['row_span']+=1;continued_ids.add(id(original))
                            for slot in range(column,column+width):active[slot]=original
                        else:
                            item={'row':row_index,'column':column,'row_span':1,'column_span':width,
                                'text':'\n'.join(paragraph_text(p) for p in cell.findall('w:p',ns)),
                                'source_locator':{'xml_row':row_index,'xml_cell':cell_index}}
                            cells.append(item)
                            if merge is not None:
                                for slot in range(column,column+width):active[slot]=item
                            if continued:builder.warn('docx_unmatched_vertical_merge')
                        column+=width
                        if len(cells)>=MAX_CELLS:builder.warn('docx_table_cell_limit');builder.truncated=True;break
                    previous=active
                    if len(cells)>=MAX_CELLS:break
                builder.table(cells,locator,semantics='explicit_ooxml_gridSpan_and_vMerge')
                figures(node,locator)
            elif node.tag!=w('sectPr'):builder.warn('docx_unparsed_body_element:'+node.tag.rsplit('}',1)[-1])
            if builder.size>=max_chars:builder.truncated=True;break
    return builder.finish()
