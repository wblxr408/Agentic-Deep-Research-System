"""
Report Generator Agent: produces the final Markdown report with citations.

Generates a structured, well-formatted research report with source attribution.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from app.config import get_settings
from app.llm_budget import ModelTokenBudget, budgeted_client, TokenBudgetExceeded
from app.graph.state import Citation, Evidence
from app.guardrails import (
    build_guardrail_decision,
    build_prompt_profile_message,
    get_research_budget,
)
from app.llm_client import (
    StreamInterruptedError,
    create_fallback_llm_client,
    create_llm_client,
    get_llm_model,
)
from app.security.prompt_security import untrusted_context
from app.claim_verification import audit_report, claim_evidence_context
from app.organization_purpose import REPORT_WRITING_GUIDANCE, analysis_snapshot, assemble_module_report, module_report_instructions

if TYPE_CHECKING:
    from openai import OpenAI

logger = logging.getLogger(__name__)


class ReportContractError(RuntimeError):
    """A finished provider reply is not necessarily a valid research report."""


class ReportAgent:
    """
    Converts the analysis and evidence into a polished Markdown research report.

    The report follows a standard business research format with:
    - Executive summary
    - Structured findings
    - Data analysis
    - Expert perspectives
    - Conclusions
    - References
    """

    SYSTEM_PROMPT = """You are an expert research report writer. Your job is to produce a polished, well-structured Markdown research report.

## Report Structure

```
# {Research Topic}

## Executive Summary
{2-3 sentence core conclusion}

## 1. Scope and Method
{Research question, dates, sources and sample selection, stated once}

## 2. Key Findings
### 2.1 [Finding Category 1]
{Detailed finding with evidence}

### 2.2 [Finding Category 2]
{Detailed finding with evidence}

## 3. Data and Statistics
{Key data points with sources}

## 4. Conclusions and Recommendations
{Actionable conclusions}

## References
{citation list}
```

## Formatting Rules

1. Use [citation:N] format for every factual claim
2. Use **bold** for key terms and important numbers
3. Use tables for data comparisons
4. Use blockquotes for expert quotes
5. Keep paragraphs focused (3-5 sentences max)
6. Use ## for main sections, ### for subsections

## Quality Standards

- Every factual claim must be cited
- Distinguish between facts (verified) and opinions (analyst interpretation)
- Attribute source claims and state conditions that materially affect the conclusion
- Provide actionable, specific conclusions
"""

    def __init__(self):
        settings = get_settings()
        self.model = settings.llm.model
        self._client: OpenAI | None = None
        self.last_usage: dict | None = None
        self.request_budget = None
        self.last_audit: dict | None = None
        self.last_module_report: dict | None = None
        self.last_draft: str | None = None
        self.last_partial_response: str | None = None
        self.last_citations: list = []
        self.last_context_manifest: dict = {}
        self.last_writing_plan:dict={}

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            from app.model_routing import initialize_agent_client
            if initialize_agent_client(self,'report'):
                return budgeted_client(self._client,self.request_budget,'report')
            self._client = create_llm_client()
            self.model = get_llm_model()
        return budgeted_client(self._client,self.request_budget,'report')

    def generate(
        self,
        user_query: str,
        analysis: str,
        evidence_list: list[Evidence],
        reflection: dict | None,
    ) -> tuple[str, list[Citation]]:
        """Generate the final report without streaming callbacks."""
        return self.generate_stream(
            user_query=user_query,
            analysis=analysis,
            evidence_list=evidence_list,
            reflection=reflection,
        )

    def generate_stream(
        self,
        user_query: str,
        analysis: str,
        evidence_list: list[Evidence],
        reflection: dict | None,
        output_length: str | None = None,
        skill_prompt: str | None = None,
        report_hints: list[str] | None = None,
        on_chunk: Callable[[str], None] | None = None,
        on_citation: Callable[[Citation], None] | None = None,
        verification_token_budget: int | None = None,
        verification_timeout_seconds: float = 90,
        organization_research: dict | None = None,
        organization_statistics: dict | None = None,
        query_understanding:dict|None=None,
    ) -> tuple[str, list[Citation]]:
        """
        Generate the final research report.

        Args:
            user_query: Original research question
            analysis: Analyst's synthesized analysis
            evidence_list: All collected evidence
            reflection: Reflection quality result (optional)

        Returns:
            Tuple of (report_markdown, citations_list)
        """
        logger.info(f"Report: generating report for query: {user_query[:80]}")
        verification_deadline = time.monotonic() + max(0, verification_timeout_seconds)
        decision = build_guardrail_decision(user_query)
        budget = get_research_budget(output_length)
        if self.request_budget is None:
            tokens = verification_token_budget if verification_token_budget is not None else budget['max_total_tokens']
            self.request_budget = ModelTokenBudget(tokens,audit_reserve=min(12000,max(0,int(tokens*.2))),
                deadline=verification_deadline,audit_seconds=min(90,max(0,verification_timeout_seconds*.2)))
        verification_deadline = self.request_budget.deadline or verification_deadline
        active_client=self.client
        output_tokens = min(budget['report_max_tokens'], max(1024, self.request_budget.available('report')//3))
        self.last_audit = None
        self.last_module_report = None
        module_mode = analysis_snapshot(organization_research) is not None
        from app.report_planning import writing_plan,writing_instructions
        self.last_writing_plan=writing_plan(query_understanding,organization_research)
        instructions = module_report_instructions(organization_research) if module_mode else (
            self.SYSTEM_PROMPT if self.last_writing_plan['output_kind']=='report' and self.last_writing_plan['structure_owner']=='reader_task'
            else 'You write source-grounded research answers in Chinese Markdown. Every factual claim uses the original [citation:N].')
        instructions+=writing_instructions(self.last_writing_plan)
        system_prompt = f"{build_prompt_profile_message(decision)}\n\n{instructions}"
        if report_hints:
            system_prompt = (
                f"{system_prompt}\n\n## Report Skill Instructions\n"
                + "\n".join(f"- {item}" for item in report_hints if item and item.strip())
            )
        system_prompt += (
            f"\n\n输出长度要求：{output_length or 'medium'}。"
            f"请优先控制在约 {budget['report_max_tokens']} tokens 内。"
            f"引用数量上限约 {budget['citation_max']} 条。"
        )
        if not evidence_list and not decision.reject_if_no_evidence:
            system_prompt += (
                "\n\n当前没有外部证据。允许回答简单事实问题，但必须明确说明“未检索验证”。"
                "不要生成虚假的 [citation:N]，不要声称已检索来源。"
            )
        if not module_mode:
            system_prompt += '\n\n' + REPORT_WRITING_GUIDANCE

        citations = self._build_citations(evidence_list)
        self.last_citations = citations
        for citation in citations:
            if on_citation:
                on_citation(citation)

        # Build reference list
        ref_list = self._build_reference_list(citations)

        # Format evidence for prompt
        from app.organization_statistics import statistics_context
        computed_statistics = statistics_context(organization_statistics)

        # Generate citation range note
        citation_note = self._citation_range_note(len(citations))

        from app.research_context import analysis_context, evidence_context, fit_messages, encoded
        def build_messages(allowance):
            selected_analysis, omitted = analysis_context(analysis, int(allowance*.18))
            formatted_evidence, manifest = evidence_context(evidence_list, user_query,
                deep=module_mode and 'deep_dive' in organization_research['modules'], max_bytes=int(allowance*.75))
            stats = dict(computed_statistics) if computed_statistics else None
            if stats:
                stats['metric_registry'] = dict(stats['metric_registry'])
                while stats['metric_registry'] and len(encoded(stats).encode('utf-8')) > allowance*.07:
                    stats['metric_registry'].pop(next(reversed(stats['metric_registry'])))
                stats['omitted_metrics'] = len(computed_statistics['metric_registry'])-len(stats['metric_registry'])
            messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"""Research Topic: {user_query}

{untrusted_context('skill_content', skill_prompt or '') if skill_prompt else ''}

Analyst's Analysis:
{untrusted_context('analyst_output', selected_analysis, limit=len(selected_analysis))}

{untrusted_context('computed_statistics', encoded(stats), limit=len(encoded(stats))) if stats else ''}

Evidence Sources:
{untrusted_context('external_evidence', formatted_evidence, limit=len(formatted_evidence))}

{citation_note}

{'Return the exact JSON module contract from the system prompt, in Chinese, with only selected modules and numeric citation arrays.' if module_mode else 'Generate the complete research report in Markdown format. Include all sections specified in the system prompt. Make sure every factual claim has a [citation:N] reference.'}"""
            },
            ]
            manifest['omitted_analysis_blocks'] = omitted
            manifest['omitted_metrics'] = stats.get('omitted_metrics', 0) if stats else 0
            return messages, manifest
        messages, self.last_context_manifest = fit_messages(build_messages, self.request_budget, 'report',
            output_tokens, max_bytes=60000,
            request_extra={'response_format': {'type': 'json_object'}} if module_mode else None)

        try:
            chunks: list[str] = []
            active_model = self.model
            finish_reason = None

            def consume(stream: Any) -> None:
                nonlocal finish_reason
                for event in stream:
                    if not event.choices:
                        continue
                    finish_reason = getattr(event.choices[0],'finish_reason',None) or finish_reason
                    delta = event.choices[0].delta.content or ""
                    if not delta:
                        continue
                    chunks.append(delta)
                    if on_chunk and not module_mode:
                        on_chunk(delta)

            try:
                consume(active_client.chat.completions.create(
                    model=active_model,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=output_tokens,
                    stream=True,
                    **({'response_format': {'type': 'json_object'}} if module_mode else {}),
                ))
            except Exception as primary_error:
                if isinstance(primary_error,TokenBudgetExceeded):
                    raise
                if chunks:
                    raise StreamInterruptedError(
                        "primary_llm_stream_interrupted_after_output"
                    ) from primary_error
                fallback = self.routed_fallback if hasattr(self,'routed_fallback') else create_fallback_llm_client()
                if fallback is None:
                    raise
                fallback_client, active_model = fallback
                self._client=fallback_client
                self.model=active_model
                fallback_client = budgeted_client(fallback_client,self.request_budget,'report')
                logger.warning("Primary report stream failed before output; using fallback: %s", type(primary_error).__name__)
                consume(fallback_client.chat.completions.create(
                    model=active_model,
                    messages=messages,
                    temperature=0.3,
                    max_tokens=output_tokens,
                    stream=True,
                    **({'response_format': {'type': 'json_object'}} if module_mode else {}),
                ))

            content = "".join(chunks).strip()
            # A later correction can be refused before dispatch. Keep this
            # actual response already, rather than losing it at that boundary.
            self.last_partial_response = ''.join(chunks)
            if finish_reason == 'length':
                raise TokenBudgetExceeded('model_output_limit')
            if module_mode:
                from app.organization_purpose import normalize_report_envelope
                normalized_raw,normalizations=normalize_report_envelope(content,organization_research['modules'],len(citations))
                content=normalized_raw
                content, self.last_module_report = assemble_module_report(content, organization_research, len(citations), statistics=organization_statistics)
                if normalizations:self.last_module_report['envelope_normalizations']=normalizations
                if self.last_module_report['issues']:
                    first_record = self.last_module_report
                    first_raw = normalized_raw
                    from app.research_context import encoded
                    rejected = first_record['rejected_paragraphs']
                    local_repair = bool(rejected) and not first_record['validation_errors']
                    repair_context = encoded({'draft': None if local_repair else first_raw, 'issues': first_record['issues'],
                        'validation_errors': first_record['validation_errors'],
                        'rejected_paragraphs': [{'paragraph_id':f'rejected:{index+1}', **row} for index,row in enumerate(rejected)], 'computed_statistics': computed_statistics})
                    repair_shape = ('Return JSON {"repairs":[{"paragraph_id":"rejected:1","text":"corrected prose"}]}. '
                        'Return exactly one text for each supplied paragraph ID; no other fields.' if local_repair
                        else 'Return the complete corrected JSON, without commentary.')
                    repair_messages = [{'role': 'system', 'content': ('' if local_repair else instructions)+
                        '\nRepair only these contract errors. Preserve factual meaning, conditions and citation numbers. '
                        'Use supplied statistic placeholders for aggregates, or name the works without an aggregate count. '
                        'Do not introduce new claims. '+repair_shape},
                        {'role': 'user', 'content': untrusted_context('report_contract_repair', repair_context, limit=len(repair_context))}]
                    if local_repair:
                        from app.organization_purpose import paragraph_repair_messages
                        repair_messages = paragraph_repair_messages(rejected)
                    # Exactly one contract correction, on the same meter and
                    # original deadline. No transport retry or fresh root.
                    from app.model_routing import prepare_capability_upgrade
                    from app.llm_budget import request_token_bound
                    if prepare_capability_upgrade(self,'report','format_failure',evidence_present=bool(evidence_list),
                            details={'validation_errors':first_record['validation_errors'],
                                'rejected_paragraph_count':len(rejected)},
                            required_tokens=request_token_bound(repair_messages,response_format={'type':'json_object'})+1024):
                        active_model=self.model
                    chunks = []; finish_reason = None
                    consume(self.client.chat.completions.create(model=active_model, messages=repair_messages,
                        temperature=0, max_tokens=output_tokens, stream=True, response_format={'type': 'json_object'}))
                    if finish_reason == 'length':
                        raise TokenBudgetExceeded('model_output_limit')
                    repaired_raw = ''.join(chunks)
                    if local_repair:
                        corrections = json.loads(repaired_raw).get('repairs', [])
                        expected = {f'rejected:{index+1}' for index in range(len(rejected))}
                        ids = [item.get('paragraph_id') for item in corrections]
                        if set(ids) != expected or len(ids) != len(expected):
                            raise ReportContractError('report_contract_invalid')
                        original = json.loads(first_raw.strip().removeprefix('```json').removesuffix('```').strip())
                        for index, row in enumerate(rejected):
                            text = next(item['text'] for item in corrections if item['paragraph_id'] == f'rejected:{index+1}')
                            targets = original.get('summary', []) if row['module_id'] == 'summary' else [paragraph
                                for module in original['modules'] if module['module_id'] == row['module_id']
                                for paragraph in [*module['paragraphs'], *module.get('appendix', [])]]
                            for paragraph in targets:
                                if paragraph == row['paragraph']:
                                    paragraph['text'] = text
                        repaired_raw = json.dumps(original, ensure_ascii=False)
                    content, self.last_module_report = assemble_module_report(repaired_raw, organization_research,
                        len(citations), statistics=organization_statistics)
                    self.last_module_report['repair_history'] = [first_record]
                if self.last_module_report['issues']:
                    self.last_partial_response = ''.join(chunks)
                    self.last_draft = content
                    raise ReportContractError('report_contract_invalid')
            elif not content:
                content = self._fallback_report(user_query, evidence_list, citations)
                self._emit_fallback_chunks(content, on_chunk)

            self.last_draft = content
            audit_tokens = self.request_budget.available('audit')
            from app.claim_verification import module_paragraph_kinds, research_method_context
            method_context = research_method_context(user_query, organization_research, evidence_list) if module_mode else None
            bound_statistics=[]
            if self.last_module_report:
                paragraphs=[*self.last_module_report.get('summary',[]), *[paragraph
                    for module in self.last_module_report['modules']
                    for paragraph in [*module['paragraphs'],*module.get('appendix',[])]]]
                bound_statistics=[{'rendered_paragraph':paragraph['rendered_text'],**binding}
                    for paragraph in paragraphs for binding in paragraph.get('statistic_bindings',[])]
            self.last_audit = audit_report(content, evidence_list,
                client=budgeted_client(self.client,self.request_budget,'audit'), model=active_model,
                token_budget=audit_tokens, deadline=verification_deadline,bound_statistics=bound_statistics,
                paragraph_kinds=module_paragraph_kinds(self.last_module_report), task_context=method_context)
            if self.last_module_report is not None:
                from app.report_revision import revise_report_claims
                def upgrade_correction(trigger,details,required_tokens):
                    from app.model_routing import prepare_capability_upgrade
                    if prepare_capability_upgrade(self,'report',trigger,evidence_present=bool(evidence_list),
                            details=details,required_tokens=required_tokens):
                        return self.client,self.model
                    return None
                content,self.last_module_report,self.last_audit=revise_report_claims(content,self.last_module_report,self.last_audit,
                    configuration=organization_research,statistics=organization_statistics,evidence=evidence_list,
                    client=self.client,model=active_model,budget=self.request_budget,deadline=verification_deadline,
                    citation_count=len(citations),upgrade_callback=upgrade_correction, task_context=method_context)
                self.last_audit['module_contract'] = self.last_module_report
                self._emit_fallback_chunks(content,on_chunk)
            # Append references section if not present
            if "## References" not in content and "## 参考" not in content:
                references_block = f"\n\n---\n\n## References\n\n{ref_list}"
                content += references_block
                if on_chunk:
                    on_chunk(references_block)

            self.last_usage = self.request_budget.usage()

            logger.info(f"Report: generated {len(content)} chars, {len(citations)} citations")
            return content, citations

        except ReportContractError:
            self.last_usage = self.request_budget.usage()
            raise
        except TokenBudgetExceeded:
            self.last_usage = self.request_budget.usage()
            if chunks:self.last_partial_response = ''.join(chunks)
            if not module_mode:self.last_draft = self.last_partial_response
            raise
        except StreamInterruptedError:
            # Do not replace a partially emitted report with a second model's
            # response; the workflow must mark this as recoverable instead.
            self.last_usage = self.request_budget.usage()
            if chunks:self.last_partial_response = ''.join(chunks)
            raise
        except (OSError, RuntimeError, TypeError, ValueError, KeyError, AttributeError) as e:
            logger.error(f"Report generation error: {e}")
            self.last_usage = None
            if module_mode:
                fallback, self.last_module_report = assemble_module_report('', organization_research, len(citations), statistics=organization_statistics)
                self.last_partial_response = ''.join(chunks)
                self.last_usage = self.request_budget.usage()
                raise ReportContractError('report_generation_failed') from e
            else:
                fallback = self._fallback_report(user_query, evidence_list, citations)
            # A generation failure cannot become a successful verification.
            self.last_audit = audit_report(fallback, evidence_list, client=None, model=self.model, max_claims=0)
            self._emit_fallback_chunks(fallback, on_chunk)
            return fallback, citations

    def _build_citations(self, evidence_list: list[Evidence]) -> list[Citation]:
        """Build a stable citation list from collected evidence."""
        from app.disclosure import projection
        citations: list[Citation] = []
        for i, ev in enumerate(evidence_list, 1):
            view=projection({'source_url':ev.source_url or '', 'source_title':ev.source_title or f'Source {i}',
                'extracted_evidence':ev.content})
            citations.append(Citation(
                citation_id=f"citation:{i}",
                source_url=view['source_url'],
                source_title=view['source_title'],
                source_type=ev.source_type,
                extracted_evidence=view['extracted_evidence'][:300],
                relevance_score=0.5,
                locator={'evidence_id':ev.evidence_id,'start':0,'end':min(len(ev.content),300),
                    'offset_unit':'task_retained_evidence_character','source_type':ev.source_type,
                    'source_document_id':(ev.acquisition or {}).get('source_document_id'),
                    'parse_version_id':(ev.acquisition or {}).get('parse_version_id'),
                    'chunk_reference':(ev.acquisition or {}).get('chunk_reference'),
                    'returned_span':(ev.acquisition or {}).get('returned_span'),
                    'semantics':'source_excerpt_locator_not_claim_verification'},
            ))
        return citations

    def _emit_fallback_chunks(
        self,
        content: str,
        on_chunk: Callable[[str], None] | None,
        chunk_size: int = 800,
    ) -> None:
        """Emit chunk events for fallback/non-streamed content."""
        if not on_chunk:
            return
        for start in range(0, len(content), chunk_size):
            on_chunk(content[start:start + chunk_size])

    def _locator_markdown(self,citations):
        located=[citation for citation in citations if citation.locator]
        if not located:return ''
        lines=['\n\n## 本次保留依据定位','位置指向本任务保留文字，不代表对应主张已完成语义审核；索引变化不替换该依据。',
            '| 引用 | 保留证据 | 起始字符 | 结束字符 |','| --- | --- | ---: | ---: |']
        for citation in located:
            locator=citation.locator
            evidence=str(locator.get('evidence_id','未知')).replace('|','\\|').replace('<','&lt;').replace('>','&gt;')
            lines.append(f"| {citation.citation_id} | {evidence} | {locator.get('start','未知')} | {locator.get('end','未知')} |")
        return '\n'.join(lines)+'\n'

    def _format_evidence(self, evidence_list: list[Evidence], citations: list[Citation]) -> str:
        """Format evidence with citation numbers."""
        lines = []
        for i, (ev, citation) in enumerate(zip(evidence_list[:20], citations[:20]), 1):
            source = f"{ev.source_title or 'Unknown'} - {ev.source_url}" if ev.source_url else (ev.source_title or "Unknown")
            lines.append(f"[{i}] {source}\nType: {ev.source_type}\n{ev.content[:300]}")
        return "\n\n".join(lines)

    def _build_reference_list(self, citations: list[Citation]) -> str:
        """Build the references section."""
        if not citations:
            return "No citations available."

        refs = []
        for i, c in enumerate(citations, 1):
            title = c.source_title or "Untitled"
            url = c.source_url or ""
            ref_str = f"[{i}] **{title}**"
            if url:
                ref_str += f" - {url}"
            refs.append(ref_str)

        return "\n".join(refs)

    def _citation_range_note(self, n: int) -> str:
        """Generate a note about available citations."""
        if n == 0:
            return "No evidence sources available."
        return f"Available citations: {n} sources (use [citation:1] through [citation:{n}] to reference them)"

    def _fallback_report(
        self,
        user_query: str,
        evidence_list: list[Evidence],
        citations: list[Citation],
    ) -> str:
        """Generate a minimal fallback report when LLM fails."""
        lines = [f"# {user_query}", "", "## 摘要", ""]
        for i, ev in enumerate(evidence_list[:10], 1):
            lines.append(f"### 来源 {i}")
            lines.append(ev.content[:500])
            lines.append("")
        if citations:
            lines.append("## 参考资料")
            for i, c in enumerate(citations[:10], 1):
                title = c.source_title or "Untitled"
                url = c.source_url or ""
                lines.append(f"[{i}] {title} - {url}")
        return "\n".join(lines)
