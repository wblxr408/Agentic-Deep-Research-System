"""Opt-in public source synchronization on the existing document lifecycle."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from app.channels.execution import ExecutionBudget, HttpReader, public_url
from app.channels.models import ChannelError
from app.data_governance import sensitive_url
from app.db.connection import get_db_pool
from app.research_scope import ScopeRecord

logger=logging.getLogger(__name__)
MAX_SUBSCRIPTIONS=50
MAX_BYTES=8*1024*1024
MAX_NETWORK_CALLS=4
RUN_SECONDS=120
LEASE_SECONDS=90
RETRY_LIMITS={'network':3,'timeout':2,'rate_limited':4,'upstream_error':2}


class SourceSyncError(Exception):
    def __init__(self,status:int,code:str):
        super().__init__(code)
        self.status,self.code=status,code


class SubscriptionCreate(ScopeRecord):
    request_id:UUID
    name:str=Field(min_length=1,max_length=200)
    group_name:str=Field(min_length=1,max_length=100)
    url:str=Field(min_length=1,max_length=2048)
    interval_seconds:int=Field(default=86400,ge=900,le=2592000)
    enabled:bool=False

    @field_validator('name','group_name')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('source_sync_blank_name_or_group')
        return value.strip()

    @field_validator('url')
    @classmethod
    def safe_url(cls,value):
        value=value.strip()
        try:
            public_url(value)
            if sensitive_url(value) or urlsplit(value).fragment:raise ValueError('source_sync_url_restricted')
        except ChannelError as error:raise ValueError('source_sync_public_https_required') from error
        return value


class SubscriptionAction(ScopeRecord):
    request_id:UUID
    expected_revision:int=Field(ge=1)
    action:str
    interval_seconds:int|None=Field(default=None,ge=900,le=2592000)

    @field_validator('action')
    @classmethod
    def action_allowed(cls,value):
        if value not in {'enable','pause','delete','interval'}:raise ValueError('source_sync_action_not_supported')
        return value

    @model_validator(mode='after')
    def valid_interval(self):
        if (self.action=='interval')!=(self.interval_seconds is not None):raise ValueError('source_sync_interval_action_mismatch')
        return self


class ManualRun(ScopeRecord):
    request_id:UUID


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _iso(value):
    return value.isoformat() if value is not None else None


def _subscription(row):
    return {'subscription_id':str(row['id']),'name':row['name'],'group_name':row['group_name'],
        'url':row['url'],'interval_seconds':row['interval_seconds'],'enabled':row['enabled'],
        'revision':row['revision'],'source_id':str(row['source_id']) if row['source_id'] else None,
        'next_run_at':_iso(row['next_run_at']),'last_run_at':_iso(row['last_run_at']),
        'last_outcome':row['last_outcome'],'last_error':row['last_error'],'created_at':_iso(row['created_at'])}


def _run(row):
    return {'run_id':str(row['id']),'subscription_id':str(row['subscription_id']),
        'trigger':row['trigger_kind'],'status':row['status'],'attempts':row['attempts'],
        'outcome':row['outcome'],'error_category':row['error_category'],
        'source_id':str(row['source_id']) if row['source_id'] else None,
        'network_calls':row['network_calls'],'network_calls_unknown':row['network_calls_unknown'],'http_status':row['http_status'],
        'created_at':_iso(row['created_at']),'updated_at':_iso(row['updated_at'])}


async def _active_owner(conn,owner_id):
    # Account state changes still serialize here; KEY SHARE from a concurrent
    # document insert remains compatible while it holds the lifecycle lock.
    row=await conn.fetchrow('SELECT id,is_active FROM auth_principals WHERE id=$1::uuid FOR NO KEY UPDATE',str(owner_id))
    if not row or not row['is_active']:raise SourceSyncError(404,'source_sync_owner_unavailable')


async def create_subscription(owner_id,request:SubscriptionCreate):
    fingerprint=_fingerprint(request.model_dump(mode='json',exclude={'request_id'}))
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await _active_owner(conn,owner_id)
        old=await conn.fetchrow('SELECT * FROM source_sync_subscriptions WHERE owner_id=$1::uuid AND request_id=$2::uuid',str(owner_id),request.request_id)
        if old:
            if old['request_fingerprint']!=fingerprint:raise SourceSyncError(409,'source_sync_request_conflict')
            return {**_subscription(old),'replayed':True}
        count=await conn.fetchval('SELECT count(*) FROM source_sync_subscriptions WHERE owner_id=$1::uuid AND deleted_at IS NULL',str(owner_id))
        if count>=MAX_SUBSCRIPTIONS:raise SourceSyncError(429,'source_sync_limit')
        row=await conn.fetchrow('''INSERT INTO source_sync_subscriptions
            (id,owner_id,request_id,request_fingerprint,name,group_name,url,interval_seconds,enabled,next_run_at)
            VALUES($1::uuid,$2::uuid,$3::uuid,$4,$5,$6,$7,$8,$9,
                CASE WHEN $9 THEN NOW()+($8::int*INTERVAL '1 second') ELSE NULL END) RETURNING *''',
            uuid4(),str(owner_id),request.request_id,fingerprint,request.name,request.group_name,request.url,request.interval_seconds,request.enabled)
        return {**_subscription(row),'replayed':False}


async def list_subscriptions(owner_id):
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        rows=await conn.fetch('''SELECT * FROM source_sync_subscriptions WHERE owner_id=$1::uuid
            AND deleted_at IS NULL ORDER BY created_at DESC,id LIMIT $2''',str(owner_id),MAX_SUBSCRIPTIONS)
        runs=await conn.fetch('''SELECT DISTINCT ON (subscription_id) * FROM source_sync_runs
            WHERE owner_id=$1::uuid ORDER BY subscription_id,created_at DESC,id DESC''',str(owner_id))
    latest={str(row['subscription_id']):_run(row) for row in runs}
    return {'items':[{**_subscription(row),'latest_run':latest.get(str(row['id']))} for row in rows]}


async def list_runs(owner_id,subscription_id):
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        found=await conn.fetchval('SELECT id FROM source_sync_subscriptions WHERE id=$1::uuid AND owner_id=$2::uuid AND deleted_at IS NULL',subscription_id,str(owner_id))
        if not found:raise SourceSyncError(404,'source_sync_not_found')
        rows=await conn.fetch('''SELECT * FROM source_sync_runs WHERE owner_id=$1::uuid AND subscription_id=$2::uuid
            ORDER BY created_at DESC,id DESC LIMIT 50''',str(owner_id),subscription_id)
    return {'items':[_run(row) for row in rows]}


async def change_subscription(owner_id,subscription_id,request:SubscriptionAction):
    fingerprint=_fingerprint({'subscription_id':str(subscription_id),**request.model_dump(mode='json',exclude={'request_id'})})
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await _active_owner(conn,owner_id)
        prior=await conn.fetchrow('SELECT fingerprint,result FROM source_sync_actions WHERE owner_id=$1::uuid AND request_id=$2::uuid',str(owner_id),request.request_id)
        if prior:
            if prior['fingerprint']!=fingerprint:raise SourceSyncError(409,'source_sync_request_conflict')
            value=json.loads(prior['result']) if isinstance(prior['result'],str) else dict(prior['result'])
            return {**value,'replayed':True}
        old=await conn.fetchrow('''SELECT * FROM source_sync_subscriptions WHERE id=$1::uuid AND owner_id=$2::uuid
            AND deleted_at IS NULL FOR UPDATE''',subscription_id,str(owner_id))
        if not old:raise SourceSyncError(404,'source_sync_not_found')
        if old['revision']!=request.expected_revision:raise SourceSyncError(409,'source_sync_revision_conflict')
        enabled=old['enabled'] if request.action=='interval' else request.action=='enable'
        interval=request.interval_seconds if request.action=='interval' else old['interval_seconds']
        deleted=request.action=='delete'
        row=await conn.fetchrow('''UPDATE source_sync_subscriptions SET enabled=$3,interval_seconds=$5,
            deleted_at=CASE WHEN $4 THEN NOW() ELSE NULL END,
            next_run_at=CASE WHEN $3 THEN NOW()+($5::int*INTERVAL '1 second') ELSE NULL END,
            revision=revision+1,updated_at=NOW() WHERE id=$1::uuid AND owner_id=$2::uuid RETURNING *''',
            subscription_id,str(owner_id),enabled,deleted,interval)
        if not deleted:
            # A schedule toggle does not revoke an explicit manual run whose
            # source and destination have not changed.
            await conn.execute('''UPDATE source_sync_runs SET subscription_revision=$3 WHERE subscription_id=$1::uuid
                AND owner_id=$2::uuid AND trigger_kind IN ('manual','webhook') AND status IN ('queued','running')''',
                subscription_id,str(owner_id),row['revision'])
        else:
            await conn.execute('''UPDATE source_sync_webhooks SET revoked_at=NOW(),secret_encrypted='' WHERE owner_id=$1::uuid
                AND subscription_id=$2::uuid AND revoked_at IS NULL''',str(owner_id),subscription_id)
            await conn.execute('''UPDATE source_sync_webhook_events SET status='canceled' WHERE owner_id=$1::uuid
                AND subscription_id=$2::uuid AND status='pending' ''',str(owner_id),subscription_id)
        await conn.execute('''UPDATE source_sync_runs SET status='canceled',error_category='subscription_changed',
            network_calls_unknown=network_calls_unknown OR status='running',
            lease_token=NULL,lease_until=NULL,updated_at=NOW() WHERE subscription_id=$1::uuid AND owner_id=$2::uuid
            AND status IN ('queued','running') AND ($3::boolean OR trigger_kind='scheduled')''',
            subscription_id,str(owner_id),deleted)
        if deleted:
            await conn.execute('''UPDATE source_sync_webhook_events e SET status='canceled' WHERE e.owner_id=$1::uuid
                AND e.subscription_id=$2::uuid AND e.status='assigned' AND EXISTS(SELECT 1 FROM source_sync_runs r
                WHERE r.id=e.run_id AND r.owner_id=e.owner_id AND r.status='canceled')''',str(owner_id),subscription_id)
        value={**_subscription(row),'deleted':deleted,'replayed':False}
        await conn.execute('''INSERT INTO source_sync_actions(owner_id,request_id,subscription_id,fingerprint,result)
            VALUES($1::uuid,$2::uuid,$3::uuid,$4,$5::jsonb)''',str(owner_id),request.request_id,subscription_id,fingerprint,json.dumps(value,ensure_ascii=False))
        return value


async def enqueue_manual(owner_id,subscription_id,request:ManualRun):
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await _active_owner(conn,owner_id)
        prior=await conn.fetchrow('SELECT * FROM source_sync_runs WHERE owner_id=$1::uuid AND request_id=$2::uuid',str(owner_id),request.request_id)
        if prior:
            if str(prior['subscription_id'])!=str(subscription_id) or prior['trigger_kind']!='manual':
                raise SourceSyncError(409,'source_sync_request_conflict')
            return {**_run(prior),'replayed':True}
        subscription=await conn.fetchrow('''SELECT * FROM source_sync_subscriptions WHERE id=$1::uuid AND owner_id=$2::uuid
            AND deleted_at IS NULL FOR UPDATE''',subscription_id,str(owner_id))
        if not subscription:raise SourceSyncError(404,'source_sync_not_found')
        existing=await conn.fetchval('''SELECT id FROM source_sync_runs WHERE owner_id=$1::uuid AND subscription_id=$2::uuid
            AND status IN ('queued','running')''',str(owner_id),subscription_id)
        if existing:raise SourceSyncError(409,'source_sync_already_running')
        row=await conn.fetchrow('''INSERT INTO source_sync_runs(id,owner_id,subscription_id,request_id,trigger_kind,
            subscription_revision,status,deadline_at) VALUES($1::uuid,$2::uuid,$3::uuid,$4::uuid,'manual',$5,'queued',
            NOW()+($6::int*INTERVAL '1 second')) RETURNING *''',uuid4(),str(owner_id),subscription_id,request.request_id,
            subscription['revision'],RUN_SECONDS)
        return {**_run(row),'replayed':False}


def _validator_for(url):
    """A subscription admits only the registered HTTPS origin, including redirects."""
    host,_=public_url(url)
    def validate(candidate):
        current,_=public_url(candidate)
        if current!=host or sensitive_url(candidate) or urlsplit(candidate).fragment:
            raise ChannelError('source_sync_redirect_out_of_scope')
    return validate


def _validator_header(value):
    return value if isinstance(value,str) and 0<len(value)<=512 and all(32<=ord(c)<=126 for c in value) else None


def _fetch_source(subscription,max_calls,deadline_at):
    from app.config import get_settings
    from app.research_documents import read_document
    seconds=min(55,(deadline_at-datetime.now(UTC)).total_seconds())
    if seconds<=0:raise ChannelError('timeout')
    deadline=time.monotonic()+seconds
    meter=ExecutionBudget(deadline,max_calls)
    conditional={key:value for key,value in {
        'etag':_validator_header(subscription.get('etag')),
        'last_modified':_validator_header(subscription.get('last_modified'))}.items() if value} if subscription.get('source_id') else None
    conditional=conditional or None
    try:
        response=HttpReader(url_validator=_validator_for(subscription['url'])).read(subscription['url'],
            timeout=min(30,seconds),max_bytes=min(MAX_BYTES,get_settings().security.upload_max_bytes),on_request=meter.take,conditional=conditional)
        if response.status==304:
            if not conditional:raise ChannelError('source_sync_unexpected_not_modified')
            return {'status':304,'network_calls':meter.used,'fetched_at':datetime.now(UTC).isoformat(),
                'etag':_validator_header(response.headers.get('etag')) or subscription.get('etag'),
                'last_modified':_validator_header(response.headers.get('last-modified')) or subscription.get('last_modified')}
        if response.status!=200:
            raise ChannelError({401:'auth_required',403:'access_denied',404:'not_found',429:'rate_limited'}.get(
                response.status,'upstream_error' if response.status>=500 else 'source_sync_unexpected_status'))
        content_type=response.headers.get('content-type','').lower()
        body=response.body
        if body.startswith(b'%PDF-'):
            format='pdf'
        elif body.startswith(b'PK\x03\x04') and ('wordprocessingml' in content_type or urlsplit(response.url).path.lower().endswith('.docx')):
            format='docx'
        elif 'html' in content_type:
            from app.openminion_research import _PageText
            parser=_PageText();parser.feed(body.decode('utf-8',errors='replace'))
            body=parser.text().encode('utf-8');format='txt'
        elif 'json' in content_type:
            format='json'
        elif content_type.startswith('text/'):
            format='md' if 'markdown' in content_type else 'txt'
        else:
            raise ChannelError('unsupported_content_type')
        remaining=deadline-time.monotonic()
        if remaining<=0:raise ChannelError('timeout')
        settings=get_settings()
        parsed=read_document(body,format=format,timeout=remaining,allow_ocr=False,
            max_pages=settings.security.upload_max_pages,max_chars=settings.document_parsing.max_chars)
        if not str(parsed.get('text') or '').strip():raise ChannelError('empty_content')
        return {'status':200,'network_calls':meter.used,'fetched_at':datetime.now(UTC).isoformat(),
            'etag':_validator_header(response.headers.get('etag')),
            'last_modified':_validator_header(response.headers.get('last-modified')),
            'final_url':response.url,'content_type':content_type[:200], 'format':format,'parsed':parsed}
    except Exception as error:
        try:error.network_call_count=meter.used
        except (AttributeError,TypeError):pass
        raise


async def _claim():
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        # The short global transaction prevents several web workers from
        # exceeding the shared bounded concurrency when they claim together.
        await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('source-sync-dispatch',0))")
        await conn.execute('''UPDATE source_sync_runs SET status='failed',error_category='original_deadline_expired',
            network_calls_unknown=network_calls_unknown OR status='running',
            lease_token=NULL,lease_until=NULL,updated_at=NOW() WHERE status IN ('queued','running') AND deadline_at<=NOW()''')
        # A dead worker may have sent requests without a receipt; do not
        # silently spend the same per-run network allowance a second time.
        await conn.execute('''UPDATE source_sync_runs SET status='failed',error_category='lease_receipt_unknown',
            network_calls_unknown=TRUE,lease_token=NULL,lease_until=NULL,updated_at=NOW()
            WHERE status='running' AND lease_until<NOW()''')
        await conn.execute('''UPDATE source_sync_webhook_events e SET status='canceled' WHERE e.status='pending' AND (
            NOT EXISTS(SELECT 1 FROM source_sync_webhooks h WHERE h.id=e.webhook_id AND h.owner_id=e.owner_id AND h.revoked_at IS NULL)
            OR NOT EXISTS(SELECT 1 FROM source_sync_subscriptions s JOIN auth_principals p ON p.id=s.owner_id
                WHERE s.id=e.subscription_id AND s.owner_id=e.owner_id AND s.deleted_at IS NULL AND p.is_active))''')
        pending=await conn.fetch('''SELECT s.* FROM source_sync_subscriptions s JOIN auth_principals p ON p.id=s.owner_id
            WHERE s.deleted_at IS NULL AND p.is_active AND EXISTS(SELECT 1 FROM source_sync_webhook_events e
                WHERE e.owner_id=s.owner_id AND e.subscription_id=s.id AND e.status='pending')
            ORDER BY s.id LIMIT 8 FOR UPDATE OF s SKIP LOCKED''')
        for item in pending:
            existing=await conn.fetchval('''SELECT id FROM source_sync_runs WHERE owner_id=$1::uuid AND subscription_id=$2::uuid
                AND status IN ('queued','running')''',item['owner_id'],item['id'])
            if existing:continue
            hook_id=await conn.fetchval('''SELECT e.webhook_id FROM source_sync_webhook_events e JOIN source_sync_webhooks h
                ON h.id=e.webhook_id AND h.owner_id=e.owner_id AND h.revoked_at IS NULL
                WHERE e.owner_id=$1::uuid AND e.subscription_id=$2::uuid AND e.status='pending'
                ORDER BY e.received_at,e.id LIMIT 1''',item['owner_id'],item['id'])
            if not hook_id:continue
            run_id=uuid4()
            await conn.execute('''INSERT INTO source_sync_runs(id,owner_id,subscription_id,request_id,trigger_kind,webhook_id,
                subscription_revision,status,deadline_at) VALUES($1::uuid,$2::uuid,$3::uuid,$4::uuid,'webhook',$5::uuid,$6,'queued',
                NOW()+($7::int*INTERVAL '1 second'))''',run_id,item['owner_id'],item['id'],uuid4(),hook_id,item['revision'],RUN_SECONDS)
            await conn.execute('''UPDATE source_sync_webhook_events SET status='assigned',run_id=$3::uuid
                WHERE owner_id=$1::uuid AND subscription_id=$2::uuid AND webhook_id=$4::uuid AND status='pending' ''',
                item['owner_id'],item['id'],run_id,hook_id)
        due=await conn.fetch('''SELECT s.* FROM source_sync_subscriptions s JOIN auth_principals p ON p.id=s.owner_id
            WHERE s.enabled AND s.deleted_at IS NULL AND s.next_run_at<=NOW() AND p.is_active
            ORDER BY s.next_run_at,s.id LIMIT 8 FOR UPDATE OF s SKIP LOCKED''')
        for item in due:
            # Skip missed intervals rather than creating a backlog of runs.
            await conn.execute('''UPDATE source_sync_subscriptions SET next_run_at=NOW()+(interval_seconds*INTERVAL '1 second')
                WHERE id=$1::uuid AND owner_id=$2::uuid''',item['id'],item['owner_id'])
            await conn.execute('''INSERT INTO source_sync_runs(id,owner_id,subscription_id,request_id,trigger_kind,
                subscription_revision,status,deadline_at) VALUES($1::uuid,$2::uuid,$3::uuid,$4::uuid,'scheduled',$5,'queued',
                NOW()+($6::int*INTERVAL '1 second')) ON CONFLICT DO NOTHING''',uuid4(),item['owner_id'],item['id'],uuid4(),item['revision'],RUN_SECONDS)
        active=await conn.fetchval("SELECT count(*) FROM source_sync_runs WHERE status='running' AND lease_until>NOW()")
        if active>=4:return None
        candidates=await conn.fetch('''SELECT r.id,r.owner_id,r.subscription_id FROM source_sync_runs r
            WHERE r.status='queued' AND r.not_before<=NOW() AND r.deadline_at>NOW()
            ORDER BY r.created_at,r.id LIMIT 12''')
        for candidate in candidates:
            subscription=await conn.fetchrow('''SELECT * FROM source_sync_subscriptions WHERE id=$1::uuid AND owner_id=$2::uuid
                FOR UPDATE SKIP LOCKED''',candidate['subscription_id'],candidate['owner_id'])
            if not subscription:continue
            run=await conn.fetchrow('''SELECT * FROM source_sync_runs WHERE id=$1::uuid AND owner_id=$2::uuid
                AND status='queued' AND not_before<=NOW() AND deadline_at>NOW() FOR UPDATE SKIP LOCKED''',candidate['id'],candidate['owner_id'])
            if not run:continue
            active_owner=await conn.fetchval('SELECT is_active FROM auth_principals WHERE id=$1::uuid',candidate['owner_id'])
            valid_hook=True
            if run['trigger_kind']=='webhook':
                valid_hook=bool(await conn.fetchval('''SELECT 1 FROM source_sync_webhooks WHERE id=$1::uuid
                    AND owner_id=$2::uuid AND subscription_id=$3::uuid AND revoked_at IS NULL''',
                    run['webhook_id'],run['owner_id'],run['subscription_id']))
            if (not active_owner or subscription['deleted_at'] or run['subscription_revision']!=subscription['revision']
                    or not valid_hook or run['trigger_kind']=='scheduled' and not subscription['enabled']):
                await conn.execute("UPDATE source_sync_runs SET status='canceled',error_category='subscription_unavailable',updated_at=NOW() WHERE id=$1::uuid",run['id'])
                continue
            if run['network_calls']>=MAX_NETWORK_CALLS:
                await conn.execute("UPDATE source_sync_runs SET status='failed',error_category='network_allowance_exhausted',updated_at=NOW() WHERE id=$1::uuid",run['id'])
                continue
            token=uuid4()
            await conn.execute('''UPDATE source_sync_runs SET status='running',attempts=attempts+1,lease_token=$2::uuid,
                lease_until=LEAST(deadline_at,NOW()+($3::int*INTERVAL '1 second')),updated_at=NOW() WHERE id=$1::uuid''',run['id'],token,LEASE_SECONDS)
            source=None
            if subscription['source_id']:
                source=await conn.fetchrow('''SELECT s.id,s.metadata->>'parse_version_id' AS parse_version,lc.revision
                    FROM document_sources s LEFT JOIN document_source_lifecycle lc ON lc.source_id=s.id AND lc.owner_id=s.owner_id
                    WHERE s.id=$1::uuid AND s.owner_id=$2::uuid''',subscription['source_id'],subscription['owner_id'])
            return {'run_id':str(run['id']),'owner_id':str(run['owner_id']),'token':str(token),
                'subscription':dict(subscription),'source_binding':dict(source) if source else None,
                'attempt':run['attempts']+1,'remaining_network_calls':MAX_NETWORK_CALLS-run['network_calls'],
                'deadline_at':run['deadline_at']}
    return None


async def _record_network_receipt(conn,claim,network_calls):
    inserted=await conn.fetchval('''INSERT INTO source_sync_network_receipts(owner_id,run_id,lease_token,network_calls)
        VALUES($1::uuid,$2::uuid,$3::uuid,$4) ON CONFLICT DO NOTHING RETURNING 1''',
        claim['owner_id'],claim['run_id'],claim['token'],network_calls)
    if inserted:
        await conn.execute('''UPDATE source_sync_runs SET network_calls=network_calls+$3,network_calls_unknown=FALSE
            WHERE id=$1::uuid AND owner_id=$2::uuid''',claim['run_id'],claim['owner_id'],network_calls)


async def _fail(claim,category,network_calls=0):
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        # Lock in the same order as user actions and successful writes.
        owner=await conn.fetchrow('SELECT id,is_active FROM auth_principals WHERE id=$1::uuid FOR UPDATE',claim['owner_id'])
        sub=await conn.fetchrow('SELECT * FROM source_sync_subscriptions WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE',
            claim['subscription']['id'],claim['owner_id'])
        run=await conn.fetchrow('SELECT * FROM source_sync_runs WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE',claim['run_id'],claim['owner_id'])
        if not sub or not run:return
        await _record_network_receipt(conn,claim,network_calls)
        if run['status']!='running' or str(run['lease_token'])!=claim['token']:return
        can_retry=(bool(owner and owner['is_active']) and category in RETRY_LIMITS and run['attempts']<RETRY_LIMITS[category]
            and run['network_calls']+network_calls<MAX_NETWORK_CALLS
            and run['deadline_at']>datetime.now(UTC) and sub['revision']==run['subscription_revision'] and not sub['deleted_at'])
        delay=min(20,2**run['attempts'])
        await conn.execute('''UPDATE source_sync_runs SET status=$3,error_category=$4,
            lease_token=NULL,lease_until=NULL,
            not_before=NOW()+($5::int*INTERVAL '1 second'),updated_at=NOW()
            WHERE id=$1::uuid AND owner_id=$2::uuid''',claim['run_id'],claim['owner_id'],
            'queued' if can_retry else 'failed',category,delay)
        if not can_retry:
            await conn.execute('''UPDATE source_sync_subscriptions SET last_outcome='failed',last_error=$3,last_run_at=NOW(),updated_at=NOW()
                WHERE id=$1::uuid AND owner_id=$2::uuid''',sub['id'],claim['owner_id'],category)


async def _finish(claim,result):
    from app.api.documents import _ingest_source
    from app.db.retrieval_indexes import IndexPolicy
    from app.evidence_chunks import ChunkPolicy
    from app.retrieval_features import FeaturePolicy
    from app.source_lifecycle import RetentionPolicy, SourceRevision, current_access, lock_owner, object_value, revise_source

    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await _active_owner(conn,claim['owner_id'])
        sub=await conn.fetchrow('''SELECT * FROM source_sync_subscriptions WHERE id=$1::uuid AND owner_id=$2::uuid
            FOR UPDATE''',claim['subscription']['id'],claim['owner_id'])
        run=await conn.fetchrow('''SELECT * FROM source_sync_runs WHERE id=$1::uuid AND owner_id=$2::uuid
            FOR UPDATE''',claim['run_id'],claim['owner_id'])
        if (not sub or not run or run['status']!='running' or str(run['lease_token'])!=claim['token']
                or run['lease_until']<=datetime.now(UTC) or run['deadline_at']<=datetime.now(UTC)
                or sub['deleted_at'] or sub['revision']!=run['subscription_revision']
                or run['trigger_kind']=='scheduled' and not sub['enabled']):
            raise SourceSyncError(409,'source_sync_run_superseded')
        if run['trigger_kind']=='webhook':
            valid_hook=await conn.fetchval('''SELECT id FROM source_sync_webhooks WHERE id=$1::uuid AND owner_id=$2::uuid
                AND subscription_id=$3::uuid AND revoked_at IS NULL FOR UPDATE''',run['webhook_id'],claim['owner_id'],sub['id'])
            if not valid_hook:raise SourceSyncError(409,'source_webhook_revoked')
        await lock_owner(conn,claim['owner_id'])
        source=None
        if sub['source_id']:
            binding=claim.get('source_binding')
            source=await conn.fetchrow('''SELECT s.*,lc.revision AS lifecycle_revision,lc.is_current,lc.state AS lifecycle_state
                FROM document_sources s JOIN document_source_lifecycle lc ON lc.source_id=s.id AND lc.owner_id=s.owner_id
                WHERE s.id=$1::uuid AND s.owner_id=$2::uuid FOR UPDATE OF s,lc''',sub['source_id'],claim['owner_id'])
            if (not binding or not source or str(source['id'])!=str(binding['id'])
                    or source['lifecycle_revision']!=binding['revision']
                    or object_value(source['metadata']).get('parse_version_id')!=binding['parse_version']
                    or not source['is_current'] or source['lifecycle_state']!='retained'
                    or not await current_access(conn,source['id'],claim['owner_id'],None,sub['group_name'],source['lifecycle_revision'])):
                raise SourceSyncError(409,'source_sync_target_changed_or_unavailable')
        if result['status']==304:
            if not source:raise SourceSyncError(409,'source_sync_target_changed_or_unavailable')
            outcome='unchanged';source_id=source['id']
        else:
            parsed=result['parsed'];text=str(parsed['text'])
            if source:
                previous_parse=object_value(source['metadata']).get('document_parse') or {}
                previous_complete=not previous_parse.get('truncated') and previous_parse.get('coverage')!='partial_text'
                current_incomplete=bool(parsed.get('truncated') or parsed.get('coverage')=='partial_text')
                if previous_complete and current_incomplete:
                    raise SourceSyncError(409,'source_sync_partial_replacement_blocked')
            if source and source['original_text']==text:
                outcome='unchanged';source_id=source['id']
            else:
                metadata={'source_sync':{'subscription_id':str(sub['id']),'registered_url':sub['url'],
                    'final_url':result['final_url'],'fetched_at':result['fetched_at'],'content_type':result['content_type'],
                    'etag':result.get('etag'),'last_modified':result.get('last_modified'),
                    'coverage':parsed.get('coverage'),'truncated':parsed.get('truncated')}}
                if not source:
                    created=await _ingest_source(name=sub['name'],group_name=sub['group_name'],source_type='web_sync',
                        content=text,metadata=metadata,file_ext=result['format'],owner_id=claim['owner_id'],
                        connection=conn,parsed_document=parsed,feature_policy=FeaturePolicy(dense=False),
                        retention_policy=RetentionPolicy(reuse_scope='group'),revision_intake_key='web-sync:'+str(sub['id']))
                    outcome='created';source_id=UUID(created['source_id'])
                else:
                    prior_metadata=object_value(source['metadata'])
                    feature_policy=FeaturePolicy.model_validate((prior_metadata.get('feature_profile') or {}).get('policy') or {})
                    if feature_policy.dense:raise SourceSyncError(409,'source_sync_dense_configuration_requires_manual_update')
                    if feature_policy.sparse:raise SourceSyncError(409,'source_sync_sparse_configuration_requires_manual_update')
                    mode=await conn.fetchval('SELECT mode FROM source_index_heads WHERE source_id=$1::uuid AND owner_id=$2::uuid',
                        source['id'],claim['owner_id'])
                    payload=SourceRevision(request_id=UUID(claim['run_id']),expected_revision=source['lifecycle_revision'],
                        expected_parse_version=prior_metadata.get('parse_version_id'),reason='explicit_public_source_sync',
                        mode='replace',text=text,format='txt',publish=True)
                    async def create_revision(replacement,old,old_metadata,policy):
                        return await _ingest_source(name=old['name'],group_name=old['group_name'],source_type='revision',
                            content=replacement,metadata={**old_metadata,**metadata},file_ext=result['format'],
                            chunk_size=old['chunk_size'],chunk_overlap=old['chunk_overlap'],owner_id=claim['owner_id'],
                            connection=conn,parsed_document=parsed,
                            chunk_policy=ChunkPolicy.model_validate((old_metadata.get('chunking_profile') or {}).get('policy') or {}),
                            feature_policy=feature_policy,index_policy=IndexPolicy(mode=mode or 'lexical',reason='explicit_source_sync_inherit_mode'),
                            retention_policy=policy,revision_intake_key=str(payload.request_id))
                    created=await revise_source(conn,source['id'],claim['owner_id'],payload,create_revision)
                    outcome='updated';source_id=UUID(created['source_id'])
        if datetime.now(UTC)>=min(run['deadline_at'],run['lease_until']):
            raise SourceSyncError(409,'source_sync_run_expired_before_commit')
        await _record_network_receipt(conn,claim,result['network_calls'])
        await conn.execute('''UPDATE source_sync_subscriptions SET source_id=$3::uuid,etag=$4,last_modified=$5,
            last_outcome=$6,last_error=NULL,last_run_at=NOW(),updated_at=NOW() WHERE id=$1::uuid AND owner_id=$2::uuid''',
            sub['id'],claim['owner_id'],source_id,result.get('etag'),result.get('last_modified'),outcome)
        await conn.execute('''UPDATE source_sync_runs SET status='completed',outcome=$3,source_id=$4::uuid,
            http_status=$5,error_category=NULL,lease_token=NULL,lease_until=NULL,updated_at=NOW()
            WHERE id=$1::uuid AND owner_id=$2::uuid''',claim['run_id'],claim['owner_id'],outcome,source_id,
            result['status'])


async def _execute(claim):
    calls=0
    try:
        result=await asyncio.to_thread(_fetch_source,claim['subscription'],claim['remaining_network_calls'],claim['deadline_at'])
        calls=result['network_calls']
        await _finish(claim,result)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        calls=max(calls,int(getattr(error,'network_call_count',0) or 0))
        if isinstance(error,ChannelError):category=error.category
        elif isinstance(error,SourceSyncError):category=error.code
        elif isinstance(error,TimeoutError):category='timeout'
        else:
            category='source_sync_processing_failed'
            logger.warning('Source sync failed: %s',type(error).__name__)
        await _fail(claim,category,calls)


class SourceSyncDispatcher:
    """One bounded dispatcher per API process; the database coordinates workers."""
    def __init__(self):self.task=None

    def start(self):
        if self.task is None:self.task=asyncio.create_task(self._loop())

    async def stop(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task,return_exceptions=True)
            self.task=None

    async def _loop(self):
        while True:
            try:
                claim=await _claim()
                if claim:await _execute(claim)
                else:await asyncio.sleep(3)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning('Source sync dispatcher unavailable: %s',type(error).__name__)
                await asyncio.sleep(5)
