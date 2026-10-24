"""Functional contracts; upstream responses are fixtures, never live-service claims."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from app.channels.catalog import route_query
from app.channels.execution import CommandRunner, HttpReader
from app.channels.models import ChannelConfig, ChannelError, CollectionRequest
from app.channels.service import ChannelService
from app.channels.store import ChannelStore

OWNER_A = "00000000-0000-0000-0000-000000000001"
OWNER_B = "00000000-0000-0000-0000-000000000002"


@pytest.fixture(autouse=True)
def explicit_test_platform_credentials(monkeypatch):
    monkeypatch.setenv("TWITTER_AUTH_TOKEN", "fixture-token")
    monkeypatch.setenv("TWITTER_CT0", "fixture-csrf")
    monkeypatch.setenv("CHANNELS_LINKEDIN_SESSION_READY", "true")


class Runner:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
    def run(self, argv, **kwargs):
        self.calls.append(argv)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return json.dumps(response) if not isinstance(response, str) else response


class Reader:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []
    def get(self, url, **kwargs):
        self.calls.append(url)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return json.dumps(response) if not isinstance(response, str) else response


def service(tmp_path, runner=None, reader=None, owner=OWNER_A):
    return ChannelService(owner, store=ChannelStore(tmp_path), commands=runner or Runner(), http=reader or Reader())


def test_missing_primary_falls_back_to_public_github_content_and_retains_attempts(tmp_path):
    svc = service(tmp_path, Runner(ChannelError("dependency_missing")), Reader({"items": [
        {"html_url": "https://github.com/a/research", "full_name": "a/research", "description": "Research DAG"}]}))
    result = svc.collect(CollectionRequest(channel="github", query="research"))
    assert result.status == "success"
    assert result.items[0].content == "Research DAG"
    assert result.items[0].backend == "github-api"
    assert [(a.status, a.error_category) for a in result.attempts] == [("failed", "dependency_missing"), ("success", None)]
    assert svc.catalog()[2]["last_attempt"]["status"] == "success"


@pytest.mark.parametrize("category", ["auth_required", "account_risk", "rate_limited"])
def test_auth_and_risk_do_not_retry_another_backend_or_produce_evidence(tmp_path, category):
    runner = Runner(ChannelError(category), [{"url": "https://x.com/a/status/1", "text": "must not run"}])
    result = service(tmp_path, runner).collect(CollectionRequest(channel="twitter", query="topic"))
    assert result.status == "failed" and result.items == []
    assert len(runner.calls) == 1


def test_empty_cli_payload_falls_back_and_does_not_become_a_citation(tmp_path):
    runner = Runner({"items": []}, [{"url": "https://www.reddit.com/r/a/comments/abc/topic/", "title": "Community evidence", "selftext": "actual result"}])
    svc = service(tmp_path, runner)
    svc.configure("reddit", ChannelConfig(backends=["opencli", "rdt"]))
    result = svc.collect(CollectionRequest(channel="reddit", query="topic"))
    assert result.items[0].content == "actual result"
    assert result.attempts[0].error_category == "empty_content"


def test_legacy_cookie_tools_are_never_default_fallbacks(tmp_path):
    runner = Runner(ChannelError("dependency_missing"), [])
    result = service(tmp_path, runner).collect(CollectionRequest(channel="reddit", query="research"))
    assert len(runner.calls) == 1
    assert result.attempts[-1].backend == "opencli"


def test_rdt_envelope_and_nested_comments_preserve_post_evidence(tmp_path):
    runner = Runner({"ok": True, "schema_version": "1", "data": {"post": {"title": "Topic", "selftext": "Question", "permalink": "/r/a/comments/abc/topic/"}, "comments": [{"body": "Useful reply", "replies": [{"body": "Nested reply"}]}]}})
    svc = service(tmp_path, runner)
    svc.configure("reddit", ChannelConfig(backends=["rdt"]))
    result = svc.collect(CollectionRequest(channel="reddit", operation="read", query="https://www.reddit.com/r/a/comments/abc/topic/"))
    assert "Nested reply" in result.items[0].content
    assert "Useful reply" in result.items[0].content


def test_reddit_link_post_cites_its_post_permalink(tmp_path):
    result = service(tmp_path, Runner([{ "url": "https://example.org/paper", "permalink": "/r/science/comments/abc/paper/", "title": "Paper discussion", "selftext": "Community evidence" }])).collect(CollectionRequest(channel="reddit", query="paper"))
    assert result.items[0].url == "https://www.reddit.com/r/science/comments/abc/paper/"


@pytest.mark.parametrize("channel,payload,url", [
    ("github", [{"url": "https://github.com/a/b", "name": "a/b", "description": "repo evidence"}], "https://github.com/a/b"),
    ("twitter", [{"id": "123", "text": "tweet evidence", "username": "alice"}], "https://x.com/alice/status/123"),
    ("reddit", [{"permalink": "/r/a/comments/abc/topic/", "title": "post", "selftext": "post evidence"}], "https://www.reddit.com/r/a/comments/abc/topic/"),
    ("xiaohongshu", {"feeds": [{"id": "abc", "xsecToken": "token", "noteCard": {"displayTitle": "笔记证据", "desc": "内容"}}]}, "https://www.xiaohongshu.com/explore/abc?xsec_token=token&xsec_source=pc_search"),
    ("facebook", [{"url": "https://www.facebook.com/a", "name": "Profile", "description": "profile evidence"}], "https://www.facebook.com/a"),
    ("instagram", [{"username": "nasa", "full_name": "NASA", "biography": "Space research"}], "https://www.instagram.com/nasa/"),
    ("linkedin", {"jobs": [{"url": "https://www.linkedin.com/jobs/view/123", "title": "Engineer", "description": "Job evidence"}]}, "https://www.linkedin.com/jobs/view/123"),
    ("boss", {"zpData": {"jobList": [{"encryptJobId": "abc", "jobName": "Engineer", "brandName": "Company", "jobDescription": "JD"}]}}, "https://www.zhipin.com/job_detail/abc.html"),
    ("xueqiu", [{"symbol": "NVDA", "name": "Nvidia", "current": 120}], "https://xueqiu.com/S/NVDA"),
    ("bilibili", [{"bvid": "BV1abc", "title": "视频", "description": "视频说明"}], "https://www.bilibili.com/video/BV1abc"),
    ("exa", {"results": [{"url": "https://example.org/research", "title": "Study", "text": "Study evidence"}]}, "https://example.org/research"),
])
def test_platform_search_normalizes_real_source_fields(tmp_path, channel, payload, url):
    result = service(tmp_path, Runner(payload)).collect(CollectionRequest(channel=channel, query="research"))
    assert result.status == "success"
    assert result.items[0].url == url
    assert result.items[0].content.strip()
    assert result.items[0].channel == channel


def test_read_rss_preserves_article_sources_and_filters_configured_feed(tmp_path):
    xml = '<rss><channel><item><title>Research</title><link>https://example.org/article</link><description>Useful evidence</description></item><item><title>Other</title><link>https://example.org/other</link><description>Unrelated</description></item></channel></rss>'
    svc = service(tmp_path, reader=Reader(xml))
    svc.configure("rss", ChannelConfig(feeds=["https://example.org/feed.xml"]))
    result = svc.collect(CollectionRequest(channel="rss", query="Research"))
    assert [i.url for i in result.items] == ["https://example.org/article"]


def test_rss_search_visits_later_configured_sources_within_shared_budget(tmp_path):
    xml = '<rss><channel><item><title>Research</title><link>https://example.org/article</link><description>Evidence</description></item></channel></rss>'
    svc = service(tmp_path, reader=Reader('<rss/>', '<rss/>', '<rss/>', xml))
    svc.configure("rss", ChannelConfig(feeds=[f"https://example.org/{i}.xml" for i in range(4)]))
    result = svc.collect(CollectionRequest(channel="rss", query="Research"))
    assert result.items[0].url == "https://example.org/article"


def test_youtube_read_includes_actual_subtitle_text_not_just_metadata(tmp_path):
    metadata = {"webpage_url": "https://www.youtube.com/watch?v=abc", "title": "Research video", "description": "Summary", "subtitles": {"en": [{"ext": "json3", "url": "https://www.youtube.com/api/timedtext?v=abc"}]}}
    caption = {"events": [{"segs": [{"utf8": "Actual transcript evidence"}]}]}
    result = service(tmp_path, Runner(metadata), Reader(caption)).collect(CollectionRequest(channel="youtube", operation="read", query=metadata["webpage_url"]))
    assert "Actual transcript evidence" in result.items[0].content


def test_video_without_captions_returns_metadata_with_explicit_transcript_gap(tmp_path):
    result = service(tmp_path, Runner({"webpage_url": "https://www.youtube.com/watch?v=abc", "title": "Video", "description": "Public metadata"}, ChannelError("dependency_missing"))).collect(CollectionRequest(channel="youtube", operation="read", query="https://www.youtube.com/watch?v=abc"))
    assert "字幕未获取" in result.items[0].content


def test_public_podcast_read_returns_page_evidence(tmp_path):
    svc = service(tmp_path, reader=Reader("Title: Podcast\nMarkdown Content:\nEpisode description"))
    svc.configure("xiaoyuzhou", ChannelConfig(backends=["jina"]))
    result = svc.collect(CollectionRequest(channel="xiaoyuzhou", operation="read", query="https://www.xiaoyuzhoufm.com/episode/abc"))
    assert "Episode description" in result.items[0].content


def test_v2ex_read_returns_topic_and_replies(tmp_path):
    result = service(tmp_path, reader=Reader([{"url": "https://www.v2ex.com/t/123", "title": "Research", "content": "Question"}], [{"content": "Useful reply"}])).collect(CollectionRequest(channel="v2ex", operation="read", query="https://www.v2ex.com/t/123"))
    assert "Useful reply" in result.items[0].content


def test_call_budget_prevents_second_http_read_and_preserves_failure(tmp_path):
    reader = Reader([{"url": "https://www.v2ex.com/t/123", "title": "Question", "content": "Topic"}], [{"content": "Reply"}])
    result = service(tmp_path, reader=reader).collect(CollectionRequest(channel="v2ex", operation="read", query="https://www.v2ex.com/t/123"), max_calls=1)
    assert len(reader.calls) == 1
    assert result.items == []
    assert result.attempts[-1].error_category == "budget_exceeded"


def test_total_deadline_is_shared_by_multi_request_backend(tmp_path, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("app.channels.service.time.monotonic", lambda: clock[0])
    class SlowReader(Reader):
        def get(self, url, **kwargs):
            value = super().get(url, **kwargs)
            clock[0] += 25
            return value
    reader = SlowReader([{"url": "https://www.v2ex.com/t/123", "title": "Topic", "content": "Question"}], [{"content": "Reply"}])
    result = service(tmp_path, reader=reader).collect(CollectionRequest(channel="v2ex", operation="read", query="https://www.v2ex.com/t/123"))
    assert len(reader.calls) == 1
    assert result.attempts[-1].error_category == "budget_exceeded"


def test_successful_article_discussing_login_and_rate_limits_is_not_an_error():
    output = CommandRunner().run([sys.executable, "-c", "print('Research: login required and rate_limit policies explained')"])
    assert "policies explained" in output


def test_structured_auth_failure_stops_fallback_even_with_exit_zero(tmp_path):
    runner = Runner({"success": False, "error": "auth_expired"}, [{"url": "https://x.com/a/status/1", "text": "must not execute"}])
    result = service(tmp_path, runner).collect(CollectionRequest(channel="twitter", query="research"))
    assert len(runner.calls) == 1
    assert result.attempts[-1].error_category == "auth_required"


def test_transcription_requires_explicit_provider_and_does_not_use_research_llm_key(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "research-credential")
    runner = Runner("Would send audio")
    svc = service(tmp_path, runner)
    svc.configure("xiaoyuzhou", ChannelConfig(backends=["transcribe"]))
    result = svc.collect(CollectionRequest(channel="xiaoyuzhou", operation="read", query="https://www.xiaoyuzhoufm.com/episode/abc"))
    assert runner.calls == []
    assert result.attempts[-1].error_category == "configuration_required"


@pytest.mark.parametrize("channel,url,payload,expected", [
    ("youtube", "https://www.youtube.com/watch?v=abc", [{"start": 0, "end": 1, "text": "First segment"}, {"start": 1, "end": 2, "text": "Second segment"}], "Second segment"),
    ("bilibili", "https://www.bilibili.com/video/BV1abc", [{"index": 1, "from": "0s", "to": "1s", "content": "第一句"}, {"index": 2, "from": "1s", "to": "2s", "content": "第二句"}], "第二句"),
    ("reddit", "https://www.reddit.com/r/a/comments/abc/topic/", [{"type": "POST", "author": "a", "text": "Question"}, {"type": "COMMENT", "author": "b", "text": "Useful reply"}], "Useful reply"),
    ("instagram", "https://www.instagram.com/nasa/", [{"index": 1, "caption": "Space mission evidence", "date": "2026-10-12", "likes": 12}], "Space mission evidence"),
])
def test_opencli_actual_read_shapes_preserve_all_source_content(tmp_path, channel, url, payload, expected):
    svc = service(tmp_path, Runner(payload))
    svc.configure(channel, ChannelConfig(backends=["opencli"]))
    result = svc.collect(CollectionRequest(channel=channel, operation="read", query=url))
    assert len(result.items) == 1
    assert expected in result.items[0].content
    assert result.items[0].url == url


def test_youtube_caption_gap_tries_opencli_before_returning_metadata(tmp_path):
    metadata = {"webpage_url": "https://www.youtube.com/watch?v=abc", "title": "Video", "description": "Metadata"}
    runner = Runner(metadata, [{"start": 0, "text": "Recovered transcript"}])
    result = service(tmp_path, runner).collect(CollectionRequest(channel="youtube", operation="read", query=metadata["webpage_url"]))
    assert result.items[0].backend == "opencli"
    assert result.items[0].content == "Recovered transcript"
    assert result.attempts[0].error_category == "no_transcript"


def test_metadata_only_result_is_partial_and_cannot_claim_transcript_success(tmp_path):
    runner = Runner({"webpage_url": "https://www.youtube.com/watch?v=abc", "title": "Video", "description": "Metadata"}, ChannelError("dependency_missing"))
    result = service(tmp_path, runner).collect(CollectionRequest(channel="youtube", operation="read", query="https://www.youtube.com/watch?v=abc"))
    assert result.status == "partial"
    assert "字幕未获取" in result.items[0].content


def test_twitter_without_explicit_credentials_does_not_read_browser_cookies(tmp_path, monkeypatch):
    monkeypatch.delenv("TWITTER_AUTH_TOKEN")
    monkeypatch.delenv("TWITTER_CT0")
    runner = Runner([])
    result = service(tmp_path, runner).collect(CollectionRequest(channel="twitter", query="research"))
    assert runner.calls == []
    assert result.attempts[-1].error_category == "auth_required"


def test_xhs_field_value_detail_preserves_body(tmp_path):
    svc = service(tmp_path, Runner([{"field": "title", "value": "研究笔记"}, {"field": "desc", "value": "真实正文"}]))
    svc.configure("xiaohongshu", ChannelConfig(backends=["opencli"]))
    result = svc.collect(CollectionRequest(channel="xiaohongshu", operation="read", query="https://www.xiaohongshu.com/explore/abc?xsec_token=token"))
    assert "真实正文" in result.items[0].content


def test_github_read_fallback_includes_actual_readme(tmp_path):
    import base64
    svc = service(tmp_path, Runner(ChannelError("dependency_missing")), Reader({"html_url": "https://github.com/a/b", "name": "Repo", "description": "Metadata"}, {"encoding": "base64", "content": base64.b64encode(b"# Actual README\nResearch architecture").decode()}))
    result = svc.collect(CollectionRequest(channel="github", operation="read", query="https://github.com/a/b"))
    assert "Research architecture" in result.items[0].content
    assert result.call_count == 3


@pytest.mark.parametrize("channel,payload,canonical", [
    ("github", {"url": "https://api.github.com/repos/a/b", "html_url": "https://github.com/a/b", "name": "Repository", "description": "Evidence"}, "https://github.com/a/b"),
    ("youtube", {"url": "https://cdn.example.org/video-stream", "webpage_url": "https://www.youtube.com/watch?v=abc", "title": "Video", "description": "Evidence"}, "https://www.youtube.com/watch?v=abc"),
])
def test_metadata_prefers_citable_web_page_over_api_or_media_stream(tmp_path, channel, payload, canonical):
    svc = service(tmp_path, Runner(payload))
    result = svc.collect(CollectionRequest(channel=channel, query="research"))
    assert result.items[0].url == canonical


def test_malformed_or_sourceless_output_never_becomes_evidence(tmp_path):
    svc = service(tmp_path, Runner({"success": True, "message": "logged in"}), Reader({"items": []}))
    result = svc.collect(CollectionRequest(channel="github", query="topic"))
    assert result.items == [] and result.status != "success"


def test_configuration_survives_new_service_without_cross_owner_history(tmp_path):
    svc = service(tmp_path, Runner([]), Reader({"items": []}))
    svc.configure("github", ChannelConfig(backends=["github-api"], enabled=False))
    result = svc.collect(CollectionRequest(channel="github", query="topic"))
    assert result.attempts[0].error_category == "disabled"
    fresh = service(tmp_path)
    assert next(c for c in fresh.catalog() if c["name"] == "github")["config"]["enabled"] is False
    other = service(tmp_path, owner=OWNER_B)
    assert next(c for c in other.catalog() if c["name"] == "github")["config"]["enabled"] is True
    assert other.history() == []


def test_concurrent_history_is_not_lost_and_is_bounded(tmp_path):
    def collect(_):
        svc = service(tmp_path)
        svc.configure("github", ChannelConfig(enabled=False))
        svc.collect(CollectionRequest(channel="github", query="topic"))
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(collect, range(20)))
    assert len(service(tmp_path).history()) == 20


def test_cross_process_history_updates_preserve_both_writers(tmp_path):
    import subprocess
    program = "from app.channels.store import ChannelStore; import sys; s=ChannelStore(sys.argv[1]); [s.record(sys.argv[2],[{'channel':'github','backend':sys.argv[3],'status':'success'}],'2026-10-12T00:00:00+00:00') for _ in range(20)]"
    processes = [subprocess.Popen([sys.executable, "-c", program, str(tmp_path), OWNER_A, name], stdout=subprocess.PIPE, stderr=subprocess.PIPE) for name in ("writer-a", "writer-b")]
    for process in processes:
        _, error = process.communicate(timeout=15)
        assert process.returncode == 0, error.decode(errors="replace")
    history = ChannelStore(tmp_path).read(OWNER_A)["history"]
    assert len(history) == 40
    assert {name: sum(a["backend"] == name for a in history) for name in ("writer-a", "writer-b")} == {"writer-a": 20, "writer-b": 20}


def test_rate_limit_cooldown_prevents_immediate_recollection(tmp_path):
    runner = Runner(ChannelError("rate_limited"), [{"url": "https://x.com/a/status/1", "text": "Must not execute"}])
    svc = service(tmp_path, runner)
    first = svc.collect(CollectionRequest(channel="twitter", query="research"))
    second = svc.collect(CollectionRequest(channel="twitter", query="research"))
    assert first.attempts[-1].error_category == "rate_limited"
    assert second.attempts[-1].backend == "policy"
    assert len(runner.calls) == 1


def test_unregistered_backend_and_owner_traversal_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        service(tmp_path).configure("github", ChannelConfig(backends=["shell"]))
    with pytest.raises(ValueError):
        ChannelStore(tmp_path).read("../another-user")


@pytest.mark.parametrize("query", ["--config=/secret", " ", "topic\x00secret"])
def test_option_injection_is_rejected(query):
    with pytest.raises(ValidationError):
        CollectionRequest(query=query)


def test_shell_metacharacters_are_only_search_data(tmp_path):
    runner = Runner([{"url": "https://github.com/a/b", "name": "Repo"}])
    value = 'topic; $(delete) & echo "hello"'
    service(tmp_path, runner).collect(CollectionRequest(channel="github", query=value))
    assert value in runner.calls[0]


@pytest.mark.parametrize("url", ["https://127.0.0.1/secret", "https://[::1]/secret", "https://169.254.169.254/", "https://a:b@example.org/", "file:///secret", "https://github.com.evil.local/"])
def test_private_or_credential_url_rejected_before_transport(tmp_path, url):
    reader = Reader("secret")
    result = service(tmp_path, reader=reader).collect(CollectionRequest(channel="web", operation="read", query=url))
    assert result.items == [] and result.attempts[0].error_category == "domain_blocked"
    assert reader.calls == []


def test_source_host_cannot_change_selected_platform(tmp_path):
    result = service(tmp_path, Runner([])).collect(CollectionRequest(channel="github", operation="read", query="https://github.com.evil.org/a/b"))
    assert result.attempts[0].error_category == "unsupported_input"


def test_output_budget_and_timeout_terminate_real_processes():
    runner = CommandRunner()
    with pytest.raises(ChannelError, match="output_limit"):
        runner.run([sys.executable, "-c", "print('x'*100000)"], max_bytes=1000)
    with pytest.raises(ChannelError, match="timeout"):
        runner.run([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.2)
    assert runner.run([sys.executable, "-c", "print('real content')"]).strip() == "real content"


def test_timeout_reclaims_descendant_even_after_its_parent_has_exited():
    import os
    import socket
    import threading
    import time
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    server.settimeout(5)
    child_pid = []
    def receive():
        with server.accept()[0] as connection:
            child_pid.append(int(connection.recv(64)))
    listener = threading.Thread(target=receive)
    listener.start()
    child = f"import os,socket,time; s=socket.create_connection(('127.0.0.1',{server.getsockname()[1]})); s.send(str(os.getpid()).encode()); s.close(); time.sleep(3)"
    parent = "import subprocess,sys; subprocess.Popen([sys.executable,'-c'," + repr(child) + "])"
    started = time.monotonic()
    try:
        with pytest.raises(ChannelError, match="timeout"):
            CommandRunner().run([sys.executable, "-c", parent], timeout=0.7)
        elapsed = time.monotonic() - started
        listener.join(1)
        assert child_pid, "descendant must actually execute before timeout"
        assert elapsed < 2, "waiting for orphaned descendants violates bounded cleanup"
        if os.name == "nt":
            import ctypes
            handle = ctypes.windll.kernel32.OpenProcess(0x100000, False, child_pid[0])
            if handle:
                try:
                    assert ctypes.windll.kernel32.WaitForSingleObject(handle, 500) == 0
                finally:
                    ctypes.windll.kernel32.CloseHandle(handle)
        else:
            with pytest.raises(ProcessLookupError):
                os.kill(child_pid[0], 0)
    finally:
        server.close()


def test_public_dns_name_resolving_private_is_rejected_before_connection(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **kw: [(2, 1, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(ChannelError, match="domain_blocked"):
        HttpReader().get("https://example.org/secret")


def test_routing_uses_exact_domains_and_explicit_prefixes():
    assert route_query("小红书: 研究反馈") == ("xiaohongshu", "search", "研究反馈")
    assert route_query("https://github.com.evil.org/a") == ("web", "read", "https://github.com.evil.org/a")


def test_catalog_and_history_are_passive_and_never_collect(tmp_path):
    runner, reader = Runner(), Reader()
    svc = service(tmp_path, runner, reader)
    assert len(svc.catalog()) == 16
    assert svc.history() == []
    assert not runner.calls and not reader.calls
