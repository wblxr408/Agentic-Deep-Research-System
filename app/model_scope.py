"""Model identity/configuration lives in one request or one owned execution."""
from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass, replace
from functools import wraps
from typing import Any

from fastapi import HTTPException

from app.config import get_settings


@dataclass(frozen=True)
class ModelScope:
    owner_id: str
    role: str
    config: Any = None


_scope: ContextVar[ModelScope | None] = ContextVar('owner_model_scope', default=None)


def set_model_identity(owner_id: str, role: str):
    return _scope.set(ModelScope(str(owner_id), role))


def environment_model_allowed() -> bool:
    scope = _scope.get()
    return not get_settings().security.auth_enabled or bool(scope and scope.role == 'admin')


def host_credentials_allowed() -> bool:
    """Host browser/CLI profiles are deployment assets, never personal accounts."""
    return environment_model_allowed()


def get_scoped_config():
    scope = _scope.get()
    return scope.config if scope else None


def set_scoped_config(config) -> None:
    scope = _scope.get()
    if not scope:
        raise RuntimeError('model_owner_required')
    _scope.set(replace(scope, config=config.model_copy(deep=True) if config else None))


async def bind_owner_model(owner_id: str) -> None:
    from app.api.config import LLMConfigRequest, get_llm_config_from_db
    from app.db.connection import get_db_pool
    if not owner_id:
        raise HTTPException(403, 'model_owner_required')
    if not get_settings().security.auth_enabled and owner_id == '00000000-0000-0000-0000-000000000000':
        role = 'admin'
    else:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow('SELECT role,is_active FROM auth_principals WHERE id=$1::uuid', owner_id)
        if not row or not row['is_active']:
            raise HTTPException(403, 'account_inactive')
        role = row['role']
    set_model_identity(owner_id, role)
    saved = await get_llm_config_from_db(owner_id)
    if saved:
        set_scoped_config(LLMConfigRequest.model_validate(saved['data']))


def owner_model_execution(function):
    """Reset execution context even when a worker reuses the same task/thread."""
    @wraps(function)
    async def run(*args, **kwargs):
        token = _scope.set(None)
        try:
            return await function(*args, **kwargs)
        finally:
            _scope.reset(token)
    return run
