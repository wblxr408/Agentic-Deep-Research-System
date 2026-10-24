"""Real independent/mixed/materials cases -> UI reweighting on saved evidence."""
import os
import argparse
import asyncio
import json
from pathlib import Path

import asyncpg
from playwright.async_api import async_playwright

ROOT = Path('.codex-homework/organization-cross-domain-e2e')
SOURCE = 'https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0351439'
DB = os.environ["ADRS_E2E_DATABASE_URL"]
LABELS = ['主题相关性', '研究路线契合', '成果表现', '证据完整度', '时效性', '合作互补性']


async def prepare_materials(page, existing):
    if not existing:
        request = {'query': f'研究 King Faisal University 的一项材料科学公开成果：{SOURCE}。仅以这项钙钛矿太阳能电池期刊论文为有界样本，核实完整题名、作者 Shrouq H. Aleithan 的发表署名、发表日期及期刊类型。学科为 materials science，不能套计算机会议 CCF 等级。优先读这一出版商原文，日期 Published July 10, 2026 不等于接受日期。页面有 Correction：记录更正线索，未核清时保留缺口，不将更正通知或参考文献另计为独立研究。只交付来源可支持的研究问题和方法概览，不摘用未经核清的效率数值，不宣称掌握该校成果全集、独立复现或正式合作关系。',
            'max_revision': 1, 'output_length': 'short', 'organization_research': {
                'scope': {'organization_types': ['university'], 'entities': [{
                    'entity_id': 'kfu', 'name': 'King Faisal University', 'type': 'university', 'source_urls': [SOURCE]}],
                    'disciplines': ['materials science'], 'topic': 'perovskite',
                    'start_date': '2026-01-01', 'end_date': '2026-10-21'},
                'weights': {'preset': 'custom', 'config_version': 'materials-case-20261021-v1',
                    'weights': {'topic_relevance': 6, 'evidence_completeness': 4}}}}
        (ROOT / 'materials-request.json').write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding='utf-8')
        response = await page.request.post('http://127.0.0.1:5173/api/v1/research', data=request)
        assert response.ok, await response.text()
        existing = (await response.json())['session_id']
        (ROOT / 'materials-session.txt').write_text(existing)
        print('Actual new materials research:', existing, flush=True)
    for _ in range(360):
        response = await page.request.get('http://127.0.0.1:5173/api/v1/research/' + existing)
        assert response.ok, await response.text()
        result = await response.json()
        if result['status'] == 'completed':
            break
        assert result['status'] != 'failed', result
        await asyncio.sleep(2)
    else:
        raise AssertionError('Observe this same actual materials research: ' + existing)
    (ROOT / 'materials-source-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    findings = result['organization_result']
    assert findings['scope_result']['summary']['publication_count'] == 1, findings['pending_records']
    assert findings['scope_result']['views'][0]['entity_id'] == 'kfu'
    outputs = findings['scope_result']['outputs']
    assert all(findings['publication_metadata'][item['output_id']]['output_type'] == 'journal_article' for item in outputs)
    assert all(item['published_until'] <= '2026-10-21' for item in outputs)
    assert SOURCE in [url for item in outputs for url in item['source_urls']]
    return existing


async def case(page, connection, name, session, expected_ids, discipline, output_type):
    folder = ROOT / name
    folder.mkdir(exist_ok=True)
    async def saved_state():
        row = await connection.fetchrow('SELECT final_report,review_status,total_tokens FROM research_sessions WHERE id=$1::uuid', session)
        return {'report': row['final_report'], 'review': row['review_status'], 'tokens': row['total_tokens'],
                'calls': await connection.fetchval('SELECT count(*) FROM tool_call_audit WHERE session_id=$1::uuid', session)}
    original = await saved_state()
    response = await page.request.get('http://127.0.0.1:5173/api/v1/research/' + session)
    assert response.ok, await response.text()
    source = await response.json()
    assert source['status'] == 'completed' and source['report']
    scoped = source['organization_result']['scope_result']
    assert {view['entity_id'] for view in scoped['views']} == expected_ids
    assert all(view['publication_count'] == 1 for view in scoped['views'])
    assert scoped['summary']['publication_count'] == 1, 'Shared work must remain a union, not summed object counts'
    await page.goto('http://127.0.0.1:5173/?session=' + session)
    panel = page.get_by_role('region', name='固定证据重排')
    async with page.expect_response(lambda r: r.url.endswith('/matching/snapshot') and r.request.method == 'POST') as waiting:
        await panel.get_by_role('button', name='准备本次证据快照', exact=True).click()
    response = await waiting.value
    assert response.ok, await response.text()
    snapshot = await response.json()
    assert {item['entity']['entity_id'] for item in snapshot['snapshot']['candidates']} == expected_ids
    assert all(group['discipline'] == discipline and group['output_type'] == output_type for group in snapshot['snapshot']['groups'])
    editor = panel.get_by_role('region', name='研究偏好与评价')
    for label, value in zip(LABELS, ['6', '0', '0', '4', '0', '0']):
        await editor.get_by_label(label + ' 权重', exact=True).fill(value)
    await editor.get_by_label('主题相关性 生效权重', exact=True).get_by_text('60.00%', exact=True).wait_for()
    async def reweight():
        async with page.expect_response(lambda r: r.url.endswith('/matching/preview') and r.request.method == 'POST') as waiting:
            await panel.get_by_role('button', name='重排当前证据', exact=True).click()
        response = await waiting.value
        assert response.ok, await response.text()
        return await response.json()
    before = await reweight()
    rows_before = before['groups'][0]['complete'] + before['groups'][0]['pending_evidence']
    assert {row['entity_id'] for row in rows_before} == expected_ids
    assert all(abs(row['coverage'] - .6) < 1e-8 and row['score'] is None for row in rows_before)
    assert all(abs((row['upper_bound'] - row['lower_bound']) - 40) < 1e-6 for row in rows_before)
    await editor.get_by_label('主题相关性 权重', exact=True).fill('10')
    await editor.get_by_label('证据完整度 权重', exact=True).fill('0')
    await editor.get_by_label('主题相关性 生效权重', exact=True).get_by_text('100.00%', exact=True).wait_for()
    after = await reweight()
    rows_after = after['groups'][0]['complete'] + after['groups'][0]['pending_evidence']
    assert before['snapshot_id'] == after['snapshot_id'] == snapshot['snapshot_id']
    assert before['configuration']['config_version'] != after['configuration']['config_version']
    assert all(row['coverage'] == 1 and row['score'] is not None and row['lower_bound'] == row['upper_bound'] for row in rows_after)
    assert all(row['family_count'] == 1 for row in rows_after)
    if len(expected_ids) > 1:
        assert len({row['score'] for row in rows_after}) == 1, 'Shared source/title yields equal lexical features, not an invented institutional ranking'
        assert not after['groups'][0]['definitely_better']
    for row in rows_after:
        await panel.get_by_label(row['name'] + ' 有效权重覆盖率', exact=True).get_by_text('100.00%', exact=True).wait_for()
    await editor.get_by_label('评价成果类型', exact=True).select_option(output_type)
    context_response = await page.request.post('http://127.0.0.1:5173/api/v1/research/evaluation/applicability', data={
        'disciplines': [discipline], 'output_type': output_type})
    assert context_response.ok, await context_response.text()
    context = await context_response.json()
    by_scheme = {item['scheme_id']: item for item in context['items']}
    if discipline == 'materials science':
        assert not by_scheme['ccf']['applicable'] and not by_scheme['icore']['applicable']
        assert by_scheme['jcr_jif']['applicable']
        await editor.get_by_role('article', name='CCF 评价状态').get_by_text('不适用', exact=True).wait_for()
        await editor.get_by_role('article', name='JCR JIF 评价状态').get_by_text('需授权导入', exact=True).wait_for()
    else:
        assert by_scheme['ccf']['applicable']
    assert await saved_state() == original, 'Changing preferences must not recollect or rewrite the original research'
    for filename, value in [('source.json', source), ('snapshot.json', snapshot), ('before.json', before), ('after.json', after), ('applicability.json', context)]:
        (folder / filename).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    await page.screenshot(path=str(folder / 'reweighted.png'), full_page=True)
    print('PASS', name, session, [(row['entity_id'], row['score'], row['coverage']) for row in rows_after], flush=True)


async def main(materials):
    ROOT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as automation:
        browser = await automation.chromium.launch(channel='msedge', headless=True)
        page = await browser.new_page(viewport={'width': 1440, 'height': 1100})
        try:
            await page.goto('http://127.0.0.1:5173')
            await page.get_by_label('用户名', exact=True).fill('organization_e2e')
            await page.get_by_label('密码', exact=True).fill(os.environ["ADRS_E2E_PASSWORD"])
            await page.get_by_role('button', name='登录', exact=True).click()
            await page.get_by_role('button', name='研究', exact=True).first.wait_for()
            materials = await prepare_materials(page, materials)
            connection = await asyncpg.connect(DB)
            try:
                await case(page, connection, 'independent-university', '2c8d4301-4cba-4adc-b692-c4da7e6add04', {'pku'}, 'computer science', 'conference_paper')
                await case(page, connection, 'mixed-organizations', '6533d261-19b7-47bc-9031-5c9237c1bf36', {'pku', 'ucsd', 'stepfun'}, 'computer science', 'conference_paper')
                await case(page, connection, 'materials-science', materials, {'kfu'}, 'materials science', 'journal_article')
            finally:
                await connection.close()
        except Exception:
            await page.screenshot(path=str(ROOT / 'failure.png'), full_page=True)
            raise
        finally:
            await browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--materials-session'); args = parser.parse_args()
    asyncio.run(main(args.materials_session))
