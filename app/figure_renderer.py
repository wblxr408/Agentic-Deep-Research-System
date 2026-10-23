"""Trusted headless child. Reads bounded JSON; never executes Skill/model code."""
from __future__ import annotations

import base64
import io
import json
import math
import re
import sys
import textwrap

import matplotlib
matplotlib.use('Agg')
from matplotlib import font_manager
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

VERSION='matplotlib-declarative-v1'


def label(value,limit=180):
    return str(value or '').replace('\x00','')[:limit]


def render(payload):
    choices=payload['plan']['figures'];charts={item['chart_id']:item for item in payload['charts']}
    if not 1<=len(choices)<=12:raise ValueError('figure_count_limit')
    names={item.name for item in font_manager.fontManager.ttflist}
    candidates=['Noto Sans CJK SC','Noto Sans CJK JP','Microsoft YaHei','SimHei','Arial Unicode MS']
    chosen=next((name for name in candidates if name in names),None)
    if re.search(r'[\u2e80-\u9fff]',json.dumps(payload,ensure_ascii=False)) and not chosen:
        raise ValueError('cjk_font_unavailable')
    font=chosen or 'DejaVu Sans'
    assets=[]
    with matplotlib.rc_context({'font.family':[font,'DejaVu Sans'],'text.usetex':False,
            'text.parse_math':False,'svg.fonttype':'path','pdf.fonttype':42,'font.size':10,
            'axes.spines.top':False,'axes.spines.right':False,'axes.unicode_minus':False}):
        for choice in choices:
            chart=charts[choice['chart_id']];kind=choice['kind']
            width=float(choice['width']);height=float(choice['height']);dpi=int(choice['dpi'])
            if not 5<=width<=12 or not 3<=height<=9 or not 120<=dpi<=240:
                raise ValueError('figure_dimensions_invalid')
            if kind=='matrix':width=max(width,10);height=max(height,7)
            if kind=='bar':height=max(height,min(9,1.5+.18*min(40,len(chart.get('points') or []))))
            fig=Figure(figsize=(width,height),dpi=dpi,layout='constrained');FigureCanvasAgg(fig)
            ax=fig.add_subplot();color='#0072B2' if choice['palette']=='colorblind' else '#444444'
            notes=[];subset={}
            if kind in {'bar','line'}:
                points=chart.get('points') or []
                if not points or len(points)>200:raise ValueError('point_count_invalid')
                limit=40 if kind=='bar' else 200
                shown=points[:limit];subset={'shown_points':len(shown),'total_points':len(points)}
                if len(shown)<len(points):notes.append(f'展示前{len(shown)}项，共{len(points)}项；完整数据见研究记录。')
                values=[]
                for point in shown:
                    value=point.get('value')
                    if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value)):
                        raise ValueError('nonfinite_or_non_numeric_measurement')
                    values.append(value)
                labels=[label(point.get('label'),100) for point in shown]
                if kind=='bar':
                    positions=list(range(len(shown)))
                    ax.barh(positions,[value or 0 for value in values],color=color,height=.7)
                    ax.set_yticks(positions,labels=[text if len(text)<=28 else text[:27]+'…' for text in labels],fontsize=9);ax.invert_yaxis()
                    finite=[value for value in values if value is not None]
                    low=min([0,*finite]);high=max([0,*finite]);span=max(high-low,1)
                    ax.set_xlim(low-.02*span if low<0 else 0,high+.2*span)
                    for index,value in enumerate(values):
                        ax.annotate('未覆盖' if value is None else f'{value:g}',(value or 0,index),
                            xytext=(4 if (value or 0)>=0 else -4,0),textcoords='offset points',
                            ha='left' if (value or 0)>=0 else 'right',va='center',fontsize=9)
                    ax.set_xlabel(label(chart['unit_label']));ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True)
                else:
                    if chart.get('source_chart_id',chart['chart_id'])!='annual_publications':raise ValueError('line_requires_ordered_time_axis')
                    ax.plot(range(len(shown)),[math.nan if value is None else value for value in values],
                        color=color,marker='o',markersize=4,linewidth=1.7)
                    every=max(1,math.ceil(len(shown)/12));ticks=list(range(0,len(shown),every))
                    ax.set_xticks(ticks,labels=[labels[index] for index in ticks],rotation=45 if len(ticks)>8 else 0)
                    ax.set_ylabel(label(chart['unit_label']));ax.set_xlabel('发表年份')
                    ax.set_ylim(bottom=0);ax.grid(alpha=.2)
                    if any(value is None for value in values):notes.append('缺失年份保留断点，不插值。')
            elif kind=='network':
                nodes=(chart.get('nodes') or [])[:24]
                ids={item['id'] for item in nodes}
                edges=[edge for edge in chart.get('edges',[]) if edge['source'] in ids and edge['target'] in ids][:60]
                if not nodes:raise ValueError('network_nodes_missing')
                positions={item['id']:(math.cos(2*math.pi*index/len(nodes)),math.sin(2*math.pi*index/len(nodes)))
                    for index,item in enumerate(nodes)}
                for edge in edges:
                    start,end=positions[edge['source']],positions[edge['target']]
                    ax.plot([start[0],end[0]],[start[1],end[1]],color='#888888',alpha=.45,linewidth=1)
                for node in nodes:
                    x,y=positions[node['id']];ax.scatter([x],[y],s=35,color=color)
                    ax.annotate(label(node['label'],70),(x,y),xytext=(5,5),textcoords='offset points',fontsize=8)
                ax.set_xlim(-1.45,1.65);ax.set_ylim(-1.3,1.3);ax.set_aspect('equal');ax.axis('off')
                subset={'shown_nodes':len(nodes),'total_nodes':len(chart.get('nodes') or []),
                    'shown_edges':len(edges),'total_edges':len(chart.get('edges') or [])}
                notes.append('连线表示有来源的关系观察，位置与距离不表示相似度或合作强度。')
                if subset['shown_edges']<subset['total_edges'] or subset['shown_nodes']<subset['total_nodes']:
                    notes.append('图示为部分节点／连线，完整关系见数据表。')
            elif kind=='matrix':
                all_columns=chart.get('columns') or []
                all_rows=chart.get('rows') or []
                if not all_rows and chart.get('points'):
                    all_columns=['条目',chart['unit_label']]
                    all_rows=[{'values':[point['label'],'未覆盖' if point.get('value') is None else str(point['value'])]}
                        for point in chart['points']]
                if not all_rows and chart.get('edges'):
                    names={item['id']:item['label'] for item in chart.get('nodes',[])}
                    all_columns=['参与方','参与方','来源关系']
                    all_rows=[{'values':[names.get(edge['source'],edge['source']),names.get(edge['target'],edge['target']),edge.get('label','')]}
                        for edge in chart['edges']]
                columns=all_columns[:5];rows=all_rows[:6]
                if not columns or not rows:raise ValueError('comparison_table_missing')
                cells=[['\n'.join(textwrap.wrap(label(value,72)+('…' if len(str(value))>72 else ''),width=16))
                    for value in row['values'][:len(columns)]] for row in rows]
                table=ax.table(cellText=cells,colLabels=[label(value,60) for value in columns],loc='center',cellLoc='left')
                table.auto_set_font_size(False);table.set_fontsize(8)
                for (row,column),cell in table.get_celld().items():
                    cell.set_height(.13 if row else .065)
                    if row==0:cell.set_facecolor('#e7edf3')
                ax.axis('off');subset={'shown_rows':len(rows),'total_rows':len(all_rows),
                    'shown_columns':len(columns),'total_columns':len(all_columns)}
                notes.append('机制／条件为文字比较，不构成跨实验性能排名；图中为缩略说明，完整原文见报告表。'
                    if chart.get('rows') else '按本次来源数据展示，缺失值保留；完整数据见报告表。')
                if len(rows)<len(all_rows) or len(columns)<len(all_columns):
                    notes.append(f'图示为{len(rows)}/{len(all_rows)}行、{len(columns)}/{len(all_columns)}列，完整数据见报告表。')
            else:raise ValueError('unsupported_figure_kind')
            ax.set_title('\n'.join(textwrap.wrap(label(chart['title']),width=max(16,int(width*3)))),fontsize=13,pad=14)
            footer='\n'.join(textwrap.wrap(' '.join(notes),width=90))
            if footer:fig.supxlabel(footer,fontsize=8)
            files={}
            for format,mime in [('svg','image/svg+xml'),('png','image/png'),('pdf','application/pdf')]:
                buffer=io.BytesIO()
                fig.savefig(buffer,format=format,dpi=dpi,metadata={'Creator':VERSION})
                data=buffer.getvalue()
                if len(data)>3000000:raise ValueError('single_figure_asset_limit')
                files[format]='data:'+mime+';base64,'+base64.b64encode(data).decode('ascii')
            assets.append({'chart_id':chart['chart_id'],'kind':kind,**files,'notes':notes,'rendered_subset':subset,
                'size_inches':{'width':width,'height':height},'dpi':dpi})
    return {'renderer_version':matplotlib.__version__,'font':font,'assets':assets}


if __name__=='__main__':
    raw=sys.stdin.buffer.read(1500001)
    if len(raw)>1500000:raise ValueError('renderer_input_limit')
    result=render(json.loads(raw.decode('utf-8')))
    sys.stdout.write(json.dumps(result,ensure_ascii=False))
