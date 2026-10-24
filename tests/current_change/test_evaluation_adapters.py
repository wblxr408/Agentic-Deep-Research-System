"""Consumer behavior for evaluation tasks 2.1–2.5; import fixtures are synthetic."""
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


def query(**extra):
    return {"disciplines": ["computing"], "output_type": "conference_paper", "target_id": "dblp:conf/sigcomm",
            "publication_year": 2022, "metric_year": 2022, **extra}


def bundle(scheme="ccf", value="A", **extra):
    return {"source_id": f"{scheme}-fixture", "scheme_id": scheme, "edition": "2022", "metric_year": 2022,
            "provider": "Synthetic authorized fixture", "source_url": "https://example.org/licensed-data",
            "retrieved_on": "2026-10-19", "access": "authorized_import", "authorized": True,
            "coverage": "partial", "records": [{"target_id": "dblp:conf/sigcomm", "track": "main",
                "category": "Computer networks", "raw_value": value}], **extra}


def evaluate(client, request):
    response = client.post("/api/v1/research/evaluation/preview", json=request)
    assert response.status_code == 200, response.text
    return {item["scheme_id"]: item for item in response.json()["evaluations"]}


@pytest.mark.parametrize("disciplines,kind,expected,excluded", [
    (["computing"], "conference_paper", ["ccf", "icore", "scopus", "fwci"], ["jcr_jif", "abdc"]),
    (["materials"], "journal_article", ["jcr_jif", "cas_partition", "citescore", "cnci"], ["ccf", "icore", "abdc"]),
    (["business"], "journal_article", ["abdc", "ajg", "wos_ssci"], ["ccf", "icore"]),
])
def test_applicability_respects_discipline_and_output(client, disciplines, kind, expected, excluded):
    result = evaluate(client, query(disciplines=disciplines, output_type=kind))
    assert all(result[key]["applicable"] is True for key in expected)
    assert all(result[key]["availability"] == "not_applicable" and result[key]["reason"] for key in excluded)
    assert {"wos_scie", "wos_ssci", "wos_ahci", "wos_esci", "scopus", "jcr_jif", "jcr_quartile",
            "jcr_jci", "cas_partition", "citescore", "citescore_percentile", "sjr", "snip", "ccf", "icore",
            "abdc", "ajg", "citation_percentile", "cnci", "fwci"} == set(result)


def test_ccf_historical_editions_keep_exact_identity_and_do_not_rank_workshop(client):
    older = bundle(value="B", edition="2019", metric_year=2019)
    newer = bundle(value="A", source_id="new", edition="2022")
    request = query(sources=[older, newer], use_public_snapshots=False)
    assert evaluate(client, request)["ccf"]["records"][0]["raw_value"] == "A"
    assert evaluate(client, {**request, "metric_year": 2019})["ccf"]["records"][0]["raw_value"] == "B"
    assert evaluate(client, {**request, "track": "workshop"})["ccf"]["availability"] == "data_missing"
    assert evaluate(client, {**request, "target_id": "dblp:conf/sigcomm-similar"})["ccf"]["records"] == []
    assert evaluate(client, {**request, "metric_year": 2020})["ccf"]["availability"] == "data_missing"


def test_icore_is_separate_and_edition_can_be_explicit(client):
    result = evaluate(client, query(sources=[bundle(), bundle("icore", "A*")], use_public_snapshots=False,
                                    editions={"icore": "2022"}))
    assert result["ccf"]["records"][0]["raw_value"] == "A"
    assert result["icore"]["records"][0]["raw_value"] == "A*"


def test_journal_metrics_preserve_all_categories_and_years_in_authorized_import(client):
    sources = []
    values = {"wos_scie": True, "wos_ssci": True, "wos_ahci": True, "wos_esci": True, "scopus": True,
              "jcr_jif": 4.2, "jcr_quartile": "Q2", "jcr_jci": 1.4, "cas_partition": "2",
              "citescore": 8.1, "citescore_percentile": 85.0, "sjr": 1.1, "snip": 1.2}
    for key, value in values.items():
        item = bundle(key, value)
        item["records"] = [{"target_id": "issn:0022-3808", "track": "journal", "category": "Economics",
                             "raw_value": value}]
        if key == "jcr_quartile":
            item["records"].append({"target_id": "issn:0022-3808", "track": "journal",
                                      "category": "Business", "raw_value": "Q1"})
        sources.append(item)
    result = evaluate(client, query(output_type="journal_article", disciplines=["business"],
                                   target_id="issn:0022-3808", sources=sources, use_public_snapshots=False))
    assert {r["raw_value"] for r in result["jcr_quartile"]["records"]} == {"Q1", "Q2"}
    assert all(result[key]["availability"] == "available" for key in values)
    assert result["jcr_jif"]["records"][0]["metric_year"] == 2022
    assert result["jcr_jif"]["records"][0]["evidence_status"] == "caller_provided"
    assert evaluate(client, query(output_type="journal_article", disciplines=["business"], metric_year=2021,
                                  target_id="issn:0022-3808", sources=sources,
                                  use_public_snapshots=False))["jcr_jif"]["availability"] == "data_missing"


def test_source_unavailable_missing_not_indexed_and_conflict_are_different(client):
    unavailable = evaluate(client, query(output_type="journal_article", disciplines=["materials"],
                                        use_public_snapshots=False))
    assert unavailable["jcr_jif"]["availability"] == "source_unavailable"
    partial = bundle(coverage="partial", records=[])
    complete = bundle(coverage="complete", records=[])
    assert evaluate(client, query(sources=[partial], use_public_snapshots=False))["ccf"]["availability"] == "data_missing"
    assert evaluate(client, query(sources=[complete], use_public_snapshots=False))["ccf"]["availability"] == "not_indexed"
    other = bundle(value="B", source_id="conflicting")
    assert evaluate(client, query(sources=[bundle(), other], use_public_snapshots=False))["ccf"]["availability"] == "conflict"


def test_business_guides_do_not_convert_or_confuse_editions(client):
    a = bundle("abdc", "A*")
    b = bundle("ajg", "4")
    historical = bundle("ajg", "3", metric_year=2021, edition="2021", source_id="old-ajg")
    for item in (a, b, historical):
        item["records"][0].update(target_id="issn:0022-3808", track="journal", category="Economics")
    request = query(disciplines=["business"], output_type="journal_article", target_id="issn:0022-3808",
                    sources=[a, b, historical], use_public_snapshots=False)
    result = evaluate(client, request)
    assert result["abdc"]["records"][0]["raw_value"] == "A*"
    assert result["ajg"]["records"][0]["raw_value"] == "4"
    assert evaluate(client, {**request, "metric_year": 2021})["ajg"]["records"][0]["raw_value"] == "3"


def test_paper_metrics_preserve_provider_normalization_and_citation_cutoff(client):
    sources = []
    for key, value, provider in [("fwci", 2.3, "OpenAlex"), ("cnci", 1.7, "Clarivate InCites"),
                                 ("citation_percentile", 0.93, "OpenAlex")]:
        item = bundle(key, value, provider=provider)
        item["records"][0].update(target_id="doi:10.1000/example", track="work",
            category="Materials", publication_year=2020, document_type="article", citation_cutoff="2026-10-01")
        sources.append(item)
    result = evaluate(client, query(disciplines=["materials"], output_type="journal_article",
                                   target_id="doi:10.1000/example", sources=sources, use_public_snapshots=False))
    assert result["fwci"]["records"][0]["provider"] == "OpenAlex"
    assert result["cnci"]["records"][0]["citation_cutoff"] == "2026-10-01"
    assert result["citation_percentile"]["records"][0]["publication_year"] == 2020
    assert result["citation_percentile"]["records"][0]["raw_value"] == 0.93


@pytest.mark.parametrize("mutation", ["unauthorized", "bad_grade", "bad_quartile", "no_citation_context", "negative", "unknown_scheme"])
def test_import_rejects_unusable_data(client, mutation):
    item = bundle()
    if mutation == "unauthorized":
        item["authorized"] = False
    elif mutation == "bad_grade":
        item["records"][0]["raw_value"] = "Q1"
    elif mutation == "bad_quartile":
        item.update(scheme_id="jcr_quartile")
        item["records"][0]["raw_value"] = "Q9"
    elif mutation == "no_citation_context":
        item.update(scheme_id="cnci")
        item["records"][0]["raw_value"] = 1.4
    elif mutation == "negative":
        item.update(scheme_id="jcr_jif")
        item["records"][0]["raw_value"] = -1
    else:
        item["scheme_id"] = "invented"
    response = client.post("/api/v1/research/evaluation/preview", json=query(sources=[item]))
    assert response.status_code == 422, response.text
