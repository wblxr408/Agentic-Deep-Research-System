"""Models select a supplied original passage instead of retyping PDF line wraps."""
import json
from types import SimpleNamespace as NS

import pytest
from app.claim_verification import audit_report
from app.graph.state import Evidence


@pytest.mark.parametrize("excerpt_id,expected", [("source:1:0:67", "supported"),
    ("source:1:999:1066", "unverifiable"), ("source:2:0:67", "unverifiable")])
def test_selected_passage_must_belong_to_this_claim_and_cited_source(excerpt_id, expected):
    text = "A hardware exper-\niment reached 73 km only in the laboratory trial."
    evidence = [Evidence(evidence_id=f"source:{i}", content=text, source_url=f"https://www.usenix.org/{i}",
                         source_title="Trial", collected_by="browser") for i in (1, 2)]
    def create(**kwargs):
        return NS(choices=[NS(message=NS(content=json.dumps({"verdicts":[{
            "claim_id":"claim:1", "status":"supported", "evidence_id":"source:1",
            "excerpt_id":excerpt_id, "quote":None if excerpt_id == "source:1:0:67" else text,
            "reason":"The supplied trial is limited to the laboratory.",
            "confidence":0.9}]})))])
    result = audit_report("The hardware trial reached 73 km only in the laboratory. [citation:1]", evidence,
        client=NS(chat=NS(completions=NS(create=create))), model="fixture")
    row = result["claims"][0]
    assert row["status"] == expected, row
    if expected == "supported":
        check = row["source_checks"][0]
        assert check["source_quote"] == evidence[0].content[check["quote_start"]:check["quote_end"]]
        assert check["quote_match"] == "selected_excerpt"
    assert row["human_review_status"] == "not_reviewed"
