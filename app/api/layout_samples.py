"""Owner-scoped, content-isolated sample inputs and parsing operations."""
from __future__ import annotations

import asyncio
import json
from pathlib import PurePath
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sse_starlette.sse import EventSourceResponse

from app.config import get_settings
from app.db.connection import get_db_pool
from app.layout_operations import LayoutOperationError, cancel_operation, read_operation, submit_operation
from app.report_layout import sample_byte_limit
from app.security.auth import Principal, require_principal

router = APIRouter(prefix='/layout-samples', dependencies=[Depends(require_principal)])


def sample_record(row):
    parsed = json.loads(row['parsed']) if isinstance(row['parsed'], str) else row['parsed']
    return {'source_id': str(row['source_id']), 'file_name': row['file_name'],
            'created_at': row['created_at'].isoformat(), **parsed}


async def _upload(file:UploadFile):
    name=(file.filename or '').replace('\\','/').rsplit('/',1)[-1]
    if not name or len(name)>240 or any(ord(char)<32 for char in name):
        raise HTTPException(422,'layout_invalid_file_name')
    format=PurePath(name).suffix.lower().lstrip('.')
    if format not in {'html','htm','docx','pdf'}:
        raise HTTPException(415,'layout_format_not_supported')
    limit=sample_byte_limit(format)
    raw=await file.read(limit+1)
    if not raw or len(raw)>limit:
        raise HTTPException(413,'layout_sample_size_limit')
    return name,format,raw


def _failure(error:LayoutOperationError):
    return HTTPException(error.status,error.code)


@router.post('/operations',status_code=202)
async def create_layout_operation(file:UploadFile=File(...),request_id:UUID=Form(...),principal:Principal=Depends(require_principal)):
    name,format,raw=await _upload(file)
    try:
        return await submit_operation(principal.id,request_id,name,format,raw)
    except LayoutOperationError as error:
        raise _failure(error) from None


@router.get('/operations/{operation_id}')
async def get_layout_operation(operation_id:UUID,principal:Principal=Depends(require_principal)):
    try:
        return await read_operation(principal.id,operation_id)
    except LayoutOperationError as error:
        raise _failure(error) from None


@router.delete('/operations/{operation_id}')
async def cancel_layout_operation(operation_id:UUID,principal:Principal=Depends(require_principal)):
    try:
        return await cancel_operation(principal.id,operation_id)
    except LayoutOperationError as error:
        raise _failure(error) from None


async def _stream_authorized(principal:Principal,operation_id:UUID):
    """Revalidate the credential and operation owner before each event."""
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        if principal.auth_type=='disabled':
            if get_settings().security.auth_enabled:
                return False
            return bool(await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM research_layout_operations
                WHERE owner_id=$1::uuid AND operation_id=$2::uuid)''',principal.id,operation_id))
        if principal.auth_type not in {'session','api_token'} or not principal.credential_hash:
            return False
        table='auth_api_tokens' if principal.auth_type=='api_token' else 'auth_sessions'
        return bool(await conn.fetchval(f'''SELECT EXISTS(SELECT 1 FROM {table} t
            JOIN auth_principals p ON p.id=t.principal_id
            JOIN research_layout_operations o ON o.owner_id=p.id
            WHERE t.token_hash=$1 AND p.id=$2::uuid AND o.operation_id=$3::uuid
              AND t.revoked_at IS NULL AND p.is_active=TRUE AND t.session_version=p.session_version
              AND (t.expires_at IS NULL OR t.expires_at>NOW()))''',principal.credential_hash,principal.id,operation_id))


@router.get('/operations/{operation_id}/events')
async def layout_operation_events(operation_id:UUID,request:Request,principal:Principal=Depends(require_principal)):
    try:
        await read_operation(principal.id,operation_id)
    except LayoutOperationError as error:
        raise _failure(error) from None
    if not await _stream_authorized(principal,operation_id):
        raise HTTPException(404,'layout_operation_not_found')
    cursor=request.headers.get('last-event-id','')
    initial=int(cursor) if cursor.isdecimal() and len(cursor)<10 else 0

    async def events():
        current=initial
        loop=asyncio.get_running_loop();start=loop.time()
        while loop.time()-start<60 and not await request.is_disconnected():
            try:
                if not await _stream_authorized(principal,operation_id):
                    return
                pool=await get_db_pool()
                async with pool.acquire() as conn:
                    rows=await conn.fetch('''SELECT sequence,status,stage,attempt,error_code,error_category,created_at
                        FROM research_layout_operation_events WHERE owner_id=$1::uuid AND operation_id=$2::uuid
                        AND sequence>$3 ORDER BY sequence LIMIT 100''',principal.id,operation_id,current)
                    state=await conn.fetchrow('''SELECT status,revision FROM research_layout_operations
                        WHERE owner_id=$1::uuid AND operation_id=$2::uuid''',principal.id,operation_id)
                if not state:
                    return
                for row in rows:
                    if not await _stream_authorized(principal,operation_id):
                        return
                    current=row['sequence']
                    payload={'operation_id':str(operation_id),'revision':current,'status':row['status'],
                        'stage':row['stage'],'attempt':row['attempt'],'error_code':row['error_code'],
                        'error_category':row['error_category'],'created_at':row['created_at'].isoformat()}
                    yield {'id':str(current),'event':'progress','data':json.dumps(payload,ensure_ascii=False)}
                if state['status'] in {'completed','failed','canceled'} and current>=state['revision']:
                    return
                await asyncio.sleep(.35)
            except asyncio.CancelledError:
                raise
            except Exception:
                # Fail closed on authentication or storage errors; reconnect
                # starts with a fresh credential and durable cursor.
                return
    return EventSourceResponse(events(),ping=10,headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})


@router.post('',status_code=201)
async def import_layout_sample(file:UploadFile=File(...),request_id:UUID=Form(...),principal:Principal=Depends(require_principal)):
    """Compatibility entry: same operation budget and idempotency, wait for result."""
    name,format,raw=await _upload(file)
    try:
        state=await submit_operation(principal.id,request_id,name,format,raw)
        for _ in range(190):
            if state['status']=='completed' and state['source_id']:
                return await get_layout_sample(UUID(state['source_id']),principal)
            if state['status']=='failed':
                raise HTTPException(503 if state['error_category'] in {'transient','deadline'} else 422,state['error_code'])
            if state['status']=='canceled':
                raise HTTPException(409,'layout_operation_canceled')
            await asyncio.sleep(.25)
            state=await read_operation(principal.id,request_id)
        raise HTTPException(503,'layout_operation_deadline')
    except LayoutOperationError as error:
        raise _failure(error) from None


@router.get('/{source_id}')
async def get_layout_sample(source_id:UUID,principal:Principal=Depends(require_principal)):
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        row=await conn.fetchrow('SELECT * FROM research_layout_samples WHERE owner_id=$1::uuid AND source_id=$2::uuid',principal.id,source_id)
    if row is None:
        raise HTTPException(404,'Layout sample not found')
    return sample_record(row)
