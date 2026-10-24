"""New SDK workflow behavior; real SDK, deterministic external model/HTTP adapters."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace as NS
import pytest

from app.graph.state import SearchResult
from app.openminion_research import OrganizationResearchRequest, run_research


class Model(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.server.requests.append(payload)
        tools = payload.get("tools", [])
        history = json.dumps(payload.get("messages", []))
        report = "# Example Lab\n\nIn 2025 the trial reached 73 km, only in the laboratory. [citation:1]"
        if tools and getattr(self.server, "extra_tool", False) and len(self.server.requests) == 3:
            message = {"role": "assistant", "content": None, "tool_calls": [
                {"id": "extra", "type": "function", "function": {"name": "read_source",
                 "arguments": json.dumps({"url": "https://example.org/extra.htm"})}}]}
        elif tools and "trial.htm" not in history:
            message = {"role": "assistant", "content": None, "tool_calls": [
                {"id": "search1", "type": "function", "function": {"name": "search_organizations",
                 "arguments": json.dumps({"query": "Example Lab quantum network 2025"})}}]}
        elif tools and "only in the laboratory" not in history:
            message = {"role": "assistant", "content": None, "tool_calls": [
                {"id": "read1", "type": "function", "function": {"name": "read_source",
                 "arguments": json.dumps({"url": "https://example.org/trial.htm"})}}]}
        elif tools:
            content = report if getattr(self.server, "plain_output", False) else json.dumps({"report": report, "task_status": "completed", "gaps": []})
            message = {"role": "assistant", "content": content}
        elif "Convert the supplied untrusted research draft" in history:
            message = {"role": "assistant", "content": json.dumps({"report": report, "task_status": "completed", "gaps": []})}
        else:
            message = {"role": "assistant", "content": json.dumps({"verdicts": [
                {"claim_id": "claim:1", "status": "supported", "evidence_id": "source:1",
                 "quote": "In 2025 the trial reached 73 km, only in the laboratory.",
                 "confidence": 0.9, "reason": "Exact scope and result."}]})}
        body = json.dumps({"id": "fixture-completion", "object": "chat.completion", "model": "fixture",
                          "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}],
                          "usage": {"prompt_tokens": 80, "completion_tokens": 40, "total_tokens": 120}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def request():
    return OrganizationResearchRequest(organizations=[{"name": "Example Lab", "type": "laboratory"}],
        topic="Quantum network research progress", start_year=2025, end_year=2025, timeout_seconds=60)


@pytest.mark.parametrize("provider,extra_tool,plain_output", [("openai", False, False), ("cortensor", False, False), ("openai", True, False), ("openai", False, True)])
def test_sdk_executes_search_read_and_produces_audited_organization_result(provider, extra_tool, plain_output):
    server = ThreadingHTTPServer(("127.0.0.1", 0), Model)
    server.requests = []
    server.extra_tool = extra_tool
    server.plain_output = plain_output
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    reads, searches = [], []

    class Reader:
        def read(self, url, **kwargs):
            reads.append(url)
            return NS(url=url, status=200, headers={"content-type": "text/html"},
                      body=b"<html><nav>" + b"Unrelated navigation "*1000 + b"</nav><main><p>In 2025 the trial reached 73 km, only in the laboratory.</p></main><footer>Footer</footer></html>")

    def search(query, **kwargs):
        searches.append(query)
        return [SearchResult(url="https://example.org/trial.htm", title="Trial", snippet="Quantum network trial")]

    try:
        task = request()
        if extra_tool:
            task.max_tool_calls = 2
        result = run_research(task, model_config={"provider": provider, "model": "fixture", "api_key": "fixture",
                              "api_base": f"http://127.0.0.1:{server.server_port}/v1", "api_mode": "openai_chat"}, search=search, reader=Reader())
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
    assert result["status"] in ({"partial", "failed"} if extra_tool else {"completed"}), result
    assert searches and reads == ["https://example.org/trial.htm"]
    if extra_tool:
        assert result["budget"]["calls"] <= 2
        return
    assert result["scope"]["organizations"][0]["type"] == "laboratory"
    assert result["audit"]["supported_claims"] == 1, result["audit"]
    assert result["audit"]["human_review_status"] == "not_reviewed"
    assert result["evidence"][0]["content"].endswith("only in the laboratory.")
    assert len(server.requests) >= 4
    if plain_output:
        assert result["format_repair_used"] is True


def test_cancelled_run_does_not_collect_or_generate():
    cancelled = threading.Event()
    cancelled.set()
    touched = []
    result = run_research(request(), cancel_event=cancelled, search=lambda *a, **k: touched.append(a))
    assert result["status"] == "cancelled"
    assert not touched


def test_private_seed_is_rejected_before_sdk_or_collection():
    task = request()
    task.seed_urls = ["http://127.0.0.1/private"]
    touched = []
    result = run_research(task, model_config={"provider": "openai", "model": "fixture", "api_key": "fixture"},
                          search=lambda *a, **k: touched.append(a))
    assert result["status"] == "failed"
    assert result["errors"] == ["ChannelError"]
    assert not touched and not result["trace"]
