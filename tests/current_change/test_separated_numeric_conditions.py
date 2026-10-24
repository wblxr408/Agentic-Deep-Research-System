"""Frozen real failure: result metrics must not displace setup conditions."""
import json
from pathlib import Path

from app.claim_verification import select_excerpts
from app.graph.state import Evidence


def test_frozen_invisiflow_claim_retrieves_both_effect_and_topology():
    saved = json.loads(Path("docs/acceptance/openminion-msr-r13-20261018T150637Z/result/result.json").read_text(encoding="utf-8"))
    evidence = [Evidence.model_validate(item) for item in saved["evidence"]]
    claim = saved["audit"]["claims"][12]
    query = "InvisiFlow telemetry loss rate approximately 0 33.8x lower than Everflow Planck FatTree 9 core 4 pod 144 servers 100Gbps high load simulation ns-3"
    selected = select_excerpts(claim["text"]+" "+query, evidence, cited=claim["citation_ids"], windows_per_source=3)
    paper = evidence[5]
    topology_position = paper.content.index("144")
    assert any(item["evidence_id"] == paper.evidence_id and item["start"] <= topology_position < item["end"] for item in selected), selected
