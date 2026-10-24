"""Repeated long titles must not crowd out a late, specific limitation."""
from app.claim_verification import select_excerpts
from app.graph.state import Evidence


def test_late_limitation_outranks_repeated_full_paper_title():
    title = "Reverie Low Pass Filter Based Switch Buffer Sharing Datacenters RDMA TCP Traffic"
    introduction = (title + " Introduction networks systems throughput design methods. ") * 90
    limitation = "A prototype implementation is beyond the scope of this paper and is part of our future work."
    body = introduction + ("Measurements and configuration details. " * 60) + "\n" + limitation + "\n" + ("References other unrelated work. " * 70)
    evidence = [Evidence(evidence_id="source:1", source_url="https://www.usenix.org/paper.pdf",
        source_title=title, content=body, collected_by="browser")]
    selected = select_excerpts(title+" prototype implementation beyond scope future work", evidence,
                               cited=[1], windows_per_source=3)
    assert any(limitation in item["quote"] for item in selected), selected
