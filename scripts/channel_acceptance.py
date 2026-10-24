"""Collect real public sources through authenticated HTTP APIs; never mock upstreams.

Use a separate local database/API and account file. Credentials and content excerpts
are deliberately separated from the shareable report. No health probes are used.
"""
from __future__ import annotations

import argparse
import json
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx


def run(base_url: str, account_file: Path, report_file: Path, initialize: bool) -> int:
    try:
        account = json.loads(account_file.read_text(encoding='utf-8'))
    except FileNotFoundError:
        if not initialize:
            raise ValueError('Supply an existing account file, or initialize a separate test database') from None
        account = {'username': 'channel_test', 'password': secrets.token_urlsafe(24)}
        account_file.parent.mkdir(parents=True, exist_ok=True)
        account_file.write_text(json.dumps(account), encoding='utf-8')
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'base_url': base_url,
              'username': account['username'], 'checks': [], 'collections': []}

    def check(name, condition):
        report['checks'].append({'name': name, 'passed': bool(condition)})
        if not condition:
            raise AssertionError(name)

    with httpx.Client(base_url=base_url, timeout=100, trust_env=False) as client:
        # Retry the actual login request while the dedicated API is starting.
        deadline = time.monotonic() + 45
        while True:
            try:
                login = client.post('/api/v1/auth/login', json=account)
                break
            except httpx.ConnectError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(.5)
        if login.status_code == 401 and initialize:
            created = client.post('/api/v1/auth/initialize', json=account)
            check('test_account_created', created.status_code == 201)
            client.post('/api/v1/auth/logout')
            login = client.post('/api/v1/auth/login', json=account)
        check('password_login', login.status_code == 200)
        owner = login.json()['principal']['id']
        report['owner_id'] = owner
        check('authenticated_identity', client.get('/api/v1/auth/me').json().get('id') == owner)
        with httpx.Client(base_url=base_url, timeout=20, trust_env=False) as anonymous:
            denied = anonymous.post('/api/v1/channels/collect', json={'channel': 'github', 'query': 'langgraph'})
            check('anonymous_collection_rejected', denied.status_code == 401)
            denied = anonymous.post('/api/v1/auth/login', json={**account, 'password': 'incorrect-test-password'})
            check('incorrect_password_rejected', denied.status_code == 401)
        catalog = client.get('/api/v1/channels').json()['items']
        report['channels'] = [item['name'] for item in catalog]
        before = client.get('/api/v1/channels/history').json()['items']
        for channel, config in (
            ('github', {'backends': ['github-api', 'gh'], 'timeout_seconds': 30}),
            ('rss', {'feeds': ['https://hnrss.org/newest?count=5'], 'timeout_seconds': 30}),
            ('web', {'backends': ['duckduckgo', 'bing-rss', 'exa-mcp', 'jina'], 'timeout_seconds': 45}),
            ('bilibili', {'backends': ['bili', 'opencli', 'bilibili-api'], 'timeout_seconds': 45}),
            ('xiaoyuzhou', {'backends': ['xiaoyuzhou-page', 'jina'], 'timeout_seconds': 30}),
            ('exa', {'timeout_seconds': 45}),
            ('youtube', {'timeout_seconds': 60}),
        ):
            response = client.put(f'/api/v1/channels/{channel}/config', json=config)
            check('save_' + channel, response.status_code == 200)
        updated = client.get('/api/v1/channels').json()['items']
        github_config = next(c['config'] for c in updated if c['name'] == 'github')
        check('priority_persisted', github_config['backends'] == ['github-api', 'gh'])

        cases = [
            ('github', 'read', 'https://github.com/Panniantong/Agent-Reach', True),
            ('github', 'search', 'LangGraph', True),
            ('v2ex', 'read', 'https://www.v2ex.com/t/1000000', True),
            ('rss', 'read', 'https://hnrss.org/newest?count=5', True),
            ('rss', 'search', 'a', True),
            ('web', 'search', 'LangGraph', True),
            ('web', 'read', 'https://example.com', False),
            ('bilibili', 'search', 'LangGraph', True),
            ('youtube', 'search', 'Python tutorial', True),
            ('exa', 'search', 'LangGraph', True),
            ('twitter', 'search', 'LangGraph', False),
            ('reddit', 'search', 'LangGraph', False),
            ('xiaohongshu', 'search', '人工智能', False),
            ('facebook', 'search', 'Python', False),
            ('instagram', 'search', 'python', False),
            ('linkedin', 'search', 'Python engineer', False),
            ('boss', 'search', 'Python', False),
            ('xueqiu', 'search', 'AAPL', False),
            ('xiaoyuzhou', 'read', 'https://www.xiaoyuzhoufm.com/podcast/6022a180ef5fdaddc30bb101', True),
            ('xiaoyuzhou', 'read', 'https://www.xiaoyuzhoufm.com/episode/6ac65b91e742e36efcbf66c8', True),
            ('xiaoyuzhou', 'read', 'https://www.xiaoyuzhoufm.com/podcast/5e280fb1418a84a0461f6183', False),
        ]
        required_failures = []
        for channel, operation, query, required in cases:
            started = time.monotonic()
            response = client.post('/api/v1/channels/collect', json={
                'channel': channel, 'operation': operation, 'query': query, 'limit': 5, 'max_chars': 8000,
            })
            check(f'{channel}_{operation}_structured_response', response.status_code == 200)
            result = response.json()
            record = {'channel': channel, 'operation': operation, 'query': query, 'required': required,
                      'status': result['status'], 'call_count': result['call_count'],
                      'duration_ms': round((time.monotonic() - started) * 1000),
                      'attempts': result['attempts'], 'items': []}
            for item in result['items']:
                check(f'{channel}_{operation}_content_has_source', bool(item['content'].strip()) and item['url'].startswith('https://') and item['channel'] == channel)
                record['items'].append({'url': item['url'], 'title': item['title'], 'backend': item['backend'],
                                        'collected_at': item['collected_at'], 'content_chars': len(item['content']),
                                        'excerpt': item['content'][:100]})
            if required and (result['status'] != 'success' or not result['items']):
                required_failures.append(channel + '/' + operation)
            if query == 'https://www.xiaoyuzhoufm.com/podcast/5e280fb1418a84a0461f6183':
                check('removed_podcast_is_not_evidence', result['status'] == 'failed' and not result['items'] and result['attempts'][-1]['error_category'] == 'not_found')
            report['collections'].append(record)
            print(json.dumps({'channel': channel, 'operation': operation, 'status': result['status'],
                              'items': len(result['items']), 'errors': [a['error_category'] for a in result['attempts'] if a['error_category']]}, ensure_ascii=False), flush=True)

        history = client.get('/api/v1/channels/history').json()['items']
        attempts = [a for row in report['collections'] for a in row['attempts']]
        check('all_attempts_persisted', len(history) == min(100, len(before) + len(attempts)))
        check('history_matches_latest_collection', history[-1]['channel'] == cases[-1][0] and history[-1]['status'] == attempts[-1]['status'])
        check('history_excludes_queries_and_credentials', all('query' not in h and 'password' not in h and 'token' not in h for h in history))
        client.post('/api/v1/auth/logout')
        check('logout_revokes_session', client.get('/api/v1/channels/history').status_code == 401)
        report['required_failures'] = required_failures
        report['completed_at'] = datetime.now(timezone.utc).isoformat()
        report['history_records'] = len(history)
        report_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        return 1 if required_failures else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--account-file', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--initialize', action='store_true', help='Only for a dedicated empty local test database')
    args = parser.parse_args()
    raise SystemExit(run(args.base_url, args.account_file, args.report, args.initialize))
