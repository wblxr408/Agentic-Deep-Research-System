"""A prose SDK verdict can be retried once, never silently accepted."""
import threading
import time
from types import SimpleNamespace as NS
import pytest


@pytest.mark.parametrize("succeeds", [True, False])
def test_audit_schema_failure_has_one_tools_free_retry(monkeypatch, succeeds):
    import openminion
    from openminion.api.agent import AgentOutputValidationError
    from app import openminion_research as research
    calls = []
    class Agent:
        def __init__(self, **kwargs): assert kwargs["tools"] == []
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def run(self, *args, **kwargs):
            calls.append(args[0])
            if len(calls) == 1 or not succeeds:
                raise AgentOutputValidationError("Expected JSON", raw_text="claim:1 supported by the supplied passage")
            return NS(output=research._AuditOutput(verdicts=[{"claim_id":"claim:1", "status":"supported",
                "excerpt_id":"source:1:0:67"}]), run_id="recovered-audit", stats={})
    monkeypatch.setattr(openminion, "Agent", Agent)
    record = {}
    arguments = dict(deadline=time.monotonic()+60, cancel=threading.Event(), record=record)
    messages=[{"content":"Return JSON verdicts, using only supplied passage identifiers."}, {"content":"Trial passages"}]
    if succeeds:
        answer=research._run_audit_judgement(None,messages,**arguments)
        assert answer.output.verdicts[0]["excerpt_id"] == "source:1:0:67"
        assert record["audit_format_recoveries"][0]["status"] == "recovered"
    else:
        with pytest.raises(AgentOutputValidationError): research._run_audit_judgement(None,messages,**arguments)
        assert record["audit_format_recoveries"][0]["status"] == "failed"
    assert len(calls) == 2
    assert record["audit_invalid_outputs"][0] == "claim:1 supported by the supplied passage"
