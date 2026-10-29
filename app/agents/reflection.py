"""
Reflection Agent: hallucination detection and evidence validation.

Performs multi-dimensional quality checks on the analysis.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from app.config import get_settings
from app.llm_budget import budgeted_client, skill_context_client, TokenBudgetExceeded
from app.graph.state import (
    ClaimConflict,
    Evidence,
    HallucinatedClaim,
    ReflectionResult,
)
from app.guardrails import build_guardrail_decision, build_prompt_profile_message
from app.llm_client import (
    call_chat_with_fallback,
    collect_usage_metrics,
    create_fallback_llm_client,
)
from app.security.prompt_security import untrusted_context,research_method_context
from app.claim_verification import claim_evidence_context

if TYPE_CHECKING:
    from openai import OpenAI

logger = logging.getLogger(__name__)


class ReflectionAgent:
    """
    Validates analysis quality through multiple dimensions:

    1. Fact Verification: Cross-reference claims with evidence
    2. Numerical Accuracy: Check if numbers match sources
    3. Temporal Validity: Ensure data is within reasonable timeframe
    4. Consistency: Detect self-contradicting claims
    5. Completeness: Check coverage of research dimensions
    """

    SYSTEM_PROMPT = """You are a critical fact-checker and quality auditor for AI research outputs. Your job is to rigorously validate analysis quality.

## Validation Dimensions

### 1. Fact Verification
Check each claim against provided evidence. Flag as hallucination if:
- The claim directly contradicts evidence
- The claim makes specific claims (numbers, dates, names) not present in any evidence
- The claim is an overgeneralization not supported by evidence

### 2. Numerical Accuracy
Extract all numbers/dates from the analysis and verify they match evidence sources.

### 3. Temporal Validity
Ensure statistical claims are from reasonable timeframes (generally within 2 years for market data).

### 4. Self-Consistency
Detect if the analysis contains contradictory statements.

### 5. Citation Coverage
Calculate what percentage of claims have supporting citations.

## Response Format

Return JSON:
{
  "total_claims": <int>,
  "verified_claims": <int>,
  "hallucinated_claims": [
    {
      "claim": "<exact text of hallucinated claim>",
      "severity": "high|medium|low",
      "reason": "<why it is flagged>",
      "suggested_action": "<how to fix>"
    }
  ],
  "conflicts": [
    {
      "claim_a": "<text>",
      "claim_b": "<text>",
      "conflict_description": "<explanation>"
    }
  ],
  "citation_coverage": <float 0-1>,
  "overall_confidence": <float 0-1>,
  "needs_revision": <bool>,
  "revision_focus": "<specific guidance for revision>" or null
}

Be strict but fair. Flag real hallucinations but don't over-flag.
"""

    def __init__(self):
        settings = get_settings()
        self.model = settings.llm.model
        self._client: OpenAI | None = None
        self.last_usage: dict | None = None
        self.request_budget = None
        self.last_partial_response = None
        self.last_context_manifest = {}

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            from app.model_routing import initialize_agent_client
            if initialize_agent_client(self,'reflection'):
                return budgeted_client(self._client,self.request_budget,'research')
            from app.llm_client import create_llm_client, get_llm_model
            self._client = create_llm_client()
            self.model = get_llm_model()
        return budgeted_client(self._client,self.request_budget,'research')

    def reflect(
        self,
        user_query: str,
        analysis: str,
        evidence_list: list[Evidence],
        skill_prompt: str | None = None,
        reflection_hints: list[str] | None = None,
        organization_research: dict | None = None,
    ) -> ReflectionResult:
        """
        Perform reflection on the analysis.

        Args:
            user_query: Original research question
            analysis: The analysis text to validate
            evidence_list: Evidence supporting the analysis

        Returns:
            ReflectionResult with quality metrics
        """
        logger.info(f"Reflection: validating analysis ({len(analysis)} chars, {len(evidence_list)} evidence items)")
        self.last_usage=None
        self.last_partial_response=None
        self.last_context_manifest={'schema_version':'adrs-reflection-response-v1','status':'pending','attempts':[]}
        decision = build_guardrail_decision(user_query)
        system_prompt = f"{build_prompt_profile_message(decision)}\n\n{self.SYSTEM_PROMPT}"
        if (organization_research or {}).get('corpus'):
            from app.organization_corpus import corpus_instructions
            from app.organization_purpose import analysis_instructions
            system_prompt += analysis_instructions(organization_research) + corpus_instructions(organization_research)
            system_prompt += ('\n审核本次已选问题和声明样本。明确披露的限定范围、全文缺口或无法确认，'
                '本身不是幻觉，不要求扩大种子或补未选模块。仍严格指出无来源事实、矛盾或越界推断。')
        if reflection_hints:
            system_prompt = (
                f"{system_prompt}\n\n## Reflection Skill Instructions\n"
                + "\n".join(f"- {item}" for item in reflection_hints if item and item.strip())
            )

        formatted_evidence = claim_evidence_context(analysis, evidence_list)

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"""Research Question: {user_query}

Analysis to Validate:
{untrusted_context('analyst_output', analysis)}

{research_method_context(skill_prompt or '',guidance=bool(getattr(self.request_budget,'skill_guidance',False))) if skill_prompt else ''}

Evidence Sources:
{untrusted_context('external_evidence', formatted_evidence, limit=25000)}

Perform a rigorous quality check and return the structured JSON output."""
            },
        ]

        try:
            active_client=skill_context_client(self.client) if skill_prompt else self.client
            primary_model=self.model
            original_messages=messages
            from app.disclosure import redact_text
            for attempt in range(2):
                response, response_model, fallback_used = call_chat_with_fallback(
                    active_client,primary_model,
                    self.routed_fallback if hasattr(self,'routed_fallback') else create_fallback_llm_client(),
                    messages=messages,temperature=0.1,max_tokens=4096 if attempt==0 else 8192,
                    response_format={"type":"json_object"})
                if fallback_used:self.model=response_model
                choice=response.choices[0] if response.choices else None
                content=(choice.message.content or '') if choice else ''
                self.last_partial_response=content
                self.last_usage=collect_usage_metrics(response=response,model=response_model,
                    messages=messages,completion_text=content)
                finish_reason=getattr(choice,'finish_reason',None)
                record={'attempt':attempt+1,'finish_reason':finish_reason,'model':response_model,
                    'raw_response':redact_text(content[:50000]),'record_truncated':len(content)>50000,
                    'usage':self.last_usage}
                self.last_context_manifest['attempts'].append(record)
                try:
                    if finish_reason=='length':raise ValueError('reflection_output_truncated')
                    if not content.strip():raise ValueError('reflection_response_empty')
                    result=self._result_from_data(json.loads(content))
                    if analysis.strip() and result.total_claims==0:
                        raise ValueError('reflection_claim_coverage_empty')
                except (ValueError,TypeError,KeyError,AttributeError) as error:
                    record.update(status='invalid',error_category=type(error).__name__,
                        failure_reason='output_truncated' if finish_reason=='length' else
                            'empty_response' if not content.strip() else
                            'json_invalid' if isinstance(error,json.JSONDecodeError) else 'response_fields_invalid')
                    self.last_context_manifest['status']='invalid'
                    if attempt==1:return self._default_result()
                    # Recheck the same analysis and evidence, not the malformed
                    # answer. One larger complete response uses the same meter.
                    messages=[{**original_messages[0],'content':original_messages[0]['content']+
                        '\nThe previous response was incomplete or invalid. Return one COMPLETE JSON object '
                        'with every required field. Keep reasons concise; preserve all detected conflicts and claims. '
                        'Do not truncate strings or add prose outside JSON.'},*original_messages[1:]]
                    continue
                record['status']='valid'
                self.last_context_manifest['status']='valid'
                break

            logger.info(
                f"Reflection: confidence={result.overall_confidence:.2f}, "
                f"hallucinations={len(result.hallucinated_claims)}, "
                f"conflicts={len(result.conflicts)}, "
                f"needs_revision={result.needs_revision}"
            )
            return result

        except TokenBudgetExceeded:
            self.last_context_manifest['status']='budget_stopped'
            raise
        except (OSError, RuntimeError, TypeError, ValueError, KeyError, AttributeError) as e:
            logger.error(f"Reflection error: {e}")
            self.last_context_manifest.update(status='response_error',error_category=type(e).__name__)
            return self._default_result()

    @staticmethod
    def _result_from_data(data):
        required={'total_claims','verified_claims','hallucinated_claims','conflicts',
            'citation_coverage','overall_confidence','needs_revision','revision_focus'}
        if not isinstance(data,dict) or not required<=data.keys():raise ValueError('reflection_fields_incomplete')
        if (type(data['total_claims']) is not int or type(data['verified_claims']) is not int
                or not 0<=data['verified_claims']<=data['total_claims']
                or type(data['needs_revision']) is not bool
                or not isinstance(data['hallucinated_claims'],list) or not isinstance(data['conflicts'],list)):
            raise ValueError('reflection_fields_invalid')
        hallucinated=[HallucinatedClaim(claim=row['claim'],severity=row['severity'],reason=row['reason'],
            suggested_fix=row.get('suggested_action') or row.get('suggested_fix','')) for row in data['hallucinated_claims']]
        conflicts=[ClaimConflict(claim_a=row['claim_a'],claim_b=row['claim_b'],
            conflict_description=row['conflict_description']) for row in data['conflicts']]
        if (hallucinated or conflicts) and not data['needs_revision']:
            raise ValueError('reflection_verdict_conflicts_with_findings')
        return ReflectionResult(total_claims=data['total_claims'],verified_claims=data['verified_claims'],
            hallucinated_claims=hallucinated,conflicts=conflicts,citation_coverage=data['citation_coverage'],
            overall_confidence=data['overall_confidence'],needs_revision=data['needs_revision'],
            revision_focus=data['revision_focus'])

    def _format_evidence(self, evidence_list: list[Evidence], analysis: str = "") -> str:
        """Compatibility helper using the same claim-oriented selection."""
        return claim_evidence_context(analysis, evidence_list)

    def _default_result(self) -> ReflectionResult:
        """Return a default result when reflection fails."""
        return ReflectionResult(
            total_claims=0,
            verified_claims=0,
            hallucinated_claims=[],
            conflicts=[],
            citation_coverage=0.0,
            overall_confidence=0.0,
            needs_revision=True,
            revision_focus="Reflection validation failed. Re-run verification and inspect evidence coverage.",
        )
