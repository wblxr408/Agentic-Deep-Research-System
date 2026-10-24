"""Only defects exposed by the current full-paper research: pause persistence and truncation."""
import os
import ast
import asyncio
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import asyncpg
import pytest

from app.agents.analyst import AnalystAgent
from app.llm_budget import TokenBudgetExceeded


def test_budget_pause_result_is_saved_without_completion_timestamp():
    # Execute the actual production persistence statement on PostgreSQL. Its
    # parameter inference cannot be represented by a connection mock.
    tree=ast.parse(Path('app/api/research.py').read_text(encoding='utf-8'))
    statement=next(node.value for node in ast.walk(tree) if isinstance(node,ast.Constant)
        and isinstance(node.value,str) and 'UPDATE research_sessions' in node.value
        and 'completed_at = CASE' in node.value)
    async def save():
        connection=await asyncpg.connect(os.environ["ADRS_E2E_DATABASE_URL"])
        try:
            async with connection.transaction():
                await connection.execute('''CREATE TEMP TABLE research_sessions (
                    id uuid PRIMARY KEY, status varchar(20), guardrail_decision jsonb,
                    guardrail_trace jsonb, evidence_status jsonb, review_status jsonb,
                    prompt_profile varchar(100), prompt_template text, enabled_tools jsonb,
                    final_report text, citations jsonb, agent_trace jsonb, total_tokens integer,
                    total_cost_usd double precision, updated_at timestamp, completed_at timestamp
                ) ON COMMIT DROP''')
                identifier=uuid4()
                await connection.execute('INSERT INTO research_sessions(id,status,completed_at) VALUES($1,$2,$3)',identifier,'running',datetime(2026,10,22))
                await connection.execute(statement,'paused','{}','[]','{}',json.dumps({'reason':'token_budget_exhausted'}),
                    'research','scope','[]','Retained partial report','[]','[]',28874,0.0,datetime(2026,10,22,11,30),identifier)
                row=await connection.fetchrow('SELECT status,final_report,total_tokens,completed_at FROM research_sessions WHERE id=$1',identifier)
                assert dict(row)=={'status':'paused','final_report':'Retained partial report','total_tokens':28874,'completed_at':None}
        finally:await connection.close()
    asyncio.run(save())


def test_truncated_analysis_stops_before_becoming_report_input():
    agent=AnalystAgent();agent._client=object()
    response=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"analysis_text":"cut off'),finish_reason='length')],
        usage=SimpleNamespace(prompt_tokens=100,completion_tokens=8192,total_tokens=8292))
    with patch('app.agents.analyst.create_fallback_llm_client',return_value=None), \
         patch('app.agents.analyst.call_chat_with_fallback',return_value=(response,'deepseek-chat',False)):
        with pytest.raises(TokenBudgetExceeded,match='model_output_limit'):
            agent.analyze('研究系统团队',[])
    assert agent.last_usage['total_tokens']==8292
    assert agent.last_partial_response=='{"analysis_text":"cut off'
