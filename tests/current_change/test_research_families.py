"""New publication/family and relationship behavior for task 1.4."""
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.research import router
from app.security.auth import Principal, require_principal


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_principal] = lambda: Principal(
        id="11111111-1111-4111-8111-111111111111", username="researcher", auth_type="session")
    with TestClient(app) as instance:
        yield instance


def request_data():
    entities = [{"entity_id": key, "name": key, "type": kind,
                 "source_urls": [f"https://example.org/{key}"]}
                for key, kind in [("u", "university"), ("c", "company"), ("funder", "company")]]
    work = {"output_id": "conference", "title": "Same study", "published_on": "2022-06-01",
            "source_urls": ["https://example.org/paper"], "affiliations": [
                {"author_id": "a", "entity_id": "u", "raw_affiliation": "University",
                 "source_urls": ["https://example.org/paper"]},
                {"author_id": "b", "entity_id": "c", "raw_affiliation": "Company",
                 "source_urls": ["https://example.org/paper"]}]}
    journal = deepcopy(work)
    journal.update(output_id="journal", published_on="2023-06-01")
    return {"scope": {"organization_types": ["university", "company"], "entities": entities,
                      "disciplines": ["computing"], "topic": "Systems", "start_date": "2020-01-01",
                      "end_date": "2026-12-31"}, "outputs": [work, journal]}


def result(client, data):
    response = client.post("/api/v1/research/scope/preview", json=data)
    assert response.status_code == 200, response.text
    return response.json()


def test_extension_family_is_distinct_from_publications_and_shared_summary(client):
    data = request_data()
    data["research_families"] = [{"family_id": "study", "output_ids": ["conference", "journal"],
                                  "source_urls": ["https://example.org/extension-evidence"]}]
    body = result(client, data)
    assert body["summary"]["publication_count"] == 2
    assert body["summary"]["research_family_count"] == 1
    assert body["summary"]["counting_method"] == "full"
    assert [view["research_family_count"] for view in body["views"]] == [1, 1, 0]
    assert body["research_families"] == data["research_families"]


def test_same_title_without_family_evidence_stays_two_studies(client):
    body = result(client, request_data())
    assert body["summary"]["publication_count"] == 2
    assert body["summary"]["research_family_count"] == 2
    assert body["summary"]["unlinked_publication_count"] == 2


def test_funding_and_citation_never_create_affiliation_or_coauthorship(client):
    data = request_data()
    data["output_relations"] = [
        {"output_id": "conference", "kind": "funding", "entity_ids": ["funder"],
         "source_urls": ["https://example.org/grant"]},
        {"output_id": "conference", "kind": "coauthorship", "entity_ids": ["u", "c"],
         "source_urls": ["https://example.org/authors"]},
        {"output_id": "journal", "kind": "citation", "entity_ids": ["funder"],
         "source_urls": ["https://example.org/reference"]}]
    body = result(client, data)
    assert body["views"][2]["publication_count"] == 0
    assert body["output_relations"] == data["output_relations"]
    assert body["relation_counts"] == {"coauthorship": 1, "funding": 1, "citation": 1}


@pytest.mark.parametrize("mutation", ["unknown_output", "overlap", "no_evidence", "unknown_entity"])
def test_unfounded_family_and_relation_references_reject(client, mutation):
    data = request_data()
    data["research_families"] = [{"family_id": "study", "output_ids": ["conference", "journal"],
                                  "source_urls": ["https://example.org/extension"]}]
    if mutation == "unknown_output":
        data["research_families"][0]["output_ids"].append("unknown")
    elif mutation == "overlap":
        data["research_families"].append({"family_id": "other", "output_ids": ["journal"],
                                          "source_urls": ["https://example.org/other"]})
    elif mutation == "no_evidence":
        data["research_families"][0]["source_urls"] = []
    else:
        data["output_relations"] = [{"output_id": "conference", "kind": "funding",
                                     "entity_ids": ["unknown"], "source_urls": ["https://example.org/grant"]}]
    assert client.post("/api/v1/research/scope/preview", json=data).status_code == 422
