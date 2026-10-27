"""Owner-scoped PostgreSQL outbox feeds with commit-before-ack semantics."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import UTC,datetime
from uuid import UUID,uuid4,uuid5

from fastapi import HTTPException
from pydantic import Field,field_validator,model_validator

from app.config import get_settings
from app.db.connection import get_db_pool
from app.research_scope import ScopeRecord
from app.security.crypto import decrypt_secret,encrypt_secret
from app.source_sync import SourceSyncError,_active_owner,_fingerprint,_iso

logger=logging.getLogger(__name__)
MAX_CONNECTIONS=10
MAX_BLOCKED=100
MAX_EVENTS=20000
RUN_SECONDS=120
LEASE_SECONDS=90
MAX_EVENT_BYTES=256*1024


def endpoint_catalog(owner_id):
    """Only operator-configured, explicitly owner-bound endpoints are visible."""
    try:records=json.loads(os.environ.get('ADRS_CDC_ENDPOINTS','[]'))
    except (ValueError,TypeError):return []
    if not isinstance(records,list) or len(records)>100:return []
    output=[];seen=set()
    for value in records:
        if not isinstance(value,dict):continue
        try:
            item={key:value[key] for key in ('id','label','owner_id','host','port','database','schema','ca_path','allowed_networks')}
            if str(UUID(str(item['owner_id'])))!=str(owner_id):continue
            if not all(isinstance(item[key],str) for key in ('id','label','host','database','schema','ca_path')):continue
            if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',item['id']) or item['id'] in seen:continue
            if not item['label'].strip() or len(item['label'])>120:continue
            if not re.fullmatch(r'[A-Za-z0-9.-]{1,253}',item['host']) or not re.fullmatch(r'[A-Za-z0-9_-]{1,63}',item['database']):continue
            if not re.fullmatch(r'[a-z_][a-z0-9_]{0,62}',item['schema']) or not Path(item['ca_path']).is_absolute():continue
            if type(item['port']) is not int or not 1<=item['port']<=65535:continue
            if not isinstance(item['allowed_networks'],list) or not 1<=len(item['allowed_networks'])<=20:continue
            item['allowed_networks']=[str(ipaddress.ip_network(network,strict=False)) for network in item['allowed_networks']]
            item['owner_id']=str(owner_id)
        except (ValueError,TypeError,KeyError):continue
        seen.add(item['id']);output.append(item)
    return output


def _endpoint(owner_id,endpoint_id):
    return next((item for item in endpoint_catalog(owner_id) if item['id']==endpoint_id),None)


def _endpoint_fingerprint(endpoint):
    return _fingerprint({key:value for key,value in endpoint.items() if key!='label'})


def _credential_fingerprint(payload):
    key=get_settings().security.encryption_key
    if not key:raise SourceSyncError(409,'cdc_encryption_unavailable')
    encoded=json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
    return hmac.new(key.encode(),encoded,hashlib.sha256).hexdigest()


class CdcCreate(ScopeRecord):
    request_id:UUID
    endpoint_id:str=Field(min_length=1,max_length=64)
    name:str=Field(min_length=1,max_length=200)
    group_name:str=Field(min_length=1,max_length=100)
    username:str=Field(min_length=1,max_length=128)
    password:str=Field(min_length=1,max_length=1024)
    interval_seconds:int=Field(default=60,ge=30,le=3600)
    enabled:bool=False

    @field_validator('name','group_name','username')
    @classmethod
    def nonblank(cls,value):
        if not value.strip() or '\x00' in value:raise ValueError('cdc_value_invalid')
        return value.strip()

    @field_validator('password')
    @classmethod
    def valid_password(cls,value):
        if '\x00' in value:raise ValueError('cdc_value_invalid')
        return value


class CdcAction(ScopeRecord):
    request_id:UUID
    expected_revision:int=Field(ge=1)
    action:str
    interval_seconds:int|None=Field(default=None,ge=30,le=3600)

    @field_validator('action')
    @classmethod
    def valid_action(cls,value):
        if value not in {'enable','pause','delete','interval'}:raise ValueError('cdc_action_invalid')
        return value

    @model_validator(mode='after')
    def interval_matches(self):
        if (self.action=='interval')!=(self.interval_seconds is not None):raise ValueError('cdc_interval_action_mismatch')
        return self


class CdcRunRequest(ScopeRecord):
    request_id:UUID


class CdcEventAction(ScopeRecord):
    request_id:UUID
    action:str

    @field_validator('action')
    @classmethod
    def action_allowed(cls,value):
        if value not in {'retry','skip'}:raise ValueError('cdc_event_action_not_supported')
        return value


class CdcCredentialChange(ScopeRecord):
    request_id:UUID
    expected_revision:int=Field(ge=1)
    username:str=Field(min_length=1,max_length=128)
    password:str=Field(min_length=1,max_length=1024)

    @field_validator('username','password')
    @classmethod
    def valid_credentials(cls,value):
        if not value.strip() or '\x00' in value:raise ValueError('cdc_value_invalid')
        return value


def _public(row):
    return {'connection_id':str(row['id']),'endpoint_id':row['endpoint_id'],'name':row['name'],
        'group_name':row['group_name'],'enabled':row['enabled'],'revision':row['revision'],
        'interval_seconds':row['interval_seconds'],'next_run_at':_iso(row['next_run_at']),
        'snapshot_status':row['snapshot_status'],'snapshot_rows':row['snapshot_rows'],
        'snapshot_pending':row['snapshot_pending'],'last_status':row['last_status'],
        'last_error':row['last_error'],'last_run_at':_iso(row['last_run_at']),'created_at':_iso(row['created_at'])}


def _run(row):
    return {'run_id':str(row['id']),'status':row['status'],'trigger':row['trigger_kind'],
        'error_category':row['error_category'],'fetched':row['fetched_count'],'applied':row['applied_count'],
        'acknowledged':row['acknowledged_count'],'created_at':_iso(row['created_at']),'updated_at':_iso(row['updated_at'])}


async def list_endpoints(owner_id):
    return {'items':[{'id':item['id'],'label':item['label']} for item in endpoint_catalog(owner_id)],
        'encryption_available':bool(get_settings().security.encryption_key)}


async def create_connection(owner_id,request:CdcCreate):
    endpoint=_endpoint(owner_id,request.endpoint_id)
    if not endpoint:raise SourceSyncError(404,'cdc_endpoint_not_authorized')
    full=request.model_dump(mode='json',exclude={'request_id'})
    fingerprint=_credential_fingerprint(full)
    try:encrypted=encrypt_secret(json.dumps({'username':request.username,'password':request.password},ensure_ascii=False))
    except RuntimeError:raise SourceSyncError(409,'cdc_encryption_unavailable') from None
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await _active_owner(conn,owner_id)
        prior=await conn.fetchrow('SELECT * FROM source_cdc_connections WHERE owner_id=$1::uuid AND request_id=$2::uuid',str(owner_id),request.request_id)
        if prior:
            if prior['request_fingerprint']!=fingerprint:raise SourceSyncError(409,'cdc_request_conflict')
            if prior['deleted_at']:raise SourceSyncError(409,'cdc_connection_removed')
            return {**_public(prior),'replayed':True}
        count=await conn.fetchval('SELECT count(*) FROM source_cdc_connections WHERE owner_id=$1::uuid AND deleted_at IS NULL',str(owner_id))
        if count>=MAX_CONNECTIONS:raise SourceSyncError(429,'cdc_connection_limit')
        row=await conn.fetchrow('''INSERT INTO source_cdc_connections(id,owner_id,request_id,request_fingerprint,
            endpoint_id,endpoint_fingerprint,name,group_name,credentials_encrypted,interval_seconds,enabled,next_run_at)
            VALUES($1::uuid,$2::uuid,$3::uuid,$4,$5,$6,$7,$8,$9,$10,$11,
                CASE WHEN $11 THEN NOW()+($10::int*INTERVAL '1 second') ELSE NULL END) RETURNING *''',
            uuid4(),str(owner_id),request.request_id,fingerprint,endpoint['id'],_endpoint_fingerprint(endpoint),request.name,
            request.group_name,encrypted,request.interval_seconds,request.enabled)
    return {**_public(row),'replayed':False}


async def list_connections(owner_id):
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        rows=await conn.fetch('''SELECT * FROM source_cdc_connections WHERE owner_id=$1::uuid AND deleted_at IS NULL
            ORDER BY created_at DESC,id LIMIT $2''',str(owner_id),MAX_CONNECTIONS)
        latest=await conn.fetch('''SELECT DISTINCT ON(connection_id) * FROM source_cdc_runs WHERE owner_id=$1::uuid
            ORDER BY connection_id,created_at DESC,id DESC''',str(owner_id))
        blocked=await conn.fetch('''SELECT connection_id,count(*) AS total FROM source_cdc_events WHERE owner_id=$1::uuid
            AND status='blocked' GROUP BY connection_id''',str(owner_id))
    runs={str(row['connection_id']):_run(row) for row in latest}
    failures={str(row['connection_id']):row['total'] for row in blocked}
    return {'items':[{**_public(row),'latest_run':runs.get(str(row['id'])),'blocked_events':failures.get(str(row['id']),0)} for row in rows]}


async def change_connection(owner_id,connection_id,request:CdcAction):
    fingerprint=_fingerprint({'connection_id':str(connection_id),**request.model_dump(mode='json',exclude={'request_id'})})
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await _active_owner(conn,owner_id)
        prior=await conn.fetchrow('SELECT fingerprint,result FROM source_cdc_actions WHERE owner_id=$1::uuid AND request_id=$2::uuid',str(owner_id),request.request_id)
        if prior:
            if prior['fingerprint']!=fingerprint:raise SourceSyncError(409,'cdc_request_conflict')
            value=json.loads(prior['result']) if isinstance(prior['result'],str) else dict(prior['result'])
            return {**value,'replayed':True}
        old=await conn.fetchrow('''SELECT * FROM source_cdc_connections WHERE id=$1::uuid AND owner_id=$2::uuid
            AND deleted_at IS NULL FOR UPDATE''',connection_id,str(owner_id))
        if not old:raise SourceSyncError(404,'cdc_connection_not_found')
        if old['revision']!=request.expected_revision:raise SourceSyncError(409,'cdc_revision_conflict')
        enabled=old['enabled'] if request.action=='interval' else request.action=='enable'
        interval=request.interval_seconds if request.action=='interval' else old['interval_seconds']
        deleted=request.action=='delete'
        row=await conn.fetchrow('''UPDATE source_cdc_connections SET enabled=$3,interval_seconds=$5,
            deleted_at=CASE WHEN $4 THEN NOW() ELSE NULL END,credentials_encrypted=CASE WHEN $4 THEN '' ELSE credentials_encrypted END,
            next_run_at=CASE WHEN $3 THEN NOW()+($5::int*INTERVAL '1 second') ELSE NULL END,
            revision=revision+1,updated_at=NOW() WHERE id=$1::uuid AND owner_id=$2::uuid RETURNING *''',
            connection_id,str(owner_id),enabled,deleted,interval)
        if request.action in {'enable','interval'}:
            await conn.execute('''UPDATE source_cdc_runs SET connection_revision=$3 WHERE connection_id=$1::uuid
                AND owner_id=$2::uuid AND trigger_kind='manual' AND status IN ('queued','running')''',connection_id,str(owner_id),row['revision'])
        await conn.execute('''UPDATE source_cdc_runs SET status='canceled',error_category='cdc_connection_changed',
            lease_token=NULL,lease_until=NULL,updated_at=NOW() WHERE connection_id=$1::uuid AND owner_id=$2::uuid
            AND status IN ('queued','running') AND ($3::boolean OR trigger_kind='scheduled')''',connection_id,str(owner_id),request.action in {'pause','delete'})
        result={**_public(row),'deleted':deleted,'replayed':False}
        await conn.execute('''INSERT INTO source_cdc_actions(owner_id,connection_id,request_id,fingerprint,result)
            VALUES($1::uuid,$2::uuid,$3::uuid,$4,$5::jsonb)''',str(owner_id),connection_id,request.request_id,fingerprint,json.dumps(result))
    return result


async def enqueue_manual(owner_id,connection_id,request:CdcRunRequest):
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await _active_owner(conn,owner_id)
        prior=await conn.fetchrow('SELECT * FROM source_cdc_runs WHERE owner_id=$1::uuid AND request_id=$2::uuid',str(owner_id),request.request_id)
        if prior:
            if str(prior['connection_id'])!=str(connection_id) or prior['trigger_kind']!='manual':raise SourceSyncError(409,'cdc_request_conflict')
            return {**_run(prior),'replayed':True}
        source=await conn.fetchrow('''SELECT * FROM source_cdc_connections WHERE id=$1::uuid AND owner_id=$2::uuid
            AND deleted_at IS NULL FOR UPDATE''',connection_id,str(owner_id))
        if not source:raise SourceSyncError(404,'cdc_connection_not_found')
        active=await conn.fetchval('''SELECT id FROM source_cdc_runs WHERE owner_id=$1::uuid AND connection_id=$2::uuid
            AND status IN ('queued','running')''',str(owner_id),connection_id)
        if active:raise SourceSyncError(409,'cdc_already_running')
        row=await conn.fetchrow('''INSERT INTO source_cdc_runs(id,owner_id,connection_id,request_id,trigger_kind,
            connection_revision,status,deadline_at) VALUES($1::uuid,$2::uuid,$3::uuid,$4::uuid,'manual',$5,'queued',
            NOW()+($6::int*INTERVAL '1 second')) RETURNING *''',uuid4(),str(owner_id),connection_id,request.request_id,source['revision'],RUN_SECONDS)
    return {**_run(row),'replayed':False}


async def change_credentials(owner_id,connection_id,request:CdcCredentialChange):
    fingerprint=_credential_fingerprint({'connection_id':str(connection_id),**request.model_dump(mode='json',exclude={'request_id'})})
    try:encrypted=encrypt_secret(json.dumps({'username':request.username,'password':request.password},ensure_ascii=False))
    except RuntimeError:raise SourceSyncError(409,'cdc_encryption_unavailable') from None
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await _active_owner(conn,owner_id)
        prior=await conn.fetchrow('SELECT fingerprint,result FROM source_cdc_actions WHERE owner_id=$1::uuid AND request_id=$2::uuid',str(owner_id),request.request_id)
        if prior:
            if prior['fingerprint']!=fingerprint:raise SourceSyncError(409,'cdc_request_conflict')
            value=json.loads(prior['result']) if isinstance(prior['result'],str) else dict(prior['result'])
            return {**value,'replayed':True}
        source=await conn.fetchrow('''SELECT * FROM source_cdc_connections WHERE id=$1::uuid AND owner_id=$2::uuid
            AND deleted_at IS NULL FOR UPDATE''',connection_id,str(owner_id))
        if not source:raise SourceSyncError(404,'cdc_connection_not_found')
        if source['revision']!=request.expected_revision:raise SourceSyncError(409,'cdc_revision_conflict')
        endpoint=_endpoint(owner_id,source['endpoint_id'])
        if not endpoint or _endpoint_fingerprint(endpoint)!=source['endpoint_fingerprint']:raise SourceSyncError(409,'cdc_endpoint_changed_reauthorize')
        source=await conn.fetchrow('''UPDATE source_cdc_connections SET credentials_encrypted=$3,revision=revision+1,
            next_run_at=CASE WHEN enabled THEN NOW() ELSE NULL END,updated_at=NOW()
            WHERE id=$1::uuid AND owner_id=$2::uuid RETURNING *''',connection_id,str(owner_id),encrypted)
        await conn.execute('''UPDATE source_cdc_runs SET status='canceled',error_category='cdc_connection_changed',
            lease_token=NULL,lease_until=NULL,updated_at=NOW() WHERE owner_id=$1::uuid AND connection_id=$2::uuid
            AND status IN ('queued','running')''',str(owner_id),connection_id)
        result={**_public(source),'replayed':False}
        await conn.execute('''INSERT INTO source_cdc_actions(owner_id,connection_id,request_id,fingerprint,result)
            VALUES($1::uuid,$2::uuid,$3::uuid,$4,$5::jsonb)''',str(owner_id),connection_id,request.request_id,fingerprint,json.dumps(result))
    return result


async def list_events(owner_id,connection_id):
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        source=await conn.fetchrow('''SELECT id FROM source_cdc_connections WHERE id=$1::uuid AND owner_id=$2::uuid
            AND deleted_at IS NULL''',connection_id,str(owner_id))
        if not source:raise SourceSyncError(404,'cdc_connection_not_found')
        rows=await conn.fetch('''SELECT * FROM source_cdc_events WHERE owner_id=$1::uuid AND connection_id=$2::uuid
            AND status IN ('blocked','retry_requested','skipped')
            ORDER BY CASE WHEN status='blocked' THEN 0 WHEN status='retry_requested' THEN 1 ELSE 2 END,
            updated_at DESC,event_id LIMIT 101''',str(owner_id),connection_id)
    return {'items':[{'event_id':str(row['event_id']),'document_key':row['entity_key'],'revision':row['source_revision'],
        'status':row['status'],'error_category':row['error_category'],'acknowledged':row['source_acknowledged'],
        'updated_at':_iso(row['updated_at'])} for row in rows[:100]],'has_more':len(rows)>100}


async def resolve_event(owner_id,connection_id,event_id,request:CdcEventAction):
    fingerprint=_fingerprint({'connection_id':str(connection_id),'event_id':str(event_id),'action':request.action})
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await _active_owner(conn,owner_id)
        prior=await conn.fetchrow('SELECT fingerprint,result FROM source_cdc_actions WHERE owner_id=$1::uuid AND request_id=$2::uuid',str(owner_id),request.request_id)
        if prior:
            if prior['fingerprint']!=fingerprint:raise SourceSyncError(409,'cdc_request_conflict')
            value=json.loads(prior['result']) if isinstance(prior['result'],str) else dict(prior['result'])
            return {**value,'replayed':True}
        source=await conn.fetchrow('''SELECT * FROM source_cdc_connections WHERE id=$1::uuid AND owner_id=$2::uuid
            AND deleted_at IS NULL FOR UPDATE''',connection_id,str(owner_id))
        if not source:raise SourceSyncError(404,'cdc_connection_not_found')
        event=await conn.fetchrow('''SELECT * FROM source_cdc_events WHERE owner_id=$1::uuid AND connection_id=$2::uuid
            AND event_id=$3::uuid FOR UPDATE''',str(owner_id),connection_id,event_id)
        if not event or event['status']!='blocked':raise SourceSyncError(409,'cdc_event_not_blocked')
        await conn.execute('''UPDATE source_cdc_events SET status=$4,error_category=NULL,updated_at=NOW()
            WHERE owner_id=$1::uuid AND connection_id=$2::uuid AND event_id=$3::uuid''',str(owner_id),connection_id,event_id,
            'retry_requested' if request.action=='retry' else 'skipped')
        source=await conn.fetchrow('''UPDATE source_cdc_connections SET revision=revision+1,updated_at=NOW()
            WHERE id=$1::uuid AND owner_id=$2::uuid RETURNING *''',connection_id,str(owner_id))
        await conn.execute('''UPDATE source_cdc_runs SET status='canceled',error_category='cdc_recovery_requested',
            lease_token=NULL,lease_until=NULL,updated_at=NOW() WHERE owner_id=$1::uuid AND connection_id=$2::uuid
            AND status IN ('queued','running')''',str(owner_id),connection_id)
        run_id=uuid4()
        await conn.execute('''INSERT INTO source_cdc_runs(id,owner_id,connection_id,request_id,trigger_kind,
            connection_revision,status,deadline_at) VALUES($1::uuid,$2::uuid,$3::uuid,$4::uuid,'manual',$5,'queued',
            NOW()+($6::int*INTERVAL '1 second'))''',run_id,str(owner_id),connection_id,uuid5(request.request_id,'cdc-recovery-run'),source['revision'],RUN_SECONDS)
        result={'event_id':str(event_id),'status':'retry_requested' if request.action=='retry' else 'skipped',
            'run_id':str(run_id),'replayed':False}
        await conn.execute('''INSERT INTO source_cdc_actions(owner_id,connection_id,request_id,fingerprint,result)
            VALUES($1::uuid,$2::uuid,$3::uuid,$4,$5::jsonb)''',str(owner_id),connection_id,request.request_id,fingerprint,json.dumps(result))
    return result


async def prune_history(owner_id,connection_id,request_id):
    fingerprint=_fingerprint({'connection_id':str(connection_id),'action':'prune_confirmed_history_90_days'})
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await _active_owner(conn,owner_id)
        prior=await conn.fetchrow('SELECT fingerprint,result FROM source_cdc_actions WHERE owner_id=$1::uuid AND request_id=$2::uuid',str(owner_id),request_id)
        if prior:
            if prior['fingerprint']!=fingerprint:raise SourceSyncError(409,'cdc_request_conflict')
            value=json.loads(prior['result']) if isinstance(prior['result'],str) else dict(prior['result'])
            return {**value,'replayed':True}
        source=await conn.fetchrow('''SELECT id FROM source_cdc_connections WHERE owner_id=$1::uuid AND id=$2::uuid
            AND deleted_at IS NULL FOR UPDATE''',str(owner_id),connection_id)
        if not source:raise SourceSyncError(404,'cdc_connection_not_found')
        removed=await conn.fetchval('''WITH removed AS (DELETE FROM source_cdc_events WHERE owner_id=$1::uuid
            AND connection_id=$2::uuid AND source_acknowledged AND created_at<NOW()-INTERVAL '90 days'
            AND status IN ('applied','superseded','duplicate_version') RETURNING 1) SELECT count(*) FROM removed''',str(owner_id),connection_id)
        result={'removed':removed,'replayed':False}
        await conn.execute('''INSERT INTO source_cdc_actions(owner_id,connection_id,request_id,fingerprint,result)
            VALUES($1::uuid,$2::uuid,$3::uuid,$4,$5::jsonb)''',str(owner_id),connection_id,request_id,fingerprint,json.dumps(result))
    return result


def _source_request(claim,operation,**kwargs):
    endpoint=_endpoint(claim['owner_id'],claim['connection']['endpoint_id'])
    if not endpoint or _endpoint_fingerprint(endpoint)!=claim['connection']['endpoint_fingerprint']:
        raise SourceSyncError(409,'cdc_endpoint_changed_reauthorize')
    try:credentials=json.loads(decrypt_secret(claim['connection']['credentials_encrypted']))
    except (ValueError,RuntimeError):raise SourceSyncError(409,'cdc_credentials_unavailable') from None
    if not isinstance(credentials,dict) or not credentials.get('username') or not credentials.get('password'):
        raise SourceSyncError(409,'cdc_credentials_unavailable')
    remaining=(claim['deadline_at']-datetime.now(UTC)).total_seconds()
    if remaining<=0:raise SourceSyncError(409,'cdc_run_deadline_expired')
    request={'endpoint':endpoint,'credentials':credentials,'consumer_id':str(claim['connection']['id']),
        'operation':operation,**kwargs}
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    try:
        result=subprocess.run([sys.executable,str(Path(__file__).with_name('cdc_source_worker.py'))],
            input=json.dumps(request,ensure_ascii=True),text=True,encoding='utf-8',capture_output=True,
            timeout=min(25,remaining),creationflags=flags,check=False)
    except subprocess.TimeoutExpired:raise SourceSyncError(503,'cdc_source_timeout') from None
    try:payload=json.loads(result.stdout)
    except ValueError:raise SourceSyncError(503,'cdc_source_worker_failed') from None
    if not isinstance(payload,dict) or not payload.get('ok'):
        raise SourceSyncError(503,str(payload.get('error') or 'cdc_source_worker_failed') if isinstance(payload,dict) else 'cdc_source_worker_failed')
    return payload['result']


async def _source_with_retries(claim,operation,**kwargs):
    limits={'cdc_source_timeout':2,'cdc_source_connection_or_query_failed':3,'cdc_source_worker_failed':2,'cdc_source_busy':3}
    attempts=0
    while True:
        attempts+=1
        try:return await asyncio.to_thread(_source_request,claim,operation,**kwargs)
        except SourceSyncError as error:
            if attempts>=limits.get(error.code,1):raise
            delay=min(4,2**attempts)
            if (claim['deadline_at']-datetime.now(UTC)).total_seconds()<=delay+5:raise
            await asyncio.sleep(delay)


async def _claim():
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('source-cdc-dispatch',0))")
        await conn.execute('''UPDATE source_cdc_runs SET status='failed',error_category='cdc_run_deadline_expired',
            lease_token=NULL,lease_until=NULL,updated_at=NOW() WHERE status IN ('queued','running') AND deadline_at<=NOW()''')
        # Local event writes are transactional and acknowledgments are
        # idempotent. A lost worker is not silently granted a new deadline.
        await conn.execute('''UPDATE source_cdc_runs SET status='failed',error_category='cdc_worker_interrupted',
            lease_token=NULL,lease_until=NULL,updated_at=NOW() WHERE status='running' AND lease_until<NOW()''')
        due=await conn.fetch('''SELECT c.* FROM source_cdc_connections c JOIN auth_principals p ON p.id=c.owner_id
            WHERE c.enabled AND c.deleted_at IS NULL AND c.next_run_at<=NOW() AND p.is_active
            ORDER BY c.next_run_at,c.id LIMIT 8 FOR UPDATE OF c SKIP LOCKED''')
        for item in due:
            await conn.execute('''UPDATE source_cdc_connections SET next_run_at=NOW()+(interval_seconds*INTERVAL '1 second')
                WHERE id=$1::uuid AND owner_id=$2::uuid''',item['id'],item['owner_id'])
            await conn.execute('''INSERT INTO source_cdc_runs(id,owner_id,connection_id,request_id,trigger_kind,
                connection_revision,status,deadline_at) VALUES($1::uuid,$2::uuid,$3::uuid,$4::uuid,'scheduled',$5,'queued',
                NOW()+($6::int*INTERVAL '1 second')) ON CONFLICT DO NOTHING''',uuid4(),item['owner_id'],item['id'],uuid4(),item['revision'],RUN_SECONDS)
        running=await conn.fetchval("SELECT count(*) FROM source_cdc_runs WHERE status='running' AND lease_until>NOW()")
        if running>=2:return None
        candidates=await conn.fetch('''SELECT id,owner_id,connection_id FROM source_cdc_runs WHERE status='queued' AND deadline_at>NOW()
            ORDER BY created_at,id LIMIT 12''')
        for candidate in candidates:
            connection=await conn.fetchrow('''SELECT * FROM source_cdc_connections WHERE id=$1::uuid AND owner_id=$2::uuid
                FOR UPDATE SKIP LOCKED''',candidate['connection_id'],candidate['owner_id'])
            if not connection:continue
            run=await conn.fetchrow('''SELECT * FROM source_cdc_runs WHERE id=$1::uuid AND owner_id=$2::uuid
                AND status='queued' AND deadline_at>NOW() FOR UPDATE SKIP LOCKED''',candidate['id'],candidate['owner_id'])
            if not run:continue
            active_owner=await conn.fetchval('SELECT is_active FROM auth_principals WHERE id=$1::uuid',candidate['owner_id'])
            if (not active_owner or connection['deleted_at'] or run['connection_revision']!=connection['revision']
                    or run['trigger_kind']=='scheduled' and not connection['enabled']):
                await conn.execute("UPDATE source_cdc_runs SET status='canceled',error_category='cdc_connection_unavailable',updated_at=NOW() WHERE id=$1::uuid",run['id'])
                continue
            blocked=await conn.fetch('''SELECT event_id FROM source_cdc_events WHERE owner_id=$1::uuid AND connection_id=$2::uuid
                AND status='blocked' ORDER BY updated_at,event_id LIMIT $3''',candidate['owner_id'],candidate['connection_id'],MAX_BLOCKED+1)
            if len(blocked)>MAX_BLOCKED:
                await conn.execute("UPDATE source_cdc_runs SET status='failed',error_category='cdc_blocked_event_limit',updated_at=NOW() WHERE id=$1::uuid",run['id'])
                continue
            waiting=await conn.fetch('''SELECT event_id FROM source_cdc_events WHERE owner_id=$1::uuid AND connection_id=$2::uuid
                AND NOT source_acknowledged AND status IN ('applied','superseded','duplicate_version','skipped')
                ORDER BY updated_at,event_id LIMIT 20''',candidate['owner_id'],candidate['connection_id'])
            token=uuid4()
            await conn.execute('''UPDATE source_cdc_runs SET status='running',lease_token=$2::uuid,
                lease_until=LEAST(deadline_at,NOW()+($3::int*INTERVAL '1 second')),updated_at=NOW() WHERE id=$1::uuid''',run['id'],token,LEASE_SECONDS)
            return {'run_id':str(run['id']),'owner_id':str(run['owner_id']),'token':str(token),
                'connection':dict(connection),'deadline_at':run['deadline_at'],
                'excluded':[str(row['event_id']) for row in blocked],'check_ids':[str(row['event_id']) for row in waiting]}
    return None


async def _fail(claim,category):
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await conn.fetchrow('SELECT id FROM auth_principals WHERE id=$1::uuid FOR UPDATE',claim['owner_id'])
        source=await conn.fetchrow('''SELECT * FROM source_cdc_connections WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE''',
            claim['connection']['id'],claim['owner_id'])
        run=await conn.fetchrow('''SELECT * FROM source_cdc_runs WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE''',claim['run_id'],claim['owner_id'])
        if not source or not run or run['status']!='running' or str(run['lease_token'])!=claim['token']:return
        await conn.execute('''UPDATE source_cdc_runs SET status='failed',error_category=$3,lease_token=NULL,lease_until=NULL,
            updated_at=NOW() WHERE id=$1::uuid AND owner_id=$2::uuid''',claim['run_id'],claim['owner_id'],category)
        await conn.execute('''UPDATE source_cdc_connections SET last_status='failed',last_error=$3,last_run_at=NOW(),updated_at=NOW()
            WHERE id=$1::uuid AND owner_id=$2::uuid''',source['id'],claim['owner_id'],category)


def _event_error(event):
    try:UUID(str(event.get('event_id')))
    except (ValueError,TypeError,AttributeError):return 'cdc_event_identity_invalid'
    key=event.get('document_key')
    if not isinstance(key,str) or not key.strip() or len(key)>200 or any(ord(char)<32 for char in key):return 'cdc_event_key_invalid'
    revision=event.get('revision')
    if type(revision) is not int or revision<1:return 'cdc_event_revision_invalid'
    if event.get('operation') not in {'upsert','delete'}:return 'cdc_event_operation_invalid'
    if event['operation']=='upsert':
        title,content=event.get('title'),event.get('content')
        if (not isinstance(title,str) or not title.strip() or len(title)>200 or '\x00' in title
                or not isinstance(content,str) or not content.strip() or '\x00' in content):
            return 'cdc_event_content_invalid_or_too_large'
        if len(content.encode('utf-8'))>MAX_EVENT_BYTES:return 'cdc_event_content_invalid_or_too_large'
    return None


def _prepare_events(events):
    from app.document_structure import VERSION,parse_text
    settings=get_settings();prepared=[]
    for event in events:
        error=_event_error(event);parsed=None
        if not error and event['operation']=='upsert':
            parsed=parse_text(event['content'].encode('utf-8'),format='txt',max_chars=settings.document_parsing.max_chars)
            if parsed.get('truncated') or not parsed.get('text','').strip():error='cdc_event_parse_incomplete'
            parsed['parse_profile']={'schema_version':VERSION,'engine':parsed['parser_engine'],
                'engine_version':parsed.get('parser_engine_version'),'max_chars':settings.document_parsing.max_chars,
                'allow_ocr':False,'source':'postgres_transactional_outbox'}
        prepared.append((event,error,parsed))
    return prepared


async def _bind_events(claim,events):
    keys=list({event.get('document_key') for event in events if isinstance(event.get('document_key'),str)})
    if not keys:return {}
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        rows=await conn.fetch('''SELECT e.entity_key,e.latest_revision,e.state,e.source_id,
            lc.revision AS lifecycle_revision,s.metadata->>'parse_version_id' AS parse_version
            FROM source_cdc_entities e LEFT JOIN document_sources s ON s.id=e.source_id AND s.owner_id=e.owner_id
            LEFT JOIN document_source_lifecycle lc ON lc.source_id=e.source_id AND lc.owner_id=e.owner_id
            WHERE e.owner_id=$1::uuid AND e.connection_id=$2::uuid AND e.entity_key=ANY($3::text[])''',
            claim['owner_id'],claim['connection']['id'],keys)
    return {row['entity_key']:(row['latest_revision'],row['state'],str(row['source_id']) if row['source_id'] else None,
        row['lifecycle_revision'],row['parse_version']) for row in rows}


async def _binding_matches(conn,claim,key,bindings):
    row=await conn.fetchrow('''SELECT e.latest_revision,e.state,e.source_id,lc.revision AS lifecycle_revision,
        s.metadata->>'parse_version_id' AS parse_version FROM source_cdc_entities e
        LEFT JOIN document_sources s ON s.id=e.source_id AND s.owner_id=e.owner_id
        LEFT JOIN document_source_lifecycle lc ON lc.source_id=e.source_id AND lc.owner_id=e.owner_id
        WHERE e.owner_id=$1::uuid AND e.connection_id=$2::uuid AND e.entity_key=$3''',
        claim['owner_id'],claim['connection']['id'],key)
    current=(row['latest_revision'],row['state'],str(row['source_id']) if row['source_id'] else None,
        row['lifecycle_revision'],row['parse_version']) if row else None
    return current==bindings.get(key)


async def _insert_event(conn,claim,event,status,*,error=None,source_id=None):
    event_id=UUID(str(event['event_id']))
    key=event.get('document_key') if isinstance(event.get('document_key'),str) else ''
    revision=event.get('revision') if type(event.get('revision')) is int else 0
    operation=event.get('operation') if isinstance(event.get('operation'),str) else ''
    await conn.execute('''INSERT INTO source_cdc_events(owner_id,connection_id,event_id,entity_key,source_revision,
        operation,payload_fingerprint,payload,status,error_category,source_id)
        VALUES($1::uuid,$2::uuid,$3::uuid,$4,$5,$6,$7,$8::jsonb,$9,$10,$11::uuid)
        ON CONFLICT(owner_id,connection_id,event_id) DO UPDATE SET status=EXCLUDED.status,
        error_category=EXCLUDED.error_category,source_id=COALESCE(EXCLUDED.source_id,source_cdc_events.source_id),updated_at=NOW()''',
        claim['owner_id'],claim['connection']['id'],event_id,key[:201],revision,operation[:20],_fingerprint(event),
        json.dumps(event,ensure_ascii=False),status,error,str(source_id) if source_id else None)


async def _apply_event(conn,claim,event,parsed):
    from app.api.documents import _ingest_source
    from app.db.retrieval_indexes import IndexPolicy
    from app.evidence_chunks import ChunkPolicy
    from app.retrieval_features import FeaturePolicy
    from app.source_lifecycle import (LifecycleAction,RetentionPolicy,SourceRevision,apply_lifecycle_action,
        current_access,object_value,revise_source)
    owner=claim['owner_id'];connection=claim['connection'];key=event['document_key'];revision=event['revision']
    prior=await conn.fetchrow('''SELECT * FROM source_cdc_entities WHERE owner_id=$1::uuid AND connection_id=$2::uuid
        AND entity_key=$3 FOR UPDATE''',owner,connection['id'],key)
    semantic=_fingerprint({field:event.get(field) for field in ('document_key','revision','operation','title','content')})
    if prior and revision<prior['latest_revision']:
        await _insert_event(conn,claim,event,'superseded',source_id=prior['source_id']);return False
    if prior and revision==prior['latest_revision']:
        if semantic!=prior['latest_fingerprint']:raise SourceSyncError(409,'cdc_entity_revision_conflict')
        await _insert_event(conn,claim,event,'duplicate_version',source_id=prior['source_id']);return False
    old=None
    if prior and prior['state']=='active' and prior['source_id']:
        old=await conn.fetchrow('''SELECT s.*,lc.revision AS lifecycle_revision,lc.state AS lifecycle_state,lc.is_current
            FROM document_sources s JOIN document_source_lifecycle lc ON lc.source_id=s.id AND lc.owner_id=s.owner_id
            WHERE s.id=$1::uuid AND s.owner_id=$2::uuid FOR UPDATE OF s,lc''',prior['source_id'],owner)
        if (not old or old['lifecycle_state']!='retained' or not old['is_current']
                or not await current_access(conn,old['id'],owner,None,connection['group_name'],old['lifecycle_revision'])):
            raise SourceSyncError(409,'cdc_target_changed_or_unavailable')
    event_request=uuid5(UUID(str(connection['id'])),str(event['event_id']))
    if event['operation']=='delete':
        if old:
            await apply_lifecycle_action(conn,old['id'],owner,LifecycleAction(request_id=event_request,action='tombstone',
                expected_revision=old['lifecycle_revision'],reason='source_database_delete'))
        source_id=old['id'] if old else None;state='deleted'
    else:
        metadata={'source_cdc':{'connection_id':str(connection['id']),'endpoint_id':connection['endpoint_id'],
            'event_id':event['event_id'],'document_key':key,'revision':revision,'source_event_time':event.get('created_at'),
            'snapshot_id':event.get('snapshot_id'),'is_snapshot':bool(event.get('is_snapshot'))}}
        if not old:
            created=await _ingest_source(name=event['title'],group_name=connection['group_name'],source_type='cdc',
                content=parsed['text'],metadata=metadata,file_ext='txt',owner_id=owner,connection=conn,parsed_document=parsed,
                feature_policy=FeaturePolicy(dense=False),retention_policy=RetentionPolicy(reuse_scope='group'),
                revision_intake_key='cdc:'+str(connection['id'])+':'+key)
            source_id=UUID(created['source_id'])
        else:
            old_metadata=object_value(old['metadata'])
            features=FeaturePolicy.model_validate((old_metadata.get('feature_profile') or {}).get('policy') or {})
            if features.dense:raise SourceSyncError(409,'cdc_dense_configuration_requires_manual_update')
            if features.sparse:raise SourceSyncError(409,'cdc_sparse_configuration_requires_manual_update')
            if features.multivector:raise SourceSyncError(409,'cdc_multivector_configuration_requires_manual_update')
            mode=await conn.fetchval('SELECT mode FROM source_index_heads WHERE source_id=$1::uuid AND owner_id=$2::uuid',old['id'],owner)
            if mode=='direct':features=features.model_copy(update={'english_stemming':False})
            request=SourceRevision(request_id=event_request,expected_revision=old['lifecycle_revision'],
                expected_parse_version=old_metadata.get('parse_version_id'),reason='source_database_change',
                mode='replace',text=parsed['text'],format='txt',publish=True)
            async def create_revision(text,source,source_metadata,policy):
                return await _ingest_source(name=event['title'],group_name=source['group_name'],source_type='revision',
                    content=text,metadata={**source_metadata,**metadata},file_ext='txt',chunk_size=source['chunk_size'],
                    chunk_overlap=source['chunk_overlap'],owner_id=owner,connection=conn,parsed_document=parsed,
                    chunk_policy=ChunkPolicy.model_validate((source_metadata.get('chunking_profile') or {}).get('policy') or {}),
                    feature_policy=features,index_policy=IndexPolicy(mode=mode or 'lexical',reason='cdc_inherit_mode'),
                    retention_policy=policy,revision_intake_key=str(request.request_id))
            created=await revise_source(conn,old['id'],owner,request,create_revision,allow_unchanged_text=True)
            source_id=UUID(created['source_id'])
        state='active'
    await conn.execute('''INSERT INTO source_cdc_entities(owner_id,connection_id,entity_key,latest_revision,latest_fingerprint,state,source_id)
        VALUES($1::uuid,$2::uuid,$3,$4,$5,$6,$7::uuid) ON CONFLICT(owner_id,connection_id,entity_key)
        DO UPDATE SET latest_revision=EXCLUDED.latest_revision,latest_fingerprint=EXCLUDED.latest_fingerprint,
            state=EXCLUDED.state,source_id=EXCLUDED.source_id''',owner,connection['id'],key,revision,semantic,state,str(source_id) if source_id else None)
    await _insert_event(conn,claim,event,'applied',source_id=source_id)
    return True


async def _commit_events(claim,source_result,prepared,bindings):
    from app.source_lifecycle import lock_owner
    pool=await get_db_pool();ack=[];applied=0;blocked=0;checked=set()
    snapshot=source_result.get('snapshot')
    if snapshot is not None:
        try:
            UUID(str(snapshot['id']))
            if any(type(snapshot[key]) is not int or snapshot[key]<0 for key in ('rows','events','pending')):raise ValueError()
        except (KeyError,ValueError,TypeError):raise SourceSyncError(409,'cdc_source_snapshot_invalid') from None
    confirmed=source_result.get('confirmed_acks') or []
    try:confirmed=[UUID(str(value)) for value in confirmed[:20]]
    except (ValueError,TypeError,AttributeError):raise SourceSyncError(409,'cdc_ack_receipt_invalid') from None
    async with pool.acquire() as conn,conn.transaction():
        await _active_owner(conn,claim['owner_id'])
        source=await conn.fetchrow('''SELECT * FROM source_cdc_connections WHERE id=$1::uuid AND owner_id=$2::uuid
            AND deleted_at IS NULL FOR UPDATE''',claim['connection']['id'],claim['owner_id'])
        run=await conn.fetchrow('''SELECT * FROM source_cdc_runs WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE''',
            claim['run_id'],claim['owner_id'])
        endpoint=_endpoint(claim['owner_id'],claim['connection']['endpoint_id'])
        if (not source or not run or run['status']!='running' or str(run['lease_token'])!=claim['token']
                or run['connection_revision']!=source['revision'] or run['lease_until']<=datetime.now(UTC)
                or run['deadline_at']<=datetime.now(UTC) or not endpoint
                or _endpoint_fingerprint(endpoint)!=source['endpoint_fingerprint']):raise SourceSyncError(409,'cdc_connection_changed')
        await lock_owner(conn,claim['owner_id'])
        if confirmed:
            await conn.execute('''UPDATE source_cdc_events SET source_acknowledged=TRUE,updated_at=NOW()
                WHERE owner_id=$1::uuid AND connection_id=$2::uuid AND event_id=ANY($3::uuid[])
                AND status IN ('applied','superseded','duplicate_version','skipped')''',
                claim['owner_id'],source['id'],confirmed)
        total=await conn.fetchval('SELECT count(*) FROM source_cdc_events WHERE owner_id=$1::uuid AND connection_id=$2::uuid',claim['owner_id'],source['id'])
        for event,error,parsed in prepared:
            try:event_id=UUID(str(event.get('event_id')))
            except (ValueError,TypeError,AttributeError):raise SourceSyncError(409,'cdc_event_identity_invalid') from None
            existing=await conn.fetchrow('''SELECT * FROM source_cdc_events WHERE owner_id=$1::uuid AND connection_id=$2::uuid
                AND event_id=$3::uuid FOR UPDATE''',claim['owner_id'],source['id'],event_id)
            if existing and existing['status']=='skipped':
                ack.append(str(event_id));continue
            if existing and existing['payload_fingerprint']!=_fingerprint(event):
                await conn.execute('''UPDATE source_cdc_events SET status='blocked',error_category='cdc_event_identity_conflict',updated_at=NOW()
                    WHERE owner_id=$1::uuid AND connection_id=$2::uuid AND event_id=$3::uuid''',claim['owner_id'],source['id'],event_id)
                blocked+=1;continue
            if existing and existing['status'] in {'applied','superseded','duplicate_version','skipped'}:
                ack.append(str(event_id));continue
            if existing and existing['status']=='blocked':blocked+=1;continue
            if not existing and total>=MAX_EVENTS:raise SourceSyncError(409,'cdc_event_history_limit')
            if error:
                await _insert_event(conn,claim,event,'blocked',error=error);blocked+=1
                if not existing:total+=1
                continue
            try:
                async with conn.transaction():
                    if event['document_key'] not in checked:
                        if not await _binding_matches(conn,claim,event['document_key'],bindings):
                            raise SourceSyncError(409,'cdc_target_changed_or_unavailable')
                        checked.add(event['document_key'])
                    changed=await _apply_event(conn,claim,event,parsed)
                applied+=int(changed);ack.append(str(event_id))
            except (SourceSyncError,ValueError,HTTPException) as problem:
                message=str(problem)
                category=(problem.code if isinstance(problem,SourceSyncError) else message
                    if isinstance(problem,ValueError) and re.fullmatch(r'[a-z][a-z0-9_]{1,99}',message)
                    else 'cdc_document_ingest_rejected')
                await _insert_event(conn,claim,event,'blocked',error=category[:100]);blocked+=1
            if not existing:total+=1
        blocked=await conn.fetchval('''SELECT count(*) FROM source_cdc_events WHERE owner_id=$1::uuid
            AND connection_id=$2::uuid AND status='blocked' ''',claim['owner_id'],source['id'])
        if datetime.now(UTC)>=run['deadline_at'] or datetime.now(UTC)>=run['lease_until']:
            raise SourceSyncError(409,'cdc_run_deadline_expired')
        snapshot_status=('not_observed' if snapshot is None else 'source_incomplete' if snapshot['events']!=snapshot['rows']
            else 'complete' if snapshot['pending']==0 else 'in_progress')
        await conn.execute('''UPDATE source_cdc_connections SET snapshot_status=$3,snapshot_id=$4::uuid,
            snapshot_rows=$5,snapshot_pending=$6,updated_at=NOW() WHERE id=$1::uuid AND owner_id=$2::uuid''',
            source['id'],claim['owner_id'],snapshot_status,snapshot['id'] if snapshot else None,
            snapshot['rows'] if snapshot else None,snapshot['pending'] if snapshot else None)
        await conn.execute('''UPDATE source_cdc_runs SET fetched_count=$3,applied_count=$4,updated_at=NOW()
            WHERE id=$1::uuid AND owner_id=$2::uuid''',claim['run_id'],claim['owner_id'],len(prepared),applied)
    return {'ack':ack,'applied':applied,'blocked':blocked,'snapshot':snapshot}


async def _may_ack(claim):
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await _active_owner(conn,claim['owner_id'])
        source=await conn.fetchrow('SELECT * FROM source_cdc_connections WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE',claim['connection']['id'],claim['owner_id'])
        run=await conn.fetchrow('SELECT * FROM source_cdc_runs WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE',claim['run_id'],claim['owner_id'])
        endpoint=_endpoint(claim['owner_id'],claim['connection']['endpoint_id'])
        return bool(source and not source['deleted_at'] and run and run['status']=='running'
            and str(run['lease_token'])==claim['token'] and run['connection_revision']==source['revision']
            and run['deadline_at']>datetime.now(UTC) and run['lease_until']>datetime.now(UTC)
            and endpoint and _endpoint_fingerprint(endpoint)==source['endpoint_fingerprint'])


async def _finalize(claim,committed,acked):
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await conn.fetchrow('SELECT id FROM auth_principals WHERE id=$1::uuid FOR UPDATE',claim['owner_id'])
        source=await conn.fetchrow('SELECT * FROM source_cdc_connections WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE',claim['connection']['id'],claim['owner_id'])
        run=await conn.fetchrow('SELECT * FROM source_cdc_runs WHERE id=$1::uuid AND owner_id=$2::uuid FOR UPDATE',claim['run_id'],claim['owner_id'])
        if acked:
            await conn.execute('''UPDATE source_cdc_events SET source_acknowledged=TRUE,updated_at=NOW()
                WHERE owner_id=$1::uuid AND connection_id=$2::uuid AND event_id=ANY($3::uuid[])
                AND status IN ('applied','superseded','duplicate_version','skipped')''',
                claim['owner_id'],claim['connection']['id'],[UUID(value) for value in acked])
        if not source or not run or run['status']!='running' or str(run['lease_token'])!=claim['token']:return
        snapshot=committed['snapshot'];pending=None
        if snapshot:
            sent=set(acked)
            accepted=sum(1 for event in committed.get('events',[]) if event.get('snapshot_id')==snapshot['id'] and event.get('event_id') in sent)
            pending=max(0,snapshot['pending']-accepted)
        snapshot_status=('not_observed' if snapshot is None else 'source_incomplete' if snapshot['events']!=snapshot['rows']
            else 'complete' if pending==0 else 'in_progress')
        status='attention' if committed['blocked'] else 'completed'
        await conn.execute('''UPDATE source_cdc_connections SET last_status=$3,last_error=$4,last_run_at=NOW(),
            snapshot_status=$5,snapshot_pending=$6,next_run_at=CASE WHEN enabled AND $7 THEN NOW()+INTERVAL '5 seconds' ELSE next_run_at END,
            updated_at=NOW() WHERE id=$1::uuid AND owner_id=$2::uuid''',
            source['id'],claim['owner_id'],status,'cdc_blocked_events' if committed['blocked'] else None,
            snapshot_status,pending,len(committed.get('events',[]))==20)
        await conn.execute('''UPDATE source_cdc_runs SET status='completed',acknowledged_count=$3,lease_token=NULL,
            lease_until=NULL,updated_at=NOW() WHERE id=$1::uuid AND owner_id=$2::uuid''',claim['run_id'],claim['owner_id'],len(acked))


async def _execute(claim):
    try:
        result=await _source_with_retries(claim,'read',exclude=claim['excluded'],check_ids=claim['check_ids'])
        events=result.get('events') if isinstance(result,dict) else None
        if not isinstance(events,list) or len(events)>20 or any(not isinstance(event,dict) for event in events):
            raise SourceSyncError(409,'cdc_source_event_batch_invalid')
        bindings=await _bind_events(claim,events)
        prepared=await asyncio.to_thread(_prepare_events,events)
        committed=await _commit_events(claim,result,prepared,bindings);committed['events']=events
        acked=[]
        if committed['ack']:
            if not await _may_ack(claim):raise SourceSyncError(409,'cdc_ack_unconfirmed')
            try:result=await _source_with_retries(claim,'ack',event_ids=committed['ack'])
            except SourceSyncError:raise SourceSyncError(503,'cdc_ack_unconfirmed') from None
            if result.get('acknowledged')!=len(committed['ack']):raise SourceSyncError(503,'cdc_ack_unconfirmed')
            acked=committed['ack']
        await _finalize(claim,committed,acked)
    except SourceSyncError as error:await _fail(claim,error.code)
    except asyncio.CancelledError:raise
    except Exception:
        logger.error('CDC run failed; credentials and source payload omitted')
        await _fail(claim,'cdc_processing_failed')


class CdcDispatcher:
    def __init__(self):self.task=None;self.running=set();self.closed=False
    async def start(self):
        if not self.task:self.task=asyncio.create_task(self._loop(),name='source-cdc-dispatcher')
    async def stop(self):
        self.closed=True
        if self.task:self.task.cancel()
        for task in self.running:task.cancel()
        await asyncio.gather(*(list(self.running)+([self.task] if self.task else [])),return_exceptions=True)
    async def _loop(self):
        while not self.closed:
            try:
                while len(self.running)<2:
                    claim=await _claim()
                    if not claim:break
                    task=asyncio.create_task(_execute(claim),name='source-cdc-run')
                    self.running.add(task);task.add_done_callback(self.running.discard)
            except asyncio.CancelledError:raise
            except Exception:logger.exception('CDC dispatcher failed')
            await asyncio.sleep(2)
