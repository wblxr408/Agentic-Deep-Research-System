"""Content-free, bounded report layouts and local sample format readers."""
from __future__ import annotations

import re
import math
from collections import Counter
from html.parser import HTMLParser
from io import BytesIO
from statistics import median
from typing import Annotated, Literal
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from pydantic import Field, StringConstraints, model_validator
from app.research_scope import ScopeRecord

VERSION = 'adrs-report-layout-v1'
MAX_SAMPLE_BYTES = 2 * 1024 * 1024
MAX_PDF_SAMPLE_BYTES = 10 * 1024 * 1024


def sample_byte_limit(format: str) -> int:
    return MAX_PDF_SAMPLE_BYTES if format == 'pdf' else MAX_SAMPLE_BYTES
SectionId = Annotated[str, StringConstraints(pattern=r'^section-[1-9][0-9]{0,2}$')]
BlockId = Annotated[str, StringConstraints(pattern=r'^block-[1-9][0-9]{0,3}$')]
Color = Annotated[str, StringConstraints(pattern=r'^#[0-9a-f]{6}$')]
Role = Literal['overview', 'findings', 'evolution', 'comparison', 'relationships', 'recommendations', 'references', 'general']
Interaction = Literal['contents', 'expand', 'sort', 'filter', 'tooltip', 'tabs']


class LayoutTokens(ScopeRecord):
    background: Color = '#f8fafb'
    foreground: Color = '#183039'
    accent: Color = '#36867c'
    font: Literal['serif', 'sans', 'mono'] = 'sans'
    title_px: int = Field(default=56, ge=24, le=96)
    body_px: int = Field(default=16, ge=14, le=24)
    spacing: int = Field(default=24, ge=8, le=48)
    width: Literal['standard', 'wide'] = 'standard'


class LayoutBlock(ScopeRecord):
    block_id: BlockId
    kind: Literal['text', 'heading', 'list', 'metric', 'chart', 'table', 'image', 'callout'] = 'text'
    level: Literal[3, 4, 5, 6] | None = None
    binding: Literal['auto', 'narrative', 'statistics', 'relationships', 'technical_comparison', 'sources'] = 'auto'
    chart_kind: Literal['auto', 'none', 'line', 'bar', 'network', 'timeline', 'table'] = 'auto'
    span: int = Field(default=12, ge=4, le=12)
    aspect: Literal['auto', 'wide', 'square', 'portrait'] = 'auto'
    missing: Literal['omit', 'text', 'require_data'] = 'text'


class LayoutSection(ScopeRecord):
    section_id: SectionId
    role: Role = 'general'
    level: int = Field(default=2, ge=1, le=6)
    columns: int = Field(default=1, ge=1, le=3)
    blocks: tuple[LayoutBlock, ...] = Field(default=(), max_length=32)


class ReportLayout(ScopeRecord):
    schema_version: Literal['adrs-report-layout-v1'] = VERSION
    tokens: LayoutTokens = Field(default_factory=LayoutTokens)
    density: Literal['compact', 'standard', 'spacious'] = 'standard'
    running_header: bool = False
    running_footer: bool = False
    interactions: tuple[Interaction, ...] = Field(default=('contents',), max_length=6)
    sections: tuple[LayoutSection, ...] = Field(min_length=1, max_length=24)

    @model_validator(mode='after')
    def bounded_structure(self):
        sections = [s.section_id for s in self.sections]
        blocks = [b.block_id for s in self.sections for b in s.blocks]
        if len(set(sections)) != len(sections) or len(set(blocks)) != len(blocks):
            raise ValueError('layout_duplicate_slot')
        if len(blocks) > 96 or sum(b.kind in {'chart', 'image'} for s in self.sections for b in s.blocks) > 12:
            raise ValueError('layout_component_limit')
        if len(set(self.interactions)) != len(self.interactions):
            raise ValueError('layout_duplicate_interaction')
        return self


class _Builder:
    def __init__(self):
        self.sections = []
        self.locations = {}
        self.count = 0
        self.interactions = {'contents'}

    def section(self, level=2, columns=1, position=None):
        if len(self.sections) >= 24:
            raise ValueError('layout_section_limit')
        item = {'section_id': f'section-{len(self.sections)+1}', 'role': 'overview' if level == 1 else 'general',
                'level': level, 'columns': columns, 'blocks': []}
        self.sections.append(item)
        self.locations[item['section_id']] = position or {}

    def block(self, kind, position=None, columns=1, **options):
        if not self.sections:
            self.section(columns=columns)
        self.count += 1
        if self.count > 96 or len(self.sections[-1]['blocks']) >= 32:
            raise ValueError('layout_component_limit')
        item = {'block_id': f'block-{self.count}', 'kind': kind, 'span': 12 // columns, **options}
        self.sections[-1]['blocks'].append(item)
        self.locations[item['block_id']] = position or {}

    def result(self, tokens=None, format='html', differences=(), **options):
        if not self.sections:
            raise ValueError('layout_structure_not_found')
        layout = ReportLayout.model_validate({'tokens': tokens or {}, 'sections': self.sections,
            'interactions': sorted(self.interactions), 'density': 'compact' if self.count > 30 else 'standard', **options})
        return {'layout': layout.model_dump(mode='json'), 'parse': {'format': format,
            'parser_version': VERSION, 'model_calls': 0, 'locations': self.locations,
            'differences': list(differences), 'source_content_retained_in_layout': False}}


class _HTMLStructure(HTMLParser):
    """Retains element geometry only. Body strings are never put in the tree."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = {'tag': 'root', 'attrs': {}, 'children': [], 'position': {}}
        self.stack = [self.root]
        self.css = ''
        self.nodes = 0

    def handle_starttag(self, tag, attrs):
        self.nodes += 1
        if self.nodes > 20000 or len(self.stack) > 64:
            raise ValueError('layout_document_complexity_limit')
        values = {k: (v or '')[:2048] for k, v in attrs if k in {'style', 'class', 'id', 'role', 'hidden', 'aria-hidden', 'data-chart-kind'}}
        line, column = self.getpos()
        node = {'tag': tag, 'attrs': values, 'children': [], 'position': {'line': line, 'column': column}, 'has_text': False}
        self.stack[-1]['children'].append(node)
        if tag not in {'img', 'input', 'br', 'hr', 'meta', 'link', 'source', 'wbr', 'area', 'base', 'embed'}:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i]['tag'] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.stack[-1]['tag'] == 'style':
            if len(self.css) + len(data) > 256000:
                raise ValueError('layout_style_limit')
            self.css += data
        elif data.strip():
            self.stack[-1]['has_text'] = True


def _declarations(value):
    allowed = {'background', 'background-color', 'color', 'font-family', 'font-size', 'gap', 'display', 'visibility', 'grid-template-columns'}
    return {key.strip().lower(): val.strip().lower() for chunk in value.split(';') if ':' in chunk
            for key, val in [chunk.split(':', 1)] if key.strip().lower() in allowed and len(val) < 200}


def _color(value):
    if re.fullmatch(r'#[0-9a-f]{3}', value or ''):
        return '#' + ''.join(c*2 for c in value[1:])
    return value if re.fullmatch(r'#[0-9a-f]{6}', value or '') else None


def _parse_html(raw, progress=None):
    if progress:
        progress('reading')
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError as error:
        raise ValueError('layout_requires_utf8') from error
    parser = _HTMLStructure()
    parser.feed(text)
    if progress:
        progress('cleaning')
    builder, rules, tokens = _Builder(), [], {}
    differences = set()
    for selectors, body in re.findall(r'([^{}]{1,200})\{([^{}]{0,3000})\}', parser.css):
        for selector in selectors.split(','):
            selector = selector.strip()
            if re.fullmatch(r'[a-zA-Z][a-zA-Z0-9-]*|[.#][a-zA-Z_][\w-]*|\*', selector):
                rules.append((selector, _declarations(body)))
                if len(rules) > 512:
                    raise ValueError('layout_style_complexity_limit')
            else:
                differences.add('complex_css_requires_adjustment')

    def style(node):
        result = {}
        attrs = node['attrs']
        for selector, declarations in rules:
            if selector in {'*', node['tag'], '#' + attrs.get('id', '')} or selector.startswith('.') and selector[1:] in attrs.get('class', '').split():
                result.update(declarations)
        result.update(_declarations(attrs.get('style', '')))
        return result

    def walk(node, columns=1):
        tag, attrs, position = node['tag'], node['attrs'], node['position']
        values = style(node)
        if tag == 'script':
            differences.add('source_scripts_not_used')
        if tag in {'img', 'svg', 'canvas', 'iframe', 'object', 'embed'}:
            differences.add('external_assets_omitted')
        if tag in {'script', 'style', 'head', 'iframe', 'object', 'embed', 'form', 'noscript', 'template'} or 'hidden' in attrs or attrs.get('aria-hidden') == 'true' or values.get('display') == 'none' or values.get('visibility') == 'hidden':
            return
        if tag in {'body', 'html'}:
            for css, token in [('background-color', 'background'), ('background', 'background'), ('color', 'foreground')]:
                color = _color(values.get(css))
                if color:
                    tokens[token] = color
            family = values.get('font-family', '')
            if family:
                tokens['font'] = 'mono' if 'mono' in family else 'sans' if 'sans' in family else 'serif'
        grid = values.get('grid-template-columns', '')
        repeat = re.match(r'repeat\(\s*([123])\s*,', grid)
        if grid:
            columns = int(repeat[1]) if repeat else min(3, max(1, len(grid.split())))
        if re.fullmatch(r'h[1-6]', tag):
            level = int(tag[1])
            if level <= 2:
                builder.section(level, columns, position)
            else:
                builder.block('heading', position, columns, level=level)
            size = re.fullmatch(r'(\d{1,2})px', values.get('font-size', ''))
            if tag == 'h1' and size:
                tokens['title_px'] = max(24, min(96, int(size[1])))
            return
        if tag == 'nav':
            return
        if attrs.get('role') == 'tablist':
            builder.interactions.add('tabs')
        classes = set(re.split(r'[\s_-]+', attrs.get('class', '').lower()))
        if tag in {'div', 'figure'} and classes & {'chart', 'diagram', 'graph', 'network'}:
            builder.block('chart', position, columns, chart_kind='network' if 'network' in classes else 'auto')
            return
        if tag == 'div' and classes & {'metric', 'stat', 'kpi'}:
            builder.block('metric', position, columns)
            return
        if tag == 'table':
            builder.block('table', position, columns)
            builder.interactions.update({'sort', 'filter'})
            return
        if tag in {'div', 'span'} and not node['children'] and node.get('has_text'):
            builder.block('text', position, columns)
            return
        if tag in {'img', 'svg', 'canvas'}:
            kind = attrs.get('data-chart-kind')
            builder.block('chart' if kind in {'line', 'bar', 'network', 'timeline', 'table'} else 'image', position, columns, chart_kind=kind if kind in {'line', 'bar', 'network', 'timeline', 'table'} else 'auto')
            return
        if tag in {'p', 'blockquote', 'ul', 'ol', 'details'}:
            builder.block({'p': 'text', 'blockquote': 'callout', 'ul': 'list', 'ol': 'list', 'details': 'callout'}[tag], position, columns)
            if tag == 'details':
                builder.interactions.add('expand')
            return
        for child in node['children']:
            walk(child, columns)

    walk(parser.root)
    return builder.result(tokens, differences=sorted(differences))


def _parse_docx(raw, progress=None):
    if progress:
        progress('reading')
    builder = _Builder()
    tokens, differences = {}, set()
    namespace = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    try:
        with ZipFile(BytesIO(raw)) as archive:
            infos = archive.infolist()
            if len(infos) > 2048 or sum(i.file_size for i in infos) > 16 * 1024 * 1024:
                raise ValueError('layout_docx_expansion_limit')
            data = archive.read('word/document.xml')
            styles = archive.read('word/styles.xml') if 'word/styles.xml' in archive.namelist() else b''
        if len(data) > 8 * 1024 * 1024 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
            raise ValueError('layout_docx_xml_limit')
        root = ET.fromstring(data)
        body = root.find(namespace + 'body')
        if body is None:
            raise ValueError('layout_structure_not_found')
        if progress:
            progress('cleaning')
        if styles:
            if len(styles) > 2 * 1024 * 1024 or b'<!DOCTYPE' in styles.upper() or b'<!ENTITY' in styles.upper():
                raise ValueError('layout_docx_xml_limit')
            style_root = ET.fromstring(styles)
            for item in style_root.findall('.//' + namespace + 'style'):
                name = item.get(namespace + 'styleId', '').lower()
                if name not in {'normal', 'heading1'}:
                    continue
                props = item.find(namespace + 'rPr')
                if props is None:
                    continue
                size, color, font = (props.find(namespace + key) for key in ('sz', 'color', 'rFonts'))
                if size is not None and (value := size.get(namespace + 'val', '')).isdigit():
                    tokens['title_px' if name == 'heading1' else 'body_px'] = max(24 if name == 'heading1' else 14, min(96 if name == 'heading1' else 24, round(int(value[:5]) * 2 / 3)))
                if color is not None and (value := _color('#' + color.get(namespace + 'val', '').lower())):
                    tokens['accent' if name == 'heading1' else 'foreground'] = value
                if font is not None and name == 'normal':
                    value = font.get(namespace + 'ascii', '').lower()
                    tokens['font'] = 'mono' if any(k in value for k in ('courier', 'consolas', 'mono')) else 'serif' if any(k in value for k in ('times', 'georgia', '宋')) else 'sans'
        section = body.find('.//' + namespace + 'sectPr')
        columns_node = section.find(namespace + 'cols') if section is not None else None
        number = columns_node.get(namespace + 'num', '1') if columns_node is not None else '1'
        columns = min(3, max(1, int(number[:3]))) if number.isdigit() else 1
        for index, node in enumerate(body):
            if index > 20000:
                raise ValueError('layout_document_complexity_limit')
            position = {'element': index}
            if node.tag == namespace + 'tbl':
                builder.block('table', position, columns)
                builder.interactions.update({'sort', 'filter'})
            elif node.tag == namespace + 'p':
                style = node.find('.//' + namespace + 'pStyle')
                heading = re.fullmatch(r'(?:heading|标题)\s*([1-6])', (style.get(namespace + 'val', '') if style is not None else '').lower())
                if heading:
                    level = int(heading[1])
                    if level <= 2:
                        builder.section(level, columns, position)
                    else:
                        builder.block('heading', position, columns, level=level)
                elif node.find('.//' + namespace + 'drawing') is not None:
                    builder.block('image', position, columns)
                    differences.update({'source_images_omitted', 'floating_objects_require_adjustment'})
                else:
                    builder.block('list' if node.find('.//' + namespace + 'numPr') is not None else 'text', position, columns)
    except (BadZipFile, KeyError, ET.ParseError, RuntimeError, NotImplementedError) as error:
        raise ValueError('layout_invalid_docx') from error
    return builder.result(tokens, format='docx', differences=sorted(differences),
        running_header=section is not None and section.find(namespace + 'headerReference') is not None,
        running_footer=section is not None and section.find(namespace + 'footerReference') is not None)


def _pdf_color(value):
    """Map only numeric PDF color components to a permitted six-digit token."""
    if isinstance(value,(int,float)) and not isinstance(value,bool):value=(value,value,value)
    if not isinstance(value,(tuple,list)) or len(value)!=3:return None
    try:components=[float(part) for part in value]
    except (TypeError,ValueError):return None
    if any(not math.isfinite(part) or part<0 or part>1 for part in components):return None
    return '#'+''.join(f'{round(part*255):02x}' for part in components)


def _pdf_luminance(color):
    parts=[int(color[index:index+2],16)/255 for index in (1,3,5)]
    return sum(weight*(part/12.92 if part<=.04045 else ((part+.055)/1.055)**2.4)
        for weight,part in zip((.2126,.7152,.0722),parts))


def _parse_pdf(raw, progress=None):
    """Create editable layout slots from page geometry, never from PDF words."""
    if not raw.startswith(b'%PDF-'):raise ValueError('layout_invalid_pdf')
    if progress:progress('reading')
    import pdfplumber
    from pdfminer.pdfdocument import PDFPasswordIncorrect
    builder=_Builder();tokens={};differences={'source_images_omitted','pdf_geometry_is_approximate'}
    figure_count=0;meaningful=False;body_sizes=[];heading_sizes=[];colors=[];fonts=[]
    try:
        with pdfplumber.open(BytesIO(raw)) as document:
            if len(document.pages)>24:differences.add('pdf_pages_limited')
            if progress:progress('cleaning')
            for index,page in enumerate(document.pages[:24]):
                width,height=float(page.width),float(page.height)
                if not math.isfinite(width) or not math.isfinite(height) or width<=0 or height<=0:
                    raise ValueError('layout_invalid_pdf')
                chars=page.chars
                if len(chars)>30000:differences.add('pdf_detail_limited')
                glyphs=[]
                for char in chars[:30000]:
                    # Glyph text is used only to ignore whitespace and is never
                    # copied to a result, location, diagnostic, or model input.
                    if not str(char.get('text') or '').strip():continue
                    try:
                        x0,x1,top,size=(float(char.get(key,0)) for key in ('x0','x1','top','size'))
                    except (TypeError,ValueError):continue
                    if not all(math.isfinite(value) for value in (x0,x1,top,size)) or size<=0:continue
                    glyphs.append((top,x0,x1,size,char.get('non_stroking_color'),str(char.get('fontname') or '')))
                buckets={}
                for glyph in glyphs:buckets.setdefault(round(glyph[0]/3),[]).append(glyph)
                lines=[]
                for bucket in sorted(buckets):
                    current=[]
                    for glyph in sorted(buckets[bucket],key=lambda item:item[1]):
                        if current and glyph[1]-current[-1][2]>max(24,current[-1][3]*2.5):
                            lines.append(current);current=[]
                        current.append(glyph)
                    if current:lines.append(current)
                lines.sort(key=lambda line:(line[0][0],line[0][1]))
                base=median([glyph[3] for glyph in glyphs]) if glyphs else 12
                headings=[line for line in lines if line[0][0]<height*.3
                    and median([glyph[3] for glyph in line])>=max(base*1.3,base+3)]
                heading_ids={id(line) for line in headings}
                body=[line for line in lines if id(line) not in heading_ids]
                body_sizes.extend(glyph[3] for line in body for glyph in line)
                heading_sizes.extend(glyph[3] for line in headings for glyph in line)
                colors.extend(color for glyph in glyphs if (color:=_pdf_color(glyph[4])))
                fonts.extend(glyph[5].lower() for glyph in glyphs)
                left=[line for line in body if max(glyph[2] for glyph in line)<=width*.52]
                right=[line for line in body if min(glyph[1] for glyph in line)>=width*.48]
                columns=2 if len(left)>=3 and len(right)>=3 else 1
                builder.section(level=1 if index==0 else 2,columns=columns,position={'page':index+1})
                slots=[]
                if body:
                    meaningful=True
                    groups=[left,right] if columns==2 else [body]
                    for number,group in enumerate(groups):
                        if group:slots.append((min(line[0][0] for line in group),'text',{'page':index+1,'element':number},{}))
                elif headings:
                    meaningful=True
                images=[]
                for image in page.images[:100]:
                    try:iw=float(image['x1'])-float(image['x0']);ih=float(image['bottom'])-float(image['top'])
                    except (KeyError,TypeError,ValueError):continue
                    if all(math.isfinite(value) for value in (iw,ih)) and iw>0 and ih>0 and iw*ih>=width*height*.03:
                        images.append((iw*ih,float(image['top']),iw,ih))
                if len(page.images)>100:differences.add('pdf_detail_limited')
                if not glyphs:differences.add('pdf_page_without_text')
                if page.curves or page.lines:differences.add('pdf_vector_graphics_require_adjustment')
                if images:
                    meaningful=True
                    if figure_count<12:
                        _,top,iw,ih=max(images)
                        aspect='wide' if iw/ih>=1.4 else 'portrait' if ih/iw>=1.4 else 'square'
                        slots.append((top,'image',{'page':index+1,'element':len(slots)},{'aspect':aspect}))
                        figure_count+=1
                    else:differences.add('pdf_images_limited')
                    if len(images)>1:differences.add('pdf_multiple_images_require_adjustment')
                elif not glyphs and (page.curves or page.lines or page.rects):
                    meaningful=True
                    differences.add('pdf_vector_graphics_require_adjustment')
                    if figure_count<12:
                        slots.append((0,'image',{'page':index+1,'element':0},{'aspect':'auto'}));figure_count+=1
                    else:differences.add('pdf_images_limited')
                for _,kind,position,options in sorted(slots,key=lambda item:item[0]):
                    builder.block(kind,position,columns,**options)
                if index==0:
                    if width>height:tokens['width']='wide'
                    backgrounds=[]
                    for rect in page.rects[:10000]:
                        try:area=float(rect['width'])*float(rect['height'])
                        except (KeyError,TypeError,ValueError):continue
                        color=_pdf_color(rect.get('non_stroking_color'))
                        if color and area>=width*height*.85:backgrounds.append((area,color))
                    if backgrounds:tokens['background']=max(backgrounds)[1]
                page.close()
        if not meaningful:raise ValueError('layout_structure_not_found')
        if body_sizes:tokens['body_px']=max(14,min(24,round(median(body_sizes)*4/3)))
        if heading_sizes:tokens['title_px']=max(24,min(96,round(median(heading_sizes)*4/3)))
        background=tokens.get('background','#f8fafb')
        foreground=Counter(colors).most_common(1)[0][0] if colors else '#183039'
        light,dark=sorted((_pdf_luminance(background),_pdf_luminance(foreground)),reverse=True)
        if (light+.05)/(dark+.05)<2.5:
            foreground='#f8fafb' if _pdf_luminance(background)<.2 else '#183039'
        tokens['foreground']=foreground
        if fonts:
            family=Counter(fonts).most_common(1)[0][0]
            tokens['font']='mono' if any(part in family for part in ('mono','courier','consolas')) else (
                'serif' if any(part in family for part in ('serif','times','songti','mincho')) and 'sans' not in family else 'sans')
        return builder.result(tokens,format='pdf',differences=sorted(differences))
    except PDFPasswordIncorrect:
        raise ValueError('layout_pdf_encrypted') from None
    except ValueError as error:
        if str(error).startswith('layout_'):raise
        raise ValueError('layout_invalid_pdf') from None
    except Exception:
        raise ValueError('layout_invalid_pdf') from None


def parse_layout_sample(raw: bytes, format: str, progress=None):
    if not raw or len(raw) > sample_byte_limit(format):
        raise ValueError('layout_sample_size_limit')
    if format in {'html', 'htm'}:
        result = _parse_html(raw, progress)
    elif format == 'docx':
        result = _parse_docx(raw, progress)
    elif format == 'pdf':
        result = _parse_pdf(raw, progress)
    else:
        raise ValueError('layout_format_not_supported')
    if progress:
        progress('preview')
    return result
