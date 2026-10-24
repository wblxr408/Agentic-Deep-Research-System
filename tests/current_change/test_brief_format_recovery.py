"""Invalid optional question count can be repaired once without repeating collection."""
import json
import threading
import time
from types import SimpleNamespace as NS

import pytest
from pydantic import ValidationError


@pytest.mark.parametrize("repair_succeeds", [True, False])
def test_bounded_sdk_format_recovery_preserves_fact_and_records_failure(monkeypatch, repair_succeeds):
    import openminion
    from openminion.api.agent import AgentOutputValidationError
    from app import openminion_research as research

    data = {"findings": [{"organization": "Example Lab", "work": "Trial", "facet": "result",
             "statement": "The trial reached 73 km only in the laboratory.", "citation_ids": [1]}],
            "questions": [f"Could condition {i} change the result?" for i in range(7)]}
    try:
        research._ResearchBrief.model_validate(data)
    except ValidationError as exc:
        invalid = AgentOutputValidationError("Too many questions", raw_text=json.dumps(data), validation_error=exc)
    calls = []
    class Agent:
        def __init__(self, **kwargs):
            assert kwargs["tools"] == []
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def run(self, message, **kwargs):
            calls.append(message)
            if len(calls) == 1 or not repair_succeeds:
                raise invalid
            valid = {**data, "questions": data["questions"][:4]}
            return NS(output=research._ResearchBrief.model_validate(valid), run_id="repaired", stats={})
    monkeypatch.setattr(openminion, "Agent", Agent)
    record = {}
    if repair_succeeds:
        output = research._run_brief_synthesis(None, {"sources": []}, instructions=research.BRIEF_INSTRUCTIONS,
            deadline=time.monotonic()+60, cancel=threading.Event(), record=record)
        assert output.output.findings[0].statement == data["findings"][0]["statement"]
        assert len(output.output.questions) == 4
    else:
        with pytest.raises(AgentOutputValidationError):
            research._run_brief_synthesis(None, {"sources": []}, instructions=research.BRIEF_INSTRUCTIONS,
                deadline=time.monotonic()+60, cancel=threading.Event(), record=record)
    assert len(calls) == 2
    assert json.loads(record["format_recoveries"][0]["invalid_output"])["questions"] == data["questions"]
