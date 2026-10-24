"""Real browser -> authenticated API -> graph/tools/model -> PostgreSQL -> report.

Uses a separately launched local application and isolated acceptance database.
No request interception, dependency overrides, or generated research fixtures.
"""
import os
import asyncio
import json
import sys
from pathlib import Path

import asyncpg
from playwright.async_api import async_playwright, TimeoutError as BrowserTimeout

ARTIFACTS = Path('.codex-homework/organization-e2e')


async def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as automation:
        browser = await automation.chromium.launch(channel='msedge', headless=True)
        page = await browser.new_page(viewport={'width': 1440, 'height': 1000})
        browser_errors = []
        page.on('pageerror', lambda error: browser_errors.append(str(error)))
        existing_session = sys.argv[1] if len(sys.argv) > 1 else None
        await page.goto('http://127.0.0.1:5173' + (f'/?session={existing_session}' if existing_session else ''))
        username = page.get_by_label('用户名', exact=True)
        for attempt in range(4):
            try:
                await username.wait_for(timeout=10000)
                break
            except BrowserTimeout:
                if attempt == 3:
                    raise
                await page.reload()
        await username.fill('organization_e2e')
        await page.get_by_label('密码', exact=True).fill(os.environ["ADRS_E2E_PASSWORD"])
        if await page.get_by_label('确认密码', exact=True).count():
            await page.get_by_label('确认密码', exact=True).fill(os.environ["ADRS_E2E_PASSWORD"])
            await page.get_by_role('button', name='创建管理员并继续', exact=True).click()
        else:
            await page.get_by_role('button', name='登录', exact=True).click()
        await page.get_by_role('button', name='研究', exact=True).first.wait_for()
        if existing_session:
            session_id = existing_session
        else:
            session_id = await submit_research(page)
        await verify_result(page, session_id, browser_errors)
        await browser.close()


async def submit_research(page):
        await page.get_by_role('button', name='研究', exact=True).first.click()
        await page.get_by_label('组织研究模式', exact=True).check(timeout=10000)
        # Empty union is a user-visible rejected input in the same research journey.
        for label in ['高校', '科研实验室', '企业']:
            await page.get_by_label(label, exact=True).uncheck()
        await page.get_by_placeholder('例如：分析 2025 年中国新能源汽车市场格局').fill(
            '研究 MIT 与 CSAIL 在计算机网络领域的公开研究方向，依据已取得的官网资料分别说明范围、共同主题及证据缺口，不要求猜测论文全集。'
        )
        await page.get_by_role('button', name='开始研究', exact=True).click()
        await page.get_by_text('请至少选择一种研究对象类型。', exact=True).wait_for()
        for label in ['高校', '科研实验室']:
            await page.get_by_label(label, exact=True).check()
        await page.get_by_label('学科（逗号分隔）').fill('computer_science')
        await page.get_by_label('研究开始日期').fill('2020-01-01')
        await page.get_by_label('研究截止日期').fill('2026-10-20')
        for index, (name, kind, url) in enumerate([
            ('MIT', 'university', 'https://www.mit.edu/research/'),
            ('CSAIL', 'laboratory', 'https://www.csail.mit.edu/research/'),
        ]):
            await page.get_by_role('button', name='添加研究对象', exact=True).click()
            await page.get_by_label(f'对象 {index + 1} 名称', exact=True).fill(name)
            await page.get_by_label(f'对象 {index + 1} 类型', exact=True).select_option(kind)
            await page.get_by_label(f'对象 {index + 1} 来源', exact=True).fill(url)
        await page.screenshot(path=str(ARTIFACTS / 'scope-selection.png'), full_page=True)
        async with page.expect_response(lambda r: r.url.endswith('/api/v1/research') and r.request.method == 'POST', timeout=90000) as submission:
            await page.get_by_role('button', name='开始研究', exact=True).click()
        response = await submission.value
        assert response.ok, await response.text()
        session_id = (await response.json())['session_id']
        (ARTIFACTS / 'session-id.txt').write_text(session_id)
        return session_id


async def verify_result(page, session_id, browser_errors):
        for _ in range(240):
            result_response = await page.request.get(f'http://127.0.0.1:5173/api/v1/research/{session_id}')
            assert result_response.ok, await result_response.text()
            result = await result_response.json()
            if result['status'] not in ('pending', 'running'):
                break
            await asyncio.sleep(2)
        else:
            raise AssertionError(f'Research did not finish; preserve live session {session_id}')
        (ARTIFACTS / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        assert result['status'] == 'completed', result
        config = result['organization_research']
        assert config['scope']['organization_types'] == ['university', 'laboratory'], config
        assert [e['name'] for e in config['scope']['entities']] == ['MIT', 'CSAIL'], config
        assert config['effective_weights']['effective_weights']['topic_relevance'] == .35, config
        views = result['organization_result']['object_views']
        assert [v['entity_id'] for v in views] == [e['entity_id'] for e in config['scope']['entities']], views
        assert result['organization_result']['evidence_count'] > 0, result
        union = result['organization_result']['combined_evidence_ids']
        assert len(union) == len(set(union)), union
        assert result['citations'] and result['report'], result
        assert result['execution_plan']['nodes'], result
        connection = await asyncpg.connect(os.environ["ADRS_E2E_DATABASE_URL"])
        row = await connection.fetchrow('SELECT request_payload, review_status, final_report FROM research_sessions WHERE id=$1::uuid', session_id)
        original = json.loads(row['request_payload']) if isinstance(row['request_payload'], str) else row['request_payload']
        persisted = json.loads(row['review_status']) if isinstance(row['review_status'], str) else row['review_status']
        assert original['organization_research']['scope'] == config['scope'], original
        assert persisted['organization_research'] == config, persisted
        assert persisted['organization_result'] == result['organization_result'], persisted
        assert row['final_report'] == result['report'], row
        runtime = await connection.fetchval('SELECT state_snapshot_json FROM session_runtime_state WHERE session_id=$1::uuid', session_id)
        runtime = json.loads(runtime) if isinstance(runtime, str) else runtime
        assert runtime['organization_research'] == config, runtime
        assert runtime['organization_result']['scope'] == config['scope'], runtime
        browser_queries = [node['query'] for node in runtime['dag']['nodes'] if node['node_type'] == 'browser']
        assert all(entity['source_urls'][0] in browser_queries for entity in config['scope']['entities']), browser_queries
        successful_tools = await connection.fetchval("SELECT count(*) FROM tool_call_audit WHERE session_id=$1::uuid AND status IN ('success','completed')", session_id)
        assert successful_tools > 0, successful_tools
        try:
            await page.get_by_role('region', name='本次组织研究范围').wait_for(timeout=15000)
            heading = next(line.lstrip('#').strip() for line in result['report'].splitlines() if line.startswith('#'))
            await page.get_by_role('heading', name=heading, exact=True).first.wait_for(timeout=15000)
            await page.get_by_role('region', name='本次研究计划').get_by_text(config['scope']['entities'][0]['source_urls'][0], exact=True).first.wait_for(timeout=15000)
        except BrowserTimeout:
            await page.screenshot(path=str(ARTIFACTS / 'ui-failure.png'), full_page=True)
            (ARTIFACTS / 'ui-failure.json').write_text(json.dumps({'errors': browser_errors, 'body': await page.locator('body').inner_text()}, ensure_ascii=False), encoding='utf-8')
            raise
        await page.screenshot(path=str(ARTIFACTS / 'research-result.png'), full_page=True)
        await connection.close()
        await page.reload()
        await page.get_by_role('region', name='本次组织研究范围').wait_for(timeout=15000)
        await page.get_by_role('heading', name=heading, exact=True).first.wait_for(timeout=15000)
        await page.screenshot(path=str(ARTIFACTS / 'research-restored.png'), full_page=True)
        # Saved API report, live workflow and database all share the same contract.
        (ARTIFACTS / 'report.md').write_text(result['report'], encoding='utf-8')
        print(f'PASS real organization research: {session_id}; {len(union)} unique evidence items; {len(result["citations"])} citations')


if __name__ == '__main__':
    asyncio.run(main())
