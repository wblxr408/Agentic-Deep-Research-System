"""Real research -> owner snapshot -> GUI rerank without collection -> new study."""
import os
import argparse
import asyncio
import json
import sys
from pathlib import Path

import asyncpg
import httpx
from playwright.async_api import async_playwright, TimeoutError as BrowserTimeout

ROOT = Path('.codex-homework/organization-rerank-e2e')
DB = os.environ["ADRS_E2E_DATABASE_URL"]
ORCA = 'https://www.usenix.org/conference/osdi22/presentation/yu'
DIST = 'https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin'


async def prepare(existing=None):
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000',timeout=120) as client:
        for attempt in range(30):
            try:
                response=await client.post('/api/v1/auth/login',json={'username':'organization_e2e','password':os.environ["ADRS_E2E_PASSWORD"]})
                if response.status_code<500:break
            except httpx.TransportError:
                if attempt==29:raise
            await asyncio.sleep(2)
        assert response.is_success,response.text
        session=existing
        if session is None:
            response=await client.post('/api/v1/research',json={
                'query':f'比较 Orca 和 DistServe 两项 LLM 推理服务研究。严格同时纳入这两个出版商页面代表的原始论文：{ORCA} 和 {DIST}，核实发表日期与作者机构。只研究 Seoul National University 与 Peking University。Orca 是本次词面偏好，不能因此排除作为对照的 DistServe。不要把引用文献或会议总议程另计为成果。',
                'max_revision':1,'output_length':'medium','organization_research':{
                    'scope':{'organization_types':['university'],'entities':[
                        {'entity_id':'snu','name':'Seoul National University','type':'university','source_urls':[ORCA]},
                        {'entity_id':'pku','name':'Peking University','type':'university','source_urls':[DIST]}],
                        'disciplines':['computer science'],'topic':'Orca','start_date':'2022-01-01','end_date':'2024-12-31'},
                    'weights':{'preset':'custom','weights':{'topic_relevance':60,'recency':20,'output_performance':20}}}})
            assert response.is_success,response.text
            session=response.json()['session_id']
            (ROOT/'session.txt').write_text(session)
            print('Actual research created:',session,flush=True)
        for _ in range(300):
            response=await client.get('/api/v1/research/'+session)
            assert response.is_success,response.text
            result=response.json()
            if result['status']=='completed':break
            assert result['status']!='failed',result
            await asyncio.sleep(2)
        else:raise AssertionError(f'Keep observing the same real research {session}')
        (ROOT/'source-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print('Actual source report completed:',session,flush=True)
        return session


async def verify(session):
    connection=await asyncpg.connect(DB)
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from app.db.matching import MATCHING_SCHEMA_SQL
    await connection.execute(MATCHING_SCHEMA_SQL)
    async def business_state():
        row=await connection.fetchrow('SELECT final_report,review_status,total_tokens,total_cost_usd FROM research_sessions WHERE id=$1::uuid',session)
        return {'report':row['final_report'],'review':row['review_status'],
            'tokens':row['total_tokens'],'cost':str(row['total_cost_usd']),
            'calls':await connection.fetchval('SELECT count(*) FROM tool_call_audit WHERE session_id=$1::uuid',session),
            'sessions':await connection.fetchval('SELECT count(*) FROM research_sessions')}
    before=await business_state()
    async with async_playwright() as automation:
        browser=await automation.chromium.launch(channel='msedge',headless=True)
        page=await browser.new_page(viewport={'width':1440,'height':1100})
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        try:
            await page.goto('http://127.0.0.1:5173/?session='+session)
            for attempt in range(4):
                try:
                    await page.get_by_label('用户名',exact=True).wait_for(timeout=10000)
                    break
                except BrowserTimeout:
                    if attempt==3:raise
                    await page.reload()
            await page.get_by_label('用户名',exact=True).fill('organization_e2e')
            await page.get_by_label('密码',exact=True).fill(os.environ["ADRS_E2E_PASSWORD"])
            await page.get_by_role('button',name='登录',exact=True).click()
            panel=page.get_by_role('region',name='固定证据重排')
            await panel.get_by_role('button',name='准备本次证据快照',exact=True).click(timeout=15000)
            await panel.get_by_text('仅重算，不重新取证',exact=True).wait_for()
            async with page.expect_response(lambda r:r.url.endswith('/matching/preview') and r.request.method=='POST') as previewed:
                await panel.get_by_role('button',name='重排当前证据',exact=True).click()
            response=await previewed.value
            assert response.ok,await response.text()
            original=await response.json()
            rows=original['groups'][0]['pending_evidence']+original['groups'][0]['complete']
            assert {row['entity_id'] for row in rows}=={'pku','snu'},original
            assert all(abs(row['coverage']-.8)<1e-8 for row in rows),original
            assert {'better':'snu','worse':'pku'} in original['groups'][0]['definitely_better'],original
            assert all(row['score'] is None and row['lower_bound']<row['upper_bound'] for row in rows),original
            for row in rows:
                await panel.get_by_label(row['name']+' 有效权重覆盖率',exact=True).get_by_text('80.00%',exact=True).wait_for()
                await panel.get_by_label(row['name']+' 分数区间',exact=True).get_by_text(f"{row['lower_bound']:.2f}–{row['upper_bound']:.2f}",exact=True).wait_for()
            await panel.get_by_text('来源快照：'+original['snapshot_id'],exact=True).wait_for()
            await panel.screenshot(path=str(ROOT/'before-rerank.png'))
            editor=panel.get_by_role('region',name='研究偏好与评价')
            await editor.get_by_label('主题相关性 权重',exact=True).fill('20')
            await editor.get_by_label('时效性 权重',exact=True).fill('80')
            await editor.get_by_label('成果表现 权重',exact=True).fill('0')
            await editor.get_by_label('主题相关性 生效权重',exact=True).get_by_text('20.00%',exact=True).wait_for()
            async with page.expect_response(lambda r:r.url.endswith('/matching/preview') and r.request.method=='POST') as previewed:
                await panel.get_by_role('button',name='重排当前证据',exact=True).click()
            response=await previewed.value
            assert response.ok,await response.text()
            changed=await response.json()
            assert changed['configuration']['config_version']!=original['configuration']['config_version'],'Changed preferences retained the old configuration version'
            assert changed['snapshot_id']==original['snapshot_id'] and changed['evidence_cutoff']==original['evidence_cutoff'],changed
            assert {'better':'pku','worse':'snu'} in changed['groups'][0]['definitely_better'],changed
            rows=changed['groups'][0]['pending_evidence']+changed['groups'][0]['complete']
            assert all(row['coverage']==1 and row['score'] is None and row['lower_bound']<row['upper_bound'] for row in rows),changed
            assert all(row['contributions']['recency']['evidence_ids'] for row in rows),changed
            for row in rows:
                await panel.get_by_label(row['name']+' 有效权重覆盖率',exact=True).get_by_text('100.00%',exact=True).wait_for()
            await panel.get_by_text('确定优先：Peking University → Seoul National University',exact=True).wait_for()
            await panel.screenshot(path=str(ROOT/'after-rerank.png'))
            assert await business_state()==before,'Reranking changed the original study or added collection'
            payload=await connection.fetchval('SELECT payload FROM research_matching_snapshots WHERE id=$1::uuid',original['snapshot_id'])
            payload=json.loads(payload) if isinstance(payload,str) else payload
            assert payload['origin']=='saved_research' and str(payload['session_id'])==session,payload
            assert all(e['verification_status']=='unreviewed' for e in payload['evidence']),payload
            forged=await page.request.post('http://127.0.0.1:5173/api/v1/research/matching/snapshots',data=json.dumps(payload),headers={'Content-Type':'application/json'})
            assert forged.status==422,await forged.text()
            repeated=await page.request.post(f'http://127.0.0.1:5173/api/v1/research/{session}/matching/snapshot')
            assert repeated.ok,await repeated.text()
            assert (await repeated.json())['snapshot_id']==original['snapshot_id']
            assert await connection.fetchval('SELECT count(*) FROM research_matching_snapshots WHERE session_id=$1::uuid',session)==1
            async with httpx.AsyncClient(base_url='http://127.0.0.1:8000',timeout=120) as other:
                login=await other.post('/api/v1/auth/login',json={'username':'organization_e2e_b','password':os.environ["ADRS_E2E_OTHER_PASSWORD"]})
                assert login.is_success,login.text
                for route,body in [(f'/{session}/matching/snapshot',None),('/matching/preview',{'snapshot_id':original['snapshot_id'],'configuration':{'weights':{'topic_relevance':1}}})]:
                    denied=await other.post('/api/v1/research'+route,json=body)
                    assert denied.status_code==404,denied.text
                explicit={**payload,'origin':'explicit_records','source_execution_id':None,'bridge_version':None,'bridge_notes':[]}
                denied=await other.post('/api/v1/research/matching/snapshots',json=explicit)
                assert denied.status_code==404,denied.text
                explicit['session_id']=None
                owned=await other.post('/api/v1/research/matching/snapshots',json=explicit)
                assert owned.status_code==201,owned.text
                own_preview=await other.post('/api/v1/research/matching/preview',json={'snapshot_id':owned.json()['snapshot_id'],'configuration':{'preset':'custom','weights':{'topic_relevance':1}}})
                assert own_preview.is_success,own_preview.text
                denied=await page.request.post('http://127.0.0.1:5173/api/v1/research/matching/preview',data=json.dumps({'snapshot_id':owned.json()['snapshot_id'],'configuration':{'weights':{'topic_relevance':1}}}),headers={'Content-Type':'application/json'})
                assert denied.status==404,await denied.text()
            async with page.expect_response(lambda r:r.url.endswith('/api/v1/research') and r.request.method=='POST') as created:
                await panel.get_by_role('button',name='重新取证并研究',exact=True).click()
            response=await created.value
            assert response.ok,await response.text()
            fresh=(await response.json())['session_id']
            assert fresh!=session
            (ROOT/'fresh-session.txt').write_text(fresh)
            for _ in range(300):
                response=await page.request.get('http://127.0.0.1:5173/api/v1/research/'+fresh)
                assert response.ok,await response.text()
                result=await response.json()
                if result['status']=='completed':break
                assert result['status']!='failed',result
                await asyncio.sleep(2)
            else:raise AssertionError(f'Preserve actual new research {fresh}')
            assert result['organization_research']['effective_weights']['effective_weights']['topic_relevance']==.2,result
            assert await connection.fetchval('SELECT count(*) FROM tool_call_audit WHERE session_id=$1::uuid',fresh)>0
            assert result['report'] and result['citations'],result
            old=await business_state()
            assert old['report']==before['report'] and old['review']==before['review'] and old['calls']==before['calls']
            assert old['sessions']==before['sessions']+1
            assert not errors,errors
            for name,value in [('before.json',original),('after.json',changed),('snapshot.json',payload),('fresh-result.json',result)]:
                (ROOT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
            print('PASS actual research -> owner PG snapshot -> range/coverage/contribution rerank with zero collection -> separate new research',session,fresh)
        except Exception:
            await page.screenshot(path=str(ROOT/'failure.png'),full_page=True)
            (ROOT/'failure-body.txt').write_text(await page.locator('body').inner_text(),encoding='utf-8')
            raise
        finally:await browser.close()
    await connection.close()


async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=['prepare','verify','all'],default='all')
    parser.add_argument('--existing')
    args=parser.parse_args()
    ROOT.mkdir(parents=True,exist_ok=True)
    session=args.existing
    if args.phase in ('prepare','all'):session=await prepare(session)
    if args.phase in ('verify','all'):await verify(session or (ROOT/'session.txt').read_text().strip())


if __name__=='__main__':asyncio.run(main())
