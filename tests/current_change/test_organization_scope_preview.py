"""Consumer contracts for organization-scope tasks 1.1–1.3 only."""
from copy import deepcopy
from itertools import combinations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.research import router
from app.security.auth import Principal, require_principal


@pytest.fixture
def scope_client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_principal] = lambda: Principal(
        id="11111111-1111-4111-8111-111111111111", username="researcher", auth_type="session"
    )
    with TestClient(app) as client:
        yield client


def entity(identifier, name, kind="university", **extra):
    return {"entity_id": identifier, "name": name, "type": kind,
            "source_urls": [f"https://example.org/entities/{identifier}"], **extra}


def scope(**extra):
    return {"disciplines": ["materials"], "topic": "研究材料制备方法的演进",
            "start_date": "2020-01-01", "end_date": "2026-12-31", **extra}


def preview(client, request):
    response = client.post("/api/v1/research/scope/preview", json=request)
    assert response.status_code == 200, response.text
    return response.json()


TYPE_COMBINATIONS = [list(group) for size in range(1, 4)
                     for group in combinations(["university", "laboratory", "company"], size)]


@pytest.mark.parametrize("types", TYPE_COMBINATIONS)
def test_scope_request_selects_exact_union_without_requiring_partnership(scope_client, types):
    candidates = [entity("u", "University"), entity("l", "Laboratory", "laboratory"),
                  entity("c", "Company", "company")]
    result = preview(scope_client, {"scope": scope(organization_types=types), "candidate_entities": candidates})
    assert {item["type"] for item in result["selected_entities"]} == set(types)
    assert result["scope"]["organization_types"] == types
    assert result["selection_mode"] == "candidate_discovery"
    assert result["discovery_query"]["disciplines"] == ["materials"]
    assert result["discovery_query"]["topic"] == "研究材料制备方法的演进"


def test_scope_request_initial_selection_defaults_to_all_types(scope_client):
    result = preview(scope_client, {"scope": scope()})
    assert result["scope"]["organization_types"] == ["university", "laboratory", "company"]
    assert result["selected_entities"] == []
    assert result["discovery_query"]["start_date"] == "2020-01-01"


@pytest.mark.parametrize("change", [
    {"organization_types": []}, {"organization_types": ["government"]},
    {"organization_types": ["university", "university"]},
    {"start_date": "2026-01-01", "end_date": "2020-01-01"},
    {"start_date": "2026-02-30"}, {"disciplines": []}, {"topic": "   "},
    {"organization_types": ["university"], "entities": [entity("c", "Company", "company")]},
])
def test_scope_request_rejects_invalid_scope_without_widening(scope_client, change):
    response = scope_client.post("/api/v1/research/scope/preview", json={"scope": scope(**change)})
    assert response.status_code == 422, response.text
    assert response.json()["detail"]


def test_named_entities_keep_distinct_pending_names_and_exact_selection(scope_client):
    labs = [entity("lab-a", "先进材料实验室", "laboratory"),
            entity("lab-b", "先进材料实验室", "laboratory")]
    result = preview(scope_client, {"scope": scope(organization_types=["laboratory"], entities=labs),
                                   "candidate_entities": [entity("lab-c", "Other Lab", "laboratory")]})
    assert [item["entity_id"] for item in result["selected_entities"]] == ["lab-a", "lab-b"]
    assert result["pending_entity_ids"] == ["lab-a", "lab-b"]
    assert result["selection_mode"] == "named_entities"
    assert result["discovery_query"] is None


def test_named_mixed_entities_preserve_names_types_and_sources(scope_client):
    selected = [entity("u-a", "University A"), entity("u-b", "University B"),
                entity("c", "Company", "company")]
    result = preview(scope_client, {"scope": scope(organization_types=["university", "company"], entities=selected)})
    assert [(item["entity_id"], item["name"], item["type"], item["source_urls"])
            for item in result["selected_entities"]] == [
                (item["entity_id"], item["name"], item["type"], item["source_urls"]) for item in selected]


@pytest.mark.parametrize("invalid_entity", [
    entity("lab", " ", "laboratory"), entity("lab", "Lab", "laboratory", source_urls=[]),
    entity("lab", "Lab", "laboratory", source_urls=["not-a-url"]),
])
def test_named_entity_requires_identifiable_name_and_source(scope_client, invalid_entity):
    response = scope_client.post("/api/v1/research/scope/preview", json={
        "scope": scope(organization_types=["laboratory"], entities=[invalid_entity])})
    assert response.status_code == 422, response.text


def hierarchy_request():
    university = entity("u", "University")
    department = entity("d", "Department", unit_kind="department")
    lab = entity("lab", "Lab", "laboratory")
    return {"scope": scope(organization_types=["university", "laboratory"], entities=[university, lab]),
            "candidate_entities": [department],
            "relationships": [
                {"parent_id": "u", "child_id": "d", "valid_from": "2018-01-01",
                 "source_urls": ["https://example.org/university-department"]},
                {"parent_id": "d", "child_id": "lab", "valid_from": "2018-01-01",
                 "valid_to": "2023-12-31", "source_urls": ["https://example.org/department-lab"]},
            ],
            "outputs": [{"output_id": "work-1", "title": "A materials study", "published_on": "2022-06-01",
                         "source_urls": ["https://example.org/paper"], "affiliations": [
                             {"author_id": "author-1", "entity_id": "lab", "raw_affiliation": "Lab, University",
                              "source_urls": ["https://example.org/paper#affiliation"]}]}]}


def test_parent_department_and_lab_views_preserve_evidence_and_deduplicate_summary(scope_client):
    request = hierarchy_request()
    result = preview(scope_client, request)
    views = {item["entity_id"]: item for item in result["views"]}
    assert views["u"]["output_ids"] == ["work-1"]
    assert views["u"]["inherited_output_ids"] == ["work-1"]
    assert views["lab"]["direct_output_ids"] == ["work-1"]
    assert result["summary"] == {"output_ids": ["work-1"], "output_count": 1}
    assert result["outputs"][0]["affiliations"] == request["outputs"][0]["affiliations"]
    assert result["relationships"][1]["source_urls"] == ["https://example.org/department-lab"]
    assert result["verification"]["external_sources_checked"] is False


def test_historical_parenthood_uses_publication_date_and_not_current_affiliation(scope_client):
    request = hierarchy_request()
    request["current_affiliations"] = [{"author_id": "author-1", "entity_id": "u",
        "raw_affiliation": "University, current appointment", "source_urls": ["https://example.org/profile"]}]
    later = deepcopy(request["outputs"][0])
    later.update(output_id="work-2", published_on="2024-06-01")
    request["outputs"].append(later)
    result = preview(scope_client, request)
    views = {item["entity_id"]: item for item in result["views"]}
    assert views["u"]["output_ids"] == ["work-1"]
    assert views["lab"]["output_ids"] == ["work-1", "work-2"]
    assert result["outputs"][1]["affiliations"] == later["affiliations"]
    assert result["current_affiliations"] == request["current_affiliations"]


def test_outputs_outside_requested_time_do_not_enter_views(scope_client):
    request = hierarchy_request()
    request["scope"]["end_date"] = "2021-12-31"
    result = preview(scope_client, request)
    assert result["summary"] == {"output_ids": [], "output_count": 0}
    assert all(view["output_count"] == 0 for view in result["views"])


@pytest.mark.parametrize("mutation", ["missing_source", "unknown_entity", "invalid_period", "cycle", "conflicting_id"])
def test_affiliation_hierarchy_rejects_unusable_relationships(scope_client, mutation):
    request = hierarchy_request()
    if mutation == "missing_source":
        request["relationships"][0]["source_urls"] = []
    elif mutation == "unknown_entity":
        request["outputs"][0]["affiliations"][0]["entity_id"] = "unknown"
    elif mutation == "invalid_period":
        request["relationships"][0].update(valid_from="2025-01-01", valid_to="2020-01-01")
    elif mutation == "cycle":
        request["relationships"].append({"parent_id": "lab", "child_id": "u",
                                         "source_urls": ["https://example.org/bad-hierarchy"]})
    else:
        request["candidate_entities"].append(entity("u", "Unrelated University"))
    response = scope_client.post("/api/v1/research/scope/preview", json=request)
    assert response.status_code == 422, response.text
