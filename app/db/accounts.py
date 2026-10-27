"""Incremental, repeatable account migration shared by both schema entrypoints."""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS auth_principals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(120) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    session_version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
ALTER TABLE auth_principals ADD COLUMN IF NOT EXISTS role VARCHAR(16);
UPDATE auth_principals SET role = CASE
    WHEN id=(SELECT id FROM auth_principals ORDER BY created_at,id LIMIT 1) THEN 'admin'
    ELSE 'user' END WHERE role IS NULL;
ALTER TABLE auth_principals ALTER COLUMN role SET DEFAULT 'user';
ALTER TABLE auth_principals ALTER COLUMN role SET NOT NULL;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='auth_principals_role_check'
                   AND conrelid='auth_principals'::regclass) THEN
        ALTER TABLE auth_principals ADD CONSTRAINT auth_principals_role_check CHECK(role IN ('user','admin'));
    END IF;
END $$;
CREATE TABLE IF NOT EXISTS auth_registration_policy (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK(singleton),
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
INSERT INTO auth_registration_policy(singleton) VALUES(TRUE) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS auth_verified_emails (
    principal_id UUID PRIMARY KEY REFERENCES auth_principals(id) ON DELETE CASCADE,
    address TEXT NOT NULL UNIQUE,
    verified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS auth_email_challenges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    principal_id UUID NOT NULL REFERENCES auth_principals(id) ON DELETE CASCADE,
    address TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('verify','reset')),
    token_hash TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_auth_email_challenge_principal
    ON auth_email_challenges(principal_id,kind,created_at DESC);
CREATE TABLE IF NOT EXISTS auth_email_rate_limits (
    key_hash TEXT NOT NULL,
    action TEXT NOT NULL,
    window_start TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    requests INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(key_hash,action)
);
CREATE INDEX IF NOT EXISTS idx_auth_email_rate_window ON auth_email_rate_limits(window_start);
CREATE TABLE IF NOT EXISTS collaboration_workspaces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID NOT NULL REFERENCES auth_principals(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    request_id UUID NOT NULL,
    request_fingerprint TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archived_at TIMESTAMPTZ,
    UNIQUE(owner_id,request_id)
);
CREATE TABLE IF NOT EXISTS collaboration_members (
    workspace_id UUID NOT NULL REFERENCES collaboration_workspaces(id) ON DELETE CASCADE,
    principal_id UUID NOT NULL REFERENCES auth_principals(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('owner','member')),
    state TEXT NOT NULL CHECK(state IN ('active','removed','left')),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY(workspace_id,principal_id)
);
CREATE INDEX IF NOT EXISTS idx_collaboration_member ON collaboration_members(principal_id,state,workspace_id);
CREATE TABLE IF NOT EXISTS collaboration_invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES collaboration_workspaces(id) ON DELETE CASCADE,
    inviter_id UUID NOT NULL REFERENCES auth_principals(id) ON DELETE CASCADE,
    invitee_id UUID NOT NULL REFERENCES auth_principals(id) ON DELETE CASCADE,
    request_id UUID NOT NULL,
    request_fingerprint TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('pending','accepted','declined','revoked','expired')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id,inviter_id,request_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_collaboration_pending_invite
    ON collaboration_invitations(workspace_id,invitee_id) WHERE state='pending';
CREATE INDEX IF NOT EXISTS idx_collaboration_invitations_invitee
    ON collaboration_invitations(invitee_id,state,created_at DESC);
ALTER TABLE skill_meta DROP CONSTRAINT IF EXISTS skill_meta_slug_key;
CREATE UNIQUE INDEX IF NOT EXISTS idx_skill_meta_owner_slug ON skill_meta(owner_id,slug);
"""


async def migrate_accounts(conn) -> None:
    # The same lock protects schema repeatability, bootstrap and account changes.
    async with conn.transaction():
        await conn.execute('SELECT pg_advisory_xact_lock(73120401)')
        await conn.execute(SCHEMA_SQL)
