"""One bounded content correction; retain the original report and its audit."""
from __future__ import annotations

import json
import re
from copy import deepcopy

from openai import APIError

from app.claim_verification import audit_report, module_paragraph_kinds
from app.llm_budget import TokenBudgetExceeded, budgeted_client, request_token_bound
from app.organization_purpose import ModuleReportDraft, assemble_module_report, report_prose
from app.security.prompt_security import untrusted_context


def revise_report_claims(content, record, audit, *, configuration, statistics, evidence,
                         client, model, budget, deadline, citation_count, upgrade_callback=None, task_context=None):
    """Only change mapped paragraph text, then audit the whole resulting report."""
    if not audit.get('needs_review') or audit.get('audit_incomplete') or audit.get('budget_incomplete'):
        return content,record,audit
    paragraphs=[]
    for index,item in enumerate(record.get('summary',[])):
        paragraphs.append(('summary',index,item))
    for module in record['modules']:
        for section in ('paragraphs','appendix'):
            for index,item in enumerate(module.get(section,[])):
                paragraphs.append((module['module_id']+':'+section,index,item))
    targets=[];excerpts={}
    for section,index,item in paragraphs:
        wire=(report_prose(item['rendered_text'])+' '+ ' '.join(f'[citation:{n}]' for n in item['citations'])).rstrip()
        failed=[row for row in audit.get('claims',[]) if row['status']!='supported'
                and row.get('paragraph_context')==wire]
        if not failed:continue
        key=f'{section}:{index}'
        targets.append({'paragraph_id':key,'text':item['text'],'kind':item['kind'],
            'citations':item['citations'],'issues':[{'text':row['text'],'reason':row['reason'],
                'status':row['status'],'excerpt_ids':[ex['excerpt_id'] for ex in row['excerpts']]} for row in failed]})
        for row in failed:
            for ex in row['excerpts']:
                excerpts[ex['excerpt_id']]={field:ex[field] for field in ('excerpt_id','evidence_id','citation_id','quote')}
    reply=None
    def retain(reason,attempted=False):
        audit['revision_attempt']={'attempted':attempted,'status':reason,'paragraph_count':len(targets),
            'raw_response':reply}
        return content,record,audit
    if not targets or len(targets)>12:return retain('unmapped_or_too_many_paragraphs')
    payload=json.dumps({'paragraphs':targets,'excerpts':list(excerpts.values())},ensure_ascii=False)
    messages=[{'role':'system','content':
        'Correct only the supplied paragraphs against their cited excerpts. Preserve supported facts, '
        'conditions and scope. Narrow or remove unsupported clauses; resolve contradictions using the evidence. '
        'Do not invent a result, endorse an action on behalf of an author, add claims, change citation numbers '
        'or introduce statistic placeholders. Do not replace substance with generic defensive language. '
        'Keep factual premises distinct from the proposed interpretation or action. '
        'Return JSON {"repairs":[{"paragraph_id":"exact supplied ID","text":"corrected plain prose"}]}, '
        'exactly once for every supplied ID; no other fields.'},
        {'role':'user','content':untrusted_context('report_content_correction',payload,limit=len(payload))}]
    required=request_token_bound(messages,response_format={'type':'json_object'})+1024
    if budget.available('report')<required or budget.available('audit')<2048:
        return retain('original_allowance_insufficient')
    # Persist the old draft, paid audit and routing decision before another
    # provider call. A checkpoint failure must reach the root pause handler.
    if upgrade_callback is not None:
        conflicts=[row for row in audit.get('claims',[]) if row.get('status')=='contradicted'
            and row.get('model_verdict') and row.get('excerpts')]
        trigger='source_conflict' if conflicts else 'evidence_gap'
        replacement=upgrade_callback(trigger,{'paragraph_ids':[item['paragraph_id'] for item in targets],
            'conflicting_claim_count':len(conflicts)},required)
        if replacement is not None:client,model=replacement
    try:
        response=client.chat.completions.create(model=model,messages=messages,temperature=0,
            max_tokens=min(4096,budget.available('report')-required+1024),response_format={'type':'json_object'})
        reply=response.choices[0].message.content
        if response.choices[0].finish_reason!='stop':return retain('correction_incomplete',True)
        changes=json.loads(reply).get('repairs',[])
        ids=[item['paragraph_id'] for item in changes]
        expected={item['paragraph_id'] for item in targets}
        if set(ids)!=expected or len(ids)!=len(expected):return retain('correction_ids_invalid',True)
        original=record['raw_model_response'].strip()
        if original.startswith('```json') and original.endswith('```'):original=original[7:-3].strip()
        draft=ModuleReportDraft.model_validate_json(original).model_dump(mode='json')
        replacements={item['paragraph_id']:item['text'] for item in changes}
        for target in targets:
            text=replacements[target['paragraph_id']]
            if not isinstance(text,str) or not text.strip():return retain('empty_correction',True)
            if not set(re.findall(r'\{stat:([^{}]+)\}',text))<=set(re.findall(r'\{stat:([^{}]+)\}',target['text'])):
                return retain('new_statistic_rejected',True)
            parts=target['paragraph_id'].split(':')
            destination=draft['summary'] if parts[0]=='summary' else next(
                module for module in draft['modules'] if module['module_id']==parts[0])[parts[1]]
            destination[int(parts[-1])]['text']=text
        revised,new_record=assemble_module_report(json.dumps(draft,ensure_ascii=False),configuration,citation_count,statistics=statistics)
        if new_record['issues']:return retain('correction_contract_invalid',True)
        bound=[{'rendered_paragraph':item['rendered_text'],**binding} for item in [
            *new_record.get('summary',[]),*[item for module in new_record['modules']
                for item in [*module['paragraphs'],*module.get('appendix',[])]]]
            for binding in item.get('statistic_bindings',[])]
        new_audit=audit_report(revised,evidence,client=budgeted_client(client,budget,'audit'),model=model,
            token_budget=budget.available('audit'),deadline=deadline,bound_statistics=bound,
            paragraph_kinds=module_paragraph_kinds(new_record), task_context=task_context)
        new_record['semantic_revision']={'original_record':deepcopy(record),'original_audit':deepcopy(audit),
            'revised_paragraph_ids':ids,'attempts':1}
        new_audit['revision_attempt']={'attempted':True,'status':'reaudited','paragraph_count':len(targets)}
        return revised,new_record,new_audit
    except (APIError,OSError,ValueError,KeyError,TypeError,AttributeError,StopIteration,TokenBudgetExceeded) as error:
        return retain(type(error).__name__,True)
