"""Review the actual table, chart and original-page descriptors before delivery."""
from __future__ import annotations

from collections import Counter
import json
from urllib.parse import urlsplit

from app.claim_verification import audit_report
from app.llm_budget import budgeted_client
from app.query_understanding import identity
from app.security.prompt_security import untrusted_context

POLICY='adrs-report-surfaces-v1'


def surface_binding(charts,media,visual_requirements=None):
    def without_pixels(value):
        if isinstance(value,dict):return {key:without_pixels(item) for key,item in value.items() if key!='png'}
        if isinstance(value,list):return [without_pixels(item) for item in value]
        return value
    return identity({'charts':[{key:value for key,value in chart.items() if key!='rendered_assets'} for chart in charts],
        **({'visual_requirements':visual_requirements} if visual_requirements is not None else {}),
        'pages':[{key:without_pixels(value) if key=='figures' else value for key,value in page.items() if key not in {'png','width','height','renderer'}}
            for page in (media or {}).get('pages',[])]})


def review_surfaces(view,media,evidence,*,statistics,client,model,budget,source_spans=None,previous=None,
                    review_scope=None,report_audit=None,findings=None):
    charts=view.get('charts') or [];issues=[];paragraphs=[];locations={};page_spans={}
    from app.source_figure_extraction import MEDIA_POLICY
    deduplicate=bool(view.get('event_timeline_policy')) or (media or {}).get('policy')==MEDIA_POLICY
    issues.extend(view.get('pdf_projection_issues') or [])
    issues.extend(view.get('visualization_issues') or [])
    retained_contexts={};retained_claims=[]
    refs={'citation:'+str(number) for number in range(1,len(evidence)+1)}
    def statement(text,citations,location,*,exact_context=None):
        valid=[key for key in citations if key in refs]
        if not valid and not review_scope:
            issues.append({'location':location,'reason':'surface_fact_has_no_source'});return
        if deduplicate and exact_context is None:valid=sorted(set(valid),key=lambda key:int(key.split(':')[1]))
        paragraph=exact_context or (' '.join(text.split())+' '+' '.join('['+key+']' for key in dict.fromkeys(valid)))
        if paragraph not in locations or not deduplicate:paragraphs.append(paragraph)
        locations[paragraph]=location
        return paragraph
    registry=(statistics or {}).get('metric_registry') or {}
    evidence_by_id={row.evidence_id:row for row in evidence}
    citation_sources={row['citation_id']:(row.get('locator') or {}).get('evidence_id') for row in view.get('citations',[])}
    def mechanism_statement(text,citations,proofs,location):
        from app.report_mechanisms import checked_proofs
        try:spans=checked_proofs(proofs,evidence_by_id,citation_sources,citations)
        except (KeyError,ValueError,TypeError) as error:
            issues.append({'location':location,'reason':str(error)[:200]});return
        paragraph=statement(text,citations,location)
        if paragraph:page_spans[paragraph]=spans
    for requirement in view.get('visual_requirements') or []:
        if not requirement.get('source_figure_id'):continue
        card=next((row for row in ((findings or {}).get('technical_reading') or {}).get('cards',[])
            if row['output_id']==requirement['output_id']),{})
        original=(card.get('mechanism_graph') or {}).get('original_reference')
        if original!=requirement.get('original_reference'):
            issues.append({'location':requirement['requirement_id'],'reason':'mechanism_original_binding_changed'});continue
        mechanism_statement(requirement['source_claim'],requirement['citation_ids'],[original['proof']],requirement['requirement_id'])
    from app.report_mechanisms import SUPPORTED_POLICIES as MECHANISM_POLICIES
    for chart in charts:
        key=chart['chart_id']
        if chart.get('mechanism_policy') in MECHANISM_POLICIES:
            from app.report_mechanisms import RELATIONS
            card=next((row for row in ((findings or {}).get('technical_reading') or {}).get('cards',[])
                if row['output_id']==chart['output_id']),{})
            graph=card.get('mechanism_graph') or {};nodes={row['id']:row for row in chart['nodes']}
            if (graph.get('policy')!=chart['mechanism_policy'] or graph.get('status')!='source_located_requires_semantic_review'
                    or [{key:row[key] for key in ('id','label','proofs')} for row in chart['nodes']]!=graph.get('nodes')
                    or [{key:row[key] for key in ('source','target','relation','label','proofs')} for row in chart['edges']]!=graph.get('edges')):
                issues.append({'location':key,'reason':'mechanism_graph_binding_changed'});continue
            for node in chart['nodes']:
                mechanism_statement(card['title']+'的机制包含组件“'+node['label']+'”。',node['citation_ids'],node['proofs'],key+':node:'+node['id'])
            for index,edge in enumerate(chart['edges']):
                mechanism_statement(card['title']+'中，“'+nodes[edge['source']]['label']+'”'+RELATIONS[edge['relation']]
                    +'“'+nodes[edge['target']]['label']+'”：'+edge['label']+'。',edge['citation_ids'],edge['proofs'],key+':edge:'+str(index))
        elif chart.get('event_policy')=='adrs-source-publication-events-v1':
            from app.report_timeline import validate_event
            events=chart.get('events') or []
            event_ids=[event['event_id'] for event in events]
            required=set(chart.get('required_event_ids') or [])
            missing={row['output_id'] for row in chart.get('missing_events') or []}
            if (not events or len(event_ids)!=len(set(event_ids)) or len(events)!=chart.get('total_events')
                    or set(event_ids)!=required-missing):
                issues.append({'location':key,'reason':'publication_event_coverage_changed'})
            sources={row.evidence_id:row for row in evidence}
            citation_sources={row['citation_id']:(row.get('locator') or {}).get('evidence_id')
                for row in view.get('citations',[])}
            for event in events:
                location=key+':event:'+event['event_id']
                try:validate_event(event,findings or {},sources,citation_sources)
                except (ValueError,KeyError,TypeError) as error:
                    issues.append({'location':location,'reason':str(error)[:200]});continue
                if event.get('detail'):
                    detail_sources={proof['evidence_id'] for proof in event['detail_proofs']}
                    detail_refs=[ref for ref in event['citation_ids'] if citation_sources.get(ref) in detail_sources]
                    statement(event['label']+'；机制：'+event['detail'],detail_refs,location)
        elif chart.get('kind') in {'table','matrix'}:
            for index,row in enumerate(chart.get('rows',[])):
                values=row.get('values') or []
                for column,value in enumerate(values[1:],1):
                    if value in {None,'','—'}:continue
                    columns=chart.get('columns') or []
                    if column>=len(columns):issues.append({'location':key,'reason':'column_binding_missing'});continue
                    cell_refs=(row.get('cell_citation_ids') or {}).get(str(column),row.get('citation_ids',[]))
                    statement(f'{values[0]}；{columns[column]}：{value}',cell_refs,f'{key}:{index}:{column}')
        elif chart.get('kind')=='network':
            nodes={row['id']:row['label'] for row in chart.get('nodes',[])}
            for index,edge in enumerate(chart.get('edges',[])):
                if edge.get('source') not in nodes or edge.get('target') not in nodes:
                    issues.append({'location':key,'reason':'edge_endpoint_missing'});continue
                statement(f"{nodes[edge['source']]}与{nodes[edge['target']]}：{edge.get('label')}；"
                    f"关系种类：{edge.get('kind')}。",
                    edge.get('citation_ids',[]),f'{key}:edge:{index}')
        elif chart.get('source_binding')=='statistical_snapshot_metric_members_and_dataset_sources':
            for point in chart.get('points',[]):
                metric=registry.get(point.get('metric_id'))
                if (not metric or chart.get('snapshot_id')!=(statistics or {}).get('snapshot_id')
                        or metric.get('value')!=point.get('value') or metric.get('unit')!=chart.get('unit')
                        or bool(point.get('missing',point.get('value') is None))!=(metric.get('value') is None)):
                    issues.append({'location':key,'metric_id':point.get('metric_id'),'reason':'chart_statistic_binding_mismatch'})
        elif chart.get('source_binding')=='retained_citation_ids':
            domains=Counter()
            for citation in {row['citation_id']:row for row in view.get('citations',[])}.values():
                try:host=urlsplit(citation.get('source_url','')).hostname or '内部/未提供域名'
                except ValueError:host='未提供有效域名'
                domains[host]+=1
            expected=[{'label':name,'value':value,'metric_id':None} for name,value in domains.most_common(200)]
            if chart.get('points')!=expected:issues.append({'location':key,'reason':'citation_population_mismatch'})
        else:issues.append({'location':key,'reason':'unsupported_surface_requires_review_contract'})
    by_id={row.evidence_id:row for row in evidence}
    for page in (media or {}).get('pages',[]):
        if page.get('presentation')=='original_pdf_figure_groups':
            from app.source_figure_extraction import EXTRACTOR,renderer_key,match_figure
            targets=page.get('targets') or [];figures=page.get('figures') or []
            if not targets or len(figures)!=len(targets) or {row['label'] for row in figures}!={row['label'] for row in targets}:
                issues.append({'location':page['asset_id']+':'+str(page['page']),'reason':'source_figure_coverage_incomplete'})
            for figure in figures:
                try:
                    layout=figure['layout']
                    match_figure({'extractor':EXTRACTOR,'figures':[layout]},page=page['page'],label=figure['label'])
                    if (figure['figure_id']!=layout['figure_id'] or figure['renderer']!=renderer_key(layout)
                            or any(type(figure.get(field)) is not int or not 1<=figure[field]<=2000 for field in ('width','height'))
                            or figure['width']*figure['height']>2_000_000):
                        raise ValueError('source_figure_render_binding_changed')
                except (KeyError,ValueError,TypeError) as error:
                    issues.append({'location':page['asset_id']+':'+str(page['page']),'reason':str(error)[:200]})
            for target in targets:
                for proof in target['proofs']:
                    source=by_id.get(proof['evidence_id']);start,end=proof.get('start'),proof.get('end')
                    if (not source or type(start) is not int or type(end) is not int
                            or not 0<=start<end<=len(source.content) or source.content[start:end]!=proof['quote']):
                        issues.append({'location':target['label'],'reason':'source_figure_caption_proof_changed'})
        for caption in page.get('captions',[]):
            located=False
            for proof in page.get('proofs',[]):
                source=by_id.get(proof.get('evidence_id'));start,end=proof.get('start'),proof.get('end')
                if source and type(start) is int and type(end) is int and 0<=start<end<=len(source.content):
                    located|=proof.get('quote')==caption==source.content[start:end]
            if not located:issues.append({'location':str(page.get('page')),'reason':'original_caption_binding_mismatch'})
        if page.get('explanation'):
            numbers=['citation:'+str(index) for index,row in enumerate(evidence,1) if row.evidence_id in page.get('evidence_ids',[])]
            exact_context=None
            from app.source_media_explanations import REPORT_CONTEXT_CONTRACT
            if page.get('explanation_basis')==REPORT_CONTEXT_CONTRACT:
                from app.organization_purpose import report_prose
                from app.claim_verification import extract_claims,claim_scope_key
                context=page.get('explanation_claim_context') or ''
                rows=[row for row in (report_audit or {}).get('claims',[]) if row['paragraph_context']==context]
                approved={claim_scope_key(row):row for row in rows}
                expected=extract_claims(context)
                # Only rendering escapes and the unchanged, ordered citation
                # suffix separate this excerpt from the reviewed paragraph.
                prefix=report_prose(page['explanation'])
                suffix=context[len(prefix):].strip() if context.startswith(prefix) else None
                citation_suffix=' '.join(f'[citation:{number}]' for number in
                    dict.fromkeys(n for row in expected for n in row['citation_ids']))
                if (not expected or suffix!=citation_suffix or any(claim_scope_key(row) not in approved
                        for row in expected) or (report_audit or {}).get('needs_review',True)
                        or (report_audit or {}).get('audit_incomplete')):
                    issues.append({'location':str(page['page']),'reason':'reviewed_report_context_binding_changed'})
                    continue
                exact_context=context
                if context not in retained_contexts:retained_claims.extend(rows)
                retained_contexts[context]=rows[0].get('declared_kind')
            paragraph=statement(page['explanation'],numbers,'original_page:'+page['asset_id']+':'+str(page['page']),
                exact_context=exact_context)
            located={}
            for evidence_id in page.get('evidence_ids',[]):
                source=by_id.get(evidence_id)
                if not source:continue
                for original in (source.acquisition or {}).get('pages',[]):
                    start,end=original.get('start'),original.get('end')
                    if (original.get('number')==page['page'] and type(start) is int and type(end) is int
                            and 0<=start<end<=len(source.content)):
                        located[evidence_id]=[('original_page',start,end)]
            if paragraph and located and not exact_context:page_spans[paragraph]=located
    prior=(previous or {}).get('claim_audit')
    if retained_claims:
        prior={**(prior or {}),'claims':[*((prior or {}).get('claims') or []),*retained_claims],
            'audit_contract_version':report_audit.get('audit_contract_version'),
            'audit_model':report_audit.get('audit_model')}
    audit=audit_report('\n\n'.join(paragraphs),evidence,
        client=budgeted_client(client,budget,'audit'),model=model,token_budget=budget.available('audit'),
        deadline=budget.deadline,source_spans=source_spans,paragraph_source_spans=page_spans,
        previous_audit=prior,review_scope=review_scope,paragraph_kinds=retained_contexts) if paragraphs else None
    passed=not issues and (audit is None or not audit.get('needs_review',True)
        and not audit.get('audit_incomplete') and not audit.get('budget_incomplete'))
    return {'policy':POLICY,'binding':surface_binding(charts,media,view.get('visual_requirements')),'passed':passed,
        'status':'satisfied' if passed else 'needs_revision','issues':issues,'claim_audit':audit,
        'paragraph_locations':locations,
        'semantics':'descriptor_facts_and_numeric_bindings_reviewed_visual_legibility_separate'}


def repair_table_cells(view,review,*,client,model,budget,on_candidate,media=None):
    """Correct only table cells with completed source-audit failures, once."""
    audit=review.get('claim_audit') or {}
    if audit.get('audit_incomplete') or audit.get('budget_incomplete'):return None
    charts={row['chart_id']:row for row in view.get('charts',[])}
    pages={'original_page:'+row['asset_id']+':'+str(row['page']):row for row in (media or {}).get('pages',[])}
    targets={}
    for claim in audit.get('claims',[]):
        if not claim.get('verification_required',True) or claim.get('status')=='supported':continue
        location=(review.get('paragraph_locations') or {}).get(claim.get('paragraph_context'))
        if not location:continue
        if location in pages:
            target=targets.setdefault(location,{'cell_id':location,'kind':'original_page_explanation',
                'text':pages[location]['explanation'],'issues':[]})
            target['issues'].append({name:claim.get(name) for name in ('text','reason','excerpts','citation_ids')})
            continue
        parts=location.rsplit(':',2)
        if len(parts)!=3 or not parts[1].isdigit() or not parts[2].isdigit():continue
        key,index,column=parts[0],int(parts[1]),int(parts[2]);chart=charts.get(key)
        if not chart or chart.get('kind') not in {'table','matrix'}:continue
        cell=chart['rows'][index]['values'][column]
        target=targets.setdefault(location,{'cell_id':location,'text':cell,'issues':[]})
        target['issues'].append({name:claim.get(name) for name in ('text','reason','excerpts','citation_ids')})
    if not targets:return None
    payload=json.dumps({'cells':list(targets.values())},ensure_ascii=False)
    messages=[{'role':'system','content':'Correct only the supplied technical table cells or original-page explanations using their original '
        'source excerpts. Preserve the useful mechanism and all conditions needed by a numerical result. '
        'Do not delete cells, replace substance with disclaimers, alter statistics, change the research scope '
        'or invent sources. Remove internal process commentary about obtaining sources or future checking; '
        'retain the mechanism, experimental conditions and supported interpretation. '
        'Return JSON {"cells":[{"cell_id":"supplied ID","text":"corrected cell or explanation"}]}, '
        'exactly once for each supplied cell. Earlier audit reasons are diagnostics, not source facts.'},
        {'role':'user','content':untrusted_context('surface_repairs',payload,limit=len(payload))}]
    response=budgeted_client(client,budget,'report',operation='surface_revision',
        content_unit_id='surface-repair:'+identity(messages)).chat.completions.create(model=model,messages=messages,
        temperature=.1,max_tokens=4096,response_format={'type':'json_object'})
    choice=response.choices[0] if response.choices else None
    if choice is None:return None
    reply=choice.message.content or ''
    on_candidate(reply,stage='table_cell_revision')
    if choice.finish_reason!='stop':return None
    try:
        cells=json.loads(reply)['cells']
        if len(cells)!=len(targets) or {row['cell_id'] for row in cells}!=set(targets):return None
        if any(not isinstance(row.get('text'),str) or not 3<=len(row['text'])<=4000 for row in cells):return None
    except (ValueError,KeyError,TypeError):return None
    return {'base_binding':surface_binding(view.get('charts',[]),None),
        'cells':[row for row in cells if row['cell_id'] not in pages],
        'pages':[row for row in cells if row['cell_id'] in pages],
        'semantics':'candidate_cell_corrections_require_full_surface_reaudit'}
