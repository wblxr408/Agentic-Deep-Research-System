"""Actual purpose/module UI -> model/tools -> scoped report and stored exports."""
import os
import argparse
import asyncio
import json
from pathlib import Path

import asyncpg
from playwright.async_api import async_playwright

ROOT = Path('.codex-homework/organization-purpose-e2e')
SOURCE = 'https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin'
DB = os.environ["ADRS_E2E_DATABASE_URL"]
QUERY = f'基于 {SOURCE} 研究 Peking University 的公开系统研究。只覆盖这篇 DistServe 发表样本；按选择的研究目的和模块交付。只有一个年度观测时明确不能确立多年趋势。署名或共著不等于正式协议、产品部署或可联系性；缺证保留未知，不把机构成果量当作内部研发投入。'


async def main(baseline, existing, purpose='research_development'):
    global ROOT
    if purpose != 'research_development':
        ROOT = ROOT / purpose
    expected_modules = {'research_development':['evolution'],
        'cooperation_discovery':['landscape','relationships','validation','actions'],
        'comprehensive':['landscape','evolution','relationships','deep_dive','validation','actions']}[purpose]
    expected_label = {'research_development':'布局与演进','cooperation_discovery':'合作发现','comprehensive':'综合研究'}[purpose]
    ROOT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as automation:
        browser = await automation.chromium.launch(channel='msedge', headless=True)
        page = await browser.new_page(viewport={'width':1440,'height':1100}, accept_downloads=True)
        try:
            await page.goto('http://127.0.0.1:5173')
            await page.get_by_label('用户名',exact=True).fill('organization_e2e')
            await page.get_by_label('密码',exact=True).fill(os.environ["ADRS_E2E_PASSWORD"])
            await page.get_by_role('button',name='登录',exact=True).click()
            await page.get_by_role('button',name='研究',exact=True).first.wait_for()
            if baseline:
                response=await page.request.post('http://127.0.0.1:5173/api/v1/research',data={
                    'query':QUERY,'max_revision':1,'output_length':'short','organization_research':{
                        'scope':{'organization_types':['university'],'entities':[{'entity_id':'pku','name':'Peking University','type':'university','source_urls':[SOURCE]}],
                            'disciplines':['computer science'],'topic':'DistServe','start_date':'2024-01-01','end_date':'2024-12-31'},
                        'purpose':'research_development','modules':['evolution'],
                        'weights':{'preset':'cooperation_discovery','config_version':'purpose-e2e-v1'}}})
                (ROOT/'baseline-response.txt').write_text(await response.text(),encoding='utf-8')
                assert response.ok, 'Valid evolution-only organization research must be accepted: '+await response.text()
                raise AssertionError('Unexpected pre-implementation acceptance; inspect the actual result instead of manufacturing RED')
            session=existing
            if not session:
                await page.get_by_role('button',name='研究',exact=True).first.click()
                await page.get_by_label('组织研究模式',exact=True).check()
                await page.get_by_placeholder('例如：分析 2025 年中国新能源汽车市场格局').fill(QUERY)
                for label in ['科研实验室','企业']:
                    await page.get_by_label(label,exact=True).uncheck()
                await page.get_by_label('学科（逗号分隔）').fill('computer science')
                await page.get_by_label('研究开始日期').fill('2024-01-01')
                await page.get_by_label('研究截止日期').fill('2024-12-31')
                await page.get_by_role('button',name='添加研究对象',exact=True).click()
                await page.get_by_label('对象 1 名称',exact=True).fill('Peking University')
                await page.get_by_label('对象 1 类型',exact=True).select_option('university')
                await page.get_by_label('对象 1 来源',exact=True).fill(SOURCE)
                weights=page.get_by_role('region',name='研究偏好与评价')
                await weights.get_by_label('权重预设',exact=True).select_option('cooperation_discovery')
                await weights.get_by_label('合作互补性 生效权重',exact=True).get_by_text('15.00%',exact=True).wait_for()
                for option in ['cooperation_discovery','comprehensive','research_development']:
                    await page.get_by_label('研究目的',exact=True).select_option(option)
                    await weights.get_by_label('合作互补性 生效权重',exact=True).get_by_text('15.00%',exact=True).wait_for()
                await page.get_by_label('研究目的',exact=True).select_option(purpose)
                modules=page.get_by_role('group',name='研究模块')
                posts=[]
                page.on('request',lambda request:posts.append(request.post_data_json) if request.url.endswith('/api/v1/research') and request.method=='POST' else None)
                if purpose == 'research_development':
                    for checkbox in await modules.get_by_role('checkbox').all():
                        await checkbox.uncheck()
                    await page.get_by_role('button',name='开始研究',exact=True).click()
                    await page.get_by_role('alert').filter(has_text='研究模块').wait_for()
                    assert not posts, 'Empty module selection must not start research'
                    await page.get_by_label('研究模块 研究演进',exact=True).check()
                async with page.expect_response(lambda r:r.url.endswith('/api/v1/research') and r.request.method=='POST') as started:
                    await page.get_by_role('button',name='开始研究',exact=True).click()
                response=await started.value
                assert response.ok,await response.text()
                session=(await response.json())['session_id'];(ROOT/'session.txt').write_text(session)
                assert len(posts)==1,posts
                requested=posts[0]['organization_research']
                assert requested['purpose']==purpose and requested['modules']==expected_modules
                assert requested['weights']['preset']=='cooperation_discovery'
                (ROOT/'request.json').write_text(json.dumps(posts[0],ensure_ascii=False,indent=2),encoding='utf-8')
                print('Actual purpose study:',purpose,session,flush=True)
            for _ in range(360):
                response=await page.request.get('http://127.0.0.1:5173/api/v1/research/'+session)
                assert response.ok,await response.text()
                result=await response.json()
                if result['status']=='completed':break
                assert result['status']!='failed',result
                await asyncio.sleep(2)
            else:raise AssertionError('Observe the same active purpose study: '+session)
            (ROOT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            config=result['organization_research'];findings=result['organization_result']
            assert config['purpose']==purpose and config['modules']==expected_modules
            assert config['effective_weights']['raw_config']['preset']=='cooperation_discovery'
            assert abs(config['effective_weights']['effective_weights']['cooperation_complementarity']-.15)<1e-8
            delivery=findings['module_report']
            assert not delivery['issues'],delivery
            assert [module['module_id'] for module in delivery['modules']]==expected_modules
            assert all(module['paragraphs'] and module['status']=='draft_requires_review' for module in delivery['modules'])
            assert any(paragraph['citations'] for module in delivery['modules'] for paragraph in module['paragraphs']),delivery
            assert findings['report_summary']['analysis']['modules']==expected_modules
            conn=await asyncpg.connect(DB)
            saved=await conn.fetchrow('SELECT final_report,review_status FROM research_sessions WHERE id=$1::uuid',session);await conn.close()
            assert saved['final_report']==result['report']
            assert json.loads(saved['review_status'])['organization_result']['module_report']==delivery
            await page.goto('http://127.0.0.1:5173/?session='+session)
            await page.get_by_label('报告研究目的',exact=True).get_by_text(expected_label,exact=True).wait_for()
            await page.get_by_label('报告研究模块',exact=True).get_by_text('、'.join(module['label'] for module in delivery['modules']),exact=True).wait_for()
            for module in delivery['modules']:
                await page.locator('.report-content').get_by_role('heading',name=module['label'],exact=True).wait_for()
            async with page.expect_download() as waiting:
                await page.get_by_role('button',name='下载研究数据',exact=True).click()
            download=await waiting.value;assert await download.failure() is None
            await download.save_as(str(ROOT/'report.json'))
            artifact=json.loads((ROOT/'report.json').read_text(encoding='utf-8'))
            assert artifact['organization_result']['module_report']==delivery
            assert artifact['organization_research']==config
            await page.screenshot(path=str(ROOT/'result.png'),full_page=True)
            if purpose == 'comprehensive':
                for label, name in [('下载 Markdown','report.md'),('下载 HTML','report.html')]:
                    async with page.expect_download() as exported:
                        await page.get_by_role('button',name=label,exact=True).click()
                    file=await exported.value;assert await file.failure() is None
                    await file.save_as(str(ROOT/name))
                assert (ROOT/'report.md').read_text(encoding='utf-8')==result['report']
                offline=await browser.new_context(offline=True)
                local=await offline.new_page()
                await local.goto((ROOT/'report.html').resolve().as_uri())
                await local.get_by_label('报告研究目的',exact=True).get_by_text(expected_label,exact=True).wait_for()
                for module in delivery['modules']:
                    await local.get_by_role('heading',name=module['label'],exact=True).wait_for()
                await local.screenshot(path=str(ROOT/'offline.png'),full_page=True)
                await offline.close()
            print('PASS actual UI purpose/modules independently frozen from weights -> scoped report/JSON:',session,flush=True)
        except Exception:
            await page.screenshot(path=str(ROOT/'failure.png'),full_page=True)
            raise
        finally:await browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',action='store_true');parser.add_argument('--session')
    parser.add_argument('--purpose',choices=['research_development','cooperation_discovery','comprehensive'],default='research_development');args=parser.parse_args()
    asyncio.run(main(args.baseline,args.session,args.purpose))
