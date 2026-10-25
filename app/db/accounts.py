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
ALTER TABLE skill_meta DROP CONSTRAINT IF EXISTS skill_meta_slug_key;
CREATE UNIQUE INDEX IF NOT EXISTS idx_skill_meta_owner_slug ON skill_meta(owner_id,slug);
"""


async def migrate_accounts(conn) -> None:
    # The same lock protects schema repeatability, bootstrap and account changes.
    async with conn.transaction():
        await conn.execute('SELECT pg_advisory_xact_lock(73120401)')
        await conn.execute(SCHEMA_SQL)
