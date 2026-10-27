"""Single-use email challenges; only a mail adapter receives raw tokens."""
from __future__ import annotations

import asyncio
import re

import asyncpg

from app.db.connection import get_db_pool
from app.security.auth import Principal, hash_password, new_secret, token_hash, verify_password

EMAIL_RE = re.compile(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", re.I)
CHALLENGE_MINUTES = 30


def normalize_email(value: str) -> str:
    address = value.strip().lower()
    if (len(address) > 254 or not EMAIL_RE.fullmatch(address) or '..' in address
            or len(address.split('@', 1)[0]) > 64):
        raise ValueError('email_invalid')
    return address


async def _require_current_credential(conn, principal: Principal):
    if principal.auth_type not in {'session', 'api_token'} or not principal.credential_hash:
        raise ValueError('email_authentication_required')
    table = 'auth_sessions' if principal.auth_type == 'session' else 'auth_api_tokens'
    valid = await conn.fetchval(f'''SELECT t.token_hash FROM {table} t
        JOIN auth_principals p ON p.id=t.principal_id
        WHERE p.id=$1::uuid AND p.is_active=TRUE AND t.token_hash=$2 AND t.revoked_at IS NULL
        AND t.session_version=p.session_version AND (t.expires_at IS NULL OR t.expires_at>NOW())
        FOR SHARE OF t''',
        principal.id, principal.credential_hash)
    if not valid: raise ValueError('email_authentication_required')


async def current_email(principal_id: str):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT address,verified_at FROM auth_verified_emails WHERE principal_id=$1::uuid', principal_id)
    return None if not row else {'address': row['address'], 'verified_at': row['verified_at'].isoformat()}


async def issue_verification(principal: Principal, email: str, current_password: str):
    """Require the current password and recheck the credential under the account lock."""
    address = normalize_email(email)
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        old_hash = await conn.fetchval('SELECT password_hash FROM auth_principals WHERE id=$1::uuid AND is_active=TRUE', principal.id)
    if not old_hash or not await asyncio.to_thread(verify_password, current_password, old_hash):
        raise ValueError('invalid_credentials')
    token = new_secret('verify')
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow('SELECT password_hash,is_active FROM auth_principals WHERE id=$1::uuid FOR UPDATE', principal.id)
        if not row or not row['is_active'] or row['password_hash'] != old_hash:
            raise ValueError('email_authentication_required')
        await _require_current_credential(conn, principal)
        await conn.execute('''UPDATE auth_email_challenges SET consumed_at=NOW()
            WHERE principal_id=$1::uuid AND kind='verify' AND consumed_at IS NULL''', principal.id)
        await conn.execute('''INSERT INTO auth_email_challenges(principal_id,address,kind,token_hash,expires_at)
            VALUES($1::uuid,$2,'verify',$3,NOW()+($4::int * INTERVAL '1 minute'))''',
            principal.id,address,token_hash(token),CHALLENGE_MINUTES)
    return {'address': address, 'token': token, 'kind': 'verify'}


async def verify_email(principal: Principal, token: str):
    pool = await get_db_pool()
    try:
        async with pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow('SELECT is_active FROM auth_principals WHERE id=$1::uuid FOR UPDATE', principal.id)
            if not row or not row['is_active']: raise ValueError('email_authentication_required')
            await _require_current_credential(conn, principal)
            challenge = await conn.fetchrow('''SELECT id,address FROM auth_email_challenges
                WHERE principal_id=$1::uuid AND token_hash=$2 AND kind='verify'
                AND consumed_at IS NULL AND expires_at>NOW() FOR UPDATE''', principal.id,token_hash(token))
            if not challenge: raise ValueError('email_challenge_invalid')
            await conn.execute('''INSERT INTO auth_verified_emails(principal_id,address,verified_at,updated_at)
                VALUES($1::uuid,$2,NOW(),NOW()) ON CONFLICT(principal_id) DO UPDATE
                SET address=EXCLUDED.address,verified_at=NOW(),updated_at=NOW()''', principal.id,challenge['address'])
            await conn.execute('UPDATE auth_email_challenges SET consumed_at=NOW() WHERE id=$1', challenge['id'])
            # A pending reset for the former address cannot outlive a change.
            await conn.execute("UPDATE auth_email_challenges SET consumed_at=NOW() WHERE principal_id=$1::uuid AND kind='reset' AND consumed_at IS NULL", principal.id)
    except asyncpg.UniqueViolationError:
        raise ValueError('email_unavailable') from None
    return {'address': challenge['address']}


async def issue_reset(email: str):
    """Return a mail-only challenge or None; callers must use a uniform response."""
    address = normalize_email(email)
    pool = await get_db_pool()
    token = new_secret('reset')
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow('''SELECT p.id FROM auth_verified_emails e
            JOIN auth_principals p ON p.id=e.principal_id
            WHERE e.address=$1 AND p.is_active=TRUE FOR UPDATE OF p''', address)
        if not row: return None
        await conn.execute("UPDATE auth_email_challenges SET consumed_at=NOW() WHERE principal_id=$1 AND kind='reset' AND consumed_at IS NULL", row['id'])
        await conn.execute('''INSERT INTO auth_email_challenges(principal_id,address,kind,token_hash,expires_at)
            VALUES($1,$2,'reset',$3,NOW()+($4::int * INTERVAL '1 minute'))''',
            row['id'],address,token_hash(token),CHALLENGE_MINUTES)
    return {'address': address, 'token': token, 'kind': 'reset'}


async def reset_password(token: str, new_password: str):
    encoded = await asyncio.to_thread(hash_password, new_password)
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
        # Lock principal before challenge: the same order is used by verification.
        principal_id = await conn.fetchval('''SELECT principal_id FROM auth_email_challenges
            WHERE token_hash=$1 AND kind='reset' AND consumed_at IS NULL AND expires_at>NOW()''', token_hash(token))
        if not principal_id: raise ValueError('email_challenge_invalid')
        principal = await conn.fetchrow('SELECT is_active FROM auth_principals WHERE id=$1 FOR UPDATE', principal_id)
        if not principal or not principal['is_active']: raise ValueError('email_challenge_invalid')
        challenge = await conn.fetchrow('''SELECT c.id FROM auth_email_challenges c
            JOIN auth_verified_emails e ON e.principal_id=c.principal_id AND e.address=c.address
            WHERE c.principal_id=$1 AND c.token_hash=$2 AND c.kind='reset'
            AND c.consumed_at IS NULL AND c.expires_at>NOW() FOR UPDATE OF c''', principal_id,token_hash(token))
        if not challenge: raise ValueError('email_challenge_invalid')
        await conn.execute('''UPDATE auth_principals SET password_hash=$2,session_version=session_version+1,updated_at=NOW()
            WHERE id=$1''', principal_id,encoded)
        await conn.execute('UPDATE auth_sessions SET revoked_at=NOW() WHERE principal_id=$1 AND revoked_at IS NULL', principal_id)
        await conn.execute('UPDATE auth_api_tokens SET revoked_at=NOW() WHERE principal_id=$1 AND revoked_at IS NULL', principal_id)
        await conn.execute('UPDATE auth_email_challenges SET consumed_at=NOW() WHERE principal_id=$1 AND consumed_at IS NULL', principal_id)
    return {'status': 'password_changed_all_credentials_revoked'}
