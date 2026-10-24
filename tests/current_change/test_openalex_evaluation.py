"""New OpenAlex payload-to-evaluation adapter behavior, not live API tests."""
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


def payload():
    return {"retrieved_on": "2026-10-19", "citation_cutoff": "2023-12-31", "work": {
        "id": "https://openalex.org/W123", "publication_year": 2020, "type": "article",
        "updated_date": "2026-10-01T00:00:00", "fwci": 2.2,
        "citation_normalized_percentile": {"value": 0.95},
        "primary_topic": {"subfield": {"id": "https://openalex.org/subfields/2501", "display_name": "Materials"}}}}


def test_openalex_payload_preserves_original_values_provider_and_missing_cnci(client):
    response = client.post("/api/v1/research/evaluation/openalex/normalize", json=payload())
    assert response.status_code == 200, response.text
    sources = response.json()["sources"]
    assert {s["scheme_id"] for s in sources} == {"fwci", "citation_percentile"}
    assert {s["provider"] for s in sources} == {"OpenAlex"}
    fwci = next(s for s in sources if s["scheme_id"] == "fwci")
    assert fwci["records"][0]["raw_value"] == 2.2
    assert fwci["records"][0]["publication_year"] == 2020
    assert fwci["records"][0]["citation_cutoff"] == "2023-12-31"


def test_null_metrics_remain_missing_and_are_never_filled_from_citation_count(client):
    request = payload()
    request["work"].update(fwci=None, citation_normalized_percentile=None, cited_by_count=1000)
    response = client.post("/api/v1/research/evaluation/openalex/normalize", json=request)
    assert response.status_code == 200, response.text
    assert all(s["records"][0]["status"] == "data_missing" and s["records"][0]["raw_value"] is None
               for s in response.json()["sources"])


def test_work_identity_and_normalization_context_are_required(client):
    request = payload()
    request["work"].pop("primary_topic")
    assert client.post("/api/v1/research/evaluation/openalex/normalize", json=request).status_code == 422
