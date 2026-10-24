"""The final brief must cover the research task using individually auditable findings."""
import json
from types import SimpleNamespace as NS


def test_structured_facts_cover_the_requested_facets_without_auditing_scope_metadata(monkeypatch):
    import openminion
    from app.openminion_research import OrganizationResearchRequest, run_research, _AuditOutput
    monkeypatch.setattr(openminion, "tool", lambda **kw: lambda fn: fn)
    monkeypatch.setattr(openminion.APIRuntime, "from_manager", lambda *a, **kw: NS(close=lambda: None))
    facts = {"affiliation": "Wei belongs to Example Lab at publication.",
        "problem": "The laboratory studied quantum network loss.",
        "method": "The trial used a filtered control signal.",
        "result": "The 2025 trial reached 73 km only in the laboratory."}
    data = {"findings": [{"organization": "Example Lab", "work": "Quantum trial", "facet": facet,
                          "statement": text, "citation_ids": [1]} for facet, text in facts.items()],
            "questions": ["How does the result change under a different laboratory load?"],
            "gaps": ["This is a bounded representative brief."], "missing_requirements": []}
    class Agent:
        def __init__(self, **kwargs):
            self.tools = {fn.__name__: fn for fn in kwargs["tools"]}
            self.output_type = kwargs.get("output_type")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def run(self, *args, **kwargs):
            if self.tools:
                self.tools["search_organizations"]("Example Lab quantum network")
                self.tools["read_source"]("https://www.usenix.org/trial")
                return NS(text="collected", run_id="collect", run_state="completed", stats={})
            if self.output_type is _AuditOutput:
                return NS(output=_AuditOutput(verdicts=[{"claim_id": f"claim:{i}", "status": "supported",
                    "evidence_id": "source:1", "quote": text, "confidence": 0.8} for i, text in enumerate(facts.values(), 1)]), stats={})
            return NS(output=NS(**data, model_dump=lambda: data), run_id="synthesis", stats={})
    monkeypatch.setattr(openminion, "Agent", Agent)
    class Reader:
        def read(self, url, **kwargs):
            return NS(url=url, status=200, headers={"content-type": "text/plain"}, body=" ".join(facts.values()).encode())
    task = OrganizationResearchRequest(organizations=[{"name": "Example Lab", "type": "laboratory"}],
        topic="Quantum network research", start_year=2025, end_year=2025)
    result = run_research(task, model_config={"provider": "openai", "model": "fixture", "api_key": "fixture"}, reader=Reader(),
        search=lambda *a, **kw: [NS(url="https://www.usenix.org/trial", title="Trial", snippet="Quantum trial")])
    assert result["status"] == "completed", result
    assert result["audit"]["total_claims"] == result["audit"]["supported_claims"] == 4
    assert result["coverage_missing"] == []
    assert "How does the result change" in result["report"]
    assert result["audit"]["human_review_status"] == "not_reviewed"
