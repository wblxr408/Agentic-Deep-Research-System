"""Registration, session, personal credentials and account administration."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, ConfigDict, field_validator

from app.config import get_settings
from app.db.connection import get_db_pool
from app.security.auth import (
    Principal,
    authenticate_password,
    bootstrap_admin,
    create_session,
    get_principal,
    is_initialized,
    new_secret,
    revoke_all_sessions,
    token_hash,
    register_user,
    registration_enabled,
    require_admin,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
principal_dependency = Depends(get_principal)


class BootstrapRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    username: str = Field(min_length=3, max_length=120, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=256)

    @field_validator('username', mode='before')
    @classmethod
    def trim_username(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('password')
    @classmethod
    def password_bytes(cls, value):
        if len(value.encode('utf-8')) > 72:
            raise ValueError('password must not exceed 72 UTF-8 bytes')
        return value


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=256)


class TokenCreateRequest(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    expires_in_days: int | None = Field(default=None, ge=1, le=365)


@router.get("/status")
async def auth_status():
    return {"initialized": await is_initialized(), "auth_enabled": get_settings().security.auth_enabled,
            "registration_enabled": await registration_enabled()}


def _set_session_cookie(response: Response, token: str, expires_at: datetime) -> None:
    settings = get_settings().security
    response.set_cookie(
        settings.cookie_name,
        token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="strict",
        max_age=settings.session_ttl_seconds,
        path="/",
    )


@router.post("/initialize", status_code=status.HTTP_201_CREATED)
async def initialize(payload: BootstrapRequest, response: Response):
    if await is_initialized():
        raise HTTPException(status_code=409, detail="administrator_already_initialized")
    try:
        principal = await bootstrap_admin(payload.username, payload.password)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400 if isinstance(exc, ValueError) else 409, detail=str(exc)) from exc
    token, expires_at = await create_session(principal)
    _set_session_cookie(response, token, expires_at)
    return {"principal": {"id": principal.id, "username": principal.username, "role": principal.role}, "expires_at": expires_at.isoformat()}


@router.post('/register', status_code=status.HTTP_201_CREATED)
async def register(payload: BootstrapRequest, response: Response):
    try:
        principal = await register_user(payload.username, payload.password)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    token, expires_at = await create_session(principal)
    _set_session_cookie(response, token, expires_at)
    return {'principal': {'id': principal.id, 'username': principal.username, 'role': principal.role},
            'expires_at': expires_at.isoformat()}


@router.post("/login")
async def login(payload: LoginRequest, response: Response):
    principal = await authenticate_password(payload.username, payload.password)
    if principal is None:
        raise HTTPException(status_code=401, detail="invalid_credentials")
    token, expires_at = await create_session(principal)
    _set_session_cookie(response, token, expires_at)
    return {"principal": {"id": principal.id, "username": principal.username, "role": principal.role}, "expires_at": expires_at.isoformat()}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response, principal: Principal = principal_dependency):
    raw = request.cookies.get(get_settings().security.cookie_name)
    if raw:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE auth_sessions SET revoked_at = NOW() WHERE token_hash = $1", token_hash(raw))
    response.delete_cookie(get_settings().security.cookie_name, path="/")


@router.get("/me")
async def me(principal: Principal = principal_dependency):
    return {"id": principal.id, "username": principal.username, "auth_type": principal.auth_type, 'role': principal.role}


@router.post("/password")
async def change_password(payload: PasswordChangeRequest, principal: Principal = principal_dependency):
    current = await authenticate_password(principal.username, payload.current_password)
    if current is None:
        raise HTTPException(status_code=401, detail="invalid_credentials")
    try:
        await revoke_all_sessions(principal.id, new_password=payload.new_password)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return {"status": "password_changed_all_credentials_revoked"}


@router.post("/tokens", status_code=status.HTTP_201_CREATED)
async def create_api_token(payload: TokenCreateRequest, principal: Principal = principal_dependency):
    from datetime import timedelta
    token = new_secret("di")
    expires_at = (datetime.now(UTC) + timedelta(days=payload.expires_in_days)).replace(tzinfo=None) if payload.expires_in_days else None
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        version = await conn.fetchval("SELECT session_version FROM auth_principals WHERE id = $1::uuid", principal.id)
        row = await conn.fetchrow(
            """INSERT INTO auth_api_tokens (principal_id, token_hash, token_prefix, label, session_version, expires_at)
               VALUES ($1::uuid, $2, $3, $4, $5, $6) RETURNING id""",
            principal.id, token_hash(token), token[:12], payload.label, version, expires_at,
        )
    return {"id": str(row["id"]), "label": payload.label, "token": token, "expires_at": expires_at.isoformat() if expires_at else None}


@router.get("/tokens")
async def list_api_tokens(principal: Principal = principal_dependency):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, token_prefix, label, expires_at, revoked_at, created_at, last_used_at
               FROM auth_api_tokens WHERE principal_id = $1::uuid ORDER BY created_at DESC""", principal.id,
        )
    return {"items": [{**dict(row), "id": str(row["id"])} for row in rows]}


@router.delete("/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_token(token_id: str, principal: Principal = principal_dependency):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE auth_api_tokens SET revoked_at = NOW() WHERE id = $1::uuid AND principal_id = $2::uuid AND revoked_at IS NULL",
            token_id, principal.id,
        )
    if result.endswith("0"):
        raise HTTPException(status_code=404, detail="token_not_found")


class RegistrationPolicy(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = Field(strict=True)


class AccountUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['user', 'admin'] | None = None
    is_active: bool | None = Field(default=None, strict=True)


AdminDep = Depends(require_admin)


@router.get('/admin/registration')
async def get_registration_policy(principal: Principal = AdminDep):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        enabled = bool(await conn.fetchval('SELECT enabled FROM auth_registration_policy WHERE singleton=TRUE'))
    return {'enabled': enabled, 'deployment_enabled': get_settings().security.registration_enabled,
            'effective_enabled': await registration_enabled()}


@router.put('/admin/registration')
async def set_registration_policy(payload: RegistrationPolicy, principal: Principal = AdminDep):
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute('SELECT pg_advisory_xact_lock(73120401)')
        actor = await conn.fetchrow('SELECT role,is_active FROM auth_principals WHERE id=$1::uuid', principal.id)
        if not actor or not actor['is_active'] or actor['role'] != 'admin':
            raise HTTPException(403, 'administrator_required')
        await conn.execute('UPDATE auth_registration_policy SET enabled=$1,updated_at=NOW() WHERE singleton=TRUE', payload.enabled)
    return await get_registration_policy(principal)


@router.get('/admin/users')
async def list_accounts(limit: int = 50, offset: int = 0, principal: Principal = AdminDep):
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(422, 'invalid_pagination')
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch('''SELECT id,username,role,is_active,created_at FROM auth_principals
            ORDER BY created_at,id LIMIT $1 OFFSET $2''', limit, offset)
        total = await conn.fetchval('SELECT COUNT(*) FROM auth_principals')
    return {'items': [{**dict(row), 'id': str(row['id'])} for row in rows], 'total': total}


@router.patch('/admin/users/{user_id}')
async def update_account(user_id: UUID, payload: AccountUpdate, principal: Principal = AdminDep):
    if not payload.model_fields_set or any(getattr(payload, key) is None for key in payload.model_fields_set):
        raise HTTPException(422, 'account_change_required')
    if str(user_id) == principal.id:
        raise HTTPException(409, 'cannot_change_own_access')
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute('SELECT pg_advisory_xact_lock(73120401)')
        # Recheck the acting administrator after waiting on a concurrent update.
        actor = await conn.fetchrow('SELECT role,is_active FROM auth_principals WHERE id=$1::uuid', principal.id)
        if not actor or not actor['is_active'] or actor['role'] != 'admin':
            raise HTTPException(403, 'administrator_required')
        row = await conn.fetchrow('SELECT role,is_active FROM auth_principals WHERE id=$1 FOR UPDATE', user_id)
        if not row:
            raise HTTPException(404, 'account_not_found')
        role = payload.role if payload.role is not None else row['role']
        active = payload.is_active if payload.is_active is not None else row['is_active']
        if row['role'] == 'admin' and row['is_active'] and (role != 'admin' or not active):
            count = await conn.fetchval("SELECT COUNT(*) FROM auth_principals WHERE role='admin' AND is_active=TRUE")
            if count <= 1:
                raise HTTPException(409, 'last_administrator_required')
        if (role, active) != (row['role'], row['is_active']):
            await conn.execute('''UPDATE auth_principals SET role=$2,is_active=$3,
                session_version=session_version+1,updated_at=NOW() WHERE id=$1''', user_id, role, active)
            await conn.execute('UPDATE auth_sessions SET revoked_at=NOW() WHERE principal_id=$1 AND revoked_at IS NULL', user_id)
            await conn.execute('UPDATE auth_api_tokens SET revoked_at=NOW() WHERE principal_id=$1 AND revoked_at IS NULL', user_id)
    return {'id': str(user_id), 'role': role, 'is_active': active}
