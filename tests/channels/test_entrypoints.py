"""Consumer contracts: platform information reaches the existing search entrypoint."""
import json
import subprocess

from app.agents.search import SearchAgent


def test_github_query_returns_repository_evidence_instead_of_generic_search(monkeypatch):
    monkeypatch.setattr(SearchAgent, "_execute_duckduckgo_html_search", lambda *a: [])
    monkeypatch.setattr(SearchAgent, "_execute_duckduckgo_instant_answer", lambda *a: [])
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: _OutputProcess(json.dumps([
        {"name": "langgraph", "description": "Stateful research workflows",
         "url": "https://github.com/langchain-ai/langgraph"}
    ])))
    results = SearchAgent().execute_search("github: langgraph")
    assert [r.url for r in results] == ["https://github.com/langchain-ai/langgraph"]
    assert "Stateful research workflows" in results[0].snippet


class _OutputProcess:
    def __init__(self, output):
        import io
        self.stdout = io.BytesIO(output.encode())
        self.returncode = 0
    def poll(self):
        return 0
    def wait(self, timeout=None):
        return 0
    def kill(self):
        self.returncode = -9
