"""Real materials study -> frozen mapping -> owner-scoped UI reclassification."""
import os
import argparse
import asyncio
from copy import deepcopy
import json
from pathlib import Path

import asyncpg
from playwright.async_api import async_playwright

ROOT = Path('.codex-homework/organization-taxonomy-e2e')
DB = os.environ["ADRS_E2E_DATABASE_URL"]
SOURCE = 'https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0351439'


async def main(existing):
    ROOT.mkdir(exist_ok=True)
    async with async_playwright() as automation:
        browser = await automation.chromium.launch(channel='msedge',headless=True)
        page = await browser.new_page(viewport={'width':1440,'height':1100},accept_downloads=True)
        try:
            await page.goto('http://127.0.0.1:5173')
            await page.get_by_label('用户名',exact=True).fill('organization_e2e')
            await page.get_by_label('密码',exact=True).fill(os.environ["ADRS_E2E_PASSWORD"])
            await page.get_by_role('button',name='登录',exact=True).click()
            await page.get_by_role('button',name='研究',exact=True).first.wait_for()
            if not existing:
                request={'query':'研究 King Faisal University 的一项材料科学成果：'+SOURCE+'。只读声明出版页；核对主成果完整题名、发表日期 July 10, 2026、Shrouq H. Aleithan 的发表署名和期刊类型。按材料学问题、方法、应用梳理，保留钙钛矿表面钝化、维度工程及太阳能电池的多标签依据。仅为2025至2026的已得样本，2025未覆盖不能补零或推断增长。更正通知是核对线索，不另计论文。不扩展来源、不声称成果全集，不用CCF评价。',
                    'max_revision':1,'output_length':'medium','organization_research':{
                    'scope':{'organization_types':['university'],'entities':[{'entity_id':'kfu','name':'King Faisal University','type':'university','source_urls':[SOURCE]}],
                        'disciplines':['materials science'],'topic':'perovskite surface passivation','start_date':'2025-01-01','end_date':'2026-10-21'},
                    'purpose':'research_development','modules':['landscape','evolution'],
                    'taxonomy':{'preset':'materials_science','version':'materials-e2e-v1'},
                    'corpus':{'collection_mode':'seeds_only','seed_urls':[SOURCE],
                        'source_scope':{'groups':['publishers'],'publisher_domains':['journals.plos.org']},'output_types':['journal_article']}}}
                (ROOT/'request.json').write_text(json.dumps(request,ensure_ascii=False,indent=2),encoding='utf-8')
                response=await page.request.post('http://127.0.0.1:5173/api/v1/research',data=request)
                assert response.ok,await response.text()
                existing=(await response.json())['session_id'];(ROOT/'session.txt').write_text(existing)
                print('Actual new materials study:',existing,flush=True)
            for _ in range(420):
                response=await page.request.get('http://127.0.0.1:5173/api/v1/research/'+existing)
                assert response.ok,await response.text()
                result=await response.json()
                if result['status'] in ['completed','failed']:
                    break
                await asyncio.sleep(2)
            else:raise AssertionError('Continue observing same research: '+existing)
            (ROOT/'source-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            assert result['status']=='completed',result.get('review_status')
            initial=result['organization_result']['classification']
            assert initial==result['organization_result']['report_summary']['classification']
            assert len(initial['records'])==1,initial
            record=initial['records'][0];tags=record['labels']
            assert {tag['axis'] for tag in tags}=={'problem','method','application'},tags
            assert any(tag['role']=='associated' and tag['basis']['field']=='publisher_abstract' for tag in tags),tags
            assert any(tag['ancestors'] for tag in tags),tags
            assert [row['year'] for row in initial['annual']]==[2026] and initial['unobserved_years']==[2025]
            conn=await asyncpg.connect(DB)
            try:
                async def original_state():
                    row=await conn.fetchrow('SELECT final_report,total_tokens,total_cost_usd,request_payload FROM research_sessions WHERE id=$1::uuid',existing)
                    state=await conn.fetchval('SELECT state_snapshot_json FROM session_runtime_state WHERE session_id=$1::uuid',existing)
                    return {'session':dict(row),'runtime':state,'tools':await conn.fetchval('SELECT count(*) FROM tool_call_audit WHERE session_id=$1::uuid',existing)}
                before=await original_state()
                state=json.loads(before['runtime']) if isinstance(before['runtime'],str) else before['runtime']
                evidence={item['evidence_id']:item for item in state['collected_evidence']}
                for tag in tags:
                    basis=tag['basis'];assert evidence[basis['evidence_id']]['content'][basis['start']:basis['end']]==basis['quote']
                await page.goto('http://127.0.0.1:5173/?session='+existing)
                panel=page.get_by_role('region',name='同证据学科重分类',exact=True)
                await panel.get_by_label('查看分类版本',exact=True).select_option(initial['snapshot_id'])
                nodes=deepcopy(initial['taxonomy']['nodes'])
                nodes.append({'node_id':'materials-methods','label':'材料界面方法','discipline':'materials science','axis':'method','role':'core','terms':[]})
                for node in nodes:
                    if node['axis']=='method':
                        node['parent_id']='materials-methods' if node['node_id']!='materials-methods' else None
                    if node['node_id'].endswith(':interface-passivation'):node['role']='associated'
                nodes.append({'node_id':'dual-cation','label':'双阳离子策略','discipline':'materials science','axis':'method','role':'core','parent_id':'materials-methods','terms':['dual-cation']})
                await panel.get_by_label('分类方案',exact=True).select_option('custom')
                await panel.get_by_label('分类版本',exact=True).fill('materials-e2e-v2')
                await panel.get_by_label('自定义分类节点',exact=True).fill(json.dumps(nodes,ensure_ascii=False))
                await panel.get_by_label('重分类原因',exact=True).fill('增加界面方法层次与双阳离子交叉标签；表面钝化改为关联方向')
                async with page.expect_response(lambda r:r.url.endswith('/classifications') and r.request.method=='POST') as waiting:
                    await panel.get_by_role('button',name='保存同证据分类',exact=True).click()
                saved_response=await waiting.value;assert saved_response.status==201,await saved_response.text()
                revised=await saved_response.json();(ROOT/'reclassification.json').write_text(json.dumps(revised,ensure_ascii=False,indent=2),encoding='utf-8')
                assert revised['comparison']['same_publication_ids'] and revised['comparison']['same_evidence_ids']
                assert revised['comparison']['kind']=='reclassification_only' and not revised['comparison']['publication_growth_claim']
                assert len(revised['comparison']['changes'])==1
                revised_tags=revised['records'][0]['labels']
                assert any(tag['node_id']=='dual-cation' and tag['basis']['field']=='publisher_abstract' for tag in revised_tags)
                assert any(tag['node_id'].endswith(':interface-passivation') and tag['role']=='associated' for tag in revised_tags)
                await panel.get_by_label('查看分类版本',exact=True).select_option(revised['snapshot_id'])
                await panel.get_by_role('table',name='成果学科分类').get_by_text('双阳离子策略（核心）',exact=False).wait_for()
                await panel.screenshot(path=str(ROOT/'reclassification.png'))
                async with page.expect_download() as waiting_download:
                    await panel.get_by_role('button',name='下载当前分类数据',exact=True).click()
                download=await waiting_download.value;await download.save_as(str(ROOT/'classification-export.json'))
                exported=json.loads((ROOT/'classification-export.json').read_text(encoding='utf-8'))
                assert exported['classification']==revised
                # New rule with no retained-source support must stay unknown, not zero-quality.
                unknown={'taxonomy':{'preset':'custom','version':'materials-e2e-v3-unknown','nodes':[
                    {'node_id':'unknown-method','label':'待证实的新方法','discipline':'materials science','axis':'method','terms':['unobserved-experimental-method']}]},'reason':'检验未命中规则时保留未知'}
                r=await page.request.post(f'http://127.0.0.1:5173/api/v1/research/{existing}/classifications',data=unknown)
                assert r.status==201,await r.text()
                missing=await r.json();assert missing['records'][0]['labels']==[] and set(missing['records'][0]['axes'].values())=={'unknown'}
                (ROOT/'unknown.json').write_text(json.dumps(missing,ensure_ascii=False,indent=2),encoding='utf-8')
                duplicate=await page.request.post(f'http://127.0.0.1:5173/api/v1/research/{existing}/classifications',data=unknown)
                assert duplicate.status==201 and (await duplicate.json())['snapshot_id']==missing['snapshot_id']
                rejects=[]
                for name,payload,status in [
                    ('wrong_discipline',{'taxonomy':{'preset':'computer_science','version':'outside'},'reason':'学科不匹配'},422),
                    ('version_conflict',{**unknown,'taxonomy':{**unknown['taxonomy'],'nodes':[{**unknown['taxonomy']['nodes'][0],'label':'改写已存在版本'}]}},409),
                    ('cycle',{'taxonomy':{'preset':'custom','version':'cycle','nodes':[
                        {'node_id':'loop','label':'循环','discipline':'materials science','axis':'method','parent_id':'loop','terms':['solar']}]},'reason':'非法层次'},422)]:
                    r=await page.request.post(f'http://127.0.0.1:5173/api/v1/research/{existing}/classifications',data=payload)
                    rejects.append({'case':name,'status':r.status,'detail':await r.json()});assert r.status==status,rejects[-1]
                other=await browser.new_context()
                try:
                    r=await other.request.post('http://127.0.0.1:5173/api/v1/auth/login',data={'username':'organization_e2e_b','password':os.environ["ADRS_E2E_OTHER_PASSWORD"]});assert r.ok
                    for method in ['get','post']:
                        r=await getattr(other.request,method)(f'http://127.0.0.1:5173/api/v1/research/{existing}/classifications',**({'data':unknown} if method=='post' else {}))
                        assert r.status==404,(method,r.status)
                        rejects.append({'case':'other_owner_'+method,'status':r.status})
                finally:await other.close()
                after=await original_state();assert after==before,'Classification changed original research/report/budget/evidence/audits'
                review=await conn.fetchval('SELECT review_status FROM research_sessions WHERE id=$1::uuid',existing)
                review=json.loads(review) if isinstance(review,str) else review
                assert review['classification_versions']==[revised,missing]
                assert review['organization_result']['classification']==initial
                (ROOT/'rejected-inputs.json').write_text(json.dumps(rejects,ensure_ascii=False,indent=2),encoding='utf-8')
                (ROOT/'verification.json').write_text(json.dumps({'result':'passed','session_id':existing,'initial':initial,
                    'reclassified':revised,'unknown':missing,'no_new_tool_calls':before['tools']==after['tools'],
                    'original_report_preserved':True,'original_runtime_and_budget_preserved':True,'tool_calls':before['tools']},ensure_ascii=False,indent=2),encoding='utf-8')
                print('PASS: real materials study, abstract and title mapping, hierarchy/multilabel, same-evidence revisions, unknown, owners, export and persistence',flush=True)
            finally:await conn.close()
        finally:await browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--session');args=parser.parse_args()
    asyncio.run(main(args.session))
