"""Versioned uploaded originals and owned research originals/page pixels.

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
CREATE TABLE IF NOT EXISTS document_source_originals (
 source_id UUID NOT NULL REFERENCES document_sources(id) ON DELETE CASCADE,
 owner_id UUID NOT NULL, parse_version_id TEXT NOT NULL, content_hash TEXT NOT NULL,
 original_bytes BYTEA NOT NULL CHECK(octet_length(original_bytes) BETWEEN 1 AND 12582912),
 byte_count INTEGER NOT NULL CHECK(byte_count=octet_length(original_bytes)),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(source_id,parse_version_id)
);
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
ALTER TABLE research_source_assets ADD COLUMN IF NOT EXISTS document_source_id UUID
 REFERENCES document_sources(id) ON DELETE CASCADE;
ALTER TABLE research_source_assets ADD COLUMN IF NOT EXISTS document_parse_version TEXT;
CREATE TABLE IF NOT EXISTS research_source_pages (
 asset_id UUID NOT NULL REFERENCES research_source_assets(asset_id) ON DELETE CASCADE,
 page INTEGER NOT NULL CHECK(page BETWEEN 1 AND 80), renderer TEXT NOT NULL,
 png BYTEA NOT NULL CHECK(octet_length(png)<=1500000),
 width INTEGER NOT NULL CHECK(width BETWEEN 1 AND 2000),
 height INTEGER NOT NULL CHECK(height BETWEEN 1 AND 2000),
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(asset_id,page,renderer), CHECK(width*height<=2000000)
);
CREATE TABLE IF NOT EXISTS research_source_figure_layouts (
 asset_id UUID NOT NULL REFERENCES research_source_assets(asset_id) ON DELETE CASCADE,
 extractor TEXT NOT NULL, payload JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(asset_id,extractor),
 CHECK(octet_length(payload::text)<=2000000)
);
'''


async def retain_document_original(conn,source_id,owner_id,parse_version_id,content_hash,original):
    """Retain uploaded bytes with their existing immutable source parse version."""
    if (not isinstance(original,bytes) or not original.startswith(b'%PDF-')
            or not 1<=len(original)<=MAX_ORIGINAL_BYTES):
        raise ValueError('source_asset_original_size_or_format')
    owned=await conn.fetchval('''SELECT 1 FROM document_sources WHERE id=$1::uuid AND owner_id=$2::uuid
        AND metadata->>'parse_version_id'=$3 AND metadata->>'content_hash'=$4''',
        str(source_id),str(owner_id),parse_version_id,content_hash)
    if not owned:raise ValueError('source_asset_document_version_changed')
    await conn.execute('''INSERT INTO document_source_originals
        (source_id,owner_id,parse_version_id,content_hash,original_bytes,byte_count)
        VALUES($1::uuid,$2::uuid,$3,$4,$5,$6) ON CONFLICT DO NOTHING''',
        str(source_id),str(owner_id),parse_version_id,content_hash,original,len(original))
    exact=await conn.fetchval('''SELECT 1 FROM document_source_originals WHERE source_id=$1::uuid
        AND owner_id=$2::uuid AND parse_version_id=$3 AND content_hash=$4 AND original_bytes=$5''',
        str(source_id),str(owner_id),parse_version_id,content_hash,original)
    if not exact:raise ValueError('source_asset_document_original_conflict')
    return {'status':'retained','format':'pdf','byte_count':len(original),'parse_version_id':parse_version_id}


async def _lock_execution(conn,binding,*,local_mode=False):
    row=await conn.fetchrow('''SELECT s.status,s.execution_id,p.is_active
        FROM research_sessions s LEFT JOIN auth_principals p ON p.id=s.owner_id
        WHERE s.id=$1::uuid AND s.owner_id=$2::uuid FOR UPDATE OF s''',
        binding['session_id'],binding['owner_id'])
    if (not row or (not row['is_active'] and not local_mode) or row['status']!='running'
            or str(row['execution_id'])!=str(binding['execution_id'])):
        raise ValueError('source_asset_execution_not_current')


async def retain_original(conn,binding,source_url,original,retained_text,*,local_mode=False,
                          document_source_id=None,parse_version_id=None):
    """Caller owns a transaction; serialize root quota with cancellation writes."""
    if (not isinstance(original,bytes) or not original.startswith(b'%PDF-')
            or not 1<=len(original)<=MAX_ORIGINAL_BYTES):
        raise ValueError('source_asset_original_size_or_format')
    if (not isinstance(retained_text,str) or not retained_text.strip()
            or len(retained_text.encode('utf-8'))>2_000_000
            or not isinstance(source_url,str) or not 1<=len(source_url)<=8192):
        raise ValueError('source_asset_parsed_version_invalid')
    await _lock_execution(conn,binding,local_mode=local_mode)
    if document_source_id is not None:
        owned=await conn.fetchval('''SELECT 1 FROM document_sources s JOIN document_source_originals o
            ON o.source_id=s.id AND o.owner_id=s.owner_id AND o.parse_version_id=s.metadata->>'parse_version_id'
            AND o.content_hash=s.metadata->>'content_hash'
            WHERE s.id=$1::uuid AND s.owner_id=$2::uuid AND s.metadata->>'parse_version_id'=$3
            AND s.original_text=$4 AND o.original_bytes=$5''',
            str(document_source_id),binding['owner_id'],parse_version_id,retained_text,original)
        if not owned:raise ValueError('source_asset_document_version_changed')
    # A repeated read of the very same bytes/text can reuse that immutable
    # original. A changed PDF, text or URL creates a distinct acquisition.
    prior=await conn.fetchval('''SELECT asset_id FROM research_source_assets
        WHERE session_id=$1::uuid AND owner_id=$2::uuid AND source_url=$3
          AND retained_text=$4 AND original_bytes=$5
          AND document_source_id IS NOT DISTINCT FROM $6::uuid
          AND document_parse_version IS NOT DISTINCT FROM $7::text LIMIT 1''',
        binding['session_id'],binding['owner_id'],source_url,retained_text,original,
        str(document_source_id) if document_source_id is not None else None,parse_version_id)
    if prior:return {'asset_id':str(prior),'status':'retained','format':'pdf','byte_count':len(original)}
    used=await conn.fetchval('''SELECT COALESCE(SUM(byte_count),0) FROM research_source_assets
        WHERE session_id=$1::uuid AND owner_id=$2::uuid''',binding['session_id'],binding['owner_id'])
    if int(used)+len(original)>MAX_TASK_BYTES:raise ValueError('source_asset_task_byte_limit')
    asset_id=uuid4()
    await conn.execute('''INSERT INTO research_source_assets
        (asset_id,session_id,owner_id,execution_id,source_url,format,original_bytes,byte_count,retained_text,document_source_id,document_parse_version)
        VALUES($1,$2::uuid,$3::uuid,$4::uuid,$5,'pdf',$6,$7,$8,$9::uuid,$10)''',asset_id,
        binding['session_id'],binding['owner_id'],binding['execution_id'],source_url,original,len(original),retained_text,
        str(document_source_id) if document_source_id is not None else None,parse_version_id)
    return {'asset_id':str(asset_id),'status':'retained','format':'pdf','byte_count':len(original)}


async def current_original(conn,session_id,owner_id,evidence,*,include_bytes=True):
    """No download or render: require the exact currently authorized text."""
    from uuid import UUID
    if not isinstance(evidence,dict):raise ValueError('source_asset_evidence_invalid')
    acquisition=evidence.get('acquisition') or {}
    ref=acquisition.get('source_asset') or {}
    from app.research_documents import source_document_format
    if acquisition.get('format')=='internal_source':
        if (evidence.get('source_type')!='knowledge_base' or evidence.get('collected_by')!='rag'
                or not acquisition.get('parse_version_id') or not acquisition.get('source_document_id')
                or acquisition['source_document_id']!=(acquisition.get('source_access_snapshot') or {}).get('source_id')):
            raise ValueError('source_asset_internal_evidence_binding_invalid')
    if (source_document_format(acquisition)!='pdf' or not isinstance(ref,dict)
            or ref.get('status')!='retained' or ref.get('format')!='pdf'):
        raise ValueError('source_asset_not_retained')
    try:asset_id=UUID(str(ref.get('asset_id')))
    except (ValueError,TypeError,AttributeError) as error:raise ValueError('source_asset_identity_invalid') from error
    row=await conn.fetchrow('''SELECT a.asset_id,a.source_url,a.byte_count,a.retained_text,a.execution_id,a.created_at,
        a.document_source_id,a.document_parse_version'''
        +(',a.original_bytes' if include_bytes else '')+''' FROM research_source_assets a
        JOIN research_sessions s ON s.id=a.session_id AND s.owner_id=a.owner_id
        WHERE a.asset_id=$1 AND a.session_id=$2::uuid AND a.owner_id=$3::uuid''',asset_id,str(session_id),str(owner_id))
    if (not row or row['source_url']!=evidence.get('source_url')
            or row['retained_text']!=evidence.get('content') or row['byte_count']!=ref.get('byte_count')):
        raise ValueError('source_asset_current_evidence_changed')
    if acquisition.get('format')=='internal_source' and (
            str(row['document_source_id'])!=acquisition['source_document_id']
            or row['document_parse_version']!=acquisition['parse_version_id']):
        raise ValueError('source_asset_internal_evidence_binding_invalid')
    return dict(row)


def _renderer_contract(renderer):
    from app.source_figure_extraction import FIGURE_RENDERER
    import re
    if not isinstance(renderer,str) or renderer!=PAGE_RENDERER and not re.fullmatch(re.escape(FIGURE_RENDERER)+r':[0-9a-f]{32}',renderer):
        raise ValueError('source_page_renderer_invalid')
    return renderer


async def retain_page(conn,binding,asset_id,page,png,width,height,*,local_mode=False,renderer=PAGE_RENDERER):
    renderer=_renderer_contract(renderer)
    if (type(page) is not int or not 1<=page<=80 or type(width) is not int or type(height) is not int
            or not 1<=width<=2000 or not 1<=height<=2000 or width*height>2_000_000
            or not isinstance(png,bytes) or not png.startswith(b'\x89PNG\r\n\x1a\n')
            or not 1<=len(png)<=MAX_PREVIEW_BYTES):raise ValueError('source_page_invalid')
    await _lock_execution(conn,binding,local_mode=local_mode)
    owned=await conn.fetchval('''SELECT 1 FROM research_source_assets WHERE asset_id=$1::uuid
        AND session_id=$2::uuid AND owner_id=$3::uuid''',str(asset_id),binding['session_id'],binding['owner_id'])
    if not owned:raise ValueError('source_asset_not_owned')
    if renderer!=PAGE_RENDERER:
        prior=await conn.fetchrow('''SELECT width,height FROM research_source_pages
            WHERE asset_id=$1::uuid AND page=$2 AND renderer=$3''',str(asset_id),page,renderer)
        if prior:
            if prior['width']!=width or prior['height']!=height:raise ValueError('source_figure_pixel_version_conflict')
            return
        used=await conn.fetchval('''SELECT COALESCE(SUM(octet_length(p.png)),0)
            FROM research_source_pages p JOIN research_source_assets a ON a.asset_id=p.asset_id
            WHERE a.session_id=$1::uuid AND a.owner_id=$2::uuid AND p.renderer<>$3''',
            binding['session_id'],binding['owner_id'],PAGE_RENDERER)
        if int(used)+len(png)>MAX_TASK_BYTES:raise ValueError('source_figure_pixel_task_byte_limit')
    await conn.execute('''INSERT INTO research_source_pages(asset_id,page,renderer,png,width,height)
        VALUES($1::uuid,$2,$3,$4,$5,$6) ON CONFLICT DO NOTHING''',str(asset_id),page,renderer,png,width,height)


async def current_page(conn,session_id,owner_id,evidence,page,*,renderer=PAGE_RENDERER):
    renderer=_renderer_contract(renderer)
    original=await current_original(conn,session_id,owner_id,evidence,include_bytes=False)
    row=await conn.fetchrow('''SELECT png,width,height,renderer FROM research_source_pages
        WHERE asset_id=$1 AND page=$2 AND renderer=$3''',original['asset_id'],page,renderer)
    return dict(row) if row else None


async def retain_figure_layout(conn,binding,evidence,layout,*,local_mode=False):
    """Immutable parser output owned by the existing original, not a new cache service."""
    import json
    from app.source_figure_extraction import EXTRACTOR,EXTRACTOR_REVISION,MAX_LAYOUT_BYTES,renderer_key
    if layout.get('extractor')!=EXTRACTOR or not isinstance(layout.get('figures'),list):
        raise ValueError('source_figure_layout_version_changed')
    if layout.get('source_revision')!=EXTRACTOR_REVISION or len(layout['figures'])>1000:
        raise ValueError('source_figure_layout_version_changed')
    for figure in layout['figures']:renderer_key(figure)
    encoded=json.dumps(layout,ensure_ascii=False)
    if len(encoded.encode('utf8'))>MAX_LAYOUT_BYTES:raise ValueError('source_figure_layout_byte_limit')
    await _lock_execution(conn,binding,local_mode=local_mode)
    original=await current_original(conn,binding['session_id'],binding['owner_id'],evidence,include_bytes=False)
    prior=await conn.fetchval('''SELECT payload FROM research_source_figure_layouts
        WHERE asset_id=$1 AND extractor=$2''',original['asset_id'],EXTRACTOR)
    if prior is not None:
        if isinstance(prior,str):prior=json.loads(prior)
        if prior!=layout:raise ValueError('source_figure_layout_version_conflict')
        return
    used=await conn.fetchval('''SELECT COALESCE(SUM(octet_length(l.payload::text)),0)
        FROM research_source_figure_layouts l JOIN research_source_assets a ON a.asset_id=l.asset_id
        WHERE a.session_id=$1::uuid AND a.owner_id=$2::uuid''',binding['session_id'],binding['owner_id'])
    if int(used)+len(encoded.encode('utf8'))>MAX_TASK_BYTES:raise ValueError('source_figure_layout_task_byte_limit')
    await conn.execute('''INSERT INTO research_source_figure_layouts(asset_id,extractor,payload)
        VALUES($1,$2,$3::jsonb) ON CONFLICT DO NOTHING''',original['asset_id'],EXTRACTOR,encoded)
    stored=await conn.fetchval('''SELECT payload FROM research_source_figure_layouts
        WHERE asset_id=$1 AND extractor=$2''',original['asset_id'],EXTRACTOR)
    if isinstance(stored,str):stored=json.loads(stored)
    if stored!=layout:raise ValueError('source_figure_layout_version_conflict')


async def current_figure_layout(conn,session_id,owner_id,evidence):
    import json
    from app.source_figure_extraction import EXTRACTOR
    original=await current_original(conn,session_id,owner_id,evidence,include_bytes=False)
    stored=await conn.fetchval('''SELECT payload FROM research_source_figure_layouts
        WHERE asset_id=$1 AND extractor=$2''',original['asset_id'],EXTRACTOR)
    return json.loads(stored) if isinstance(stored,str) else stored
