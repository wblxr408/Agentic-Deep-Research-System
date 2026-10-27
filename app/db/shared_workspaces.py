"""Member-scoped workspaces; personal resources keep their original owner."""
from __future__ import annotations

from app.db.connection import get_db_pool
from app.query_understanding import identity
from app.security.account_recovery import _require_current_credential


async def actor(conn, principal):
    active = await conn.fetchval('SELECT is_active FROM auth_principals WHERE id=$1::uuid FOR SHARE', principal.id)
    if not active: raise ValueError('workspace_authentication_required')
    await _require_current_credential(conn, principal)


async def locked_workspace(conn, workspace_id):
    row = await conn.fetchrow('''SELECT w.id,w.owner_id,w.name,w.archived_at,p.is_active AS owner_active
        FROM collaboration_workspaces w JOIN auth_principals p ON p.id=w.owner_id
        WHERE w.id=$1::uuid FOR UPDATE OF w''', str(workspace_id))
    if not row or row['archived_at'] or not row['owner_active']: raise ValueError('workspace_not_found')
    return row


async def membership(conn, workspace_id, principal_id, *, owner=False):
    row = await conn.fetchrow('''SELECT role,state FROM collaboration_members WHERE workspace_id=$1::uuid
        AND principal_id=$2::uuid''', str(workspace_id), principal_id)
    if not row or row['state'] != 'active': raise ValueError('workspace_not_found')
    if owner and row['role'] != 'owner': raise ValueError('workspace_owner_required')
    return row


async def create_workspace(principal, request_id, name):
    fingerprint = identity({'name': name})
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
        await actor(conn,principal)
        # Serializes retries and capacity for this owner across workers.
        await conn.execute('SELECT pg_advisory_xact_lock(hashtextextended($1,0))','workspace-owner:'+principal.id)
        old = await conn.fetchrow('''SELECT id,name,archived_at,request_fingerprint FROM collaboration_workspaces
            WHERE owner_id=$1::uuid AND request_id=$2::uuid''', principal.id,str(request_id))
        if old:
            if old['request_fingerprint'] != fingerprint: raise ValueError('workspace_request_conflict')
            return {'id':str(old['id']),'name':old['name'],'archived':bool(old['archived_at']),'replayed':True}
        if await conn.fetchval('SELECT COUNT(*) FROM collaboration_workspaces WHERE owner_id=$1::uuid AND archived_at IS NULL',principal.id) >= 50:
            raise ValueError('workspace_limit')
        row = await conn.fetchrow('''INSERT INTO collaboration_workspaces(owner_id,name,request_id,request_fingerprint)
            VALUES($1::uuid,$2,$3::uuid,$4) RETURNING id''',principal.id,name,str(request_id),fingerprint)
        await conn.execute('''INSERT INTO collaboration_members(workspace_id,principal_id,role,state)
            VALUES($1,$2::uuid,'owner','active')''',row['id'],principal.id)
        return {'id':str(row['id']),'name':name,'archived':False,'replayed':False}


async def list_workspaces(principal):
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
        await actor(conn,principal)
        rows = await conn.fetch('''SELECT w.id,w.name,w.owner_id,w.created_at,m.role
            FROM collaboration_workspaces w JOIN collaboration_members m ON m.workspace_id=w.id
            JOIN auth_principals p ON p.id=w.owner_id
            WHERE m.principal_id=$1::uuid AND m.state='active' AND w.archived_at IS NULL AND p.is_active=TRUE
            ORDER BY w.created_at DESC,w.id LIMIT 100''',principal.id)
    return [{'id':str(row['id']),'name':row['name'],'owner_id':str(row['owner_id']),
             'role':row['role'],'created_at':row['created_at'].isoformat()} for row in rows]


async def workspace_detail(principal, workspace_id):
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
        await actor(conn,principal)
        workspace = await locked_workspace(conn,workspace_id)
        own = await membership(conn,workspace_id,principal.id)
        rows = await conn.fetch('''SELECT m.principal_id,m.role,m.joined_at,p.username
            FROM collaboration_members m JOIN auth_principals p ON p.id=m.principal_id
            WHERE m.workspace_id=$1::uuid AND m.state='active' AND p.is_active=TRUE
            ORDER BY m.joined_at,m.principal_id LIMIT 100''',str(workspace_id))
        invites = await conn.fetch('''SELECT i.id,p.username,i.created_at,i.expires_at
            FROM collaboration_invitations i JOIN auth_principals p ON p.id=i.invitee_id
            WHERE i.workspace_id=$1::uuid AND i.state='pending' AND i.expires_at>NOW()
            ORDER BY i.created_at,i.id LIMIT 100''',str(workspace_id)) if own['role']=='owner' else []
    return {'id':str(workspace['id']),'name':workspace['name'],'role':own['role'],
        'members':[{'id':str(row['principal_id']),'username':row['username'],'role':row['role'],
                    'joined_at':row['joined_at'].isoformat()} for row in rows],
        'invitations':[{'id':str(row['id']),'username':row['username'],'created_at':row['created_at'].isoformat(),
                        'expires_at':row['expires_at'].isoformat()} for row in invites]}


async def invite(principal, workspace_id, request_id, username):
    username = username.strip().lower()
    fingerprint = identity({'workspace_id':str(workspace_id),'username':username})
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
        await actor(conn,principal)
        await locked_workspace(conn,workspace_id)
        await membership(conn,workspace_id,principal.id,owner=True)
        old = await conn.fetchrow('''SELECT id,CASE WHEN state='pending' AND expires_at<=NOW() THEN 'expired' ELSE state END AS state,
            request_fingerprint FROM collaboration_invitations
            WHERE workspace_id=$1::uuid AND inviter_id=$2::uuid AND request_id=$3::uuid''',
            str(workspace_id),principal.id,str(request_id))
        if old:
            if old['request_fingerprint'] != fingerprint: raise ValueError('workspace_request_conflict')
            return {'id':str(old['id']),'state':old['state'],'replayed':True}
        target = await conn.fetchrow('SELECT id,is_active FROM auth_principals WHERE username=$1 FOR SHARE', username)
        if not target or not target['is_active']: raise ValueError('workspace_account_not_found')
        if str(target['id']) == principal.id: raise ValueError('workspace_already_member')
        active = await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM collaboration_members WHERE workspace_id=$1::uuid
            AND principal_id=$2 AND state='active')''',str(workspace_id),target['id'])
        if active: raise ValueError('workspace_already_member')
        await conn.execute('''UPDATE collaboration_invitations SET state='expired',updated_at=NOW()
            WHERE workspace_id=$1::uuid AND state='pending' AND expires_at<=NOW()''',str(workspace_id))
        if await conn.fetchval('''SELECT EXISTS(SELECT 1 FROM collaboration_invitations WHERE workspace_id=$1::uuid
            AND invitee_id=$2 AND state='pending')''',str(workspace_id),target['id']):
            raise ValueError('workspace_invitation_exists')
        count = await conn.fetchval('''SELECT (SELECT COUNT(*) FROM collaboration_members WHERE workspace_id=$1::uuid AND state='active') +
            (SELECT COUNT(*) FROM collaboration_invitations WHERE workspace_id=$1::uuid AND state='pending')''',str(workspace_id))
        if count >= 100: raise ValueError('workspace_member_limit')
        row = await conn.fetchrow('''INSERT INTO collaboration_invitations(workspace_id,inviter_id,invitee_id,request_id,request_fingerprint,state,expires_at)
            VALUES($1::uuid,$2::uuid,$3,$4::uuid,$5,'pending',NOW()+INTERVAL '7 days') RETURNING id''',
            str(workspace_id),principal.id,target['id'],str(request_id),fingerprint)
        return {'id':str(row['id']),'state':'pending','replayed':False}


async def invitations(principal):
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
        await actor(conn,principal)
        rows = await conn.fetch('''SELECT i.id,i.workspace_id,i.expires_at,w.name,p.username AS inviter
            FROM collaboration_invitations i JOIN collaboration_workspaces w ON w.id=i.workspace_id
            JOIN auth_principals p ON p.id=w.owner_id
            WHERE i.invitee_id=$1::uuid AND i.state='pending' AND i.expires_at>NOW()
                AND w.archived_at IS NULL AND p.is_active=TRUE
            ORDER BY i.created_at,i.id LIMIT 100''',principal.id)
    return [{'id':str(row['id']),'workspace_id':str(row['workspace_id']),'workspace_name':row['name'],
             'inviter':row['inviter'],'expires_at':row['expires_at'].isoformat()} for row in rows]


async def respond_invitation(principal, invite_id, accept):
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
        await actor(conn,principal)
        workspace_id = await conn.fetchval('''SELECT workspace_id FROM collaboration_invitations
            WHERE id=$1::uuid AND invitee_id=$2::uuid''',str(invite_id),principal.id)
        if not workspace_id: raise ValueError('workspace_invitation_not_found')
        await locked_workspace(conn,workspace_id)
        row = await conn.fetchrow('''SELECT state,expires_at FROM collaboration_invitations
            WHERE id=$1::uuid AND invitee_id=$2::uuid FOR UPDATE''',str(invite_id),principal.id)
        desired = 'accepted' if accept else 'declined'
        if row['state'] == desired:
            member = await conn.fetchval('''SELECT state FROM collaboration_members
                WHERE workspace_id=$1 AND principal_id=$2::uuid''',workspace_id,principal.id)
            return {'state':desired,'membership':member,'replayed':True}
        if row['state'] != 'pending': raise ValueError('workspace_invitation_closed')
        live = await conn.fetchval('SELECT $1::timestamptz>NOW()',row['expires_at'])
        if not live: raise ValueError('workspace_invitation_expired')
        await conn.execute('UPDATE collaboration_invitations SET state=$2,updated_at=NOW() WHERE id=$1::uuid',str(invite_id),desired)
        if accept:
            await conn.execute('''INSERT INTO collaboration_members(workspace_id,principal_id,role,state)
                VALUES($1,$2::uuid,'member','active') ON CONFLICT(workspace_id,principal_id) DO UPDATE
                SET state='active',joined_at=NOW(),updated_at=NOW()''',workspace_id,principal.id)
        return {'state':desired,'membership':'active' if accept else None,'replayed':False}


async def remove_member(principal, workspace_id, target_id):
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
        await actor(conn,principal)
        await locked_workspace(conn,workspace_id)
        if str(target_id) == principal.id:
            prior = await conn.fetchval('''SELECT state FROM collaboration_members WHERE workspace_id=$1::uuid
                AND principal_id=$2::uuid''',str(workspace_id),principal.id)
            if prior=='left': return {'state':'left','replayed':True}
        own = await membership(conn,workspace_id,principal.id)
        if str(target_id) != principal.id and own['role'] != 'owner': raise ValueError('workspace_owner_required')
        target = await conn.fetchrow('''SELECT role,state FROM collaboration_members WHERE workspace_id=$1::uuid
            AND principal_id=$2::uuid''',str(workspace_id),str(target_id))
        if not target: raise ValueError('workspace_member_not_found')
        if target['role']=='owner': raise ValueError('workspace_owner_cannot_leave')
        state = 'left' if str(target_id)==principal.id else 'removed'
        if target['state']=='active':
            await conn.execute('''UPDATE collaboration_members SET state=$3,updated_at=NOW()
                WHERE workspace_id=$1::uuid AND principal_id=$2::uuid''',str(workspace_id),str(target_id),state)
            # A later invitation must not silently reactivate the departing member's grants.
            await conn.execute('''UPDATE collaboration_shares SET revoked_at=NOW()
                WHERE workspace_id=$1::uuid AND owner_id=$2::uuid AND revoked_at IS NULL''',str(workspace_id),str(target_id))
        return {'state':state if target['state']=='active' else target['state'],'replayed':target['state']!='active'}


async def revoke_invitation(principal, workspace_id, invite_id):
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
        await actor(conn,principal)
        await locked_workspace(conn,workspace_id)
        await membership(conn,workspace_id,principal.id,owner=True)
        row = await conn.fetchrow('''SELECT state FROM collaboration_invitations WHERE workspace_id=$1::uuid
            AND id=$2::uuid FOR UPDATE''',str(workspace_id),str(invite_id))
        if not row: raise ValueError('workspace_invitation_not_found')
        if row['state']=='pending':
            await conn.execute("UPDATE collaboration_invitations SET state='revoked',updated_at=NOW() WHERE id=$1::uuid",str(invite_id))
            return {'state':'revoked','replayed':False}
        if row['state']=='revoked': return {'state':'revoked','replayed':True}
        raise ValueError('workspace_invitation_closed')


async def archive_workspace(principal, workspace_id):
    pool = await get_db_pool()
    async with pool.acquire() as conn, conn.transaction():
        await actor(conn,principal)
        row = await conn.fetchrow('''SELECT owner_id,archived_at FROM collaboration_workspaces
            WHERE id=$1::uuid FOR UPDATE''',str(workspace_id))
        if not row or str(row['owner_id']) != principal.id: raise ValueError('workspace_not_found')
        if row['archived_at']: return {'status':'archived','replayed':True}
        await membership(conn,workspace_id,principal.id,owner=True)
        await conn.execute('UPDATE collaboration_workspaces SET archived_at=NOW() WHERE id=$1::uuid',str(workspace_id))
    return {'status':'archived','replayed':False}
