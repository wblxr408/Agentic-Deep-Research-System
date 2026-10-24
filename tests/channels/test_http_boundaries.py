"""Transport behavior at redirect, output and credential boundaries."""
import io
import json
import os
import socket
import sys

import pytest

from app.channels.execution import CommandRunner, HttpReader
from app.channels.models import ChannelError


def test_redirect_to_private_address_never_creates_a_second_connection(monkeypatch):
    connections = []
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    class Redirect:
        status = 302
        def getheader(self, *args):
            return "https://127.0.0.1/secret"
    class Connection:
        def __init__(self, host, address, timeout):
            connections.append((host, address))
        def request(self, *args, **kwargs):
            pass
        def getresponse(self):
            return Redirect()
        def close(self):
            pass
    monkeypatch.setattr("app.channels.execution._PinnedHTTPS", Connection)
    with pytest.raises(ChannelError, match="domain_blocked"):
        HttpReader().get("https://example.org/article")
    assert connections == [("example.org", "93.184.216.34")]


def test_http_content_cannot_exceed_output_budget(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 443))])
    class Response(io.BytesIO):
        status = 200
    class Connection:
        sock = None
        def __init__(self, *args):
            pass
        def request(self, *args, **kwargs):
            pass
        def getresponse(self):
            return Response(b"content larger than the requested limit")
        def close(self):
            pass
    monkeypatch.setattr("app.channels.execution._PinnedHTTPS", Connection)
    with pytest.raises(ChannelError, match="output_limit"):
        HttpReader().get("https://example.org/article", max_bytes=10)


def test_tool_receives_only_its_explicit_platform_credentials(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "research-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "research-openai-secret")
    monkeypatch.setenv("GH_TOKEN", "github-secret")
    monkeypatch.setenv("TWITTER_AUTH_TOKEN", "twitter-secret")
    expression = "import os,json; print(json.dumps({k:os.getenv(k) for k in ['LLM_API_KEY','OPENAI_API_KEY','GH_TOKEN','TWITTER_AUTH_TOKEN']}))"
    received = json.loads(CommandRunner().run([sys.executable, "-c", expression], secrets=("GH_TOKEN",)))
    assert received == {"LLM_API_KEY": None, "OPENAI_API_KEY": None, "GH_TOKEN": "github-secret", "TWITTER_AUTH_TOKEN": None}


@pytest.mark.skipif(os.name != "nt", reason="Windows batch interpolation boundary")
def test_batch_shim_rejected_before_user_query_can_be_interpolated(monkeypatch):
    monkeypatch.setenv("CHANNELS_TOOL_PREFIXES", json.dumps({"opencli": ["tool.cmd"]}))
    with pytest.raises(ChannelError, match="native_launcher_required"):
        CommandRunner().run(["opencli", "github", "search", "$(malicious)"])
