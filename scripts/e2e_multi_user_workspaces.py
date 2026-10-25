"""Real HTTP/PostgreSQL journey for the new multi-user feature, no existing suites.

Requires a dedicated DATABASE_URL and a running API using that same database.
The account fixture and results stay in an ignored local directory. No model
provider is contacted except the explicitly supplied local refusing endpoint.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import time
from pathlib import Path
from uuid import uuid4

import asyncpg
import httpx


def expect(response, code):
    assert response.status_code == code, f'{response.request.method} {response.request.url.path}: expected {code}, observed {response.status_code}'
    return response.json() if response.content else None


async def retained_task(database_url, owner_id):
    """A retained pending task for access checks; never dispatched to research."""
    conn = await asyncpg.connect(database_url)
    session_id = str(uuid4())
    try:
        await conn.execute('''INSERT INTO research_sessions(id,owner_id,user_query,status,final_report)
            VALUES($1::uuid,$2::uuid,'Private account journey fixture','paused','Private retained fixture report')''', session_id, owner_id)
    finally:
        await conn.close()
    return session_id


async def model_scope_journey(database_url, a, b, aid, bid):
    """DB configuration → context → async worker thread, with no paid provider."""
    from app.config import get_settings
    from app.db.connection import close_db, get_db_pool
    from app.model_scope import bind_owner_model, owner_model_execution
    from app.llm_client import get_llm_client_config
    # This is the same dedicated PostgreSQL used by the real HTTP service.
    assert get_settings().database.url == database_url
    await get_db_pool()

    @owner_model_execution
    async def worker(owner, expected):
        await bind_owner_model(owner)
        await asyncio.sleep(0.02)
        config = await asyncio.to_thread(get_llm_client_config)
        assert config['model'] == expected, 'owned model context crossed between workers'
        return config['model']
    try:
        result = await asyncio.gather(worker(aid, 'account-model-a'), worker(bid, 'account-model-b'))
        assert result == ['account-model-a', 'account-model-b']
        # A context copied into a background worker is not modified by B's reset.
        await bind_owner_model(aid)
        expect(b.delete('/api/v1/config/llm'), 200)
        assert get_llm_client_config()['model'] == 'account-model-a'
    finally:
        await close_db()


def journey(base_url, database_url, output):
    assert os.environ.get('MULTIUSER_E2E_DEDICATED') == '1', 'use a dedicated database/service'
    suffix = secrets.token_hex(5)
    credentials = {key: {'username': f'account_{key}_{suffix}', 'password': secrets.token_urlsafe(24)} for key in ('admin', 'a', 'b')}
    output.mkdir(parents=True, exist_ok=True)
    (output/'accounts.private.json').write_text(json.dumps(credentials), encoding='utf-8')
    report = {'scope': 'new multi-user HTTP/PostgreSQL feature only', 'results': [], 'model_provider_calls': 0}
    def recorded(label):
        report['results'].append(label)
        print('PASS:', label, flush=True)
    with httpx.Client(base_url=base_url, timeout=45) as admin, httpx.Client(base_url=base_url, timeout=45) as a, httpx.Client(base_url=base_url, timeout=45) as b:
        # Retry only connection refusal while this dedicated service launches;
        # this is the actual requested initialization, never a health probe.
        for attempt in range(15):
            try:
                initialized = admin.post('/api/v1/auth/initialize', json=credentials['admin'])
                break
            except httpx.ConnectError:
                if attempt == 14:
                    raise
                time.sleep(2)
        setup = expect(initialized, 201)
        admin_id = setup['principal']['id']
        assert setup['principal']['role'] == 'admin'
        aid = expect(a.post('/api/v1/auth/register', json=credentials['a']), 201)['principal']['id']
        bid = expect(b.post('/api/v1/auth/register', json=credentials['b']), 201)['principal']['id']
        assert expect(a.get('/api/v1/auth/me'), 200)['role'] == 'user'
        assert expect(b.get('/api/v1/auth/me'), 200)['role'] == 'user'
        recorded('bootstrap administrator and two ordinary registrations with persistent sessions')

        duplicate = {**credentials['a'], 'username': credentials['a']['username'].upper()}
        expect(b.post('/api/v1/auth/register', json=duplicate), 409)
        expect(b.post('/api/v1/auth/register', json={'username': 'escalation_'+suffix, 'password': secrets.token_urlsafe(20), 'role': 'admin'}), 422)
        expect(b.post('/api/v1/auth/register', json={'username': 'longpass_'+suffix, 'password': '密'*30}), 422)
        expect(b.get('/api/v1/auth/admin/users'), 403)
        expect(b.put('/api/v1/auth/admin/registration', json={'enabled': False}), 403)
        expect(admin.patch('/api/v1/auth/admin/users/'+admin_id, json={'is_active': False}), 409)
        recorded('case-insensitive duplicate, role injection, password byte bound and administrator permissions')

        assert not expect(a.get('/api/v1/config/llm/status'), 200)['is_configured']
        assert expect(a.get('/api/v1/config/llm'), 200)['api_key_masked'] == ''
        expect(a.post('/api/v1/research', json={'query': 'Account isolation fixture question, no provider call expected.'}), 409)
        recorded('new users cannot read or inherit deployment model credentials')
        for client, model in ((a, 'account-model-a'), (b, 'account-model-b')):
            expect(client.post('/api/v1/config/llm', json={'provider':'openai','model':model,'api_key':'fixture-'+secrets.token_hex(15),'api_base':'http://127.0.0.1:1/v1','max_tokens':512}), 200)
        for _ in range(2):
            assert expect(a.get('/api/v1/config/llm'), 200)['model'] == 'account-model-a'
            assert expect(b.get('/api/v1/config/llm'), 200)['model'] == 'account-model-b'
        asyncio.run(model_scope_journey(database_url, a, b, aid, bid))
        assert expect(a.get('/api/v1/config/llm'), 200)['model'] == 'account-model-a'
        assert not expect(b.get('/api/v1/config/llm/status'), 200)['is_configured']
        recorded('interleaved personal configuration, concurrent owned worker contexts and independent reset')

        task = asyncio.run(retained_task(database_url, aid))
        assert expect(a.get('/api/v1/research/'+task), 200)['report'] == 'Private retained fixture report'
        for client in (b, admin):
            for path in (f'/research/{task}', f'/research/status/{task}', f'/research/stream/{task}', f'/research/{task}/reports', f'/research/{task}/evidence/unknown'):
                expect(client.get('/api/v1'+path), 404)
        recorded('retained task, report, status, event stream and evidence are owner-only even for administrators')

        source = expect(a.post('/api/v1/documents/sources', json={'name':'Private fixture material','group_name':'private-account-fixture','content':'Private fixture material for account separation. The source belongs to exactly one researcher.','index_policy':{'mode':'lexical'}}), 200)
        source_id = source.get('source_id') or source.get('id')
        assert source_id
        assert any(row['id'] == source_id for row in expect(a.get('/api/v1/documents/sources'), 200)['items'])
        for client in (b, admin):
            assert all(row['id'] != source_id for row in expect(client.get('/api/v1/documents/sources'), 200)['items'])
            expect(client.get(f'/api/v1/documents/sources/{source_id}/parsing'), 404)
            expect(client.put(f'/api/v1/documents/sources/{source_id}', json={'name':'not permitted'}), 404)
            assert expect(client.get('/api/v1/documents/chunks', params={'source_id':source_id}), 200)['items'] == []
        recorded('private source ingestion, lists, retained parsing, editing and chunk access')

        markdown = '---\nname: Account fixture\nslug: shared-account-fixture\ndescription: Private research method\nversion: 1\n---\n# Overview\nUse only the current owner sources.\n'
        sa = expect(a.post('/api/v1/skills', json={'markdown_content':markdown}), 200)
        sb = expect(b.post('/api/v1/skills', json={'markdown_content':markdown}), 200)
        assert sa['id'] != sb['id']
        expect(b.get('/api/v1/skills/'+sa['id']), 404)
        expect(admin.get('/api/v1/skills/'+sa['id']), 404)
        recorded('same-named skills have independent identifiers and inaccessible foreign content')

        template = expect(a.post('/api/v1/research/delivery-templates', json={'request_id':str(uuid4()),'name':'Private account template','configuration':{}}), 201)
        for client in (b, admin):
            expect(client.get('/api/v1/research/delivery-templates/'+template['template_id']), 404)
        expect(a.put('/api/v1/channels/web/config', json={'enabled':False}), 200)
        channels_a = expect(a.get('/api/v1/channels'), 200)['items']
        channels_b = expect(b.get('/api/v1/channels'), 200)['items']
        assert not next(row for row in channels_a if row['name']=='web')['config']['enabled']
        assert next(row for row in channels_b if row['name']=='web')['config']['enabled']
        recorded('report templates and channel preferences remain private')
        expect(b.put('/api/v1/channels/github/config', json={'backends':['gh']}), 200)
        denied = expect(b.post('/api/v1/channels/collect', json={'channel':'github','query':'research account fixture','operation':'search'}), 200)
        assert not denied['items'] and any(item.get('error_category') == 'administrator_required' for item in denied['attempts'])
        recorded('ordinary users cannot reuse deployment CLI/browser authentication')

        expect(admin.put('/api/v1/auth/admin/registration', json={'enabled':False}), 200)
        assert not expect(b.get('/api/v1/auth/status'), 200)['registration_enabled']
        expect(b.post('/api/v1/auth/register', json={'username':'closed_'+suffix,'password':secrets.token_urlsafe(24)}), 403)
        expect(admin.put('/api/v1/auth/admin/registration', json={'enabled':True}), 200)
        token = expect(b.post('/api/v1/auth/tokens', json={'label':'account feature fixture'}), 201)['token']
        expect(admin.patch('/api/v1/auth/admin/users/'+bid, json={'is_active':False}), 200)
        expect(b.get('/api/v1/auth/me'), 401)
        expect(b.post('/api/v1/auth/login', json=credentials['b']), 401)
        expect(b.get('/api/v1/auth/me', headers={'Authorization':'Bearer '+token}), 401)
        expect(admin.patch('/api/v1/auth/admin/users/'+bid, json={'is_active':True}), 200)
        expect(b.post('/api/v1/auth/login', json=credentials['b']), 200)
        recorded('registration switch, disabled-account login denial and revocation of sessions and API tokens')

        expect(admin.patch('/api/v1/auth/admin/users/'+bid, json={'role':'admin'}), 200)
        expect(b.get('/api/v1/auth/me'), 401)
        expect(b.post('/api/v1/auth/login', json=credentials['b']), 200)
        assert expect(b.get('/api/v1/auth/me'), 200)['role'] == 'admin'
        expect(b.get('/api/v1/auth/admin/users'), 200)
        expect(b.get('/api/v1/research/'+task), 404)
        expect(admin.patch('/api/v1/auth/admin/users/'+bid, json={'role':'user'}), 200)
        expect(b.post('/api/v1/auth/login', json=credentials['b']), 200)
        expect(b.get('/api/v1/auth/admin/users'), 403)
        expect(a.post('/api/v1/auth/logout'), 204)
        expect(a.get('/api/v1/auth/me'), 401)
        expect(a.post('/api/v1/auth/login', json=credentials['a']), 200)
        assert expect(a.get('/api/v1/research/'+task), 200)['report'] == 'Private retained fixture report'
        assert expect(a.get('/api/v1/config/llm'), 200)['model'] == 'account-model-a'
        recorded('role changes revoke old sessions; promotion grants management only; logout/relogin preserves personal data')
    output.mkdir(parents=True, exist_ok=True)
    (output/'accounts.private.json').write_text(json.dumps(credentials), encoding='utf-8')
    (output/'results.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Multi-user feature journey complete; no paid model calls.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    journey(args.base_url, os.environ['DATABASE_URL'], args.output)
