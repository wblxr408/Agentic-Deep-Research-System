"""Owner-scoped, bounded sample parsing operations; never starts research."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import UUID, uuid4

from app.db.connection import get_db_pool
from app.report_layout import MAX_SAMPLE_BYTES, ReportLayout, VERSION as LAYOUT_VERSION

logger = logging.getLogger(__name__)
OPERATION_SECONDS = 45
ATTEMPT_SECONDS = 15
LEASE_SECONDS = 20
MAX_ATTEMPTS = 3
MAX_OWNER_ACTIVE = 2
MAX_GLOBAL_ACTIVE = 4
MAX_OWNER_OPERATIONS = 500
TERMINAL = frozenset({'completed', 'failed', 'canceled'})
STAGES = frozenset({'reading', 'cleaning', 'preview'})
DIFFERENCES = frozenset({'complex_css_requires_adjustment','source_scripts_not_used','external_assets_omitted',
                         'source_images_omitted','floating_objects_require_adjustment'})
PARSER_FAILURES = frozenset({'layout_sample_size_limit','layout_requires_utf8','layout_format_not_supported',
    'layout_structure_not_found','layout_invalid_docx','layout_docx_xml_limit','layout_docx_expansion_limit',
    'layout_document_complexity_limit','layout_component_limit','layout_section_limit','layout_style_limit',
    'layout_style_complexity_limit','layout_invalid_document','layout_parser_internal'})


class LayoutOperationError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status, self.code = status, code


def public_operation(row):
    return {'operation_id':str(row['operation_id']), 'status':row['status'], 'stage':row['stage'],
        'revision':row['revision'], 'file_name':row['file_name'], 'format':row['format'],
        'source_id':str(row['source_id']) if row['source_id'] else None,
        'attempts':row['attempts'], 'max_attempts':row['max_attempts'],
        'error_code':row['error_code'], 'error_category':row['error_category'],
        'deadline_at':row['deadline_at'].isoformat(), 'updated_at':row['updated_at'].isoformat(),
        'budget':{'max_bytes':MAX_SAMPLE_BYTES,'max_attempts':row['max_attempts'],
                  'attempt_seconds':ATTEMPT_SECONDS,'operation_seconds':OPERATION_SECONDS,
                  'model_calls':0,'network_calls':0}}


async def _event(conn, row):
    await conn.execute('''INSERT INTO research_layout_operation_events
        (owner_id,operation_id,sequence,status,stage,attempt,error_code,error_category)
        VALUES($1::uuid,$2::uuid,$3,$4,$5,$6,$7,$8)''',row['owner_id'],row['operation_id'],row['revision'],
        row['status'],row['stage'],row['attempts'],row['error_code'],row['error_category'])


async def _lock_owner(conn, owner_id):
    await conn.execute("SELECT set_config('lock_timeout','3000',true)")
    row = await conn.fetchrow('SELECT id,is_active FROM auth_principals WHERE id=$1::uuid FOR UPDATE', str(owner_id))
    if not row or not row['is_active']:
        raise LayoutOperationError(404, 'layout_owner_unavailable')


async def _prune_owner(conn, owner_id):
    # Only terminal operation metadata is ephemeral; saved samples are separate.
    await conn.execute('''DELETE FROM research_layout_operations WHERE owner_id=$1::uuid
        AND status IN ('completed','failed','canceled') AND updated_at<NOW()-INTERVAL '7 days' ''', str(owner_id))


async def submit_operation(owner_id, operation_id:UUID, name:str, format:str, raw:bytes):
    if format not in {'html','htm','docx'}:
        raise LayoutOperationError(415,'layout_format_not_supported')
    if not raw or len(raw)>MAX_SAMPLE_BYTES:
        raise LayoutOperationError(413,'layout_sample_size_limit')
    fingerprint=hashlib.sha256(raw).hexdigest()
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await _lock_owner(conn,owner_id)
        await _prune_owner(conn,owner_id)
        existing=await conn.fetchrow('''SELECT * FROM research_layout_operations
            WHERE owner_id=$1::uuid AND operation_id=$2::uuid FOR UPDATE''',str(owner_id),operation_id)
        if existing:
            # A cancellation can arrive before the upload finishes. Its
            # tombstone wins and the same request cannot later create a job.
            if existing['status']=='canceled' and existing['file_identity'] is None:
                return public_operation(existing)
            if existing['file_identity']!=fingerprint or existing['file_size']!=len(raw) or existing['file_name']!=name:
                raise LayoutOperationError(409,'layout_request_id_payload_conflict')
            return public_operation(existing)
        total=await conn.fetchval('SELECT COUNT(*) FROM research_layout_operations WHERE owner_id=$1::uuid',str(owner_id))
        if total>=MAX_OWNER_OPERATIONS:
            raise LayoutOperationError(429,'layout_operation_limit')
        sample=await conn.fetchrow('''SELECT * FROM research_layout_samples WHERE owner_id=$1::uuid AND request_id=$2::uuid''',str(owner_id),operation_id)
        if sample:
            if bytes(sample['file_bytes'])!=raw or sample['file_name']!=name:
                raise LayoutOperationError(409,'layout_request_id_payload_conflict')
            row=await conn.fetchrow('''INSERT INTO research_layout_operations
                (owner_id,operation_id,status,stage,file_name,format,file_size,file_identity,source_id,deadline_at)
                VALUES($1::uuid,$2::uuid,'completed','completed',$3,$4,$5,$6,$7::uuid,NOW()+INTERVAL '45 seconds') RETURNING *''',
                str(owner_id),operation_id,name,format,len(raw),fingerprint,sample['source_id'])
        else:
            active=await conn.fetchval('''SELECT COUNT(*) FROM research_layout_operations
                WHERE owner_id=$1::uuid AND status IN ('queued','running')''',str(owner_id))
            if active>=MAX_OWNER_ACTIVE:
                raise LayoutOperationError(429,'layout_owner_active_limit')
            count=await conn.fetchval('SELECT COUNT(*) FROM research_layout_samples WHERE owner_id=$1::uuid',str(owner_id))
            if count>=50:
                raise LayoutOperationError(409,'layout_sample_limit_50')
            row=await conn.fetchrow('''INSERT INTO research_layout_operations
                (owner_id,operation_id,status,stage,file_name,format,file_size,file_identity,file_bytes,not_before,deadline_at)
                VALUES($1::uuid,$2::uuid,'queued','queued',$3,$4,$5,$6,$7,NOW(),NOW()+INTERVAL '45 seconds') RETURNING *''',
                str(owner_id),operation_id,name,format,len(raw),fingerprint,raw)
        await _event(conn,row)
    return public_operation(row)


async def read_operation(owner_id,operation_id):
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        row=await conn.fetchrow('''SELECT * FROM research_layout_operations WHERE owner_id=$1::uuid AND operation_id=$2::uuid''',
            str(owner_id),operation_id)
    if not row:
        raise LayoutOperationError(404,'layout_operation_not_found')
    return public_operation(row)


async def cancel_operation(owner_id,operation_id):
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await _lock_owner(conn,owner_id)
        await _prune_owner(conn,owner_id)
        row=await conn.fetchrow('''SELECT * FROM research_layout_operations
            WHERE owner_id=$1::uuid AND operation_id=$2::uuid FOR UPDATE''',str(owner_id),operation_id)
        if not row:
            count=await conn.fetchval('SELECT COUNT(*) FROM research_layout_operations WHERE owner_id=$1::uuid',str(owner_id))
            if count>=MAX_OWNER_OPERATIONS:
                raise LayoutOperationError(429,'layout_operation_limit')
            row=await conn.fetchrow('''INSERT INTO research_layout_operations(owner_id,operation_id,status,stage,deadline_at,error_category)
                VALUES($1::uuid,$2::uuid,'canceled','canceled',NOW()+INTERVAL '45 seconds','canceled') RETURNING *''',str(owner_id),operation_id)
            await _event(conn,row)
        elif row['status'] not in TERMINAL:
            row=await conn.fetchrow('''UPDATE research_layout_operations SET status='canceled',stage='canceled',
                error_category='canceled',file_bytes=NULL,run_token=NULL,lease_until=NULL,revision=revision+1,updated_at=NOW()
                WHERE owner_id=$1::uuid AND operation_id=$2::uuid RETURNING *''',str(owner_id),operation_id)
            await _event(conn,row)
    return public_operation(row)


async def _transition_stage(owner_id,operation_id,run_token,stage):
    if stage not in STAGES:
        return False
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        row=await conn.fetchrow('''UPDATE research_layout_operations SET stage=$4,revision=revision+1,updated_at=NOW()
            WHERE owner_id=$1::uuid AND operation_id=$2::uuid AND run_token=$3::uuid
              AND status='running' AND deadline_at>NOW() RETURNING *''',str(owner_id),operation_id,run_token,stage)
        if row:
            await _event(conn,row)
    return bool(row)


async def _still_running(owner_id,operation_id,run_token):
    pool=await get_db_pool()
    async with pool.acquire() as conn:
        return bool(await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM research_layout_operations o
            JOIN auth_principals p ON p.id=o.owner_id AND p.is_active=TRUE
            WHERE o.owner_id=$1::uuid AND o.operation_id=$2::uuid AND o.run_token=$3::uuid
              AND o.status='running' AND o.deadline_at>NOW() AND o.lease_until>NOW())''',str(owner_id),operation_id,run_token))


def _category(code):
    if code in {'layout_worker_unavailable','layout_worker_exited','layout_worker_interrupted'}:
        return 'transient'
    if code in {'layout_parse_timeout','layout_operation_deadline'}:
        return 'deadline'
    if code in {'layout_sample_size_limit','layout_component_limit','layout_section_limit','layout_document_complexity_limit',
                'layout_style_limit','layout_style_complexity_limit','layout_docx_expansion_limit','layout_docx_xml_limit','layout_sample_limit_50'}:
        return 'resource_limit'
    return 'invalid_document'


def _sanitize_result(parsed,format):
    """Accept only the content-free layout and bounded structural locations."""
    if len(json.dumps(parsed,ensure_ascii=False).encode('utf-8'))>500_000:
        raise ValueError('layout_document_complexity_limit')
    layout=ReportLayout.model_validate(parsed.get('layout'))
    metadata=parsed.get('parse')
    if not isinstance(metadata,dict) or metadata.get('parser_version')!=LAYOUT_VERSION or metadata.get('model_calls')!=0:
        raise ValueError('layout_invalid_document')
    if metadata.get('format')!=('html' if format in {'html','htm'} else 'docx') or metadata.get('source_content_retained_in_layout') is not False:
        raise ValueError('layout_invalid_document')
    allowed_ids={section.section_id for section in layout.sections}|{block.block_id for section in layout.sections for block in section.blocks}
    locations=metadata.get('locations')
    if not isinstance(locations,dict) or set(locations)-allowed_ids:
        raise ValueError('layout_invalid_document')
    clean_locations={}
    for key,value in locations.items():
        if not isinstance(value,dict) or set(value)-{'line','column','element'} or any(
                isinstance(item,bool) or not isinstance(item,int) or not 0<=item<=2_000_000 for item in value.values()):
            raise ValueError('layout_invalid_document')
        clean_locations[key]=value
    differences=metadata.get('differences')
    if not isinstance(differences,list) or len(differences)>len(DIFFERENCES) or any(not isinstance(item,str) or item not in DIFFERENCES for item in differences):
        raise ValueError('layout_invalid_document')
    return {'layout':layout.model_dump(mode='json'),'parse':{'format':metadata['format'],
        'parser_version':LAYOUT_VERSION,'model_calls':0,'locations':clean_locations,
        'differences':differences,'source_content_retained_in_layout':False}}


async def _fail(owner_id,operation_id,run_token,code):
    category=_category(code)
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        row=await conn.fetchrow('''SELECT * FROM research_layout_operations
            WHERE owner_id=$1::uuid AND operation_id=$2::uuid FOR UPDATE''',str(owner_id),operation_id)
        if not row or row['status']!='running' or str(row['run_token'])!=str(run_token):
            return
        can_retry=category=='transient' and row['attempts']<row['max_attempts'] and await conn.fetchval('SELECT $1::timestamptz>NOW()+INTERVAL \'2 seconds\'',row['deadline_at'])
        row=await conn.fetchrow('''UPDATE research_layout_operations SET status=$4,stage=$5,
            error_code=$6,error_category=$7,not_before=NOW()+($8::double precision*INTERVAL '1 second'),
            run_token=NULL,lease_until=NULL,file_bytes=CASE WHEN $4='failed' THEN NULL ELSE file_bytes END,
            revision=revision+1,updated_at=NOW() WHERE owner_id=$1::uuid AND operation_id=$2::uuid AND run_token=$3::uuid RETURNING *''',
            str(owner_id),operation_id,run_token,'queued' if can_retry else 'failed','retrying' if can_retry else 'failed',
            code,category,0.35*(2**max(0,row['attempts']-1)))
        if row:
            await _event(conn,row)


async def _complete(owner_id,operation_id,run_token,parsed):
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await _lock_owner(conn,owner_id)
        row=await conn.fetchrow('''SELECT * FROM research_layout_operations WHERE owner_id=$1::uuid
            AND operation_id=$2::uuid FOR UPDATE''',str(owner_id),operation_id)
        if not row or row['status']!='running' or str(row['run_token'])!=str(run_token):
            return False
        if not await conn.fetchval('SELECT $1::timestamptz>NOW()',row['deadline_at']):
            return False
        try:
            parsed=_sanitize_result(parsed,row['format'])
        except (TypeError,ValueError) as error:
            raise LayoutOperationError(422,str(error) if str(error) in PARSER_FAILURES else 'layout_invalid_document') from None
        existing=await conn.fetchrow('''SELECT * FROM research_layout_samples WHERE owner_id=$1::uuid AND request_id=$2::uuid''',str(owner_id),operation_id)
        if existing:
            if bytes(existing['file_bytes'])!=bytes(row['file_bytes']) or existing['file_name']!=row['file_name']:
                raise LayoutOperationError(409,'layout_request_id_payload_conflict')
            source_id=existing['source_id']
        else:
            count=await conn.fetchval('SELECT COUNT(*) FROM research_layout_samples WHERE owner_id=$1::uuid',str(owner_id))
            if count>=50:
                raise LayoutOperationError(409,'layout_sample_limit_50')
            source_id=uuid4()
            await conn.execute('''INSERT INTO research_layout_samples(source_id,owner_id,request_id,file_name,format,file_bytes,parsed)
                VALUES($1::uuid,$2::uuid,$3::uuid,$4,$5,$6,$7::jsonb)''',source_id,str(owner_id),operation_id,
                row['file_name'],row['format'],row['file_bytes'],json.dumps(parsed,ensure_ascii=False))
        row=await conn.fetchrow('''UPDATE research_layout_operations SET status='completed',stage='completed',source_id=$4::uuid,
            error_code=NULL,error_category=NULL,file_bytes=NULL,run_token=NULL,lease_until=NULL,revision=revision+1,updated_at=NOW()
            WHERE owner_id=$1::uuid AND operation_id=$2::uuid AND run_token=$3::uuid RETURNING *''',
            str(owner_id),operation_id,run_token,source_id)
        if row:
            await _event(conn,row)
    return bool(row)


async def _claim_next():
    pool=await get_db_pool()
    async with pool.acquire() as conn,conn.transaction():
        await conn.execute('SELECT pg_advisory_xact_lock(73120472)')
        # A crashed worker cannot extend the original deadline or retry budget.
        expired=await conn.fetch('''UPDATE research_layout_operations SET status='failed',stage='failed',
            error_code='layout_operation_deadline',error_category='deadline',file_bytes=NULL,run_token=NULL,lease_until=NULL,
            revision=revision+1,updated_at=NOW() WHERE status IN ('queued','running') AND deadline_at<=NOW() RETURNING *''')
        for row in expired:
            await _event(conn,row)
        interrupted=await conn.fetch('''UPDATE research_layout_operations SET
            status=CASE WHEN attempts<max_attempts THEN 'queued' ELSE 'failed' END,
            stage=CASE WHEN attempts<max_attempts THEN 'retrying' ELSE 'failed' END,
            error_code='layout_worker_interrupted',error_category='transient',
            file_bytes=CASE WHEN attempts<max_attempts THEN file_bytes ELSE NULL END,
            run_token=NULL,lease_until=NULL,not_before=NOW(),revision=revision+1,updated_at=NOW()
            WHERE status='running' AND lease_until<=NOW() AND deadline_at>NOW() RETURNING *''')
        for row in interrupted:
            await _event(conn,row)
        running=await conn.fetchval("SELECT COUNT(*) FROM research_layout_operations WHERE status='running' AND lease_until>NOW()")
        if running>=MAX_GLOBAL_ACTIVE:
            return None
        candidate=await conn.fetchrow('''SELECT o.* FROM research_layout_operations o
            JOIN auth_principals p ON p.id=o.owner_id AND p.is_active=TRUE
            WHERE o.status='queued' AND o.deadline_at>NOW() AND o.not_before<=NOW()
            AND (SELECT COUNT(*) FROM research_layout_operations active WHERE active.owner_id=o.owner_id
                 AND active.status='running' AND active.lease_until>NOW())<$1
            ORDER BY o.created_at LIMIT 1 FOR UPDATE OF o SKIP LOCKED''',MAX_OWNER_ACTIVE)
        if not candidate:
            return None
        row=await conn.fetchrow('''UPDATE research_layout_operations SET status='running',stage='starting',
            run_token=$3::uuid,attempts=attempts+1,lease_until=NOW()+INTERVAL '20 seconds',
            error_code=NULL,error_category=NULL,revision=revision+1,updated_at=NOW()
            WHERE owner_id=$1::uuid AND operation_id=$2::uuid RETURNING *''',candidate['owner_id'],candidate['operation_id'],uuid4())
        await _event(conn,row)
        return dict(row)


async def _execute(row):
    owner_id,operation_id,run_token=row['owner_id'],row['operation_id'],row['run_token']
    process=None;read_task=None
    try:
        if not await _still_running(owner_id,operation_id,run_token):
            return
        # The child receives only these bytes and an allowlisted environment.
        with tempfile.TemporaryFile() as source:
            source.write(bytes(row['file_bytes']));source.seek(0)
            environment={key:value for key,value in os.environ.items()
                if key.upper() in {'PATH','SYSTEMROOT','WINDIR','TEMP','TMP','LANG','LC_ALL'}}
            environment['PYTHONUTF8']='1'
            try:
                process=subprocess.Popen([sys.executable,'-I',str(Path(__file__).with_name('layout_parse_worker.py').resolve()),row['format']],
                    stdin=source,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=environment,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            except OSError:
                await _fail(owner_id,operation_id,run_token,'layout_worker_unavailable')
                return
            loop=asyncio.get_running_loop();started=loop.time();read_task=asyncio.create_task(asyncio.to_thread(process.stdout.readline,500_001))
            try:
                while True:
                    done,_=await asyncio.wait({read_task},timeout=.25)
                    if not await _still_running(owner_id,operation_id,run_token):
                        return
                    if loop.time()-started>=ATTEMPT_SECONDS:
                        await _fail(owner_id,operation_id,run_token,'layout_parse_timeout')
                        return
                    if not done:
                        continue
                    line=read_task.result()
                    if not line:
                        await _fail(owner_id,operation_id,run_token,'layout_worker_exited')
                        return
                    if len(line)>500_000 or not line.endswith(b'\n'):
                        await _fail(owner_id,operation_id,run_token,'layout_document_complexity_limit')
                        return
                    try:
                        message=json.loads(line)
                    except (ValueError,UnicodeDecodeError):
                        await _fail(owner_id,operation_id,run_token,'layout_worker_exited')
                        return
                    if message.get('event')=='stage':
                        if not await _transition_stage(owner_id,operation_id,run_token,message.get('stage')):
                            return
                    elif message.get('event')=='failure':
                        code=message.get('code')
                        await _fail(owner_id,operation_id,run_token,code if isinstance(code,str) and code in PARSER_FAILURES else 'layout_parser_internal')
                        return
                    elif message.get('event')=='result' and isinstance(message.get('result'),dict):
                        try:
                            await _complete(owner_id,operation_id,run_token,message['result'])
                        except LayoutOperationError as error:
                            await _fail(owner_id,operation_id,run_token,error.code)
                        return
                    else:
                        await _fail(owner_id,operation_id,run_token,'layout_worker_exited')
                        return
                    read_task=asyncio.create_task(asyncio.to_thread(process.stdout.readline,500_001))
            finally:
                if process.poll() is None:
                    try:process.kill()
                    except ProcessLookupError:pass
                await asyncio.to_thread(process.wait)
                if read_task and not read_task.done():
                    await asyncio.gather(read_task,return_exceptions=True)
                if process.stdout:
                    process.stdout.close()
    except asyncio.CancelledError:
        raise
    except Exception:
        # On lost storage the lease expires and the dispatcher resumes within
        # the original deadline; raw document text never enters the log.
        logger.warning('Layout operation worker interrupted',extra={'operation_id':str(operation_id)})


class LayoutDispatcher:
    def __init__(self):
        self._runner=None
        self._workers=set()

    def start(self):
        if self._runner is None:
            self._runner=asyncio.create_task(self._run(),name='layout-operation-dispatcher')

    async def _run(self):
        while True:
            try:
                while len(self._workers)<MAX_GLOBAL_ACTIVE:
                    row=await _claim_next()
                    if not row:
                        break
                    task=asyncio.create_task(_execute(row),name='layout-operation')
                    self._workers.add(task);task.add_done_callback(self._workers.discard)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning('Layout dispatcher temporarily unavailable')
            await asyncio.sleep(.5)

    async def stop(self):
        if self._runner:
            self._runner.cancel();await asyncio.gather(self._runner,return_exceptions=True);self._runner=None
        workers=list(self._workers)
        for task in workers:
            task.cancel()
        await asyncio.gather(*workers,return_exceptions=True)
        self._workers.clear()
