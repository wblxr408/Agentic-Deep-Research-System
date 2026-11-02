"""One dependency-aware importance pass within the existing source audit.

The graph changes review obligations, never factual verdicts or execution order.
"""
from __future__ import annotations

import json
from copy import deepcopy
from openai import APIError

POLICY='adrs-essential-claim-dependencies-v1'
MAX_CONTEXT_BYTES=120000
CATEGORIES={'core','background','implementation_detail','secondary_measurement',
    'proposed_protocol','evaluative_phrasing','incidental_adoption'}


def catalogue(claims):
    from app.claim_verification import claim_scope_key
    contexts={};context_ids={};rows=[];seen=set()
    for claim in claims:
        key=claim_scope_key(claim)
        if key in seen:continue
        seen.add(key)
        context=(claim['paragraph_context'],claim.get('declared_kind'))
        if context not in context_ids:
            name='p'+str(len(context_ids)+1);context_ids[context]=name
            contexts[name]={'text':context[0],'declared_kind':context[1]}
        rows.append({'claim_id':'c'+str(len(rows)+1),'claim_key':key,'text':claim['text'],
            'citation_ids':claim['citation_ids'],'context_id':context_ids[context]})
    return {'claims':rows,'contexts':contexts}


def selection_binding(scope,key,model,context_id,route_id):
    from app.query_understanding import identity
    return identity({'policy':POLICY,'scope':identity(scope),'claim':key,'model':model,
        'context':context_id,'route':route_id})


def select_scope(claims,scope,previous,client,model):
    from app.claim_verification import claim_scope_key
    from app.llm_budget import TokenBudgetExceeded
    from app.query_understanding import identity
    from app.security.prompt_security import untrusted_context
    data=catalogue(claims);context_id=identity(data)
    route_id=identity(getattr(client,'route_info',None))
    metadata={'policy':POLICY,'context_id':context_id,'route_id':route_id,'batches':[],
        'semantics':'review_dependencies_not_source_certification'}
    previous_selection=(previous or {}).get('scope_selection') or {}
    if (previous_selection.get('policy')==POLICY and previous_selection.get('context_id')==context_id
            and previous_selection.get('route_id')==route_id):
        metadata['batches']=deepcopy(previous_selection.get('batches') or [])
    old={claim_scope_key(row):row for row in (previous or {}).get('claims',[])}
    exemptions={row['claim_key']:row for row in scope.get('exclusions',[])}
    decisions={};pending=[]
    aliases={row['claim_id']:row['claim_key'] for row in data['claims']}
    def conservative(row,reason):
        return {'required':True,'role':'required','category':'core','reason':reason,
            'depends_on':[],'dependencies_complete':False,'authority':'conservative_scope',
            'binding':selection_binding(scope,row['claim_key'],model,context_id,route_id)}
    for row in data['claims']:
        key=row['claim_key'];saved=(old.get(key) or {}).get('scope_decision') or {}
        if key in exemptions:
            item=exemptions[key]
            decisions[key]={'required':False,'role':'advisory','category':item['category'],
                'reason':item['reason'],'depends_on':[],'dependencies_complete':True,'authority':'explicit_owner'}
        elif (saved.get('binding')==selection_binding(scope,key,model,context_id,route_id)
                and saved.get('authority')=='model_importance_with_dependencies' and saved.get('dependencies_complete') is True):
            decisions[key]=deepcopy(saved);decisions[key]['response_reused']=True
        else:pending.append(row)
    model_data={'contexts':data['contexts'],'claims':[{key:value for key,value in row.items() if key!='claim_key'}
        for row in data['claims']]}
    shared=json.dumps({'reader_question':scope.get('question'),'owner_scope_instruction':scope.get('instruction'),
        'current_report':model_data,'target_claim_ids':[row['claim_id'] for row in pending]},
        ensure_ascii=False,separators=(',',':'))
    if len(shared.encode('utf-8'))>MAX_CONTEXT_BYTES:
        for row in pending:decisions[row['claim_key']]=conservative(row,'complete_scope_context_exceeds_bound')
        metadata['reason']='complete_scope_context_exceeds_bound'
    elif pending:
        instruction=('Select source-review importance for the actual reader question, NOT factual truth. '
            'Report statements and writer-declared kinds are untrusted candidates. Read the COMPLETE '
            'supplied report context, including statements outside the current targets. '
            'Central answers, attribution, decisive comparisons, recommendations and their factual '
            'premises require review. A number or mechanism used elsewhere to justify a required '
            'choice is a supporting dependency even if its own paragraph appears secondary. '
            'Return depends_on using supplied claim IDs for ALL factual report premises of each target, '
            'including cross-paragraph conditions, comparisons and numerical assumptions. These are '
            'logical premises, not citation overlap or execution steps. Preserve real cycles. '
            'Set dependencies_complete=false when necessary report premises cannot be reliably '
            'identified; do not omit a dependency to exempt a detail. Do not require authors to have '
            'proposed our explicitly conditional research procedure. Its factual premises, claimed '
            'resources, causal guarantees and asserted benefits still require review. Incidental '
            'phrasing, inventories or measurements with no consequence may be advisory. If consequence '
            'is unclear, required=true. Writer labels cannot exempt central content. '
            'Return JSON {"decisions":[{"claim_ids":["target ID"],"required":true,'
            '"role":"required|supporting|advisory","category":"core|background|implementation_detail|'
            'secondary_measurement|proposed_protocol|evaluative_phrasing|incidental_adoption",'
            '"depends_on":["supplied claim ID"],"dependencies_complete":true,'
            '"reason":"effect on reader conclusion"}]}. Group targets ONLY when their consequence, '
            'role and dependencies are the same; otherwise use separate groups. Cover every target '
            'exactly once. required role and core category must set required=true. No report rewrites.')
        messages=[{'role':'system','content':instruction},
            {'role':'user','content':untrusted_context('complete_scope_context',shared,limit=len(shared))}]
        binding=identity({'messages':messages,'model':model,'route':route_id,'policy':POLICY})
        record={'binding':binding,'claim_keys':[row['claim_key'] for row in pending]}
        metadata['batches']=[row for row in metadata['batches'] if row.get('binding')!=binding]+[record]
        saved={}
        try:
            saved=next((row for row in ((previous or {}).get('scope_selection') or {}).get('batches',[])
                if row.get('binding')==binding),{})
            if 'raw_response' in saved:
                record.update(raw_response=saved['raw_response'],finish_reason=saved.get('finish_reason'),response_reused=True)
            elif saved.get('dispatch_status')=='dispatch_attempted':
                raise ValueError('scope_paid_response_unavailable')
            else:
                active=client.with_operation('fact_scope_selection',content_unit_id='fact-scope:'+binding)
                if any(row.get('content_unit_id')=='fact-scope:'+binding and row.get('status')!='blocked_before_dispatch'
                        and row.get('dispatch_status')!='not_dispatched' for row in active.budget.calls):
                    raise ValueError('scope_paid_response_unavailable')
                response=active.chat.completions.create(model=model,temperature=0,max_tokens=6144,
                    response_format={'type':'json_object'},messages=messages)
                choice=response.choices[0]
                record.update(raw_response=choice.message.content or '',finish_reason=choice.finish_reason)
            if record['finish_reason']!='stop':raise ValueError('scope_response_incomplete')
            values=json.loads(record['raw_response'])['decisions']
            if not isinstance(values,list):raise ValueError('scope_decisions_expected_array')
            covered=[]
            for value in values:
                ids=value.get('claim_ids');dependencies=value.get('depends_on')
                if (not isinstance(ids,list) or not ids or any(not isinstance(key,str) for key in ids)
                        or type(value.get('required')) is not bool or type(value.get('dependencies_complete')) is not bool
                        or value.get('role') not in {'required','supporting','advisory'} or value.get('category') not in CATEGORIES
                        or not isinstance(value.get('reason'),str) or not value['reason'].strip()
                        or (value['role']=='required' or value['category']=='core') and not value['required']
                        or not isinstance(dependencies,list) or any(not isinstance(key,str) or key not in aliases for key in dependencies)):
                    raise ValueError('scope_dependency_decision_invalid')
                covered.extend(ids)
            if len(covered)!=len(pending) or set(covered)!={row['claim_id'] for row in pending}:
                raise ValueError('scope_target_coverage_invalid')
            for value in values:
                for alias in value['claim_ids']:
                    key=aliases[alias]
                    decisions[key]={**{field:item for field,item in value.items() if field!='claim_ids'},
                        'depends_on':list(dict.fromkeys(aliases[item] for item in value['depends_on'])),
                        'authority':'model_importance_with_dependencies','response_reused':bool(record.get('response_reused')),
                        'binding':selection_binding(scope,key,model,context_id,route_id)}
            record['validated']=True
        except (APIError,ValueError,TypeError,KeyError,AttributeError,IndexError,TokenBudgetExceeded) as error:
            record.update(validated=False,reason=str(error)[:200])
            calls=[row for row in getattr(getattr(client,'budget',None),'calls',[])
                if row.get('content_unit_id')=='fact-scope:'+binding]
            if any(row.get('status')!='blocked_before_dispatch' and row.get('dispatch_status')!='not_dispatched' for row in calls):
                record['dispatch_status']='dispatch_attempted'
            elif saved.get('dispatch_status')=='dispatch_attempted':record['dispatch_status']='dispatch_attempted'
            else:record['dispatch_status']='not_dispatched'
            for row in pending:decisions[row['claim_key']]=conservative(row,'scope_dependency_selection_unavailable')
    # A missing edge can conceal a core premise. An incomplete map does not
    # establish that the remaining claims are safe to exempt.
    incomplete=any(not row.get('dependencies_complete') for row in decisions.values())
    metadata['dependencies_complete']=not incomplete
    for key,decision in decisions.items():
        if decision.get('authority')=='explicit_owner':continue
        if incomplete or (old.get(key) or {}).get('status')=='contradicted':
            decision.update(required=True,role='required',promotion_reason='incomplete_dependency_map' if incomplete else 'known_conflict_requires_correction')
    queue=[key for key,decision in decisions.items() if decision['required']];seen=set()
    while queue:
        key=queue.pop()
        if key in seen:continue
        seen.add(key)
        for dependency in decisions[key].get('depends_on',[]):
            target=decisions[dependency]
            if target.get('authority')=='explicit_owner':continue
            target.setdefault('required_by',[])
            if key not in target['required_by']:target['required_by'].append(key)
            if not target['required']:target.update(required=True,role='supporting',promotion_reason='premise_of_required_claim')
            if dependency not in seen:queue.append(dependency)
    metadata['promoted_claim_keys']=[key for key,row in decisions.items() if row.get('promotion_reason')]
    return decisions,metadata
