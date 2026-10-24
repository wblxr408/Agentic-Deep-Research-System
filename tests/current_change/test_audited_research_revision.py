"""A failed source-support audit must drive a bounded, source-based correction."""
import json
from types import SimpleNamespace as NS


def test_final_audit_is_recomputed_after_correcting_the_unsupported_report(monkeypatch):
    import openminion
    from app.openminion_research import OrganizationResearchRequest, run_research, _ResearchOutput, _AuditOutput
    monkeypatch.setattr(openminion, "tool", lambda **kw: lambda fn: fn)
    monkeypatch.setattr(openminion.APIRuntime, "from_manager", lambda *a, **kw: NS(close=lambda: None))
    fact = "The 2025 trial reached 73 km only in the laboratory; no commercial deployment occurred."
    state = {"writers": 0, "audits": 0}
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
                self.tools["search_organizations"]("trial research")
                self.tools["read_source"]("https://www.usenix.org/trial")
                return NS(text="Research draft", run_id="collect", run_state="completed", stats={})
            if self.output_type is _AuditOutput:
                state["audits"] += 1
                return NS(output=_AuditOutput(verdicts=[{"claim_id": "claim:1", "status": "contradicted" if state["audits"] == 1 else "supported",
                    "evidence_id": "source:1", "quote": fact, "confidence": 0.9}]), stats={})
            state["writers"] += 1
            report = "The trial entered commercial deployment in 2025. [citation:1]" if state["writers"] == 1 else fact+" [citation:1]"
            return NS(output=_ResearchOutput(report=report, task_status="completed", gaps=[]), run_id="writer", stats={})
    monkeypatch.setattr(openminion, "Agent", Agent)
    class Reader:
        def read(self, url, **kwargs):
            return NS(url=url, status=200, headers={"content-type": "text/plain"}, body=fact.encode())
    task = OrganizationResearchRequest(organizations=[{"name": "Lab", "type": "laboratory"}],
        topic="Quantum trial development", start_year=2025, end_year=2025)
    result = run_research(task, model_config={"provider": "openai", "model": "fixture", "api_key": "fixture"}, reader=Reader(),
        search=lambda *a, **kw: [NS(url="https://www.usenix.org/trial", title="Trial", snippet=fact)])
    assert result["status"] == "completed", result
    assert result["audit"]["claims"][0]["status"] == "supported"
    assert result["initial_audit"]["claims"][0]["status"] == "contradicted"
    assert state == {"writers": 2, "audits": 2}
    assert result["report"].startswith(fact)
    assert result["revision"]["applied"] is True
