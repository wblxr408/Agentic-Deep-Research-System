"""Per-owner default baselines for immutable personal skill revisions."""

SCHEMA_SQL = '''
CREATE TABLE IF NOT EXISTS skill_default_transitions (
 owner_id UUID NOT NULL REFERENCES auth_principals(id) ON DELETE CASCADE,
 skill_id UUID NOT NULL REFERENCES skill_meta(id) ON DELETE CASCADE,
 personal_version INTEGER NOT NULL,
 bundle_slug TEXT NOT NULL,
 baseline_hash CHAR(64) NOT NULL,
 baseline_markdown TEXT NOT NULL,
 provenance TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 PRIMARY KEY(owner_id,skill_id,personal_version)
);
CREATE INDEX IF NOT EXISTS idx_skill_default_lineage
 ON skill_default_transitions(owner_id,skill_id,personal_version DESC);
'''
