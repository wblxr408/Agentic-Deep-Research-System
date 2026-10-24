"""Deliver a new public Tencent networking case through the actual application."""
import os
import argparse
import asyncio
import json
from pathlib import Path

import asyncpg
from playwright.async_api import async_playwright

ROOT = Path('.codex-homework/tencent-network-case-20261021')
SOURCE = 'https://www.usenix.org/conference/nsdi26/presentation/hu-jiayu'
DB = os.environ["ADRS_E2E_DATABASE_URL"]


async def main(existing):
    ROOT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as automation:
        browser = await automation.chromium.launch(channel='msedge', headless=True)
        page = await browser.new_page(viewport={'width':1440,'height':1100}, accept_downloads=True)
        try:
            await page.goto('http://127.0.0.1:5173')
            await page.get_by_label('用户名', exact=True).fill('organization_e2e')
            await page.get_by_label('密码', exact=True).fill(os.environ["ADRS_E2E_PASSWORD"])
            await page.get_by_role('button',name='登录',exact=True).click()
            await page.get_by_role('button',name='研究',exact=True).first.wait_for()
            session = existing
            if not session:
                request = {
                    'query': f'交付腾讯网络研究的一个有界、可分享案例：仅以 Harp 出版商页面 {SOURCE} 为种子，核实2026年腾讯在VPC网络故障检测与恢复方面的公开研究。识别论文题名、发表月份、Tencent署名及外部高校共著线索，解释摘要可支持的问题、软件路径监测与故障绕行机制。区分作者自述部署／生产结果与独立验证；无法取得全文时不补造实验条件和图表。仅一项公开成果，不代表腾讯2020—2026全集，不以数量推断投入，不把共著称为正式协议。BibTeX year=2026及month=may是发表时间来源，应保留月精度而非具体某日。没有直接依据的指标、资助、内部战略与未来方向保留缺口，最后给出待验证问题。',
                    'max_revision':1, 'output_length':'medium',
                    'organization_research': {'scope': {
                        'organization_types':['company'], 'entities':[{
                            'entity_id':'tencent','name':'Tencent','type':'company',
                            'aliases':['Tencent Cloud','腾讯','腾讯云'], 'source_urls':[SOURCE]}],
                        'disciplines':['computer science'], 'topic':'VPC network failure detection and recovery',
                        'start_date':'2026-01-01','end_date':'2026-10-21'},
                        'weights':{'preset':'research_development','config_version':'tencent-network-case-20261021-v1'}}}
                (ROOT/'request.json').write_text(json.dumps(request,ensure_ascii=False,indent=2),encoding='utf-8')
                response = await page.request.post('http://127.0.0.1:5173/api/v1/research', data=request)
                assert response.ok, await response.text()
                session = (await response.json())['session_id']
                (ROOT/'session.txt').write_text(session)
                print('Actual Tencent research created:',session,flush=True)
            for _ in range(360):
                response = await page.request.get('http://127.0.0.1:5173/api/v1/research/'+session)
                assert response.ok, await response.text()
                result = await response.json()
                if result['status']=='completed':break
                assert result['status']!='failed',result
                await asyncio.sleep(2)
            else:raise AssertionError('Continue observing the same actual Tencent job: '+session)
            (ROOT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            calls = await page.request.get('http://127.0.0.1:5173/api/v1/research/'+session+'/tool-calls')
            assert calls.ok, await calls.text()
            calls = await calls.json()
            (ROOT/'tool-calls.json').write_text(json.dumps(calls,ensure_ascii=False,indent=2),encoding='utf-8')
            assert calls, 'Actual public acquisition must have taken place'
            findings = result['organization_result']
            summary = findings['report_summary']
            assert summary['sample']['summary']['publication_count'] >= 1, findings['pending_records']
            assert all(entity['type']=='company' for entity in summary['sample']['entities'])
            assert [view['entity_id'] for view in summary['sample']['views']] == ['tencent']
            assert SOURCE in [source['source_url'] for source in summary['sources']]
            assert summary['gaps'] and not summary['evaluation']['applied_to_evidence']
            conn = await asyncpg.connect(DB)
            saved = await conn.fetchrow('SELECT final_report,review_status,total_tokens,total_cost_usd FROM research_sessions WHERE id=$1::uuid',session)
            await conn.close()
            assert saved['final_report']==result['report']
            assert json.loads(saved['review_status'])['organization_result']==findings
            assert saved['total_tokens']>0, 'A new model run must be evidenced'
            await page.goto('http://127.0.0.1:5173/?session='+session)
            await page.get_by_role('region',name='报告口径与冻结配置').wait_for()
            for suffix,label in [('json','下载研究数据'),('md','下载 Markdown'),('html','下载 HTML')]:
                async with page.expect_download() as waiting:
                    await page.get_by_role('button',name=label,exact=True).click()
                download = await waiting.value
                assert await download.failure() is None
                await download.save_as(str(ROOT/('tencent-report.'+suffix)))
            artifact=json.loads((ROOT/'tencent-report.json').read_text(encoding='utf-8'))
            assert artifact['organization_result']==findings and artifact['report']==saved['final_report']
            await page.screenshot(path=str(ROOT/'application.png'),full_page=True)
            metrics={'session_id':session,'total_tokens':saved['total_tokens'],'total_cost_usd':str(saved['total_cost_usd']),
                'tool_calls':len(calls),'report_chars':len(result['report']),'citations':len(result['citations']),
                'summary':summary['sample']['summary'],'gaps':summary['gaps']}
            (ROOT/'delivery.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf-8')
            print('PASS actual Tencent case, model/tools/PostgreSQL/downloaded report:',json.dumps(metrics,ensure_ascii=False),flush=True)
        except Exception:
            await page.screenshot(path=str(ROOT/'failure.png'),full_page=True)
            raise
        finally:await browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--session');args=parser.parse_args()
    asyncio.run(main(args.session))
