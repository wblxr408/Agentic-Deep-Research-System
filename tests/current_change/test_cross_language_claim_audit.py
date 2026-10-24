"""Current gap: Chinese claims must retrieve the English conditions they cite."""
import json
from types import SimpleNamespace as NS
from app.graph.state import Evidence
from app.claim_verification import audit_report, select_excerpts


def test_chinese_claim_retrieves_english_limit_late_in_cited_original():
    fact = "The implementation was evaluated only in the laboratory, not in commercial deployment."
    evidence = [Evidence(evidence_id="s1", content="Unrelated background. "*2000+fact, collected_by="browser")]
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            data = {"verdicts": [{"claim_id": "claim:1", "search_query": "implementation evaluated laboratory commercial deployment"}]}
        else:
            assert fact in kwargs["messages"][1]["content"]
            data = {"verdicts": [{"claim_id": "claim:1", "status": "supported", "evidence_id": "s1", "quote": fact, "confidence": 0.8}]}
        return NS(usage=None, choices=[NS(message=NS(content=json.dumps(data)))])
    audit = audit_report("该实现仅在实验室评估，未做商用部署。[citation:1]", evidence,
                         client=NS(chat=NS(completions=NS(create=create))), model="fixture")
    assert audit["supported_claims"] == 1, audit
    assert audit["claims"][0]["source_checks"][0]["quote_start"] > 20000


def test_claim_can_select_separate_result_and_condition_windows_in_one_source():
    evidence = [Evidence(evidence_id="s1", content="The trial reached 73 km. " + "Background. "*1000
        + "Commercial deployment was excluded; laboratory conditions applied.", collected_by="browser")]
    try:
        excerpts = select_excerpts("trial reached 73 km commercial deployment excluded laboratory conditions", evidence,
                                  windows_per_source=3)
    except TypeError:
        excerpts = select_excerpts("trial reached 73 km commercial deployment excluded laboratory conditions", evidence)
    context = "\n".join(item["quote"] for item in excerpts)
    assert "73 km" in context and "Commercial deployment was excluded" in context
