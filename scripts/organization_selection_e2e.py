"""Real standalone organization selections through UI, research and saved report."""
import os
import asyncio
import argparse
import json
from pathlib import Path

import asyncpg
from playwright.async_api import async_playwright

ROOT = Path('.codex-homework/organization-selection-e2e')
CASES = [
    ('university', '高校', 'Peking University', 'https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin', '2024-01-01', '2024-12-31',
     '只以 DistServe 出版商页面核实北京大学在该篇成果中的署名与研究主题，说明有来源样本与缺口。'),
    ('laboratory', '科研实验室', 'CSAIL', 'https://www.csail.mit.edu/research', '2020-01-01', '2026-10-20',
     '只研究 CSAIL 实验室官网公开的研究方向，用简短报告说明可核实的主题和证据缺口，不要求企业业务或合作名单。'),
]


async def journey(browser, case, resume=False):
    kind, label, name, source, start, end, query = case
    folder = ROOT / kind
    folder.mkdir(parents=True, exist_ok=True)
    page = await browser.new_page(viewport={'width':1440, 'height':1000})
    errors, submissions = [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: submissions.append(request.post_data_json)
            if request.url.endswith('/api/v1/research') and request.method == 'POST' else None)
    existing = (folder/'session.txt').read_text().strip() if resume else None
    await page.goto('http://127.0.0.1:5173' + (f'/?session={existing}' if existing else ''))
    await page.get_by_label('用户名', exact=True).fill('organization_e2e')
    await page.get_by_label('密码', exact=True).fill(os.environ["ADRS_E2E_PASSWORD"])
    await page.get_by_role('button', name='登录', exact=True).click()
    await page.get_by_role('button', name='研究', exact=True).first.wait_for()
    if existing:
        submitted = json.loads((folder/'request.json').read_text(encoding='utf-8'))
        await finish(page, case, existing, submitted, errors)
        return
    await page.get_by_role('button', name='研究', exact=True).first.click()
    await page.get_by_label('组织研究模式', exact=True).check()
    await page.get_by_placeholder('例如：分析 2025 年中国新能源汽车市场格局').fill(query)
    await page.get_by_role('button', name='短文', exact=True).click()
    channel_boxes = page.get_by_role('region', name='联网渠道').get_by_role('checkbox')
    await channel_boxes.first.wait_for()
    channel_before = [await box.is_checked() for box in await channel_boxes.all()]
    for item in ['高校', '科研实验室', '企业']:
        await page.get_by_label(item, exact=True).uncheck()
    await page.get_by_role('button', name='开始研究', exact=True).click()
    await page.get_by_role('alert').get_by_text('请至少选择一种研究对象类型。', exact=True).wait_for()
    assert not submissions, submissions
    await page.get_by_label(label, exact=True).check()
    await page.get_by_role('button', name='添加研究对象', exact=True).click()
    await page.get_by_label('对象 1 名称', exact=True).fill(name)
    other_type = 'company' if kind == 'university' else 'university'
    await page.get_by_label('对象 1 类型', exact=True).select_option(other_type)
    await page.get_by_role('button', name='开始研究', exact=True).click()
    await page.get_by_role('alert').get_by_text('对象 1 的类型不在当前选择范围内。', exact=True).wait_for()
    assert not submissions, submissions
    await page.get_by_label('对象 1 类型', exact=True).select_option(kind)
    await page.get_by_label('对象 1 来源', exact=True).fill(source)
    await page.get_by_label('学科（逗号分隔）').fill('computer_science')
    await page.get_by_label('研究开始日期').fill('2025-01-01')
    await page.get_by_label('研究截止日期').fill('2024-01-01')
    await page.get_by_role('button', name='开始研究', exact=True).click()
    await page.get_by_role('alert').get_by_text('请填写有效的研究起止日期。', exact=True).wait_for()
    assert not submissions, submissions
    await page.get_by_label('研究开始日期').fill(start)
    await page.get_by_label('研究截止日期').fill(end)
    assert channel_before == [await box.is_checked() for box in await channel_boxes.all()]
    await page.screenshot(path=str(folder/'selection.png'), full_page=True)
    async with page.expect_response(lambda r:r.url.endswith('/api/v1/research') and r.request.method == 'POST') as created:
        await page.get_by_role('button', name='开始研究', exact=True).click()
    response = await created.value
    assert response.ok, await response.text()
    session = (await response.json())['session_id']
    (folder/'session.txt').write_text(session)
    assert len(submissions) == 1, submissions
    (folder/'request.json').write_text(json.dumps(submissions[0],ensure_ascii=False,indent=2),encoding='utf-8')
    await finish(page, case, session, submissions[0], errors)


async def finish(page, case, session, submitted, errors):
    kind, label, name, source, start, end, query = case
    folder = ROOT / kind
    request_scope = submitted['organization_research']['scope']
    assert request_scope['organization_types'] == [kind], request_scope
    assert len(request_scope['entities']) == 1 and request_scope['entities'][0]['name'] == name, request_scope
    assert request_scope['start_date'] == start and request_scope['end_date'] == end, request_scope
    for _ in range(300):
        response = await page.request.get(f'http://127.0.0.1:5173/api/v1/research/{session}')
        assert response.ok, await response.text()
        result = await response.json()
        if result['status'] == 'completed':
            break
        assert result['status'] != 'failed', result
        await asyncio.sleep(2)
    else:
        raise AssertionError(f'Preserve same running research {session}')
    actual_scope = result['organization_research']['scope']
    assert all(actual_scope[key] == value for key,value in request_scope.items() if key != 'entities'), actual_scope
    assert len(actual_scope['entities']) == len(request_scope['entities']), actual_scope
    for actual, requested in zip(actual_scope['entities'], request_scope['entities']):
        assert all(actual[key] == value for key,value in requested.items()), actual_scope
    assert result['report'] and result['citations'], result
    scope_region = page.get_by_role('region', name='本次组织研究范围')
    await scope_region.get_by_text(name + ' · computer_science', exact=True).wait_for()
    heading = next(line.lstrip('#').strip() for line in result['report'].splitlines() if line.startswith('#'))
    await page.get_by_role('heading', name=heading, exact=True).first.wait_for(timeout=20000)
    await page.screenshot(path=str(folder/'report.png'), full_page=True)
    connection = await asyncpg.connect(os.environ["ADRS_E2E_DATABASE_URL"])
    saved = json.loads(await connection.fetchval('SELECT request_payload FROM research_sessions WHERE id=$1::uuid',session))
    assert saved['organization_research']['scope'] == actual_scope, saved
    assert saved['channels'] == submitted['channels'], saved
    await connection.close()
    assert not errors, errors
    (folder/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (folder/'report.md').write_text(result['report'],encoding='utf-8')
    print(f'PASS actual {kind} selection -> input rejections -> saved scope -> report: {session}', flush=True)
    await page.close()


async def main(resume=False):
    async with async_playwright() as automation:
        browser = await automation.chromium.launch(channel='msedge',headless=True)
        try:
            await asyncio.gather(*(journey(browser,case,resume) for case in CASES))
        finally:
            await browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume', action='store_true', help='Observe the recorded sessions without new research')
    asyncio.run(main(parser.parse_args().resume))
