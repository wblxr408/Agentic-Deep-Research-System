"""Authenticated collaboration spaces; never impersonate the owning user."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.db import shared_workspaces as spaces
from app.security.auth import Principal, require_principal

router = APIRouter(prefix='/api/v1/workspaces',tags=['workspaces'])
principal_dependency = Depends(require_principal)
Name = Annotated[str, StringConstraints(strip_whitespace=True,min_length=1,max_length=120)]


class CreateWorkspace(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    name: Name


class InviteMember(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    username: Annotated[str, StringConstraints(strip_whitespace=True,min_length=3,max_length=120,pattern=r'^[A-Za-z0-9_.-]+$')]


async def _call(operation):
    try: return await operation
    except ValueError as error:
        message = str(error)
        code = (401 if message in {'workspace_authentication_required','email_authentication_required'} else
                403 if message=='workspace_owner_required' else
                404 if message in {'workspace_not_found','workspace_account_not_found','workspace_member_not_found','workspace_invitation_not_found'} else 409)
        raise HTTPException(code,message) from None


@router.get('')
async def list_spaces(principal: Principal = principal_dependency):
    return {'items':await _call(spaces.list_workspaces(principal))}


@router.post('',status_code=201)
async def create_space(payload:CreateWorkspace,principal: Principal = principal_dependency):
    return await _call(spaces.create_workspace(principal,payload.request_id,payload.name))


@router.get('/invitations')
async def list_invitations(principal: Principal = principal_dependency):
    return {'items':await _call(spaces.invitations(principal))}


@router.post('/invitations/{invite_id}/accept')
async def accept_invitation(invite_id:UUID,principal: Principal = principal_dependency):
    return await _call(spaces.respond_invitation(principal,invite_id,True))


@router.post('/invitations/{invite_id}/decline')
async def decline_invitation(invite_id:UUID,principal: Principal = principal_dependency):
    return await _call(spaces.respond_invitation(principal,invite_id,False))


@router.get('/{workspace_id}')
async def get_space(workspace_id:UUID,principal: Principal = principal_dependency):
    return await _call(spaces.workspace_detail(principal,workspace_id))


@router.post('/{workspace_id}/invitations',status_code=201)
async def invite_user(workspace_id:UUID,payload:InviteMember,principal: Principal = principal_dependency):
    return await _call(spaces.invite(principal,workspace_id,payload.request_id,payload.username))


@router.delete('/{workspace_id}/invitations/{invite_id}')
async def revoke_invitation(workspace_id:UUID,invite_id:UUID,principal: Principal = principal_dependency):
    return await _call(spaces.revoke_invitation(principal,workspace_id,invite_id))


@router.delete('/{workspace_id}/members/{member_id}')
async def remove_member(workspace_id:UUID,member_id:UUID,principal: Principal = principal_dependency):
    return await _call(spaces.remove_member(principal,workspace_id,member_id))


@router.delete('/{workspace_id}')
async def archive_space(workspace_id:UUID,principal: Principal = principal_dependency):
    return await _call(spaces.archive_workspace(principal,workspace_id))
