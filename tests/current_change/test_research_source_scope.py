"""Current source-selection contract: constrain discovery and every read hop."""
from types import SimpleNamespace as NS
from urllib.parse import urlsplit

import pytest

from app.channels.execution import HttpReader
from app.channels.models import ChannelError
from app.research_sources import ResearchSourceScope


@pytest.mark.parametrize("initial", ["https://arxiv.org/abs/1234", "https://outside.example/paper"])
def test_selected_scope_blocks_unselected_host_before_connection(monkeypatch, initial):
    import app.channels.execution as transport

    contacted, resolved = [], []

    def resolve(host, *args, **kwargs):
        resolved.append(host)
        return [(2, 1, 6, "", ("93.184.216.34", 443))]

    class Connection:
        sock = None

        def __init__(self, host, *args):
            self.host = host
            contacted.append(host)

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return NS(status=302 if self.host == "arxiv.org" else 200,
                      getheader=lambda *a: "https://outside.example/paper",
                      read=lambda *a: b"", getheaders=lambda: [])

        def close(self):
            pass

    monkeypatch.setattr(transport.socket, "getaddrinfo", resolve)
    monkeypatch.setattr(transport, "_PinnedHTTPS", Connection)

    def admit(url):
        if urlsplit(url).hostname != "arxiv.org":
            raise ChannelError("source_out_of_scope")

    reader = HttpReader()
    reader.url_validator = admit
    outcome = "accepted"
    try:
        reader.read(initial)
    except ChannelError as exc:
        outcome = exc.category
    assert outcome == "source_out_of_scope"
    expected = ["arxiv.org"] if "arxiv.org" in initial else []
    assert contacted == resolved == expected


def test_mixed_scope_delivers_only_selected_leads_with_distinct_source_uses():
    scope = ResearchSourceScope(groups=["official", "dblp", "arxiv", "google_scholar"],
                                official_domains=["Example.EDU"])
    urls = ["https://lab.example.edu/papers", "https://dblp.org/rec/123", "https://arxiv.org/abs/123",
            "https://scholar.google.com/scholar?q=network", "https://example.edu.evil.test/a",
            "https://notexample.edu/a", "https://dl.acm.org/doi/123"]
    leads, rejected = scope.filter_leads([NS(url=u, title="paper", snippet="lead") for u in urls])
    assert [lead["url"] for lead in leads] == urls[:4]
    assert [lead["source_use"] for lead in leads] == [
        "official_document_check_entity_and_claim", "bibliographic_metadata",
        "preprint_check_version_and_review_status", "discovery_only"]
    assert {r["url"] for r in rejected} == set(urls[4:])
    with pytest.raises(ChannelError) as error:
        scope.admit(urls[3])
    assert error.value.category == "discovery_only"
    single = ResearchSourceScope(groups=["publishers"], publisher_domains=["papers.example.org"])
    assert single.admit("https://papers.example.org/proceedings/2025") == "publishers"
    with pytest.raises(ChannelError):
        single.admit("https://arxiv.org/abs/123")


@pytest.mark.parametrize("config", [
    {"groups": []}, {"groups": ["unknown"]}, {"groups": ["official"]},
    {"groups": ["official"], "official_domains": ["https://example.edu"]},
    {"groups": ["official"], "official_domains": ["*.example.edu"]},
    {"groups": ["official"], "official_domains": ["edu.cn"]},
    {"groups": ["official"], "official_domains": ["lab.local"]},
])
def test_invalid_source_selection_is_rejected(config):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ResearchSourceScope(**config)


def test_runtime_scope_filters_search_and_prevents_disallowed_reads(monkeypatch):
    import openminion
    import app.claim_verification as verification
    from app.openminion_research import OrganizationResearchRequest, run_research

    reads, queries, outputs = [], [], {}
    # The subject here is the source boundary in actual research tool closures;
    # model and SDK scheduling are external substitutes, not live SDK evidence.
    monkeypatch.setattr(openminion, "tool", lambda **kwargs: lambda fn: fn)
    monkeypatch.setattr(openminion.APIRuntime, "from_manager", lambda *a, **kw: NS(close=lambda: None))
    monkeypatch.setattr(verification, "audit_report", lambda *a, **kw: {
        "claims": [], "total_claims": 0, "supported_claims": 0})

    class Agent:
        def __init__(self, **kwargs):
            self.tools = {fn.__name__: fn for fn in kwargs["tools"]}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def run(self, *args, **kwargs):
            import json
            outputs["search"] = json.loads(self.tools["search_organizations"]("network research"))
            for key, url in [("outside", "https://outside.example/a"),
                             ("scholar", "https://scholar.google.com/scholar?q=network"),
                             ("official", "https://lab.example.edu/papers")]:
                outputs[key] = json.loads(self.tools["read_source"](url))
            return NS(text=json.dumps({"report": "资料有待进一步核验。", "task_status": "partial", "gaps": []}),
                      run_id="fixture", run_state="completed", stats={})

    monkeypatch.setattr(openminion, "Agent", Agent)

    def search(query, **kwargs):
        queries.append(query)
        return [NS(url=url, title="Lab", snippet="network") for url in
                ["https://lab.example.edu/papers", "https://outside.example/a"]]

    class Reader:
        def read(self, url, **kwargs):
            reads.append(url)
            return NS(url=url, status=200, headers={"content-type": "text/plain"},
                      body=b"The laboratory researches network congestion control.")

    task = OrganizationResearchRequest(organizations=[{"name": "Example Lab", "type": "laboratory"}],
        topic="Network research", start_year=2025, end_year=2025,
        source_scope={"groups": ["official", "google_scholar"], "official_domains": ["example.edu"]})
    result = run_research(task, model_config={"provider": "openai", "model": "fixture", "api_key": "fixture"},
                          search=search, reader=Reader())
    assert outputs["outside"] == {"error": "source_out_of_scope"}
    assert outputs["scholar"] == {"error": "discovery_only"}
    assert [lead["url"] for lead in outputs["search"]["leads"]] == ["https://lab.example.edu/papers"]
    assert reads == ["https://lab.example.edu/papers"]
    assert "site:example.edu" in queries[0] and "site:scholar.google.com" in queries[0]
    assert result["source_policy"]["domains_by_group"]["official"] == ("example.edu",)
    assert result["source_uses"][outputs["official"]["evidence_id"]]["group"] == "official"
    assert result["trace"][0]["rejected_sources"] == [
        {"url": "https://outside.example/a", "reason": "source_out_of_scope"}]
