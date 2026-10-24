"""Model-generated numeric references must be audited against their real sources."""
import json
from types import SimpleNamespace as NS
from app.claim_verification import audit_report
from app.graph.state import Evidence


def test_numeric_reference_after_sentence_is_bound_before_support_audit():
    fact = "The trial reached 73 km only in the laboratory."
    evidence = [Evidence(evidence_id="s1", content=fact, collected_by="browser")]
    client = NS(chat=NS(completions=NS(create=lambda **kw: NS(usage=None, choices=[NS(message=NS(content=json.dumps({
        "verdicts": [{"claim_id": "claim:1", "status": "supported", "evidence_id": "s1", "quote": fact, "confidence": 0.9}]
    })))]))))
    audit = audit_report(fact + " [1]", evidence, client=client, model="fixture")
    assert audit["total_claims"] == 1 and audit["supported_claims"] == 1, audit
