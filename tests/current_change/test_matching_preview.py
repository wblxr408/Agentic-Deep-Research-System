"""Tasks 3.2–3.5: HTTP outputs and real SQL snapshot isolation on SQLite.

Only the asyncpg connection shape is adapted; production SQL executes unchanged.
Authentication is a fixed test principal, not a credential verification test.
"""
import json
import sqlite3
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import date, datetime

import pytest
import httpx
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.api import research as api
from app.db.matching import MATCHING_SCHEMA_SQL
from app.security.auth import Principal, require_principal

OWNER_A = "11111111-1111-4111-8111-111111111111"
OWNER_B = "22222222-2222-4222-8222-222222222222"


@pytest.fixture
def client(monkeypatch):
    database = sqlite3.connect(":memory:", check_same_thread=False, isolation_level=None)
    database.row_factory = sqlite3.Row
    database.executescript("""
      PRAGMA foreign_keys = ON;
      CREATE TABLE auth_principals(id UUID PRIMARY KEY);
      CREATE TABLE research_sessions(id UUID PRIMARY KEY, owner_id UUID NOT NULL);
    """)
    database.executescript(MATCHING_SCHEMA_SQL)
    database.executemany("INSERT INTO auth_principals VALUES (?)", [(OWNER_A,), (OWNER_B,)])

    class Connection:
        @staticmethod
        def params(args):
            return tuple(value.isoformat() if isinstance(value, (date, datetime)) else value for value in args)

        async def fetchrow(self, sql, *args):
            return database.execute(sql, self.params(args)).fetchone()

        async def execute(self, sql, *args):
            return database.execute(sql, self.params(args))

    class Pool:
        @asynccontextmanager
        async def acquire(self):
            yield Connection()

    async def pool():
        return Pool()

    monkeypatch.setattr(api, "get_db_pool", pool)
    app = FastAPI()
    app.include_router(api.router)

    def principal(request: Request):
        return Principal(id=request.headers.get("X-Test-Owner", OWNER_A), username="fixture", auth_type="session")

    app.dependency_overrides[require_principal] = principal
    with TestClient(app) as instance:
        yield instance, database
    database.close()


def feature(value, **extra):
    return {"value": value, "evidence_ids": ["ev"], "reason": "Curated explicit rubric", **extra}


def candidate(key, topic=0.9, evidence=None, kind="university", **extra):
    return {"entity": {"entity_id": key, "name": key, "type": kind, "source_urls": ["https://example.org/org"]},
            "observations": [{"family_id": f"family-{key}", "group_id": "materials-2024",
                "published_on": "2024-06-01", "title": "Battery materials", "evidence_ids": ["ev"],
                "features": {"topic_relevance": feature(topic), "evidence_completeness": feature(evidence)}}],
            **extra}


def snapshot(**extra):
    return {"scope": {"organization_types": ["university"], "disciplines": ["materials"], "topic": "battery materials",
                      "start_date": "2020-01-01", "end_date": "2026-12-31"},
            "evidence_cutoff": "2026-10-19", "evaluation_versions": {"jcr_quartile": "2024"},
            "evidence": [{"evidence_id": "ev", "source_url": "https://example.org/paper",
                          "retrieved_on": "2026-10-19", "verification_status": "confirmed"}],
            "groups": [{"group_id": "materials-2024", "discipline": "materials", "output_type": "journal_article",
                        "metric_year": 2024, "category": "Materials", "feature_rules": {
                            "topic_relevance": "provided_v1", "evidence_completeness": "provided_v1"},
                        "metric_rules": {}}],
            "candidates": [candidate("A", 0.9), candidate("B", 0.8, 0.7)], **extra}


def save(client, data, **kwargs):
    response = client.post("/api/v1/research/matching/snapshots", json=data, **kwargs)
    assert response.status_code == 201, response.text
    return response.json()["snapshot_id"]


def weights(topic=6, completeness=4):
    return {"preset": "custom", "weights": {"topic_relevance": topic, "evidence_completeness": completeness}}


def preview(client, identifier, configuration=None, **extra):
    response = client.post("/api/v1/research/matching/preview", json={
        "snapshot_id": identifier, "configuration": configuration or weights(), **extra})
    assert response.status_code == 200, response.text
    return response.json()


def results(body):
    group = body["groups"][0]
    return {item["entity_id"]: item for item in [*group["complete"], *group["pending_evidence"]]}


def test_unknown_dimension_gives_54_to_94_and_complete_candidate_76(client):
    http, _ = client
    body = preview(http, save(http, snapshot()))
    candidates = results(body)
    assert candidates["A"]["lower_bound"] == pytest.approx(54)
    assert candidates["A"]["upper_bound"] == pytest.approx(94)
    assert candidates["A"]["coverage"] == pytest.approx(0.6)
    assert candidates["A"]["score"] is None
    assert candidates["B"]["score"] == pytest.approx(76)
    assert candidates["B"]["coverage"] == 1
    assert body["groups"][0]["definitely_better"] == []


def test_high_scoring_company_is_excluded_before_scoring_and_unknown_funding_cannot_pass(client):
    http, _ = client
    data = snapshot(candidates=[candidate("company", 1, 1, kind="company"), candidate("unknown", 1, 1),
                               candidate("funded", 0.6, 0.6, facts={"funding": {
                                   "value": True, "verification_status": "confirmed", "evidence_ids": ["ev"]}})],
                    required_relations=["funding"])
    body = preview(http, save(http, data))
    rejected = {item["entity_id"]: item["reasons"] for item in body["excluded"]}
    assert "entity_type_out_of_scope" in rejected["company"]
    assert "required_relation_unverified:funding" in rejected["unknown"]
    assert set(results(body)) == {"funded"}


def test_discipline_time_and_named_entity_constraints_are_frozen(client):
    http, _ = client
    data = snapshot(candidates=[candidate("chosen", 0.8, 0.8), candidate("not-chosen", 1, 1)])
    data["scope"]["entities"] = [data["candidates"][0]["entity"]]
    old = deepcopy(data["candidates"][0]["observations"][0])
    old.update(family_id="old", published_on="2019-01-01")
    data["candidates"][0]["observations"].append(old)
    data["groups"].append({**data["groups"][0], "group_id": "business", "discipline": "business"})
    irrelevant = deepcopy(old)
    irrelevant.update(group_id="business", family_id="other", published_on="2024-01-01")
    data["candidates"][0]["observations"].append(irrelevant)
    body = preview(http, save(http, data))
    assert results(body)["chosen"]["family_count"] == 1
    assert body["excluded"][0]["entity_id"] == "not-chosen"
    assert {item["reason"] for item in body["excluded_observations"]} == {"time_out_of_scope", "discipline_out_of_scope"}


def test_same_context_family_aggregation_is_equal_weight_and_keeps_provenance(client):
    http, _ = client
    data = snapshot(candidates=[candidate("A", 1, 1)])
    second = deepcopy(data["candidates"][0]["observations"][0])
    second.update(family_id="second", features={"topic_relevance": feature(0), "evidence_completeness": feature(1)})
    data["candidates"][0]["observations"].append(second)
    result = results(preview(http, save(http, data)))["A"]
    assert result["score"] == pytest.approx(70)
    assert result["family_count"] == 2
    assert result["contributions"]["topic_relevance"]["lower_contribution"] == pytest.approx(30)
    assert result["contributions"]["topic_relevance"]["evidence_ids"] == ["ev"]
    assert result["contributions"]["topic_relevance"]["rule_version"] == "provided_v1"


def metric_record(scheme="jcr_jif", raw=4.2):
    return {"scheme_id": scheme, "edition": "2024", "metric_year": 2024, "provider": "Clarivate",
            "source_id": "source", "source_url": "https://example.org/metrics", "retrieved_on": "2026-10-19",
            "target_id": "issn:1234-5679", "track": "journal", "category": "Materials", "raw_value": raw,
            "status": "available", "evidence_status": "caller_provided"}


def performance_snapshot():
    data = snapshot(candidates=[candidate("A", 1, 1)])
    for key, raw in [("jcr_jif", 4.2), ("jcr_quartile", "Q1"), ("jcr_jci", 1.2)]:
        data["groups"][0]["metric_rules"][key] = {"provider": "Clarivate", "edition": "2024",
                                                  "normalization_version": "rubric-v1"}
        data["candidates"][0]["observations"][0].setdefault("metrics", {})[key] = {
            "record": metric_record(key, raw), "normalized_value": None if key == "jcr_quartile" else 1,
            "evidence_ids": ["ev"], "reason": "Declared scale rubric"}
    return data


def test_correlated_jcr_metrics_share_parent_cap_with_explained_contributions(client):
    http, _ = client
    identifier = save(http, performance_snapshot())
    for metrics in [{"jcr_jif": 1}, {"jcr_jif": 1, "jcr_quartile": 1, "jcr_jci": 1}]:
        configuration = {"preset": "custom", "weights": {"topic_relevance": 8, "output_performance": 2},
                         "metric_weights": metrics, "performance_groups": {"venue": 1, "paper": 0}}
        candidate_result = results(preview(http, identifier, configuration))["A"]
        performance = candidate_result["contributions"]["output_performance"]
        assert performance["upper_contribution"] == pytest.approx(20)
        assert sum(item["upper_contribution"] for item in performance["metric_contributions"].values()) == pytest.approx(20)
        assert candidate_result["score"] == pytest.approx(100)


def test_unknown_metric_keeps_its_budget_and_known_zero_is_covered(client):
    http, _ = client
    data = performance_snapshot()
    data["candidates"][0]["observations"][0]["metrics"]["jcr_jif"]["normalized_value"] = 0
    del data["candidates"][0]["observations"][0]["metrics"]["jcr_jci"]
    configuration = {"preset": "custom", "weights": {"output_performance": 1},
                     "metric_weights": {"jcr_jif": 6, "jcr_jci": 4},
                     "performance_groups": {"venue": 1, "paper": 0}}
    result = results(preview(http, save(http, data), configuration))["A"]
    assert result["lower_bound"] == 0
    assert result["upper_bound"] == pytest.approx(40)
    assert result["coverage"] == pytest.approx(0.6)


def test_incomparable_groups_are_separate_and_disjoint_intervals_can_be_ordered(client):
    http, _ = client
    data = snapshot(candidates=[candidate("A", 0.2, 0.2), candidate("B", 0.8, 0.8)])
    data["groups"].append({**data["groups"][0], "group_id": "materials-2023", "metric_year": 2023})
    other = candidate("C", 1, 1)
    other["observations"][0]["group_id"] = "materials-2023"
    data["candidates"].append(other)
    body = preview(http, save(http, data))
    assert len(body["groups"]) == 2
    first = next(g for g in body["groups"] if g["group_id"] == "materials-2024")
    assert first["definitely_better"] == [{"better": "B", "worse": "A"}]
    assert body["cross_group_ranking"] is False


def test_reweight_changes_ranking_without_mutating_or_collecting_evidence(client, monkeypatch):
    http, database = client
    def forbid_network(*args, **kwargs):
        raise AssertionError("Matching preview attempted an external HTTP request")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbid_network)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbid_network)
    data = snapshot(candidates=[candidate("A", 0.9, 0.2), candidate("B", 0.4, 0.9)])
    identifier = save(http, data)
    before = database.execute("SELECT payload FROM research_matching_snapshots WHERE id=?", (identifier,)).fetchone()[0]
    first = preview(http, identifier, weights(9, 1))
    second = preview(http, identifier, weights(1, 9))
    assert [x["entity_id"] for x in first["groups"][0]["complete"]] == ["A", "B"]
    assert [x["entity_id"] for x in second["groups"][0]["complete"]] == ["B", "A"]
    assert first["snapshot_id"] == second["snapshot_id"] == identifier
    assert first["external_requests"] == second["external_requests"] == 0
    assert database.execute("SELECT payload FROM research_matching_snapshots WHERE id=?", (identifier,)).fetchone()[0] == before
    assert json.loads(before)["evidence_cutoff"] == "2026-10-19"


def test_another_owner_cannot_read_snapshot_and_payload_cannot_override_candidates(client):
    http, _ = client
    identifier = save(http, snapshot())
    response = http.post("/api/v1/research/matching/preview", headers={"X-Test-Owner": OWNER_B},
                         json={"snapshot_id": identifier, "configuration": weights()})
    assert response.status_code == 404
    response = http.post("/api/v1/research/matching/preview", json={
        "snapshot_id": identifier, "configuration": weights(), "candidates": [candidate("forged", 1, 1)]})
    assert response.status_code == 422


def test_topic_features_can_be_extracted_by_recorded_deterministic_rule(client):
    http, _ = client
    data = snapshot(candidates=[candidate("A", 0, 0)])
    data["groups"][0]["feature_rules"]["topic_relevance"] = "token_overlap_v1"
    data["candidates"][0]["observations"][0]["features"].pop("topic_relevance")
    item = results(preview(http, save(http, data), weights(1, 0)))["A"]
    assert item["score"] == 100
    assert item["contributions"]["topic_relevance"]["rule_version"] == "token_overlap_v1"


def test_no_applicable_dimensions_is_incomparable_without_a_false_zero_interval(client):
    http, _ = client
    body = preview(http, save(http, snapshot()), {"preset": "custom", "weights": {"recency": 1}})
    assert body["groups"][0]["comparison_status"] == "no_applicable_dimensions"
    assert results(body)["A"]["lower_bound"] is None
    assert results(body)["A"]["upper_bound"] is None


def test_filtering_to_only_zero_weight_metrics_does_not_renormalize_or_crash(client):
    http, _ = client
    configuration = {"preset": "custom", "weights": {"output_performance": 1},
                     "metric_weights": {"ccf": 1, "jcr_jif": 0},
                     "performance_groups": {"venue": 1, "paper": 0}}
    body = preview(http, save(http, performance_snapshot()), configuration)
    assert results(body)["A"]["score"] is None
    assert results(body)["A"]["lower_bound"] == 0
    assert results(body)["A"]["upper_bound"] == 100


def test_session_binding_rejects_other_owner_and_rechecks_access_on_preview(client):
    http, database = client
    own_session = "33333333-3333-4333-8333-333333333333"
    other_session = "44444444-4444-4444-8444-444444444444"
    database.executemany("INSERT INTO research_sessions VALUES (?, ?)", [(own_session, OWNER_A), (other_session, OWNER_B)])
    rejected = http.post("/api/v1/research/matching/snapshots", json=snapshot(session_id=other_session))
    assert rejected.status_code == 404
    identifier = save(http, snapshot(session_id=own_session))
    assert results(preview(http, identifier))["B"]["score"] == pytest.approx(76)
    database.execute("UPDATE research_sessions SET owner_id=? WHERE id=?", (OWNER_B, own_session))
    response = http.post("/api/v1/research/matching/preview", json={"snapshot_id": identifier, "configuration": weights()})
    assert response.status_code == 404


def test_unreviewed_relation_evidence_never_satisfies_confirmed_hard_condition(client):
    http, _ = client
    data = snapshot(candidates=[candidate("A", 1, 1, facts={"funding": {
        "value": True, "verification_status": "confirmed", "evidence_ids": ["ev"]}})], required_relations=["funding"])
    data["evidence"][0]["verification_status"] = "unreviewed"
    body = preview(http, save(http, data))
    assert body["groups"] == []
    assert body["excluded"][0]["reasons"] == ["required_relation_unverified:funding"]


def test_invalid_raw_grade_cannot_enter_a_scoring_snapshot(client):
    http, _ = client
    data = performance_snapshot()
    data["candidates"][0]["observations"][0]["metrics"]["jcr_quartile"]["record"]["raw_value"] = "Q9"
    assert http.post("/api/v1/research/matching/snapshots", json=data).status_code == 422


def test_inapplicable_ccf_cannot_be_declared_as_a_materials_journal_metric(client):
    http, _ = client
    data = snapshot()
    data["groups"][0]["metric_rules"]["ccf"] = {
        "provider": "CCF", "edition": "2022", "normalization_version": "grades-v1"}
    assert http.post("/api/v1/research/matching/snapshots", json=data).status_code == 422


def test_explicit_metric_threshold_filters_before_aggregation(client):
    http, _ = client
    data = performance_snapshot()
    data["required_metrics"] = [{"scheme_id": "jcr_jif", "minimum": 5}]
    body = preview(http, save(http, data))
    assert body["groups"] == []
    assert body["excluded_observations"][0]["reason"] == "required_metric_not_satisfied:jcr_jif"
    data["required_metrics"][0]["minimum"] = 4
    assert results(preview(http, save(http, data)))["A"]["score"] == 100


def test_partial_family_coverage_is_averaged_without_dropping_the_unknown(client):
    http, _ = client
    data = snapshot(candidates=[candidate("A", 1, 1)])
    other = deepcopy(data["candidates"][0]["observations"][0])
    other.update(family_id="unknown", features={"topic_relevance": feature(None)})
    data["candidates"][0]["observations"].append(other)
    item = results(preview(http, save(http, data), weights(1, 0)))["A"]
    assert item["lower_bound"] == 50
    assert item["upper_bound"] == 100
    assert item["coverage"] == 0.5
    assert item["score"] is None


@pytest.mark.parametrize("mutation", ["missing_evidence", "duplicate_family", "inconsistent_metric", "bad_value"])
def test_inconsistent_snapshot_is_rejected_before_persistence(client, mutation):
    http, database = client
    data = performance_snapshot()
    if mutation == "missing_evidence":
        data["candidates"][0]["observations"][0]["features"]["topic_relevance"]["evidence_ids"] = ["unknown"]
    elif mutation == "duplicate_family":
        data["candidates"][0]["observations"].append(deepcopy(data["candidates"][0]["observations"][0]))
    elif mutation == "inconsistent_metric":
        data["candidates"][0]["observations"][0]["metrics"]["jcr_jif"]["record"]["metric_year"] = 2020
    else:
        data["candidates"][0]["observations"][0]["features"]["topic_relevance"]["value"] = 1.5
    assert http.post("/api/v1/research/matching/snapshots", json=data).status_code == 422
    assert database.execute("SELECT COUNT(*) FROM research_matching_snapshots").fetchone()[0] == 0
