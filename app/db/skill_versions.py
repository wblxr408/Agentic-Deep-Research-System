"""Per-owner default baselines for immutable personal skill revisions."""

SCHEMA_SQL = '''
CREATE TABLE IF NOT EXISTS skill_registry_generations (
 owner_id UUID PRIMARY KEY REFERENCES auth_principals(id) ON DELETE CASCADE,
 generation BIGINT NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS skill_default_transitions (
 owner_id UUID NOT NULL REFERENCES auth_principals(id) ON DELETE CASCADE,
 skill_id UUID NOT NULL REFERENCES skill_meta(id) ON DELETE CASCADE,
 personal_version INTEGER NOT NULL,
 bundle_slug TEXT,
 baseline_hash CHAR(64),
 baseline_markdown TEXT,
 baseline_release TEXT,
 provenance TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(owner_id,skill_id,personal_version)
);
ALTER TABLE skill_default_transitions ALTER COLUMN bundle_slug DROP NOT NULL;
ALTER TABLE skill_default_transitions ALTER COLUMN baseline_hash DROP NOT NULL;
ALTER TABLE skill_default_transitions ALTER COLUMN baseline_markdown DROP NOT NULL;
ALTER TABLE skill_default_transitions ADD COLUMN IF NOT EXISTS baseline_release TEXT;
CREATE INDEX IF NOT EXISTS idx_skill_default_lineage
 ON skill_default_transitions(owner_id,skill_id,personal_version DESC);
'''
