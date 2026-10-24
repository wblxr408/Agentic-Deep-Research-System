"""Consumer behavior of task 3.1 only; no matching/ranking execution."""
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


def post(client, data):
    response = client.post("/api/v1/research/weights/preview", json=data)
    assert response.status_code == 200, response.text
    return response.json()


def test_six_to_four_normalizes_and_zero_disables_without_replacing_raw_input(client):
    request = {"preset": "custom", "weights": {"topic_relevance": 6, "evidence_completeness": 4,
                                                "cooperation_complementarity": 0}}
    result = post(client, request)
    assert result["effective_weights"]["topic_relevance"] == pytest.approx(0.6)
    assert result["effective_weights"]["evidence_completeness"] == pytest.approx(0.4)
    assert result["effective_weights"]["cooperation_complementarity"] == 0
    assert result["raw_config"]["weights"]["topic_relevance"]["weight"] == 6


def test_switching_off_preserves_weight_and_restore_selects_the_preset(client):
    changed = post(client, {"preset": "research_development", "weights": {
        "topic_relevance": {"weight": 99, "enabled": False}}})
    assert changed["effective_weights"]["topic_relevance"] == 0
    assert changed["raw_config"]["weights"]["topic_relevance"]["weight"] == 99
    restored = post(client, {"preset": "research_development"})
    assert restored["effective_weights"]["topic_relevance"] == pytest.approx(0.35)
    assert restored["effective_weights"]["cooperation_complementarity"] == 0
    assert post(client, {"preset": "cooperation_discovery"})["effective_weights"]["cooperation_complementarity"] == pytest.approx(0.15)


def test_metric_levels_and_mappings_are_versioned_preferences(client):
    result = post(client, {"preset": "custom", "weights": {"output_performance": 1},
        "metric_weights": {"ccf": 6, "jcr_quartile": 4, "fwci": 2},
        "performance_groups": {"venue": 3, "paper": 1},
        "mappings": [{"scheme_id": "ccf", "version": "my-ccf-v2", "scores": {"A": 1, "B": 0.7, "C": 0.2}}]})
    assert result["effective_groups"] == {"venue": 0.75, "paper": 0.25}
    assert result["effective_metric_weights"]["ccf"] == pytest.approx(0.6)
    assert result["effective_metric_weights"]["jcr_quartile"] == pytest.approx(0.4)
    assert result["effective_metric_weights"]["fwci"] == 1
    assert result["mappings"][0]["version"] == "my-ccf-v2"
    assert result["rule_version"]


def test_large_finite_weights_normalize_without_overflow(client):
    result = post(client, {"preset": "custom", "weights": {"topic_relevance": 1e308,
                                                            "evidence_completeness": 1e308}})
    assert result["effective_weights"]["topic_relevance"] == 0.5
    assert result["effective_weights"]["evidence_completeness"] == 0.5


def test_disabled_performance_parent_can_keep_disabled_child_levels(client):
    result = post(client, {"preset": "custom", "weights": {"topic_relevance": 1, "output_performance": 0},
                           "performance_groups": {"venue": 0, "paper": 0}, "metric_weights": {"ccf": 0}})
    assert result["effective_groups"] == {"venue": 0, "paper": 0}
    assert result["effective_metric_weights"]["ccf"] == 0


@pytest.mark.parametrize("configuration", [
    {"preset": "custom", "weights": {"topic_relevance": -1}},
    {"preset": "custom", "weights": {"topic_relevance": True}},
    {"preset": "custom", "weights": {"topic_relevance": "NaN"}},
    {"preset": "custom", "weights": {"topic_relevance": "Infinity"}},
    {"preset": "custom", "weights": {"unknown": 1}},
    {"preset": "custom", "weights": {"topic_relevance": 0}},
    {"preset": "custom", "weights": {}},
    {"metric_weights": {"ccf": 0}},
    {"mappings": [{"scheme_id": "ccf", "version": "v1", "scores": {"A": 0.2, "B": 0.8, "C": 0.1}}]},
    {"mappings": [{"scheme_id": "ccf", "version": "", "scores": {"A": 1, "B": 0.8, "C": 0.1}}]},
    {"mappings": [{"scheme_id": "ccf", "version": "v1", "scores": {"A": 1, "B": 0.8, "D": 0.1}}]},
])
def test_invalid_configuration_is_rejected(client, configuration):
    response = client.post("/api/v1/research/weights/preview", json=configuration)
    assert response.status_code == 422, response.text
