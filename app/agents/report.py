"""
Report Generator Agent: produces the final Markdown report with citations.

Generates a structured, well-formatted research report with source attribution.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.config import get_settings
from app.graph.state import Citation, Evidence

if TYPE_CHECKING:
    from openai import OpenAI

logger = logging.getLogger(__name__)


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

> Generated: {timestamp} | Research Depth: Comprehensive

## Executive Summary
{2-3 sentence core conclusion}

## 1. Background and Context
{Research background and scope}

## 2. Key Findings
### 2.1 [Finding Category 1]
{Detailed finding with evidence}

### 2.2 [Finding Category 2]
{Detailed finding with evidence}

## 3. Data and Statistics
{Key data points with sources}

## 4. Expert Perspectives
{Expert opinions and analyses}

## 5. Conclusions and Recommendations
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
- Include confidence levels for uncertain claims
- Provide actionable, specific conclusions
"""

    def __init__(self):
        settings = get_settings()
        self.model = settings.llm.model
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            from openai import OpenAI
            settings = get_settings()
            self._client = OpenAI(
                api_key=settings.llm.api_key,
                base_url=settings.llm.api_base or "https://api.openai.com/v1",
            )
        return self._client

    def generate(
        self,
        user_query: str,
        analysis: str,
        evidence_list: list[Evidence],
        reflection: dict | None,
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

        # Build citation index
        citations: list[Citation] = []
        evidence_map: dict[str, Citation] = {}

        for i, ev in enumerate(evidence_list[:30], 1):
            citation_id = f"citation:{i}"
            if getattr(ev, 'citation', None):
                citation_text = ev.citation
                citation = Citation(
                    citation_id=citation_id,
                    source_url=ev.source_url or "",
                    source_title=ev.source_title or f"Source {i}",
                    source_type=ev.source_type,
                    extracted_evidence=citation_text[:300] if citation_text else ev.content[:300],
                    relevance_score=0.5,
                )
            else:
                citation = Citation(
                    citation_id=citation_id,
                    source_url=ev.source_url or "",
                    source_title=ev.source_title or f"Source {i}",
                    source_type=ev.source_type,
                    extracted_evidence=ev.content[:300],
                    relevance_score=0.5,
                )
            citations.append(citation)
            evidence_map[ev.evidence_id] = citation

        # Build reference list
        ref_list = self._build_reference_list(citations)

        # Format evidence for prompt
        formatted_evidence = self._format_evidence(evidence_list, citations)

        # Confidence note if reflection is available
        confidence_note = ""
        if reflection:
            conf = reflection.get("overall_confidence", 0.5)
            if conf < 0.7:
                confidence_note = f"\n\n**Quality Note**: This report has moderate confidence ({conf:.0%}). Some claims may need verification."

        # Generate citation range note
        citation_note = self._citation_range_note(len(citations))

        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"""Research Topic: {user_query}

Analyst's Analysis:
{analysis}

Evidence Sources:
{formatted_evidence}

{citation_note}

{confidence_note}

Generate the complete research report in Markdown format. Include all sections specified in the system prompt.
Make sure every factual claim has a [citation:N] reference."""
            },
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
                max_tokens=8192,
            )

            content = response.choices[0].message.content
            if not content:
                return self._fallback_report(user_query, evidence_list, citations)

            # Append references section if not present
            if "## References" not in content and "## 参考" not in content:
                content += f"\n\n---\n\n## References\n\n{ref_list}"

            logger.info(f"Report: generated {len(content)} chars, {len(citations)} citations")
            return content, citations

        except Exception as e:
            logger.error(f"Report generation error: {e}")
            return self._fallback_report(user_query, evidence_list, citations), citations

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
