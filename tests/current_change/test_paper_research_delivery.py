"""New paper-text and report-claim behavior for the complete research delivery."""
import io
import json
from types import SimpleNamespace as NS
import pytest

from app.claim_verification import extract_claims


def test_technical_comparison_is_a_complete_claim_and_table_metadata_is_not():
    report = ("# Findings\n| Paper | Finding |\n| --- | --- |\n"
              "| Trial | RDMA vs. TCP improved by 33% in simulation. [citation:1] |\n"
              "<citation_notes>\nMetadata source map, not a finding.\n</citation_notes>\n"
              "```json\n{\"citation:1\": \"metadata\"}\n```\n"
              "Commercial deployment has not been established. [citation:1]")
    claims = extract_claims(report)
    assert len(claims) == 2, claims
    assert "RDMA vs. TCP improved by 33%" in claims[0]["text"]
    assert claims[0]["citation_ids"] == [1]
    assert "Commercial deployment" in claims[1]["text"]


def pdf_bytes():
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
    writer = PdfWriter()
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    for text in ["Introduction context. " * 1500,
                 "The 2025 simulation reduced p99 completion time by 33 percent; no production deployment was evaluated."]:
        page = writer.add_blank_page(width=600, height=800)
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        content = DecodedStreamObject()
        content.set_data(("BT /F1 12 Tf 50 700 Td (" + text + ") Tj ET").encode())
        page[NameObject("/Contents")] = writer._add_object(content)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_research_reads_pdf_tail_with_page_offsets_and_reuses_original(monkeypatch):
    import openminion
    import app.claim_verification as verification
    from app.openminion_research import OrganizationResearchRequest, run_research
    reads, outputs = [], {}
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
            outputs["page"] = json.loads(self.tools["read_source"]("https://www.usenix.org/presentation/trial"))
            for key, focus in [("pdf", "simulation p99 completion 33 percent production deployment"), ("repeat", "Introduction")]:
                outputs[key] = json.loads(self.tools["read_source"]("https://www.usenix.org/paper.pdf", focus))
            return NS(text=json.dumps({"report": "待核验。", "task_status": "partial", "gaps": []}),
                      run_id="paper-fixture", run_state="completed", stats={})
    monkeypatch.setattr(openminion, "Agent", Agent)
    raw = pdf_bytes()
    class Reader:
        def read(self, url, **kwargs):
            reads.append(url)
            pdf = url.endswith(".pdf")
            return NS(url=url, status=200, headers={"content-type": "application/pdf" if pdf else "text/html"},
                      body=raw if pdf else b'<main>Trial paper <a href="/paper.pdf">Full paper PDF</a></main>')
    task = OrganizationResearchRequest(organizations=[{"name": "Example Lab", "type": "laboratory"}],
        topic="Network simulation research", start_year=2025, end_year=2025)
    result = run_research(task, model_config={"provider": "openai", "model": "fixture", "api_key": "fixture"},
                          search=lambda *a, **kw: [], reader=Reader())
    assert "no production deployment was evaluated" in outputs["pdf"].get("text", ""), outputs
    assert outputs["page"]["links"][0]["url"] == "https://www.usenix.org/paper.pdf"
    assert outputs["pdf"]["evidence_id"] == outputs["repeat"]["evidence_id"]
    assert reads.count("https://www.usenix.org/paper.pdf") == 1
    evidence = next(e for e in result["evidence"] if e["evidence_id"] == outputs["pdf"]["evidence_id"])
    assert evidence["content"][outputs["pdf"]["start"]:outputs["pdf"]["end"]] == outputs["pdf"]["text"]
    metadata = result["documents"][evidence["evidence_id"]]
    assert metadata["pages"][1]["number"] == 2
    assert metadata["pages"][1]["start"] > 20000
    assert result["budget"]["calls"] == 3


@pytest.mark.parametrize("kind,expected", [("malformed", "invalid_pdf"),
    ("encrypted", "encrypted_pdf"), ("scanned", "pdf_no_extractable_text"), ("deadline", "timeout")])
def test_pdf_failure_remains_explicit_and_bounded(kind, expected):
    from app.research_documents import read_pdf
    from app.channels.models import ChannelError
    from pypdf import PdfWriter
    if kind in {"encrypted", "scanned"}:
        writer = PdfWriter()
        writer.add_blank_page(width=600, height=800)
        if kind == "encrypted":
            writer.encrypt("not-authorized")
        stream = io.BytesIO()
        writer.write(stream)
        raw = stream.getvalue()
    else:
        raw = pdf_bytes() if kind == "deadline" else b"%PDF-1.7\ninvalid object data"
    with pytest.raises(ChannelError) as error:
        read_pdf(raw, timeout=0.01 if kind == "deadline" else 10)
    assert error.value.category == expected
