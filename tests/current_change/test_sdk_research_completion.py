"""Current delivery: synthesis consumes collected evidence rather than an uncited draft."""
import json
from types import SimpleNamespace as NS


def test_final_report_is_synthesized_from_sources_then_audited(monkeypatch):
    import openminion
    from app.openminion_research import OrganizationResearchRequest, run_research, _ResearchOutput, _AuditOutput
    monkeypatch.setattr(openminion, "tool", lambda **kw: lambda fn: fn)
    monkeypatch.setattr(openminion.APIRuntime, "from_manager", lambda *a, **kw: NS(close=lambda: None))
    consumed = []
    fact = "The 2025 quantum network trial reached 73 km, only in the laboratory."

    class Agent:
        def __init__(self, **kwargs):
            self.tools = {fn.__name__: fn for fn in kwargs["tools"]}
            self.output_type = kwargs.get("output_type")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def run(self, message, **kwargs):
            if self.tools:
                self.tools["search_organizations"]("Example Lab quantum network 2025")
                self.tools["read_source"]("https://www.usenix.org/trial")
                return NS(text="organization-research: The network entered commercial deployment in 2025.",
                          run_id="collection", run_state="completed", stats={})
            if self.output_type is _AuditOutput:
                return NS(output=_AuditOutput(verdicts=[{"claim_id": "claim:1", "status": "supported",
                    "evidence_id": "source:1", "quote": fact, "confidence": 0.8}]), stats={})
            if isinstance(message, dict) and message.get("sources"):
                consumed.append(message)
                output = _ResearchOutput(report=fact+" [citation:1]", task_status="completed", gaps=[])
            else:
                output = _ResearchOutput(report="The network entered commercial deployment in 2025.", task_status="partial", gaps=[])
            return NS(output=output, stats={}, run_id="synthesis", run_state="completed")
    monkeypatch.setattr(openminion, "Agent", Agent)

    class Reader:
        def read(self, url, **kwargs):
            return NS(url=url, status=200, headers={"content-type": "text/plain"}, body=fact.encode())
    task = OrganizationResearchRequest(organizations=[{"name": "Example Lab", "type": "laboratory"}],
        topic="Quantum network development", start_year=2025, end_year=2025)
    result = run_research(task, model_config={"provider": "openai", "model": "fixture", "api_key": "fixture"},
        reader=Reader(), search=lambda *a, **kw: [NS(url="https://www.usenix.org/trial", title="Trial", snippet=fact)])
    assert result["status"] == "completed", result
    assert result["audit"]["supported_claims"] == 1
    assert result["audit"]["claims"][0]["source_checks"][0]["quote_valid"] is True
    assert result["audit"]["human_review_status"] == "not_reviewed"
    assert consumed[0]["sources"][0]["text"] == fact
    assert result["synthesis_run_id"] == "synthesis"
    assert "commercial deployment" in result["draft_report"]
    assert result["report"].startswith(fact)


def test_paper_page_read_delivers_linked_pdf_in_the_same_tool_result(monkeypatch):
    import io
    import openminion
    import app.claim_verification as verification
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    from app.openminion_research import OrganizationResearchRequest, run_research, _ResearchOutput
    writer = PdfWriter()
    page = writer.add_blank_page(width=600, height=800)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 50 700 Td (The trial reached 73 km only in the laboratory.) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(content)
    stream = io.BytesIO()
    writer.write(stream)
    outputs, reads = [], []
    monkeypatch.setattr(openminion, "tool", lambda **kw: lambda fn: fn)
    monkeypatch.setattr(openminion.APIRuntime, "from_manager", lambda *a, **kw: NS(close=lambda: None))
    monkeypatch.setattr(verification, "audit_report", lambda *a, **kw: {"claims": [], "total_claims": 0, "supported_claims": 0})
    class Agent:
        def __init__(self, **kwargs):
            self.tools = {fn.__name__: fn for fn in kwargs["tools"]}
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def run(self, *args, **kwargs):
            if self.tools:
                for _ in range(2):
                    outputs.append(json.loads(self.tools["read_source"]("https://www.usenix.org/trial")))
                return NS(text="Collected trial.", run_id="collect", run_state="completed", stats={})
            return NS(output=_ResearchOutput(report="", task_status="partial", gaps=[]), run_id="synth", stats={})
    monkeypatch.setattr(openminion, "Agent", Agent)
    class Reader:
        def read(self, url, **kwargs):
            reads.append(url)
            pdf = url.endswith(".pdf")
            return NS(url=url, status=200, headers={"content-type": "application/pdf" if pdf else "text/html"},
                body=stream.getvalue() if pdf else b'<main>Trial<a href="/trial.pdf">Paper PDF</a></main>')
    task = OrganizationResearchRequest(organizations=[{"name": "Example Lab", "type": "laboratory"}],
        topic="Quantum trial research", start_year=2025, end_year=2025)
    result = run_research(task, model_config={"provider": "openai", "model": "fixture", "api_key": "fixture"}, reader=Reader(), search=lambda *a, **kw: [])
    assert "73 km only in the laboratory" in outputs[0].get("paper", {}).get("text", ""), outputs
    assert outputs[0]["paper"]["citation"] == outputs[1]["paper"]["citation"]
    assert reads == ["https://www.usenix.org/trial", "https://www.usenix.org/trial.pdf"]
    assert result["budget"]["calls"] == 2
