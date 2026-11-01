"""Fixed ReportLab layout; source text is escaped, images are retained PNGs."""
from __future__ import annotations

import base64
import io
import xml.etree.ElementTree as ET
import json
import re
import sys
from contextlib import redirect_stdout
from html import escape
from urllib.parse import urlsplit


def inline(text):
    value=escape(re.sub(r'\\([\\`*_{}\[\]()#+\-.!|>])',r'\1',str(text)))
    superscripts=str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾','0123456789+-=()')
    value=re.sub(r'[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾]+',
        lambda match:'<super>'+match[0].translate(superscripts)+'</super>',value)
    value=re.sub(r'\*\*([^*]+)\*\*',r'<b>\1</b>',value)
    value=re.sub(r'`([^`]+)`',r'<font name="Courier">\1</font>',value)
    def link(match):
        url=match[2]
        return f'<a href="{url}">{match[1]}</a>' if urlsplit(url).scheme in {'https','http'} else match[1]
    value=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',link,value)
    return re.sub(r'\[(?:citation:)?(\d+)\]',r'<a href="#source-\1">[\1]</a>',value)


def prose(markdown):
    blocks=[];paragraph=[];rows=[]
    def flush():
        if paragraph:blocks.append('<p>'+inline(' '.join(paragraph))+'</p>');paragraph.clear()
        if rows:
            blocks.append('<table>'+''.join('<tr>'+''.join('<td>'+inline(cell)+'</td>' for cell in row)+'</tr>' for row in rows)+'</table>')
            rows.clear()
    for line in markdown.splitlines():
        if re.match(r'^\s*\[(?:citation:)?\d+\]:\s*<?https?://',line):
            flush();continue
        heading=re.match(r'^(#{1,4})\s+(.+)',line)
        if not line.strip():flush()
        elif heading:
            flush();level=min(len(heading[1]),3)
            blocks.append(f'<h{level}>'+inline(heading[2])+f'</h{level}>')
        elif line.startswith('|'):
            if paragraph:flush()
            if not re.fullmatch(r'[| :\-]+',line):rows.append([cell.strip() for cell in line.strip('|').split('|')])
        else:
            if rows:flush()
            paragraph.append(line)
    flush()
    return ''.join(blocks)


def render(payload):
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Image, LongTable, TableStyle, PageBreak, CondPageBreak
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    pdfmetrics.registerFontFamily('STSong-Light',normal='STSong-Light',bold='STSong-Light',
        italic='STSong-Light',boldItalic='STSong-Light')
    if payload.get('part') not in {'main','appendix'}:raise ValueError('pdf_part_invalid')
    body=prose(payload['markdown'])
    if payload['part']=='appendix' and not payload['markdown'].strip():raise ValueError('pdf_appendix_empty')
    # The prose appendix already owns technical detail. Do not print the same
    # full matrix a second time. Retained original figures keep their reviewed
    # captions and explanations; page layout is deterministic, not model-made.
    images={}
    figure_refs=set()
    if payload['part']=='main':
        comparison=next((chart for chart in payload.get('charts',[])
            if chart.get('chart_id')=='technical_comparison' and chart.get('rows')),None)
        if comparison:
            # The main report uses the reviewed problem/mechanism columns;
            # experimental conditions remain in the technical appendix.
            table='<h3>代表成果的问题与机制</h3><table><tr><td>成果</td><td>问题</td><td>机制</td></tr>'
            for row in comparison['rows']:
                cells=[]
                for index,value in enumerate(row['values'][:3]):
                    refs=(row.get('cell_citation_ids') or {}).get(str(index),[])
                    numbers=[str(ref).replace('citation:','') for ref in refs]
                    figure_refs.update(int(n) for n in numbers if n.isdigit())
                    cells.append('<td>'+inline(str(value)+' '+' '.join('['+n+']' for n in numbers))+'</td>')
                table+='<tr>'+''.join(cells)+'</tr>'
            table+='</table>'
            from app.organization_purpose import MODULES
            heading='<h2>'+inline(MODULES['deep_dive'][0])+'</h2>'
            body=body.replace(heading,heading+table,1) if heading in body else body+table
        networks=[chart for chart in payload.get('charts',[]) if chart.get('kind')=='network'
            and chart.get('nodes') and len(chart['nodes'])<=24 and len(chart.get('edges',[]))<=60]
        if networks:
            from app.figure_renderer import render as render_figures
            rendered=render_figures({'charts':networks,'plan':{'figures':[
                {'chart_id':chart['chart_id'],'kind':'network','width':10,'height':5,
                    'dpi':160,'palette':'colorblind'} for chart in networks]}})
            for index,asset in enumerate(rendered['assets']):
                name=f'relations-{index}.png'
                images[name]=base64.b64decode(asset['png'].split(',',1)[1],validate=True)
                chart=networks[index]
                body+='<h2>'+inline(chart['title'])+'</h2>'
                body+=f'<img src="{name}" width="470" height="235"/>'
                body+='<p>'+inline(' '.join(asset['notes']))+'</p>'
                refs=[str(ref).replace('citation:','') for ref in chart.get('citation_ids',[])]
                figure_refs.update(int(ref) for ref in refs if ref.isdigit())
                body+='<p>'+inline(' '.join('['+ref+']' for ref in refs))+'</p>'
    explanation_anchors={}
    for index,page in enumerate(payload.get('original_pages',[])):
        body+='<pagebreak/>'
        data=page.get('png','')
        if not data.startswith('data:image/png;base64,'):raise ValueError('pdf_original_image_missing')
        raw=base64.b64decode(data.split(',',1)[1],validate=True)
        if len(raw)>1_500_000:raise ValueError('pdf_image_limit')
        name=f'original-{index}.png';images[name]=raw
        width=min(470,490*page['width']/page['height']);height=width*page['height']/page['width']
        body+='<h2>'+inline(' / '.join(page.get('titles',[])))+' · 原文第 '+str(page['page'])+' 页</h2>'
        explanation=page.get('explanation') or ''
        explanation_key=((page.get('report_anchor') or {}).get('paragraph_id'),explanation)
        if explanation_key in explanation_anchors:
            body+='<p>关联说明：<a href="#'+explanation_anchors[explanation_key]+'">查看同组说明</a></p>'
        else:
            anchor=f'original-explanation-{index}'
            explanation_anchors[explanation_key]=anchor
            body+='<p id="'+anchor+'">'+inline(explanation)+'</p>'
        body+=f'<img src="{name}" width="{width}" height="{height}"/>'
        # The retained whole page already contains its literal caption. Do
        # not duplicate long extraction windows as another caption paragraph.
        source_url=page.get('source_url') or ''
        if urlsplit(source_url).scheme in {'http','https'}:
            body+='<p><a href="'+escape(source_url,quote=True)+'">原始论文</a></p>'
    references=[]
    used={int(number) for number in re.findall(r'\[(?:citation:)?(\d+)\]',payload['markdown'])}|figure_refs
    page_evidence={key for page in payload.get('original_pages',[]) for key in page.get('evidence_ids',[])}
    for source in payload.get('sources',[]):
        number=str(source.get('citation_id','')).replace('citation:','')
        if not number.isdigit():continue
        if int(number) not in used and (source.get('locator') or {}).get('evidence_id') not in page_evidence:continue
        url=source.get('source_url') or ''
        label=source.get('title') or source.get('source_title') or url
        source_link=('<a href="'+escape(url,quote=True)+'">'+escape(url)+'</a>'
            if urlsplit(url).scheme in {'http','https'} else '')
        references.append(f'<p id="source-{number}">[{number}] '+
            (source_link if label==url and source_link else inline(label)+(' · '+source_link if source_link else ''))+'</p>')
    body+='<h2>来源</h2>'+''.join(references)
    styles={
        'p':ParagraphStyle('body',fontName='STSong-Light',fontSize=10.5,leading=16.3,
            spaceAfter=9,wordWrap='CJK',textColor=colors.HexColor('#20313d')),
        'h1':ParagraphStyle('title',fontName='STSong-Light',fontSize=22,leading=29,
            spaceAfter=18,wordWrap='CJK',textColor=colors.HexColor('#153e4a'),keepWithNext=True),
        'h2':ParagraphStyle('section',fontName='STSong-Light',fontSize=15,leading=22,
            spaceBefore=18,spaceAfter=9,wordWrap='CJK',textColor=colors.HexColor('#17636b'),keepWithNext=True),
        'h3':ParagraphStyle('subsection',fontName='STSong-Light',fontSize=12,leading=18,
            spaceBefore=12,spaceAfter=7,wordWrap='CJK',keepWithNext=True),
    }
    def inner(element):
        value=ET.tostring(element,encoding='unicode')
        return value[value.index('>')+1:value.rindex('<')]
    flow=[]
    for element in ET.fromstring('<root>'+body+'</root>'):
        if element.tag in styles:
            anchor='<a name="'+escape(element.attrib['id'],quote=True)+'"/>' if element.get('id') else ''
            paragraph=Paragraph(anchor+inner(element),styles[element.tag])
            if str(element.get('id','')).startswith('source-'):paragraph.keepWithNext=True
            flow.append(paragraph)
        elif element.tag=='img':
            flow.append(Image(io.BytesIO(images[element.attrib['src']]),
                width=float(element.attrib['width']),height=float(element.attrib['height'])))
        elif element.tag=='pagebreak':
            flow.append(PageBreak())
        elif element.tag=='table':
            rows=[[Paragraph(inner(cell),styles['p']) for cell in row] for row in element]
            table=LongTable(rows,colWidths=[(A4[0]-84)/max(map(len,rows))]*max(map(len,rows)),repeatRows=1)
            table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),
                ('GRID',(0,0),(-1,-1),.4,colors.HexColor('#bccbd0')),
                ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf3f2'))]))
            # Keep headings with the first table row, not the entire multipage
            # table. A keepWithNext chain otherwise wastes almost a whole page.
            headings=[]
            while flow and isinstance(flow[-1],Paragraph) and flow[-1].style.name in {'title','section','subsection'}:
                heading=flow.pop();heading.keepWithNext=False;headings.insert(0,heading)
            if headings:
                table.wrap(A4[0]-84,A4[1]-89)
                needed=sum(table._rowHeights[:2])+sum(
                    heading.wrap(A4[0]-96,A4[1])[1]+heading.getSpaceBefore()+heading.getSpaceAfter()
                    for heading in headings)+12
                flow.extend([CondPageBreak(needed),*headings])
            flow.append(table)
    def footer(canvas,document):
        if document.page>160:raise ValueError('pdf_page_limit')
        canvas.saveState();canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#63737c'))
        canvas.drawRightString(A4[0]-42,23,str(document.page));canvas.restoreState()
    output=io.BytesIO()
    document=SimpleDocTemplate(output,pagesize=A4,leftMargin=42,rightMargin=42,topMargin=45,bottomMargin=44,
        title=payload['title']+(' · 技术附录' if payload['part']=='appendix' else ''),author='ADRS')
    document.build(flow,onFirstPage=footer,onLaterPages=footer)
    output=output.getvalue()
    return {'pdf':base64.b64encode(output).decode('ascii')}


if __name__=='__main__':
    raw=sys.stdin.buffer.read(24_000_001)
    if len(raw)>24_000_000:raise ValueError('pdf_input_limit')
    with redirect_stdout(sys.stderr):result=render(json.loads(raw.decode('utf8')))
    sys.stdout.write(json.dumps(result,separators=(',',':')))
