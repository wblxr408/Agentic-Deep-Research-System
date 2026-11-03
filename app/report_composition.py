"""Compose bounded report sections from whole retained research records."""
from __future__ import annotations

import json
import re

from app.llm_budget import TokenBudgetExceeded, request_token_bound
from app.organization_purpose import ModuleReportDraft, MODULES, CHAPTER_RESPONSIBILITIES, REPORT_MATERIAL_POLICY, REPORT_MATERIAL_POLICIES, report_draft_model
from app.research_context import _paragraph_window
from app.security.prompt_security import untrusted_context
from app.query_understanding import identity


def compose_sections(*,question,analysis,configuration,findings,evidence,statistics,
                     system_prompt,client,model,budget,on_section,retained_sections=None):
    findings=findings or {}
    assembled_model=report_draft_model(configuration)
    material_policy=configuration.get('report_material_policy')
    if material_policy is not None and material_policy not in REPORT_MATERIAL_POLICIES:
        raise TokenBudgetExceeded('report_material_policy_unsupported')
    owned_input=material_policy in REPORT_MATERIAL_POLICIES
    ownership=material_policy==REPORT_MATERIAL_POLICY
    input_version='structured-section-input-v4' if ownership else 'structured-section-input-v3' if owned_input else 'structured-section-input-v2'
    chapter_plan={'version':material_policy,'chapters':[
        {'module_id':module,'reader_question':MODULES[module][1],
         'responsibility':CHAPTER_RESPONSIBILITIES[module]} for module in configuration['modules']]}
    works=(findings.get('scope_result') or {}).get('outputs') or []
    cards=(findings.get('technical_reading') or {}).get('cards') or []
    metadata=findings.get('publication_metadata') or {}
    numbers={source.evidence_id:index for index,source in enumerate(evidence,1)}
    sources={source.evidence_id:source for source in evidence
        if (source.acquisition or {}).get('coverage')!='discovery_only'}
    sections=[];manifest={'version':'adrs-section-composition-v1','sections':[],'sources':[],
        'material_policy':material_policy,'application_response_reuse':[]}
    if configuration.get('report_assembly_policy'):
        manifest['assembly_policy']=configuration['report_assembly_policy']
    if owned_input:manifest['chapter_plan']=chapter_plan
    assigned_judgments={module:{} for module in configuration['modules']}

    def material(module,assigned,*,focused=False):
        work_ids={row['output_id'] for row in assigned}
        technical=[row for row in cards if row.get('output_id') in work_ids]
        if configuration.get('mechanism_graph_policy'):
            technical=[{key:value for key,value in row.items() if key!='mechanism_graph'} for row in technical]
        if focused and module not in {'deep_dive','validation'}:
            fields={'problem','method_overview','innovation'} if module in {'landscape','relationships'} else {
                'problem','method_overview','mechanism','innovation','conditions','limitations'}
            if owned_input:fields|={'conditions','limitations','prior_limitations'}
            technical=[{**row,'fields':{key:value for key,value in row.get('fields',{}).items() if key in fields},
                'field_scope':'chapter_selection_full_card_retained_for_deep_dive'} for row in technical]
        judgments=[row for row in (findings.get('research_judgments') or {}).get('records',[])
            if not row.get('related_output_ids') or set(row['related_output_ids']) & work_ids]
        judgment_references=[]
        if ownership:
            from app.research_judgments import ContentPlacement
            selected=[]
            for row in judgments:
                placement=None
                if row.get('content_placement'):
                    try:
                        placement=ContentPlacement.model_validate(row['content_placement']).for_modules(assigned_judgments)
                    except ValueError:pass
                if placement:
                    use=next((item for item in placement.supporting_uses if item.module_id==module),None)
                    if placement.owner_module!=module and use is None:continue
                    row={**row,'writing_role':'develop' if placement.owner_module==module else 'apply',
                        'reader_use':use.reader_use if use else placement.reason}
                else:
                    row={**row,'writing_role':'placement_unresolved_preserve_candidate'}
                    unresolved=manifest.setdefault('unassigned_judgment_ids',[])
                    if row['judgment_id'] not in unresolved:unresolved.append(row['judgment_id'])
                if row['judgment_id'] in assigned_judgments[module]:
                    judgment_references.append({**{key:row[key] for key in
                        ('judgment_id','question','conclusion','observations','basis','alternatives','choice','content_placement','reader_use') if key in row},
                        'writing_role':'reference_to_assigned_argument',
                        'assigned_section_id':assigned_judgments[module][row['judgment_id']]})
                    continue
                selected.append(row)
            judgments=selected
        actions=findings.get('actions') if module=='actions' else None
        relationships=findings.get('relationship_view') if module in {'relationships','evolution'} else None
        trends=findings.get('trend_view') if module in {'evolution','validation'} else None
        ranges={};missing=[]
        def proofs(value):
            if isinstance(value,dict):
                key=value.get('evidence_id');quote=value.get('quote')
                if isinstance(key,str) and isinstance(quote,str) and quote.strip():
                    source=sources.get(key)
                    start=source.content.find(quote) if source else -1
                    if start>=0:ranges.setdefault(key,[]).append((start,start+len(quote)) if focused and not owned_input
                        else _paragraph_window(source.content,start,start+len(quote)))
                    else:missing.append({'evidence_id':key,'reason':'retained_proof_not_in_current_acquired_text'})
                for item in value.values():proofs(item)
            elif isinstance(value,(list,tuple)):
                for item in value:proofs(item)
        proofs(technical);proofs(judgments);proofs(judgment_references);proofs(actions);proofs(relationships);proofs(trends)
        for work in assigned:
            proofs(work.get('affiliations'))
            for key in (metadata.get(work['output_id']) or {}).get('evidence_ids',[]):
                source=sources.get(key)
                if not source:continue
                pages=(source.acquisition or {}).get('pages') or []
                end=pages[0].get('end') if pages else None
                if type(end) is not int or not 0<end<=len(source.content):end=min(3000,len(source.content))
                ranges.setdefault(key,[]).append((0,end))
        passages=[]
        for key,items in sorted(ranges.items()):
            merged=[]
            for start,end in sorted(items):
                if merged and start<=merged[-1][1]:merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
                else:merged.append((start,end))
            source=sources[key]
            passages.append({'evidence_id':key,'citation':numbers[key],'url':source.source_url,
                'excerpts':[{'start':start,'end':end,'text':source.content[start:end]} for start,end in merged]})
        section_analysis=re.search(r'(?ms)^## '+re.escape(MODULES[module][0])+r'\s*\n(.*?)(?=^## |\Z)',analysis)
        def located(value):
            if isinstance(value,list):return [located(item) for item in value]
            if isinstance(value,tuple):return [located(item) for item in value]
            if not isinstance(value,dict):return value
            result={key:located(item) for key,item in value.items()}
            source=sources.get(value.get('evidence_id'));quote=value.get('quote')
            if source and isinstance(quote,str) and quote and (start:=source.content.find(quote))>=0:
                result.pop('quote',None)
                result.update(start=start,end=start+len(quote),proof_location='sources.excerpts')
            return result
        selected_statistics=statistics
        if focused:
            selected_statistics=None
            if module=='landscape' and statistics:
                selected_statistics={'metric_registry':{key:value for key,value in statistics.get('metric_registry',{}).items()
                    if key.startswith('sample:')},'sample_status':statistics.get('sample_status'),
                    'reader_use':statistics.get('reader_use'),
                    'selection_scope':'sample_only_full_registry_retained_for_figures_and_research_record'}
        packet={'question':question,'module':module,'assigned_works':assigned,
            'technical_cards':technical,'judgments':judgments,'actions':actions,'relationships':relationships,
            'trends':trends,'statistics':selected_statistics,
            'analysis':section_analysis[1] if section_analysis else None if owned_input else analysis,
            'sources':passages,'missing_proofs':missing}
        if ownership:packet['judgment_references']=judgment_references
        if owned_input:
            packet['chapter_plan']=chapter_plan
            packet['analysis_selection']={'status':'module_section' if section_analysis else 'module_section_unavailable',
                'fallback':'structured_material_and_original_passages','whole_analysis_included':False}
        return {key:value if key=='sources' else located(value) for key,value in packet.items()}

    def messages_for(payload,instruction):
        raw=json.dumps(payload,ensure_ascii=False,separators=(',',':'),sort_keys=True)
        system={'role':'system','content':system_prompt+'\n'+instruction}
        if not owned_input or 'sources' not in payload:
            return [system,{'role':'user','content':untrusted_context('section_research',raw,limit=len(raw))}]
        # Stable instructions and actual source windows precede the changing
        # chapter task. One provider request, no cache warm-up or source summary.
        shared=json.dumps({key:payload[key] for key in ('chapter_plan','sources')},
            ensure_ascii=False,separators=(',',':'),sort_keys=True)
        task=json.dumps({key:value for key,value in payload.items() if key not in {'chapter_plan','sources'}},
            ensure_ascii=False,separators=(',',':'),sort_keys=True)
        return [system,
            {'role':'user','content':untrusted_context('section_research_sources',shared,limit=len(shared))},
            {'role':'user','content':untrusted_context('section_research_task',task,limit=len(task))}]

    def ask(payload,instruction,output_tokens,section_id,context,validate):
        messages=messages_for(payload,instruction)
        bound={'system':messages[0]['content'],'payload':payload,
            'model':model,'section_id':section_id,'version':input_version}
        if owned_input:bound['messages']=messages
        section_binding=identity(bound)
        context={**context,'section_binding_version':input_version}
        retained=(retained_sections or {}).get(section_id)
        if retained:
            old_context=retained.get('report_context') or {}
            exact=old_context.get('section_binding_version')==input_version and old_context.get('section_input_id')==section_binding
            # Legacy string bindings were sensitive to JSONB object key order.
            # Only the protected loader may attest the original root inputs;
            # reuse remains an unreviewed candidate, with fresh final audits.
            legacy=(not owned_input and not old_context.get('section_binding_version')
                and retained.get('validated_root_input') is True
                and old_context.get('assigned_output_ids')==context.get('assigned_output_ids'))
            if retained.get('model')!=model or not (exact or legacy):
                raise TokenBudgetExceeded('section_writing_inputs_changed')
            reply=retained['raw_model_response']
            manifest['application_response_reuse'].append({'operation':'section_writing',
                'content_unit_id':section_id,'input_binding':section_binding,
                'basis':'exact_current_input_and_model' if exact else 'protected_legacy_root_candidate',
                'effect':'initial_model_request_avoided_not_review_approval',
                'saved_tokens':None,'saved_cost_usd':None})
        else:
            required=request_token_bound(messages,response_format={'type':'json_object'})+output_tokens
            if required>budget.available('report'):raise TokenBudgetExceeded('section_writing_original_allowance_insufficient')
            active=client.with_operation('section_writing',content_unit_id=section_id) if hasattr(client,'with_operation') else client
            response=active.chat.completions.create(model=model,messages=messages,temperature=.2,
                max_tokens=output_tokens,response_format={'type':'json_object'})
            choice=response.choices[0] if response.choices else None
            reply=choice.message.content or '' if choice else ''
            on_section(reply,section_id,{**context,'section_input_id':section_binding,
                'finish_reason':choice.finish_reason if choice else None})
            if choice is None or choice.finish_reason!='stop':raise TokenBudgetExceeded('section_writing_response_incomplete')
        try:return validate(reply)
        except (ValueError,TypeError,KeyError) as error:
            if (retained and (retained.get('report_context') or {}).get('repair_attempted')
                    and not (retained.get('report_context') or {}).get('repair_admission_denied')):
                raise TokenBudgetExceeded('section_writing_repair_exhausted') from error
            # Persist the consumed attempt and original response before dispatch.
            # A crash cannot reset this section's correction allowance.
            repair_context={**context,'section_input_id':section_binding,'repair_attempted':True,
                'original_response':reply,'repair_reason':type(error).__name__}
            on_section(reply,section_id,repair_context)
            repair_payload=json.dumps({'invalid_section':reply,'validation_error':str(error)[:2000],
                'assigned_works':payload.get('assigned_works'),'sources':payload.get('sources'),
                'statistics':payload.get('statistics'),'question':payload.get('question'),
                'allowed_citations':[row['citation'] for row in payload.get('sources',[])]},ensure_ascii=False)
            repair_messages=[messages[0],{'role':'user','content':
                'Repair only this section against the original schema and supplied source numbers. '
                'Preserve its supported substance and conditions. Return the complete corrected section; '
                'do not write other chapters or a whole report. The complete assigned source windows are supplied '
                'here; previous analytical summaries are not factual authority. Remove or correct statements '
                'about unassigned works rather than retaining an unsupplied citation.\n'+
                untrusted_context('section_repair',repair_payload,limit=len(repair_payload))}]
            required=request_token_bound(repair_messages,response_format={'type':'json_object'})+output_tokens
            if required>budget.available('report'):
                on_section(reply,section_id,{**repair_context,'repair_admission_denied':True})
                raise TokenBudgetExceeded('section_repair_original_allowance_insufficient')
            active=client.with_operation('section_format_repair',content_unit_id=section_id) if hasattr(client,'with_operation') else client
            response=active.chat.completions.create(model=model,messages=repair_messages,temperature=.1,
                max_tokens=output_tokens,response_format={'type':'json_object'})
            choice=response.choices[0] if response.choices else None
            repaired=choice.message.content or '' if choice else ''
            on_section(repaired,section_id,{**repair_context,'finish_reason':choice.finish_reason if choice else None})
            if choice is None or choice.finish_reason!='stop':raise TokenBudgetExceeded('section_writing_repair_incomplete')
            try:return validate(repaired)
            except (ValueError,TypeError,KeyError) as failure:
                raise TokenBudgetExceeded('section_writing_repair_exhausted') from failure

    # Validated module completion, not raw response persistence, reduces the
    # forecast. Reused sections go through the same validator before counting.
    budget.remaining_writing_units=len(configuration['modules'])+2
    for module in configuration['modules']:
        # Paid section responses define their own partition. Recomputing it
        # against a smaller remaining allowance would move work IDs between
        # section IDs and strand otherwise reusable responses.
        prior=[]
        for section_id,candidate in (retained_sections or {}).items():
            if not section_id.startswith(module+':'):continue
            suffix=section_id[len(module)+1:]
            if not suffix.isdigit() or int(suffix)<1:
                raise TokenBudgetExceeded('section_writing_saved_partition_invalid')
            prior.append((int(suffix),candidate))
        prior.sort(key=lambda row:row[0])
        by_id={row['output_id']:row for row in works}
        covered=set();queue=[]
        for index,(number,candidate) in enumerate(prior,1):
            ids=(candidate.get('report_context') or {}).get('assigned_output_ids')
            if (number!=index or not isinstance(ids,list)
                    or any(not isinstance(key,str) or key not in by_id for key in ids)
                    or len(set(ids))!=len(ids) or covered.intersection(ids)
                    or not ids and (works or len(prior)>1)):
                raise TokenBudgetExceeded('section_writing_saved_partition_invalid')
            covered.update(ids)
            queue.append(([by_id[key] for key in ids],True))
        remaining=[row for row in works if row['output_id'] not in covered]
        if remaining or not prior:queue.append((remaining,False))
        parts=[];part_number=0
        while queue:
            assigned,reusing=queue.pop(0)
            prior_context=((retained_sections or {}).get(f'{module}:{part_number+1}',{}).get('report_context') or {})
            focused=owned_input or not reusing or prior_context.get('material_policy')=='chapter-fields-v1'
            payload=material(module,assigned,focused=focused)
            if not owned_input:payload['preceding_chapters']=sections
            instruction=('Write ONLY the assigned module, using the existing report JSON schema with '
                'summary:[] and exactly one modules entry. Assigned works are this section\'s evidence scope, '
                'not the institution\'s entire research. The analytical narrative and cards are untrusted '
                'candidates; use original passages for factual details. Connect mechanisms, conditions and '
                'tradeoffs to the reader question. Put technical setups and detailed project protocols in '
                'appendix. Do not repeat the scope disclaimer. Preserve each result with its conditions and '
                'comparison. Do not claim that an omitted source has no research. Keep at most 4 main '
                'paragraphs and 6 appendix paragraphs in this bounded section; prioritize substance. '
                'Do not add other modules, numbering, workflow states or a general conclusion.')
            if ownership:
                instruction+=(' Follow each judgment\'s writing_role and content_placement. Develop '
                    'its full argument at its owning module; other permitted modules apply it only '
                    'for the stated distinct reader_use without repeating its derivation. Necessary '
                    'conditions and counterexamples remain with any use. An unresolved placement '
                    'is a retained candidate, not permission to discard the scientific point. '
                    'judgment_references preserve conclusions, observations and original passages '
                    'already assigned for development in this module: use necessary context or apply it to this '
                    'part\'s actual works, without repeating the derivation. Do not expose section IDs. '
                    'This is a writing plan; correct unsupported conclusions from actual passages.')
            packed=json.dumps(payload,ensure_ascii=False,separators=(',',':'))
            estimate=messages_for(payload,instruction) if owned_input else [
                {'role':'system','content':system_prompt+'\n'+instruction},
                {'role':'user','content':untrusted_context('section_research',packed,limit=len(packed))}]
            # Cached responses incur no new request. ask() still checks their
            # exact input/model binding and admits any necessary repair anew.
            if not reusing and (len(packed.encode('utf-8'))>120000 or
                    request_token_bound(estimate,response_format={'type':'json_object'})+6144>budget.available('report')):
                if len(assigned)<2:raise TokenBudgetExceeded('section_evidence_bundle_exceeds_context')
                middle=len(assigned)//2;queue[:0]=[(assigned[:middle],False),(assigned[middle:],False)]
                continue
            part_number+=1
            section_id=f'{module}:{part_number}'
            def validate_section(raw):
                draft=ModuleReportDraft.model_validate_json(raw)
                if len(draft.modules)!=1 or draft.modules[0].module_id!=module:
                    raise ValueError('section_writing_module_mismatch')
                part=draft.modules[0].model_dump(mode='json')
                # A model may put this chapter's lead in the global summary
                # envelope. Preserve those paragraphs in the assigned chapter;
                # do not spend another call merely moving JSON fields.
                combined=[row.model_dump(mode='json') for row in draft.summary]+part['paragraphs']
                seen=set();part['paragraphs']=[]
                for row in combined:
                    key=identity(row)
                    if key not in seen:part['paragraphs'].append(row);seen.add(key)
                ModuleReportDraft.model_validate({'title':draft.title,'summary':[],'modules':[part]})
                allowed={row['citation'] for row in payload['sources']}
                if any(not set(row['citations'])<=allowed for row in [*part['paragraphs'],*part['appendix']]):
                    raise ValueError('section_writing_unsupplied_citation')
                return part
            part=ask(payload,instruction,6144,section_id,{'assigned_output_ids':[row['output_id'] for row in assigned],
                'material_policy':material_policy if owned_input else 'chapter-fields-v1' if focused else 'legacy-full-fields',
                'sources':payload['sources'],'missing_proofs':payload['missing_proofs']},validate_section)
            parts.append(part)
            if ownership:assigned_judgments[module].update({row['judgment_id']:section_id for row in payload['judgments']})
            manifest['sections'].append({'section_id':section_id,'output_ids':[row['output_id'] for row in assigned],
                **({'judgment_ids':[row['judgment_id'] for row in payload['judgments']]} if ownership else {}),
                'evidence_ids':[row['evidence_id'] for row in payload['sources']],
                'missing_proofs':payload['missing_proofs']})
            manifest['sources'].extend({'evidence_id':row['evidence_id'],'citation_id':'citation:'+str(row['citation']),
                'excerpts':[{'start':part['start'],'end':part['end']} for part in row['excerpts']]} for row in payload['sources'])
        sections.append({'module_id':module,'paragraphs':[row for part in parts for row in part['paragraphs']],
            'appendix':[row for part in parts for row in part['appendix']]})
        budget.remaining_writing_units=len(configuration['modules'])-len(sections)+2
    from app.report_editorial import select_paragraphs
    retained_selection=(retained_sections or {}).get('editorial-selection') or {}
    saved_selection=json.loads(retained_selection['raw_model_response']) if retained_selection.get('raw_model_response') else None
    def save_selection(value):
        on_section(json.dumps(value,ensure_ascii=False),'editorial-selection',{'section_input_id':value['binding']})
    sections,selection=select_paragraphs(sections,question=question,client=client,model=model,budget=budget,
        retained=saved_selection,on_saved=save_selection,configuration=configuration)
    manifest['editorial_selection']=selection
    manifest['application_response_reuse'].extend(selection.get('application_response_reuse') or [])
    if configuration.get('report_assembly_policy'):
        # Assembly defects cannot be repaired by paying to rewrite the lead.
        assembled_model.model_validate({'title':'assembled report','summary':[],'modules':sections})
    # The lead is written last from completed sections, never from an early
    # compressed evidence sample. Its new claims are still audited below.
    def validate_lead(raw):
        lead=json.loads(raw)
        result=assembled_model.model_validate({'title':lead['title'],'summary':lead['summary'],'modules':sections})
        used={ref for section in sections for row in [*section['paragraphs'],*section['appendix']] for ref in row['citations']}
        if any(not set(row.citations)<=used for row in result.summary):raise ValueError('lead_writing_new_citation')
        return result
    # The lead consumes chapter judgments, not a duplicate of the appendix.
    # Whole sections remain above and are assembled unchanged for full audit.
    lead_sections=[{'module_id':row['module_id'],'judgments':row['paragraphs']}
        for row in sections]
    result=ask({'question':question,'chapter_judgments':lead_sections},
        'Return JSON with title and summary only. Write a concise research title and up to five substantive '
        'leading judgments grounded in the completed sections. Summary paragraphs use text/kind/citations '
        'as in the report schema. Reuse only citations present in these sections; introduce no new facts. '
        'Do not return modules or repeat chapter inventories.',3072,'lead',
        {'based_on_completed_sections':[row['section_id'] for row in manifest['sections']]},validate_lead)
    manifest['semantics']='whole_selected_evidence_windows_not_independent_semantic_approval'
    budget.remaining_writing_units=0
    return result.model_dump_json(),manifest
