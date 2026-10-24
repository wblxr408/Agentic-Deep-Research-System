"""Consumer regressions for response shapes observed during real collection."""
import io
import json
import socket
import sys

import pytest

from app.agents.search import SearchAgent
from app.channels.execution import CommandRunner, HttpReader
from app.channels.models import ChannelError, CollectionRequest
from tests.channels.test_channels import Reader, Runner, service


def test_web_results_retain_nested_title_and_matching_snippet(tmp_path):
    page = '''<div class="result results_links"><div class="result__body">
    <h2><a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fdocs.langchain.com%2Flanggraph" class="result__a">LangGraph <b>overview</b></a></h2>
    <div class="result__extras"><div class="result__extras__url">docs.langchain.com</div></div>
    <a class="result__snippet">Build <b>durable</b> agents &amp; workflows.</a></div></div>
    <div class="result"><a class="result__a" href="https://github.com/langchain-ai/langgraph">Source</a>
    <a class="result__snippet">Framework source.</a></div>'''
    result = service(tmp_path, reader=Reader(page, {})).collect(CollectionRequest(channel="web", query="LangGraph"))
    assert result.status == "success"
    assert [(i.title, i.content) for i in result.items] == [
        ("LangGraph overview", "Build durable agents & workflows."), ("Source", "Framework source.")]
    assert result.items[0].url == "https://docs.langchain.com/langgraph"
    assert SearchAgent()._parse_duckduckgo_html(page, "LangGraph")[0].snippet == "Build durable agents & workflows."


@pytest.mark.parametrize("kind", ["podcast", "episode"])
def test_xiaoyuzhou_public_page_returns_descriptions_and_shownotes(tmp_path, kind):
    data = {"props": {"pageProps": {kind: {
        "pid": "a" * 24, "eid": "b" * 24, "title": "商业访谈", "description": "讨论商业变化。",
        "shownotes": "<p>02:15 城市研究</p><p>参考资料 &amp; 时间轴</p>",
        "episodes": [{"eid": "c" * 24, "title": "城市观察", "description": "研究公开城市数据"}],
    }}}}
    page = '<script type="application/json" id="__NEXT_DATA__">' + json.dumps(data, ensure_ascii=False) + '</script>'
    result = service(tmp_path, reader=Reader(page)).collect(CollectionRequest(
        channel="xiaoyuzhou", operation="read", query=f"https://www.xiaoyuzhoufm.com/{kind}/" + "a" * 24))
    assert result.status == "success"
    assert result.items[0].title == "商业访谈"
    assert "讨论商业变化。" in result.items[0].content
    assert "02:15 城市研究\n参考资料 & 时间轴" in result.items[0].content
    assert "音频转录未获取" in result.items[0].content
    if kind == "podcast":
        assert "https://www.xiaoyuzhoufm.com/episode/" + "c" * 24 in result.items[0].content


def test_missing_xiaoyuzhou_does_not_fall_back_into_error_page_evidence(tmp_path):
    reader = Reader(ChannelError("not_found"), 'Title: missing\nMarkdown Content:\n404')
    result = service(tmp_path, reader=reader).collect(CollectionRequest(
        channel="xiaoyuzhou", operation="read", query="https://www.xiaoyuzhoufm.com/podcast/" + "a" * 24))
    assert result.items == [] and result.attempts[0].error_category == "not_found"
    assert len(reader.calls) == 1


def test_bili_normalized_video_envelope_retains_metadata_and_partial_label(tmp_path):
    runner = Runner({"ok": True, "data": {"video": {"bvid": "BV178w1z7EHQ", "title": "教程", "description": "实际视频介绍"}}})
    svc = service(tmp_path, runner=runner)
    from app.channels.models import ChannelConfig
    svc.configure("bilibili", ChannelConfig(backends=["bili"]))
    result = svc.collect(CollectionRequest(channel="bilibili", operation="read", query="https://www.bilibili.com/video/BV178w1z7EHQ"))
    assert result.status == "partial"
    assert "实际视频介绍" in result.items[0].content
    assert "字幕未获取" in result.items[0].content


@pytest.mark.parametrize("status, category", [(404, "not_found"), (412, "account_risk")])
def test_http_rejection_reports_missing_source_or_platform_risk(monkeypatch, status, category):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    class Response(io.BytesIO):
        pass
    response = Response(b"error page")
    response.status = status
    class Connection:
        def __init__(self, *args): pass
        def request(self, *args, **kwargs): pass
        def getresponse(self): return response
        def close(self): pass
    monkeypatch.setattr("app.channels.execution._PinnedHTTPS", Connection)
    with pytest.raises(ChannelError, match=category):
        HttpReader().get("https://www.xiaoyuzhoufm.com/podcast/" + "a" * 24)


def test_persistent_native_tool_mapping_executes_requested_collection_input(tmp_path, monkeypatch):
    mapping = tmp_path / "native-tools.json"
    mapping.write_text(json.dumps({"bili": [sys.executable, "-c", "import sys,json; print(json.dumps({'query': sys.argv[1:]}))"]}))
    monkeypatch.delenv("CHANNELS_TOOL_PREFIXES", raising=False)
    monkeypatch.setenv("CHANNELS_TOOL_PREFIXES_FILE", str(mapping))
    result = json.loads(CommandRunner().run(["bili", "search", "LangGraph & tools", "--json"]))
    assert result == {"query": ["search", "LangGraph & tools", "--json"]}


def test_configured_browser_endpoint_is_used_for_collection(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENCLI_CDP_ENDPOINT", "http://127.0.0.1:9223")
    expression = "import os,json; print(json.dumps([{'url':'https://www.reddit.com/r/agents/comments/abc/topic/','title':'Topic','content':os.getenv('OPENCLI_CDP_ENDPOINT','wrong browser')}]))"
    monkeypatch.setenv("CHANNELS_TOOL_PREFIXES", json.dumps({"opencli": [sys.executable, "-c", expression]}))
    result = service(tmp_path, runner=CommandRunner()).collect(CollectionRequest(channel="reddit", query="LangGraph"))
    assert result.items[0].content == "http://127.0.0.1:9223"


def test_search_challenge_uses_independent_engine_without_reciting_challenge(tmp_path):
    reader = Reader('<form action="/anomaly.js">Please select all ducks</form>', {})
    runner = Runner("Title: LangGraph docs\nURL: https://docs.langchain.com/oss/python/langgraph/overview\nHighlights:\nDurable workflows.")
    svc = service(tmp_path, runner=runner, reader=reader)
    from app.channels.models import ChannelConfig
    svc.configure("web", ChannelConfig(backends=["duckduckgo", "exa-mcp"]))
    result = svc.collect(CollectionRequest(channel="web", query="LangGraph"))
    assert result.items[0].content.endswith("Durable workflows.")
    assert result.attempts[0].error_category == "access_denied"
    assert len(reader.calls) == 1


def test_linkedin_requires_operator_completed_session_before_invoking_autologin_tool(tmp_path, monkeypatch):
    monkeypatch.delenv("CHANNELS_LINKEDIN_SESSION_READY", raising=False)
    runner = Runner([{ "url": "https://www.linkedin.com/jobs/view/123", "title": "Python", "description": "Job details" }])
    result = service(tmp_path, runner=runner).collect(CollectionRequest(channel="linkedin", query="Python engineer"))
    assert result.attempts[0].error_category == "auth_required"
    assert runner.calls == [] and result.items == []


@pytest.mark.parametrize("channel, error, category", [
    ("boss", {"code": "BROWSER_SESSION_NOT_FOUND", "message": "No reusable logged-in browser session"}, "auth_required"),
    ("reddit", {"code": "BROWSER_CONNECT", "message": "Browser Bridge unavailable"}, "configuration_required"),
    ("reddit", {"code": "UNKNOWN", "message": "Evaluate error: TypeError: Failed to fetch"}, "network"),
])
def test_real_tool_errors_distinguish_login_browser_setup_and_network(tmp_path, channel, error, category):
    result = service(tmp_path, runner=Runner({"ok": False, "error": error})).collect(CollectionRequest(channel=channel, query="Python"))
    assert result.items == []
    assert result.attempts[0].error_category == category


def test_public_search_feed_returns_source_and_description_without_paid_engine(tmp_path):
    reader = Reader(ChannelError("access_denied"), '<rss><channel><item><title>LangGraph overview</title><link>https://docs.langchain.com/oss/python/langgraph/overview</link><description>Durable execution and streaming.</description></item></channel></rss>')
    from app.channels.models import ChannelConfig
    svc = service(tmp_path, reader=reader)
    svc.configure("web", ChannelConfig(backends=["duckduckgo", "bing-rss"]))
    result = svc.collect(CollectionRequest(channel="web", query="LangGraph"))
    assert result.status == "success"
    assert result.items[0].content == "Durable execution and streaming."
    assert result.items[0].url == "https://docs.langchain.com/oss/python/langgraph/overview"


def test_exa_free_quota_message_is_rate_limit_and_not_content(tmp_path):
    runner = Runner("You've hit Exa's free MCP rate limit. To continue using without limits, create your own Exa API key.")
    result = service(tmp_path, runner=runner).collect(CollectionRequest(channel="exa", query="LangGraph"))
    assert result.items == [] and result.attempts[0].error_category == "rate_limited"
