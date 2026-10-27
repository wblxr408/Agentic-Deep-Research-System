"""Personal, encrypted platform credentials; responses never contain a secret."""
from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, SecretStr

from app.channels.models import ChannelError
from app.channels.store import ChannelStore
from app.config import get_settings
from app.db.connection import get_db_pool
from app.db.shared_workspaces import actor
from app.security.auth import Principal, require_principal

router = APIRouter(prefix='/api/v1/connections',tags=['personal connections'])
principal_dependency = Depends(require_principal)


class GitHubCredential(BaseModel):
    model_config = ConfigDict(extra='forbid')
    token: SecretStr
    enabled: bool = False


class ConnectionEnabled(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool


def available():
    return bool(get_settings().security.encryption_key)


async def personal(principal, method, *args):
    pool = await get_db_pool()
    try:
        async with pool.acquire() as conn, conn.transaction():
            # Keep the principal and credential locked through the owner-file mutation.
            await actor(conn,principal)
            return await asyncio.to_thread(getattr(ChannelStore(),method),principal.id,*args)
    except ValueError as error:
        if str(error) in {'workspace_authentication_required','email_authentication_required'}:
            raise HTTPException(401,'authentication_required') from None
        raise HTTPException(409,'personal_connection_unavailable') from None
    except ChannelError as error:
        raise HTTPException(409 if error.category=='personal_connection_not_configured' else 503,error.category) from None
    except RuntimeError:
        raise HTTPException(503,'personal_connection_unavailable') from None


@router.get('/github')
async def github_status(principal:Principal=principal_dependency):
    return {**await personal(principal,'github_status'),'encryption_available':available(),'verified':False}


@router.put('/github')
async def save_github(body:GitHubCredential,principal:Principal=principal_dependency):
    token = body.token.get_secret_value()
    if not 20 <= len(token) <= 512 or not re.fullmatch(r'[A-Za-z0-9_.-]+',token) or token.startswith('enc:'):
        raise HTTPException(422,'invalid_personal_credential')
    if not available(): raise HTTPException(503,'personal_connection_encryption_unavailable')
    return await personal(principal,'save_github',token,body.enabled)


@router.patch('/github')
async def enable_github(body:ConnectionEnabled,principal:Principal=principal_dependency):
    if body.enabled and not available(): raise HTTPException(503,'personal_connection_encryption_unavailable')
    return await personal(principal,'enable_github',body.enabled)


@router.delete('/github')
async def revoke_github(principal:Principal=principal_dependency):
    return await personal(principal,'revoke_github')
