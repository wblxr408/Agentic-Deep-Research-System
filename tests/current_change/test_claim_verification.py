"""Current change: source-tail retrieval and audit of newly generated claims."""
import json
from types import SimpleNamespace as NS
from unittest.mock import patch

from app.agents.reflection import ReflectionAgent
from app.agents.report import ReportAgent
from app.graph.state import Evidence


def source(content, n=1):
    return Evidence(evidence_id=f"e{n}", content=content, source_url=f"https://example.org/{n}",
                    source_title=f"Source {n}", source_type="web", collected_by="browser")


def response(data):
    return NS(choices=[NS(message=NS(content=json.dumps(data)))], usage=None)


def test_reflection_reads_relevant_tail_of_sixteenth_source():
    evidence = [source("Unrelated background. " * 100, i) for i in range(1, 17)]
    evidence[-1].content += "In 2025 the quantum network trial reached 73 km, only in the laboratory."
    captured = []

    def complete(*args, **kwargs):
        captured.append(kwargs["messages"])
        return response({"overall_confidence": 0.4, "needs_revision": True}), "fixture", False

    agent = ReflectionAgent()
    agent._client = NS()
    with patch("app.agents.reflection.call_chat_with_fallback", complete), \
         patch("app.agents.reflection.create_fallback_llm_client", return_value=None):
        agent.reflect("What was achieved?", "The 2025 quantum network trial reached 73 km.", evidence)
    prompt = captured[0][1]["content"]
    assert "73 km, only in the laboratory" in prompt


def test_generated_report_has_semantic_audit_and_separate_human_status():
    evidence = [source("The 2025 trial reached 73 km, only in the laboratory; no commercial deployment occurred.")]
    generated = "# Findings\n\nThe network entered commercial deployment in 2025. [citation:1]\n"

    def create(**kwargs):
        if kwargs.get("stream"):
            return iter([NS(choices=[NS(delta=NS(content=generated))])])
        return response({"verdicts": [{"claim_id": "claim:1", "status": "contradicted",
                         "evidence_id": "e1", "quote": "no commercial deployment occurred",
                         "reason": "The source explicitly rules out commercial deployment.", "confidence": 0.98}]})

    agent = ReportAgent()
    agent._client = NS(chat=NS(completions=NS(create=create)))
    with patch("app.agents.report.create_fallback_llm_client", return_value=None):
        report, _ = agent.generate("Research development", "Draft analysis", evidence, {"overall_confidence": 0.99})
    audit = getattr(agent, "last_audit", {})
    assert audit.get("human_review_status") == "not_reviewed"
    assert audit["claims"][0]["status"] == "contradicted"
    assert audit["supported_claims"] == 0
    assert audit["claims"][0]["source_checks"][0]["quote_start"] >= 0
    assert report.startswith(generated)


def test_invalid_citation_invented_quote_and_unchecked_claim_are_not_supported():
    from app.claim_verification import audit_report
    evidence = [source("The experiment involved 12 laboratories and did not include clinical participants.")]
    report = ("A clinical trial was completed. [citation:1]\n"
              "It involved 12 laboratories. [citation:99]\n"
              "This result needs verification.\n"
              "A follow-up was completed. [citation:1]")
    def create(**kwargs):
        return response({"verdicts": [{"claim_id": "claim:1", "status": "supported", "evidence_id": "e1",
                                      "quote": "A clinical trial was completed", "confidence": 1}]})
    audit = audit_report(report, evidence, client=NS(chat=NS(completions=NS(create=create))), model="fixture", max_claims=3)
    assert [row["status"] for row in audit["claims"]] == ["unverifiable", "invalid_citation", "missing_citation", "not_checked"]
    assert audit["supported_claims"] == 0
    assert audit["claims"][0]["source_checks"][0]["quote_valid"] is False


def test_budget_skip_does_not_invoke_auditor_or_claim_verification():
    from app.claim_verification import audit_report
    calls = []
    client = NS(chat=NS(completions=NS(create=lambda **kwargs: calls.append(kwargs))))
    audit = audit_report("The trial reached 73 km. [citation:1]", [source("The trial reached 73 km.")],
                         client=client, model="fixture", token_budget=0)
    assert not calls
    assert audit["claims"][0]["status"] == "not_checked"
    assert audit["checked_claims"] == 0 and audit["supported_claims"] == 0
