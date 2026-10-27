"""Owner-scoped template inputs. Never creates research evidence or calls models."""
from __future__ import annotations

import asyncio
import json
from pathlib import PurePath
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from app.db.connection import get_db_pool
from app.report_layout import MAX_SAMPLE_BYTES, parse_layout_sample
from app.security.auth import Principal, require_principal

router = APIRouter(prefix='/layout-samples', dependencies=[Depends(require_principal)])


def sample_record(row):
    parsed = json.loads(row['parsed']) if isinstance(row['parsed'], str) else row['parsed']
    return {'source_id': str(row['source_id']), 'file_name': row['file_name'],
            'created_at': row['created_at'].isoformat(), **parsed}


@router.post('', status_code=201)
async def import_layout_sample(file: UploadFile = File(...), request_id: UUID = Form(...), principal: Principal = Depends(require_principal)):
    name = (file.filename or '').replace('\\', '/').rsplit('/', 1)[-1]
    if not name or len(name) > 240 or any(ord(c) < 32 for c in name):
        raise HTTPException(422, 'layout_invalid_file_name')
    format = PurePath(name).suffix.lower().lstrip('.')
    if format not in {'html', 'htm', 'docx'}:
        raise HTTPException(415, 'layout_format_not_supported')
    raw = await file.read(MAX_SAMPLE_BYTES + 1)
    if not raw or len(raw) > MAX_SAMPLE_BYTES:
        raise HTTPException(413, 'layout_sample_size_limit')
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("SELECT set_config('lock_timeout','3000',true)")
        await conn.fetchval('SELECT id FROM auth_principals WHERE id=$1::uuid FOR UPDATE', principal.id)
        prior = await conn.fetchrow('SELECT * FROM research_layout_samples WHERE owner_id=$1::uuid AND request_id=$2::uuid', principal.id, request_id)
        if prior:
            if bytes(prior['file_bytes']) != raw or prior['file_name'] != name:
                raise HTTPException(409, 'layout_request_id_payload_conflict')
            return sample_record(prior)
        count = await conn.fetchval('SELECT COUNT(*) FROM research_layout_samples WHERE owner_id=$1::uuid', principal.id)
        if count >= 50:
            raise HTTPException(409, 'layout_sample_limit_50')
        try:
            parsed = await asyncio.wait_for(asyncio.to_thread(parse_layout_sample, raw, format), timeout=15)
        except TimeoutError as error:
            raise HTTPException(422, 'layout_parse_timeout') from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        row = await conn.fetchrow('''INSERT INTO research_layout_samples(source_id,owner_id,request_id,file_name,format,file_bytes,parsed)
            VALUES($1::uuid,$2::uuid,$3::uuid,$4,$5,$6,$7::jsonb) RETURNING *''', uuid4(), principal.id, request_id, name, format, raw, json.dumps(parsed, ensure_ascii=False))
    return sample_record(row)


@router.get('/{source_id}')
async def get_layout_sample(source_id: UUID, principal: Principal = Depends(require_principal)):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow('SELECT * FROM research_layout_samples WHERE owner_id=$1::uuid AND source_id=$2::uuid', principal.id, source_id)
    if row is None:
        raise HTTPException(404, 'Layout sample not found')
    return sample_record(row)
