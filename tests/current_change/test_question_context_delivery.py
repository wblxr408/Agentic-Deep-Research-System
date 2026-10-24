"""Current 4.5 consumer contract: late-paper methods, bounded calls, reading layers."""
import os
import json
import pytest
from types import SimpleNamespace
from unittest.mock import patch

from app.agents.analyst import AnalystAgent
from app.agents.report import ReportAgent
from app.graph.state import Evidence, AgentType
from app.llm_budget import ModelTokenBudget, request_token_bound
from app.organization_purpose import assemble_module_report, POLICY_VERSION
from app.research_delivery import build_delivery_view


def papers():
    sources=[]
    for number in range(6):
        intro=('Background material without experimental conditions. '*160)
        authors=f'AUTHORS-{number}: Peking University systems group. '
        method=f'METHOD-{number}: partition phases with independent placement. '
        evaluation=f'EXPERIMENT-{number}: 32 A100 GPUs; baseline vLLM; both TTFT and TPOT SLO at 90%. '
        text=intro+authors+method+('Implementation details. '*200)+evaluation+('Discussion. '*100)
        start=text.index(evaluation)
        sources.append(Evidence(evidence_id=f'paper-{number}',source_type='web',collected_by=AgentType.BROWSER,
            source_title=f'Paper {number}',source_url=f'https://example.org/paper-{number}',content=text,
            acquisition={'format':'pdf','coverage':'full_text','truncated':False,
                'total_pages':2,'retained_pages':2,'pages':[{'number':1,'start':0,'end':len(intro)},{'number':2,'start':len(intro),'end':len(text)}],
                'scientific_sections':[{'label':'Method','start':len(intro)+len(authors),'end':len(intro)+len(authors)+len(method)},
                    {'label':'Evaluation','start':start,'end':start+len(evaluation)}]}))
    return sources


def configuration():
    return {'analysis_policy_version':POLICY_VERSION,'purpose':'research_development',
        'modules':['deep_dive'],'scope':{'topic':'系统方法与实验条件比较'}}


def draft():
    return {'title':'系统方法与实验条件比较','summary':[{'text':'阶段拆分需要结合负载和延迟目标评估。','kind':'interpretation','citations':[1]}],
        'modules':[{'module_id':'deep_dive','paragraphs':[{'text':'论文以两种阶段的独立部署控制资源分配。','kind':'observation','citations':[1]}],
            'appendix':[{'text':'实验采用32块A100，对照vLLM，同时约束TTFT和TPOT，满足率为90%。','kind':'observation','citations':[1]}]}]}


def test_analyst_receives_method_and_conditions_from_each_retained_paper():
    agent=AnalystAgent(); sources=papers()
    context=agent._format_evidence(sources,organization_mode=True,deep_dive=True)
    assert set(agent.last_evidence_ids)=={source.evidence_id for source in sources}
    for index in range(6):
        assert f'METHOD-{index}:' in context and f'EXPERIMENT-{index}:' in context
        assert f'AUTHORS-{index}:' in context
    manifest=agent.last_context_manifest
    assert len(manifest['sources'])==6
    for record in manifest['sources']:
        source=next(item for item in sources if item.evidence_id==record['evidence_id'])
        for excerpt in record['excerpts']:
            assert excerpt['quote']==source.content[excerpt['start']:excerpt['end']]
        assert record['model_read_entire_document'] is False


def test_report_dispatch_fits_remaining_budget_with_audit_and_output_room():
    from app.graph import compiler
    agent=ReportAgent(); agent.request_budget=ModelTokenBudget(24000,audit_reserve=5000)
    sent=[]
    def create(**request):
        sent.append(request)
        return iter([SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=json.dumps(draft(),ensure_ascii=False)),finish_reason='stop')]),
            SimpleNamespace(choices=[],usage=SimpleNamespace(prompt_tokens=1500,completion_tokens=500,total_tokens=2000))])
    agent._client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    organization=configuration()
    organization.update(evidence_cutoff='2026-10-22T00:00:00',scope_rule_version='v1',
        effective_weights={'effective_weights':{f'long_preference_dimension_{i}':1/200 for i in range(200)}})
    state={'user_query':'比较方法和实验条件','organization_research':organization}
    question=getattr(compiler,'_synthesis_question',compiler._research_question)(state)
    analysis=('## 方法比较\n阶段拆分需要保留实验条件。[citation:1]\n\n'*800)+('\n## 负载\n真实负载决定资源配置。[citation:6]\n'*500)
    sources=papers()+[Evidence(content='Public academic contact: professor@example.edu',source_url='https://example.edu/faculty',
        collected_by=AgentType.BROWSER,acquisition={'format':'html','coverage':'metadata_or_page_text'})]
    with patch('app.agents.report.audit_report',return_value={'needs_review':False,'claims':[]}):
        content,_=agent.generate_stream(question,analysis,sources,None,output_length='long',organization_research=configuration())
    assert len(sent)==1
    assert '32 A100' in sent[0]['messages'][1]['content']
    assert 'professor@example.edu' in sent[0]['messages'][1]['content']
    assert request_token_bound(sent[0]['messages'])+sent[0]['max_tokens']<=19000
    assert agent.request_budget.available('audit')>=5000
    assert '32' in content
    assert agent.last_context_manifest['omitted_analysis_blocks']>0


def test_main_and_appendix_are_citable_separate_reading_layers():
    report,record=assemble_module_report(json.dumps(draft(),ensure_ascii=False),configuration(),6)
    assert record['issues']==[]
    assert record['reading_structure']['main_markdown'] and record['reading_structure']['appendix_markdown']
    assert '32' not in record['reading_structure']['main_markdown']
    assert '32' in record['reading_structure']['appendix_markdown']
    assert '[citation:1]' in record['reading_structure']['appendix_markdown']
    view=build_delivery_view(task_id='current',execution_id=None,query='比较',report=report,
        citations=[{'citation_id':'citation:1','source_url':'https://example.org/source'}],
        understanding={'delivery':{'template':'organization-development-v1'},'slots':{'modules':['deep_dive']}},organization_result=None,audit=None)
    assert view['pages'][0]['title']=='核心判断'
    assert '32' not in view['main_report_markdown']
    assert '32' in view['appendix_markdown']
    assert '[1]: <https://example.org/source>' in view['main_report_markdown']
    assert '[1]: <https://example.org/source>' in view['appendix_markdown']


def test_technical_comparison_chart_uses_located_fields_instead_of_counts():
    reading={'cards':[{'title':'DistServe','output_id':'distserve','fields':{
        'mechanism':{'text':'independent placement','status':'source_summary_requires_semantic_review','proofs':[{'evidence_id':'p1'}]},
        'conditions':{'text':'32 A100 GPUs','status':'source_summary_requires_semantic_review','proofs':[{'evidence_id':'p1'}]}}}]}
    view=build_delivery_view(task_id='current',execution_id=None,query='比较',report='## 成果深读\n来源方法',
        citations=[{'citation_id':'citation:1','source_url':'https://example.org/paper','locator':{'evidence_id':'p1'}}],
        understanding={'delivery':{'template':'technology-comparison-v1'},'slots':{'modules':['deep_dive']}},
        organization_result={'technical_reading':reading},audit=None)
    comparison=next(chart for chart in view['charts'] if chart['chart_id']=='technical_comparison')
    assert comparison['rows'][0]['citation_ids']==['citation:1']
    assert '32 A100 GPUs' in comparison['rows'][0]['values']
    assert view['pages'][0]['charts']==[{'chart_id':'technical_comparison','kind':'table'}]


def test_long_two_column_pdf_keeps_late_experiments_and_page_positions():
    import io
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    from app.document_pdf import parse_pdf
    writer=PdfWriter()
    for number in range(12):
        page=writer.add_blank_page(width=612,height=792)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):font})})
        stream=DecodedStreamObject()
        instructions=['BT /F1 8 Tf']
        for column,x in [('left',40),('right',320)]:
            for row in range(50):
                instructions.append(f'1 0 0 1 {x} {760-row*13} Tm (Page {number+1} {column} experiment condition {row}) Tj')
        instructions.append('ET')
        if number==0:
            # Nine distinct table candidates exceed the layout adapter's
            # eight-table allowance, while the complete text remains present.
            for table in range(9):
                x=40+(table%3)*180; y=100+(table//3)*85
                for delta in [0,20,40]:
                    instructions += [f'{x+delta} {y} m {x+delta} {y+40} l S', f'{x} {y+delta} m {x+40} {y+delta} l S']
        stream.set_data('\n'.join(instructions).encode())
        page[NameObject('/Contents')]=writer._add_object(stream)
    output=io.BytesIO();writer.write(output)
    result=parse_pdf(output.getvalue(),options={'timeout_seconds':25})
    assert result['coverage']=='full_text' and not result['truncated']
    assert result['retained_pages']==12
    assert result['structure_truncated'] is True
    late=next(p for p in result['pages'] if p['number']==12)
    assert 'Page 12 right experiment condition 49' in result['text'][late['start']:late['end']]
    assert result['text'].index('Page 12 left experiment condition 49') < result['text'].index('Page 12 right experiment condition 0')


def test_audit_checks_all_current_claims_without_repeating_locator_payloads():
    from app.claim_verification import audit_report
    from app.llm_budget import BudgetedClient
    sources=papers()[:3]; meter=ModelTokenBudget(22000); sent=[]
    def create(**request):
        payload=json.loads(request['messages'][1]['content'].split('\n',1)[1].split('\n</untrusted_data>',1)[0])
        sent.append(payload)
        if isinstance(payload,dict):
            by_id={item['excerpt_id']:item for item in payload['excerpts']}
            payload=[{**item,'excerpts':[by_id[key] for key in item['excerpt_ids']]} for item in payload['claims']]
        verdicts=[{'claim_id':claim['claim_id'],'status':'supported','evidence_id':claim['excerpts'][0]['evidence_id'],
            'excerpt_id':claim['excerpts'][0]['excerpt_id'],'reason':'Both latency conditions occur in the cited experiment.'} for claim in payload]
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({'verdicts':verdicts})))],
            usage=SimpleNamespace(prompt_tokens=1200,completion_tokens=300,total_tokens=1500))
    client=BudgetedClient(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))),meter,'audit')
    report='\n\n'.join(f'Experiment {i} compares vLLM with TTFT and TPOT SLO at 90% on 32 A100 GPUs. [citation:1] [citation:2] [citation:3]' for i in range(10))
    result=audit_report(report,sources,client=client,model='deepseek-chat',token_budget=22000)
    assert result['checked_claims']==10 and not result['budget_incomplete']
    assert meter.spent<=22000


def test_native_pdf_control_character_can_be_saved_and_original_recovered():
    import asyncio
    import base64
    import asyncpg
    from app.document_structure import DocumentBuilder
    builder=DocumentBuilder('pdf');builder.add('left\x00right','paragraph',{'page':1})
    document=builder.finish()
    async def save():
        connection=await asyncpg.connect(os.environ["ADRS_E2E_DATABASE_URL"])
        try:
            return json.loads(await connection.fetchval('SELECT $1::jsonb',json.dumps(document)))
        finally:await connection.close()
    saved=asyncio.run(save())
    assert saved['text']=='left\ufffdright'
    assert base64.b64decode(saved['blocks'][0]['raw_text_original_utf8_base64']).decode()=='left\x00right'


def test_invalid_report_structure_cannot_become_completed_empty_sections():
    agent=ReportAgent();agent.request_budget=ModelTokenBudget(40000,audit_reserve=5000)
    raw='{"title":"study","modules":[{"module_id":"deep_dive","paragraphs":"wrong shape"}]}'
    def create(**request):
        return iter([SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=raw),finish_reason='stop')]),
            SimpleNamespace(choices=[],usage=SimpleNamespace(prompt_tokens=1000,completion_tokens=200,total_tokens=1200))])
    agent._client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with patch('app.agents.report.audit_report') as audit:
        with pytest.raises(RuntimeError,match='report_contract_invalid'):
            agent.generate_stream('深读','方法分析',papers(),None,organization_research=configuration())
    audit.assert_not_called()
    assert agent.last_module_report['raw_model_response']==raw
    assert agent.last_module_report['validation_errors']
    view=build_delivery_view(task_id='current',execution_id=None,query='深读',report=agent.last_draft,citations=[],
        understanding=None,organization_result={'module_report':agent.last_module_report},audit=None)
    assert view['delivery_complete'] is False


def test_report_repairs_a_rejected_aggregate_once_within_same_meter():
    agent=ReportAgent();agent.request_budget=ModelTokenBudget(50000,audit_reserve=6000)
    statistics={'snapshot_id':'current','metric_registry':{'sample:publications':{'label':'采纳论文','display':'2','value':2,'unit':'publication'}},'conventions':[],'conflicts':[]}
    bad=draft();bad['modules'][0]['paragraphs'][0]['text']='样本共2篇论文。'
    good=draft();good['modules'][0]['paragraphs'][0]['text']='样本共{stat:sample:publications}篇论文。'
    sent=[]
    def create(**request):
        sent.append(request)
        value=bad if len(sent)==1 else {'repairs':[{'paragraph_id':'rejected:1','text':good['modules'][0]['paragraphs'][0]['text']}]}
        return iter([SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=json.dumps(value,ensure_ascii=False)),finish_reason='stop')]),
            SimpleNamespace(choices=[],usage=SimpleNamespace(prompt_tokens=1000,completion_tokens=200,total_tokens=1200))])
    agent._client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with patch('app.agents.report.audit_report',return_value={'needs_review':False,'claims':[]}):
        report,_=agent.generate_stream('研究比较','来源机制',papers(),None,organization_research=configuration(),organization_statistics=statistics)
    assert '2篇论文' in report
    assert agent.last_module_report['issues']==[] and len(agent.last_module_report['repair_history'])==1
    assert len(sent)==2 and agent.request_budget.spent==2400
