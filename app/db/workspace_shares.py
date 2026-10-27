"""Explicit, read-only shares of owned versions; no owner credential delegation."""
from __future__ import annotations

from app.db.connection import get_db_pool
from app.db.shared_workspaces import actor, locked_workspace, membership
from app.disclosure import redact_text
from app.query_understanding import identity


def document_version(revision, updated_at):
    return f'source:{int(revision or 0)}:{updated_at.isoformat()}'


async def _resource(conn, owner_id, kind, resource_id, version, *, content=False):
    """Lock and recheck the original resource and its retention policy on each read."""
    if kind == 'report':
        row = await conn.fetchrow('''SELECT s.user_query,r.report_id,r.sequence,
                r.payload->>'kind' AS kind,r.payload->>'status' AS report_status,
                CASE WHEN $4 THEN r.payload->>'report' ELSE NULL END AS content
            FROM research_report_versions r JOIN research_sessions s ON s.id=r.session_id AND s.owner_id=r.owner_id
            JOIN auth_principals p ON p.id=s.owner_id AND p.is_active
            WHERE r.owner_id=$1::uuid AND r.session_id=$2::uuid AND r.report_id=$3
                AND r.payload->>'kind'='report' AND r.payload->>'status' IN ('supported_report','saved_draft')
            FOR SHARE OF s,r''',str(owner_id),str(resource_id),version,content)
        if not row: return None
        return {'title':redact_text(row['user_query']), 'version':row['report_id'],
                'report_status':row['report_status'], 'content':redact_text(row['content']) if content else None}
    if kind != 'document': return None
    row = await conn.fetchrow('''SELECT s.name,s.status,s.updated_at,
            CASE WHEN $3 THEN s.original_text ELSE NULL END AS content
        FROM document_sources s JOIN auth_principals p ON p.id=s.owner_id AND p.is_active
        WHERE s.owner_id=$1::uuid AND s.id=$2::uuid FOR SHARE OF s''',str(owner_id),str(resource_id),content)
    if not row or row['status'] != 'active': return None
    lifecycle = await conn.fetchrow('''SELECT revision,state,is_current,reuse_scope,
        (valid_from IS NULL OR valid_from<=CURRENT_TIMESTAMP) AS started,
        (valid_until IS NULL OR valid_until>CURRENT_TIMESTAMP) AS unexpired
        FROM document_source_lifecycle WHERE owner_id=$1::uuid AND source_id=$2::uuid FOR SHARE''',str(owner_id),str(resource_id))
    if lifecycle and (lifecycle['state']!='retained' or not lifecycle['is_current'] or
                      not lifecycle['started'] or not lifecycle['unexpired'] or lifecycle['reuse_scope']=='task'):
        return None
    actual = document_version(lifecycle['revision'] if lifecycle else 0,row['updated_at'])
    if actual != version: return None
    return {'title':redact_text(row['name']),'version':actual,
            'content':redact_text(row['content'] or '') if content else None}


async def shareable(principal, workspace_id):
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
        await actor(conn,principal)
        await locked_workspace(conn,workspace_id)
        await membership(conn,workspace_id,principal.id)
        reports = await conn.fetch('''SELECT r.session_id,r.report_id,r.sequence,s.user_query,
                r.payload->>'status' AS report_status,r.created_at
            FROM research_report_versions r JOIN research_sessions s ON s.id=r.session_id AND s.owner_id=r.owner_id
            WHERE r.owner_id=$1::uuid AND r.payload->>'kind'='report'
                AND r.payload->>'status' IN ('supported_report','saved_draft')
            ORDER BY r.created_at DESC,r.sequence DESC LIMIT 200''',principal.id)
        documents = await conn.fetch('''SELECT s.id,s.name,s.updated_at,COALESCE(l.revision,0) AS revision
            FROM document_sources s LEFT JOIN document_source_lifecycle l ON l.source_id=s.id AND l.owner_id=s.owner_id
            WHERE s.owner_id=$1::uuid AND s.status='active' AND (l.source_id IS NULL OR
                (l.state='retained' AND l.is_current AND l.reuse_scope IN ('group','owner')
                 AND (l.valid_from IS NULL OR l.valid_from<=NOW()) AND (l.valid_until IS NULL OR l.valid_until>NOW())))
            ORDER BY s.updated_at DESC,s.id LIMIT 200''',principal.id)
    return {'reports':[{'resource_id':str(row['session_id']),'version':row['report_id'],
                        'sequence':row['sequence'],'title':redact_text(row['user_query']),
                        'status':row['report_status']} for row in reports],
            'documents':[{'resource_id':str(row['id']),'version':document_version(row['revision'],row['updated_at']),
                          'title':redact_text(row['name'])} for row in documents]}


async def create_share(principal, workspace_id, request_id, kind, resource_id, version):
    fingerprint = identity({'type':kind,'resource_id':str(resource_id),'version':version})
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
        await actor(conn,principal)
        await locked_workspace(conn,workspace_id)
        await membership(conn,workspace_id,principal.id)
        old = await conn.fetchrow('''SELECT id,request_fingerprint,revoked_at FROM collaboration_shares
            WHERE workspace_id=$1::uuid AND owner_id=$2::uuid AND request_id=$3::uuid''',str(workspace_id),principal.id,str(request_id))
        if old:
            if old['request_fingerprint'] != fingerprint: raise ValueError('workspace_request_conflict')
            return {'id':str(old['id']),'state':'revoked' if old['revoked_at'] else 'active','replayed':True}
        if not await _resource(conn,principal.id,kind,resource_id,version):
            raise ValueError('workspace_resource_not_found')
        existing = await conn.fetchval('''SELECT id FROM collaboration_shares WHERE workspace_id=$1::uuid
            AND owner_id=$2::uuid AND resource_type=$3 AND resource_id=$4::uuid AND resource_version=$5 AND revoked_at IS NULL''',
            str(workspace_id),principal.id,kind,str(resource_id),version)
        if existing: raise ValueError('workspace_share_exists')
        if await conn.fetchval('''SELECT COUNT(*) FROM collaboration_shares
            WHERE workspace_id=$1::uuid AND revoked_at IS NULL''',str(workspace_id)) >= 500:
            raise ValueError('workspace_share_limit')
        share_id = await conn.fetchval('''INSERT INTO collaboration_shares
            (workspace_id,owner_id,resource_type,resource_id,resource_version,request_id,request_fingerprint)
            VALUES($1::uuid,$2::uuid,$3,$4::uuid,$5,$6::uuid,$7) RETURNING id''',
            str(workspace_id),principal.id,kind,str(resource_id),version,str(request_id),fingerprint)
        return {'id':str(share_id),'state':'active','replayed':False}


async def list_shares(principal, workspace_id):
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
        await actor(conn,principal)
        await locked_workspace(conn,workspace_id)
        await membership(conn,workspace_id,principal.id)
        rows = await conn.fetch('''SELECT s.*,p.username FROM collaboration_shares s
            JOIN collaboration_members m ON m.workspace_id=s.workspace_id AND m.principal_id=s.owner_id AND m.state='active'
            JOIN auth_principals p ON p.id=s.owner_id AND p.is_active
            WHERE s.workspace_id=$1::uuid AND s.revoked_at IS NULL ORDER BY s.created_at DESC,s.id LIMIT 500''',str(workspace_id))
        items = []
        for row in rows:
            resource = await _resource(conn,row['owner_id'],row['resource_type'],row['resource_id'],row['resource_version'])
            # The owner can still see and withdraw a share whose source became unavailable.
            if not resource and str(row['owner_id']) != principal.id: continue
            items.append({'id':str(row['id']),'type':row['resource_type'],'owner_id':str(row['owner_id']),
                'owner':row['username'],'available':bool(resource),'title':resource['title'] if resource else None,
                'created_at':row['created_at'].isoformat()})
    return items


async def read_share(principal, workspace_id, share_id):
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
        await actor(conn,principal)
        await locked_workspace(conn,workspace_id)
        await membership(conn,workspace_id,principal.id)
        row = await conn.fetchrow('''SELECT s.*,p.username FROM collaboration_shares s
            JOIN collaboration_members m ON m.workspace_id=s.workspace_id AND m.principal_id=s.owner_id AND m.state='active'
            JOIN auth_principals p ON p.id=s.owner_id AND p.is_active
            WHERE s.workspace_id=$1::uuid AND s.id=$2::uuid AND s.revoked_at IS NULL FOR SHARE OF s''',str(workspace_id),str(share_id))
        if not row: raise ValueError('workspace_resource_not_found')
        resource = await _resource(conn,row['owner_id'],row['resource_type'],row['resource_id'],row['resource_version'],content=True)
        if not resource: raise ValueError('workspace_resource_not_found')
        # The report body is shared intentionally. Private citation records and source APIs are not.
        return {'id':str(row['id']),'type':row['resource_type'],'owner':row['username'],**resource}


async def revoke_share(principal, workspace_id, share_id):
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
        await actor(conn,principal)
        await locked_workspace(conn,workspace_id)
        await membership(conn,workspace_id,principal.id)
        row = await conn.fetchrow('''SELECT revoked_at FROM collaboration_shares
            WHERE workspace_id=$1::uuid AND id=$2::uuid AND owner_id=$3::uuid FOR UPDATE''',str(workspace_id),str(share_id),principal.id)
        if not row: raise ValueError('workspace_resource_not_found')
        if row['revoked_at']: return {'state':'revoked','replayed':True}
        await conn.execute('UPDATE collaboration_shares SET revoked_at=NOW() WHERE id=$1::uuid',str(share_id))
        return {'state':'revoked','replayed':False}
