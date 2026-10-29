"""Immutable originals and page pixels scoped to an owned research task.

The caller supplies evidence from the current authorized task snapshot. A UUID
is only a locator; the retained text and URL must still match that evidence.
"""
from __future__ import annotations

from uuid import uuid4

MAX_ORIGINAL_BYTES=12*1024*1024
MAX_TASK_BYTES=64*1024*1024
MAX_PREVIEW_BYTES=1_500_000
PAGE_RENDERER='adrs-original-pdf-page-v1'

SCHEMA_SQL='''
CREATE TABLE IF NOT EXISTS research_source_assets (
 asset_id UUID PRIMARY KEY,
 session_id UUID NOT NULL REFERENCES research_sessions(id) ON DELETE CASCADE,
 owner_id UUID NOT NULL, execution_id UUID NOT NULL,
 source_url TEXT NOT NULL, format TEXT NOT NULL CHECK(format='pdf'),
 original_bytes BYTEA NOT NULL CHECK(octet_length(original_bytes)<=12582912),
 byte_count INTEGER NOT NULL CHECK(byte_count=octet_length(original_bytes)),
 retained_text TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_source_assets_owner_task
 ON research_source_assets(owner_id,session_id);
CREATE TABLE IF NOT EXISTS research_source_pages (
 asset_id UUID NOT NULL REFERENCES research_source_assets(asset_id) ON DELETE CASCADE,
 page INTEGER NOT NULL CHECK(page BETWEEN 1 AND 80), renderer TEXT NOT NULL,
 png BYTEA NOT NULL CHECK(octet_length(png)<=1500000),
 width INTEGER NOT NULL CHECK(width BETWEEN 1 AND 2000),
 height INTEGER NOT NULL CHECK(height BETWEEN 1 AND 2000),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(asset_id,page,renderer), CHECK(width*height<=2000000)
);
'''


async def _lock_execution(conn,binding,*,local_mode=False):
    row=await conn.fetchrow('''SELECT s.status,s.execution_id,p.is_active
        FROM research_sessions s LEFT JOIN auth_principals p ON p.id=s.owner_id
        WHERE s.id=$1::uuid AND s.owner_id=$2::uuid FOR UPDATE OF s''',
        binding['session_id'],binding['owner_id'])
    if (not row or (not row['is_active'] and not local_mode) or row['status']!='running'
            or str(row['execution_id'])!=str(binding['execution_id'])):
        raise ValueError('source_asset_execution_not_current')


async def retain_original(conn,binding,source_url,original,retained_text,*,local_mode=False):
    """Caller owns a transaction; serialize root quota with cancellation writes."""
    if (not isinstance(original,bytes) or not original.startswith(b'%PDF-')
            or not 1<=len(original)<=MAX_ORIGINAL_BYTES):
        raise ValueError('source_asset_original_size_or_format')
    if (not isinstance(retained_text,str) or not retained_text.strip()
            or len(retained_text.encode('utf-8'))>2_000_000
            or not isinstance(source_url,str) or not 1<=len(source_url)<=8192):
        raise ValueError('source_asset_parsed_version_invalid')
    await _lock_execution(conn,binding,local_mode=local_mode)
    # A repeated read of the very same bytes/text can reuse that immutable
    # original. A changed PDF, text or URL creates a distinct acquisition.
    prior=await conn.fetchval('''SELECT asset_id FROM research_source_assets
        WHERE session_id=$1::uuid AND owner_id=$2::uuid AND source_url=$3
          AND retained_text=$4 AND original_bytes=$5 LIMIT 1''',
        binding['session_id'],binding['owner_id'],source_url,retained_text,original)
    if prior:return {'asset_id':str(prior),'status':'retained','format':'pdf','byte_count':len(original)}
    used=await conn.fetchval('''SELECT COALESCE(SUM(byte_count),0) FROM research_source_assets
        WHERE session_id=$1::uuid AND owner_id=$2::uuid''',binding['session_id'],binding['owner_id'])
    if int(used)+len(original)>MAX_TASK_BYTES:raise ValueError('source_asset_task_byte_limit')
    asset_id=uuid4()
    await conn.execute('''INSERT INTO research_source_assets
        (asset_id,session_id,owner_id,execution_id,source_url,format,original_bytes,byte_count,retained_text)
        VALUES($1,$2::uuid,$3::uuid,$4::uuid,$5,'pdf',$6,$7,$8)''',asset_id,
        binding['session_id'],binding['owner_id'],binding['execution_id'],source_url,original,len(original),retained_text)
    return {'asset_id':str(asset_id),'status':'retained','format':'pdf','byte_count':len(original)}


async def current_original(conn,session_id,owner_id,evidence,*,include_bytes=True):
    """No download or render: require the exact currently authorized text."""
    from uuid import UUID
    if not isinstance(evidence,dict):raise ValueError('source_asset_evidence_invalid')
    acquisition=evidence.get('acquisition') or {}
    ref=acquisition.get('source_asset') or {}
    if (acquisition.get('format')!='pdf' or not isinstance(ref,dict)
            or ref.get('status')!='retained' or ref.get('format')!='pdf'):
        raise ValueError('source_asset_not_retained')
    try:asset_id=UUID(str(ref.get('asset_id')))
    except (ValueError,TypeError,AttributeError) as error:raise ValueError('source_asset_identity_invalid') from error
    row=await conn.fetchrow('''SELECT a.asset_id,a.source_url,a.byte_count,a.retained_text,a.execution_id,a.created_at'''
        +(',a.original_bytes' if include_bytes else '')+''' FROM research_source_assets a
        JOIN research_sessions s ON s.id=a.session_id AND s.owner_id=a.owner_id
        WHERE a.asset_id=$1 AND a.session_id=$2::uuid AND a.owner_id=$3::uuid''',asset_id,str(session_id),str(owner_id))
    if (not row or row['source_url']!=evidence.get('source_url')
            or row['retained_text']!=evidence.get('content') or row['byte_count']!=ref.get('byte_count')):
        raise ValueError('source_asset_current_evidence_changed')
    return dict(row)


async def retain_page(conn,binding,asset_id,page,png,width,height,*,local_mode=False):
    if (type(page) is not int or not 1<=page<=80 or type(width) is not int or type(height) is not int
            or not 1<=width<=2000 or not 1<=height<=2000 or width*height>2_000_000
            or not isinstance(png,bytes) or not png.startswith(b'\x89PNG\r\n\x1a\n')
            or not 1<=len(png)<=MAX_PREVIEW_BYTES):raise ValueError('source_page_invalid')
    await _lock_execution(conn,binding,local_mode=local_mode)
    owned=await conn.fetchval('''SELECT 1 FROM research_source_assets WHERE asset_id=$1::uuid
        AND session_id=$2::uuid AND owner_id=$3::uuid''',str(asset_id),binding['session_id'],binding['owner_id'])
    if not owned:raise ValueError('source_asset_not_owned')
    await conn.execute('''INSERT INTO research_source_pages(asset_id,page,renderer,png,width,height)
        VALUES($1::uuid,$2,$3,$4,$5,$6) ON CONFLICT DO NOTHING''',str(asset_id),page,PAGE_RENDERER,png,width,height)


async def current_page(conn,session_id,owner_id,evidence,page):
    original=await current_original(conn,session_id,owner_id,evidence,include_bytes=False)
    row=await conn.fetchrow('''SELECT png,width,height,renderer FROM research_source_pages
        WHERE asset_id=$1 AND page=$2 AND renderer=$3''',original['asset_id'],page,PAGE_RENDERER)
    return dict(row) if row else None
