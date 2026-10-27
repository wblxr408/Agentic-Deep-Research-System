"""Authenticated, owner-scoped PostgreSQL transactional event feeds."""
from uuid import UUID

from fastapi import APIRouter,Depends,HTTPException

from app.security.auth import Principal,require_principal
from app.source_cdc import (CdcAction,CdcCreate,CdcCredentialChange,CdcEventAction,CdcRunRequest,
    change_connection,change_credentials,create_connection,enqueue_manual,list_connections,list_endpoints,list_events,prune_history,resolve_event)
from app.source_sync import SourceSyncError

router=APIRouter(prefix='/api/v1/source-cdc',tags=['source-cdc'],dependencies=[Depends(require_principal)])


async def _answer(coroutine):
    try:return await coroutine
    except SourceSyncError as error:raise HTTPException(error.status,error.code) from None


@router.get('/endpoints')
async def endpoints(principal:Principal=Depends(require_principal)):
    return await _answer(list_endpoints(principal.id))


@router.get('/connections')
async def connections(principal:Principal=Depends(require_principal)):
    return await _answer(list_connections(principal.id))


@router.post('/connections',status_code=201)
async def create(payload:CdcCreate,principal:Principal=Depends(require_principal)):
    return await _answer(create_connection(principal.id,payload))


@router.post('/connections/{connection_id}/actions')
async def change(connection_id:UUID,payload:CdcAction,principal:Principal=Depends(require_principal)):
    return await _answer(change_connection(principal.id,connection_id,payload))


@router.post('/connections/{connection_id}/credentials')
async def credentials(connection_id:UUID,payload:CdcCredentialChange,principal:Principal=Depends(require_principal)):
    return await _answer(change_credentials(principal.id,connection_id,payload))


@router.post('/connections/{connection_id}/runs',status_code=202)
async def run(connection_id:UUID,payload:CdcRunRequest,principal:Principal=Depends(require_principal)):
    return await _answer(enqueue_manual(principal.id,connection_id,payload))


@router.get('/connections/{connection_id}/events')
async def events(connection_id:UUID,principal:Principal=Depends(require_principal)):
    return await _answer(list_events(principal.id,connection_id))


@router.post('/connections/{connection_id}/events/{event_id}/actions')
async def resolve(connection_id:UUID,event_id:UUID,payload:CdcEventAction,principal:Principal=Depends(require_principal)):
    return await _answer(resolve_event(principal.id,connection_id,event_id,payload))


@router.post('/connections/{connection_id}/history/prune')
async def prune(connection_id:UUID,payload:CdcRunRequest,principal:Principal=Depends(require_principal)):
    return await _answer(prune_history(principal.id,connection_id,payload.request_id))
