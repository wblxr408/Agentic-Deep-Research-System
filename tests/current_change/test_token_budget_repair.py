"""Only the current token-budget defect: provider calls, native usage and final state."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.agents.report import ReportAgent
from app.graph.compiler import _apply_llm_usage_to_state


class Provider:
    def __init__(self):
        self.calls = []
        self.chat = SimpleNamespace(completions=self)

    def with_options(self, **options):
        return self

    def create(self, **request):
        self.calls.append(request)
        if request.get('stream'):
            return iter([
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content='# Study\n\nA bounded result.'))], usage=None),
                SimpleNamespace(choices=[],usage=SimpleNamespace(prompt_tokens=1500,completion_tokens=64,total_tokens=1564)),
            ])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"verdicts":[]}'))],
            usage=SimpleNamespace(prompt_tokens=100,completion_tokens=10,total_tokens=110))


def test_report_rejects_input_that_cannot_fit_before_contacting_provider():
    provider = Provider()
    agent = ReportAgent()
    agent._client = provider
    with patch('app.agents.report.create_fallback_llm_client', return_value=None):
        with pytest.raises(RuntimeError):
            agent.generate_stream('研究' * 3000, 'evidence summary', [], None,
                verification_token_budget=1000, verification_timeout_seconds=60)
    assert provider.calls == []


def test_report_uses_native_stream_usage_instead_of_counting_visible_text():
    agent = ReportAgent()
    agent._client = Provider()
    with patch('app.agents.report.create_fallback_llm_client', return_value=None):
        agent.generate_stream('study', 'analysis', [], None,
            verification_token_budget=30000, verification_timeout_seconds=60)
    assert agent.last_usage['total_tokens'] == 1564


def test_final_usage_refreshes_root_stop_and_warning():
    _, budget = _apply_llm_usage_to_state({'session':{},'budget_state':{
        'max_total_tokens':60000,'used_total_tokens':59000,'hard_stop_reason':None,'warning':False}},
        'report',{'total_tokens':1500,'cost_usd':0,'estimated':False})
    assert budget['used_total_tokens'] == 60500
    assert budget['hard_stop_reason'] == 'token_limit'


def test_tool_and_model_tokens_both_consume_the_root_allowance():
    from app.graph.compiler import _build_budget_state
    budget = _build_budget_state({'budget_state':{'used_total_tokens':1000,
        'llm_usage':[{'agent':'planner','total_tokens':1000}]},
        'tool_histories':[{'tool_calls':[{'tokens_used':500}]}]})
    assert budget['used_total_tokens'] == 1500


def test_unknown_primary_failure_cannot_spend_again_through_fallback():
    from app.llm_budget import BudgetedClient, ModelTokenBudget
    from app.llm_client import call_chat_with_fallback
    primary, fallback = Provider(),Provider()
    def timeout(**request):
        primary.calls.append(request)
        raise TimeoutError('response lost after dispatch')
    primary.create = timeout
    primary.chat.completions = primary
    meter = ModelTokenBudget(1200)
    with pytest.raises(RuntimeError):
        call_chat_with_fallback(BudgetedClient(primary,meter,'research'),'test-model',
            (fallback,'test-model'),messages=[{'role':'user','content':'hello'}],max_tokens=800)
    assert len(primary.calls) == 1
    assert not fallback.calls
    assert meter.spent > 0


def test_final_audit_gets_a_real_judgement_call_after_generation():
    from app.graph.state import Evidence
    provider = Provider()
    quote = 'The cache holds 64 entries.'
    def create(**request):
        provider.calls.append(request)
        if request.get('stream'):
            return iter([SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(
                content='# Cache\n\nThe cache holds 64 entries. [citation:1]'))],usage=None),
                SimpleNamespace(choices=[],usage=SimpleNamespace(prompt_tokens=1500,completion_tokens=64,total_tokens=1564))])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=
            '{"verdicts":[{"claim_id":"claim:1","status":"supported","evidence_id":"ev-budget",'
            f'"excerpt_id":"ev-budget:0:{len(quote)}","reason":"Exact reported capacity"'+'}]}'))],
            usage=SimpleNamespace(prompt_tokens=100,completion_tokens=10,total_tokens=110))
    provider.create = create
    provider.chat.completions = provider
    agent = ReportAgent();agent._client = provider
    evidence = Evidence(evidence_id='ev-budget',source_type='web',content=quote,collected_by='browser',
        source_url='https://example.org/cache',source_title='Cache specification')
    with patch('app.agents.report.create_fallback_llm_client',return_value=None):
        agent.generate_stream('Cache capacity','The cache holds 64 entries. [citation:1]',[evidence],None,
            verification_token_budget=8000,verification_timeout_seconds=60)
    assert len(provider.calls) == 2
    assert agent.last_audit['checked_claims'] == 1
    assert agent.last_audit['supported_claims'] == 1
    assert not agent.last_audit['budget_incomplete']
    assert agent.last_usage['total_tokens'] == 1674


def test_early_stage_cannot_use_final_report_and_audit_share():
    from app.graph.compiler import _stage_model_budget
    from app.llm_budget import BudgetedClient
    provider = Provider()
    meter = _stage_model_budget({'budget_state':{'max_total_tokens':10000}},'analyst')
    response = BudgetedClient(provider,meter,'research').chat.completions.create(model='test-model',
        messages=[{'role':'user','content':'analyse'}],max_tokens=9000)
    assert response.usage.total_tokens == 110
    assert provider.calls[0]['max_tokens'] < 6000
    assert meter.spent == 110


@pytest.mark.asyncio
async def test_root_report_stays_paused_when_no_admissible_request_exists():
    from app.graph.compiler import report_node
    from app.graph.state import Evidence
    from app.governance.runtime import public_status_from_runtime
    provider = Provider();agent = ReportAgent();agent._client = provider
    evidence = Evidence(evidence_id='ev-budget',source_type='web',collected_by='browser',
        source_url='https://example.org/cache',content='The cache holds 64 entries.')
    state = {'user_query':'研究' * 3000,'analysis':'The cache holds 64 entries. [citation:1]',
        'collected_evidence':[evidence.model_dump()], 'session':{},'budget_state':{'max_total_tokens':1000}}
    with patch('app.agents.report.ReportAgent',return_value=agent):
        result = await report_node(state)
    assert result['status'] == 'paused'
    assert public_status_from_runtime(result['runtime_status']) == 'paused'
    assert result['budget_state']['used_total_tokens'] == 0
    assert not provider.calls


def test_audit_splits_a_batch_instead_of_skipping_every_claim():
    from app.claim_verification import audit_report
    from app.graph.state import Evidence
    quote = 'The cache holds 64 entries. The cache uses a FIFO policy. ' + 'Source appendix. ' * 30
    evidence = Evidence(evidence_id='ev-budget',source_type='web',content=quote,collected_by='browser',
        source_url='https://example.org/cache',source_title='Cache specification')
    provider = Provider()
    def judge(**request):
        import json
        provider.calls.append(request)
        payload = request['messages'][-1]['content'].split('>\n',1)[1].split('\n</untrusted_data>',1)[0]
        claims = json.loads(payload)
        verdicts = [{'claim_id':claim['claim_id'],'status':'supported','evidence_id':'ev-budget',
            'excerpt_id':claim['excerpts'][0]['excerpt_id'],'reason':'Matches source'} for claim in claims]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({'verdicts':verdicts})))],
            usage=SimpleNamespace(prompt_tokens=100,completion_tokens=10,total_tokens=110))
    provider.create = judge;provider.chat.completions = provider
    audit = audit_report('The cache holds 64 entries. [citation:1]\n\nThe cache uses a FIFO policy. [citation:1]',
        [evidence],client=provider,model='test-model',token_budget=4000)
    assert len(provider.calls) == 2
    assert audit['checked_claims'] == 2
    assert not audit['budget_incomplete']


def test_provider_overrun_is_not_allowed_to_consume_the_held_audit_share():
    from app.llm_budget import BudgetedClient, ModelTokenBudget
    provider = Provider()
    def overrun(**request):
        provider.calls.append(request)
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1600,completion_tokens=100,total_tokens=1700))
    provider.create = overrun;provider.chat.completions = provider
    meter = ModelTokenBudget(2000,audit_reserve=400)
    with pytest.raises(RuntimeError):
        BudgetedClient(provider,meter,'report').chat.completions.create(model='test-model',
            messages=[{'role':'user','content':'hello'}],max_tokens=800)
    assert meter.spent == 1700
    assert len(provider.calls) == 1
