"""Real restricted-source study -> sample flow, persistence, UI and actual export."""
import os
import argparse
import asyncio
from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import urlsplit

import asyncpg
from playwright.async_api import async_playwright

ROOT = Path('.codex-homework/organization-corpus-e2e')
DIST = 'https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin'
HARP = 'https://www.usenix.org/conference/nsdi26/presentation/hu-jiayu'
DB = os.environ["ADRS_E2E_DATABASE_URL"]
QUERY = '研究 Peking University 的2024年系统成果样本。只读取声明的两个USENIX种子：DistServe应按原文评估纳入，Harp发表在2026年应排除。不要求取得论文PDF；缺全文不能说已深读。声明实际样本流转和未知，不把这两个页面称为现实成果全集。'
REQUEST = {'query':QUERY,'max_revision':1,'output_length':'medium','organization_research':{
    'scope':{'organization_types':['university'],'entities':[{'entity_id':'pku','name':'Peking University','type':'university','source_urls':[DIST]}],
        'disciplines':['computer science'],'topic':'systems research','start_date':'2024-01-01','end_date':'2024-12-31'},
    'purpose':'research_development','modules':['landscape'],
    'corpus':{'source_scope':{'groups':['publishers'],'publisher_domains':['usenix.org']},
        'collection_mode':'seeds_only','seed_urls':[DIST,DIST+'#abstract',HARP],
        'search_terms':['DistServe Peking University','Harp 2026'],
        'output_types':['conference_paper']}}}


async def main(baseline, existing, use_ui=False, search_mode=False, overlap=False):
    global ROOT, REQUEST
    if search_mode:
        ROOT=ROOT/'search_and_seeds';REQUEST=deepcopy(REQUEST)
        REQUEST['organization_research']['corpus']['collection_mode']='search_and_seeds'
        REQUEST['organization_research']['scope']['topic']='DistServe'
        REQUEST['query']='在声明的USENIX范围内检索并研究 Peking University 2024年 DistServe 样本，读取两个种子核对身份与日期。Harp发表于2026年应明确排除。检索线索与已读材料分开，未取得全文保持缺口，不声称现实成果全集。'
    if overlap:
        ROOT=ROOT/'date_overlap';REQUEST=deepcopy(REQUEST)
        REQUEST['organization_research']['scope'].update(start_date='2024-07-16',end_date='2024-07-31')
        REQUEST['organization_research']['corpus']['seed_urls']=[DIST]
        REQUEST['query']='只读声明的 DistServe 页面，评估 Peking University 在2024年7月16日至31日内的样本。若出版商只给2024年7月而无日期，应保留候选日期精度不足，不认定已在范围内或已在范围外，不编造具体日。'
    ROOT.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as automation:
        browser=await automation.chromium.launch(channel='msedge',headless=True)
        page=await browser.new_page(viewport={'width':1440,'height':1100},accept_downloads=True)
        try:
            await page.goto('http://127.0.0.1:5173')
            await page.get_by_label('用户名',exact=True).fill('organization_e2e')
            await page.get_by_label('密码',exact=True).fill(os.environ["ADRS_E2E_PASSWORD"])
            await page.get_by_role('button',name='登录',exact=True).click()
            await page.get_by_role('button',name='研究',exact=True).first.wait_for()
            session=existing
            if not session:
                if not baseline and not search_mode and not overlap:
                    rejected=[]
                    for name in ['out_of_scope_seed','unsupported_channel']:
                        invalid=deepcopy(REQUEST)
                        if name=='out_of_scope_seed':
                            invalid['organization_research']['corpus']['seed_urls']=['https://example.com/paper']
                        else:invalid['channels']=['youtube']
                        response=await page.request.post('http://127.0.0.1:5173/api/v1/research',data=invalid)
                        rejected.append({'case':name,'status':response.status,'response':await response.json()})
                        assert response.status==422,rejected[-1]
                    (ROOT/'rejected-inputs.json').write_text(json.dumps(rejected,ensure_ascii=False,indent=2),encoding='utf-8')
                submitted=REQUEST
                if use_ui:
                    await page.get_by_role('button',name='研究',exact=True).first.click()
                    await page.get_by_label('组织研究模式',exact=True).check()
                    await page.get_by_placeholder('例如：分析 2025 年中国新能源汽车市场格局').fill(QUERY)
                    for label in ['科研实验室','企业']:await page.get_by_label(label,exact=True).uncheck()
                    await page.get_by_label('学科（逗号分隔）').fill('computer science')
                    await page.get_by_label('研究开始日期').fill('2024-01-01');await page.get_by_label('研究截止日期').fill('2024-12-31')
                    await page.get_by_role('button',name='添加研究对象',exact=True).click()
                    await page.get_by_label('对象 1 名称',exact=True).fill('Peking University')
                    await page.get_by_label('对象 1 来源',exact=True).fill(DIST)
                    modules=page.get_by_role('group',name='研究模块')
                    for checkbox in await modules.get_by_role('checkbox').all():await checkbox.uncheck()
                    await page.get_by_label('研究模块 研究全景',exact=True).check()
                    await page.get_by_label('声明样本与来源范围',exact=True).check()
                    await page.get_by_label('样本采集方式',exact=True).select_option('seeds_only')
                    await page.get_by_label('来源域名（逗号分隔）').fill('usenix.org')
                    await page.get_by_label('样本种子（每行一个 HTTPS 网址）').fill('\n'.join(REQUEST['organization_research']['corpus']['seed_urls']))
                    await page.get_by_label('检索式声明（每行一条）').fill('\n'.join(REQUEST['organization_research']['corpus']['search_terms']))
                    await page.get_by_label('成果类型（可选，逗号分隔）').fill('conference_paper')
                    await page.get_by_role('region',name='研究偏好与评价').get_by_label('主题相关性 生效权重',exact=True).get_by_text('35.00%',exact=True).wait_for()
                    async with page.expect_response(lambda r:r.url.endswith('/api/v1/research') and r.request.method=='POST') as starting:
                        await page.get_by_role('button',name='开始研究',exact=True).click()
                    response=await starting.value;submitted=response.request.post_data_json
                else:
                    response=await page.request.post('http://127.0.0.1:5173/api/v1/research',data=REQUEST)
                if baseline:(ROOT/'baseline-response.txt').write_text(await response.text(),encoding='utf-8')
                assert response.ok,'A declared restricted corpus must start a real research: '+await response.text()
                session=(await response.json())['session_id'];(ROOT/'session.txt').write_text(session)
                (ROOT/'request.json').write_text(json.dumps(submitted,ensure_ascii=False,indent=2),encoding='utf-8')
                print('Actual corpus research:',session,flush=True)
            for _ in range(420):
                response=await page.request.get('http://127.0.0.1:5173/api/v1/research/'+session)
                assert response.ok,await response.text()
                result=await response.json()
                if result['status']=='completed':break
                if result['status']=='failed':
                    (ROOT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
                    raise AssertionError('Research failed; inspect saved result for '+session)
                await asyncio.sleep(2)
            else:raise AssertionError('Keep observing the same corpus study: '+session)
            (ROOT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            corpus=result['organization_result']['corpus']
            assert corpus['coverage']=='declared_retrieved_sample_not_real_world_census'
            assert corpus['declaration']['collection_mode']==('search_and_seeds' if search_mode else 'seeds_only')
            assert corpus['declaration']['search_terms']==REQUEST['organization_research']['corpus']['search_terms']
            assert corpus['request_frozen_at']==result['organization_research']['evidence_cutoff']
            records={item['source_url']:item for item in corpus['records']}
            assert ({DIST,HARP} <= set(records) if search_mode else set(records)==({DIST} if overlap else {DIST,HARP})),records
            if overlap:
                assert records[DIST]['admission_status']=='candidate' and records[DIST]['reason_code']=='date_precision_overlaps_scope',records[DIST]
            else:
                assert records[DIST]['admission_status']=='accepted',records[DIST]
                assert records[HARP]['admission_status']=='excluded' and records[HARP]['reason_code']=='publication_date_out_of_scope',records[HARP]
            assert records[DIST]['full_text_status']=='not_acquired',records[DIST]
            assert records[DIST]['stages'][0]['status']=='candidate'
            if search_mode:
                assert corpus['counts']['accepted_publications']>=1 and corpus['executed_queries'],corpus
                for item in corpus['records']:
                    host=urlsplit(item['source_url']).hostname or ''
                    if item['evidence_ids']:
                        assert host=='usenix.org' or host.endswith('.usenix.org'),item
                    elif host!='usenix.org' and not host.endswith('.usenix.org'):
                        assert item['admission_status']=='excluded',item
            elif overlap:
                assert corpus['counts']['accepted_publications']==0 and corpus['counts']['excluded_candidates']==0
            else:
                assert corpus['counts']['accepted_publications']==1 and corpus['counts']['accepted_research_families']==1
            assert corpus['counts']['duplicate_seed_urls']==(0 if overlap else 1)
            calls=await page.request.get('http://127.0.0.1:5173/api/v1/research/'+session+'/tool-calls')
            assert calls.ok,await calls.text()
            tools=await calls.json();assert tools,tools
            if search_mode:
                assert any(item['tool_name']=='execute_search' for item in tools),tools
                assert all(item['tool_name'] in {'execute_search','execute_browse'} for item in tools),tools
            else:
                assert all(item['tool_name']=='execute_browse' for item in tools),tools
                assert {item['args_json']['query'] for item in tools}==({DIST} if overlap else {DIST,HARP}),tools
            if not search_mode and len(tools)>2:
                assert sum(not item['safety_json'].get('reused_task_evidence') for item in tools)==2,tools
            (ROOT/'tool-calls.json').write_text(json.dumps(tools,ensure_ascii=False,indent=2),encoding='utf-8')
            conn=await asyncpg.connect(DB)
            saved=await conn.fetchrow('SELECT final_report,review_status FROM research_sessions WHERE id=$1::uuid',session);await conn.close()
            assert saved['final_report']==result['report']
            assert json.loads(saved['review_status'])['organization_result']['corpus']==corpus
            await page.goto('http://127.0.0.1:5173/?session='+session)
            panel=page.get_by_role('region',name='样本基线与流转')
            dist_row=panel.locator('tbody tr').filter(has=page.locator(f'a[href="{DIST}"]'))
            if overlap:
                await dist_row.get_by_text('候选待核',exact=True).wait_for()
            else:
                await dist_row.get_by_text('已采纳',exact=True).wait_for()
                await panel.locator('tbody tr').filter(has=page.locator(f'a[href="{HARP}"]')).get_by_text('已排除',exact=True).wait_for()
            await dist_row.get_by_text('未取得全文',exact=True).wait_for()
            async with page.expect_download() as exported:
                await page.get_by_role('button',name='下载研究数据',exact=True).click()
            file=await exported.value;assert await file.failure() is None;await file.save_as(str(ROOT/'export.json'))
            artifact=json.loads((ROOT/'export.json').read_text(encoding='utf-8'))
            assert artifact['organization_result']['corpus']==corpus
            await page.screenshot(path=str(ROOT/'result.png'),full_page=True)
            print('PASS restricted sources -> candidate/accepted/excluded/missing fulltext -> DB/UI/export:',session,flush=True)
        except Exception:
            await page.screenshot(path=str(ROOT/'failure.png'),full_page=True)
            raise
        finally:await browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--baseline',action='store_true');parser.add_argument('--session');parser.add_argument('--ui',action='store_true');parser.add_argument('--search',action='store_true');parser.add_argument('--overlap',action='store_true');args=parser.parse_args()
    asyncio.run(main(args.baseline,args.session,args.ui,args.search,args.overlap))
