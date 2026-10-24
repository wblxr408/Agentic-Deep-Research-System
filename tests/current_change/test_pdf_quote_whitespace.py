"""PDF line wrapping may normalize; words, numbers and source offsets may not."""
import json
from types import SimpleNamespace as NS
import pytest
from app.claim_verification import audit_report
from app.graph.state import Evidence


@pytest.mark.parametrize("quote,expected", [
    ("The experiment reached 73 km, only in the laboratory.", "supported"),
    ("The experiment reached 73 miles, only in the laboratory.", "unverifiable"),
])
def test_pdf_line_wrap_is_distinguished_from_a_changed_unit(quote, expected):
    original = "The experiment\nreached 73 km,\nonly in the laboratory."
    evidence = [Evidence(evidence_id="s1", content=original, collected_by="browser")]
    client = NS(chat=NS(completions=NS(create=lambda **kw: NS(usage=None, choices=[NS(message=NS(content=json.dumps({
        "verdicts": [{"claim_id": "claim:1", "status": "supported", "evidence_id": "s1", "quote": quote, "confidence": 0.9}]
    })))]))))
    audit = audit_report("The experiment reached 73 km, only in the laboratory. [citation:1]", evidence, client=client, model="fixture")
    row = audit["claims"][0]
    assert row["status"] == expected, row
    if expected == "supported":
        check = row["source_checks"][0]
        assert check["quote_match"] == "whitespace_normalized"
        assert original[check["quote_start"]:check["quote_end"]] == check["source_quote"] == original

