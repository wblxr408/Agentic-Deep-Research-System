"""Actual publisher acquisition -> scoped extraction -> shared-output counts -> report."""
import os
import asyncio
import argparse
import json
from pathlib import Path

import asyncpg
import httpx

ROOT = Path('.codex-homework/organization-outputs-e2e')
SOURCE = 'https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin'


async def main(existing_session: str | None = None):
    ROOT.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000', timeout=120) as client:
        login = await client.post('/api/v1/auth/login', json={'username':'organization_e2e','password':os.environ["ADRS_E2E_PASSWORD"]})
        assert login.is_success, login.text
        request = {'query':f'只研究 DistServe 这一篇成果，根据出版商页面 {SOURCE} 核实 2024 年发表信息与作者单位。比较 Peking University、UC San Diego 和 StepFun 的本次样本归属，三方共有成果汇总不得重复；给出基于该成果的下一步评估建议，资助和正式协议证据不足须标明。',
            'max_revision':1, 'organization_research':{'scope':{
                'organization_types':['university','company'], 'disciplines':['computer science'],
                'topic':'DistServe', 'start_date':'2024-01-01','end_date':'2024-12-31',
                'entities':[{'entity_id':key,'name':name,'type':kind,'source_urls':[SOURCE]}
                    for key,name,kind in [('pku','Peking University','university'),('ucsd','UC San Diego','university'),('stepfun','StepFun','company')]]}}}
        session = existing_session
        if session is None:
            response = await client.post('/api/v1/research', json=request)
            assert response.is_success, response.text
            session = response.json()['session_id']
        (ROOT/'session.txt').write_text(session)
        for _ in range(240):
            response = await client.get(f'/api/v1/research/{session}')
            assert response.is_success, response.text
            result = response.json()
            if result['status'] == 'completed':
                break
            assert result['status'] != 'failed', result
            await asyncio.sleep(2)
        else:
            raise AssertionError(f'Preserve actual running research {session}')
    (ROOT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    data = result['organization_result']
    scope = data['scope_result']
    assert scope['summary']['publication_count'] == 1, scope
    assert scope['summary']['research_family_count'] == 1, scope
    assert [v['entity_id'] for v in scope['views']] == ['pku','ucsd','stepfun'], scope
    assert all(v['publication_count'] == 1 and v['research_family_count'] == 1 for v in scope['views']), scope
    assert len({key for view in scope['views'] for key in view['output_ids']}) == 1, scope
    assert data['source_checks']['accepted_output_count'] == 1, data
    assert data['comparison_groups'] and all(len(g['objects']) == 3 for g in data['comparison_groups']), data
    assert data['recommendations'] and all(item['evidence_ids'] for item in data['recommendations']), data
    assert data['relationship_coverage']['funding'] == 'not_established', data
    output = scope['outputs'][0]
    assert 'DistServe' in output['title'], output
    assert len({a['entity_id'] for a in output['affiliations']}) == 3, output
    assert output['published_on'] >= '2024-01-01' and output['published_until'] <= '2024-12-31', output
    appendix = result['report'].split('## 可复核样本与对象比较', 1)[1]
    for view in scope['views']:
        rows = [line.split('|')[1:-1] for line in appendix.splitlines() if line.startswith('|')]
        cells = next([cell.strip() for cell in row] for row in rows if row and row[0].strip() == view['name'])
        assert [int(cells[1]), int(cells[2])] == [1,1], cells
    assert all(item['statement'] in result['report'] for item in data['recommendations']), data
    connection = await asyncpg.connect(os.environ["ADRS_E2E_DATABASE_URL"])
    snapshot = json.loads(await connection.fetchval('SELECT state_snapshot_json FROM session_runtime_state WHERE session_id=$1::uuid',session))
    assert snapshot['organization_result'] == data, snapshot
    evidence = {e['evidence_id']:e for e in snapshot['collected_evidence']}
    for proof in data['source_checks']['proofs']:
        original = evidence[proof['evidence_id']]['content']
        assert original[proof['start']:proof['end']] == proof['quote'], proof
    await connection.close()
    (ROOT/'state.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf-8')
    (ROOT/'report.md').write_text(result['report'],encoding='utf-8')
    print(f'PASS actual publisher -> 3 attributed objects -> 1 shared publication/family -> matching report counts and provenance: {session}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', help='Continue observing the same real research without creating another job')
    asyncio.run(main(parser.parse_args().session))
