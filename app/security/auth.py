"""Account authentication and explicit role checks backed by PostgreSQL."""

from __future__ import annotations

import hashlib
import secrets
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import bcrypt
import asyncpg
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.db.connection import get_db_pool

bearer_scheme = HTTPBearer(auto_error=False)
credentials_dependency = Depends(bearer_scheme)
RESERVED_USERNAMES = {"admin", "root", "system", "support", "api", "anonymous"}


@dataclass(frozen=True)
class Principal:
    id: str
    username: str
    auth_type: str
    credential_hash: str | None = field(default=None, repr=False, compare=False)
    role: str = "user"


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("password must be at least 12 characters")
    if len(password.encode('utf-8')) > 72:
        raise ValueError('password must not exceed 72 UTF-8 bytes')
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, encoded: str) -> bool:
    if len(password.encode('utf-8')) > 72:
        return False
    return bcrypt.checkpw(password.encode("utf-8"), encoded.encode("utf-8"))


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_secret(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


async def is_initialized() -> bool:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        return bool(await conn.fetchval("SELECT EXISTS(SELECT 1 FROM auth_principals)"))


async def bootstrap_admin(username: str, password: str) -> Principal:
    normalized = normalize_username(username)
    encoded = hash_password(password)
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
            # Serializes first initialization across processes.
            await conn.execute("SELECT pg_advisory_xact_lock(73120401)")
            if await conn.fetchval("SELECT EXISTS(SELECT 1 FROM auth_principals)"):
                raise RuntimeError("administrator already initialized")
            row = await conn.fetchrow(
                """INSERT INTO auth_principals (username, password_hash, role)
                   VALUES ($1, $2, 'admin') RETURNING id, username""",
                normalized,
                encoded,
            )
            owner_id = row["id"]
            for table in ("documents", "document_sources", "research_sessions", "tool_call_audit", "approval_requests", "system_config", "skill_meta"):
                await conn.execute(f"UPDATE {table} SET owner_id = $1 WHERE owner_id IS NULL", owner_id)
    return Principal(id=str(row["id"]), username=row["username"], auth_type="bootstrap", role='admin')


def normalize_username(username: str) -> str:
    normalized = username.strip().lower()
    if not re.fullmatch(r'[a-z0-9_.-]{3,120}', normalized) or normalized in RESERVED_USERNAMES:
        raise ValueError('username_invalid_or_reserved')
    return normalized


async def registration_enabled() -> bool:
    if not get_settings().security.auth_enabled or not get_settings().security.registration_enabled:
        return False
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        return bool(await conn.fetchval('SELECT enabled FROM auth_registration_policy WHERE singleton=TRUE'))


async def register_user(username: str, password: str) -> Principal:
    normalized = normalize_username(username)
    encoded = hash_password(password)
    pool = await get_db_pool()
    try:
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute('SELECT pg_advisory_xact_lock(73120401)')
            if not await conn.fetchval('SELECT EXISTS(SELECT 1 FROM auth_principals)'):
                raise HTTPException(409, 'administrator_setup_required')
            enabled = await conn.fetchval('SELECT enabled FROM auth_registration_policy WHERE singleton=TRUE')
            if not get_settings().security.auth_enabled or not get_settings().security.registration_enabled or not enabled:
                raise HTTPException(403, 'registration_closed')
            row = await conn.fetchrow("""INSERT INTO auth_principals(username,password_hash,role)
                VALUES($1,$2,'user') RETURNING id,username""", normalized, encoded)
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, 'username_unavailable') from None
    return Principal(id=str(row['id']), username=row['username'], auth_type='session', role='user')


async def create_session(principal: Principal) -> tuple[str, datetime]:
    token = new_secret("ds")
    expires_at = (datetime.now(UTC) + timedelta(seconds=get_settings().security.session_ttl_seconds)).replace(tzinfo=None)
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        version = await conn.fetchval("SELECT session_version FROM auth_principals WHERE id = $1::uuid", principal.id)
        await conn.execute(
            """INSERT INTO auth_sessions (principal_id, token_hash, session_version, expires_at)
               VALUES ($1::uuid, $2, $3, $4)""",
            principal.id, token_hash(token), version, expires_at,
        )
    return token, expires_at


async def authenticate_password(username: str, password: str) -> Principal | None:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, username, password_hash, role FROM auth_principals WHERE username = $1 AND is_active = TRUE",
            username.strip().lower(),
        )
    if not row or not verify_password(password, row["password_hash"]):
        return None
    return Principal(id=str(row["id"]), username=row["username"], auth_type="session", role=row['role'])


async def _principal_from_token(raw_token: str, kind: str) -> Principal | None:
    table = "auth_api_tokens" if kind == "api_token" else "auth_sessions"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""SELECT p.id, p.username, p.role
                 FROM {table} t JOIN auth_principals p ON p.id = t.principal_id
                 WHERE t.token_hash = $1 AND t.revoked_at IS NULL AND p.is_active = TRUE
                   AND t.session_version = p.session_version
                   AND (t.expires_at IS NULL OR t.expires_at > NOW())""",
            token_hash(raw_token),
        )
        if row:
            await conn.execute(f"UPDATE {table} SET last_used_at = NOW() WHERE token_hash = $1", token_hash(raw_token))
    return Principal(id=str(row["id"]), username=row["username"], auth_type=kind, credential_hash=token_hash(raw_token), role=row['role']) if row else None


async def stream_principal_valid(principal: Principal, session_id: str,*,execution_id=None,enforce_execution=False) -> bool:
    """Revalidate the original credential and ownership at the event boundary."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        if principal.auth_type == "disabled":
            if get_settings().security.auth_enabled:
                return False
            return bool(await conn.fetchval(
                """SELECT EXISTS(SELECT 1 FROM research_sessions WHERE id=$1::uuid AND owner_id=$2::uuid
                    AND ($3::boolean=FALSE OR execution_id IS NOT DISTINCT FROM $4::uuid))""",
                session_id, principal.id,enforce_execution,execution_id,
            ))
        if principal.auth_type not in {"session", "api_token"} or not principal.credential_hash:
            return False
        table = "auth_api_tokens" if principal.auth_type == "api_token" else "auth_sessions"
        return bool(await conn.fetchval(
            f"""SELECT EXISTS(
                SELECT 1 FROM {table} t
                JOIN auth_principals p ON p.id = t.principal_id
                JOIN research_sessions s ON s.owner_id = p.id
                WHERE t.token_hash = $1 AND p.id = $2::uuid AND s.id = $3::uuid
                  AND t.revoked_at IS NULL AND p.is_active = TRUE
                  AND t.session_version = p.session_version
                  AND (t.expires_at IS NULL OR t.expires_at > NOW())
                  AND ($4::boolean=FALSE OR s.execution_id IS NOT DISTINCT FROM $5::uuid)
            )""", principal.credential_hash, principal.id, session_id,enforce_execution,execution_id,
        ))


async def get_principal(request: Request, credentials: HTTPAuthorizationCredentials | None = credentials_dependency) -> Principal:
    if not get_settings().security.auth_enabled:
        principal = Principal(id="00000000-0000-0000-0000-000000000000", username="local", auth_type="disabled", role='admin')
        from app.model_scope import set_model_identity
        set_model_identity(principal.id, principal.role)
        request.state.principal = principal
        return principal
    raw = credentials.credentials if credentials else request.cookies.get(get_settings().security.cookie_name)
    principal = await _principal_from_token(raw, "api_token" if credentials else "session") if raw else None
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication_required", headers={"WWW-Authenticate": "Bearer"})
    request.state.principal = principal
    from app.model_scope import set_model_identity
    set_model_identity(principal.id, principal.role)
    return principal


principal_dependency = Depends(get_principal)


async def require_principal(principal: Principal = principal_dependency) -> Principal:
    return principal


async def require_admin(principal: Principal = principal_dependency) -> Principal:
    if principal.role != 'admin':
        raise HTTPException(403, 'administrator_required')
    return principal


async def revoke_all_sessions(principal_id: str, *, new_password: str | None = None) -> None:
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
            if new_password:
                await conn.execute(
                    "UPDATE auth_principals SET password_hash = $1, session_version = session_version + 1, updated_at = NOW() WHERE id = $2::uuid",
                    hash_password(new_password), principal_id,
                )
            else:
                await conn.execute("UPDATE auth_principals SET session_version = session_version + 1, updated_at = NOW() WHERE id = $1::uuid", principal_id)
            await conn.execute("UPDATE auth_sessions SET revoked_at = NOW() WHERE principal_id = $1::uuid AND revoked_at IS NULL", principal_id)
            await conn.execute("UPDATE auth_api_tokens SET revoked_at = NOW() WHERE principal_id = $1::uuid AND revoked_at IS NULL", principal_id)
