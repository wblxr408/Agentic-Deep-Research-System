"""
Analyst Agent: reasoning, synthesis, and comparison of collected evidence.

Produces a structured analysis with evidence attribution.
"""

from __future__ import annotations

import json
import logging
import re
from copy import deepcopy
from collections.abc import Callable
from typing import TYPE_CHECKING
from openai import APIError

from app.config import get_settings
from app.llm_budget import budgeted_client, skill_context_client, TokenBudgetExceeded
from app.graph.state import Evidence
from app.guardrails import build_guardrail_decision, build_prompt_profile_message
from app.llm_client import (
    call_chat_with_fallback,
    collect_usage_metrics,
    create_fallback_llm_client,
)
from app.security.prompt_security import untrusted_context,research_method_context

if TYPE_CHECKING:
    from openai import OpenAI

logger = logging.getLogger(__name__)


def _decode_response_object(content: str, *, normalizations: list | None = None) -> tuple[object, int]:
    """Recover literal LF/CR/tab inside JSON strings, retaining their value.

    A complete object with one redundant final close retains the whole object.
    No arbitrary object search, delimiter completion, key invention or prose repair.
    Other malformed JSON is still rejected by the standard decoder.
    """
    text=content.strip()
    if text.startswith('```json') and text.endswith('```'):text=text[7:-3].strip()
    try:return json.loads(text),0
    except json.JSONDecodeError as error:
        if error.msg == 'Extra data' and text[error.pos:] == '}':
            complete = json.loads(text[:error.pos])
            if isinstance(complete, dict):
                if normalizations is not None:
                    normalizations.append({'kind':'single_redundant_final_object_close',
                        'cleaned_response_offset':error.pos})
                return complete,0
        if not error.msg.startswith('Invalid control character'):raise
    quoted=False;escaped=False;repairs=0;parts=[]
    for char in text:
        if quoted and not escaped and char in '\n\r\t':
            parts.append({'\n':'\\n','\r':'\\r','\t':'\\t'}[char]);repairs+=1;continue
        parts.append(char)
        if escaped:escaped=False
        elif quoted and char=='\\':escaped=True
        elif char=='"':quoted=not quoted
    return json.loads(''.join(parts)),repairs


class AnalystAgent:
    """
    Synthesizes evidence from multiple agents into a coherent analysis.

    Uses structured output to ensure parseable, evidence-linked analysis.
    """

    SYSTEM_PROMPT = """You are a senior business research analyst. Your role is to synthesize diverse evidence into a structured, well-reasoned analysis.

## Analysis Framework

1. **Fact vs. Inference**: Clearly distinguish hard facts from analyst inferences
2. **Evidence Attribution**: Every key claim must cite its source using [citation:N] format
3. **Conflict Resolution**: Identify contradictions between sources and provide judgment
4. **Confidence Assessment**: Rate each major finding as HIGH/MEDIUM/LOW confidence
5. **Completeness Check**: Ensure all research dimensions are covered

## Response Format

Return a JSON object with these fields:
- "findings": array of {finding, evidence_ids, confidence, category}
- "data_points": array of {value, source_citation, context}
- "conflicts": array of {claim_a, claim_b, resolution}
- "gaps": array of {topic, severity} for areas needing more research
- "analysis_text": comprehensive narrative analysis (main output)
"""

    def __init__(self):
        settings = get_settings()
        self.model = settings.llm.model
        self._client: OpenAI | None = None
        self.last_usage: dict | None = None
        self.request_budget = None
        self.last_organization_data: dict | None = None
        self.last_evidence_ids: list[str] = []
        self.last_extraction_status: dict = {}
        self.last_partial_response: str | None = None
        self.last_context_manifest: dict = {}
        self.last_workflow: dict = {}

    def _analyze_workflow(self, user_query, evidence_list, skill_prompt, analyst_hints,
                          configuration, resume_state, on_progress):
        """Sequential questions share one analyst, root allowance and checkpoint."""
        from app.research_context import (analysis_binding, identity_batches, QUESTION_SEED_VERSION,
            CONTEXT_PACKING_VERSION, LEGACY_CONTEXT_PACKING_VERSION, workflow_packing_version)
        from app.organization_purpose import MODULES
        from app.organization_findings import build_organization_findings
        modules=list(configuration.get('modules') or [])
        packing_version=workflow_packing_version(resume_state) if resume_state else CONTEXT_PACKING_VERSION
        if packing_version not in {CONTEXT_PACKING_VERSION,LEGACY_CONTEXT_PACKING_VERSION}:
            self.last_workflow=deepcopy(resume_state)
            raise TokenBudgetExceeded('analysis_context_contract_changed')
        self.context_packing_version=packing_version
        binding=analysis_binding(user_query,configuration,skill_prompt,analyst_hints,evidence_list,
            packing_version=packing_version)
        if isinstance(resume_state,dict) and resume_state and resume_state.get('question_seed_version')!=QUESTION_SEED_VERSION:
            self.last_workflow=deepcopy(resume_state)
            raise TokenBudgetExceeded('analysis_context_contract_changed')
        workflow=deepcopy(resume_state) if isinstance(resume_state,dict) and resume_state.get('binding')==binding else {
            'schema_version':'adrs-analysis-questions-v2','binding':binding,'question_seed_version':QUESTION_SEED_VERSION,
            'context_packing_version':packing_version,
            'completed':{},'attempts':{},'status':'running'}
        self.last_workflow=workflow

        def progress():
            if on_progress:on_progress(deepcopy(workflow))

        def phase(key, phase_config, kind, seed=None):
            if key in workflow['completed']:return workflow['completed'][key]
            attempts=workflow['attempts'].get(key,0)
            from app.recovery_policy import PHASE_ATTEMPT_LIMIT
            if attempts>=PHASE_ATTEMPT_LIMIT:raise TokenBudgetExceeded('analysis_phase_attempt_limit')
            self.phase_repair=(workflow.get('repairs') or {}).get(key) or {}
            workflow.update(active_phase=key,status='running')
            workflow['attempts'][key]=attempts+1
            try:
                progress()
                output_tokens=8192 if (kind=='extraction' or attempts
                    or 'deep_dive' in phase_config.get('modules',[])) else 4096
                output_tokens=int(self.phase_repair.get('output_tokens') or output_tokens)
                text=self.analyze(user_query,evidence_list,skill_prompt,analyst_hints,phase_config,
                    _phase=kind,_seed=seed,_output_tokens=output_tokens)
                record={'analysis_text':text,'organization_data':deepcopy(self.last_organization_data or {}),
                    'context':deepcopy(self.last_context_manifest),'extraction':deepcopy(self.last_extraction_status)}
                workflow.setdefault('attempt_records',{}).setdefault(key,[]).append({
                    'attempt':workflow['attempts'][key],**record})
                if workflow['attempts'][key]<2 and not (
                        packing_version==CONTEXT_PACKING_VERSION and kind=='question'
                        and 'deep_dive' in phase_config.get('modules',[])):
                    requested=set((seed or {}).get('identity_evidence_ids',[]))
                    for output in (seed or {}).get('outputs',[]):
                        requested.update(((seed or {}).get('publication_metadata',{}).get(output['output_id']) or {}).get('evidence_ids',[]))
                    full={item.evidence_id for item in evidence_list if (item.acquisition or {}).get('coverage')=='full_text'}
                    selected={item['evidence_id'] for item in self.last_context_manifest.get('sources',[])}
                    missing=sorted((requested & full)-selected)
                    if missing:
                        from app.model_routing import prepare_capability_upgrade
                        if prepare_capability_upgrade(self,'analyst','context_gap',evidence_present=True,
                                details={'phase_id':key,'omitted_full_text_ids':missing[:10]},
                                required_tokens=int(self.last_context_manifest.get('prompt_bound') or 0)+1024):
                            return phase(key,phase_config,kind,seed)
                workflow['completed'][key]=record
                for recovery in reversed(workflow.get('recovery_history') or []):
                    if recovery.get('phase')==key:
                        recovery['outcome']='resolved';break
                workflow.pop('partial_response',None)
                progress()
                return record
            except TokenBudgetExceeded as error:
                workflow.update(status='paused',stop_reason=error.reason,partial_response=self.last_partial_response)
                failed={'attempt':workflow['attempts'][key],
                    'reason':error.reason,'raw_response':self.last_partial_response,
                    'provider_error_type':self.last_extraction_status.get('reason') if error.reason=='analysis_provider_unavailable' else None,
                    'retry_after_seconds':self.last_extraction_status.get('retry_after_seconds'),
                    'provider_error_code':self.last_extraction_status.get('provider_error_code'),
                    'admission':deepcopy(getattr(error,'admission',None)),
                    'context':deepcopy(self.last_context_manifest)}
                failures=workflow.setdefault('failed_attempts',{}).setdefault(key,[])
                if not failures or failures[-1]!=failed:failures.append(failed)
                if workflow['attempts'][key]<2 and error.reason in {'analysis_output_incomplete','model_output_limit','insufficient_context_budget'}:
                    from app.model_routing import prepare_capability_upgrade
                    trigger='output_truncated' if error.reason=='model_output_limit' else (
                        'context_gap' if error.reason=='insufficient_context_budget' else 'format_failure')
                    admission=getattr(error,'admission',{})
                    if prepare_capability_upgrade(self,'analyst',trigger,
                            evidence_present=bool(evidence_list) if trigger=='context_gap' else bool(self.last_context_manifest.get('sources')),
                            details={'phase_id':key,'extraction_status':self.last_extraction_status.get('status')},
                            required_tokens=int(self.last_context_manifest.get('prompt_bound') or admission.get('prompt_bound') or 0)+1024):
                        return phase(key,phase_config,kind,seed)
                if error.reason!='analysis_checkpoint_unavailable':progress()
                raise

        extract_config={**configuration,'modules':[]}
        data={};extractions=[]
        selected_entities={item['entity_id'] for item in configuration['scope'].get('entities',[])}
        from app.query_understanding import identity
        for index,ids in enumerate(identity_batches(evidence_list)):
            phase_id=f'extract_publications:{index+1}'
            record=phase(phase_id,extract_config,'extraction',{'identity_evidence_ids':ids})
            proposal=deepcopy(record['organization_data']);extractions.append(record)
            # Model-local names such as paper-1 may recur in another batch.
            # Namespacing proposals does not merge or validate their meaning.
            output_ids={item['output_id']:'out-'+identity({'phase':phase_id,'id':item['output_id']})[:32]
                for item in proposal.get('outputs',[]) if isinstance(item,dict) and isinstance(item.get('output_id'),str)}
            entity_ids={item['entity_id']:'entity-'+identity({'phase':phase_id,'id':item['entity_id']})[:32]
                for item in proposal.get('candidate_entities',[]) if isinstance(item,dict)
                    and isinstance(item.get('entity_id'),str) and item['entity_id'] not in selected_entities}
            def remap(item):
                if isinstance(item,list):return [remap(value) for value in item]
                if not isinstance(item,dict):return item
                result={key:remap(value) for key,value in item.items()}
                for key in ('output_id',):
                    if isinstance(result.get(key),str):result[key]=output_ids.get(result[key],result[key])
                if isinstance(result.get('output_ids'),list):
                    result['output_ids']=[output_ids.get(key,key) if isinstance(key,str) else key for key in result['output_ids']]
                for key in ('entity_id','parent_id','child_id'):
                    if isinstance(result.get(key),str):result[key]=entity_ids.get(result[key],result[key])
                if isinstance(result.get('entity_ids'),list):
                    result['entity_ids']=[entity_ids.get(key,key) if isinstance(key,str) else key for key in result['entity_ids']]
                if isinstance(result.get('family_id'),str):
                    result['family_id']='family-'+identity({'phase':phase_id,'id':result['family_id']})[:32]
                return result
            proposal=remap(proposal)
            for key in ('candidate_entities','outputs','research_families','relationships','output_relations','interpretations'):
                if isinstance(proposal.get(key),list):data.setdefault(key,[]).extend(proposal[key])
        accepted=build_organization_findings(extract_config,[item.model_dump(mode='json') for item in evidence_list],data) or {}
        ambiguous=[item for item in accepted.get('pending_records',[])
            if 'ambiguous affiliation identity' in str(item.get('reason',''))]
        if ambiguous:
            from app.model_routing import prepare_capability_upgrade
            prepare_capability_upgrade(self,'analyst','entity_ambiguity',evidence_present=True,
                details={'pending_count':len(ambiguous),'output_ids':[item.get('output_id') for item in ambiguous[:10]]})
        seed={'outputs':[{key:item.get(key) for key in ('output_id','title','source_urls','published_on','published_until','affiliations')}
            for item in (accepted.get('scope_result') or {}).get('outputs',[])],
            'publication_metadata':accepted.get('publication_metadata',{}),
            'pending_records':accepted.get('pending_records',[])[:10]}
        allowed={'landscape':('interpretations',),'relationships':('relationship_entities','research_relationships','geographies'),
            'deep_dive':('technical_cards',),'evolution':('trend_observations',),'validation':('trend_observations',),
            'actions':('action_cards',)}
        texts=[];contexts=[]
        technical_by_output={}
        retained_evidence=[item.model_dump(mode='json') for item in evidence_list]
        def retain_technical(record, batch):
            from app.organization_deep_dive import build_technical_cards
            permitted={item['output_id'] for item in batch['outputs']}
            view=build_technical_cards(configuration,accepted,retained_evidence,record['organization_data'])
            record['context']['technical_field_checks']=[{'output_id':card['output_id'],'field':key,
                'status':field['status'],'reason':field.get('reason')}
                for card in view['cards'] if card['output_id'] in permitted for key,field in card['fields'].items()]
            record['context']['technical_card_pending_records']=view.get('pending_records',[])
            for card in view['cards']:
                if card['output_id'] not in permitted:continue
                target=technical_by_output.setdefault(card['output_id'],{'output_id':card['output_id'],'fields':{},'figure_references':[]})
                for key,field in card['fields'].items():
                    if field.get('text') and field.get('proofs') and key not in target['fields']:
                        target['fields'][key]={'text':field['text'],'proofs':[
                            {'evidence_id':proof['evidence_id'],'quote':proof['quote']} for proof in field['proofs']]}
                for figure in card['figure_references']:
                    normalized={'label':figure['label'],'page':figure['page'],'proof':{
                        'evidence_id':figure['proof']['evidence_id'],'quote':figure['proof']['quote']}}
                    if normalized not in target['figure_references']:target['figure_references'].append(normalized)
        for module in modules:
            batches=[seed]
            if module=='deep_dive' and len(seed['outputs'])>2:
                batches=[{**seed,'outputs':seed['outputs'][index:index+2]} for index in range(0,len(seed['outputs']),2)]
            module_texts=[]
            for index,batch in enumerate(batches):
                batch={**batch,'publication_metadata':{item['output_id']:seed['publication_metadata'].get(item['output_id'],{})
                    for item in batch['outputs']}}
                phase_id='question:'+module+(f':{index+1}' if len(batches)>1 else '')
                record=phase(phase_id,{**configuration,'modules':[module]},'question',batch)
                module_texts.append(record['analysis_text'])
                contexts.append({'module':module,'phase_id':phase_id,**record['context']})
                if module=='deep_dive':
                    retain_technical(record,batch)
                    contexts[-1]['technical_field_checks']=record['context']['technical_field_checks']
                    contexts[-1]['technical_card_pending_records']=record['context']['technical_card_pending_records']
                    condition_fields=('experimental_design','baselines','conditions','results')
                    missing={item['output_id']:[field for field in condition_fields if field not in
                        technical_by_output.get(item['output_id'],{}).get('fields',{})] for item in batch['outputs']}
                    missing={key:value for key,value in missing.items() if value}
                    if missing:
                        followup={**batch,'reading_focus':list(dict.fromkeys(field for values in missing.values() for field in values)),
                            'missing_fields_by_output':missing,'outputs':[item for item in batch['outputs'] if item['output_id'] in missing]}
                        follow_id='question:deep_dive:conditions:'+str(index+1)
                        conditions=phase(follow_id,{**configuration,'modules':[module]},'question',followup)
                        retain_technical(conditions,followup)
                        module_texts.append(conditions['analysis_text'])
                        contexts.append({'module':module,'phase_id':follow_id,**conditions['context']})
                for key in allowed[module]:
                    if key=='technical_cards':continue
                    if isinstance(record['organization_data'].get(key),list):
                        if not isinstance(data.get(key),list):data[key]=[]
                        data.setdefault(key,[]).extend(record['organization_data'][key])
            texts.append('## '+MODULES[module][0]+'\n\n'+'\n\n'.join(module_texts))
        if 'deep_dive' in modules:data['technical_cards']=list(technical_by_output.values())
        workflow.update(status='completed',active_phase=None)
        self.last_workflow=workflow
        self.last_organization_data=data
        self.last_context_manifest={'schema_version':'adrs-analysis-questions-v2','phases':contexts,
            'publication_contexts':[record['context'] for record in extractions],
            'conclusion_coverage':'question_responses_not_semantic_certification'}
        self.last_evidence_ids=list(dict.fromkeys(source['evidence_id'] for record in workflow['completed'].values()
            for source in record['context'].get('sources',[])))
        self.last_extraction_status={'status':'returned','phase_count':len(workflow['completed']),'finish_reason':'all_question_responses_retained'}
        progress()
        return '\n\n'.join(texts)

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            from app.model_routing import initialize_agent_client
            if initialize_agent_client(self,'analyst'):
                return budgeted_client(self._client,self.request_budget,'research')
            from app.llm_client import create_llm_client, get_llm_model
            self._client = create_llm_client()
            self.model = get_llm_model()
        return budgeted_client(self._client,self.request_budget,'research')

    def analyze(
        self,
        user_query: str,
        evidence_list: list[Evidence],
        skill_prompt: str | None = None,
        analyst_hints: list[str] | None = None,
        organization_research: dict | None = None,
        *, resume_state: dict | None = None, on_progress: Callable[[dict], None] | None = None,
        _phase: str | None = None, _seed: dict | None = None,
        _output_tokens: int = 4096,
    ) -> str:
        """
        Generate analysis from collected evidence.

        Args:
            user_query: The original research question
            evidence_list: All evidence collected by sub-agents

        Returns:
            Analysis text (Markdown format)
        """
        if organization_research and _phase is None:
            return self._analyze_workflow(user_query,evidence_list,skill_prompt,analyst_hints,
                organization_research,resume_state,on_progress)
        logger.info(f"Analyst: analyzing {len(evidence_list)} evidence items")
        self.last_organization_data=None
        self.last_partial_response=None
        self.last_extraction_status={}
        decision = build_guardrail_decision(user_query)
        # The complete frozen question is already in the user message. Keep
        # only the enforcement/profile instructions in the system message.
        system_prompt = f"{build_prompt_profile_message(decision)}\n\n{self.SYSTEM_PROMPT}"
        repair=getattr(self,'phase_repair',{})
        if repair.get('instruction'):system_prompt+='\n'+repair['instruction']
        if analyst_hints:
            system_prompt = (
                f"{system_prompt}\n\n## Analyst Skill Instructions\n"
                + "\n".join(f"- {item}" for item in analyst_hints if item and item.strip())
            )
        if not evidence_list and not decision.reject_if_no_evidence:
            system_prompt += (
                "\n\n当前没有检索到外部证据。你可以基于模型已有知识回答简单事实问题，"
                "但必须明确标注“未检索验证”，不要编造来源、引用或实时数据。"
            )

        # Format evidence for the prompt
        self.last_organization_data = None
        self.last_evidence_ids = []
        self.last_extraction_status = {'status': 'not_returned'}
        self.last_partial_response = None
        self.last_context_manifest = {}
        context_seed=_seed or {}
        seed_manifest=None
        if organization_research:
            from app.organization_findings import EXTRACTION_INSTRUCTIONS
            if _phase!='question':system_prompt += '\n\n' + EXTRACTION_INSTRUCTIONS
            else:
                system_prompt += ('\nReturn JSON with analysis_text and organization_data. Answer only this selected question. '
                    'Use the server-retained publication IDs below; do not re-extract or modify publications/affiliations. '
                    'Cite existing source numbers, preserve experiment conditions, and use literal proof excerpts for structured fields. '
                    'Prefix new observation/event IDs with the selected module name to avoid cross-question collisions.')
                from app.research_context import question_seed, encoded
                seed,seed_manifest=question_seed(_seed,deep='deep_dive' in organization_research.get('modules',[]))
                seed_text=encoded(seed)
                context_seed=seed
                system_prompt += '\n'+untrusted_context('retained_publication_records',seed_text,limit=len(seed_text))
                if seed.get('reading_focus'):
                    system_prompt += ('\nThis is a targeted follow-up for missing experimental fields. '
                        'Return only the requested fields for the specified publication IDs, with literal proofs. '
                        'Preserve model/sample/population, hardware/environment, dataset/workload, metrics/units, '
                        'comparison baseline and measurement conditions together when reporting a result. '
                        'Use multiple excerpts when the conditions span paragraphs; do not infer absent values. '
                        'Explain which comparisons are meaningful under the actual shared conditions.')
            system_prompt += ('\nFor this organization task return ONLY analysis_text and organization_data as root keys. '
                'Keep analysis_text a compact question-led synthesis; source proofs belong in organization_data, '
                'not repeated copies in findings/data_points/conflicts. Prefer a few concise, complete technical '
                'fields with literal proofs over an unfinished large response. The report stage receives source passages itself.')
            if _phase=='question':
                system_prompt += ('\nFor this selected-question phase, analysis_text is a lead of one to four sentences, '
                    'not a report or a nested JSON document. Put the complete requested field details, '
                    'conditions, evidence and action records in organization_data. Do not repeat prior chapters '
                    'or answer other modules in the lead; the final report owns the full narrative.')
            system_prompt += '\nSelected scope: ' + json.dumps(organization_research['scope'], ensure_ascii=False)
            from app.organization_purpose import analysis_instructions
            if _phase!='extraction':system_prompt += analysis_instructions(organization_research)
            else:system_prompt += ('\nThis prerequisite extracts publication identities, dates and affiliations only; '
                'it is not an additional report module. Do not draft technical, trend or action fields yet. '
                'Use only the selected source openings in this batch; preserve full titles and author/organization '
                'blocks, publisher dates and literal proofs. Do not infer a formal affiliation from a profile or citation.')
            from app.organization_corpus import corpus_instructions
            if _phase!='question':system_prompt += corpus_instructions(organization_research)
            from app.organization_relationships import relationship_instructions
            system_prompt += relationship_instructions(organization_research)
            from app.organization_deep_dive import technical_instructions
            system_prompt += technical_instructions(organization_research)
            from app.organization_trends import trend_instructions
            system_prompt += trend_instructions(organization_research)
            from app.organization_actions import action_instructions
            system_prompt += action_instructions(organization_research)
            if 'actions' in organization_research.get('modules',[]):
                system_prompt += '\nUser action requirements (do not invent missing values): ' + json.dumps(organization_research.get('action_requirements') or {},ensure_ascii=False)
        from app.research_context import evidence_context, fit_messages, CONTEXT_PACKING_VERSION
        phase_request = (
            'Answer only the currently selected module question. Return the short analysis_text lead and complete '
            'organization_data with literal source proofs; do not draft the final report.' if _phase=='question' else
            'Extract only the publication identities, dates and affiliations selected for this batch, with literal proofs. '
            'Return analysis_text and organization_data; do not draft technical analysis or a report.' if _phase=='extraction' else
            'Please provide a comprehensive analysis addressing the research question. Use [citation:N] format to '
            'attribute claims to evidence items (e.g., [citation:1] for the first evidence item). Also provide the structured JSON output.')
        def build_messages(allowance):
            preferred=[]
            preferred.extend(context_seed.get('identity_evidence_ids',[]))
            groups={}
            for output in context_seed.get('outputs',[]):
                identifiers=(context_seed.get('publication_metadata',{}).get(output['output_id']) or {}).get('evidence_ids',[])
                preferred.extend(identifiers)
                groups[output['output_id']]=identifiers
            text, manifest = evidence_context(evidence_list, user_query,
                deep='deep_dive' in (organization_research or {}).get('modules', []), max_bytes=allowance,
                preferred_ids=preferred,focus=context_seed.get('reading_focus'),identity_only=_phase=='extraction',
                required_groups=groups if _phase=='question' else None,
                packing_version=getattr(self,'context_packing_version',CONTEXT_PACKING_VERSION))
            self.last_evidence_ids = [row['evidence_id'] for row in manifest['sources']]
            formatted_evidence = untrusted_context('external_evidence', text, limit=len(text))
            messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"""Research Question: {user_query}

{research_method_context(skill_prompt or '',guidance=bool(getattr(self.request_budget,'skill_guidance',False))) if skill_prompt else ''}

Collected Evidence:
{formatted_evidence}

{phase_request}"""
            },
            ]
            if seed_manifest is not None:manifest['publication_seed']=seed_manifest
            return messages, manifest
        # Resolve the permitted context capacity before packing optional text.
        # This constructs a client but does not dispatch a model request.
        active_client=skill_context_client(self.client) if skill_prompt else self.client
        if seed_manifest is not None:self.last_context_manifest={'publication_seed':seed_manifest}
        messages, self.last_context_manifest = fit_messages(build_messages, self.request_budget,
            'research', _output_tokens, max_bytes=int(repair.get('max_bytes') or (getattr(self,'context_expansion_bytes',36000) if organization_research else 10000)),
            request_extra={'response_format': {'type': 'json_object'}} if organization_research else None)
        missing=self.last_context_manifest.get('missing_full_text_outputs') or []
        if missing:
            error=TokenBudgetExceeded('insufficient_context_budget')
            error.admission={'reason':'assigned_full_text_source_not_in_context',
                'missing_output_ids':missing,'selected_sources':len(self.last_context_manifest.get('sources') or []),
                'prompt_bound':self.last_context_manifest.get('prompt_bound'),
                'requested_output_tokens':_output_tokens,
                'available_tokens':self.request_budget.available() if self.request_budget else None}
            raise error
        if organization_research and not self.last_context_manifest.get('sources'):
            error=TokenBudgetExceeded('insufficient_context_budget')
            error.admission={'reason':'no_acquired_source_fits','prompt_bound':self.last_context_manifest.get('prompt_bound'),
                'requested_output_tokens':_output_tokens,'available_tokens':self.request_budget.available() if self.request_budget else None,
                'selected_sources':0}
            raise error

        try:
            fallback=self.routed_fallback if hasattr(self,'routed_fallback') else create_fallback_llm_client()
            response, response_model, fallback_used = call_chat_with_fallback(
                active_client,
                self.model,
                fallback,
                messages=messages,
                temperature=0.4,
                max_tokens=_output_tokens,
                **({'response_format': {'type': 'json_object'}} if organization_research else {}),
            )
            if fallback_used:
                if fallback is not None:self._client=fallback[0]
                self.model = response_model
            content = response.choices[0].message.content
            self.last_usage = collect_usage_metrics(
                response=response,
                model=response_model,
                messages=messages,
                completion_text=content,
            )

            if response.choices[0].finish_reason == 'length':
                self.last_partial_response = content
                self.last_extraction_status = {'status': 'truncated', 'finish_reason': 'length'}
                raise TokenBudgetExceeded('model_output_limit')

            if not content:
                if organization_research:raise TokenBudgetExceeded('analysis_output_incomplete')
                return self._fallback_analysis(user_query, evidence_list)

            # Try to parse structured output
            try:
                normalizations = []
                structured,control_repairs = _decode_response_object(content,normalizations=normalizations)
                if not isinstance(structured, dict):
                    structured = {}
                if isinstance(structured.get('organization_data'), dict):
                    self.last_organization_data = structured['organization_data']
                self.last_extraction_status = {
                    'status': 'returned' if self.last_organization_data is not None else 'missing_organization_data',
                    'response_fields': list(structured),
                    'finish_reason': response.choices[0].finish_reason,
                    'json_string_control_repairs':control_repairs,
                }
                if control_repairs:
                    self.last_extraction_status['raw_response_before_control_repair']=content
                if normalizations:
                    self.last_extraction_status['json_envelope_normalizations']=normalizations
                    self.last_extraction_status['raw_response_before_envelope_normalization']=content
            except json.JSONDecodeError as error:
                structured = {}
                self.last_extraction_status = {'status': 'invalid_json', 'reason': str(error),
                    'finish_reason': response.choices[0].finish_reason}

            if organization_research and (self.last_organization_data is None or not isinstance(structured.get('analysis_text'),str)
                    or (_phase=='question' and not structured['analysis_text'].strip())):
                self.last_partial_response=content
                raise TokenBudgetExceeded('analysis_output_incomplete')

            # Return the narrative text portion
            if structured.get("analysis_text"):
                return structured["analysis_text"]

            # Fallback: return the full response
            return content

        except TokenBudgetExceeded:
            raise
        except (APIError, OSError, RuntimeError, TypeError, ValueError, KeyError, AttributeError) as e:
            logger.error('Analyst error: %s', type(e).__name__)
            if organization_research:
                if getattr(e,'code',None) in {'context_length_exceeded','max_tokens_exceeded'}:
                    error=TokenBudgetExceeded('insufficient_context_budget')
                    error.admission={'reason':'provider_context_limit','prompt_bound':self.last_context_manifest.get('prompt_bound'),
                        'requested_output_tokens':_output_tokens,
                        'available_tokens':self.request_budget.available() if self.request_budget else None}
                    raise error from e
                self.last_extraction_status={'status':'failed','reason':type(e).__name__}
                code=getattr(e,'code',None)
                if code in {'insufficient_quota','billing_hard_limit_reached','account_deactivated'}:
                    self.last_extraction_status['provider_error_code']=code
                import ssl
                cause=e
                for _ in range(6):
                    if isinstance(cause,ssl.SSLCertVerificationError):
                        self.last_extraction_status['provider_error_code']='tls_validation_failed';break
                    cause=getattr(cause,'__cause__',None)
                    if cause is None:break
                response=getattr(e,'response',None)
                raw=response.headers.get('retry-after') if response is not None else None
                try:self.last_extraction_status['retry_after_seconds']=max(0,float(raw))
                except (TypeError,ValueError):
                    if raw:
                        from email.utils import parsedate_to_datetime
                        from datetime import UTC,datetime
                        try:self.last_extraction_status['retry_after_seconds']=max(0,
                            (parsedate_to_datetime(raw)-datetime.now(UTC)).total_seconds())
                        except (TypeError,ValueError,OverflowError):pass
                raise TokenBudgetExceeded('analysis_provider_unavailable') from e
            self.last_usage = None
            return self._fallback_analysis(user_query, evidence_list)

    def _format_evidence(self, evidence_list: list[Evidence], organization_mode: bool = False, deep_dive: bool = False) -> str:
        """Format evidence list for the prompt."""
        if organization_mode:
            from app.research_context import evidence_context
            text, self.last_context_manifest = evidence_context(evidence_list,
                'method architecture evaluation hardware baseline workload limitations 方法 实验 条件',
                deep=deep_dive, max_bytes=28000)
            self.last_evidence_ids = [row['evidence_id'] for row in self.last_context_manifest['sources']]
            return text
        lines = []
        remaining = 28000 if organization_mode else 10000
        for i, ev in enumerate(evidence_list[:20], 1):  # Limit to 20 for token budget
            if remaining <= 0:
                break
            acquisition=dict(ev.acquisition or {})
            # Full structures/raw blocks stay in the source. Hand off bounded
            # locators rather than duplicating complete documents in prompts.
            if acquisition.get('document_structure'):
                structure=acquisition.pop('document_structure')
                acquisition['document_structure_summary']={key:structure.get(key) for key in ('schema_version','format','quality')}
                acquisition['document_structure_summary']['counts']={key:len(structure.get(key,[])) for key in ('blocks','tables','figures')}
            for field in ('blocks','tables','figures'):
                if field in acquisition:acquisition[field+'_retained_count']=len(acquisition.pop(field))
            acquisition.pop('original_serialized_text',None)
            if 'deduplication' in acquisition:
                duplicates=acquisition.pop('deduplication')
                acquisition['deduplication_summary']={'exact_groups':len(duplicates.get('exact_groups',[])),
                    'near_candidates':len(duplicates.get('near_candidates',[])),'automatic_content_removal':False}
            if 'pages' in acquisition:acquisition['pages']=acquisition['pages'][:8]
            if isinstance(acquisition.get('beam_path'),dict):
                path=acquisition['beam_path'];acquisition['beam_path']={'depth':path.get('depth'),
                    'edge_kinds':[item.get('kind') for item in (path.get('edges') or []) if isinstance(item,dict)],
                    'status':'retrieval_signal_not_confirmed_identity_or_relationship'}
            if acquisition.get('chunk_reference'):
                chunk=acquisition['chunk_reference']
                acquisition['chunk_reference']={key:chunk.get(key) for key in ('logical_chunk_id','source_version','start','end','parent_block_id','kind','title_path','metadata_quality')}
            if 'publisher_abstract_spans' in acquisition:
                acquisition['publisher_abstract_spans']=[{key:value for key,value in span.items() if key!='quote'} for span in acquisition['publisher_abstract_spans']]
            if 'document_links' in acquisition:acquisition['document_links']=[value for value in acquisition['document_links'] if len(value)<=1000][:3]
            if 'public_links' in acquisition:
                acquisition['public_links']=[url for url in acquisition['public_links'] if len(url)<=1000 and re.search(r'contact|people|author|faculty|orcid',url,re.I)][:3]
            metadata=json.dumps(acquisition,ensure_ascii=False)
            if len(metadata)>2400:
                acquisition={key:acquisition.get(key) for key in ('format','coverage','truncated','source_document_id','parse_version_id','returned_span','document_links','source_lead_excerpt','source_summary','model_entity_candidates','linked_entities','image_match')}
                acquisition['context_note']='metadata_excerpt_only_full_metadata_retained_by_evidence_id'
                metadata=json.dumps(acquisition,ensure_ascii=False)
                if len(metadata)>2400:
                    acquisition.pop('document_links',None);metadata=json.dumps(acquisition,ensure_ascii=False)
            self.last_evidence_ids.append(ev.evidence_id)
            source_info = f"[Source: {ev.source_title[:300]}]" if ev.source_title else ""
            url_info = f"({ev.source_url})" if ev.source_url and len(ev.source_url)<=2000 else '[source URL retained outside this context]' if ev.source_url else ''
            header=f"[{i}] Evidence ID: {ev.evidence_id} {source_info} {url_info}\nType: {ev.source_type} | Agent: {ev.agent_type.value}\nAcquisition: {metadata}\nContent: "
            content_limit=min(10000 if deep_dive else 7000 if organization_mode else 500,max(0,remaining-len(header)-40))
            if content_limit<100:
                self.last_evidence_ids.pop();break
            if deep_dive:
                from app.organization_deep_dive import technical_evidence_windows
                excerpt,_=technical_evidence_windows(ev,content_limit)
            else:excerpt=ev.content[:content_limit]
            excerpt=excerpt[:content_limit]
            formatted=header+excerpt+("... [excerpt truncated]" if len(ev.content)>content_limit else '')
            remaining-=len(formatted)+2;lines.append(formatted)
        return "\n\n".join(lines)

    def _fallback_analysis(self, user_query: str, evidence_list: list[Evidence]) -> str:
        """Generate a basic analysis when the LLM fails."""
        lines = [f"# Research Analysis: {user_query}\n"]

        if evidence_list:
            lines.append(f"\nBased on {len(evidence_list)} evidence items:\n")
            for i, ev in enumerate(evidence_list[:5], 1):
                lines.append(f"- {ev.content[:200]}...")
        else:
            lines.append("\nNo sufficient evidence collected for analysis. I don't know.")

        return "\n".join(lines)
