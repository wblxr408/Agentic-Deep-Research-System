"""Versioned statistical data shared by text, tables, charts and exports."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

VERSION='adrs-statistical-snapshot-v2'


def build_statistics(config,findings,evidence,*,source_id):
    if not isinstance(source_id,str) or not source_id.strip():
        raise ValueError('statistics_require_recorded_source_identity')
    findings=findings or {}
    scoped=findings.get('scope_result') or {};metrics={};conflicts=[];publications={}
    for output in scoped.get('outputs',[]):
        identity=output['output_id']
        if identity in publications and publications[identity]!=output:conflicts.append({'kind':'publication_identity','id':identity,'reason':'conflicting_duplicate_output_id'})
        else:publications[identity]=output
    ids=set(publications);families={};linked={}
    for family in scoped.get('research_families',[]):
        members=set(family['output_ids'])
        unit='family:'+family['family_id']
        if unit in families:
            conflicts.append({'kind':'research_family','id':family['family_id'],'reason':'duplicate_family_identity'});continue
        if not members or not members<=ids or any(member in linked for member in members):
            conflicts.append({'kind':'research_family','id':family['family_id'],'reason':'missing_or_already_linked_publication'});continue
        families[unit]=members
        for member in members:linked[member]=unit
    for identity in ids:
        if identity not in linked:linked[identity]='publication:'+identity;families[linked[identity]]={identity}
    def count(key,label,members,unit,*,basis=None):
        members=sorted(set(members));value=len(members)
        metrics[key]={'metric_id':key,'label':label,'kind':'count','value':value,'display':str(value),
            'unit':unit,'member_ids':members,'numerator':value,'denominator':None,'basis':basis or 'distinct_declared_members'}
        return metrics[key]
    def ratio(key,label,numerator_ids,denominator_ids,unit,*,basis):
        top,bottom=set(numerator_ids),set(denominator_ids)
        if not top<=bottom:conflicts.append({'kind':'ratio','id':key,'reason':'numerator_not_subset_of_declared_denominator'})
        value=(Decimal(len(top))*100/Decimal(len(bottom))).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP) if bottom else None
        metrics[key]={'metric_id':key,'label':label,'kind':'percentage','value':float(value) if value is not None else None,
            'display':f'{value:.2f}%' if value is not None else '未知（空分母）','unit':'percent','counting_unit':unit,
            'numerator':len(top),'denominator':len(bottom),'numerator_ids':sorted(top),'denominator_ids':sorted(bottom),
            'rounding':'decimal_half_up_2','basis':basis,'status':'computed' if bottom else 'undefined_empty_denominator'}
        return metrics[key]
    count('sample:publications','采纳发表记录',ids,'publication')
    count('sample:families','研究家族及未链接发表单元',families,'research_family_or_unlinked_publication')
    object_rows=[];seen_objects=set()
    for view in scoped.get('views',[]):
        members=set(view.get('output_ids',[]))&ids;units={linked[identity] for identity in members};identity=view['entity_id']
        if identity in seen_objects:
            conflicts.append({'kind':'object_view','id':identity,'reason':'duplicate_object_view_not_counted_again'});continue
        seen_objects.add(identity)
        count('object:'+identity+':publications',view['name']+'：发表',members,'publication')
        count('object:'+identity+':families',view['name']+'：家族',units,'research_family_or_unlinked_publication')
        ratio('object:'+identity+':sample_share',view['name']+'：样本覆盖占比',members,ids,'publication',basis='per_object_full_count_multiple_objects_may_share_outputs')
        object_rows.append({**view,'output_ids':sorted(members),'publication_count':len(members),'output_count':len(members),
            'research_family_count':len(units),'research_family_ids':sorted(units),
            'publication_metric_id':'object:'+identity+':publications','family_metric_id':'object:'+identity+':families'})
    years=defaultdict(set);unknown_year=set();publication_years={}
    for identity,output in publications.items():
        metadata_year=(findings.get('publication_metadata',{}).get(identity) or {}).get('year')
        try:
            lower=date.fromisoformat(output.get('published_on') or '')
            upper=date.fromisoformat(output.get('published_until') or output['published_on'])
            year=lower.year if lower<=upper and lower.year==upper.year else None
        except (ValueError,KeyError,TypeError):year=None
        if metadata_year is not None and metadata_year!=year:
            conflicts.append({'kind':'publication_year','id':identity,'claimed':metadata_year,'computed':year,
                'reason':'accepted_date_interval_is_authoritative_metadata_not_used_to_fill_unknown'})
        publication_years[identity]=year
        if year is None:unknown_year.add(identity)
        else:years[year].add(identity)
    count('sample:unknown_year','采纳样本中年份未知',unknown_year,'publication')
    pending_unknown={str(index) for index,item in enumerate(findings.get('pending_records',[]))
        if item.get('kind')=='publication' and not (item.get('proposed_record') or {}).get('publication_date')}
    count('candidates:unknown_year','待核候选中年份未知',pending_unknown,'pending_record_not_accepted_publication')
    annual=[]
    for year in range(int(config['scope']['start_date'][:4]),int(config['scope']['end_date'][:4])+1):
        members=years.get(year,set());key=f'year:{year}:publications'
        if members:
            count(key,f'{year}年采纳发表',members,'publication')
            ratio(f'year:{year}:sample_share',f'{year}年占采纳样本',members,ids,'publication',basis='all_accepted_publications_including_unknown_year')
            annual.append({'year':year,'publication_count':len(members),'research_family_count':len({linked[item] for item in members}),
                'coverage':'observed_sample_not_census','metric_id':key})
        else:
            metrics[key]={'metric_id':key,'label':f'{year}年','kind':'count','value':None,'display':'未覆盖（不补零）',
                'unit':'publication','member_ids':[],'numerator':None,'denominator':None,'status':'unobserved_year'}
            annual.append({'year':year,'publication_count':None,'research_family_count':None,'coverage':'unobserved_not_zero','metric_id':key})
    classification=findings.get('classification') or {};nodes={node['node_id']:node for node in (classification.get('taxonomy') or {}).get('nodes',[])}
    assignments=defaultdict(set);unknown_by_axis={axis:set(ids) for axis in ('problem','method','application')}
    for record in classification.get('records',[]):
        identity=record['output_id']
        if identity not in ids:conflicts.append({'kind':'classification','id':identity,'reason':'unavailable_publication'});continue
        for tag in record.get('labels',[]):
            node=nodes.get(tag['node_id'])
            if node is None or node['axis']!=tag['axis']:
                conflicts.append({'kind':'classification','id':tag['node_id'],'reason':'unknown_or_mismatched_node'});continue
            assignments[tag['node_id']].add(identity);unknown_by_axis[tag['axis']].discard(identity)
    label_rows=[]
    for identity,node in nodes.items():
        if not node.get('terms') and not assignments.get(identity):continue
        members=assignments.get(identity,set());units={linked[item] for item in members}
        metric=count('label:'+identity+':publications',node['label'],members,'publication',basis='each_label_once_per_publication_multilabel_allowed')
        percentage=ratio('label:'+identity+':sample_share',node['label']+'：采纳样本占比',members,ids,'publication',basis='shared_all_publication_denominator_multilabel_sum_can_exceed_100')
        count('label:'+identity+':families',node['label']+'：家族',units,'research_family_or_unlinked_publication')
        label_rows.append({'node_id':identity,'label':node['label'],'axis':node['axis'],'role':node['role'],
            'publication_count':len(members),'research_family_count':len(units),'count_metric_id':metric['metric_id'],
            'percentage_metric_id':percentage['metric_id']})
    for axis,members in unknown_by_axis.items():count('classification:'+axis+':unknown','未知分类：'+axis,members,'publication')
    canonical_annual=[]
    for year,members in sorted(years.items()):
        canonical_annual.append({'year':year,'publication_count':len(members),
            'label_counts':{node:len(values&members) for node,values in assignments.items() if values&members},
            'unknown_publication_count':len(members-set().union(*assignments.values())) if assignments else len(members),
            'unknown_by_axis':{axis:len(values&members) for axis,values in unknown_by_axis.items()}})
    source_ids={item['evidence_id'] for item in evidence if item.get('evidence_id')}
    count('sources:retained','保留来源证据',source_ids,'evidence_not_publication')
    # A document, its evidence chunks and its accepted publication record are
    # different populations. A complete source is not automatically in scope
    # or attributable to a selected institution.
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    documents=defaultdict(list)
    for item in evidence:
        acquisition=item.get('acquisition') or {}
        url=item.get('source_url') or ''
        try:
            parsed=urlsplit(url)
            url=urlunsplit((parsed.scheme,parsed.netloc.lower(),parsed.path,
                urlencode([(key,value) for key,value in parse_qsl(parsed.query) if not key.startswith('utm_')]),''))
        except ValueError:pass
        identity=str(acquisition.get('source_document_id') or url or item.get('evidence_id'))
        revision=acquisition.get('parse_version_id') or acquisition.get('source_version') or ''
        documents[identity+':'+str(revision)].append(item)
    full_text=set();partial_text=set();landing=set()
    for identity,items in documents.items():
        for item in items:
            acquisition=item.get('acquisition') or {}
            if acquisition.get('chunk_reference') or item.get('source_type')=='knowledge_base':continue
            complete=acquisition.get('coverage')=='full_text' and not acquisition.get('truncated')
            if acquisition.get('format')=='pdf':
                complete=complete and bool(acquisition.get('total_pages')) and acquisition.get('retained_pages')==acquisition.get('total_pages')
            if complete:full_text.add(identity)
            elif acquisition.get('coverage')=='partial_text':partial_text.add(identity)
            elif acquisition.get('coverage')!='discovery_only':landing.add(identity)
    partial_text-=full_text;landing-=full_text|partial_text
    count('sources:documents','取得的来源文档版本',documents,'source_document_version')
    count('sources:full_text_documents','取得全文的文档版本',full_text,'full_text_document_version',basis='complete_acquired_body_not_publication_admission')
    count('sources:partial_text_documents','取得部分正文的文档版本',partial_text,'partial_text_document_version')
    count('sources:landing_documents','落地页或元数据文档版本',landing,'metadata_document_version')
    corpus=findings.get('corpus') or {};flow=defaultdict(set)
    for record in corpus.get('records',[]):flow[record['admission_status']].add(record['source_url'])
    for status,members in flow.items():count('sources:'+status,'来源候选：'+status,members,'source_url_not_publication')
    for view in object_rows:
        old=next((item for item in scoped.get('views',[]) if item['entity_id']==view['entity_id']),{})
        for key in ('publication_count','research_family_count'):
            if old.get(key) is not None and old[key]!=view[key]:conflicts.append({'kind':'input_count','id':view['entity_id']+':'+key,'claimed':old[key],'computed':view[key]})
    for key,value in [('publication_count',len(ids)),('research_family_count',len(families))]:
        old=(scoped.get('summary') or {}).get(key)
        if old is not None and old!=value:conflicts.append({'kind':'input_count','id':'summary:'+key,'claimed':old,'computed':value})
    comparison_groups=[]
    for group in findings.get('comparison_groups',[]):
        members={identity for identity in ids if publication_years[identity]==group.get('publication_year')
            and (findings.get('publication_metadata',{}).get(identity) or {}).get('output_type')==group.get('output_type')}
        objects=[]
        for view in object_rows:
            own=set(view['output_ids'])&members;units={linked[identity] for identity in own}
            objects.append({'entity_id':view['entity_id'],'research_family_count':len(units),
                'publication_count':len(own),'output_ids':sorted(own),'family_unit_ids':sorted(units)})
        comparison_groups.append({**group,'objects':objects,'ranking':None})
    classification_id=classification.get('snapshot_id','unclassified')
    snapshot_id=source_id+':'+VERSION+':'+classification_id
    return {'schema_version':VERSION,'snapshot_id':snapshot_id,'source_id':source_id,'classification_snapshot_id':classification.get('snapshot_id'),
        'taxonomy_version':(classification.get('taxonomy') or {}).get('version'),'metric_registry':metrics,
        'publication_ids':sorted(ids),'family_units':{identity:sorted(members) for identity,members in families.items()},
        'object_rows':object_rows,'annual':annual,'classification_annual':canonical_annual,'label_rows':label_rows,
        'publication_years':publication_years,'comparison_groups':comparison_groups,
        'unknown_year_ids':sorted(unknown_year),'unknown_by_axis':{axis:sorted(values) for axis,values in unknown_by_axis.items()},
        'input_count_claims':{'summary':scoped.get('summary'),'views':[{key:item.get(key) for key in ('entity_id','publication_count','research_family_count')} for item in scoped.get('views',[])]},
        'conflicts':conflicts,'calculation_status':'computed_with_explained_input_conflicts' if conflicts else 'computed',
        'series':{'annual_publications':[{'x':row['year'],'y':row['publication_count'],'metric_id':row['metric_id'],'missing':row['publication_count'] is None} for row in annual],
            'classification_publications':[{'x':row['label'],'y':row['publication_count'],'metric_id':row['count_metric_id']} for row in label_rows]},
        'conventions':['发表与研究家族分别计数；未链接版本按独立发表单元，汇总用并集而非机构数相加。',
            '同一篇可有多个标签，每标签每篇只计一次，共同分母为全部采纳发表；比例合计可超过100%。',
            '标签零值只表示本样本没有规则命中，不证明真实研究方向不存在；未分类按问题／方法／应用分别保留。',
            '未知年份单列；未观察年份为null，不补零或自动计算增长率。',
            '不同年份可观察同一家族，年度家族数不可直接求和当成全期家族数。',
            '来源证据条目、来源文档版本、全文文档版本、采纳发表及研究家族分别计数；全文取得不证明归属或范围采纳。',
            '图表、正文、表格及导出引用同一snapshot_id与metric_id；算术计算不等于独立语义核实或现实全集。']}


def apply_statistics(findings,snapshot):
    result={**findings};scoped=deepcopy(findings.get('scope_result') or {})
    if scoped:
        unique={}
        for output in scoped.get('outputs',[]):unique.setdefault(output['output_id'],output)
        scoped['outputs']=[unique[identity] for identity in snapshot['publication_ids']]
        scoped['summary']={**scoped.get('summary',{}),'publication_count':len(snapshot['publication_ids']),
            'output_count':len(snapshot['publication_ids']),'research_family_count':len(snapshot['family_units']),
            'output_ids':snapshot['publication_ids'],'research_family_ids':list(snapshot['family_units'])}
        scoped['views']=snapshot['object_rows'];result['scope_result']=scoped
    result['publication_metadata']={identity:{**metadata,'year':snapshot['publication_years'].get(identity),
        'original_metadata_year':metadata.get('original_metadata_year',metadata.get('year')),
        'year_basis':'accepted_publication_date_interval'} for identity,metadata in findings.get('publication_metadata',{}).items()}
    if findings.get('classification'):
        classification={**findings['classification'],'annual':snapshot['classification_annual'],
            'statistics_snapshot_id':snapshot['snapshot_id']}
        classification['records']=[{**row,'year':snapshot['publication_years'].get(row['output_id'])}
            for row in classification.get('records',[])]
        classification['unobserved_years']=[row['year'] for row in snapshot['annual'] if row['publication_count'] is None]
        if classification.get('comparison'):
            classification['comparison']={**classification['comparison'],'annual_after':snapshot['classification_annual']}
        result['classification']=classification
    result['comparison_groups']=snapshot['comparison_groups']
    result['statistics']=snapshot
    return result


def statistics_context(snapshot):
    if not snapshot:return None
    priority=('sample:publications','sample:families','sources:documents','sources:full_text_documents',
        'sources:partial_text_documents','sources:landing_documents','sources:retained')
    registry=snapshot['metric_registry']
    ordered=[key for key in priority if key in registry]+[key for key in registry if key not in priority]
    return {'snapshot_id':snapshot['snapshot_id'],'schema_version':snapshot.get('schema_version',VERSION),'metric_registry':{
        key:{field:registry[key].get(field) for field in ('label','kind','display','value','numerator','denominator','unit','counting_unit','basis','status')}
        for key in ordered[:100]},'conventions':snapshot['conventions'],
        'conflicts':snapshot['conflicts'][:10],'retained_metric_count':len(snapshot['metric_registry'])}


def statistics_markdown(snapshot):
    if not snapshot:return ''
    def safe(value):return str(value).replace('|','\\|').replace('<','&lt;').replace('>','&gt;').replace('\n',' ')
    lines=['\n\n## 统一统计口径与可复核数值','快照：'+safe(snapshot['snapshot_id']),*snapshot['conventions'],
        '| 指标 ID | 指标 | 值 | 分子 | 分母 | 单位 |','| --- | --- | ---: | ---: | ---: | --- |']
    for key,value in snapshot['metric_registry'].items():
        lines.append('| '+' | '.join(safe(item) for item in [key,value['label'],value['display'],value.get('numerator','未知'),value.get('denominator','不适用'),value.get('counting_unit',value['unit'])])+' |')
    if snapshot['conflicts']:lines+=['\n### 输入口径冲突（使用上述程序计算值）']+['- '+safe(item) for item in snapshot['conflicts']]
    return '\n'.join(lines)
