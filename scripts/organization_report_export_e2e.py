"""New actual research -> frozen summary -> report UI -> downloaded artifacts."""
import os
import argparse
import asyncio
import json
from pathlib import Path

import asyncpg
from playwright.async_api import async_playwright

ROOT = Path('.codex-homework/organization-report-export-e2e')
DB = os.environ["ADRS_E2E_DATABASE_URL"]
SOURCE = 'https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin'


async def main(existing=None):
    ROOT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as automation:
        browser = await automation.chromium.launch(channel='msedge', headless=True)
        page = await browser.new_page(viewport={'width': 1440, 'height': 1100}, accept_downloads=True)
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        try:
            await page.goto('http://127.0.0.1:5173')
            await page.get_by_label('用户名', exact=True).fill('organization_e2e')
            await page.get_by_label('密码', exact=True).fill(os.environ["ADRS_E2E_PASSWORD"])
            await page.get_by_role('button', name='登录', exact=True).click()
            await page.get_by_role('button', name='研究', exact=True).first.wait_for()
            session = existing
            if not session:
                response = await page.request.post('http://127.0.0.1:5173/api/v1/research', data={
                    'query': f'基于出版商页面 {SOURCE}，研究 DistServe 论文的发表日期、Peking University 署名、研究问题和方法。只分析这一项有界公开样本，保留原文依据；没有直接证据的资助、协议、评价指标和当前任职明确未知，不外推全集或部署。',
                    'max_revision': 1, 'output_length': 'short', 'organization_research': {
                        'scope': {'organization_types': ['university'], 'entities': [{
                            'entity_id': 'pku', 'name': 'Peking University', 'type': 'university', 'source_urls': [SOURCE]}],
                            'disciplines': ['computer science'], 'topic': 'DistServe',
                            'start_date': '2024-01-01', 'end_date': '2024-12-31'},
                        'weights': {'preset': 'custom', 'config_version': 'report-export-e2e-v1',
                            'weights': {'topic_relevance': 6, 'evidence_completeness': 4, 'recency': 0,
                                'research_alignment': 0, 'output_performance': 0, 'cooperation_complementarity': 0}}}})
                assert response.ok, await response.text()
                session = (await response.json())['session_id']
                (ROOT / 'session.txt').write_text(session)
                print('New actual research:', session, flush=True)
            for _ in range(300):
                response = await page.request.get('http://127.0.0.1:5173/api/v1/research/' + session)
                assert response.ok, await response.text()
                result = await response.json()
                if result['status'] == 'completed':
                    break
                assert result['status'] != 'failed', result
                await asyncio.sleep(2)
            else:
                raise AssertionError('Keep observing this same actual research: ' + session)
            (ROOT / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            summary = (result.get('organization_result') or {}).get('report_summary')
            assert summary is not None, 'The completed new report must carry its frozen export summary'
            assert summary['configuration']['scope'] == result['organization_research']['scope']
            assert summary['weights'] == result['organization_research']['effective_weights']
            assert summary['sample']['summary']['publication_count'] >= 1, 'A real attributed publication is required'
            assert summary['gaps'] and summary['sources']
            assert summary['evaluation']['applied_to_evidence'] is False
            assert SOURCE in [item['source_url'] for item in summary['sources']]
            assert abs(summary['weights']['effective_weights']['topic_relevance'] - .6) < 1e-8
            assert abs(summary['weights']['effective_weights']['evidence_completeness'] - .4) < 1e-8
            connection = await asyncpg.connect(DB)
            saved = await connection.fetchrow('SELECT final_report,review_status FROM research_sessions WHERE id=$1::uuid', session)
            await connection.close()
            assert saved['final_report'] == result['report']
            assert json.loads(saved['review_status'])['organization_result']['report_summary'] == summary
            await page.goto('http://127.0.0.1:5173/?session=' + session)
            region = page.get_by_role('region', name='报告口径与冻结配置')
            await region.get_by_role('button', name='展开研究口径').click()
            weights = region.get_by_role('table', name='报告有效权重')
            assert await weights.get_by_role('row').filter(has=page.get_by_role('rowheader', name='主题相关性', exact=True)).get_by_role('cell').inner_text() == '60.00%'
            assert await weights.get_by_role('row').filter(has=page.get_by_role('rowheader', name='证据完整度', exact=True)).get_by_role('cell').inner_text() == '40.00%'
            await region.get_by_role('link', name='Peking University', exact=True).first.wait_for()
            await region.get_by_role('heading', name='缺口与解释边界', exact=True).wait_for()
            await region.screenshot(path=str(ROOT / 'summary.png'))
            downloads = {}
            for kind, label in [('md', '下载 Markdown'), ('json', '下载研究数据'), ('html', '下载 HTML')]:
                async with page.expect_download() as waiting:
                    await page.get_by_role('button', name=label, exact=True).click()
                download = await waiting.value
                assert await download.failure() is None
                destination = ROOT / ('report.' + kind)
                await download.save_as(str(destination))
                downloads[kind] = destination
            data = json.loads(downloads['json'].read_text(encoding='utf-8-sig'))
            assert data['organization_result']['report_summary'] == summary
            assert data['organization_research'] == result['organization_research']
            assert data['report'] == result['report']
            assert downloads['md'].read_text(encoding='utf-8-sig') == result['report']
            offline = await browser.new_page(viewport={'width': 1200, 'height': 1000})
            await offline.context.set_offline(True)
            await offline.goto(downloads['html'].resolve().as_uri())
            offline_region = offline.get_by_role('region', name='报告口径与冻结配置')
            await offline_region.get_by_role('button', name='展开研究口径').click()
            offline_weights = offline_region.get_by_role('table', name='报告有效权重')
            assert await offline_weights.get_by_role('row').filter(has=offline.get_by_role('rowheader', name='主题相关性', exact=True)).get_by_role('cell').inner_text() == '60.00%'
            sources = offline_region.get_by_role('link')
            assert SOURCE in await sources.evaluate_all('(nodes) => nodes.map(node => node.href)')
            await offline_region.get_by_role('heading', name='缺口与解释边界', exact=True).wait_for()
            await offline.screenshot(path=str(ROOT / 'offline-report.png'), full_page=True)
            await offline.context.set_offline(False)
            await offline.close()
            await page.reload()
            await page.get_by_role('region', name='报告口径与冻结配置').wait_for()
            assert not errors, errors
            print('PASS actual new research -> persisted summary -> UI -> Markdown/JSON/offline HTML:', session, flush=True)
        except Exception:
            await page.screenshot(path=str(ROOT / 'failure.png'), full_page=True)
            raise
        finally:
            await browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--session')
    args = parser.parse_args()
    asyncio.run(main(args.session))
