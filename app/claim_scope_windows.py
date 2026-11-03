"""Use assembled main text with bounded complete appendix views for scope only."""
from __future__ import annotations

from copy import deepcopy

from app.query_understanding import identity


def select_window_scope(claims,scope,previous,client,model,*,on_progress,retained_selection,support_candidates,layout):
    from app.claim_verification import claim_scope_key,AuditCheckpointError
    from app.claim_scope_dependencies import WINDOW_POLICY,catalogue,selection_binding,_select_scope_pages,_finish_scope
    data=catalogue(claims);context_id=identity(data);route_id=identity(getattr(client,'route_info',None))
    control=client.budget.execution_control;root=control.binding
    binding=identity({'policy':WINDOW_POLICY,'scope':scope,'context':context_id,'layout':layout,
        'model':model,'route':route_id,'governance':client.budget.data_governance,'skill_packet':client.skill_packet,
        'root':{key:root.get(key) for key in ('owner_id','session_id')}})
    saved=retained_selection or (previous or {}).get('scope_selection') or {}
    restoring=saved.get('window_binding')==binding
    full=None
    if not restoring:
        result,full=_select_scope_pages(claims,scope,previous,client,model,on_progress=on_progress,
            retained_selection=retained_selection,support_candidates=support_candidates)
        admission=full.get('admission') or {};window=(getattr(client,'route_info',None) or {}).get('context_tokens')
        paid=any('raw_response' in row or row.get('dispatch_status') in {'dispatch_intent','dispatch_attempted'}
            for row in full.get('batches',[]))
        if (not layout or layout.get('policy')!='adrs-assembled-scope-layout-v1' or paid or not window
                or full.get('reason')!='scope_complete_request_exceeds_current_capacity'
                or admission.get('request_bound',0)<=window):return result,full
    placements={}
    for row in (layout or {}).get('paragraphs',[]):placements.setdefault(row['text'],[]).append(row)
    main=[];appendix=[];navigation=[];citations={}
    for row in data['claims']:
        citations.setdefault(row['context_id'],{}).update({number:None for number in row['citation_ids']})
    for key,context in data['contexts'].items():
        locations=placements.get(context['text']) or []
        if not locations or any(row.get('section')!='appendix' for row in locations):main.append(key)
        else:
            appendix.append(key)
            navigation.append({'context_id':key,'module_ids':sorted({row['module_id'] for row in locations}),
                'citation_ids':list(citations.get(key,{}))})
    # Preserve headings, code and other main-document text omitted by the
    # sentence catalogue. Exact paragraph references avoid a second prose copy.
    original=layout['main_markdown'];cursor=0;main_layout=[]
    for key in main:
        text=data['contexts'][key]['text'];start=original.find(text,cursor)
        if start<0:continue
        if start>cursor:main_layout.append({'text':original[cursor:start]})
        main_layout.append({'context_id':key});cursor=start+len(text)
    if cursor<len(original):main_layout.append({'text':original[cursor:]})
    state={'policy':WINDOW_POLICY,'context_id':context_id,'route_id':route_id,'window_binding':binding,
        'semantics':'main_and_complete_appendix_views_not_full_appendix_or_source_certification',
        'main_context_ids':main,'appendix_context_ids':appendix,
        'views':deepcopy(saved.get('views') or {}) if restoring else {},
        'full_admission':deepcopy(saved.get('full_admission')) if restoring else (full or {}).get('admission'),
        'blocked_view_ids':[],'support_reuse':{},'support_reuse_contexts':{}}
    decisions={};old={claim_scope_key(row):row for row in (previous or {}).get('claims',[])}
    all_keys={row['claim_key'] for row in data['claims']}
    def checkpoint():
        control.check()
        try:on_progress(deepcopy(state))
        except AuditCheckpointError:raise
        except Exception as error:raise AuditCheckpointError() from error
    checkpoint()
    def visit(local,prefix,*,core=False):
        targets=set(main if core else local);supplied=set(main)|set(local)
        view_data={'contexts':{key:value for key,value in data['contexts'].items() if key in supplied},
            'claims':[row for row in data['claims'] if row['context_id'] in supplied]}
        target_keys={row['claim_key'] for row in data['claims'] if row['context_id'] in targets}
        if not target_keys:return True
        view={'data':view_data,'navigation':navigation,'main_layout':main_layout}
        view['binding']=identity(view)
        def save(value):state['views'][prefix]=value;checkpoint()
        values,part=_select_scope_pages(claims,scope,previous,client,model,on_progress=save,
            retained_selection=state['views'].get(prefix),support_candidates=support_candidates,
            target_claim_keys=target_keys,input_view=view,finalize=False)
        admission=part.get('admission') or {};window=(getattr(client,'route_info',None) or {}).get('context_tokens')
        paid=any('raw_response' in row or row.get('dispatch_status') in {'dispatch_intent','dispatch_attempted'}
            for row in part.get('batches',[]))
        overflow=(part.get('reason')=='scope_complete_request_exceeds_current_capacity'
            and window and admission.get('request_bound',0)>window and not paid)
        if overflow and not core and len(local)>1:
            midpoint=len(local)//2
            visit(local[:midpoint],prefix+'0');visit(local[midpoint:],prefix+'1')
            return True
        decisions.update(values)
        state['support_reuse'].update(part.get('support_reuse') or {})
        state['support_reuse_contexts'].update(part.get('support_reuse_contexts') or {})
        if overflow:state['blocked_view_ids'].append(prefix)
        checkpoint()
        return not overflow
    if visit([],'main',core=True):visit(appendix,'appendix')
    for key in all_keys-set(decisions):
        decisions[key]={'required':True,'role':'required','category':'core','depends_on':[],
            'dependencies_complete':False,'context_sufficient':False,
            'reason':'scope_main_or_appendix_context_unavailable','authority':'conservative_scope',
            'binding':selection_binding(scope,key,model,context_id,route_id)}
    for key,value in decisions.items():
        if not value.get('dependencies_complete'):
            known=(old.get(key) or {}).get('scope_decision') or {}
            value['depends_on']=list(dict.fromkeys([*value.get('depends_on',[]),
                *[item for item in known.get('depends_on',[]) if isinstance(item,str) and item in all_keys]]))
    state['local_fallback_claim_keys']=[key for key,value in decisions.items() if value.get('authority')=='conservative_scope']
    return _finish_scope(decisions,state,old,True,lambda value:checkpoint())
