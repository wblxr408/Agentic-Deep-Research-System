"""User-owned source subscriptions; never accept owner identity from payloads."""
from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException

from app.security.auth import Principal, require_principal
from app.source_sync import (ManualRun, SourceSyncError, SubscriptionAction, SubscriptionCreate,
    change_subscription, create_subscription, enqueue_manual, list_runs, list_subscriptions)

router=APIRouter(prefix='/api/v1/source-sync',tags=['source-sync'],dependencies=[Depends(require_principal)])


async def _answer(coroutine):
    try:return await coroutine
    except SourceSyncError as error:raise HTTPException(error.status,error.code) from None


@router.get('/subscriptions')
async def subscriptions(principal:Principal=Depends(require_principal)):
    return await _answer(list_subscriptions(principal.id))


@router.post('/subscriptions',status_code=201)
async def subscribe(payload:SubscriptionCreate,principal:Principal=Depends(require_principal)):
    return await _answer(create_subscription(principal.id,payload))


@router.post('/subscriptions/{subscription_id}/actions')
async def action(subscription_id:UUID,payload:SubscriptionAction,principal:Principal=Depends(require_principal)):
    return await _answer(change_subscription(principal.id,subscription_id,payload))


@router.post('/subscriptions/{subscription_id}/runs',status_code=202)
async def run(subscription_id:UUID,payload:ManualRun,principal:Principal=Depends(require_principal)):
    return await _answer(enqueue_manual(principal.id,subscription_id,payload))


@router.get('/subscriptions/{subscription_id}/runs')
async def runs(subscription_id:UUID,principal:Principal=Depends(require_principal)):
    return await _answer(list_runs(principal.id,subscription_id))
