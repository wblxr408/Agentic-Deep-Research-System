"""Signed GitHub notifications for an explicitly registered source."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from urllib.parse import urlsplit
from uuid import UUID,uuid4

from pydantic import Field,field_validator

from app.db.connection import get_db_pool
from app.research_scope import ScopeRecord
from app.security.crypto import decrypt_secret,encrypt_secret
from app.source_sync import RUN_SECONDS,SourceSyncError,_active_owner,_fingerprint

MAX_BODY_BYTES=256*1024
MAX_EVENTS_PER_MINUTE=30
MAX_EVENTS_PER_OWNER=20000
MAX_EVENTS_PER_HOOK=5000


class WebhookCreate(ScopeRecord):
    request_id:UUID
    secret:str=Field(min_length=32,max_length=128)

    @field_validator('secret')
    @classmethod
    def valid_secret(cls,value):
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}',value) or len(set(value))<12:
            raise ValueError('source_webhook_secret_invalid')
        return value


def _repository(url):
    parsed=urlsplit(url)
    parts=parsed.path.strip('/').split('/')
    if parsed.hostname not in {'github.com','raw.githubusercontent.com'} or len(parts)<2:
        return None
    owner,repo=parts[:2]
    if repo.endswith('.git'):repo=repo[:-4]
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',owner) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',repo):return None
    return (owner+'/'+repo).casefold()


def _public(row):
    return {'webhook_id':str(row['id']),'subscription_id':str(row['subscription_id']),
        'callback_path':'/api/v1/source-sync/hooks/'+str(row['id']),
        'created_at':row['created_at'].isoformat(),'provider':'github'}


async def webhook_status(owner_id,subscription_id):
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        sub=await conn.fetchrow('''SELECT id,url FROM source_sync_subscriptions WHERE id=$1::uuid AND owner_id=$2::uuid
            AND deleted_at IS NULL''',subscription_id,str(owner_id))
        if not sub:raise SourceSyncError(404,'source_sync_not_found')
        hook=await conn.fetchrow('''SELECT * FROM source_sync_webhooks WHERE owner_id=$1::uuid AND subscription_id=$2::uuid
            AND revoked_at IS NULL''',str(owner_id),subscription_id)
        latest=await conn.fetchrow('''SELECT e.received_at,e.status FROM source_sync_webhook_events e
            WHERE e.owner_id=$1::uuid AND e.subscription_id=$2::uuid ORDER BY e.received_at DESC LIMIT 1''',str(owner_id),subscription_id)
        counts=await conn.fetchrow('''SELECT count(*) AS total,count(*) FILTER (WHERE e.received_at<NOW()-INTERVAL '90 days'
            AND e.status<>'pending' AND NOT EXISTS(SELECT 1 FROM source_sync_runs r WHERE r.id=e.run_id
                AND r.owner_id=e.owner_id AND r.status IN ('queued','running'))) AS removable
            FROM source_sync_webhook_events e WHERE e.owner_id=$1::uuid AND e.subscription_id=$2::uuid''',str(owner_id),subscription_id)
        hook_count=await conn.fetchval('SELECT count(*) FROM source_sync_webhook_events WHERE webhook_id=$1::uuid',hook['id']) if hook else 0
        owner_count=await conn.fetchval('SELECT count(*) FROM source_sync_webhook_events WHERE owner_id=$1::uuid',str(owner_id))
        recent=await conn.fetchval('''SELECT count(*) FROM source_sync_webhook_events WHERE webhook_id=$1::uuid
            AND received_at>NOW()-INTERVAL '1 minute' ''',hook['id']) if hook else 0
    from app.config import get_settings
    return {'supported':bool(_repository(sub['url'])),'encryption_available':bool(get_settings().security.encryption_key),
        'webhook':_public(hook) if hook else None,'latest_event':{'received_at':latest['received_at'].isoformat(),
        'status':latest['status']} if latest else None,'retained_events':counts['total'],'removable_events':counts['removable'],
        'reception_status':'history_limit' if hook_count>=MAX_EVENTS_PER_HOOK or owner_count>=MAX_EVENTS_PER_OWNER
            else 'rate_limit' if recent>=MAX_EVENTS_PER_MINUTE else 'ready'}


async def create_webhook(owner_id,subscription_id,request:WebhookCreate):
    try:encrypted=encrypt_secret(request.secret)
    except RuntimeError:raise SourceSyncError(409,'source_webhook_encryption_unavailable') from None
    fingerprint=_fingerprint({'subscription_id':str(subscription_id),'secret_sha256':hashlib.sha256(request.secret.encode()).hexdigest()})
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await _active_owner(conn,owner_id)
        prior=await conn.fetchrow('''SELECT * FROM source_sync_webhooks WHERE owner_id=$1::uuid AND request_id=$2::uuid''',str(owner_id),request.request_id)
        if prior:
            if prior['request_fingerprint']!=fingerprint:raise SourceSyncError(409,'source_sync_request_conflict')
            if prior['revoked_at']:raise SourceSyncError(409,'source_webhook_revoked')
            return {**_public(prior),'replayed':True}
        sub=await conn.fetchrow('''SELECT * FROM source_sync_subscriptions WHERE id=$1::uuid AND owner_id=$2::uuid
            AND deleted_at IS NULL FOR UPDATE''',subscription_id,str(owner_id))
        if not sub:raise SourceSyncError(404,'source_sync_not_found')
        if not _repository(sub['url']):raise SourceSyncError(422,'source_webhook_github_source_required')
        active=await conn.fetchval('''SELECT id FROM source_sync_webhooks WHERE owner_id=$1::uuid
            AND subscription_id=$2::uuid AND revoked_at IS NULL''',str(owner_id),subscription_id)
        if active:raise SourceSyncError(409,'source_webhook_already_enabled')
        row=await conn.fetchrow('''INSERT INTO source_sync_webhooks(id,owner_id,subscription_id,request_id,request_fingerprint,secret_encrypted)
            VALUES($1::uuid,$2::uuid,$3::uuid,$4::uuid,$5,$6) RETURNING *''',uuid4(),str(owner_id),subscription_id,
            request.request_id,fingerprint,encrypted)
    return {**_public(row),'replayed':False}


async def revoke_webhook(owner_id,subscription_id,webhook_id):
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await _active_owner(conn,owner_id)
        sub=await conn.fetchrow('''SELECT id FROM source_sync_subscriptions WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE''',subscription_id,str(owner_id))
        if not sub:raise SourceSyncError(404,'source_sync_not_found')
        hook=await conn.fetchrow('''SELECT * FROM source_sync_webhooks WHERE id=$1::uuid AND owner_id=$2::uuid
            AND subscription_id=$3::uuid FOR UPDATE''',webhook_id,str(owner_id),subscription_id)
        if not hook:raise SourceSyncError(404,'source_webhook_not_found')
        if not hook['revoked_at']:
            await conn.execute("UPDATE source_sync_webhooks SET revoked_at=NOW(),secret_encrypted='' WHERE id=$1::uuid",webhook_id)
            await conn.execute('''UPDATE source_sync_webhook_events SET status='canceled' WHERE owner_id=$1::uuid
                AND webhook_id=$2::uuid AND status='pending' ''',str(owner_id),webhook_id)
            await conn.execute('''UPDATE source_sync_runs SET status='canceled',error_category='webhook_revoked',
                network_calls_unknown=network_calls_unknown OR status='running',lease_token=NULL,lease_until=NULL,updated_at=NOW()
                WHERE owner_id=$1::uuid AND webhook_id=$2::uuid AND trigger_kind='webhook' AND status IN ('queued','running')''',str(owner_id),webhook_id)
            await conn.execute('''UPDATE source_sync_webhook_events e SET status='canceled' WHERE e.owner_id=$1::uuid
                AND e.webhook_id=$2::uuid AND e.status='assigned' AND EXISTS(SELECT 1 FROM source_sync_runs r
                WHERE r.id=e.run_id AND r.owner_id=e.owner_id AND r.status='canceled')''',str(owner_id),webhook_id)
    return {'webhook_id':str(webhook_id),'revoked':True}


async def prune_old_events(owner_id,subscription_id,request_id):
    fingerprint=_fingerprint({'subscription_id':str(subscription_id),'action':'prune_webhook_events_90_days'})
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await _active_owner(conn,owner_id)
        prior=await conn.fetchrow('SELECT fingerprint,result FROM source_sync_actions WHERE owner_id=$1::uuid AND request_id=$2::uuid',str(owner_id),request_id)
        if prior:
            if prior['fingerprint']!=fingerprint:raise SourceSyncError(409,'source_sync_request_conflict')
            value=json.loads(prior['result']) if isinstance(prior['result'],str) else dict(prior['result'])
            return {**value,'replayed':True}
        sub=await conn.fetchrow('''SELECT id FROM source_sync_subscriptions WHERE id=$1::uuid AND owner_id=$2::uuid
            AND deleted_at IS NULL FOR UPDATE''',subscription_id,str(owner_id))
        if not sub:raise SourceSyncError(404,'source_sync_not_found')
        removed=await conn.fetch('''DELETE FROM source_sync_webhook_events e WHERE e.owner_id=$1::uuid
            AND e.subscription_id=$2::uuid AND e.received_at<NOW()-INTERVAL '90 days' AND e.status<>'pending'
            AND NOT EXISTS(SELECT 1 FROM source_sync_runs r WHERE r.id=e.run_id AND r.owner_id=e.owner_id
                AND r.status IN ('queued','running')) RETURNING e.id''',str(owner_id),subscription_id)
        value={'removed':len(removed),'older_than_days':90,'replayed':False}
        await conn.execute('''INSERT INTO source_sync_actions(owner_id,request_id,subscription_id,fingerprint,result)
            VALUES($1::uuid,$2::uuid,$3::uuid,$4,$5::jsonb)''',str(owner_id),request_id,subscription_id,fingerprint,json.dumps(value))
    return value


def _signature(secret,body,signature):
    if not isinstance(signature,str) or not re.fullmatch(r'sha256=[0-9a-f]{64}',signature):return False
    expected='sha256='+hmac.new(secret.encode(),body,hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected,signature)


async def accept_delivery(webhook_id,body:bytes,signature:str,event_type:str,delivery_id:str):
    try:delivery=UUID(delivery_id)
    except (ValueError,TypeError,AttributeError):raise SourceSyncError(400,'source_webhook_delivery_invalid') from None
    if event_type not in {'push','ping'}:raise SourceSyncError(400,'source_webhook_event_unsupported')
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        hook=await conn.fetchrow('''SELECT h.*,s.url FROM source_sync_webhooks h JOIN source_sync_subscriptions s
            ON s.id=h.subscription_id AND s.owner_id=h.owner_id JOIN auth_principals p ON p.id=h.owner_id
            WHERE h.id=$1::uuid AND h.revoked_at IS NULL AND s.deleted_at IS NULL AND p.is_active''',webhook_id)
    if not hook:raise SourceSyncError(404,'source_webhook_unavailable')
    try:secret=decrypt_secret(hook['secret_encrypted'])
    except RuntimeError:raise SourceSyncError(503,'source_webhook_encryption_unavailable') from None
    if not _signature(secret,body,signature):raise SourceSyncError(403,'source_webhook_signature_invalid')
    try:payload=json.loads(body)
    except (ValueError,UnicodeDecodeError,RecursionError):raise SourceSyncError(400,'source_webhook_payload_invalid') from None
    if not isinstance(payload,dict):raise SourceSyncError(400,'source_webhook_payload_invalid')
    if event_type=='push':
        repo=(payload.get('repository') or {}) if isinstance(payload.get('repository'),dict) else {}
        if (not isinstance(repo.get('full_name'),str) or repo['full_name'].casefold()!=_repository(hook['url'])
                or not isinstance(payload.get('ref'),str) or not isinstance(payload.get('after'),str)
                or not re.fullmatch(r'(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})',payload['after'])):
            raise SourceSyncError(403,'source_webhook_repository_mismatch')
    body_key=hmac.new(secret.encode(),b'adrs-webhook-body\x00'+body,hashlib.sha256).hexdigest()
    async with pool.acquire() as conn,conn.transaction():
        await _active_owner(conn,hook['owner_id'])
        sub=await conn.fetchrow('''SELECT * FROM source_sync_subscriptions WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE''',hook['subscription_id'],hook['owner_id'])
        current=await conn.fetchrow('''SELECT * FROM source_sync_webhooks WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE''',webhook_id,hook['owner_id'])
        if (not sub or sub['deleted_at'] or sub['url']!=hook['url'] or not current or current['revoked_at']
                or current['secret_encrypted']!=hook['secret_encrypted']):
            raise SourceSyncError(404,'source_webhook_unavailable')
        if event_type=='ping':return {'accepted':True,'kind':'ping'}
        duplicate=await conn.fetchrow('''SELECT * FROM source_sync_webhook_events WHERE webhook_id=$1::uuid
            AND delivery_id=$2::uuid''',webhook_id,delivery)
        if duplicate:
            if duplicate['payload_fingerprint']!=body_key:raise SourceSyncError(409,'source_webhook_delivery_conflict')
            return {'accepted':True,'kind':'duplicate'}
        duplicate=await conn.fetchval('''SELECT id FROM source_sync_webhook_events WHERE webhook_id=$1::uuid
            AND payload_fingerprint=$2''',webhook_id,body_key)
        if duplicate:
            return {'accepted':True,'kind':'duplicate'}
        recent=await conn.fetchval('''SELECT count(*) FROM source_sync_webhook_events WHERE webhook_id=$1::uuid
            AND received_at>NOW()-INTERVAL '1 minute' ''',webhook_id)
        if recent>=MAX_EVENTS_PER_MINUTE:raise SourceSyncError(429,'source_webhook_rate_limited')
        total_hook=await conn.fetchval('SELECT count(*) FROM source_sync_webhook_events WHERE webhook_id=$1::uuid',webhook_id)
        total_owner=await conn.fetchval('SELECT count(*) FROM source_sync_webhook_events WHERE owner_id=$1::uuid',hook['owner_id'])
        if total_hook>=MAX_EVENTS_PER_HOOK or total_owner>=MAX_EVENTS_PER_OWNER:
            raise SourceSyncError(429,'source_webhook_event_limit')
        active=await conn.fetchrow('''SELECT * FROM source_sync_runs WHERE owner_id=$1::uuid AND subscription_id=$2::uuid
            AND status IN ('queued','running') FOR UPDATE''',hook['owner_id'],sub['id'])
        run_id=None;status='pending'
        if active and active['status']=='queued' and active['trigger_kind']=='webhook' and active['webhook_id']==current['id']:
            run_id=active['id'];status='assigned'
        elif not active:
            run_id=uuid4();status='assigned'
            await conn.execute('''INSERT INTO source_sync_runs(id,owner_id,subscription_id,request_id,trigger_kind,webhook_id,
                subscription_revision,status,deadline_at) VALUES($1::uuid,$2::uuid,$3::uuid,$4::uuid,'webhook',$5::uuid,$6,'queued',
                NOW()+($7::int*INTERVAL '1 second'))''',run_id,hook['owner_id'],sub['id'],uuid4(),current['id'],sub['revision'],RUN_SECONDS)
        await conn.execute('''INSERT INTO source_sync_webhook_events(id,owner_id,webhook_id,subscription_id,delivery_id,
            payload_fingerprint,status,run_id) VALUES($1::uuid,$2::uuid,$3::uuid,$4::uuid,$5::uuid,$6,$7,$8::uuid)''',
            uuid4(),hook['owner_id'],current['id'],sub['id'],delivery,body_key,status,run_id)
    return {'accepted':True,'kind':'queued' if run_id else 'pending'}
