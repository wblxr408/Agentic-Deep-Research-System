"""Actual layered preference editing -> saved preset -> research -> frozen report."""
import os
import asyncio
import json
from pathlib import Path

import asyncpg
from playwright.async_api import async_playwright, TimeoutError as BrowserTimeout

ROOT = Path('.codex-homework/organization-weights-ui-e2e')
LABELS = ['主题相关性','研究路线契合','成果表现','证据完整度','时效性','合作互补性']


async def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as automation:
        browser = await automation.chromium.launch(channel='msedge',headless=True)
        page = await browser.new_page(viewport={'width':1440,'height':1100})
        errors, research_posts = [], []
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.on('request',lambda request:research_posts.append(request.post_data_json)
            if request.url.endswith('/api/v1/research') and request.method == 'POST' else None)
        try:
            await page.goto('http://127.0.0.1:5173')
            for attempt in range(4):
                try:
                    await page.get_by_label('用户名',exact=True).wait_for(timeout=10000)
                    break
                except BrowserTimeout:
                    if attempt == 3:raise
                    await page.reload()
            await page.get_by_label('用户名',exact=True).fill('organization_e2e')
            await page.get_by_label('密码',exact=True).fill(os.environ["ADRS_E2E_PASSWORD"])
            await page.get_by_role('button',name='登录',exact=True).click()
            await page.get_by_role('button',name='研究',exact=True).first.click()
            await page.get_by_label('组织研究模式',exact=True).check()
            await page.get_by_role('region',name='研究偏好与评价').wait_for(timeout=15000)
            await page.get_by_placeholder('例如：分析 2025 年中国新能源汽车市场格局').fill('只研究 DistServe 出版商页面中 Peking University 的署名、发表年月和研究主题，保留来源及未知项。')
            for label in ['科研实验室','企业']:
                await page.get_by_label(label,exact=True).uncheck()
            await page.get_by_label('研究开始日期').fill('2024-01-01')
            await page.get_by_label('研究截止日期').fill('2024-12-31')
            await page.get_by_role('button',name='添加研究对象',exact=True).click()
            await page.get_by_label('对象 1 名称',exact=True).fill('Peking University')
            await page.get_by_label('对象 1 来源',exact=True).fill('https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin')
            await page.get_by_role('button',name='短文',exact=True).click()
            await page.get_by_label('权重预设',exact=True).select_option('research_development')
            await percentage(page,'主题相关性 生效权重',35)
            await page.get_by_label('时效性 启用',exact=True).uncheck()
            await percentage(page,'时效性 生效权重',0)
            await page.get_by_role('button',name='恢复所选预设',exact=True).click()
            await percentage(page,'时效性 生效权重',10)
            for label in LABELS:
                await page.get_by_label(label+' 权重',exact=True).fill('0')
            await page.get_by_role('button',name='开始研究',exact=True).click()
            await page.get_by_role('alert').filter(has_text='至少一项正权重').first.wait_for()
            assert not research_posts, research_posts
            await page.get_by_label('主题相关性 权重',exact=True).fill('-1')
            await page.get_by_role('button',name='开始研究',exact=True).click()
            await page.get_by_role('alert').filter(has_text='非负').first.wait_for()
            assert not research_posts, research_posts
            for label,value in zip(LABELS,['60','0','20','20','10','0']):
                await page.get_by_label(label+' 权重',exact=True).fill(value)
            await page.get_by_label('时效性 启用',exact=True).uncheck()
            await percentage(page,'主题相关性 生效权重',60)
            await page.get_by_role('alert').filter(has_text='非负').wait_for(state='hidden')
            await page.get_by_label('载体指标组 权重',exact=True).fill('3')
            await page.get_by_label('论文指标组 权重',exact=True).fill('1')
            await page.get_by_label('CCF 指标启用',exact=True).check()
            await page.get_by_label('CCF 指标权重',exact=True).fill('3')
            await page.get_by_label('ICORE 指标启用',exact=True).check()
            await page.get_by_label('ICORE 指标权重',exact=True).fill('1')
            await percentage(page,'CCF 组内比例',75)
            await page.get_by_label('ICORE 指标启用',exact=True).uncheck()
            await percentage(page,'CCF 组内比例',100)
            await page.get_by_label('ICORE 指标启用',exact=True).check()
            await percentage(page,'CCF 组内比例',75)
            await page.get_by_label('学科（逗号分隔）').fill('materials')
            await page.get_by_label('评价成果类型',exact=True).select_option('journal_article')
            await page.get_by_role('article',name='CCF 评价状态').get_by_text('不适用',exact=True).wait_for()
            await page.get_by_role('article',name='JCR JIF 评价状态').get_by_text('需授权导入',exact=True).wait_for()
            await page.get_by_label('学科（逗号分隔）').fill('computer science')
            await page.get_by_label('评价成果类型',exact=True).select_option('conference_paper')
            await page.get_by_text('查询精确载体／论文的目录样本',exact=True).click()
            await page.get_by_label('载体规范 ID',exact=True).fill('dblp:conf/nsdi')
            await page.get_by_label('成果发表年',exact=True).fill('2022')
            await page.get_by_label('评价年份',exact=True).fill('2022')
            await page.get_by_role('button',name='查询指定成果评价',exact=True).click()
            card = page.get_by_role('article',name='CCF 评价状态')
            await card.get_by_text('有匹配记录',exact=True).wait_for()
            await card.get_by_text('A · 2022',exact=True).wait_for()
            await page.get_by_label('个人预设名称',exact=True).fill('真实界面分层方案')
            async with page.expect_response(lambda r:r.url.endswith('/research/presets') and r.request.method=='POST') as saving:
                await page.get_by_role('button',name='保存为新预设',exact=True).click()
            response=await saving.value
            assert response.status==201,await response.text()
            version1=await response.json()
            await page.get_by_label('权重预设',exact=True).select_option('research_development')
            await percentage(page,'主题相关性 生效权重',35)
            await page.get_by_label('权重预设',exact=True).select_option(f"personal:{version1['preset_id']}:1")
            await percentage(page,'主题相关性 生效权重',60)
            await page.get_by_label('主题相关性 权重',exact=True).fill('90')
            await page.get_by_role('button',name='恢复所选预设',exact=True).click()
            await percentage(page,'主题相关性 生效权重',60)
            await page.get_by_label('主题相关性 权重',exact=True).fill('80')
            await percentage(page,'主题相关性 生效权重',200/3)
            async with page.expect_response(lambda r:r.url.endswith('/presets/'+version1['preset_id']) and r.request.method=='PUT') as saving:
                await page.get_by_role('button',name='保存新版本',exact=True).click()
            response=await saving.value
            assert response.ok,await response.text()
            version2=await response.json()
            assert version2['version']==2 and version1['preset_id']==version2['preset_id']
            await page.get_by_text('已选个人预设：真实界面分层方案 · v2',exact=True).wait_for()
            await page.screenshot(path=str(ROOT/'configured.png'),full_page=True)
            async with page.expect_response(lambda r:r.url.endswith('/api/v1/research') and r.request.method=='POST') as started:
                await page.get_by_role('button',name='开始研究',exact=True).click()
            response=await started.value
            assert response.ok,await response.text()
            session=(await response.json())['session_id']
            (ROOT/'session.txt').write_text(session)
            assert len(research_posts)==1,research_posts
            org=research_posts[0]['organization_research']
            assert org['weight_preset']=={'preset_id':version2['preset_id'],'version':2} and 'weights' not in org,org
            for _ in range(300):
                response=await page.request.get(f'http://127.0.0.1:5173/api/v1/research/{session}')
                assert response.ok,await response.text()
                result=await response.json()
                if result['status']=='completed':break
                assert result['status']!='failed',result
                await asyncio.sleep(2)
            else:raise AssertionError(f'Preserve the same live research {session}')
            frozen=result['organization_research']
            assert frozen['selected_preset']['version']==2,frozen
            preview=frozen['effective_weights']
            assert abs(preview['effective_weights']['topic_relevance']-2/3)<1e-8,preview
            assert preview['effective_weights']['recency']==0 and preview['effective_groups']['venue']==.75,preview
            assert preview['effective_metric_weights']['ccf']==.75 and preview['effective_metric_weights']['icore']==.25,preview
            assert result['report'] and result['citations'],result
            heading=next(line.lstrip('#').strip() for line in result['report'].splitlines() if line.startswith('#'))
            await page.get_by_role('heading',name=heading,exact=True).first.wait_for(timeout=20000)
            connection=await asyncpg.connect(os.environ["ADRS_E2E_DATABASE_URL"])
            saved=json.loads(await connection.fetchval('SELECT review_status FROM research_sessions WHERE id=$1::uuid',session))
            assert saved['organization_research']==frozen,saved
            await connection.close()
            assert not errors,errors
            for filename,value in [('result.json',result),('preset-v1.json',version1),('preset-v2.json',version2),('request.json',research_posts[0])]:
                (ROOT/filename).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
            (ROOT/'report.md').write_text(result['report'],encoding='utf-8')
            await page.screenshot(path=str(ROOT/'report.png'),full_page=True)
            print('PASS actual editable layered UI -> owner preset v2 -> frozen research/report:',session)
        except Exception:
            await page.screenshot(path=str(ROOT/'failure.png'),full_page=True)
            (ROOT/'failure-body.txt').write_text(await page.locator('body').inner_text(),encoding='utf-8')
            raise
        finally:await browser.close()


async def percentage(page,label,expected):
    expected_text=f'{expected:.2f}%'
    await page.get_by_label(label,exact=True).get_by_text(expected_text,exact=True).wait_for(timeout=15000)


if __name__=='__main__':asyncio.run(main())
