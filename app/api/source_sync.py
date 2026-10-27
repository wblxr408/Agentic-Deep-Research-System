"""User-owned source subscriptions; never accept owner identity from payloads."""
from __future__ import annotations

from uuid import UUID
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Request

from app.security.auth import Principal, require_principal
from app.source_sync import (ManualRun, SourceSyncError, SubscriptionAction, SubscriptionCreate,
    change_subscription, create_subscription, enqueue_manual, list_runs, list_subscriptions)

router=APIRouter(prefix='/api/v1/source-sync',tags=['source-sync'],dependencies=[Depends(require_principal)])
public_router=APIRouter(prefix='/api/v1/source-sync/hooks',tags=['source-sync-events'])
_event_slots=asyncio.Semaphore(8)


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


@router.get('/subscriptions/{subscription_id}/webhook')
async def event_settings(subscription_id:UUID,principal:Principal=Depends(require_principal)):
    from app.source_webhooks import webhook_status
    return await _answer(webhook_status(principal.id,subscription_id))


from app.source_webhooks import WebhookCreate


@router.post('/subscriptions/{subscription_id}/webhook',status_code=201)
async def enable_events(subscription_id:UUID,payload:WebhookCreate,principal:Principal=Depends(require_principal)):
    from app.source_webhooks import create_webhook
    return await _answer(create_webhook(principal.id,subscription_id,payload))


@router.delete('/subscriptions/{subscription_id}/webhook/{webhook_id}')
async def disable_events(subscription_id:UUID,webhook_id:UUID,principal:Principal=Depends(require_principal)):
    from app.source_webhooks import revoke_webhook
    return await _answer(revoke_webhook(principal.id,subscription_id,webhook_id))


@router.post('/subscriptions/{subscription_id}/webhook/events/prune')
async def prune_events(subscription_id:UUID,payload:ManualRun,principal:Principal=Depends(require_principal)):
    from app.source_webhooks import prune_old_events
    return await _answer(prune_old_events(principal.id,subscription_id,payload.request_id))


@public_router.post('/{webhook_id}',status_code=202)
async def receive_github_event(webhook_id:UUID,request:Request):
    from app.source_webhooks import MAX_BODY_BYTES,accept_delivery
    try:
        await asyncio.wait_for(_event_slots.acquire(),timeout=2)
    except TimeoutError:raise HTTPException(429,'source_webhook_busy') from None
    try:
        chunks=[];size=0
        try:
            async with asyncio.timeout(8):
                async for chunk in request.stream():
                    size+=len(chunk)
                    if size>MAX_BODY_BYTES:raise HTTPException(413,'source_webhook_payload_too_large')
                    chunks.append(chunk)
        except TimeoutError:raise HTTPException(408,'source_webhook_receive_timeout') from None
        try:
            async with asyncio.timeout(1.5):
                return await _answer(accept_delivery(webhook_id,b''.join(chunks),request.headers.get('X-Hub-Signature-256',''),
                    request.headers.get('X-GitHub-Event',''),request.headers.get('X-GitHub-Delivery','')))
        except TimeoutError:raise HTTPException(503,'source_webhook_busy') from None
    finally:
        _event_slots.release()
