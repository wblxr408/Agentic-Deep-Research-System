"""Two real identities -> versioned personal preset -> actual research report."""
import os
import asyncio
import json
import sys
from pathlib import Path

import asyncpg
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.security.auth import hash_password

ROOT = Path('.codex-homework/organization-presets-e2e')


async def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    connection = await asyncpg.connect(os.environ["ADRS_E2E_DATABASE_URL"])
    # Provision a second independent identity only in this isolated acceptance DB.
    # Authentication itself still goes through the real password/session API.
    await connection.execute("INSERT INTO auth_principals (username,password_hash) VALUES ($1,$2) ON CONFLICT (username) DO NOTHING", 'organization_e2e_b', hash_password(os.environ["ADRS_E2E_OTHER_PASSWORD"]))
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000', timeout=120) as alice, httpx.AsyncClient(base_url='http://127.0.0.1:8000', timeout=120) as bob:
        for client, username, password in [(alice, 'organization_e2e', os.environ["ADRS_E2E_PASSWORD"]), (bob, 'organization_e2e_b', os.environ["ADRS_E2E_OTHER_PASSWORD"])]:
            response = await client.post('/api/v1/auth/login', json={'username':username, 'password':password})
            assert response.is_success, response.text
        first = await alice.post('/api/v1/research/presets', json={'name':'个人科研偏好', 'configuration':{'preset':'custom', 'weights':{'topic_relevance':6, 'evidence_completeness':4}}})
        assert first.status_code == 201, first.text
        version1 = first.json()
        identifier = version1['preset_id']
        other = await bob.post('/api/v1/research/presets', json={'name':'个人科研偏好', 'configuration':{'preset':'custom','weights':{'topic_relevance':1}}})
        assert other.status_code == 201, other.text
        for response in [await bob.get(f'/api/v1/research/presets/{identifier}'), await bob.put(f'/api/v1/research/presets/{identifier}',json={'expected_version':1,'name':'篡改','configuration':{'preset':'research_development'}})]:
            assert response.status_code == 404, response.text
        assert all(item['preset_id'] != identifier for item in (await bob.get('/api/v1/research/presets')).json()['items'])
        request = {'query':'研究 MIT 官网公开科研组织架构，核对来源与证据缺口，只读 https://www.mit.edu/research/ ，无需论文全集。', 'max_revision':1,
            'organization_research': {'scope': {'organization_types':['university'], 'entities':[{'entity_id':'mit','name':'MIT','type':'university','source_urls':['https://www.mit.edu/research/']}],
                'disciplines':['computer science'],'topic':'科研组织架构','start_date':'2020-01-01','end_date':'2026-10-20'},
                'weight_preset':{'preset_id':identifier,'version':1}}}
        denied = await bob.post('/api/v1/research', json=request)
        assert denied.status_code == 404, denied.text
        response = await alice.post('/api/v1/research', json=request)
        assert response.is_success, response.text
        session = response.json()['session_id']
        (ROOT/'session.txt').write_text(session)
        update = await alice.put(f'/api/v1/research/presets/{identifier}',json={'expected_version':1,'name':'个人科研偏好 v2','configuration':{'preset':'custom','weights':{'topic_relevance':1,'evidence_completeness':9}}})
        assert update.is_success and update.json()['version'] == 2, update.text
        stale = await alice.put(f'/api/v1/research/presets/{identifier}',json={'expected_version':1,'name':'旧写入','configuration':{'preset':'research_development'}})
        assert stale.status_code == 409, stale.text
        historical = await alice.get(f'/api/v1/research/presets/{identifier}?version=1')
        assert historical.json() == version1, historical.text
        for _ in range(240):
            result = (await alice.get(f'/api/v1/research/{session}')).json()
            if result['status'] == 'completed':
                break
            assert result['status'] != 'failed', result
            await asyncio.sleep(2)
        else:
            raise AssertionError(f'Preserve live research {session}')
        config = result['organization_research']
        assert config['selected_preset']['version'] == 1, config
        assert abs(config['effective_weights']['effective_weights']['topic_relevance'] - .6) < 1e-12, config
        assert abs(update.json()['effective_configuration']['effective_weights']['topic_relevance'] - .1) < 1e-12, update.text
        assert result['report'] and result['citations'], result
        final_edit = await alice.put(f'/api/v1/research/presets/{identifier}',json={'expected_version':2,'name':'个人科研偏好 v3','configuration':{'preset':'custom','weights':{'topic_relevance':9,'evidence_completeness':1}}})
        assert final_edit.is_success and final_edit.json()['version'] == 3, final_edit.text
        unchanged = await alice.get(f'/api/v1/research/{session}')
        assert unchanged.json() == result, unchanged.text
        for name, value in [('version1.json',version1),('version2.json',update.json()),('version3.json',final_edit.json()),('result.json',result)]:
            (ROOT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f'PASS two-owner isolation, historical preset, stale update rejection, actual research keeps selected v1: {session}')
    await connection.close()


if __name__ == '__main__':
    asyncio.run(main())
