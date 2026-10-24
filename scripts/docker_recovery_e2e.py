"""Windows taskbar launch -> Docker -> published PostgreSQL evidence round trip.

This scenario stops Desktop gracefully and resumes only the two ADRS local
acceptance containers. It never deletes Docker data or starts other projects.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

import asyncpg

ROOT = Path('.codex-homework/docker-startup-20261021')
DB = os.environ["ADRS_E2E_DATABASE_URL"]
SESSION = '871eae63-4ece-4832-a8e5-6885bc32593f'
SNAPSHOT = 'f994b0c0-a866-490e-939d-3945b4b5b853'
CONTAINERS = ['adrs-organization-e2e-20261020', 'adrs-organization-redis-20261020']
LINK = Path(os.environ['APPDATA']) / 'Microsoft/Internet Explorer/Quick Launch/User Pinned/TaskBar/Docker Desktop.lnk'
LOGS = Path(os.environ['LOCALAPPDATA']) / 'Docker/log/host'


def run(*args, timeout=70):
    return subprocess.run(args, text=True, encoding='utf-8', errors='replace', capture_output=True, timeout=timeout)


async def evidence(connection):
    report = await connection.fetchval('SELECT final_report FROM research_sessions WHERE id=$1::uuid', SESSION)
    snapshot = await connection.fetchval('SELECT payload FROM research_matching_snapshots WHERE id=$1::uuid', SNAPSHOT)
    assert report and snapshot, 'Actual saved research and matching evidence must be available'
    return {'report': report, 'snapshot': json.loads(snapshot) if isinstance(snapshot, str) else snapshot}


def restart_through_taskbar():
    stopped = run('docker', 'desktop', 'stop', '--timeout', '60')
    assert stopped.returncode == 0, stopped.stderr
    print('Desktop stopped gracefully; launching the actual pinned shortcut', flush=True)
    started_at = time.time()
    # Keep the shortcut path out of PowerShell source, including paths with spaces.
    env = dict(os.environ, ADRS_DOCKER_SHORTCUT=str(LINK))
    launch = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                             'Start-Process -FilePath $env:ADRS_DOCKER_SHORTCUT -WindowStyle Hidden'],
                            env=env, text=True, encoding='utf-8', errors='replace', capture_output=True, timeout=20)
    assert launch.returncode == 0, launch.stderr
    deadline = time.monotonic() + 150
    failure = ''
    while time.monotonic() < deadline:
        try:
            resumed = run('docker', 'start', *CONTAINERS, timeout=20)
            if resumed.returncode == 0:
                return
            failure = resumed.stderr[-800:]
        except subprocess.TimeoutExpired:
            failure = 'The pending container resume operation timed out'
        for path in LOGS.glob('com.docker.backend.exe.log*'):
            if path.stat().st_mtime < started_at:
                continue
            # Inspect only current-attempt fatal evidence, not historic errors.
            cutoff = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(started_at))
            for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
                if line.startswith('[') and line[1:20] >= cutoff and 'backend crashed' in line:
                    raise AssertionError('Pinned launch aborted before evidence could be read: ' + line[:900])
        time.sleep(2)
    raise AssertionError('Evidence workload could not resume after pinned launch: ' + failure)


async def main(phase, cycles, resume):
    ROOT.mkdir(parents=True, exist_ok=True)
    state_path = ROOT / 'before.json'
    if phase == 'baseline' and not resume:
        conn = await asyncpg.connect(DB)
        try:
            saved = await evidence(conn)
            saved['run_id'] = str(uuid.uuid4())
            await conn.execute('''CREATE TABLE IF NOT EXISTS docker_recovery_evidence (
                id uuid PRIMARY KEY, evidence jsonb NOT NULL, restart_count integer NOT NULL DEFAULT 0)''')
            await conn.execute('INSERT INTO docker_recovery_evidence(id,evidence) VALUES($1::uuid,$2::jsonb)',
                               saved['run_id'], json.dumps({'source_session': SESSION, 'snapshot_id': SNAPSHOT,
                                                          'decision': 'preserve committed research across restart'}))
            state_path.write_text(json.dumps(saved, ensure_ascii=False), encoding='utf-8')
        finally:
            await conn.close()
    else:
        saved = json.loads(state_path.read_text(encoding='utf-8'))
    for cycle in range(1, cycles + 1):
        restart_through_taskbar()
        conn = None
        for attempt in range(45):
            try:
                conn = await asyncpg.connect(DB, timeout=5)
                actual = await evidence(conn)
                break
            except (OSError, asyncpg.CannotConnectNowError, asyncpg.ConnectionDoesNotExistError):
                if conn:
                    await conn.close()
                await asyncio.sleep(2)
        else:
            raise AssertionError('Actual evidence transaction unavailable after Docker restart')
        try:
            assert actual['report'] == saved['report'], 'Saved report changed across Docker restart'
            assert actual['snapshot'] == saved['snapshot'], 'Saved matching evidence changed across Docker restart'
            async with conn.transaction():
                row = await conn.fetchrow('''UPDATE docker_recovery_evidence
                    SET restart_count=restart_count+1 WHERE id=$1::uuid RETURNING evidence,restart_count''', saved['run_id'])
                assert row and json.loads(row['evidence'])['snapshot_id'] == SNAPSHOT
            committed = await conn.fetchval('SELECT restart_count FROM docker_recovery_evidence WHERE id=$1::uuid', saved['run_id'])
            assert committed == cycle, (committed, cycle)
            print(f'PASS cycle {cycle}: pinned launch, original report/snapshot, committed evidence update {committed}', flush=True)
        finally:
            await conn.close()
    (ROOT / (phase + '-result.json')).write_text(json.dumps({'phase': phase, 'cycles': cycles,
        'run_id': saved['run_id'], 'source_session': SESSION, 'snapshot_id': SNAPSHOT,
        'result': 'passed'}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['baseline', 'verify'], required=True)
    parser.add_argument('--cycles', type=int, default=1)
    parser.add_argument('--resume', action='store_true', help='Retain the already committed baseline evidence')
    args = parser.parse_args()
    asyncio.run(main(args.phase, args.cycles, args.resume))
