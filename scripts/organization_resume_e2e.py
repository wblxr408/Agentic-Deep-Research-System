"""Actual authenticated research pause -> operator defaults change -> resume.

prepare creates a new real task and records its server-owned paused snapshot.
resume consumes that same task; it never substitutes an agent/tool/database.
"""
import os
import asyncio
import json
import sys
from pathlib import Path

import asyncpg
import httpx

ROOT = Path('.codex-homework/organization-resume-e2e')
DATABASE = os.environ["ADRS_E2E_DATABASE_URL"]


async def runtime(connection, session):
    record = await connection.fetchrow('SELECT state_snapshot_json FROM session_runtime_state WHERE session_id=$1::uuid', session)
    return json.loads(record['state_snapshot_json']) if record else None


async def prepare(client, connection):
    query = '研究 MIT 官网的公开科研组织架构及其证据边界。只阅读 https://www.mit.edu/research/ ，不要修改任何系统，不需要论文全集。'
    payload = {'query': query, 'user_confirmed': True, 'max_revision': 1,
        'organization_research': {'scope': {'organization_types': ['university'],
            'entities': [{'entity_id': 'mit', 'name': 'MIT', 'type': 'university',
                'source_urls': ['https://www.mit.edu/research/']}],
            'disciplines': ['computer science'], 'topic': '科研组织架构',
            'start_date': '2020-01-01', 'end_date': '2026-10-20'},
            'weights': {'preset': 'research_development'}}}
    response = await client.post('/api/v1/research', json=payload)
    assert response.is_success, response.text
    session = response.json()['session_id']
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / 'session.txt').write_text(session)
    for _ in range(120):
        snapshot = await runtime(connection, session)
        if snapshot and snapshot['status'] == 'paused':
            break
        await asyncio.sleep(2)
    else:
        raise AssertionError(f'Actual task did not pause: {session}')
    (ROOT / 'before.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
    original = snapshot['organization_research']
    assert snapshot['pending_approvals'], snapshot
    assert original['catalog_manifest']['sources'], original
    assert original['effective_weights']['effective_weights']['topic_relevance'] == .35, original
    print(f'Actual task paused with frozen configuration: {session}')


async def resume(client, connection):
    session = (ROOT / 'session.txt').read_text().strip()
    before = json.loads((ROOT / 'before.json').read_text(encoding='utf-8'))
    original = before['organization_research']
    changed = await client.post('/api/v1/research/weights/preview', json={'preset': 'research_development'})
    assert changed.is_success, changed.text
    assert changed.json()['preset_version'] != original['effective_weights']['preset_version'], changed.text
    assert changed.json()['effective_weights']['topic_relevance'] != original['effective_weights']['effective_weights']['topic_relevance'], changed.text
    for _ in range(180):
        response = await client.get(f'/api/v1/research/{session}')
        assert response.is_success, response.text
        result = response.json()
        if result['status'] == 'completed':
            break
        if result['status'] == 'failed':
            raise AssertionError(result)
        if result['status'] == 'paused':
            snapshot = await runtime(connection, session)
            assert snapshot['organization_research'] == original, snapshot
            for approval in snapshot['pending_approvals']:
                # Approve only actual readonly reads, bound to this exact task.
                assert approval['tool_name'] in {'browse_webpage', 'duckduckgo_search'}, approval
                response = await client.post(f'/api/v1/research/{session}/approvals/{approval["approval_id"]}',
                    json={'action': 'approve', 'approved_by': 'organization_e2e', 'comment': 'Read-only research resume acceptance'})
                assert response.is_success, response.text
        await asyncio.sleep(2)
    else:
        raise AssertionError(f'Resumed task has not completed; preserve {session}')
    final = await runtime(connection, session)
    assert final['organization_research'] == original, final
    assert result['organization_research'] == original, result
    assert result['report'] and result['citations'], result
    assert final['approval_decisions'], final
    (ROOT / 'after.json').write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding='utf-8')
    (ROOT / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'PASS actual pause -> changed defaults -> bound approval resume -> original config -> sourced report: {session}')


async def main():
    async with httpx.AsyncClient(base_url='http://127.0.0.1:8000', timeout=120) as client:
        for attempt in range(12):
            try:
                login = await client.post('/api/v1/auth/login', json={'username':'organization_e2e', 'password':os.environ["ADRS_E2E_PASSWORD"]})
                break
            except httpx.ConnectError:
                if attempt == 11:
                    raise
                await asyncio.sleep(1)
        assert login.is_success, login.text
        connection = await asyncpg.connect(DATABASE)
        try:
            await (prepare if sys.argv[1] == 'prepare' else resume)(client, connection)
        finally:
            await connection.close()


if __name__ == '__main__':
    asyncio.run(main())
