"""Content-free, bounded report layouts and local sample format readers."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from io import BytesIO
from typing import Annotated, Literal
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

from pydantic import Field, StringConstraints, model_validator
from app.research_scope import ScopeRecord

VERSION = 'adrs-report-layout-v1'
MAX_SAMPLE_BYTES = 2 * 1024 * 1024
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


def parse_layout_sample(raw: bytes, format: str, progress=None):
    if not raw or len(raw) > MAX_SAMPLE_BYTES:
        raise ValueError('layout_sample_size_limit')
    if format in {'html', 'htm'}:
        result = _parse_html(raw, progress)
    elif format == 'docx':
        result = _parse_docx(raw, progress)
    else:
        raise ValueError('layout_format_not_supported')
    if progress:
        progress('preview')
    return result
