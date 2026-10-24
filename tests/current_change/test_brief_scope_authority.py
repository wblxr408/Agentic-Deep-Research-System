"""Model warnings cannot invent requirements beyond the requested bounded brief."""
from types import SimpleNamespace as NS
from app.graph.state import Evidence
from app.openminion_research import OrganizationResearchRequest, _render_brief


def test_exhaustive_census_warning_is_retained_without_becoming_a_required_facet():
    request = OrganizationResearchRequest(organizations=[{"name": "Lab", "type": "laboratory"}],
        topic="Representative research brief; no exhaustive publication census is required.", start_year=2024, end_year=2025)
    warning = "An exhaustive publication census and internal strategy inference are missing."
    data = {"findings": [{"organization": "Lab", "work": "Trial", "facet": facet,
        "statement": "A source-backed research fact.", "citation_ids": [1]} for facet in ["affiliation", "problem", "method", "result"]],
        "questions": ["Which experimental condition should be checked next?"], "gaps": [], "missing_requirements": [warning]}
    body, missing, preserved = _render_brief(NS(model_dump=lambda: data), request,
        [Evidence(evidence_id="s1", content="A source-backed research fact.", collected_by="browser")])
    assert missing == [], missing
    assert preserved["missing_requirements"] == [warning]
