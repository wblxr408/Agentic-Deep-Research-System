"""The synthesis consumer must keep citations attached to the correct original."""
import json
from types import SimpleNamespace as NS
from app.graph.state import Evidence
from app.openminion_research import OrganizationResearchRequest, _build_synthesis_input
from app.claim_verification import audit_report


def test_synthesis_excerpt_citation_points_to_the_second_original():
    fact = "Evaluation simulation reached 73 km only in the laboratory testbed."
    evidence = [Evidence(evidence_id="s1", content="An unrelated institution profile.", collected_by="browser"),
        Evidence(evidence_id="s2", content="Background notes. "*300 + fact, collected_by="browser")]
    request = OrganizationResearchRequest(organizations=[{"name": "Lab", "type": "laboratory"}],
        topic="Quantum network research", start_year=2025, end_year=2025)
    payload = _build_synthesis_input(request, evidence, "", {"s1": {}, "s2": {}}, [])
    # A synthesis consumer cites the excerpt it actually used, rather than
    # guessing which source the application intended it to cite.
    excerpt = payload["sources"][1]["excerpts"][0]
    report = fact + f" [citation:{excerpt['citation_id']}]"
    client = NS(chat=NS(completions=NS(create=lambda **kw: NS(usage=None, choices=[NS(message=NS(content=json.dumps({
        "verdicts": [{"claim_id": "claim:1", "status": "supported", "evidence_id": "s2", "quote": fact, "confidence": 0.9}]
    })))]))))
    audit = audit_report(report, evidence, client=client, model="fixture")
    assert audit["supported_claims"] == 1, audit
